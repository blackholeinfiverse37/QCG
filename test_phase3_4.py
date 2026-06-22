import unittest
import hashlib
from execution_record import ExecutionRecord
from quantum_execution_context import QuantumExecutionContext, QuantumProvider
from evidence_ledger import EvidenceLedger


class TestPhase3And4(unittest.TestCase):

    def test_quantum_execution_context(self):
        ctx = QuantumExecutionContext(
            provider=QuantumProvider.IBM_QUANTUM,
            solver_name="ibmq_qasm_simulator",
            shots=1024,
            noise_model="fake_vigo",
            optimization_level=3,
            backend_properties={"qubits": 5},
            seed_simulator=42
        )
        
        ctx_dict = ctx.to_dict()
        self.assertEqual(ctx_dict["provider"], "IBM_QUANTUM")
        self.assertEqual(ctx_dict["shots"], 1024)
        
        ctx_hash = ctx.compute_hash()
        self.assertTrue(isinstance(ctx_hash, str))
        self.assertEqual(len(ctx_hash), 64)

    def test_evidence_ledger(self):
        ledger = EvidenceLedger()
        
        # Genesis hash
        genesis_hash = hashlib.sha256(b"GENESIS").hexdigest()
        
        record1 = ExecutionRecord(
            execution_id="exec-1",
            trace_id="tr-1",
            replay_reference="ref-1",
            execution_sequence=1,
            producer_identity="producer-1",
            runtime_identity="runtime-1",
            governance_identity="gov-1",
            execution_status="SUCCESS",
            runtime_hash="hash-rt-1",
            execution_hash="hash-ex-1",
            previous_execution_hash=genesis_hash,
            execution_root_hash="root-1",
            schema_version="1.0"
        )
        
        snap1 = ledger.append(record1)
        self.assertEqual(snap1.sequence_length, 1)
        
        record2 = ExecutionRecord(
            execution_id="exec-2",
            trace_id="tr-2",
            replay_reference="ref-2",
            execution_sequence=2,
            producer_identity="producer-1",
            runtime_identity="runtime-1",
            governance_identity="gov-1",
            execution_status="SUCCESS",
            runtime_hash="hash-rt-2",
            execution_hash="hash-ex-2",
            previous_execution_hash=snap1.latest_evidence_hash,
            execution_root_hash="root-2",
            schema_version="1.0"
        )
        
        snap2 = ledger.append(record2)
        self.assertEqual(snap2.sequence_length, 2)
        
        self.assertTrue(ledger.verify_chain())
        
        # Test Merkle Root
        merkle_root = ledger.get_merkle_root()
        self.assertTrue(isinstance(merkle_root, str))
        self.assertEqual(len(merkle_root), 64)


if __name__ == "__main__":
    unittest.main()
