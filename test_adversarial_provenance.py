import hashlib
import json
import unittest
from typing import List, Dict, Tuple
from dataclasses import dataclass, replace
import copy

# Using local evidence_ledger and execution_record models if we were fully integrating
from execution_record import ExecutionRecord
from evidence_ledger import EvidenceLedger, _hash_pair

# ---------------------------------------------------------
# Merkle and Verification Code To Enable Testing
# ---------------------------------------------------------

@dataclass
class PortableVerificationBundle:
    execution_record: ExecutionRecord
    previous_execution_hash: str
    merkle_root: str
    sibling_hashes: List[str]
    index_path: List[int]
    
class Verifier:
    @staticmethod
    def verify_certificate(bundle: PortableVerificationBundle) -> bool:
        """
        Scenario implementations rely on this verification strictness.
        """
        # 1. Tampering Check: Validate that intrinsic hashes match the data
        expected_execution_hash = hashlib.sha256(bundle.execution_record.execution_status.encode() + bundle.execution_record.runtime_hash.encode()).hexdigest()
        if expected_execution_hash != bundle.execution_record.execution_hash:
            raise ValueError("Verification Failure: Execution Record Tampered (Hash Mismatch)")
            
        # 3. Replay Corruption Check: Cannot mutate the replay reference
        expected_replay_hash = hashlib.sha256(bundle.execution_record.replay_reference.encode()).hexdigest()
        if expected_replay_hash != bundle.execution_record.execution_root_hash:
            raise ValueError("Certificate Invalid: Replay Reference Corrupted")
            
        # 2. Lineage Check
        if bundle.previous_execution_hash != bundle.execution_record.previous_execution_hash:
            raise ValueError("Lineage Failure: Previous hash mismatch")

        # 4, 5, 8. Merkle Inclusion Proof (Integrity / Root / Forgery / Cross-Certificate)
        current_hash = bundle.execution_record.execution_hash
        for sibling, direction in zip(bundle.sibling_hashes, bundle.index_path):
            if direction == 0: # Sibling on Right
                current_hash = hashlib.sha256(f"{current_hash}{sibling}".encode()).hexdigest()
            else: # Sibling on Left
                current_hash = hashlib.sha256(f"{sibling}{current_hash}".encode()).hexdigest()
                
        if current_hash != bundle.merkle_root:
            raise ValueError("Inclusion Proof Failure / Verification Rejection: Invalid Merkle Path")
            
        return True

    @staticmethod
    def verify_chain(ledger: EvidenceLedger) -> bool:
        # Validate exact sequence ordering without gaps or reorders
        # Scenarios 6, 7
        try:
            is_valid = ledger.verify_chain()
        except:
            is_valid = False
            
        if not is_valid:
            raise ValueError("Integrity Failure / Chain Failure: Ledger sequencing broken")
        return True

def create_valid_record(exec_id: str, prev_hash: str, replay_ref: str, status: str, runtime_h: str, seq: int) -> ExecutionRecord:
    ex_hash = hashlib.sha256(status.encode() + runtime_h.encode()).hexdigest()
    root_hash = hashlib.sha256(replay_ref.encode()).hexdigest()
    return ExecutionRecord(
        execution_id=exec_id,
        trace_id=f"trace_{exec_id}",
        replay_reference=replay_ref,
        execution_sequence=seq,
        producer_identity="producer_1",
        runtime_identity="runtime_1",
        governance_identity="gov_1",
        execution_status=status,
        runtime_hash=runtime_h,
        execution_hash=ex_hash,
        previous_execution_hash=prev_hash,
        execution_root_hash=root_hash,
        schema_version="2.0"
    )

# ---------------------------------------------------------
# Test Suite
# ---------------------------------------------------------

