"""
execution_process.py — Phase 2: Independent Execution OS Process

Receives a signed contract from the producer queue, executes it through
RuntimeCore, and sends the ExecutionResult to the consensus queue.

IPC contract (input Queue message):
  { "type": "CONTRACT", "contract": {...}, "producer_public_key": "<hex>", "issued_at": <float> }

IPC contract (output Queue message):
  { "type": "EXECUTION_RESULT", "result": {...}, "issued_at": <float> }

On crash, process exits with code 1.
"""

import json
import os
import sys
import time


def run(queue_in, queue_out, crash: bool = False) -> None:
    pid = os.getpid()
    _log(pid, "EXECUTION", "started")

    if crash:
        _log(pid, "EXECUTION", "simulated crash")
        sys.exit(1)

    from execution_contract import ComputationExecutionContract
    from runtime_core import RuntimeCore
    from replay_enforcer import ReplayEnforcer
    from producer_verification import ProducerRegistry, ProducerVerificationLayer
    import config

    runtime = RuntimeCore()
    enforcer = ReplayEnforcer(ttl_seconds=config.REPLAY_TTL_SECONDS)
    # Trust layer: registry is populated from producer_public_key in each IPC message
    _trust_registry = ProducerRegistry()
    verifier = ProducerVerificationLayer(_trust_registry)

    while True:
        msg = queue_in.get()
        if msg.get("type") == "DONE":
            _log(pid, "EXECUTION", "received DONE, shutting down")
            queue_out.put({"type": "DONE"})
            break

        if msg.get("type") != "CONTRACT":
            continue

        raw = msg["contract"]
        pub_key = msg["producer_public_key"]
        issued_at_wall = msg.get("issued_at", time.time())
        # Convert wall time to monotonic-equivalent offset
        age = time.time() - issued_at_wall
        issued_at_mono = time.monotonic() - age

        # Replay enforcement
        decision = enforcer.submit(raw["trace_id"], issued_at=issued_at_mono)
        _log(pid, "EXECUTION", "replay_check",
             message_id=raw["trace_id"],
             sequence_number=decision.sequence_id,
             status=decision.status)

        if decision.status != "ACCEPTED":
            queue_out.put({
                "type": "EXECUTION_RESULT",
                "result": {"ack": f"HALT:{decision.status}", "trace_id": raw["trace_id"]},
                "issued_at": time.time(),
            })
            continue

        try:
            contract = ComputationExecutionContract(**raw)
        except Exception as exc:
            _log(pid, "EXECUTION", "contract_construction_error",
                 trace_id=raw.get("trace_id", "unknown"), error=str(exc))
            queue_out.put({
                "type": "EXECUTION_RESULT",
                "result": {"ack": f"HALT:INVALID_CONTRACT:{exc}",
                            "trace_id": raw.get("trace_id", "unknown")},
                "issued_at": time.time(),
            })
            continue

        # Trust verification: register producer on-the-fly from IPC-supplied public key
        # then verify identity, signature, and type in one call.
        from node_identity import NodeIdentity
        if not _trust_registry.is_registered(contract.producer_id):
            identity = NodeIdentity(
                node_id=contract.producer_id,
                public_key=pub_key,
                node_role="PRODUCER",
                version="1.0.0",
            )
            _trust_registry.register(identity, allowed_types={contract.producer_type})

        trust_result = verifier.verify(contract)
        if not trust_result.passed:
            _log(pid, "EXECUTION", "trust_verification_failed",
                 message_id=contract.trace_id,
                 status=trust_result.failure_mode,
                 reason=trust_result.reason)
            queue_out.put({
                "type": "EXECUTION_RESULT",
                "result": {"ack": trust_result.halt_signal(), "trace_id": contract.trace_id},
                "issued_at": time.time(),
            })
            continue

        result = runtime.execute(contract)
        _log(pid, "EXECUTION", "executed",
             message_id=result.contract_trace_id,
             sequence_number=decision.sequence_id,
             status=result.ack,
             runtime_hash=result.runtime_hash[:16])

        queue_out.put({
            "type": "EXECUTION_RESULT",
            "result": result.to_dict(),
            "contract": raw,
            "producer_public_key": pub_key,
            "issued_at": time.time(),
        })

    _log(pid, "EXECUTION", "finished")


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
    _append_log("logs/process_2.log", line)


def _append_log(path: str, line: str) -> None:
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass
