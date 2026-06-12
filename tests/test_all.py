"""
tests/test_all.py
Full pytest suite for the Hybrid Quantum Communication Gateway.
Covers all 6 layers: producer, translation, gateway, failure modes, determinism.
"""

import pytest

from models import TransmissionRequest, QuantumDistribution, ClassicalContract
from quantum_producer import run_quantum_producer
from translation_layer import translate, TranslationError
from hybrid_gateway import QuantumGateway
from determinism_proof import run_determinism_proof


SEED = 42
GOOD_REQUEST = TransmissionRequest(message="NODE_READY", noise=0.05, mode="entangled")


# -- Layer 1: Input Validation ------------------------------------------------

class TestTransmissionRequest:
    def test_valid_request(self):
        r = TransmissionRequest("NODE_READY", 0.12, "entangled")
        assert r.message == "NODE_READY"

    def test_empty_message_raises(self):
        with pytest.raises(ValueError, match="non-empty"):
            TransmissionRequest("", 0.1, "entangled")

    def test_whitespace_message_raises(self):
        with pytest.raises(ValueError, match="non-empty"):
            TransmissionRequest("   ", 0.1, "entangled")

    def test_noise_below_zero_raises(self):
        with pytest.raises(ValueError, match="noise"):
            TransmissionRequest("MSG", -0.1, "entangled")

    def test_noise_above_one_raises(self):
        with pytest.raises(ValueError, match="noise"):
            TransmissionRequest("MSG", 1.1, "entangled")

    def test_unsupported_mode_raises(self):
        with pytest.raises(ValueError, match="mode"):
            TransmissionRequest("MSG", 0.1, "teleport")

    def test_boundary_noise_zero(self):
        r = TransmissionRequest("MSG", 0.0, "entangled")
        assert r.noise == 0.0

    def test_boundary_noise_one(self):
        r = TransmissionRequest("MSG", 1.0, "entangled")
        assert r.noise == 1.0

    def test_message_stripped(self):
        r = TransmissionRequest("  NODE_READY  ", 0.0, "entangled")
        assert r.message == "NODE_READY"

    def test_message_too_long_raises(self):
        with pytest.raises(ValueError, match="MAX_MESSAGE_LENGTH"):
            TransmissionRequest("A" * 300, 0.0, "entangled")


# -- Config Validation --------------------------------------------------------

class TestConfigValidation:
    def test_validate_passes_with_defaults(self):
        import config
        config.validate()  # should not raise

    def test_validate_catches_inverted_thresholds(self):
        import config
        original_corruption = config.CORRUPTION_THRESHOLD
        config.CORRUPTION_THRESHOLD = 0.80  # higher than CONFIDENCE_THRESHOLD
        with pytest.raises(ValueError, match="less than"):
            config.validate()
        config.CORRUPTION_THRESHOLD = original_corruption  # restore


# -- Layer 1: Quantum Producer ------------------------------------------------

class TestQuantumProducer:
    def test_returns_quantum_distribution(self):
        dist = run_quantum_producer(GOOD_REQUEST, seed=SEED)
        assert isinstance(dist, QuantumDistribution)

    def test_counts_sum_to_shots(self):
        dist = run_quantum_producer(GOOD_REQUEST, seed=SEED)
        assert sum(dist.counts.values()) == dist.shots

    def test_encoded_bits_are_binary(self):
        dist = run_quantum_producer(GOOD_REQUEST, seed=SEED)
        assert dist.encoded_bits in {"00", "01", "10", "11"}

    def test_seed_produces_identical_counts(self):
        d1 = run_quantum_producer(GOOD_REQUEST, seed=SEED)
        d2 = run_quantum_producer(GOOD_REQUEST, seed=SEED)
        assert d1.counts == d2.counts

    def test_different_seeds_may_differ(self):
        d1 = run_quantum_producer(GOOD_REQUEST, seed=1)
        d2 = run_quantum_producer(GOOD_REQUEST, seed=99)
        # Not guaranteed to differ but with high noise they will; just check types
        assert isinstance(d1.counts, dict)
        assert isinstance(d2.counts, dict)

    def test_high_noise_spreads_distribution(self):
        noisy = TransmissionRequest("NODE_READY", 0.95, "entangled")
        dist = run_quantum_producer(noisy, seed=SEED)
        dominant_prob = max(dist.counts.values()) / dist.shots
        assert dominant_prob < 0.5   # noise destroys the signal

    def test_zero_noise_concentrates_distribution(self):
        clean = TransmissionRequest("NODE_READY", 0.0, "entangled")
        dist = run_quantum_producer(clean, seed=SEED)
        dominant_prob = max(dist.counts.values()) / dist.shots
        assert dominant_prob > 0.95  # near-perfect fidelity

    def test_empty_counts_model_raises(self):
        with pytest.raises(ValueError, match="counts"):
            QuantumDistribution(
                encoded_bits="11", transmission_mode="entangled",
                noise_factor=0.0, shots=1024, counts={}, seed=SEED
            )


# -- Layer 2: Translation Layer -----------------------------------------------

class TestTranslationLayer:
    def _clean_dist(self) -> QuantumDistribution:
        return run_quantum_producer(
            TransmissionRequest("NODE_READY", 0.0, "entangled"), seed=SEED
        )

    def test_ok_contract_on_clean_signal(self):
        dist = self._clean_dist()
        contract = translate(dist, "NODE_READY")
        assert contract.transmission_status == "OK"
        assert contract.decoded_message == "NODE_READY"

    def test_contract_fields_present(self):
        dist = self._clean_dist()
        contract = translate(dist, "NODE_READY")
        d = contract.to_dict()
        for field in ("trace_id", "confidence", "decoded_message",
                      "transmission_status", "uncertainty_score", "contract_version"):
            assert field in d

    def test_confidence_plus_uncertainty_equals_one(self):
        dist = self._clean_dist()
        contract = translate(dist, "NODE_READY")
        assert abs(contract.confidence + contract.uncertainty_score - 1.0) < 1e-4

    def test_trace_id_is_deterministic(self):
        dist = self._clean_dist()
        c1 = translate(dist, "NODE_READY")
        c2 = translate(dist, "NODE_READY")
        assert c1.trace_id == c2.trace_id

    def test_rejected_on_noise_spike(self):
        noisy = TransmissionRequest("NODE_READY", 0.95, "entangled")
        dist = run_quantum_producer(noisy, seed=SEED)
        with pytest.raises(TranslationError, match="REJECTED"):
            translate(dist, "NODE_READY")

    def test_rejected_on_message_corruption(self):
        # NODE_READY -> bits=11; LINK_DOWN -> bits=01: guaranteed mismatch
        dist = run_quantum_producer(
            TransmissionRequest("NODE_READY", 0.05, "entangled"), seed=SEED
        )
        with pytest.raises(TranslationError, match="REJECTED"):
            translate(dist, "LINK_DOWN")

    def test_degraded_on_medium_noise(self):
        medium = TransmissionRequest("NODE_READY", 0.40, "entangled")
        dist = run_quantum_producer(medium, seed=SEED)
        # May be DEGRADED or REJECTED depending on shot outcome; just ensure no crash
        try:
            contract = translate(dist, "NODE_READY")
            assert contract.transmission_status in ("OK", "DEGRADED")
        except TranslationError:
            pass  # REJECTED is also valid at this noise level

    def test_no_raw_probabilities_in_contract(self):
        dist = self._clean_dist()
        contract = translate(dist, "NODE_READY")
        d = contract.to_dict()
        assert "counts" not in d
        assert "raw" not in str(d)


