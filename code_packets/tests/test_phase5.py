"""
tests/test_phase5.py
Phase 5 — Additional tests to reach 250+ total.

Covers gaps across:
  - ReplayRegistry (FUTURE state, window edge cases, reset persistence)
  - ReplayEnforcer (eviction, reset, sequence count)
  - DeterministicComparisonResult (edge cases)
  - ReplayContract (field isolation, hash stability)
  - ProducerRegistry (re-register, empty types)
  - ProducerVerificationLayer (all three failure modes, halt signal format)
  - Proof runners (determinism, replay enforcement, crash recovery, trust)
  - CrashRecovery (sequence continuity, isolation variants)
  - ProcessIsolation (ack value, pid distinctness)
  - StructuredLogs (field types, cross-process pid uniqueness)
  - ConcurrentReplay (high-contention uniqueness)
  - Sequence validation boundary conditions
"""

from __future__ import annotations

import hashlib
import json
import tempfile
import threading
import time
from pathlib import Path

import pytest


# =============================================================================
# ReplayRegistry — extended
# =============================================================================

class TestReplayRegistryExtended:

    def _reg(self, ttl=60.0):
        from replay_registry import ReplayRegistry
        return ReplayRegistry(path=tempfile.mktemp(suffix=".json"), ttl_seconds=ttl)

    def test_future_sequence_never_triggered_on_normal_increment(self):
        """Normal sequential submits never hit FUTURE."""
        reg = self._reg()
        for i in range(10):
            d = reg.submit(f"future-normal-{i}")
            assert d.status == "VALID"

    def test_validate_sequence_order_exactly_at_counter(self):
        reg = self._reg()
        reg.submit("seq-exact-001")
        assert reg.validate_sequence_order(1) == "VALID"

    def test_validate_sequence_order_one_above_counter(self):
        """One above current counter is still VALID (within max gap)."""
        reg = self._reg()
        reg.submit("seq-above-001")
        assert reg.validate_sequence_order(2) == "VALID"

    def test_validate_sequence_order_negative_is_stale(self):
        reg = self._reg()
        assert reg.validate_sequence_order(-1) == "STALE"

    def test_reset_then_sequence_restarts_at_one(self):
        reg = self._reg()
        reg.submit("pre-reset-001")
        reg.submit("pre-reset-002")
        reg.reset()
        d = reg.submit("post-reset-001")
        assert d.sequence_number == 1

    def test_stale_does_not_increment_sequence(self):
        reg = self._reg(ttl=1.0)
        d = reg.submit("stale-no-seq", issued_at=time.time() - 10.0)
        assert d.status == "STALE"
        assert reg.sequence_count == 0

    def test_duplicate_does_not_increment_sequence(self):
        reg = self._reg()
        reg.submit("dup-seq-001")
        reg.submit("dup-seq-001")
        assert reg.sequence_count == 1

    def test_entry_count_does_not_grow_on_duplicate(self):
        reg = self._reg()
        reg.submit("ec-dup-001")
        reg.submit("ec-dup-001")
        assert reg.entry_count == 1

    def test_multiple_stale_submissions_leave_registry_empty(self):
        reg = self._reg(ttl=1.0)
        for i in range(5):
            reg.submit(f"ms-{i}", issued_at=time.time() - 100.0)
        assert reg.entry_count == 0
        assert reg.sequence_count == 0

    def test_persist_called_only_on_valid(self):
        """Registry file only grows on VALID submissions."""
        path = Path(tempfile.mktemp(suffix=".json"))
        try:
            from replay_registry import ReplayRegistry
            reg = ReplayRegistry(path=path, ttl_seconds=60.0)
            reg.submit("persist-valid-001")
            size_after_valid = path.stat().st_size

            reg.submit("persist-valid-001")  # duplicate — no write
            size_after_dup = path.stat().st_size

            assert size_after_valid == size_after_dup
        finally:
            if path.exists():
                path.unlink()

    def test_get_entry_has_correct_sequence(self):
        from replay_registry import _RegistryEntry
        reg = self._reg()
        reg.submit("ge-seq-001")
        reg.submit("ge-seq-002")
        e2 = reg.get_entry("ge-seq-002")
        assert isinstance(e2, _RegistryEntry)
        assert e2.sequence_number == 2

    def test_is_known_false_before_submit(self):
        reg = self._reg()
        assert reg.is_known("never-submitted") is False

    def test_is_known_true_after_submit(self):
        reg = self._reg()
        reg.submit("known-after-001")
        assert reg.is_known("known-after-001") is True

    def test_corrupted_file_recovers_to_zero_state(self):
        from replay_registry import ReplayRegistry
        path = Path(tempfile.mktemp(suffix=".json"))
        try:
            path.write_text("{bad json")
            reg = ReplayRegistry(path=path, ttl_seconds=60.0)
            assert reg.entry_count == 0
            assert reg.sequence_count == 0
        finally:
            if path.exists():
                path.unlink()

    def test_empty_file_treated_as_fresh(self):
        from replay_registry import ReplayRegistry
        path = Path(tempfile.mktemp(suffix=".json"))
        try:
            path.write_text("")
            reg = ReplayRegistry(path=path, ttl_seconds=60.0)
            assert reg.sequence_count == 0
        finally:
            if path.exists():
                path.unlink()


