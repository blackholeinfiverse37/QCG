"""
tests/test_adapter_layer.py
Comprehensive test suite for the Hybrid Quantum Runtime Adapter Layer.
Covers all 6 phases: contract, adapters, runtime, governance, observability, distributed.
"""

import pytest
import json
import hashlib

from models import TransmissionRequest, QuantumDistribution
from quantum_producer import run_quantum_producer
from translation_layer import translate

from execution_contract import (
    ComputationExecutionContract,
    ProducerType,
    ContractValidationError,
    validate_contract,
    _canonical_hash,
)
from adapters import (
    QuantumAdapter,
    ClassicalAdapter,
    HybridAdapter,
    AdapterTrace,
)
from runtime_core import RuntimeCore, ExecutionResult
from governance import GovernanceLayer, GovernanceViolation
from observability import TraceStore, TraceEntry, ReplayProof
from distributed_simulation import DistributedSimulation, SimulatedNode

import config

SEED = 42


# ═══════════════════════════════════════════════════════════════════════════
# Phase 1: Generic Computation Contract
# ═══════════════════════════════════════════════════════════════════════════

class TestComputationExecutionContract:

    def test_create_valid_contract(self):
        c = ComputationExecutionContract(
            producer_type=ProducerType.QUANTUM.value,
            payload={"msg": "NODE_READY"},
            confidence=0.95,
            trace_id="test-trace-001",
            contract_version="2.0.0",
        )
        assert c.producer_type == "QUANTUM"
        assert c.confidence == 0.95
        assert c.payload_hash != ""

    def test_payload_hash_computed_automatically(self):
        c = ComputationExecutionContract(
            producer_type="CLASSICAL",
            payload={"x": 42},
            confidence=0.8,
            trace_id="t-001",
            contract_version="2.0.0",
        )
        expected = _canonical_hash({"x": 42})
        assert c.payload_hash == expected

    def test_payload_hash_deterministic(self):
        p = {"a": 1, "b": 2}
        c1 = ComputationExecutionContract(
            producer_type="CLASSICAL", payload=p, confidence=0.9,
            trace_id="t", contract_version="2.0.0",
        )
        c2 = ComputationExecutionContract(
            producer_type="CLASSICAL", payload=p, confidence=0.9,
            trace_id="t", contract_version="2.0.0",
        )
        assert c1.payload_hash == c2.payload_hash

    def test_contract_is_frozen(self):
        c = ComputationExecutionContract(
            producer_type="QUANTUM", payload={"x": 1}, confidence=0.9,
            trace_id="t", contract_version="2.0.0",
        )
        with pytest.raises(AttributeError):
            c.confidence = 0.5

    def test_to_dict(self):
        c = ComputationExecutionContract(
            producer_type="QUANTUM", payload={"x": 1}, confidence=0.9,
            trace_id="t", contract_version="2.0.0",
        )
        d = c.to_dict()
        assert "producer_type" in d
        assert "payload_hash" in d
        assert "timestamp" in d

    def test_timestamp_auto_generated(self):
        c = ComputationExecutionContract(
            producer_type="QUANTUM", payload={"x": 1}, confidence=0.9,
            trace_id="t", contract_version="2.0.0",
        )
        assert c.timestamp != ""


