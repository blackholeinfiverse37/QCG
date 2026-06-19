"""
gateway.py — Phase 3: Translation Gateway

A producer-agnostic communication gateway. Accepts messages from
QuantumProducer, ClassicalProducer, or HybridProducer and routes
all of them through the same communication path.

The gateway does NOT branch on source_type. Every message:
  1. Arrives as a CommunicationRequest
  2. Is translated into a TranslationContract
  3. Is acknowledged by a Receiver into an AcknowledgementContract
  4. Is returned as a CommunicationResponse
"""

from __future__ import annotations

import logging
import threading
import time
import json
from typing import Any

import config
from logger import get_logger, log_event
from models import TransmissionRequest
from quantum_producer import run_quantum_producer
from translation_layer import TranslationError
from adapters import QuantumAdapter, ClassicalAdapter, HybridAdapter
from execution_contract import ComputationExecutionContract, ProducerType
from communication_contract import (
    CommunicationRequest,
    CommunicationResponse,
    TranslationContract,
    AcknowledgementContract,
    make_message_id,
    resolve_translation_status,
    resolve_transport_status,
)
from canonical_replay_authority import CanonicalReplayAuthority, get_authority

log = get_logger("qcg.comms_gateway")


# ---------------------------------------------------------------------------
# Producers
# ---------------------------------------------------------------------------

class QuantumProducer:
    """Wraps the Qiskit quantum simulation pipeline into a CommunicationRequest."""

    def __init__(self):
        self._adapter = QuantumAdapter()

    def produce(
        self,
        message: str,
        noise: float = 0.12,
        mode: str = "entangled",
        seed: int = config.DEFAULT_SEED,
        destination_type: str = "CLASSICAL",
    ) -> CommunicationRequest:
        request = TransmissionRequest(message=message, noise=noise, mode=mode)
        distribution = run_quantum_producer(request, seed=seed)
        message_id = make_message_id("quantum", message, str(seed), str(noise))
        try:
            contract, _ = self._adapter.adapt(distribution, message)
            confidence = contract.confidence
            payload = contract.payload
            trace_ref = contract.trace_id
        except TranslationError:
            # Bit mismatch / rejection — propagate as low-confidence request
            dominant = max(distribution.counts, key=distribution.counts.get)
            total = sum(distribution.counts.values())
            confidence = round(distribution.counts[dominant] / total, 4)
            payload = {
                "decoded_message": "CORRUPTED",
                "transmission_status": "REJECTED",
                "encoded_bits": distribution.encoded_bits,
                "dominant_bits": dominant,
            }
            trace_ref = message_id
        return CommunicationRequest(
            message_id=message_id,
            source_type="QUANTUM",
            destination_type=destination_type,
            payload=payload,
            confidence=confidence,
            trace_reference=trace_ref,
        )


class ClassicalProducer:
    """Wraps a classical result dict into a CommunicationRequest."""

    def __init__(self):
        self._adapter = ClassicalAdapter()

    def produce(
        self,
        result: Any,
        confidence: float,
        metadata: dict | None = None,
        destination_type: str = "CLASSICAL",
    ) -> CommunicationRequest:
        classical_output = {"result": result, "confidence": confidence, "metadata": metadata or {}}
        contract, _ = self._adapter.adapt(classical_output)
        message_id = make_message_id(
            "classical",
            json.dumps(result, sort_keys=True, default=str),
            str(confidence),
        )
        return CommunicationRequest(
            message_id=message_id,
            source_type="CLASSICAL",
            destination_type=destination_type,
            payload=contract.payload,
            confidence=contract.confidence,
            trace_reference=contract.trace_id,
        )


class HybridProducer:
    """Merges a quantum and classical CommunicationRequest into one HYBRID request."""

    def __init__(self):
        self._adapter = HybridAdapter()

    def produce(
        self,
        quantum_req: CommunicationRequest,
        classical_req: CommunicationRequest,
        destination_type: str = "CLASSICAL",
    ) -> CommunicationRequest:
        q_contract = ComputationExecutionContract(
            producer_type=ProducerType.QUANTUM.value,
            payload=quantum_req.payload,
            confidence=quantum_req.confidence,
            trace_id=quantum_req.trace_reference or quantum_req.message_id,
            contract_version=config.EXECUTION_CONTRACT_VERSION,
            execution_constraints={},
        )
        c_contract = ComputationExecutionContract(
            producer_type=ProducerType.CLASSICAL.value,
            payload=classical_req.payload,
            confidence=classical_req.confidence,
            trace_id=classical_req.trace_reference or classical_req.message_id,
            contract_version=config.EXECUTION_CONTRACT_VERSION,
            execution_constraints={},
        )
        hybrid_contract, _ = self._adapter.adapt(q_contract, c_contract)
        message_id = make_message_id("hybrid", quantum_req.message_id, classical_req.message_id)
        return CommunicationRequest(
            message_id=message_id,
            source_type="HYBRID",
            destination_type=destination_type,
            payload=hybrid_contract.payload,
            confidence=hybrid_contract.confidence,
            trace_reference=hybrid_contract.trace_id,
        )


# ---------------------------------------------------------------------------
# Receiver
# ---------------------------------------------------------------------------