# =============================================================================
# ReplayEnforcer — extended
# =============================================================================

class TestReplayEnforcerExtended:

    def _enforcer(self, ttl=60.0):
        from replay_enforcer import ReplayEnforcer
        return ReplayEnforcer(ttl_seconds=ttl)

    def test_sequence_increments_only_on_accepted(self):
        e = self._enforcer()
        e.submit("art-A")
        e.submit("art-A")  # duplicate
        assert e.sequence_count == 1

    def test_stale_does_not_increment_sequence_count(self):
        e = self._enforcer(ttl=1.0)
        e.submit("art-stale", issued_at=time.monotonic() - 100.0)
        assert e.sequence_count == 0

    def test_reset_clears_sequence_and_cache(self):
        e = self._enforcer()
        e.submit("art-reset-001")
        e.reset()
        assert e.sequence_count == 0
        d = e.submit("art-reset-001")
        assert d.status == "ACCEPTED"

    def test_many_unique_artifacts_all_accepted(self):
        e = self._enforcer()
        for i in range(50):
            d = e.submit(f"bulk-art-{i:04d}")
            assert d.status == "ACCEPTED"
        assert e.sequence_count == 50

    def test_reason_empty_on_accepted(self):
        e = self._enforcer()
        d = e.submit("reason-test-001")
        assert d.reason == ""

    def test_reason_non_empty_on_duplicate(self):
        e = self._enforcer()
        e.submit("dup-reason-001")
        d = e.submit("dup-reason-001")
        assert d.reason != ""

    def test_reason_non_empty_on_stale(self):
        e = self._enforcer(ttl=1.0)
        d = e.submit("stale-reason-001", issued_at=time.monotonic() - 10.0)
        assert d.reason != ""

    def test_sequence_id_zero_on_stale(self):
        e = self._enforcer(ttl=1.0)
        d = e.submit("stale-seq-001", issued_at=time.monotonic() - 10.0)
        assert d.sequence_id == 0

    def test_sequence_id_nonzero_on_duplicate(self):
        e = self._enforcer()
        e.submit("dup-seq-nonzero")
        d = e.submit("dup-seq-nonzero")
        assert d.sequence_id > 0

    def test_artifact_id_preserved_in_decision(self):
        e = self._enforcer()
        d = e.submit("preserve-id-001")
        assert d.artifact_id == "preserve-id-001"


# =============================================================================
# DeterministicComparisonResult — extended
# =============================================================================

class TestDeterministicComparisonResultExtended:

    def _result(self, passed=True, mismatched=(), obs_diffs=None):
        from deterministic_replay import DeterministicComparisonResult
        return DeterministicComparisonResult(
            passed=passed,
            deterministic_match=passed,
            mismatched_fields=mismatched,
            observability_diffs=obs_diffs or {},
            projection_a={"confidence": 0.9},
            projection_b={"confidence": 0.9},
        )

    def test_passed_true_is_deterministic(self):
        r = self._result(passed=True)
        assert r.is_deterministic is True

    def test_passed_false_not_deterministic(self):
        r = self._result(passed=False, mismatched=("confidence",))
        assert r.is_deterministic is False

    def test_empty_mismatched_fields_on_pass(self):
        r = self._result(passed=True)
        assert r.mismatched_fields == ()

    def test_multiple_mismatched_fields_captured(self):
        r = self._result(passed=False, mismatched=("confidence", "payload_hash"))
        assert "confidence" in r.mismatched_fields
        assert "payload_hash" in r.mismatched_fields

    def test_observability_diffs_recorded_on_pass(self):
        """A passing result can still have observability diffs (timestamps differ)."""
        r = self._result(passed=True, obs_diffs={"created_at": {"a": "T1", "b": "T2"}})
        assert len(r.observability_diffs) == 1
        assert r.passed is True

    def test_frozen_result_immutable(self):
        r = self._result()
        with pytest.raises((AttributeError, TypeError)):
            r.passed = False