class TestContractValidation:

    def _valid(self, **overrides):
        defaults = dict(
            producer_type="QUANTUM",
            payload={"msg": "OK"},
            confidence=0.9,
            trace_id="valid-001",
            contract_version="2.0.0",
        )
        defaults.update(overrides)
        return ComputationExecutionContract(**defaults)

    def test_valid_contract_passes(self):
        validate_contract(self._valid())  # no raise

    def test_unauthorized_producer_raises(self):
        c = self._valid(producer_type="ALIEN")
        with pytest.raises(ContractValidationError, match="Unauthorized"):
            validate_contract(c)

    def test_empty_payload_raises(self):
        c = self._valid(payload={})
        with pytest.raises(ContractValidationError, match="payload"):
            validate_contract(c)

    def test_confidence_below_zero_raises(self):
        c = self._valid(confidence=-0.1)
        with pytest.raises(ContractValidationError, match="confidence"):
            validate_contract(c)

    def test_confidence_above_one_raises(self):
        c = self._valid(confidence=1.1)
        with pytest.raises(ContractValidationError, match="confidence"):
            validate_contract(c)

    def test_empty_trace_id_raises(self):
        c = self._valid(trace_id="")
        with pytest.raises(ContractValidationError, match="trace_id"):
            validate_contract(c)

    def test_version_downgrade_raises(self):
        c = self._valid(contract_version="1.0.0")
        with pytest.raises(ContractValidationError, match="downgrade"):
            validate_contract(c)

    def test_bad_version_format_raises(self):
        c = self._valid(contract_version="not.a.version")
        with pytest.raises(ContractValidationError, match="Invalid semantic version"):
            validate_contract(c)

    def test_payload_hash_tamper_raises(self):
        c = ComputationExecutionContract(
            producer_type="QUANTUM", payload={"msg": "OK"}, confidence=0.9,
            trace_id="tamper-001", contract_version="2.0.0",
            payload_hash="0000000000000000000000000000000000000000000000000000000000000000",
        )
        with pytest.raises(ContractValidationError, match="payload_hash mismatch"):
            validate_contract(c)

    def test_custom_allowed_producers(self):
        c = self._valid(producer_type="QUANTUM")
        # Only allow CLASSICAL
        with pytest.raises(ContractValidationError, match="Unauthorized"):
            validate_contract(c, allowed_producers={"CLASSICAL"})


class TestProducerType:

    def test_enum_values(self):
        assert ProducerType.CLASSICAL.value == "CLASSICAL"
        assert ProducerType.QUANTUM.value == "QUANTUM"
        assert ProducerType.HYBRID.value == "HYBRID"

    def test_enum_membership(self):
        assert "QUANTUM" in [e.value for e in ProducerType]


# ═══════════════════════════════════════════════════════════════════════════
# Phase 2: Adapter Layer
# ═══════════════════════════════════════════════════════════════════════════

class TestQuantumAdapter:

    def _distribution(self):
        req = TransmissionRequest("NODE_READY", 0.05, "entangled")
        return run_quantum_producer(req, seed=SEED)

    def test_produces_valid_contract(self):
        dist = self._distribution()
        contract, trace = QuantumAdapter().adapt(dist, "NODE_READY")
        assert contract.producer_type == "QUANTUM"
        validate_contract(contract)

    def test_confidence_matches_translation(self):
        dist = self._distribution()
        classical = translate(dist, "NODE_READY")
        contract, _ = QuantumAdapter().adapt(dist, "NODE_READY")
        assert contract.confidence == classical.confidence

    def test_produces_adapter_trace(self):
        dist = self._distribution()
        _, trace = QuantumAdapter().adapt(dist, "NODE_READY")
        assert isinstance(trace, AdapterTrace)
        assert trace.adapter_type == "QuantumAdapter"
        assert trace.producer_type == "QUANTUM"

    def test_trace_id_deterministic(self):
        dist = self._distribution()
        c1, _ = QuantumAdapter().adapt(dist, "NODE_READY")
        c2, _ = QuantumAdapter().adapt(dist, "NODE_READY")
        assert c1.trace_id == c2.trace_id

    def test_execution_constraints_contain_quantum_fields(self):
        dist = self._distribution()
        contract, _ = QuantumAdapter().adapt(dist, "NODE_READY")
        ec = contract.execution_constraints
        assert "shots" in ec
        assert "noise_factor" in ec
        assert "seed" in ec
        assert "encoded_bits" in ec