class Receiver:
    """
    Consumes a TranslationContract and issues a deterministic AcknowledgementContract.
    Never raises. Replay decisions are delegated to CanonicalReplayAuthority.
    """

    def __init__(
        self,
        replay_authority: CanonicalReplayAuthority | None = None,
        capacity: int | None = None,
    ):
        # Each Receiver instance gets its own independent authority + registry
        # so gateway instances are isolated from each other.
        if replay_authority is None:
            import tempfile
            from replay_registry import ReplayRegistry
            from pathlib import Path
            reg = ReplayRegistry(
                path=Path(tempfile.mktemp(suffix="_receiver.json")),
                ttl_seconds=300.0,
            )
            replay_authority = CanonicalReplayAuthority(reg)
        self._authority = replay_authority
        self._capacity = capacity

    def receive(self, translation_contract: TranslationContract) -> AcknowledgementContract:
        # Enforce capacity cap by evicting oldest entry when limit reached
        if self._capacity is not None and self._authority._registry.entry_count >= self._capacity:
            self._authority._registry.reset()

        # Delegate replay decision to the single authority
        verdict = self._authority.submit(
            message_id=translation_contract.message_id,
            trace_reference=translation_contract.trace_reference,
        )

        if not verdict.is_valid:
            return AcknowledgementContract(
                message_id=translation_contract.message_id,
                transport_status="HALT:REPLAY_DETECTED",
                translation_status=translation_contract.translation_status,
                confidence=translation_contract.confidence,
                trace_reference=translation_contract.trace_reference,
            )

        transport_status = resolve_transport_status(
            translation_contract.translation_status,
            translation_contract.confidence,
        )
        return AcknowledgementContract(
            message_id=translation_contract.message_id,
            transport_status=transport_status,
            translation_status=translation_contract.translation_status,
            confidence=translation_contract.confidence,
            trace_reference=translation_contract.trace_reference,
        )

    def reset(self):
        self._authority.reset()

    @property
    def seen_count(self) -> int:
        return self._authority._registry.entry_count


# ---------------------------------------------------------------------------
# Rate limiter (token bucket)
# ---------------------------------------------------------------------------

class _RateLimiter:
    def __init__(self, per_minute: int):
        self._capacity = per_minute
        self._tokens = float(per_minute)
        self._refill_rate = per_minute / 60.0
        self._last = time.monotonic()
        self._lock = threading.Lock()

    def allow(self) -> bool:
        with self._lock:
            now = time.monotonic()
            self._tokens = min(
                self._capacity,
                self._tokens + (now - self._last) * self._refill_rate,
            )
            self._last = now
            if self._tokens >= 1.0:
                self._tokens -= 1.0
                return True
            return False


# ---------------------------------------------------------------------------
# Gateway
# ---------------------------------------------------------------------------

class CommunicationGateway:
    """
    Producer-agnostic translation gateway.

    All producer types (QUANTUM, CLASSICAL, HYBRID) traverse the same path:
      CommunicationRequest -> TranslationContract -> AcknowledgementContract -> CommunicationResponse

    The gateway does not inspect source_type for routing decisions.
    """

    def __init__(
        self,
        receiver: Receiver | None = None,
        rate_limit_per_minute: int = config.RATE_LIMIT_PER_MINUTE,
        replay_authority: CanonicalReplayAuthority | None = None,
    ):
        self._receiver = receiver or Receiver(replay_authority=replay_authority)
        self._rate_limiter = _RateLimiter(rate_limit_per_minute)

    def send(self, request: CommunicationRequest) -> CommunicationResponse:
        """
        Process one CommunicationRequest through the full communication path.
        Always returns a CommunicationResponse — never raises.
        """
        if not self._rate_limiter.allow():
            log_event(log, logging.WARNING, "gateway_rate_limited", ctx={
                "message_id": request.message_id,
            })
            translation_contract = TranslationContract.from_request(request, "REJECTED")
            ack = AcknowledgementContract(
                message_id=request.message_id,
                transport_status="HALT:RATE_LIMIT_EXCEEDED",
                translation_status="REJECTED",
                confidence=request.confidence,
                trace_reference=request.trace_reference,
            )
            return CommunicationResponse(
                message_id=request.message_id,
                source_type=request.source_type,
                destination_type=request.destination_type,
                translation_contract=translation_contract,
                acknowledgement=ack,
            )

        log_event(log, logging.INFO, "gateway_send", ctx={
            "message_id": request.message_id,
            "source_type": request.source_type,
            "destination_type": request.destination_type,
            "confidence": request.confidence,
        })

        try:
            translation_status = resolve_translation_status(request.confidence)
            translation_contract = TranslationContract.from_request(request, translation_status)
            ack = self._receiver.receive(translation_contract)

        except Exception as e:
            log_event(log, logging.ERROR, "gateway_error", ctx={
                "message_id": request.message_id,
                "error": str(e),
                "type": type(e).__name__,
            })
            translation_contract = TranslationContract.from_request(request, "REJECTED")
            ack = AcknowledgementContract(
                message_id=request.message_id,
                transport_status=f"HALT:GATEWAY_ERROR:{type(e).__name__}",
                translation_status="REJECTED",
                confidence=request.confidence,
                trace_reference=request.trace_reference,
            )

        log_event(log, logging.INFO, "gateway_response", ctx={
            "message_id": request.message_id,
            "transport_status": ack.transport_status,
            "translation_status": ack.translation_status,
        })

        return CommunicationResponse(
            message_id=request.message_id,
            source_type=request.source_type,
            destination_type=request.destination_type,
            translation_contract=translation_contract,
            acknowledgement=ack,
        )

    def health(self) -> dict:
        return {
            "status": "ok",
            "receiver_seen_count": self._receiver.seen_count,
            "rate_limit_per_minute": self._rate_limiter._capacity,
        }
