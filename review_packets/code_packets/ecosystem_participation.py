"""
ecosystem_participation.py -- Phase 6: Ecosystem Participation Proof (Enhanced)

Demonstrates that the execution runtime and trust layer handle contracts
from any producer transparently.  The system is no longer quantum-specific;
it is a generic trust and verification engine for any ecosystem participant.

Enhancements over v1:
- Named future consumers: NICAI, InsightFlow, Pravah, Sampada
- NodeRegistry integration: all participants must register
- TrustChain tracking: each processing step records a custody handoff
- MerkleAuditTrail: shared event log with inclusion proofs
- Full verification report per participant
"""

from __future__ import annotations

import json
import hashlib
from datetime import datetime, timezone

from execution_contract import ComputationExecutionContract
from provenance import sign_contract
from node_identity import NodeSigner
from consensus_simulation import DistributedConsensusNode, ConsensusEngine
from replay_bundle import (
    ReplayBundle, ProducerLineage, AdapterLineage,
    GovernanceLineage, ExecutionLineage,
)
from trust_chain import NodeRegistry, TrustChain
from audit_trail import MerkleAuditTrail


# ---------------------------------------------------------------------------
# Setup: Global Network Infrastructure
# ---------------------------------------------------------------------------

# Gateway
gateway = NodeSigner("GLOBAL_GATEWAY", "GATEWAY")

# Execution nodes
exec_nodes = [
    DistributedConsensusNode("EXEC_NODE_1"),
    DistributedConsensusNode("EXEC_NODE_2"),
    DistributedConsensusNode("EXEC_NODE_3"),
]
engine = ConsensusEngine(exec_nodes)

# Registry
registry = NodeRegistry()
registry.register(gateway.identity)
for n in exec_nodes:
    registry.register(n.signer.identity)

# Shared audit trail
audit_trail = MerkleAuditTrail()


# ---------------------------------------------------------------------------
# Generic participant pipeline
# ---------------------------------------------------------------------------