class TestClassicalAdapter:

    def _output(self):
        return {
            "result": "OPTIMISED_ROUTE_A",
            "confidence": 0.92,
            "metadata": {"algorithm": "gradient_descent"},
        }

    def test_produces_valid_contract(self):
        contract, _ = ClassicalAdapter().adapt(self._output())
        assert contract.producer_type == "CLASSICAL"
        validate_contract(contract)

    def test_confidence_passthrough(self):
        out = self._output()
        contract, _ = ClassicalAdapter().adapt(out)
        assert contract.confidence == 0.92

    def test_produces_adapter_trace(self):
        _, trace = ClassicalAdapter().adapt(self._output())
        assert trace.adapter_type == "ClassicalAdapter"

    def test_missing_result_raises(self):
        with pytest.raises(ValueError, match="result"):
            ClassicalAdapter().adapt({"confidence": 0.5})

    def test_missing_confidence_raises(self):
        with pytest.raises(ValueError, match="confidence"):
            ClassicalAdapter().adapt({"result": "x"})

    def test_bad_confidence_raises(self):
        with pytest.raises(ValueError, match="confidence"):
            ClassicalAdapter().adapt({"result": "x", "confidence": 1.5})

    def test_trace_id_deterministic(self):
        out = self._output()
        c1, _ = ClassicalAdapter().adapt(out)
        c2, _ = ClassicalAdapter().adapt(out)
        assert c1.trace_id == c2.trace_id


class TestHybridAdapter:

    def _contracts(self):
        req = TransmissionRequest("NODE_READY", 0.05, "entangled")
        dist = run_quantum_producer(req, seed=SEED)
        q, _ = QuantumAdapter().adapt(dist, "NODE_READY")
        c, _ = ClassicalAdapter().adapt({
            "result": "ROUTE_A", "confidence": 0.85,
        })
        return q, c

    def test_produces_hybrid_contract(self):
        q, c = self._contracts()
        h, _ = HybridAdapter().adapt(q, c)
        assert h.producer_type == "HYBRID"
        validate_contract(h)

    def test_selects_higher_confidence(self):
        q, c = self._contracts()
        h, _ = HybridAdapter().adapt(q, c)
        assert h.confidence == max(q.confidence, c.confidence)

    def test_produces_adapter_trace(self):
        q, c = self._contracts()
        _, trace = HybridAdapter().adapt(q, c)
        assert trace.adapter_type == "HybridAdapter"

    def test_payload_contains_both_sources(self):
        q, c = self._contracts()
        h, _ = HybridAdapter().adapt(q, c)
        assert "primary_payload" in h.payload
        assert "secondary_payload" in h.payload


# ═══════════════════════════════════════════════════════════════════════════
# Phase 3: Runtime Participation Proof
# ═══════════════════════════════════════════════════════════════════════════

class TestRuntimeCore:

    def _valid_contract(self, trace_id="rt-001"):
        return ComputationExecutionContract(
            producer_type="QUANTUM",
            payload={"msg": "NODE_READY"},
            confidence=0.95,
            trace_id=trace_id,
            contract_version="2.0.0",
        )

    def test_execute_returns_execution_result(self):
        core = RuntimeCore()
        result = core.execute(self._valid_contract())
        assert isinstance(result, ExecutionResult)

    def test_valid_contract_produces_ack_ok(self):
        core = RuntimeCore()
        result = core.execute(self._valid_contract())
        assert result.ack == "ACK:OK"

    def test_low_confidence_produces_degraded(self):
        core = RuntimeCore()
        c = ComputationExecutionContract(
            producer_type="QUANTUM", payload={"x": 1}, confidence=0.55,
            trace_id="deg-001", contract_version="2.0.0",
        )
        result = core.execute(c)
        assert "DEGRADED" in result.ack

    def test_very_low_confidence_produces_halt(self):
        core = RuntimeCore()
        c = ComputationExecutionContract(
            producer_type="QUANTUM", payload={"x": 1}, confidence=0.15,
            trace_id="low-001", contract_version="2.0.0",
        )
        result = core.execute(c)
        assert result.ack.startswith("HALT:LOW_CONFIDENCE")


    def test_producer_type_passthrough(self):
        core = RuntimeCore()
        q = self._valid_contract("q-001")
        result = core.execute(q)
        assert result.producer_type == "QUANTUM"

    def test_runtime_hash_present(self):
        core = RuntimeCore()
        result = core.execute(self._valid_contract())
        assert result.runtime_hash != ""
        assert len(result.runtime_hash) == 64  # SHA-256 hex

    def test_never_raises(self):
        core = RuntimeCore()
        # Even invalid contracts produce results, not exceptions
        bad = ComputationExecutionContract(
            producer_type="ALIEN", payload={"x": 1}, confidence=0.9,
            trace_id="bad-001", contract_version="2.0.0",
        )
        result = core.execute(bad)
        assert isinstance(result, ExecutionResult)