# =============================================================================
# ReplayContract — extended
# =============================================================================

class TestReplayContractExtended:

    def _rc(self, msg_id="m1", confidence=0.9, ts="OK", tp="ACK:OK"):
        from deterministic_replay import ReplayContract
        ph = hashlib.sha256(json.dumps({"x": 1}).encode()).hexdigest()
        return ReplayContract(
            message_id=msg_id, payload_hash=ph,
            confidence=confidence, translation_status=ts, transport_status=tp,
        )

    def test_deterministic_projection_has_all_five_fields(self):
        from deterministic_replay import DETERMINISTIC_FIELDS
        rc = self._rc()
        proj = rc.deterministic_projection()
        assert set(proj.keys()) == DETERMINISTIC_FIELDS

    def test_observability_fields_not_in_projection(self):
        from deterministic_replay import OBSERVABILITY_FIELDS
        rc = self._rc()
        proj = rc.deterministic_projection()
        for f in OBSERVABILITY_FIELDS:
            assert f not in proj

    def test_hash_changes_when_confidence_changes(self):
        rc1 = self._rc(confidence=0.9)
        rc2 = self._rc(confidence=0.5)
        assert rc1.deterministic_hash() != rc2.deterministic_hash()

    def test_hash_changes_when_translation_status_changes(self):
        rc1 = self._rc(ts="OK")
        rc2 = self._rc(ts="DEGRADED")
        assert rc1.deterministic_hash() != rc2.deterministic_hash()

    def test_hash_changes_when_transport_status_changes(self):
        rc1 = self._rc(tp="ACK:OK")
        rc2 = self._rc(tp="HALT:REPLAY_DETECTED")
        assert rc1.deterministic_hash() != rc2.deterministic_hash()

    def test_hash_is_64_char_hex(self):
        rc = self._rc()
        h = rc.deterministic_hash()
        assert len(h) == 64
        int(h, 16)  # must be valid hex

    def test_observability_fields_default_empty(self):
        rc = self._rc()
        assert rc.created_at == ""
        assert rc.issued_at == ""
        assert rc.trace_timestamp == ""

    def test_comparator_symmetric(self):
        """compare(a, b).passed == compare(b, a).passed"""
        from deterministic_replay import ReplayComparator
        a = self._rc(confidence=0.9)
        b = self._rc(confidence=0.5)
        cmp = ReplayComparator()
        assert cmp.compare(a, b).passed == cmp.compare(b, a).passed


# =============================================================================
# ProducerRegistry — extended
# =============================================================================

