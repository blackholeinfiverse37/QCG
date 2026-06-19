"""
tests/test_communication_layer.py
Test suite for Phase 2-5: communication_contract, gateway, simulation.
"""

import threading
import pytest

from communication_contract import (
    CommunicationRequest,
    TranslationContract,
    AcknowledgementContract,
    CommunicationResponse,
    make_message_id,
    resolve_translation_status,
    resolve_transport_status,
    SCHEMA_VERSION,
)
from gateway import (
    CommunicationGateway,
    QuantumProducer,
    ClassicalProducer,
    HybridProducer,
    Receiver,
    _RateLimiter,
)
import config

SEED = 42


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _request(
    source_type="CLASSICAL",
    destination_type="QUANTUM",
    confidence=0.95,
    payload=None,
    message_id=None,
) -> CommunicationRequest:
    return CommunicationRequest(
        message_id=message_id or make_message_id("test", source_type, str(confidence)),
        source_type=source_type,
        destination_type=destination_type,
        payload=payload or {"result": "OK"},
        confidence=confidence,
    )


# ---------------------------------------------------------------------------
# CommunicationRequest
# ---------------------------------------------------------------------------

class TestCommunicationRequest:

    def test_valid_request(self):
        r = _request()
        assert r.source_type == "CLASSICAL"
        assert r.schema_version == SCHEMA_VERSION

    def test_invalid_source_type_raises(self):
        with pytest.raises(ValueError, match="source_type"):
            CommunicationRequest(
                message_id="x", source_type="UNKNOWN", destination_type="CLASSICAL",
                payload={"x": 1}, confidence=0.9,
            )

    def test_invalid_destination_type_raises(self):
        with pytest.raises(ValueError, match="destination_type"):
            CommunicationRequest(
                message_id="x", source_type="CLASSICAL", destination_type="UNKNOWN",
                payload={"x": 1}, confidence=0.9,
            )

    def test_confidence_below_zero_raises(self):
        with pytest.raises(ValueError, match="confidence"):
            CommunicationRequest(
                message_id="x", source_type="CLASSICAL", destination_type="QUANTUM",
                payload={"x": 1}, confidence=-0.1,
            )

    def test_confidence_above_one_raises(self):
        with pytest.raises(ValueError, match="confidence"):
            CommunicationRequest(
                message_id="x", source_type="CLASSICAL", destination_type="QUANTUM",
                payload={"x": 1}, confidence=1.1,
            )

    def test_empty_payload_raises(self):
        with pytest.raises(ValueError, match="payload"):
            CommunicationRequest(
                message_id="x", source_type="CLASSICAL", destination_type="QUANTUM",
                payload={}, confidence=0.9,
            )

    def test_boundary_confidence_zero(self):
        r = _request(confidence=0.0)
        assert r.confidence == 0.0

    def test_boundary_confidence_one(self):
        r = _request(confidence=1.0)
        assert r.confidence == 1.0

    def test_frozen(self):
        r = _request()
        with pytest.raises(AttributeError):
            r.confidence = 0.5

    def test_to_dict_contains_required_fields(self):
        r = _request()
        d = r.to_dict()
        for f in ("message_id", "source_type", "destination_type", "payload",
                  "confidence", "schema_version", "trace_reference"):
            assert f in d

    def test_all_valid_source_types(self):
        for st in ("QUANTUM", "CLASSICAL", "HYBRID"):
            r = _request(source_type=st)
            assert r.source_type == st

    def test_all_valid_destination_types(self):
        for dt in ("QUANTUM", "CLASSICAL", "HYBRID"):
            r = _request(destination_type=dt)
            assert r.destination_type == dt


# ---------------------------------------------------------------------------
# TranslationContract
# ---------------------------------------------------------------------------