class TestParticipationProof:

    def test_same_interface_different_origin(self):
        """Core proof: quantum and classical both produce ExecutionResult
        through the same execute() method."""
        core = RuntimeCore()

        # Quantum
        req = TransmissionRequest("NODE_READY", 0.05, "entangled")
        dist = run_quantum_producer(req, seed=SEED)
        q_contract, _ = QuantumAdapter().adapt(dist, "NODE_READY")

        # Classical
        c_contract, _ = ClassicalAdapter().adapt({
            "result": "ROUTE_A", "confidence": 0.92,
        })

        q_result = core.execute(q_contract)
        c_result = core.execute(c_contract)

        # Same interface
        assert type(q_result) == type(c_result) == ExecutionResult
        assert set(q_result.to_dict().keys()) == set(c_result.to_dict().keys())

        # Different origin
        assert q_result.producer_type == "QUANTUM"
        assert c_result.producer_type == "CLASSICAL"

        # Both valid
        assert q_result.ack.startswith("ACK:")
        assert c_result.ack.startswith("ACK:")


# ═══════════════════════════════════════════════════════════════════════════
# Phase 4: Governance Boundaries
# ═══════════════════════════════════════════════════════════════════════════

class TestGovernanceLayer:

    def _valid(self, trace_id="gov-001"):
        return ComputationExecutionContract(
            producer_type="QUANTUM", payload={"msg": "OK"}, confidence=0.95,
            trace_id=trace_id, contract_version="2.0.0",
        )

    def test_valid_contract_passes(self):
        gov = GovernanceLayer()
        result, violations = gov.enforce(self._valid())
        assert result.ack == "ACK:OK"
        assert len(violations) == 0

    def test_unauthorized_producer_halts(self):
        gov = GovernanceLayer(strict=True)
        c = ComputationExecutionContract(
            producer_type="ALIEN", payload={"x": 1}, confidence=0.9,
            trace_id="unauth-001", contract_version="2.0.0",
        )
        result, violations = gov.enforce(c)
        assert "UNAUTHORIZED_PRODUCER" in result.ack
        assert any(v.violation_type == "UNAUTHORIZED_PRODUCER" for v in violations)

    def test_contract_downgrade_halts(self):
        gov = GovernanceLayer(strict=True)
        c = ComputationExecutionContract(
            producer_type="QUANTUM", payload={"x": 1}, confidence=0.9,
            trace_id="down-001", contract_version="1.0.0",
        )
        result, violations = gov.enforce(c)
        assert "CONTRACT_DOWNGRADE" in result.ack

    def test_invalid_contract_halts(self):
        gov = GovernanceLayer(strict=True)
        c = ComputationExecutionContract(
            producer_type="QUANTUM", payload={}, confidence=0.9,
            trace_id="inv-001", contract_version="2.0.0",
        )
        result, violations = gov.enforce(c)
        assert "INVALID_CONTRACT" in result.ack

    def test_low_confidence_produces_violation(self):
        gov = GovernanceLayer(strict=True)
        c = ComputationExecutionContract(
            producer_type="QUANTUM", payload={"x": 1}, confidence=0.15,
            trace_id="low-001", contract_version="2.0.0",
        )
        result, violations = gov.enforce(c)
        assert any(v.violation_type == "LOW_CONFIDENCE" for v in violations)


    def test_violations_accumulate(self):
        gov = GovernanceLayer(strict=True)
        bad1 = ComputationExecutionContract(
            producer_type="ALIEN", payload={"x": 1}, confidence=0.9,
            trace_id="b1", contract_version="2.0.0",
        )
        bad2 = ComputationExecutionContract(
            producer_type="ALIEN", payload={"x": 1}, confidence=0.9,
            trace_id="b2", contract_version="2.0.0",
        )
        gov.enforce(bad1)
        gov.enforce(bad2)
        assert len(gov.get_violations()) >= 2
    def test_permissive_mode_allows_execution(self):
        gov = GovernanceLayer(strict=False, allowed_producers={"QUANTUM", "CLASSICAL", "HYBRID", "ALIEN"})
        c = ComputationExecutionContract(
            producer_type="ALIEN", payload={"x": 1}, confidence=0.9,
            trace_id="perm-001", contract_version="2.0.0",
        )
        result, violations = gov.enforce(c)
        # In permissive mode with ALIEN in allowed set, it should pass validation
        # but the contract validation will still fail on unauthorized if not in allowed
        assert isinstance(result, ExecutionResult)

    def test_governance_never_crashes(self):
        gov = GovernanceLayer(strict=True)
        # Throw everything bad at it
        scenarios = [
            ComputationExecutionContract(
                producer_type="ALIEN", payload={"x": 1}, confidence=0.9,
                trace_id="crash-1", contract_version="2.0.0",
            ),
            ComputationExecutionContract(
                producer_type="QUANTUM", payload={}, confidence=0.9,
                trace_id="crash-2", contract_version="2.0.0",
            ),
            ComputationExecutionContract(
                producer_type="QUANTUM", payload={"x": 1}, confidence=-1.0,
                trace_id="crash-3", contract_version="2.0.0",
            ),
        ]
        for c in scenarios:
            result, _ = gov.enforce(c)
            assert isinstance(result, ExecutionResult)
            assert result.ack.startswith("HALT:")


