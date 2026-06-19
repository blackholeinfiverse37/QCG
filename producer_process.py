"""
producer_process.py — Phase 2: Independent Producer OS Process

Produces a signed ComputationExecutionContract and puts it on an IPC Queue.
Intended to be spawned as a separate OS process by process_runner.py.

IPC contract (Queue message schema):
  {
    "type": "CONTRACT",
    "contract": { ...ComputationExecutionContract.to_dict()... },
    "producer_public_key": "<hex>",
    "issued_at": <float monotonic-equivalent via time.time()>
  }

On completion, sends:
  { "type": "DONE" }

On crash, the process exits with code 1 — the runner detects absence of DONE.
"""

import json
import logging
import os
import sys
import time


def run(out_port: int, crash: bool = False, hb_port: int = 9101) -> None:
    pid = os.getpid()
    _log(pid, "PRODUCER", "started")

    if crash:
        _log(pid, "PRODUCER", "simulated crash")
        sys.exit(1)

    # Import inside the process to avoid multiprocessing pickling issues
    from execution_contract import ComputationExecutionContract
    from node_identity import NodeSigner
    from provenance import sign_contract
    from network_ipc import IPCSender, start_heartbeat_server
    
    start_heartbeat_server(hb_port)
    queue_out = IPCSender(port=out_port)

    producer = NodeSigner("PROC_PRODUCER_01", "QUANTUM_PRODUCER")

    contract = ComputationExecutionContract(
        producer_type="QUANTUM",
        payload={"data": "process_entangled_pair", "source": "producer_process"},
        confidence=0.97,
        trace_id="proc-trace-001",
        contract_version="2.0.0",
    )
    signed = sign_contract(contract, producer)

    msg = {
        "type": "CONTRACT",
        "contract": signed.to_dict(),
        "producer_public_key": producer.identity.public_key,
        "issued_at": time.time(),
    }
    queue_out.put(msg)
    _log(pid, "PRODUCER", "contract_sent",
         message_id=contract.trace_id,
         status="SENT")

    queue_out.put({"type": "DONE"})
    queue_out.close()
    _log(pid, "PRODUCER", "finished")


def _log(pid: int, role: str, event: str, **kwargs) -> None:
    entry = {
        "process_id":     pid,
        "role":           role,
        "event":          event,
        "message_id":     kwargs.pop("message_id", ""),
        "sequence_number": kwargs.pop("sequence_number", 0),
        "status":         kwargs.pop("status", ""),
        "timestamp":      time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        **kwargs,
    }
    line = json.dumps(entry)
    print(line, flush=True)
    _append_log("logs/process_1.log", line)


def _append_log(path: str, line: str) -> None:
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


if __name__ == "__main__":
    import multiprocessing
    q: multiprocessing.Queue = multiprocessing.Queue()
    run(q)
    while not q.empty():
        print(q.get())