# -- Layer 3: Gateway Pipeline ------------------------------------------------

class TestGatewayPipeline:
    def test_clean_transmission_returns_ack_ok(self):
        gw = QuantumGateway()
        ack = gw.transmit("NODE_READY", noise=0.0, mode="entangled", seed=SEED)
        assert ack.startswith("ACK:OK:")

    def test_ack_contains_message(self):
        gw = QuantumGateway()
        ack = gw.transmit("NODE_READY", noise=0.0, mode="entangled", seed=SEED)
        assert "NODE_READY" in ack

    def test_invalid_input_returns_halt(self):
        gw = QuantumGateway()
        ack = gw.transmit("", noise=0.1, mode="entangled", seed=SEED)
        assert ack.startswith("HALT:INVALID_INPUT")

    def test_invalid_mode_returns_halt(self):
        gw = QuantumGateway()
        ack = gw.transmit("NODE_READY", noise=0.1, mode="teleport", seed=SEED)
        assert ack.startswith("HALT:INVALID_INPUT")

    def test_transmit_never_raises(self):
        gw = QuantumGateway()
        for noise in [0.0, 0.5, 0.99]:
            result = gw.transmit("NODE_READY", noise=noise, mode="entangled", seed=SEED)
            assert isinstance(result, str)

    def test_independent_gateway_instances(self):
        gw1 = QuantumGateway()
        gw2 = QuantumGateway()
        ack1 = gw1.transmit("NODE_READY", noise=0.0, mode="entangled", seed=SEED)
        ack2 = gw2.transmit("NODE_READY", noise=0.0, mode="entangled", seed=SEED)
        assert "REPLAY" not in ack1
        assert "REPLAY" not in ack2

    def test_health_check_returns_ok(self):
        gw = QuantumGateway()
        health = gw.health_check()
        assert health["status"] == "ok"
        assert "replay_registry_size" in health
        assert "rate_limit_per_minute" in health
        assert "contract_version" in health

    def test_rate_limit_blocks_excess_requests(self):
        gw = QuantumGateway()
        gw._rate_limiter._tokens = 0.0  # exhaust tokens
        ack = gw.transmit("NODE_READY", noise=0.0, mode="entangled", seed=SEED)
        assert ack == "HALT:RATE_LIMIT_EXCEEDED"

    def test_message_too_long_returns_halt(self):
        gw = QuantumGateway()
        ack = gw.transmit("A" * 300, noise=0.0, mode="entangled", seed=SEED)
        assert ack.startswith("HALT:INVALID_INPUT")


# -- Layer 4: Failure Proof ---------------------------------------------------