# ═══════════════════════════════════════════════════════════════════════════
# Phase 5: Observability + Replay
# ═══════════════════════════════════════════════════════════════════════════

class TestTraceStore:

    def test_record_and_query(self):
        store = TraceStore()
        entry = TraceEntry(
            trace_id="obs-001", trace_type="execution",
            data={"ack": "ACK:OK"},
        )
        store.record(entry)
        results = store.query(trace_id="obs-001")
        assert len(results) == 1
        assert results[0].trace_type == "execution"

    def test_query_by_type(self):
        store = TraceStore()
        store.record(TraceEntry(trace_id="t1", trace_type="execution", data={"a": 1}))
        store.record(TraceEntry(trace_id="t2", trace_type="adapter", data={"b": 2}))
        store.record(TraceEntry(trace_id="t3", trace_type="execution", data={"c": 3}))

        execs = store.query(trace_type="execution")
        assert len(execs) == 2

    def test_record_execution_trace(self):
        store = TraceStore()
        entry = store.record_execution_trace(
            trace_id="ex-001", contract_hash="abc", ack="ACK:OK",
            runtime_hash="def", confidence=0.95,
        )
        assert entry.trace_type == "execution"
        assert entry.data["ack"] == "ACK:OK"

    def test_record_adapter_trace(self):
        store = TraceStore()
        entry = store.record_adapter_trace(
            trace_id="ad-001", adapter_type="QuantumAdapter",
            producer_type="QUANTUM", input_hash="in", output_hash="out",
        )
        assert entry.trace_type == "adapter"

    def test_record_producer_lineage(self):
        store = TraceStore()
        entry = store.record_producer_lineage(
            trace_id="pl-001", producer_type="QUANTUM",
            raw_input_hash="raw", adapter_output_hash="adapted",
            contract_hash="contract",
        )
        assert entry.trace_type == "producer_lineage"

    def test_record_contract_lineage(self):
        store = TraceStore()
        entry = store.record_contract_lineage(
            trace_id="cl-001", contract_version="2.0.0",
            producer_type="QUANTUM",
            governance_decisions=[], final_ack="ACK:OK",
        )
        assert entry.trace_type == "contract_lineage"

    def test_entry_hash_integrity(self):
        entry = TraceEntry(
            trace_id="hash-001", trace_type="execution",
            data={"x": 1},
        )
        # Recompute expected hash
        raw = json.dumps({
            "trace_id": entry.trace_id,
            "trace_type": entry.trace_type,
            "data": entry.data,
            "timestamp": entry.timestamp,
        }, sort_keys=True, default=str)
        expected = hashlib.sha256(raw.encode()).hexdigest()
        assert entry.entry_hash == expected

    def test_clear(self):
        store = TraceStore()
        store.record(TraceEntry(trace_id="c", trace_type="x", data={}))
        store.clear()
        assert len(store.all_entries()) == 0