class TestProducerRegistryExtended:

    def _signer(self, node_id, role="QUANTUM_PRODUCER"):
        from node_identity import NodeSigner
        return NodeSigner(node_id, role)

    def test_re_register_overwrites_allowed_types(self):
        from producer_verification import ProducerRegistry
        reg = ProducerRegistry()
        s = self._signer("REREG_01", "QUANTUM_PRODUCER")
        reg.register(s.identity)
        assert "CLASSICAL" not in reg.allowed_types(s.identity.node_id)
        reg.register(s.identity, allowed_types={"QUANTUM", "CLASSICAL"})
        assert "CLASSICAL" in reg.allowed_types(s.identity.node_id)

    def test_lookup_returns_tuple(self):
        from producer_verification import ProducerRegistry
        reg = ProducerRegistry()
        s = self._signer("LOOKUP_01")
        reg.register(s.identity)
        result = reg.lookup(s.identity.node_id)
        assert result is not None
        identity, types = result
        assert identity.node_id == "LOOKUP_01"
        assert isinstance(types, frozenset)

    def test_lookup_returns_none_for_unknown(self):
        from producer_verification import ProducerRegistry
        reg = ProducerRegistry()
        assert reg.lookup("NOBODY_999") is None

    def test_multiple_producers_independent(self):
        from producer_verification import ProducerRegistry
        reg = ProducerRegistry()
        a = self._signer("MULTI_A", "QUANTUM_PRODUCER")
        b = self._signer("MULTI_B", "CLASSICAL_PRODUCER")
        reg.register(a.identity)
        reg.register(b.identity)
        assert reg.is_registered("MULTI_A")
        assert reg.is_registered("MULTI_B")
        assert "QUANTUM" in reg.allowed_types("MULTI_A")
        assert "CLASSICAL" in reg.allowed_types("MULTI_B")
        assert "QUANTUM" not in reg.allowed_types("MULTI_B")

    def test_unknown_role_allows_all_types(self):
        from producer_verification import ProducerRegistry
        reg = ProducerRegistry()
        s = self._signer("UNKNOWN_ROLE_01", "SOME_OTHER_ROLE")
        reg.register(s.identity)
        allowed = reg.allowed_types(s.identity.node_id)
        assert {"QUANTUM", "CLASSICAL", "HYBRID"}.issubset(allowed)


# =============================================================================
# ProducerVerificationLayer — extended
# =============================================================================

class TestProducerVerificationLayerExtended:

    def _setup(self, role="QUANTUM_PRODUCER", ptype="QUANTUM"):
        from node_identity import NodeSigner
        from execution_contract import ComputationExecutionContract
        from provenance import sign_contract
        from producer_verification import ProducerRegistry, ProducerVerificationLayer

        producer = NodeSigner(f"PVL_EXT_{role}", role)
        base = ComputationExecutionContract(
            producer_type=ptype,
            payload={"data": "ext_verify_test"},
            confidence=0.95,
            trace_id=f"pvl-ext-{role.lower()}-001",
            contract_version="2.0.0",
        )
        signed = sign_contract(base, producer)
        reg = ProducerRegistry()
        reg.register(producer.identity)
        verifier = ProducerVerificationLayer(reg)
        return verifier, signed, producer

    def test_valid_result_is_trusted(self):
        verifier, signed, _ = self._setup()
        result = verifier.verify(signed)
        assert result.is_trusted is True

    def test_valid_result_halt_signal_empty_string(self):
        verifier, signed, _ = self._setup()
        result = verifier.verify(signed)
        assert result.halt_signal() == ""

    def test_unverified_halt_signal_starts_with_halt(self):
        from execution_contract import ComputationExecutionContract
        from producer_verification import ProducerRegistry, ProducerVerificationLayer
        reg = ProducerRegistry()
        verifier = ProducerVerificationLayer(reg)
        contract = ComputationExecutionContract(
            producer_type="QUANTUM", payload={"x": 1}, confidence=0.9,
            trace_id="halt-unverified-ext", contract_version="2.0.0",
        )
        result = verifier.verify(contract)
        sig = result.halt_signal()
        assert sig.startswith("HALT:UNVERIFIED_PRODUCER")

    def test_invalid_signature_halt_signal_contains_mode(self):
        from execution_contract import ComputationExecutionContract
        from producer_verification import VerificationFailure
        verifier, signed, _ = self._setup()

        d = signed.to_dict()
        d["contract_signature"] = "00" * 64
        forged = ComputationExecutionContract(**d)
        result = verifier.verify(forged)
        assert VerificationFailure.INVALID_SIGNATURE in result.halt_signal()

    def test_trust_failure_halt_signal_contains_mode(self):
        from node_identity import NodeSigner
        from execution_contract import ComputationExecutionContract
        from provenance import sign_contract
        from producer_verification import ProducerRegistry, ProducerVerificationLayer, VerificationFailure

        producer = NodeSigner("TF_EXT_01", "CLASSICAL_PRODUCER")
        base = ComputationExecutionContract(
            producer_type="QUANTUM",  # mismatch
            payload={"x": 1}, confidence=0.9,
            trace_id="tf-ext-001", contract_version="2.0.0",
        )
        signed = sign_contract(base, producer)
        reg = ProducerRegistry()
        reg.register(producer.identity)  # allowed: {"CLASSICAL"}
        verifier = ProducerVerificationLayer(reg)
        result = verifier.verify(signed)
        assert VerificationFailure.TRUST_FAILURE in result.halt_signal()

    def test_result_producer_id_matches_contract(self):
        verifier, signed, producer = self._setup()
        result = verifier.verify(signed)
        assert result.producer_id == producer.identity.node_id

    def test_result_producer_type_matches_contract(self):
        verifier, signed, _ = self._setup()
        result = verifier.verify(signed)
        assert result.producer_type == "QUANTUM"

    def test_reason_empty_on_success(self):
        verifier, signed, _ = self._setup()
        result = verifier.verify(signed)
        assert result.reason == ""

    def test_reason_non_empty_on_failure(self):
        from execution_contract import ComputationExecutionContract
        from producer_verification import ProducerRegistry, ProducerVerificationLayer
        reg = ProducerRegistry()
        verifier = ProducerVerificationLayer(reg)
        contract = ComputationExecutionContract(
            producer_type="QUANTUM", payload={"x": 1}, confidence=0.9,
            trace_id="reason-fail-001", contract_version="2.0.0",
        )
        result = verifier.verify(contract)
        assert result.reason != ""