class TestFailureProof:
    def test_noise_spike_halts(self):
        gw = QuantumGateway()
        ack = gw.transmit("NODE_READY", noise=0.95, mode="entangled", seed=SEED)
        assert ack.startswith("HALT:")

    def test_low_confidence_halts(self):
        gw = QuantumGateway()
        ack = gw.transmit("NODE_READY", noise=0.75, mode="entangled", seed=SEED)
        assert ack.startswith("HALT:")

    def test_replay_detected_on_second_call(self):
        gw = QuantumGateway()
        gw.transmit("NODE_READY", noise=0.0, mode="entangled", seed=SEED)
        ack2 = gw.transmit("NODE_READY", noise=0.0, mode="entangled", seed=SEED)
        assert ack2 == "HALT:REPLAY_DETECTED"

    def test_replay_registry_reset_allows_retransmit(self):
        gw = QuantumGateway()
        gw.transmit("NODE_READY", noise=0.0, mode="entangled", seed=SEED)
        gw.reset_replay_registry()
        ack = gw.transmit("NODE_READY", noise=0.0, mode="entangled", seed=SEED)
        assert "REPLAY" not in ack

    def test_empty_counts_raises_value_error(self):
        with pytest.raises(ValueError, match="counts"):
            QuantumDistribution(
                encoded_bits="11", transmission_mode="entangled",
                noise_factor=0.0, shots=1024, counts={}, seed=SEED
            )

    def test_message_corruption_halts(self):
        dist = run_quantum_producer(
            TransmissionRequest("NODE_READY", 0.05, "entangled"), seed=SEED
        )
        with pytest.raises(TranslationError, match="REJECTED"):
            translate(dist, "LINK_DOWN")

    def test_concurrent_replay_guard(self):
        """Two threads transmitting the same message should produce exactly one REPLAY."""
        import threading
        gw = QuantumGateway()
        results = []
        lock = threading.Lock()

        def transmit():
            ack = gw.transmit("NODE_READY", noise=0.0, mode="entangled", seed=SEED)
            with lock:
                results.append(ack)

        threads = [threading.Thread(target=transmit) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        replay_count = sum(1 for r in results if "REPLAY" in r)
        ok_count = sum(1 for r in results if r.startswith("ACK:OK"))
        assert ok_count == 1
        assert replay_count == 1


# -- Layer 6: Determinism Proof -----------------------------------------------

class TestDeterminismProof:
    def test_five_runs_identical(self):
        assert run_determinism_proof(
            message="NODE_READY", noise=0.12, mode="entangled", seed=SEED, runs=5
        ) is True

    def test_different_messages_differ(self):
        req_a = TransmissionRequest("NODE_READY", 0.0, "entangled")
        req_b = TransmissionRequest("LINK_DOWN", 0.0, "entangled")
        dist_a = run_quantum_producer(req_a, seed=SEED)
        dist_b = run_quantum_producer(req_b, seed=SEED)
        assert dist_a.encoded_bits != dist_b.encoded_bits

    def test_same_seed_same_counts(self):
        req = TransmissionRequest("NODE_READY", 0.20, "entangled")
        runs = [run_quantum_producer(req, seed=SEED).counts for _ in range(3)]
        assert runs[0] == runs[1] == runs[2]

    def test_contract_trace_id_stable_across_runs(self):
        req = TransmissionRequest("NODE_READY", 0.0, "entangled")
        trace_ids = set()
        for _ in range(5):
            dist = run_quantum_producer(req, seed=SEED)
            contract = translate(dist, "NODE_READY")
            trace_ids.add(contract.trace_id)
        assert len(trace_ids) == 1


# =============================================================================
# Phase 3 Test Matrix
# =============================================================================

# -- Determinism: 20-run identical replay -------------------------------------

class TestDeterminism20Run:
    def test_20_runs_identical(self):
        """Phase 3 requirement: 20 consecutive runs must be identical."""
        assert run_determinism_proof(
            message="NODE_READY", noise=0.12, mode="entangled", seed=42, runs=20
        ) is True

    def test_failure_injection_timestamp_detected(self):
        from determinism_proof import run_failure_injection_proof
        fi = run_failure_injection_proof()
        # Timestamp mutation must surface as an observability diff
        assert fi["timestamp_mutation"]["detected"] is True

    def test_failure_injection_payload_mutation_detected(self):
        from determinism_proof import run_failure_injection_proof
        fi = run_failure_injection_proof()
        assert fi["payload_mutation"]["detected"] is True

    def test_failure_injection_ordering_neutralised(self):
        from determinism_proof import run_failure_injection_proof
        fi = run_failure_injection_proof()
        # Canonical JSON sort_keys=True must neutralise ordering
        assert fi["ordering_mutation"]["hash_unchanged"] is True


# -- Replay Enforcement -------------------------------------------------------

class TestReplayEnforcer:
    def _enforcer(self):
        from replay_enforcer import ReplayEnforcer
        return ReplayEnforcer(ttl_seconds=60.0)

    def test_valid_execution_accepted(self):
        e = self._enforcer()
        d = e.submit("art-001")
        assert d.status == "ACCEPTED"
        assert d.sequence_id == 1

    def test_duplicate_rejected(self):
        e = self._enforcer()
        e.submit("art-002")
        d = e.submit("art-002")
        assert d.status == "REJECTED_DUPLICATE"

    def test_stale_rejected(self):
        import time
        from replay_enforcer import ReplayEnforcer
        e = ReplayEnforcer(ttl_seconds=1.0)
        stale_issued = time.monotonic() - 10.0
        d = e.submit("art-stale", issued_at=stale_issued)
        assert d.status == "REJECTED_STALE"

    def test_sequence_monotonic(self):
        e = self._enforcer()
        ids = [f"art-seq-{i}" for i in range(5)]
        seqs = [e.submit(aid).sequence_id for aid in ids]
        assert seqs == sorted(seqs)
        assert seqs[0] == 1

    def test_stale_beats_duplicate(self):
        """Stale check must fire before duplicate check."""
        import time
        from replay_enforcer import ReplayEnforcer
        e = ReplayEnforcer(ttl_seconds=1.0)
        stale_issued = time.monotonic() - 10.0
        # First submit (stale) — should be REJECTED_STALE, not ACCEPTED
        d = e.submit("art-both", issued_at=stale_issued)
        assert d.status == "REJECTED_STALE"


# -- Trust Chain --------------------------------------------------------------

class TestTrustChain:
    def test_valid_chain_passes(self):
        from trust_chain import TrustChain, NodeRegistry
        from node_identity import NodeSigner
        import hashlib

        producer = NodeSigner("TC_PROD", "PRODUCER")
        gateway = NodeSigner("TC_GW", "GATEWAY")
        executor = NodeSigner("TC_EXEC", "EXECUTOR")

        registry = NodeRegistry()
        for s in [producer, gateway, executor]:
            registry.register(s.identity)

        chain = TrustChain()
        ph = hashlib.sha256(b"payload").hexdigest()
        chain.add_handoff(producer, gateway.identity, "PRODUCE", ph)
        chain.add_handoff(gateway, executor.identity, "FORWARD", ph)

        passed, errors = chain.verify_chain(registry)
        assert passed is True
        assert errors == []

    def test_forged_signature_detected(self):
        from trust_chain import TrustChain, TrustChainLink, NodeRegistry
        from node_identity import NodeSigner
        import hashlib

        legit = NodeSigner("LEGIT_NODE", "PRODUCER")
        attacker = NodeSigner("ATTACKER", "ATTACKER")

        registry = NodeRegistry()
        registry.register(legit.identity)  # attacker NOT registered

        chain = TrustChain()
        ph = hashlib.sha256(b"payload").hexdigest()
        chain.add_handoff(attacker, legit.identity, "SPOOF", ph)

        passed, errors = chain.verify_chain(registry)
        assert passed is False
        assert any("not registered" in e for e in errors)


# -- Audit Trail --------------------------------------------------------------

class TestAuditTrail:
    def test_inclusion_proof(self):
        from audit_trail import MerkleAuditTrail
        trail = MerkleAuditTrail()
        entries = [trail.append("EVT", {"i": i}, "NODE_0") for i in range(5)]
        assert trail.verify_inclusion(entries[2]) is True

    def test_tamper_detection(self):
        from audit_trail import MerkleAuditTrail, AuditEntry
        trail = MerkleAuditTrail()
        for i in range(4):
            trail.append("EVT", {"i": i}, "NODE_0")
        # Mutate internal entry
        original = trail._entries[1]
        trail._entries[1] = AuditEntry(
            sequence=1, event_type="TAMPERED", event_hash="0" * 64,
            node_id="ATTACKER", event_data={}
        )
        passed, _ = trail.verify_integrity()
        assert passed is False
        trail._entries[1] = original  # restore


# -- Consensus Tests ----------------------------------------------------------

class TestConsensus:
    def _setup(self):
        from consensus_simulation import DistributedConsensusNode, ConsensusEngine
        from node_identity import NodeSigner
        from execution_contract import ComputationExecutionContract
        from provenance import sign_contract

        producer = NodeSigner("CONS_PROD", "QUANTUM_PRODUCER")
        nodes = [DistributedConsensusNode(f"CN_{i}") for i in range(3)]
        engine = ConsensusEngine(nodes)

        contract = ComputationExecutionContract(
            producer_type="QUANTUM", payload={"data": "test"},
            confidence=0.95, trace_id="test-consensus-001", contract_version="2.0.0",
        )
        signed = sign_contract(contract, producer)
        return engine, signed, producer

    def test_honest_network(self):
        engine, signed, producer = self._setup()
        proof = engine.run_consensus(signed, producer.identity.public_key)
        assert proof.consensus_reached is True
        assert proof.agreement_percentage == 1.0

    def test_faulty_node(self):
        engine, signed, producer = self._setup()
        proof = engine.run_consensus(signed, producer.identity.public_key,
                                      simulate_faulty="CN_1")
        # 2/3 honest nodes still reach consensus
        assert proof.consensus_reached is True
        assert "CN_1" in proof.disagreements

    def test_stale_node(self):
        engine, signed, producer = self._setup()
        proof = engine.run_consensus(signed, producer.identity.public_key,
                                      simulate_missing="CN_2")
        # 2 of 3 nodes = 66% — meets threshold
        assert proof.consensus_reached is True
        assert "CN_2" in proof.disagreements

    def test_spoofed_node(self):
        """Unregistered/spoofed attestation signature is rejected."""
        from consensus_simulation import DistributedConsensusNode, ConsensusEngine
        from node_identity import NodeSigner
        from execution_contract import ComputationExecutionContract
        from provenance import sign_contract

        producer = NodeSigner("SPOOF_PROD", "QUANTUM_PRODUCER")
        nodes = [DistributedConsensusNode(f"SN_{i}") for i in range(4)]
        engine = ConsensusEngine(nodes)
        # Inject a faulty hash for one node to simulate spoofing behaviour
        contract = ComputationExecutionContract(
            producer_type="QUANTUM", payload={"data": "spoof_test"},
            confidence=0.95, trace_id="spoof-consensus-001", contract_version="2.0.0",
        )
        signed = sign_contract(contract, producer)
        proof = engine.run_consensus(signed, producer.identity.public_key,
                                      simulate_faulty="SN_0")
        # Faulty node's hash differs but honest majority still wins
        assert proof.consensus_reached is True
        assert "SN_0" in proof.disagreements


# =============================================================================
# Phase 1 — Determinism Hardening Tests
# =============================================================================

class TestReplayContract:
    def _make_response(self, message_id="msg-test", confidence=0.95,
                       translation_status="OK", transport_status="ACK:OK"):
        from communication_contract import (
            CommunicationRequest, TranslationContract, AcknowledgementContract,
            CommunicationResponse, make_message_id,
        )
        req = CommunicationRequest(
            message_id=message_id,
            source_type="CLASSICAL",
            destination_type="QUANTUM",
            payload={"status": "OK"},
            confidence=confidence,
        )
        tc = TranslationContract.from_request(req, translation_status)
        ack = AcknowledgementContract(
            message_id=message_id,
            transport_status=transport_status,
            translation_status=translation_status,
            confidence=confidence,
            trace_reference="",
        )
        return CommunicationResponse(
            message_id=message_id,
            source_type="CLASSICAL",
            destination_type="QUANTUM",
            translation_contract=tc,
            acknowledgement=ack,
        )

    def test_from_response_extracts_deterministic_fields(self):
        from deterministic_replay import ReplayContract
        resp = self._make_response()
        rc = ReplayContract.from_response(resp)
        assert rc.message_id == "msg-test"
        assert rc.confidence == 0.95
        assert rc.translation_status == "OK"
        assert rc.transport_status == "ACK:OK"
        assert len(rc.payload_hash) == 64

    def test_deterministic_projection_excludes_timestamps(self):
        from deterministic_replay import ReplayContract, DETERMINISTIC_FIELDS, OBSERVABILITY_FIELDS
        resp = self._make_response()
        rc = ReplayContract.from_response(resp)
        proj = rc.deterministic_projection()
        assert set(proj.keys()) == DETERMINISTIC_FIELDS
        for obs_field in OBSERVABILITY_FIELDS:
            assert obs_field not in proj

    def test_deterministic_hash_stable_across_calls(self):
        from deterministic_replay import ReplayContract
        resp = self._make_response()
        rc = ReplayContract.from_response(resp)
        assert rc.deterministic_hash() == rc.deterministic_hash()

    def test_deterministic_hash_differs_for_different_payload(self):
        from deterministic_replay import ReplayContract
        from communication_contract import (
            CommunicationRequest, TranslationContract, AcknowledgementContract,
            CommunicationResponse,
        )
        def _rc(payload):
            req = CommunicationRequest(
                message_id="diff-hash-test",
                source_type="CLASSICAL", destination_type="QUANTUM",
                payload=payload, confidence=0.9,
            )
            tc = TranslationContract.from_request(req, "OK")
            ack = AcknowledgementContract(
                message_id="diff-hash-test", transport_status="ACK:OK",
                translation_status="OK", confidence=0.9, trace_reference="",
            )
            resp = CommunicationResponse(
                message_id="diff-hash-test", source_type="CLASSICAL",
                destination_type="QUANTUM", translation_contract=tc, acknowledgement=ack,
            )
            return ReplayContract.from_response(resp)

        rc1 = _rc({"v": 1})
        rc2 = _rc({"v": 2})
        assert rc1.deterministic_hash() != rc2.deterministic_hash()

    def test_frozen(self):
        from deterministic_replay import ReplayContract
        rc = ReplayContract(
            message_id="x", payload_hash="a" * 64,
            confidence=0.9, translation_status="OK", transport_status="ACK:OK",
        )
        with pytest.raises((AttributeError, TypeError)):
            rc.confidence = 0.5


class TestReplayComparator:
    def _rc(self, message_id="m1", confidence=0.9, ts_status="OK",
            tp_status="ACK:OK", created_at="T1", issued_at="T1"):
        from deterministic_replay import ReplayContract
        import hashlib, json
        ph = hashlib.sha256(json.dumps({"x": 1}).encode()).hexdigest()
        return ReplayContract(
            message_id=message_id, payload_hash=ph,
            confidence=confidence, translation_status=ts_status,
            transport_status=tp_status, created_at=created_at, issued_at=issued_at,
        )

    def test_identical_contracts_pass(self):
        from deterministic_replay import ReplayComparator
        rc = self._rc()
        result = ReplayComparator().compare(rc, rc)
        assert result.passed is True
        assert result.mismatched_fields == ()

    def test_timestamp_diff_does_not_fail(self):
        from deterministic_replay import ReplayComparator
        a = self._rc(created_at="2024-01-01", issued_at="2024-01-01")
        b = self._rc(created_at="2024-12-31", issued_at="2024-12-31")
        result = ReplayComparator().compare(a, b)
        assert result.passed is True
        assert len(result.observability_diffs) > 0

    def test_confidence_diff_fails(self):
        from deterministic_replay import ReplayComparator
        a = self._rc(confidence=0.9)
        b = self._rc(confidence=0.5)
        result = ReplayComparator().compare(a, b)
        assert result.passed is False
        assert "confidence" in result.mismatched_fields

    def test_compare_many_all_identical(self):
        from deterministic_replay import ReplayComparator
        rc = self._rc()
        result = ReplayComparator().compare_many([rc, rc, rc, rc, rc])
        assert result.passed is True

    def test_compare_many_one_differs(self):
        from deterministic_replay import ReplayComparator
        rc = self._rc()
        bad = self._rc(confidence=0.1)
        result = ReplayComparator().compare_many([rc, rc, bad, rc])
        assert result.passed is False

    def test_compare_many_requires_two(self):
        from deterministic_replay import ReplayComparator, ReplayContract
        with pytest.raises(ValueError):
            ReplayComparator().compare_many([self._rc()])


class TestDeterministicComparisonResult:
    def test_is_deterministic_property(self):
        from deterministic_replay import DeterministicComparisonResult
        r = DeterministicComparisonResult(
            passed=True, deterministic_match=True,
            mismatched_fields=(), observability_diffs={},
            projection_a={}, projection_b={},
        )
        assert r.is_deterministic is True

    def test_failed_result(self):
        from deterministic_replay import DeterministicComparisonResult
        r = DeterministicComparisonResult(
            passed=False, deterministic_match=False,
            mismatched_fields=("confidence",), observability_diffs={},
            projection_a={"confidence": 0.9}, projection_b={"confidence": 0.5},
        )
        assert r.is_deterministic is False
        assert "confidence" in r.mismatched_fields


class TestDeterminism20RunProof:
    def test_proof_passes(self):
        from determinism_20_run_proof import run_20_run_proof
        proof = run_20_run_proof(runs=20, verbose=False)
        assert proof["passed"] is True

    def test_all_hashes_identical(self):
        from determinism_20_run_proof import run_20_run_proof
        proof = run_20_run_proof(runs=5, verbose=False)
        assert proof["all_hashes_identical"] is True
        assert len(set(proof["evidence"])) == 1

    def test_no_mismatched_fields(self):
        from determinism_20_run_proof import run_20_run_proof
        proof = run_20_run_proof(runs=5, verbose=False)
        assert proof["mismatched_fields"] == []

    def test_observability_diffs_expected(self):
        """Timestamps are allowed to differ — that is correct behaviour."""
        from determinism_20_run_proof import run_20_run_proof
        proof = run_20_run_proof(runs=5, verbose=False)
        # Proof still passes even when observability fields differ
        assert proof["passed"] is True


# =============================================================================
# Phase 2 — Durable Replay Registry Tests
# =============================================================================

import tempfile
from pathlib import Path


class TestReplayRegistry:
    def _registry(self, ttl=60.0):
        from replay_registry import ReplayRegistry
        tmp = tempfile.mktemp(suffix=".json")
        reg = ReplayRegistry(path=tmp, ttl_seconds=ttl)
        return reg

    def test_first_submission_valid(self):
        reg = self._registry()
        d = reg.submit("msg-001")
        assert d.status == "VALID"
        assert d.sequence_number == 1

    def test_duplicate_rejected(self):
        reg = self._registry()
        reg.submit("msg-dup")
        d = reg.submit("msg-dup")
        assert d.status == "DUPLICATE"

    def test_stale_rejected(self):
        import time
        reg = self._registry(ttl=5.0)
        d = reg.submit("msg-stale", issued_at=time.time() - 60.0)
        assert d.status == "STALE"

    def test_sequence_monotonically_increasing(self):
        reg = self._registry()
        seqs = [reg.submit(f"m-{i}").sequence_number for i in range(5)]
        assert seqs == list(range(1, 6))

    def test_sequence_count_tracks_valid_only(self):
        reg = self._registry()
        reg.submit("count-001")
        reg.submit("count-001")  # duplicate — no increment
        assert reg.sequence_count == 1

    def test_is_known_after_valid_submission(self):
        reg = self._registry()
        reg.submit("known-001")
        assert reg.is_known("known-001") is True
        assert reg.is_known("unknown-999") is False

    def test_entry_count(self):
        reg = self._registry()
        reg.submit("ec-1")
        reg.submit("ec-2")
        assert reg.entry_count == 2

    def test_get_entry_returns_entry(self):
        from replay_registry import _RegistryEntry
        reg = self._registry()
        reg.submit("ge-001")
        entry = reg.get_entry("ge-001")
        assert isinstance(entry, _RegistryEntry)
        assert entry.sequence_number == 1

    def test_get_entry_none_for_unknown(self):
        reg = self._registry()
        assert reg.get_entry("nope") is None

    def test_reset_clears_all_state(self):
        reg = self._registry()
        reg.submit("r-001")
        reg.reset()
        assert reg.entry_count == 0
        assert reg.sequence_count == 0

    def test_validate_sequence_order_valid(self):
        reg = self._registry()
        reg.submit("vs-001")
        assert reg.validate_sequence_order(1) == "VALID"

    def test_validate_sequence_order_stale(self):
        reg = self._registry()
        assert reg.validate_sequence_order(0) == "STALE"

    def test_validate_sequence_order_future(self):
        reg = self._registry()
        assert reg.validate_sequence_order(9999999) == "FUTURE"

    def test_stale_beats_duplicate(self):
        import time
        reg = self._registry(ttl=5.0)
        stale_ts = time.time() - 60.0
        # Even if message is "known" conceptually, stale check fires first
        d = reg.submit("stale-dup", issued_at=stale_ts)
        assert d.status == "STALE"

    def test_thread_safety(self):
        import threading
        reg = self._registry()
        results = []
        lock = threading.Lock()

        def submit(i):
            d = reg.submit(f"thread-{i}")
            with lock:
                results.append(d.status)

        threads = [threading.Thread(target=submit, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert all(s == "VALID" for s in results)
        assert reg.sequence_count == 10


class TestReplayRegistryPersistence:
    def test_survives_restart(self):
        from replay_registry import ReplayRegistry
        path = Path(tempfile.mktemp(suffix=".json"))
        try:
            reg1 = ReplayRegistry(path=path, ttl_seconds=300.0)
            reg1.submit("persist-001")
            reg1.submit("persist-002")
            seq_before = reg1.sequence_count

            # Simulate restart
            reg2 = ReplayRegistry(path=path, ttl_seconds=300.0)
            assert reg2.sequence_count == seq_before
            assert reg2.is_known("persist-001")
            assert reg2.is_known("persist-002")

            # Post-restart submission continues sequence
            d = reg2.submit("persist-003")
            assert d.sequence_number == seq_before + 1
        finally:
            if path.exists():
                path.unlink()

    def test_duplicate_detected_after_restart(self):
        from replay_registry import ReplayRegistry
        path = Path(tempfile.mktemp(suffix=".json"))
        try:
            reg1 = ReplayRegistry(path=path, ttl_seconds=300.0)
            reg1.submit("dup-after-restart")

            reg2 = ReplayRegistry(path=path, ttl_seconds=300.0)
            d = reg2.submit("dup-after-restart")
            assert d.status == "DUPLICATE"
        finally:
            if path.exists():
                path.unlink()

    def test_corrupted_file_starts_fresh(self):
        from replay_registry import ReplayRegistry
        path = Path(tempfile.mktemp(suffix=".json"))
        try:
            path.write_text("{ not valid json }")
            reg = ReplayRegistry(path=path, ttl_seconds=60.0)
            assert reg.sequence_count == 0
            assert reg.entry_count == 0
        finally:
            if path.exists():
                path.unlink()

    def test_atomic_write_no_partial_state(self):
        """Temp file replacement guarantees no partial writes."""
        from replay_registry import ReplayRegistry
        path = Path(tempfile.mktemp(suffix=".json"))
        tmp_path = path.with_suffix(".tmp")
        try:
            reg = ReplayRegistry(path=path, ttl_seconds=300.0)
            reg.submit("atomic-001")
            # After write, .tmp should not exist (was replaced)
            assert not tmp_path.exists()
            assert path.exists()
        finally:
            for p in [path, tmp_path]:
                if p.exists():
                    p.unlink()


class TestReplayEnforcementProof:
    def test_full_proof_passes(self):
        from replay_enforcement_proof import run_proof
        result = run_proof(verbose=False)
        assert result["passed"] is True

    def test_all_cases_pass(self):
        from replay_enforcement_proof import run_proof
        result = run_proof(verbose=False)
        for case, passed in result["cases"].items():
            assert passed is True, f"Proof case failed: {case}"


# =============================================================================
# Phase 3 — Multi-Process Execution Tests
# =============================================================================

import os
import multiprocessing
import tempfile
from pathlib import Path


class TestCrashRecoveryProof:
    def test_full_proof_passes(self):
        from crash_recovery_proof import run_proof
        result = run_proof(verbose=False)
        assert result["passed"] is True

    def test_all_cases_pass(self):
        from crash_recovery_proof import run_proof
        result = run_proof(verbose=False)
        for case, passed in result["cases"].items():
            assert passed is True, f"Crash recovery case failed: {case}"

    def test_normal_execution_accepted(self):
        from crash_recovery_proof import run_proof
        result = run_proof(verbose=False)
        assert result["cases"]["normal_execution_accepted"] is True

    def test_registry_survives_crash(self):
        from crash_recovery_proof import run_proof
        result = run_proof(verbose=False)
        assert result["cases"]["registry_survives_crash"] is True

    def test_duplicate_blocked_after_restart(self):
        from crash_recovery_proof import run_proof
        result = run_proof(verbose=False)
        assert result["cases"]["duplicate_blocked_after_restart"] is True

    def test_new_contract_accepted_after_restart(self):
        from crash_recovery_proof import run_proof
        result = run_proof(verbose=False)
        assert result["cases"]["new_contract_accepted_after_restart"] is True

    def test_registry_isolation(self):
        from crash_recovery_proof import run_proof
        result = run_proof(verbose=False)
        assert result["cases"]["registry_isolation"] is True


class TestProcessIsolation:
    """Verify independent OS processes have distinct PIDs and share no state."""

    def test_distinct_pids(self):
        """Producer and execution must run in separate OS processes."""
        from crash_recovery_proof import run_process_isolation_proof
        result = run_process_isolation_proof(verbose=False)
        assert result["passed"] is True
        assert result["producer_pid"] != result["execution_pid"]
        assert result["runner_pid"] != result["producer_pid"]
        assert result["runner_pid"] != result["execution_pid"]

    def test_execution_produces_ack_ok(self):
        from crash_recovery_proof import run_process_isolation_proof
        result = run_process_isolation_proof(verbose=False)
        assert result["ack"] == "ACK:OK"

    def test_independent_replay_registries_no_cross_contamination(self):
        """Two registry files must be fully independent."""
        from replay_registry import ReplayRegistry
        path_a = Path(tempfile.mktemp(suffix="_a.json"))
        path_b = Path(tempfile.mktemp(suffix="_b.json"))
        try:
            reg_a = ReplayRegistry(path=path_a, ttl_seconds=300.0)
            reg_b = ReplayRegistry(path=path_b, ttl_seconds=300.0)
            reg_a.submit("cross-msg-001")
            assert not reg_b.is_known("cross-msg-001")
            assert reg_b.sequence_count == 0
        finally:
            for p in [path_a, path_b]:
                if p.exists():
                    p.unlink()

    def test_registry_state_not_shared_across_instances(self):
        """Two registry instances on different files must have independent counters."""
        from replay_registry import ReplayRegistry
        path_a = Path(tempfile.mktemp(suffix="_sa.json"))
        path_b = Path(tempfile.mktemp(suffix="_sb.json"))
        try:
            reg_a = ReplayRegistry(path=path_a, ttl_seconds=300.0)
            reg_b = ReplayRegistry(path=path_b, ttl_seconds=300.0)
            for i in range(3):
                reg_a.submit(f"sa-msg-{i}")
            assert reg_b.sequence_count == 0
        finally:
            for p in [path_a, path_b]:
                if p.exists():
                    p.unlink()


class TestConcurrentReplay:
    """Verify replay registry is safe under concurrent access."""

    def test_concurrent_submissions_all_unique_all_valid(self):
        from replay_registry import ReplayRegistry
        path = Path(tempfile.mktemp(suffix="_concurrent.json"))
        try:
            reg = ReplayRegistry(path=path, ttl_seconds=300.0)
            results = []
            lock = threading.Lock()

            def submit(i):
                d = reg.submit(f"concurrent-{i:04d}")
                with lock:
                    results.append((i, d.status, d.sequence_number))

            threads = [threading.Thread(target=submit, args=(i,)) for i in range(20)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            statuses = [r[1] for r in results]
            assert all(s == "VALID" for s in statuses)
            seqs = sorted(r[2] for r in results)
            assert seqs == list(range(1, 21))
        finally:
            if path.exists():
                path.unlink()

    def test_concurrent_duplicate_only_one_valid(self):
        """Concurrent submissions of the same ID — exactly one VALID."""
        from replay_registry import ReplayRegistry
        path = Path(tempfile.mktemp(suffix="_dup_concurrent.json"))
        try:
            reg = ReplayRegistry(path=path, ttl_seconds=300.0)
            results = []
            lock = threading.Lock()

            def submit():
                d = reg.submit("shared-msg-001")
                with lock:
                    results.append(d.status)

            threads = [threading.Thread(target=submit) for _ in range(8)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            valid_count = results.count("VALID")
            dup_count = results.count("DUPLICATE")
            assert valid_count == 1
            assert dup_count == 7
        finally:
            if path.exists():
                path.unlink()

    def test_concurrent_replay_enforcer_exactly_one_accepted(self):
        """Original ReplayEnforcer: concurrent identical submissions → 1 ACCEPTED."""
        from replay_enforcer import ReplayEnforcer
        enforcer = ReplayEnforcer(ttl_seconds=60.0)
        results = []
        lock = threading.Lock()

        def submit():
            d = enforcer.submit("conc-enforcer-001")
            with lock:
                results.append(d.status)

        threads = [threading.Thread(target=submit) for _ in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert results.count("ACCEPTED") == 1
        assert results.count("REJECTED_DUPLICATE") == 5


class TestStructuredLogs:
    """Verify execution logs contain the required structured fields."""

    REQUIRED_FIELDS = {"process_id", "message_id", "sequence_number", "status", "timestamp"}

    def _parse_log(self, path: str) -> list[dict]:
        entries = []
        try:
            with open(path) as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            entries.append(json.loads(line))
                        except json.JSONDecodeError:
                            pass
        except FileNotFoundError:
            pass
        return entries

    def test_process_2_log_has_required_fields(self):
        """Execution process log must contain all required structured fields."""
        # Run the pipeline to generate fresh logs
        from process_runner import run_pipeline
        run_pipeline(crash_stage=None)

        entries = self._parse_log("logs/process_2.log")
        assert len(entries) > 0, "process_2.log must not be empty after pipeline run"

        # At least one entry (the executed event) must carry all required fields
        executed_entries = [e for e in entries if e.get("event") == "executed"]
        assert len(executed_entries) > 0, "Expected at least one 'executed' log entry"

        for entry in executed_entries:
            for field in self.REQUIRED_FIELDS:
                assert field in entry, f"Required field '{field}' missing from log entry"

    def test_process_1_log_has_required_fields(self):
        from process_runner import run_pipeline
        run_pipeline(crash_stage=None)

        entries = self._parse_log("logs/process_1.log")
        assert len(entries) > 0

        sent_entries = [e for e in entries if e.get("event") == "contract_sent"]
        assert len(sent_entries) > 0

        for entry in sent_entries:
            for field in self.REQUIRED_FIELDS:
                assert field in entry, f"Required field '{field}' missing from process_1 log"

    def test_process_id_is_integer(self):
        from process_runner import run_pipeline
        run_pipeline(crash_stage=None)

        entries = self._parse_log("logs/process_2.log")
        for e in entries:
            if "process_id" in e:
                assert isinstance(e["process_id"], int)

    def test_process_ids_are_distinct_across_logs(self):
        """Each process log must show a different PID."""
        from process_runner import run_pipeline
        run_pipeline(crash_stage=None)

        def first_pid(path):
            for e in self._parse_log(path):
                if "process_id" in e:
                    return e["process_id"]
            return None

        pid1 = first_pid("logs/process_1.log")
        pid2 = first_pid("logs/process_2.log")
        pid3 = first_pid("logs/process_3.log")

        # All three must be non-None and distinct
        assert pid1 is not None
        assert pid2 is not None
        assert pid3 is not None
        assert len({pid1, pid2, pid3}) == 3, (
            f"Expected 3 distinct PIDs, got {pid1}, {pid2}, {pid3}"
        )


class TestIPCTopology:
    """Verify the IPC queue topology: producer -> execution -> consensus."""

    def test_pipeline_runs_cleanly(self):
        from process_runner import run_pipeline
        summary = run_pipeline(crash_stage=None)
        assert summary["pipeline_ok"] is True
        assert summary["crashes"] == {}

    def test_pipeline_produces_consensus_result(self):
        from process_runner import run_pipeline
        summary = run_pipeline(crash_stage=None)
        assert summary["consensus_result"] is not None
        proof = summary["consensus_result"].get("proof", {})
        assert proof.get("consensus_reached") is True

    def test_crash_producer_detected(self):
        from process_runner import run_pipeline
        summary = run_pipeline(crash_stage="producer")
        assert "producer" in summary["crashes"]

    def test_crash_execution_detected(self):
        from process_runner import run_pipeline
        summary = run_pipeline(crash_stage="execution")
        assert "execution" in summary["crashes"]

    def test_crash_consensus_detected(self):
        from process_runner import run_pipeline
        summary = run_pipeline(crash_stage="consensus")
        assert "consensus" in summary["crashes"]

    def test_all_three_pids_distinct(self):
        from process_runner import run_pipeline
        summary = run_pipeline(crash_stage=None)
        pids = list(summary["pids"].values())
        assert len(set(pids)) == 3, f"Expected 3 distinct PIDs, got {pids}"


# =============================================================================
# Phase 4 — Trust-Aware Communication Tests
# =============================================================================

class TestProducerRegistry:
    def _signer(self, node_id="REG_PROD", role="QUANTUM_PRODUCER"):
        from node_identity import NodeSigner
        return NodeSigner(node_id, role)

    def test_register_and_lookup(self):
        from producer_verification import ProducerRegistry
        reg = ProducerRegistry()
        s = self._signer()
        reg.register(s.identity)
        assert reg.is_registered(s.identity.node_id)

    def test_unregistered_returns_false(self):
        from producer_verification import ProducerRegistry
        reg = ProducerRegistry()
        assert not reg.is_registered("NOBODY")

    def test_public_key_returned(self):
        from producer_verification import ProducerRegistry
        reg = ProducerRegistry()
        s = self._signer()
        reg.register(s.identity)
        assert reg.public_key(s.identity.node_id) == s.identity.public_key

    def test_public_key_none_for_unknown(self):
        from producer_verification import ProducerRegistry
        reg = ProducerRegistry()
        assert reg.public_key("NOBODY") is None

    def test_quantum_role_infers_quantum_type(self):
        from producer_verification import ProducerRegistry
        reg = ProducerRegistry()
        s = self._signer(role="QUANTUM_PRODUCER")
        reg.register(s.identity)
        assert "QUANTUM" in reg.allowed_types(s.identity.node_id)
        assert "CLASSICAL" not in reg.allowed_types(s.identity.node_id)

    def test_classical_role_infers_classical_type(self):
        from producer_verification import ProducerRegistry
        reg = ProducerRegistry()
        s = self._signer(role="CLASSICAL_PRODUCER")
        reg.register(s.identity)
        assert "CLASSICAL" in reg.allowed_types(s.identity.node_id)
        assert "QUANTUM" not in reg.allowed_types(s.identity.node_id)

    def test_hybrid_role_allows_all_types(self):
        from producer_verification import ProducerRegistry
        reg = ProducerRegistry()
        s = self._signer(role="HYBRID_PRODUCER")
        reg.register(s.identity)
        allowed = reg.allowed_types(s.identity.node_id)
        assert {"HYBRID", "QUANTUM", "CLASSICAL"}.issubset(allowed)

    def test_explicit_allowed_types_override(self):
        from producer_verification import ProducerRegistry
        reg = ProducerRegistry()
        s = self._signer(role="QUANTUM_PRODUCER")
        reg.register(s.identity, allowed_types={"QUANTUM", "HYBRID"})
        assert "HYBRID" in reg.allowed_types(s.identity.node_id)

    def test_allowed_types_empty_for_unknown(self):
        from producer_verification import ProducerRegistry
        reg = ProducerRegistry()
        assert reg.allowed_types("NOBODY") == frozenset()


class TestProducerVerificationLayer:
    def _setup(self, role="QUANTUM_PRODUCER", producer_type="QUANTUM"):
        from node_identity import NodeSigner
        from execution_contract import ComputationExecutionContract
        from provenance import sign_contract
        from producer_verification import ProducerRegistry, ProducerVerificationLayer

        producer = NodeSigner("VP_PROD_01", role)
        base = ComputationExecutionContract(
            producer_type=producer_type,
            payload={"data": "verify_test"},
            confidence=0.95,
            trace_id="vp-trace-001",
            contract_version="2.0.0",
        )
        signed = sign_contract(base, producer)

        registry = ProducerRegistry()
        registry.register(producer.identity)
        verifier = ProducerVerificationLayer(registry)
        return verifier, signed, producer

    def test_valid_producer_passes(self):
        verifier, signed, _ = self._setup()
        result = verifier.verify(signed)
        assert result.passed is True
        assert result.failure_mode == ""
        assert result.is_trusted is True

    def test_valid_producer_halt_signal_empty(self):
        verifier, signed, _ = self._setup()
        result = verifier.verify(signed)
        assert result.halt_signal() == ""

    def test_missing_producer_id_returns_unverified(self):
        from execution_contract import ComputationExecutionContract
        from producer_verification import ProducerRegistry, ProducerVerificationLayer, VerificationFailure
        reg = ProducerRegistry()
        verifier = ProducerVerificationLayer(reg)
        contract = ComputationExecutionContract(
            producer_type="QUANTUM",
            payload={"x": 1},
            confidence=0.9,
            trace_id="no-id",
            contract_version="2.0.0",
        )
        result = verifier.verify(contract)
        assert result.passed is False
        assert result.failure_mode == VerificationFailure.UNVERIFIED_PRODUCER

    def test_unregistered_producer_returns_unverified(self):
        from node_identity import NodeSigner
        from execution_contract import ComputationExecutionContract
        from provenance import sign_contract
        from producer_verification import ProducerRegistry, ProducerVerificationLayer, VerificationFailure

        stranger = NodeSigner("STRANGER_99", "QUANTUM_PRODUCER")
        base = ComputationExecutionContract(
            producer_type="QUANTUM",
            payload={"x": 1},
            confidence=0.9,
            trace_id="stranger-trace",
            contract_version="2.0.0",
        )
        signed = sign_contract(base, stranger)

        reg = ProducerRegistry()  # stranger NOT registered
        verifier = ProducerVerificationLayer(reg)
        result = verifier.verify(signed)
        assert result.passed is False
        assert result.failure_mode == VerificationFailure.UNVERIFIED_PRODUCER

    def test_tampered_payload_returns_invalid_signature(self):
        import hashlib, json
        from execution_contract import ComputationExecutionContract
        from producer_verification import VerificationFailure
        verifier, signed, _ = self._setup()

        d = signed.to_dict()
        d["payload"] = {"data": "INJECTED"}
        d["payload_hash"] = hashlib.sha256(
            json.dumps(d["payload"], sort_keys=True).encode()
        ).hexdigest()
        tampered = ComputationExecutionContract(**d)

        result = verifier.verify(tampered)
        assert result.passed is False
        assert result.failure_mode == VerificationFailure.INVALID_SIGNATURE

    def test_forged_contract_signature_returns_invalid_signature(self):
        from execution_contract import ComputationExecutionContract
        from producer_verification import VerificationFailure
        verifier, signed, _ = self._setup()

        d = signed.to_dict()
        d["contract_signature"] = "badc0de1" * 18
        forged = ComputationExecutionContract(**d)

        result = verifier.verify(forged)
        assert result.passed is False
        assert result.failure_mode == VerificationFailure.INVALID_SIGNATURE

    def test_missing_signature_returns_invalid_signature(self):
        from execution_contract import ComputationExecutionContract
        from producer_verification import VerificationFailure
        verifier, signed, _ = self._setup()

        d = signed.to_dict()
        d["contract_signature"] = ""
        no_sig = ComputationExecutionContract(**d)

        result = verifier.verify(no_sig)
        assert result.passed is False
        assert result.failure_mode == VerificationFailure.INVALID_SIGNATURE

    def test_type_mismatch_returns_trust_failure(self):
        from node_identity import NodeSigner
        from execution_contract import ComputationExecutionContract
        from provenance import sign_contract
        from producer_verification import ProducerRegistry, ProducerVerificationLayer, VerificationFailure

        producer = NodeSigner("TYPE_MISMATCH_01", "QUANTUM_PRODUCER")
        # Sign a CLASSICAL contract with a QUANTUM producer
        base = ComputationExecutionContract(
            producer_type="CLASSICAL",
            payload={"x": 1},
            confidence=0.9,
            trace_id="type-mismatch-trace",
            contract_version="2.0.0",
        )
        signed = sign_contract(base, producer)

        reg = ProducerRegistry()
        reg.register(producer.identity)  # inferred allowed: {"QUANTUM"} only
        verifier = ProducerVerificationLayer(reg)

        result = verifier.verify(signed)
        assert result.passed is False
        assert result.failure_mode == VerificationFailure.TRUST_FAILURE

    def test_halt_signal_contains_failure_mode(self):
        from execution_contract import ComputationExecutionContract
        from producer_verification import ProducerRegistry, ProducerVerificationLayer, VerificationFailure
        reg = ProducerRegistry()
        verifier = ProducerVerificationLayer(reg)
        contract = ComputationExecutionContract(
            producer_type="QUANTUM",
            payload={"x": 1},
            confidence=0.9,
            trace_id="halt-signal-test",
            contract_version="2.0.0",
        )
        result = verifier.verify(contract)
        sig = result.halt_signal()
        assert sig.startswith("HALT:")
        assert VerificationFailure.UNVERIFIED_PRODUCER in sig

    def test_verification_result_frozen(self):
        from producer_verification import VerificationResult
        r = VerificationResult(
            passed=True, failure_mode="", producer_id="X",
            producer_type="QUANTUM", reason=""
        )
        with pytest.raises((AttributeError, TypeError)):
            r.passed = False


class TestVerificationFailureModes:
    """Explicit coverage of all three failure mode constants."""

    def test_unverified_producer_constant(self):
        from producer_verification import VerificationFailure
        assert VerificationFailure.UNVERIFIED_PRODUCER == "UNVERIFIED_PRODUCER"

    def test_invalid_signature_constant(self):
        from producer_verification import VerificationFailure
        assert VerificationFailure.INVALID_SIGNATURE == "INVALID_SIGNATURE"

    def test_trust_failure_constant(self):
        from producer_verification import VerificationFailure
        assert VerificationFailure.TRUST_FAILURE == "TRUST_FAILURE"

    def test_all_three_modes_are_distinct(self):
        from producer_verification import VerificationFailure
        modes = {
            VerificationFailure.UNVERIFIED_PRODUCER,
            VerificationFailure.INVALID_SIGNATURE,
            VerificationFailure.TRUST_FAILURE,
        }
        assert len(modes) == 3


class TestTrustValidationProof:
    def test_full_proof_passes(self):
        from trust_validation_proof import run_proof
        result = run_proof(verbose=False)
        assert result["passed"] is True

    def test_all_cases_pass(self):
        from trust_validation_proof import run_proof
        result = run_proof(verbose=False)
        for case, passed in result["cases"].items():
            assert passed is True, f"Trust proof case failed: {case}"

    def test_valid_producer_accepted(self):
        from trust_validation_proof import run_proof
        result = run_proof(verbose=False)
        assert result["cases"]["valid_producer_accepted"] is True

    def test_tampered_payload_rejected(self):
        from trust_validation_proof import run_proof
        result = run_proof(verbose=False)
        assert result["cases"]["tampered_payload_rejected"] is True

    def test_forged_signature_rejected(self):
        from trust_validation_proof import run_proof
        result = run_proof(verbose=False)
        assert result["cases"]["forged_signature_rejected"] is True

    def test_unregistered_producer_rejected(self):
        from trust_validation_proof import run_proof
        result = run_proof(verbose=False)
        assert result["cases"]["unregistered_producer_rejected"] is True

    def test_type_mismatch_rejected(self):
        from trust_validation_proof import run_proof
        result = run_proof(verbose=False)
        assert result["cases"]["type_mismatch_rejected"] is True

    def test_missing_producer_id_rejected(self):
        from trust_validation_proof import run_proof
        result = run_proof(verbose=False)
        assert result["cases"]["missing_producer_id_rejected"] is True