class TestReplayReconstruction:

    def _store_with_traces(self):
        store = TraceStore()
        tid = "replay-test-001"
        store.record_producer_lineage(
            trace_id=tid, producer_type="QUANTUM",
            raw_input_hash="raw", adapter_output_hash="adapted",
            contract_hash="contract",
        )
        store.record_adapter_trace(
            trace_id=tid, adapter_type="QuantumAdapter",
            producer_type="QUANTUM", input_hash="in", output_hash="out",
        )
        store.record_execution_trace(
            trace_id=tid, contract_hash="contract",
            ack="ACK:OK", runtime_hash="rthash", confidence=0.95,
        )
        store.record_contract_lineage(
            trace_id=tid, contract_version="2.0.0",
            producer_type="QUANTUM",
            governance_decisions=[], final_ack="ACK:OK",
        )
        return store, tid

    def test_replay_proof_valid(self):
        store, tid = self._store_with_traces()
        proof = store.reconstruct_replay(tid)
        assert proof.is_valid is True
        assert len(proof.chain) == 4
        assert proof.mismatches == []

    def test_replay_proof_no_entries(self):
        store = TraceStore()
        proof = store.reconstruct_replay("nonexistent")
        assert proof.is_valid is False
        assert "No trace entries" in proof.mismatches[0]

    def test_replay_chain_ordered(self):
        store, tid = self._store_with_traces()
        proof = store.reconstruct_replay(tid)
        types = [e["trace_type"] for e in proof.chain]
        assert types[0] == "producer_lineage"
        assert types[-1] == "contract_lineage"


# ═══════════════════════════════════════════════════════════════════════════
# Phase 6: Distributed Readiness
# ═══════════════════════════════════════════════════════════════════════════

class TestDistributedSimulation:

    def test_simulation_passes(self):
        sim = DistributedSimulation(node_count=3, seed=SEED)
        proof = sim.run()
        assert proof.passed is True

    def test_hash_agreement(self):
        sim = DistributedSimulation(node_count=3, seed=SEED)
        proof = sim.run()
        assert proof.hash_agreement is True

    def test_correct_counts(self):
        sim = DistributedSimulation(node_count=3, seed=SEED)
        proof = sim.run()
        assert proof.node_count == 3
        assert proof.producer_count == 2
        # Each of 2 contracts goes through 3 nodes = 6 total
        assert proof.contracts_processed == 6

    def test_all_nodes_have_same_ledger(self):
        sim = DistributedSimulation(node_count=3, seed=SEED)
        proof = sim.run()
        ledgers = list(proof.node_ledgers.values())
        assert all(l == ledgers[0] for l in ledgers)

    def test_two_node_simulation(self):
        sim = DistributedSimulation(node_count=2, seed=SEED)
        proof = sim.run()
        assert proof.passed is True
        assert proof.node_count == 2


