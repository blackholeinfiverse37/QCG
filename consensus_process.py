"""
consensus_process.py — Phase 2: Independent Consensus OS Process

Receives ExecutionResult messages, collects attestations from independent
consensus nodes, and emits a ConsensusProof.

IPC contract (input Queue message):
  { "type": "EXECUTION_RESULT", "result": {...}, "issued_at": <float> }

IPC contract (output Queue message):
  { "type": "CONSENSUS_PROOF", "proof": {...} }

On crash, process exits with code 1.
"""

import json
import os
import sys
import time


def run(in_port: int, out_port: int, crash: bool = False, hb_port: int = 9103) -> None:
    pid = os.getpid()
    _log(pid, "CONSENSUS", "started")

    if crash:
        _log(pid, "CONSENSUS", "simulated crash")
        sys.exit(1)

    from consensus_simulation import DistributedConsensusNode, ConsensusEngine
    from execution_contract import ComputationExecutionContract
    from network_ipc import IPCReceiver, IPCSender, start_heartbeat_server

    start_heartbeat_server(hb_port)
    queue_in = IPCReceiver(port=in_port)
    queue_out = IPCSender(port=out_port)

    # Three independent consensus nodes
    nodes = [
        DistributedConsensusNode("CONS_NODE_A"),
        DistributedConsensusNode("CONS_NODE_B"),
        DistributedConsensusNode("CONS_NODE_C"),
    ]
    engine = ConsensusEngine(nodes)

    while True:
        msg = queue_in.get()
        if msg.get("type") == "DONE":
            _log(pid, "CONSENSUS", "received DONE, shutting down")
            queue_out.put({"type": "DONE"})
            queue_in.close()
            queue_out.close()
            break

        if msg.get("type") != "EXECUTION_RESULT":
            continue

        result_raw = msg["result"]
        if "HALT" in result_raw.get("ack", ""):
            _log(pid, "CONSENSUS", "skipping halted result", ack=result_raw.get("ack"))
            queue_out.put({"type": "CONSENSUS_PROOF", "proof": {"consensus_reached": False,
                           "reason": result_raw.get("ack")}})
            continue

        # Reconstruct the signed contract from the IPC message
        contract_raw = msg.get("contract")
        pub_key = msg.get("producer_public_key")
        if not contract_raw or not pub_key:
            _log(pid, "CONSENSUS", "missing contract or public_key in message")
            continue

        try:
            signed = ComputationExecutionContract(**contract_raw)
        except Exception as exc:
            _log(pid, "CONSENSUS", "contract_reconstruction_error", error=str(exc))
            continue

        proof = engine.run_consensus(signed, pub_key)
        _log(pid, "CONSENSUS", "consensus_complete",
             message_id=signed.trace_id,
             status="REACHED" if proof.consensus_reached else "FAILED",
             agreement=f"{proof.agreement_percentage:.0%}")

        queue_out.put({"type": "CONSENSUS_PROOF", "proof": proof.to_dict()})

    _log(pid, "CONSENSUS", "finished")


def _log(pid: int, role: str, event: str, **kwargs) -> None:
    entry = {
        "process_id":      pid,
        "role":            role,
        "event":           event,
        "message_id":      kwargs.pop("message_id", ""),
        "sequence_number": kwargs.pop("sequence_number", 0),
        "status":          kwargs.pop("status", ""),
        "timestamp":       time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        **kwargs,
    }
    line = json.dumps(entry)
    print(line, flush=True)
    _append_log("logs/process_3.log", line)


def _append_log(path: str, line: str) -> None:
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass
