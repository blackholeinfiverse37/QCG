"""
adapters.py — Phase 2: Adapter Layer

Maps external producer outputs into canonical ComputationExecutionContract.
After adaptation, the core runtime processes every contract identically —
no direct runtime branching inside core.

Adapters
--------
QuantumAdapter    – QuantumDistribution → ComputationExecutionContract (QUANTUM)
ClassicalAdapter  – raw optimisation dict → ComputationExecutionContract (CLASSICAL)
HybridAdapter     – merges quantum + classical → ComputationExecutionContract (HYBRID)
"""

import hashlib
import json
import logging
import uuid
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from typing import Any

import config
from logger import get_logger, log_event
from models import QuantumDistribution
from translation_layer import translate
from execution_contract import (
    ComputationExecutionContract,
    ProducerType,
    _canonical_hash,
)

log = get_logger("qcg.adapters")



# ---------------------------------------------------------------------------
# Adapter trace record — produced by every adaptation for observability
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AdapterTrace:
    """Immutable record of one adaptation event."""
    adapter_type:    str
    producer_type:   str
    input_type:      str
    input_hash:      str
    output_trace_id: str
    output_hash:     str
    timestamp:       str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _deterministic_trace_id(namespace_label: str, *parts: str) -> str:
    """UUID-5 from a deterministic seed string."""
    seed = ":".join(str(p) for p in parts)
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{namespace_label}:{seed}"))