# =============================================================================
# Proof runners — integration assertions
# =============================================================================

class TestDeterminismProofIntegration:

    def test_proof_returns_dict_with_required_keys(self):
        from determinism_20_run_proof import run_20_run_proof
        proof = run_20_run_proof(runs=3, verbose=False)
        for key in ("passed", "runs", "deterministic_hash", "all_hashes_identical",
                    "mismatched_fields", "evidence"):
            assert key in proof

    def test_proof_evidence_length_matches_runs(self):
        from determinism_20_run_proof import run_20_run_proof
        proof = run_20_run_proof(runs=5, verbose=False)
        assert len(proof["evidence"]) == 5

    def test_proof_deterministic_hash_is_64_chars(self):
        from determinism_20_run_proof import run_20_run_proof
        proof = run_20_run_proof(runs=3, verbose=False)
        assert len(proof["deterministic_hash"]) == 64

    def test_proof_runs_field_matches_requested(self):
        from determinism_20_run_proof import run_20_run_proof
        proof = run_20_run_proof(runs=7, verbose=False)
        assert proof["runs"] == 7


class TestReplayEnforcementProofIntegration:

    def test_proof_returns_passed_true(self):
        from replay_enforcement_proof import run_proof
        result = run_proof(verbose=False)
        assert result["passed"] is True

    def test_proof_has_cases_dict(self):
        from replay_enforcement_proof import run_proof
        result = run_proof(verbose=False)
        assert isinstance(result["cases"], dict)
        assert len(result["cases"]) >= 4

    def test_valid_first_submission_case(self):
        from replay_enforcement_proof import run_proof
        result = run_proof(verbose=False)
        assert result["cases"]["valid_first_submission"] is True

    def test_duplicate_rejected_case(self):
        from replay_enforcement_proof import run_proof
        result = run_proof(verbose=False)
        assert result["cases"]["duplicate_rejected"] is True

    def test_stale_rejected_case(self):
        from replay_enforcement_proof import run_proof
        result = run_proof(verbose=False)
        assert result["cases"]["stale_rejected"] is True

    def test_sequence_monotonic_case(self):
        from replay_enforcement_proof import run_proof
        result = run_proof(verbose=False)
        assert result["cases"]["sequence_monotonic"] is True

    def test_persistence_survives_restart_case(self):
        from replay_enforcement_proof import run_proof
        result = run_proof(verbose=False)
        assert result["cases"]["persistence_survives_restart"] is True