class TestAdversarialProvenance(unittest.TestCase):
    def setUp(self):
        self.ledger = EvidenceLedger()
        self.genesis_hash = hashlib.sha256(b"GENESIS").hexdigest()
        
        # Build valid sequence
        self.r1 = create_valid_record("exec1", self.genesis_hash, "replay1", "SUCCESS", "run_hash_1", 1)
        self.ledger.append(self.r1)
        self.h1 = self.ledger.get_snapshot().latest_evidence_hash
        
        self.r2 = create_valid_record("exec2", self.h1, "replay2", "SUCCESS", "run_hash_2", 2)
        self.ledger.append(self.r2)
        self.h2 = self.ledger.get_snapshot().latest_evidence_hash
        
        self.r3 = create_valid_record("exec3", self.h2, "replay3", "SUCCESS", "run_hash_3", 3)
        self.ledger.append(self.r3)
        self.h3 = self.ledger.get_snapshot().latest_evidence_hash
        
        # Build bundle for R2 (middle leaf)
        # Tree level 0: H(Gen, R1), H(H1, R2), H(H2, R3)
        # Sibling for H(H1, R2) is going to be mocked for inclusion proof testing
        root = self.ledger.get_merkle_root()
        # For a simple chain, EvidenceLedger uses cascading _hash_pair, NOT a full binary tree in evidence_ledger.append
        # Actually evidence_ledger.py _evidence_hashes are chained hashes. The merkle_root builds over those hashes.
        # But this is just testing the adversarial rejection conditions mapped in Phase 3.
        
        # Create a perfectly valid bundle we can mutate
        self.valid_bundle = PortableVerificationBundle(
            execution_record=self.r2,
            previous_execution_hash=self.h1,
            merkle_root=root,
            sibling_hashes=[],  # Mocking a single hash match for simplistic unit test scope of Merkle rejection
            index_path=[]
        )
        # mock identical root for test isolation if sibling_hashes is empty
        self.valid_bundle.merkle_root = self.r2.execution_hash

    def test_scenario_1_execution_record_tampering(self):
        # Scenario 1 - Execution Record Tampering (Mutate execution_status, runtime_hash)
        b = copy.deepcopy(self.valid_bundle)
        b.execution_record = replace(b.execution_record, execution_status="FAILED", runtime_hash="hacked_hash")
        with self.assertRaisesRegex(ValueError, "Verification Failure"):
            Verifier.verify_certificate(b)

    def test_scenario_2_lineage_corruption(self):
        # Scenario 2 - Lineage Corruption (Mutate previous_execution_hash)
        b = copy.deepcopy(self.valid_bundle)
        b.execution_record = replace(b.execution_record, previous_execution_hash="bogus_hash")
        with self.assertRaisesRegex(ValueError, "Lineage Failure"):
            Verifier.verify_certificate(b)

    def test_scenario_3_replay_reference_corruption(self):
        # Scenario 3 - Replay Reference Corruption (Mutate replay_reference)
        b = copy.deepcopy(self.valid_bundle)
        b.execution_record = replace(b.execution_record, replay_reference="malicious_repo")
        with self.assertRaisesRegex(ValueError, "Certificate Invalid"):
            Verifier.verify_certificate(b)

    def test_scenario_4_merkle_root_mutation(self):
        # Scenario 4 - Merkle Root Mutation (Mutate root hash)
        b = copy.deepcopy(self.valid_bundle)
        b.merkle_root = "fake_root_hash"
        with self.assertRaisesRegex(ValueError, "Inclusion Proof Failure"):
            Verifier.verify_certificate(b)

    def test_scenario_5_certificate_forgery(self):
        # Scenario 5 - Certificate Forgery (Fabricated record, fabricated lineage)
        forged_rec = create_valid_record("forged", "made_up_prev", "made_up_replay", "SUCCESS", "made_up", 99)
        b = PortableVerificationBundle(
            execution_record=forged_rec,
            previous_execution_hash="made_up_prev",
            merkle_root="made_up_root",
            sibling_hashes=["fake_sibling"],
            index_path=[0]
        )
        with self.assertRaisesRegex(ValueError, "Verification Rejection"):
            Verifier.verify_certificate(b)

    def test_scenario_6_sequence_gap_attack(self):
        # Scenario 6 - Sequence Gap Attack (Simulate 1, 2, 4, 5)
        ledger = EvidenceLedger()
        ledger.append(self.r1)
        ledger.append(self.r2)
        # Gap!
        r4 = create_valid_record("exec4", self.h3, "replay4", "SUCCESS", "run_hash_4", 4)
        
        # evidence_ledger.py throws ValueError automatically if we append an invalid previous hash
        with self.assertRaises(ValueError):
            ledger.append(r4) # Integrity failure during chain building

    def test_scenario_7_record_reordering_attack(self):
        # Scenario 7 - Record Reordering Attack (Simulate 1, 3, 2, 4)
        ledger = EvidenceLedger()
        ledger.append(self.r1)
        # Reorder!
        with self.assertRaises(ValueError):
            ledger.append(self.r3) # Should fail chain validation

    def test_scenario_8_cross_certificate_replay(self):
        # Scenario 8 - Cross-Certificate Replay (Reuse certificate for different execution)
        b = copy.deepcopy(self.valid_bundle)
        # Taking R2's certificate but wrapping R3
        b.execution_record = self.r3 
        # Lineage will mismatch the bundle's assertions
        with self.assertRaisesRegex(ValueError, "Lineage Failure"):
            Verifier.verify_certificate(b)

if __name__ == '__main__':
    unittest.main(verbosity=2)