def process_participant(
    name: str,
    producer_type: str,
    payload: dict,
    producer: NodeSigner,
) -> ReplayBundle:
    """Generic processing pipeline for ANY ecosystem participant."""
    print(f"\n{'='*60}")
    print(f"  {name} ({producer_type})")
    print(f"  Producer: {producer.identity.node_id}")
    print(f"{'='*60}")

    # Register producer
    registry.register(producer.identity)

    # 1. Create and sign contract
    contract = ComputationExecutionContract(
        producer_type=producer_type,
        payload=payload,
        confidence=0.95,
        trace_id=f"tr-{producer.identity.node_id.lower()}-01",
        contract_version="2.0.0",
    )
    signed_contract = sign_contract(contract, producer)
    print("  [+] Contract signed by producer")

    # 2. Build trust chain: Producer -> Gateway -> Exec
    chain = TrustChain()
    chain.add_handoff(producer, gateway.identity, "PRODUCE", signed_contract.payload_hash)
    chain.add_handoff(gateway, exec_nodes[0].signer.identity, "GATEWAY_FORWARD", signed_contract.payload_hash)
    print(f"  [+] Trust chain: {len(chain)} handoffs recorded")

    # 3. Audit trail events
    audit_trail.append("CONTRACT_SIGNED", {
        "trace_id": signed_contract.trace_id,
        "producer_id": producer.identity.node_id,
    }, producer.identity.node_id)

    # 4. Consensus
    consensus_proof = engine.run_consensus(signed_contract, producer.identity.public_key)
    print(f"  [+] Consensus: reached={consensus_proof.consensus_reached}  "
          f"agreement={consensus_proof.agreement_percentage:.0%}  "
          f"attestations={len(consensus_proof.node_attestations)}")

    audit_trail.append("CONSENSUS_COMPLETED", {
        "trace_id": signed_contract.trace_id,
        "consensus_reached": consensus_proof.consensus_reached,
        "agreement_pct": consensus_proof.agreement_percentage,
    }, gateway.identity.node_id)

    # 5. Verify trust chain
    chain_ok, chain_errs = chain.verify_chain(registry)
    print(f"  [+] Trust chain verification: {'PASS' if chain_ok else 'FAIL'}")

    # 6. Build ReplayBundle
    bundle = ReplayBundle(
        bundle_id=f"RB-{producer.identity.node_id}",
        producer_lineage=ProducerLineage(
            producer.identity.node_id,
            producer_type,
            signed_contract.payload_hash,
            signed_contract.producer_signature,
        ),
        adapter_lineage=AdapterLineage("1.0.0", "2.0.0"),
        governance_lineage=GovernanceLineage(True, []),
        execution_lineage=ExecutionLineage(
            signed_contract.trace_id,
            consensus_proof.final_hash,
            "ACK:OK",
            datetime.now(timezone.utc).isoformat(),
        ),
        consensus_lineage=consensus_proof,
        audit_trail_root=audit_trail.root_hash(),
        trust_chain=chain.to_dict_list(),
    )
    bundle.sign(gateway)

    # 7. Verify bundle
    res = bundle.verify(gateway.identity.public_key, producer.identity.public_key)
    report = bundle.verification_report()
    print(f"  [+] Replay Bundle: {res}")
    for check, status in report.get("checks", {}).items():
        print(f"      {check}: {status}")

    return bundle


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print("  ECOSYSTEM PARTICIPATION PROOF (ENHANCED)")
    print("  Runtime is producer-agnostic. Trust is universal.")
    print("=" * 60)

    # Participant A: Quantum Producer
    quantum_producer = NodeSigner("PROD_QUANTUM_01", "QUANTUM_PRODUCER")
    process_participant(
        "Participant A: Quantum Producer",
        "QUANTUM",
        {"task": "superdense_coding", "bits": "11"},
        quantum_producer,
    )

    # Participant B: Classical Producer
    classical_producer = NodeSigner("PROD_CLASSICAL_01", "CLASSICAL_PRODUCER")
    process_participant(
        "Participant B: Classical Producer",
        "CLASSICAL",
        {"task": "risk_analysis", "model": "monte_carlo"},
        classical_producer,
    )

    # Participant C: NICAI (Future Consumer)
    nicai_producer = NodeSigner("NICAI_NODE", "ECOSYSTEM_PARTICIPANT")
    process_participant(
        "Participant C: NICAI",
        "HYBRID",
        {"task": "inference_verification", "model_id": "nicai-v3"},
        nicai_producer,
    )

    # Participant D: InsightFlow (Future Consumer)
    insightflow_producer = NodeSigner("INSIGHTFLOW_NODE", "ECOSYSTEM_PARTICIPANT")
    process_participant(
        "Participant D: InsightFlow",
        "CLASSICAL",
        {"task": "data_pipeline_audit", "pipeline": "etl-prod-7"},
        insightflow_producer,
    )

    # Participant E: Pravah (Future Consumer)
    pravah_producer = NodeSigner("PRAVAH_NODE", "ECOSYSTEM_PARTICIPANT")
    process_participant(
        "Participant E: Pravah",
        "HYBRID",
        {"task": "stream_integrity_check", "stream_id": "pravah-main"},
        pravah_producer,
    )

    # Participant F: Sampada (Future Consumer)
    sampada_producer = NodeSigner("SAMPADA_NODE", "ECOSYSTEM_PARTICIPANT")
    process_participant(
        "Participant F: Sampada",
        "QUANTUM",
        {"task": "resource_optimization", "cluster": "sampada-east"},
        sampada_producer,
    )

    # --- Summary ---
    print(f"\n{'='*60}")
    print(f"  SUMMARY")
    print(f"{'='*60}")
    print(f"  Registered Nodes     : {len(registry)}")
    print(f"  Audit Trail Entries  : {len(audit_trail)}")
    print(f"  Audit Trail Root     : {audit_trail.root_hash()[:32]}...")
    trail_ok, trail_errs = audit_trail.verify_integrity()
    print(f"  Audit Trail Integrity: {'PASS' if trail_ok else 'FAIL'}")
    print(f"\n  All 6 participants processed through identical trust pipeline.")
    print(f"  Runtime is no longer quantum-specific.")
    print(f"  It is an ecosystem execution participant.")
    print(f"{'='*60}")