class TestTranslationContract:

    def test_from_request_ok(self):
        r = _request(confidence=0.95)
        tc = TranslationContract.from_request(r, "OK")
        assert tc.translation_status == "OK"
        assert tc.confidence == 0.95
        assert tc.uncertainty == round(1.0 - 0.95, 4)
        assert tc.payload_hash != ""

    def test_payload_hash_deterministic(self):
        r = _request()
        tc1 = TranslationContract.from_request(r, "OK")
        tc2 = TranslationContract.from_request(r, "OK")
        assert tc1.payload_hash == tc2.payload_hash

    def test_payload_hash_differs_for_different_payload(self):
        r1 = _request(payload={"a": 1})
        r2 = _request(payload={"a": 2})
        assert (TranslationContract.from_request(r1, "OK").payload_hash !=
                TranslationContract.from_request(r2, "OK").payload_hash)

    def test_uncertainty_plus_confidence_equals_one(self):
        r = _request(confidence=0.73)
        tc = TranslationContract.from_request(r, "OK")
        assert abs(tc.confidence + tc.uncertainty - 1.0) < 1e-4

    def test_frozen(self):
        r = _request()
        tc = TranslationContract.from_request(r, "OK")
        with pytest.raises(AttributeError):
            tc.confidence = 0.5

    def test_to_dict_contains_required_fields(self):
        r = _request()
        tc = TranslationContract.from_request(r, "OK")
        d = tc.to_dict()
        for f in ("message_id", "source_type", "destination_type", "payload_hash",
                  "confidence", "uncertainty", "translation_status", "schema_version",
                  "trace_reference", "created_at"):
            assert f in d


# ---------------------------------------------------------------------------
# AcknowledgementContract
# ---------------------------------------------------------------------------

class TestAcknowledgementContract:

    def _ack(self, transport_status="ACK:OK", translation_status="OK", confidence=0.95):
        return AcknowledgementContract(
            message_id="ack-001",
            transport_status=transport_status,
            translation_status=translation_status,
            confidence=confidence,
            trace_reference="",
        )

    def test_is_accepted_ack_ok(self):
        assert self._ack("ACK:OK").is_accepted is True

    def test_is_accepted_ack_degraded(self):
        assert self._ack("ACK:DEGRADED:confidence=0.5500").is_accepted is True

    def test_is_halted(self):
        assert self._ack("HALT:REPLAY_DETECTED").is_halted is True

    def test_is_accepted_false_for_halt(self):
        assert self._ack("HALT:REPLAY_DETECTED").is_accepted is False

    def test_frozen(self):
        ack = self._ack()
        with pytest.raises(AttributeError):
            ack.transport_status = "ACK:OK"

    def test_to_dict_contains_required_fields(self):
        d = self._ack().to_dict()
        for f in ("message_id", "transport_status", "translation_status",
                  "confidence", "trace_reference", "schema_version", "issued_at"):
            assert f in d


# ---------------------------------------------------------------------------
# resolve_translation_status
# ---------------------------------------------------------------------------

class TestResolveTranslationStatus:

    def test_ok_above_threshold(self):
        assert resolve_translation_status(config.CONFIDENCE_THRESHOLD) == "OK"
        assert resolve_translation_status(1.0) == "OK"

    def test_degraded_in_middle_band(self):
        mid = (config.CONFIDENCE_THRESHOLD + config.CORRUPTION_THRESHOLD) / 2
        assert resolve_translation_status(mid) == "DEGRADED"

    def test_rejected_below_corruption_threshold(self):
        assert resolve_translation_status(0.0) == "REJECTED"
        below = config.CORRUPTION_THRESHOLD - 0.01
        assert resolve_translation_status(below) == "REJECTED"

    def test_custom_thresholds(self):
        assert resolve_translation_status(0.80, ok_threshold=0.75, degraded_threshold=0.50) == "OK"
        assert resolve_translation_status(0.60, ok_threshold=0.75, degraded_threshold=0.50) == "DEGRADED"
        assert resolve_translation_status(0.30, ok_threshold=0.75, degraded_threshold=0.50) == "REJECTED"


# ---------------------------------------------------------------------------
# resolve_transport_status
# ---------------------------------------------------------------------------

class TestResolveTransportStatus:

    def test_ok_maps_to_ack_ok(self):
        assert resolve_transport_status("OK", 0.9) == "ACK:OK"

    def test_degraded_maps_to_ack_degraded(self):
        s = resolve_transport_status("DEGRADED", 0.55)
        assert s.startswith("ACK:DEGRADED")
        assert "0.5500" in s

    def test_rejected_maps_to_halt(self):
        s = resolve_transport_status("REJECTED", 0.30)
        assert s.startswith("HALT:TRANSLATION_REJECTED")


# ---------------------------------------------------------------------------
# make_message_id
# ---------------------------------------------------------------------------

