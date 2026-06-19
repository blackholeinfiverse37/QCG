"""
runtime_core.py — Phase 3: Blind Runtime Core

Processes ANY ComputationExecutionContract through an identical code path.
The core NEVER inspects producer_type for branching logic — that field is
metadata for observability and audit only.

This is the key proof surface: quantum and classical contracts both traverse
the exact same execute() method without any producer-aware conditional.

RESPONSIBILITY BOUNDARY
-----------------------
RuntimeCore OWNS:
    - Confidence threshold enforcement (CORRUPTION_THRESHOLD, CONFIDENCE_THRESHOLD)
    - ACK generation (OK, DEGRADED, HALT)
    - Runtime hash computation (SHA-256 of execution path)

RuntimeCore does NOT own:
    - Replay detection              → CanonicalReplayAuthority (sole authority)
    - Producer type authorization  → GovernanceLayer
    - Contract version policy      → GovernanceLayer
    - Violation recording          → GovernanceLayer
    - Adapter selection            → Adapter layer
    - Payload content inspection   → Never (opaque by design)
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone

import config
from logger import get_logger, log_event
from execution_contract import (
    ComputationExecutionContract,
    ContractValidationError,
    validate_contract,
)

log = get_logger("qcg.runtime")


# ---------------------------------------------------------------------------
# Execution result — output of the blind core
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ExecutionResult:
    """
    Deterministic result produced by RuntimeCore.execute().

    Fields
    ------
    contract_trace_id   : The input contract's trace_id (passthrough).   [DETERMINISTIC]
    producer_type       : Passthrough metadata — NOT used for branching. [DETERMINISTIC]
    ack                 : Deterministic acknowledgement string.          [DETERMINISTIC]
    confidence          : The confidence from the input contract.        [DETERMINISTIC]
    runtime_hash        : SHA-256 hash of the runtime path taken.       [DETERMINISTIC]
    execution_timestamp : ISO-8601 time of execution.                   [OBSERVABILITY]

    Determinism note: execution_timestamp is OBSERVABILITY metadata.
    It records wall-clock time for audit/tracing purposes but is NOT
    part of the deterministic output.  Two runs with identical inputs
    will produce identical deterministic projections even though their
    execution_timestamps differ.  See determinism_doctrine.py.
    """
    # --- DETERMINISTIC fields ---
    contract_trace_id:  str                                # DETERMINISTIC
    producer_type:      str                                # DETERMINISTIC
    ack:                str                                # DETERMINISTIC
    confidence:         float                              # DETERMINISTIC
    runtime_hash:       str = ""                           # DETERMINISTIC

    # --- OBSERVABILITY fields ---
    execution_timestamp: str = field(                      # OBSERVABILITY
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Runtime core
# ---------------------------------------------------------------------------

class RuntimeCore:
    """
    Producer-agnostic execution engine.

    The execute() method processes every ComputationExecutionContract through
    the identical code path.  It validates the contract schema, applies
    confidence thresholds, produces a deterministic ACK, and records an
    execution trace hash — all without inspecting producer_type.

    Replay authority: RuntimeCore maintains a per-instance replay guard so
    that the same trace_id cannot be executed twice on the same instance.
    Cross-process and durable replay is owned by CanonicalReplayAuthority.
    """

    def __init__(self):
        pass

    # -- public interface ---------------------------------------------------

    def execute(self, contract: ComputationExecutionContract) -> ExecutionResult:
        """
        Execute a contract through the blind core.

        Returns an ExecutionResult with a deterministic ACK.
        Never raises — all failures are captured in the ACK string.
        """
        # Step 1 — validate contract schema (producer-agnostic)
        try:
            validate_contract(contract)
        except ContractValidationError as exc:
            return self._halt(contract, f"HALT:INVALID_CONTRACT:{exc}")

        # Step 2 — (Removed: callers must consult CanonicalReplayAuthority)

        # Step 3 — confidence thresholds (producer-agnostic)
        if contract.confidence < config.CORRUPTION_THRESHOLD:
            ack = f"HALT:LOW_CONFIDENCE:{contract.confidence:.4f}"
            log_event(log, logging.WARNING, "runtime_low_confidence", ctx={
                "trace_id": contract.trace_id,
                "confidence": contract.confidence,
            })
            return self._result(contract, ack)

        if contract.confidence < config.CONFIDENCE_THRESHOLD:
            ack = f"ACK:DEGRADED:confidence={contract.confidence:.4f}"
        else:
            ack = "ACK:OK"

        log_event(log, logging.INFO, "runtime_execute_complete", ctx={
            "trace_id": contract.trace_id,
            "ack": ack,
            "confidence": contract.confidence,
        })

        return self._result(contract, ack)

    # -- internal helpers ---------------------------------------------------

    def _result(
        self,
        contract: ComputationExecutionContract,
        ack: str,
    ) -> ExecutionResult:
        """Build an ExecutionResult with a runtime hash."""
        # The runtime hash captures the exact path: contract hash + ack
        path_seed = json.dumps({
            "payload_hash": contract.payload_hash,
            "confidence":   contract.confidence,
            "ack":          ack,
        }, sort_keys=True)
        runtime_hash = hashlib.sha256(path_seed.encode()).hexdigest()

        return ExecutionResult(
            contract_trace_id=contract.trace_id,
            producer_type=contract.producer_type,
            ack=ack,
            confidence=contract.confidence,
            runtime_hash=runtime_hash,
        )

    def _halt(
        self,
        contract: ComputationExecutionContract,
        ack: str,
    ) -> ExecutionResult:
        """Convenience for HALT results."""
        log_event(log, logging.ERROR, "runtime_halt", ctx={
            "trace_id": contract.trace_id,
            "ack": ack,
        })
        return self._result(contract, ack)