def _input_hash(obj: Any) -> str:
    """SHA-256 fingerprint of an arbitrary object."""
    raw = json.dumps(obj, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


# ═══════════════════════════════════════════════════════════════════════════
# QuantumAdapter
# ═══════════════════════════════════════════════════════════════════════════

class QuantumAdapter:
    """
    Maps a QuantumDistribution (+ original message) into a
    ComputationExecutionContract with producer_type = QUANTUM.

    Internally calls the existing translation_layer.translate() to obtain
    a ClassicalContract, then wraps it.
    """

    def adapt(
        self,
        distribution: QuantumDistribution,
        original_message: str,
    ) -> tuple[ComputationExecutionContract, AdapterTrace]:
        """
        Adapt a quantum distribution into a canonical execution contract.

        Returns
        -------
        (contract, adapter_trace)
        """
        # Step 1 — translate using existing pipeline
        classical_contract = translate(distribution, original_message)

        # Step 2 — build payload (opaque to core)
        payload = {
            "decoded_message":     classical_contract.decoded_message,
            "transmission_status": classical_contract.transmission_status,
            "original_trace_id":   classical_contract.trace_id,
            "uncertainty_score":   classical_contract.uncertainty_score,
        }

        # Step 3 — execution constraints (quantum-specific metadata)
        constraints = {
            "shots":             distribution.shots,
            "noise_factor":      distribution.noise_factor,
            "seed":              distribution.seed,
            "encoded_bits":      distribution.encoded_bits,
            "transmission_mode": distribution.transmission_mode,
        }

        # Step 4 — deterministic trace id
        trace_id = _deterministic_trace_id(
            "quantum",
            original_message,
            str(distribution.seed),
            distribution.encoded_bits,
            str(distribution.noise_factor),
        )

        contract = ComputationExecutionContract(
            producer_type=ProducerType.QUANTUM.value,
            payload=payload,
            confidence=classical_contract.confidence,
            trace_id=trace_id,
            contract_version=config.EXECUTION_CONTRACT_VERSION,
            execution_constraints=constraints,
        )

        in_hash = _input_hash(asdict(distribution))
        adapter_trace = AdapterTrace(
            adapter_type="QuantumAdapter",
            producer_type=ProducerType.QUANTUM.value,
            input_type="QuantumDistribution",
            input_hash=in_hash,
            output_trace_id=trace_id,
            output_hash=contract.payload_hash,
        )

        log_event(log, logging.INFO, "quantum_adapter_complete", ctx={
            "trace_id": trace_id,
            "confidence": contract.confidence,
        })

        return contract, adapter_trace


# ═══════════════════════════════════════════════════════════════════════════
# ClassicalAdapter
# ═══════════════════════════════════════════════════════════════════════════

class ClassicalAdapter:
    """
    Maps a raw classical optimisation result into a
    ComputationExecutionContract with producer_type = CLASSICAL.

    Expected input schema::

        {
            "result":     <any JSON-serialisable value>,
            "confidence": float in [0.0, 1.0],
            "metadata":   dict   (optional, defaults to {})
        }
    """

    def adapt(
        self,
        classical_output: dict,
    ) -> tuple[ComputationExecutionContract, AdapterTrace]:
        """
        Adapt a classical optimisation result into a canonical contract.

        Raises ValueError if the input is malformed.
        """
        if not isinstance(classical_output, dict):
            raise ValueError("classical_output must be a dict.")

        result     = classical_output.get("result")
        confidence = classical_output.get("confidence")
        metadata   = classical_output.get("metadata", {})

        if result is None:
            raise ValueError("classical_output must contain 'result'.")
        if confidence is None or not (0.0 <= confidence <= 1.0):
            raise ValueError(
                f"classical_output.confidence must be in [0.0, 1.0], got {confidence}"
            )

        payload = {
            "result":   result,
            "metadata": metadata,
        }

        trace_id = _deterministic_trace_id(
            "classical",
            json.dumps(result, sort_keys=True, default=str),
            str(confidence),
        )

        constraints = {
            "source": "classical_optimisation",
            "metadata_keys": sorted(metadata.keys()) if metadata else [],
        }

        contract = ComputationExecutionContract(
            producer_type=ProducerType.CLASSICAL.value,
            payload=payload,
            confidence=confidence,
            trace_id=trace_id,
            contract_version=config.EXECUTION_CONTRACT_VERSION,
            execution_constraints=constraints,
        )

        in_hash = _input_hash(classical_output)
        adapter_trace = AdapterTrace(
            adapter_type="ClassicalAdapter",
            producer_type=ProducerType.CLASSICAL.value,
            input_type="dict",
            input_hash=in_hash,
            output_trace_id=trace_id,
            output_hash=contract.payload_hash,
        )

        log_event(log, logging.INFO, "classical_adapter_complete", ctx={
            "trace_id": trace_id,
            "confidence": contract.confidence,
        })

        return contract, adapter_trace


# ═══════════════════════════════════════════════════════════════════════════
# HybridAdapter
# ═══════════════════════════════════════════════════════════════════════════

class HybridAdapter:
    """
    Merges a quantum contract and a classical contract into a single
    ComputationExecutionContract with producer_type = HYBRID.

    Default strategy: confidence-weighted selection — picks the sub-result
    with the highest confidence.
    """

    def adapt(
        self,
        quantum_contract:   ComputationExecutionContract,
        classical_contract: ComputationExecutionContract,
    ) -> tuple[ComputationExecutionContract, AdapterTrace]:
        """
        Merge two contracts (one QUANTUM, one CLASSICAL) into a HYBRID
        contract.
        """
        # Choose the higher-confidence source
        if quantum_contract.confidence >= classical_contract.confidence:
            primary, secondary = quantum_contract, classical_contract
        else:
            primary, secondary = classical_contract, quantum_contract

        payload = {
            "primary_payload":     primary.payload,
            "secondary_payload":   secondary.payload,
            "primary_producer":    primary.producer_type,
            "secondary_producer":  secondary.producer_type,
            "selection_strategy":  "confidence_weighted",
            "primary_confidence":  primary.confidence,
            "secondary_confidence": secondary.confidence,
        }

        trace_id = _deterministic_trace_id(
            "hybrid",
            primary.trace_id,
            secondary.trace_id,
        )

        constraints = {
            "primary_constraints":   primary.execution_constraints,
            "secondary_constraints": secondary.execution_constraints,
            "merge_strategy":        "confidence_weighted",
        }

        contract = ComputationExecutionContract(
            producer_type=ProducerType.HYBRID.value,
            payload=payload,
            confidence=primary.confidence,
            trace_id=trace_id,
            contract_version=config.EXECUTION_CONTRACT_VERSION,
            execution_constraints=constraints,
        )

        in_hash = _input_hash({
            "quantum_trace":   quantum_contract.trace_id,
            "classical_trace": classical_contract.trace_id,
        })
        adapter_trace = AdapterTrace(
            adapter_type="HybridAdapter",
            producer_type=ProducerType.HYBRID.value,
            input_type="ComputationExecutionContract+ComputationExecutionContract",
            input_hash=in_hash,
            output_trace_id=trace_id,
            output_hash=contract.payload_hash,
        )

        log_event(log, logging.INFO, "hybrid_adapter_complete", ctx={
            "trace_id": trace_id,
            "primary_producer": primary.producer_type,
            "confidence": contract.confidence,
        })

        return contract, adapter_trace