class TestSimulatedNode:

    def test_node_processes_contract(self):
        node = SimulatedNode(node_id="test_node")
        c = ComputationExecutionContract(
            producer_type="QUANTUM", payload={"x": 1}, confidence=0.95,
            trace_id="node-test-001", contract_version="2.0.0",
        )
        result = node.process(c)
        assert isinstance(result, ExecutionResult)
        assert len(node.ledger) == 1

    def test_node_builds_hash_chain(self):
        node = SimulatedNode(node_id="chain_node")
        for i in range(3):
            c = ComputationExecutionContract(
                producer_type="CLASSICAL", payload={"i": i}, confidence=0.9,
                trace_id=f"chain-{i}", contract_version="2.0.0",
            )
            node.process(c)
        assert len(node.ledger) == 3
        # All hashes are unique
        assert len(set(node.ledger)) == 3

    def test_node_records_traces(self):
        node = SimulatedNode(node_id="trace_node")
        c = ComputationExecutionContract(
            producer_type="QUANTUM", payload={"x": 1}, confidence=0.95,
            trace_id="trace-test-001", contract_version="2.0.0",
        )
        node.process(c)
        entries = node.traces.all_entries()
        assert len(entries) >= 1
        assert any(e.trace_type == "execution" for e in entries)


# ═══════════════════════════════════════════════════════════════════════════
# Cross-phase integration
# ═══════════════════════════════════════════════════════════════════════════

class TestCrossPhaseIntegration:

    def test_full_quantum_pipeline(self):
        """Quantum: produce → adapt → validate → execute → trace → reconstruct."""
        # Produce
        req = TransmissionRequest("NODE_READY", 0.05, "entangled")
        dist = run_quantum_producer(req, seed=SEED)

        # Adapt
        contract, adapter_trace = QuantumAdapter().adapt(dist, "NODE_READY")
        validate_contract(contract)

        # Execute
        core = RuntimeCore()
        result = core.execute(contract)
        assert result.ack.startswith("ACK:")

        # Trace
        store = TraceStore()
        store.record_adapter_trace(
            trace_id=contract.trace_id,
            adapter_type=adapter_trace.adapter_type,
            producer_type=adapter_trace.producer_type,
            input_hash=adapter_trace.input_hash,
            output_hash=adapter_trace.output_hash,
        )
        store.record_execution_trace(
            trace_id=contract.trace_id,
            contract_hash=contract.payload_hash,
            ack=result.ack,
            runtime_hash=result.runtime_hash,
            confidence=result.confidence,
        )

        # Reconstruct
        proof = store.reconstruct_replay(contract.trace_id)
        assert proof.is_valid is True

    def test_full_classical_pipeline(self):
        """Classical: produce → adapt → validate → execute → trace."""
        output = {"result": "PATH_A", "confidence": 0.88}
        contract, _ = ClassicalAdapter().adapt(output)
        validate_contract(contract)

        core = RuntimeCore()
        result = core.execute(contract)
        assert result.ack.startswith("ACK:")
        assert result.producer_type == "CLASSICAL"

    def test_governance_wraps_runtime_correctly(self):
        """Governance → RuntimeCore integration."""
        req = TransmissionRequest("NODE_READY", 0.05, "entangled")
        dist = run_quantum_producer(req, seed=SEED)
        contract, _ = QuantumAdapter().adapt(dist, "NODE_READY")

        gov = GovernanceLayer()
        result, violations = gov.enforce(contract)
        assert result.ack.startswith("ACK:")
        assert len(violations) == 0
