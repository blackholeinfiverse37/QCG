"""
communication_contract.py — Phase 2: Hybrid Communication Contract

Defines the shared contract schema for all communication across quantum,
classical, and hybrid producer boundaries.

Guarantees:
- Every message traverses the same contract path regardless of source type.
- Every contract is immutable, versioned, and trace-identified.
- Every acknowledgement is deterministic.

Does NOT guarantee:
- Quantum output accuracy (confidence is probabilistic).
- Delivery (transport failures produce HALT, not exceptions).
- Ordering across concurrent transmissions.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = "1.0.0"


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _payload_hash(data: Any) -> str:
    raw = json.dumps(data, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


# ---------------------------------------------------------------------------
# CommunicationRequest
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CommunicationRequest:
    """
    Normalized inbound message from any producer type.
    The gateway accepts only this structure — source type is declared
    but does not alter the processing path.
    """
    message_id:       str        # deterministic UUID-5 from producer
    source_type:      str        # QUANTUM | CLASSICAL | HYBRID
    destination_type: str        # CLASSICAL | QUANTUM | HYBRID
    payload:          dict       # opaque, producer-specific content
    confidence:       float      # asserted by producer/adapter
    schema_version:   str = SCHEMA_VERSION
    trace_reference:  str = ""   # upstream trace id if chained; else ""

    def __post_init__(self):
        if self.source_type not in {"QUANTUM", "CLASSICAL", "HYBRID"}:
            raise ValueError(f"Unsupported source_type: {self.source_type}")
        if self.destination_type not in {"QUANTUM", "CLASSICAL", "HYBRID"}:
            raise ValueError(f"Unsupported destination_type: {self.destination_type}")
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError(f"confidence must be in [0.0, 1.0], got {self.confidence}")
        if not self.payload:
            raise ValueError("payload must not be empty")

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# TranslationContract
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TranslationContract:
    """
    Output of the translation step. Carries confidence, status, and a
    content-addressed payload hash. Immutable once created.
    """
    message_id:         str
    source_type:        str
    destination_type:   str
    payload_hash:       str
    confidence:         float
    uncertainty:        float
    translation_status: str        # OK | DEGRADED | REJECTED
    schema_version:     str = SCHEMA_VERSION
    trace_reference:    str = ""
    created_at:         str = field(default_factory=_utcnow)

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_request(request: CommunicationRequest, translation_status: str) -> "TranslationContract":
        uncertainty = round(1.0 - request.confidence, 4)
        return TranslationContract(
            message_id=request.message_id,
            source_type=request.source_type,
            destination_type=request.destination_type,
            payload_hash=_payload_hash(request.payload),
            confidence=request.confidence,
            uncertainty=uncertainty,
            translation_status=translation_status,
            schema_version=request.schema_version,
            trace_reference=request.trace_reference,
        )


# ---------------------------------------------------------------------------
# AcknowledgementContract
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AcknowledgementContract:
    """
    Deterministic receipt issued by the receiver.
    The receiver never raises — all outcomes are expressed as status codes.
    """
    message_id:        str
    transport_status:  str        # ACK:OK | ACK:DEGRADED | HALT:*
    translation_status: str       # OK | DEGRADED | REJECTED
    confidence:        float
    trace_reference:   str
    schema_version:    str = SCHEMA_VERSION
    issued_at:         str = field(default_factory=_utcnow)

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def is_accepted(self) -> bool:
        return self.transport_status.startswith("ACK:")

    @property
    def is_halted(self) -> bool:
        return self.transport_status.startswith("HALT:")


# ---------------------------------------------------------------------------
# CommunicationResponse
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CommunicationResponse:
    """
    Full response envelope returned by the gateway to the caller.
    Bundles the translation contract and the acknowledgement together.
    """
    message_id:           str
    source_type:          str
    destination_type:     str
    translation_contract: TranslationContract
    acknowledgement:      AcknowledgementContract
    schema_version:       str = SCHEMA_VERSION

    def to_dict(self) -> dict:
        return {
            "message_id":           self.message_id,
            "source_type":          self.source_type,
            "destination_type":     self.destination_type,
            "translation_contract": self.translation_contract.to_dict(),
            "acknowledgement":      self.acknowledgement.to_dict(),
            "schema_version":       self.schema_version,
        }


# ---------------------------------------------------------------------------
# Contract factories
# ---------------------------------------------------------------------------

def make_message_id(*parts: str) -> str:
    """Deterministic UUID-5 from arbitrary string parts."""
    seed = ":".join(str(p) for p in parts)
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, seed))


def resolve_translation_status(
    confidence: float,
    ok_threshold: float | None = None,
    degraded_threshold: float | None = None,
) -> str:
    import config as _cfg
    ok = ok_threshold if ok_threshold is not None else _cfg.CONFIDENCE_THRESHOLD
    deg = degraded_threshold if degraded_threshold is not None else _cfg.CORRUPTION_THRESHOLD
    if confidence >= ok:
        return "OK"
    if confidence >= deg:
        return "DEGRADED"
    return "REJECTED"


def resolve_transport_status(translation_status: str, confidence: float) -> str:
    if translation_status == "OK":
        return "ACK:OK"
    if translation_status == "DEGRADED":
        return f"ACK:DEGRADED:confidence={confidence:.4f}"
    return f"HALT:TRANSLATION_REJECTED:confidence={confidence:.4f}"