class TestMakeMessageId:

    def test_deterministic(self):
        id1 = make_message_id("a", "b", "c")
        id2 = make_message_id("a", "b", "c")
        assert id1 == id2

    def test_different_parts_differ(self):
        assert make_message_id("a", "b") != make_message_id("a", "c")

    def test_returns_uuid_string(self):
        mid = make_message_id("test")
        assert len(mid) == 36
        assert mid.count("-") == 4


# ---------------------------------------------------------------------------
# Receiver
# ---------------------------------------------------------------------------

class TestReceiver:

    def _tc(self, message_id="msg-001", confidence=0.95, translation_status="OK"):
        r = _request(confidence=confidence, message_id=message_id)
        return TranslationContract.from_request(r, translation_status)

    def test_first_receive_returns_ack(self):
        rx = Receiver()
        ack = rx.receive(self._tc())
        assert ack.is_accepted

    def test_second_receive_same_id_returns_replay_halt(self):
        rx = Receiver()
        rx.receive(self._tc("dup-001"))
        ack2 = rx.receive(self._tc("dup-001"))
        assert ack2.transport_status == "HALT:REPLAY_DETECTED"

    def test_different_ids_both_accepted(self):
        rx = Receiver()
        a1 = rx.receive(self._tc("id-1"))
        a2 = rx.receive(self._tc("id-2"))
        assert a1.is_accepted
        assert a2.is_accepted

    def test_reset_clears_seen(self):
        rx = Receiver()
        rx.receive(self._tc("reset-001"))
        rx.reset()
        ack = rx.receive(self._tc("reset-001"))
        assert ack.is_accepted

    def test_seen_count(self):
        rx = Receiver()
        rx.receive(self._tc("cnt-1"))
        rx.receive(self._tc("cnt-2"))
        assert rx.seen_count == 2

    def test_eviction_when_max_reached(self):
        rx = Receiver(capacity=5)
        for i in range(5):
            rx.receive(self._tc(f"evict-{i}"))
        assert rx.seen_count == 5
        # Adding one more triggers eviction
        rx.receive(self._tc("evict-new"))
        assert rx.seen_count <= 5

    def test_degraded_confidence_returns_ack_degraded(self):
        rx = Receiver()
        mid_conf = (config.CONFIDENCE_THRESHOLD + config.CORRUPTION_THRESHOLD) / 2
        ack = rx.receive(self._tc(confidence=mid_conf, translation_status="DEGRADED"))
        assert "DEGRADED" in ack.transport_status

    def test_rejected_translation_returns_halt(self):
        rx = Receiver()
        low_conf = config.CORRUPTION_THRESHOLD - 0.05
        ack = rx.receive(self._tc(confidence=low_conf, translation_status="REJECTED"))
        assert ack.is_halted

    def test_thread_safe_replay_detection(self):
        rx = Receiver()
        tc = self._tc("concurrent-001")
        results = []
        lock = threading.Lock()

        def receive():
            ack = rx.receive(tc)
            with lock:
                results.append(ack.transport_status)

        threads = [threading.Thread(target=receive) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        accepted = [r for r in results if r.startswith("ACK:")]
        replayed = [r for r in results if r == "HALT:REPLAY_DETECTED"]
        assert len(accepted) == 1
        assert len(replayed) == 3


# ---------------------------------------------------------------------------
# CommunicationGateway
# ---------------------------------------------------------------------------

class TestCommunicationGateway:

    def test_send_classical_request_returns_ack_ok(self):
        gw = CommunicationGateway()
        req = _request(confidence=0.95)
        resp = gw.send(req)
        assert resp.acknowledgement.is_accepted
        assert resp.acknowledgement.transport_status == "ACK:OK"

    def test_send_always_returns_response(self):
        gw = CommunicationGateway()
        for conf in [0.0, 0.3, 0.55, 0.9, 1.0]:
            resp = gw.send(_request(confidence=conf))
            assert isinstance(resp, CommunicationResponse)

    def test_send_never_raises(self):
        gw = CommunicationGateway()
        resp = gw.send(_request())
        assert resp is not None

    def test_replay_detection_in_gateway(self):
        gw = CommunicationGateway()
        mid = make_message_id("gw-replay-test")
        req = _request(message_id=mid)
        gw.send(req)
        resp2 = gw.send(req)
        assert resp2.acknowledgement.transport_status == "HALT:REPLAY_DETECTED"

    def test_rate_limit_produces_halt(self):
        gw = CommunicationGateway(rate_limit_per_minute=1)
        gw._rate_limiter._tokens = 0.0
        resp = gw.send(_request())
        assert resp.acknowledgement.transport_status == "HALT:RATE_LIMIT_EXCEEDED"

    def test_low_confidence_produces_halt(self):
        gw = CommunicationGateway()
        resp = gw.send(_request(confidence=config.CORRUPTION_THRESHOLD - 0.01))
        assert resp.acknowledgement.is_halted

    def test_degraded_confidence_produces_ack_degraded(self):
        gw = CommunicationGateway()
        mid_conf = (config.CONFIDENCE_THRESHOLD + config.CORRUPTION_THRESHOLD) / 2
        resp = gw.send(_request(confidence=mid_conf))
        assert "DEGRADED" in resp.acknowledgement.transport_status

    def test_response_message_id_matches_request(self):
        gw = CommunicationGateway()
        req = _request()
        resp = gw.send(req)
        assert resp.message_id == req.message_id

    def test_response_source_type_preserved(self):
        gw = CommunicationGateway()
        for st in ("QUANTUM", "CLASSICAL", "HYBRID"):
            resp = gw.send(_request(source_type=st))
            assert resp.source_type == st

    def test_translation_contract_payload_hash_present(self):
        gw = CommunicationGateway()
        resp = gw.send(_request())
        assert len(resp.translation_contract.payload_hash) == 64

    def test_health_returns_ok(self):
        gw = CommunicationGateway()
        h = gw.health()
        assert h["status"] == "ok"
        assert "receiver_seen_count" in h
        assert "rate_limit_per_minute" in h

    def test_independent_gateways_no_replay_cross_contamination(self):
        gw1 = CommunicationGateway()
        gw2 = CommunicationGateway()
        mid = make_message_id("cross-gw-test")
        req = _request(message_id=mid)
        r1 = gw1.send(req)
        r2 = gw2.send(req)
        assert r1.acknowledgement.is_accepted
        assert r2.acknowledgement.is_accepted

    def test_concurrent_sends_are_safe(self):
        gw = CommunicationGateway()
        errors = []

        def send_request(i):
            try:
                req = _request(message_id=make_message_id("concurrent", str(i)))
                resp = gw.send(req)
                assert isinstance(resp, CommunicationResponse)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=send_request, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert errors == []


# ---------------------------------------------------------------------------
# QuantumProducer
# ---------------------------------------------------------------------------

class TestQuantumProducer:

    def test_produces_valid_request(self):
        p = QuantumProducer()
        req = p.produce("NODE_READY", noise=0.05, mode="entangled", seed=SEED)
        assert req.source_type == "QUANTUM"
        assert 0.0 <= req.confidence <= 1.0
        assert req.payload

    def test_message_id_deterministic(self):
        p = QuantumProducer()
        r1 = p.produce("NODE_READY", noise=0.05, seed=SEED)
        r2 = p.produce("NODE_READY", noise=0.05, seed=SEED)
        assert r1.message_id == r2.message_id

    def test_destination_type_passthrough(self):
        p = QuantumProducer()
        req = p.produce("NODE_READY", noise=0.05, seed=SEED, destination_type="HYBRID")
        assert req.destination_type == "HYBRID"

    def test_bit_mismatch_produces_low_confidence_request(self):
        # "SYNC" with seed=42 produces a bit mismatch — should not raise
        p = QuantumProducer()
        req = p.produce("SYNC", noise=0.08, seed=SEED)
        assert isinstance(req, CommunicationRequest)
        assert req.source_type == "QUANTUM"


# ---------------------------------------------------------------------------
# ClassicalProducer
# ---------------------------------------------------------------------------

class TestClassicalProducer:

    def test_produces_valid_request(self):
        p = ClassicalProducer()
        req = p.produce(result={"x": 1}, confidence=0.9)
        assert req.source_type == "CLASSICAL"
        assert req.confidence == 0.9

    def test_message_id_deterministic(self):
        p = ClassicalProducer()
        r1 = p.produce(result={"x": 1}, confidence=0.9)
        r2 = p.produce(result={"x": 1}, confidence=0.9)
        assert r1.message_id == r2.message_id

    def test_destination_type_passthrough(self):
        p = ClassicalProducer()
        req = p.produce(result="OK", confidence=0.8, destination_type="QUANTUM")
        assert req.destination_type == "QUANTUM"

    def test_invalid_confidence_raises(self):
        p = ClassicalProducer()
        with pytest.raises(ValueError):
            p.produce(result="x", confidence=1.5)

    def test_metadata_included(self):
        p = ClassicalProducer()
        req = p.produce(result="OK", confidence=0.9, metadata={"key": "val"})
        assert req.payload  # metadata is inside the adapter payload


# ---------------------------------------------------------------------------
# HybridProducer
# ---------------------------------------------------------------------------

class TestHybridProducer:

    def _quantum_req(self):
        return QuantumProducer().produce("NODE_READY", noise=0.05, seed=SEED)

    def _classical_req(self):
        return ClassicalProducer().produce(result={"status": "OK"}, confidence=0.92)

    def test_produces_hybrid_request(self):
        req = HybridProducer().produce(self._quantum_req(), self._classical_req())
        assert req.source_type == "HYBRID"

    def test_confidence_is_max_of_inputs(self):
        q = self._quantum_req()
        c = self._classical_req()
        req = HybridProducer().produce(q, c)
        assert req.confidence == max(q.confidence, c.confidence)

    def test_destination_type_passthrough(self):
        req = HybridProducer().produce(
            self._quantum_req(), self._classical_req(), destination_type="QUANTUM"
        )
        assert req.destination_type == "QUANTUM"

    def test_message_id_deterministic(self):
        q = self._quantum_req()
        c = self._classical_req()
        r1 = HybridProducer().produce(q, c)
        r2 = HybridProducer().produce(q, c)
        assert r1.message_id == r2.message_id


# ---------------------------------------------------------------------------
# End-to-end: all 4 cross-system paths
# ---------------------------------------------------------------------------

class TestCrossSystemPaths:

    def _gw(self):
        return CommunicationGateway()

    def test_quantum_to_classical(self):
        gw = self._gw()
        req = QuantumProducer().produce("NODE_READY", noise=0.05, seed=SEED, destination_type="CLASSICAL")
        resp = gw.send(req)
        assert resp.source_type == "QUANTUM"
        assert resp.destination_type == "CLASSICAL"
        assert isinstance(resp.acknowledgement, AcknowledgementContract)

    def test_classical_to_quantum(self):
        gw = self._gw()
        req = ClassicalProducer().produce(result={"v": 1}, confidence=0.95, destination_type="QUANTUM")
        resp = gw.send(req)
        assert resp.source_type == "CLASSICAL"
        assert resp.destination_type == "QUANTUM"
        assert resp.acknowledgement.is_accepted

    def test_hybrid_to_classical(self):
        gw = self._gw()
        q_req = QuantumProducer().produce("NODE_READY", noise=0.05, seed=SEED)
        c_req = ClassicalProducer().produce(result={"mode": "X"}, confidence=0.88)
        req = HybridProducer().produce(q_req, c_req, destination_type="CLASSICAL")
        resp = gw.send(req)
        assert resp.source_type == "HYBRID"
        assert resp.destination_type == "CLASSICAL"

    def test_hybrid_to_quantum(self):
        gw = self._gw()
        q_req = QuantumProducer().produce("LINK_UP", noise=0.05, seed=SEED)
        c_req = ClassicalProducer().produce(result={"link": "UP"}, confidence=0.91)
        req = HybridProducer().produce(q_req, c_req, destination_type="QUANTUM")
        resp = gw.send(req)
        assert resp.source_type == "HYBRID"
        assert resp.destination_type == "QUANTUM"

    def test_all_paths_same_gateway_method(self):
        """All 4 paths call the identical gateway.send() — no branching."""
        gw = self._gw()
        producers = [
            QuantumProducer().produce("NODE_READY", noise=0.05, seed=SEED, destination_type="CLASSICAL"),
            ClassicalProducer().produce(result="x", confidence=0.95, destination_type="QUANTUM"),
        ]
        q_req = QuantumProducer().produce("NODE_READY", noise=0.05, seed=SEED)
        c_req = ClassicalProducer().produce(result={"y": 1}, confidence=0.88)
        producers.append(HybridProducer().produce(q_req, c_req, destination_type="CLASSICAL"))

        responses = [gw.send(req) for req in producers]
        assert all(isinstance(r, CommunicationResponse) for r in responses)
        # All use same response schema
        keys = [set(r.to_dict().keys()) for r in responses]
        assert keys[0] == keys[1] == keys[2]