class TestCrashRecoveryProofIntegration:

    def test_proof_returns_passed_true(self):
        from crash_recovery_proof import run_proof
        result = run_proof(verbose=False)
        assert result["passed"] is True

    def test_proof_has_cases_dict(self):
        from crash_recovery_proof import run_proof
        result = run_proof(verbose=False)
        assert isinstance(result["cases"], dict)

    def test_sequence_continues_after_restart(self):
        """Sequence number after restart must be > sequence before crash."""
        from replay_registry import ReplayRegistry
        path = Path(tempfile.mktemp(suffix="_seq_cont.json"))
        try:
            reg1 = ReplayRegistry(path=path, ttl_seconds=300.0)
            d1 = reg1.submit("seq-cont-001")
            seq_before = d1.sequence_number

            reg2 = ReplayRegistry(path=path, ttl_seconds=300.0)
            d2 = reg2.submit("seq-cont-002")
            assert d2.sequence_number == seq_before + 1
        finally:
            if path.exists():
                path.unlink()

    def test_three_registries_fully_independent(self):
        from replay_registry import ReplayRegistry
        paths = [Path(tempfile.mktemp(suffix=f"_ind{i}.json")) for i in range(3)]
        try:
            regs = [ReplayRegistry(path=p, ttl_seconds=300.0) for p in paths]
            regs[0].submit("shared-msg-X")
            assert not regs[1].is_known("shared-msg-X")
            assert not regs[2].is_known("shared-msg-X")
            assert regs[1].sequence_count == 0
            assert regs[2].sequence_count == 0
        finally:
            for p in paths:
                if p.exists():
                    p.unlink()


class TestTrustValidationProofIntegration:

    def test_proof_returns_passed_true(self):
        from trust_validation_proof import run_proof
        result = run_proof(verbose=False)
        assert result["passed"] is True

    def test_proof_has_six_cases(self):
        from trust_validation_proof import run_proof
        result = run_proof(verbose=False)
        assert len(result["cases"]) == 6

    def test_all_six_cases_pass(self):
        from trust_validation_proof import run_proof
        result = run_proof(verbose=False)
        for case, passed in result["cases"].items():
            assert passed is True, f"Trust proof case failed: {case}"


# =============================================================================
# Concurrent replay — additional contention scenarios
# =============================================================================

class TestConcurrentReplayExtended:

    def test_high_contention_all_unique_ids_all_valid(self):
        """50 threads, all unique IDs → all VALID, sequences 1..50."""
        from replay_registry import ReplayRegistry
        path = Path(tempfile.mktemp(suffix="_hc.json"))
        try:
            reg = ReplayRegistry(path=path, ttl_seconds=300.0)
            results = []
            lock = threading.Lock()

            def submit(i):
                d = reg.submit(f"hc-{i:04d}")
                with lock:
                    results.append(d)

            threads = [threading.Thread(target=submit, args=(i,)) for i in range(50)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            assert all(r.status == "VALID" for r in results)
            seqs = sorted(r.sequence_number for r in results)
            assert seqs == list(range(1, 51))
        finally:
            if path.exists():
                path.unlink()

    def test_enforcer_high_contention_unique_ids(self):
        """30 threads, all unique artifact IDs → all ACCEPTED."""
        from replay_enforcer import ReplayEnforcer
        enforcer = ReplayEnforcer(ttl_seconds=60.0)
        results = []
        lock = threading.Lock()

        def submit(i):
            d = enforcer.submit(f"hc-art-{i:04d}")
            with lock:
                results.append(d.status)

        threads = [threading.Thread(target=submit, args=(i,)) for i in range(30)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert all(s == "ACCEPTED" for s in results)
        assert enforcer.sequence_count == 30

    def test_registry_concurrent_mixed_duplicate_and_unique(self):
        """10 unique + 10 duplicate submissions concurrently → 10 VALID, 10 DUPLICATE."""
        from replay_registry import ReplayRegistry
        path = Path(tempfile.mktemp(suffix="_mixed.json"))
        try:
            reg = ReplayRegistry(path=path, ttl_seconds=300.0)
            results = []
            lock = threading.Lock()

            def submit_unique(i):
                d = reg.submit(f"mixed-unique-{i}")
                with lock:
                    results.append(d.status)

            def submit_dup():
                d = reg.submit("mixed-dup-shared")
                with lock:
                    results.append(d.status)

            threads = (
                [threading.Thread(target=submit_unique, args=(i,)) for i in range(10)] +
                [threading.Thread(target=submit_dup) for _ in range(10)]
            )
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            valid_count = results.count("VALID")
            dup_count = results.count("DUPLICATE")
            # 10 unique → 10 VALID; 10 dup submissions → 1 VALID + 9 DUPLICATE
            assert valid_count == 11
            assert dup_count == 9
        finally:
            if path.exists():
                path.unlink()
