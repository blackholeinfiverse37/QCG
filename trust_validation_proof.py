"""
trust_validation_proof.py — Phase 4: Trust Validation Proof

Demonstrates all four trust verification scenarios:
  1. Valid registered producer          → PASS (VerificationResult.passed=True)
  2. Tampered contract payload          → HALT:INVALID_SIGNATURE
  3. Forged / invalid signature         → HALT:INVALID_SIGNATURE
  4. Unregistered producer              → HALT:UNVERIFIED_PRODUCER
  5. Type mismatch (wrong producer_type)→ HALT:TRUST_FAILURE

Exit codes:
    0 — all cases pass
    1 — one or more cases failed
"""

from __future__ import annotations

import sys

from execution_contract import ComputationExecutionContract
from node_identity import NodeSigner
from provenance import sign_contract
from producer_verification import (
    ProducerRegistry,
    ProducerVerificationLayer,
    VerificationFailure,
)


def _make_producer(node_id: str, role: str = "QUANTUM_PRODUCER") -> NodeSigner:
    return NodeSigner(node_id, role)


def _make_signed_contract(
    producer: NodeSigner,
    trace_id: str = "trust-proof-001",
    producer_type: str = "QUANTUM",
) -> ComputationExecutionContract:
    base = ComputationExecutionContract(
        producer_type=producer_type,
        payload={"data": "trust_validation_test", "value": 42},
        confidence=0.95,
        trace_id=trace_id,
        contract_version="2.0.0",
    )
    return sign_contract(base, producer)


def run_proof(verbose: bool = True) -> dict:
    results: dict[str, bool] = {}

    producer = _make_producer("TRUST_PROOF_PRODUCER", "QUANTUM_PRODUCER")

    registry = ProducerRegistry()
    registry.register(producer.identity)

    verifier = ProducerVerificationLayer(registry)

    # ------------------------------------------------------------------
    # Case 1: Valid registered producer → passed=True
    # ------------------------------------------------------------------
    signed = _make_signed_contract(producer, "trust-proof-001")
    r1 = verifier.verify(signed)
    results["valid_producer_accepted"] = r1.passed is True and r1.failure_mode == ""
    if verbose:
        print(f"\n  [Case 1: Valid producer]")
        print(f"    producer_id={r1.producer_id}  type={r1.producer_type}")
        print(f"    passed={r1.passed}  failure_mode='{r1.failure_mode}'")
        print(f"    pass={results['valid_producer_accepted']}")

    # ------------------------------------------------------------------
    # Case 2: Tampered payload → INVALID_SIGNATURE
    # ------------------------------------------------------------------
    signed2 = _make_signed_contract(producer, "trust-proof-002")
    # Mutate payload without re-signing — payload_hash mismatch
    tampered_dict = signed2.to_dict()
    tampered_dict["payload"] = {"data": "INJECTED", "value": 999}
    # Force-recompute payload_hash so it matches new payload but breaks sig
    import hashlib, json
    tampered_dict["payload_hash"] = hashlib.sha256(
        json.dumps(tampered_dict["payload"], sort_keys=True).encode()
    ).hexdigest()
    tampered = ComputationExecutionContract(**tampered_dict)
    r2 = verifier.verify(tampered)
    results["tampered_payload_rejected"] = (
        r2.passed is False
        and r2.failure_mode == VerificationFailure.INVALID_SIGNATURE
    )
    if verbose:
        print(f"\n  [Case 2: Tampered payload]")
        print(f"    passed={r2.passed}  failure_mode={r2.failure_mode}")
        print(f"    reason='{r2.reason}'")
        print(f"    pass={results['tampered_payload_rejected']}")

    # ------------------------------------------------------------------
    # Case 3: Forged signature (random bytes) → INVALID_SIGNATURE
    # ------------------------------------------------------------------
    signed3 = _make_signed_contract(producer, "trust-proof-003")
    forged_dict = signed3.to_dict()
    forged_dict["contract_signature"] = "deadbeef" * 18   # invalid DER ECDSA
    forged = ComputationExecutionContract(**forged_dict)
    r3 = verifier.verify(forged)
    results["forged_signature_rejected"] = (
        r3.passed is False
        and r3.failure_mode == VerificationFailure.INVALID_SIGNATURE
    )
    if verbose:
        print(f"\n  [Case 3: Forged signature]")
        print(f"    passed={r3.passed}  failure_mode={r3.failure_mode}")
        print(f"    reason='{r3.reason}'")
        print(f"    pass={results['forged_signature_rejected']}")

    # ------------------------------------------------------------------
    # Case 4: Unregistered producer → UNVERIFIED_PRODUCER
    # ------------------------------------------------------------------
    unknown_producer = _make_producer("UNKNOWN_PRODUCER_99", "QUANTUM_PRODUCER")
    # Do NOT register unknown_producer
    signed4 = _make_signed_contract(unknown_producer, "trust-proof-004")
    r4 = verifier.verify(signed4)
    results["unregistered_producer_rejected"] = (
        r4.passed is False
        and r4.failure_mode == VerificationFailure.UNVERIFIED_PRODUCER
    )
    if verbose:
        print(f"\n  [Case 4: Unregistered producer]")
        print(f"    producer_id={r4.producer_id}")
        print(f"    passed={r4.passed}  failure_mode={r4.failure_mode}")
        print(f"    reason='{r4.reason}'")
        print(f"    pass={results['unregistered_producer_rejected']}")

    # ------------------------------------------------------------------
    # Case 5: Type mismatch — producer registered as QUANTUM, declares CLASSICAL
    # ------------------------------------------------------------------
    type_mismatch_producer = _make_producer("TYPE_MISMATCH_PRODUCER", "QUANTUM_PRODUCER")
    registry.register(type_mismatch_producer.identity)  # allowed: {"QUANTUM"}
    # Sign a CLASSICAL contract with a QUANTUM producer
    signed5 = _make_signed_contract(type_mismatch_producer, "trust-proof-005", producer_type="CLASSICAL")
    r5 = verifier.verify(signed5)
    results["type_mismatch_rejected"] = (
        r5.passed is False
        and r5.failure_mode == VerificationFailure.TRUST_FAILURE
    )
    if verbose:
        print(f"\n  [Case 5: Type mismatch]")
        print(f"    declared_type={r5.producer_type}  allowed={sorted(registry.allowed_types(r5.producer_id))}")
        print(f"    passed={r5.passed}  failure_mode={r5.failure_mode}")
        print(f"    reason='{r5.reason}'")
        print(f"    pass={results['type_mismatch_rejected']}")

    # ------------------------------------------------------------------
    # Case 6: Missing producer_id → UNVERIFIED_PRODUCER
    # ------------------------------------------------------------------
    no_id_base = ComputationExecutionContract(
        producer_type="QUANTUM",
        payload={"data": "no_id_test"},
        confidence=0.95,
        trace_id="trust-proof-006",
        contract_version="2.0.0",
    )
    # producer_id defaults to "" — no signing, no id
    r6 = verifier.verify(no_id_base)
    results["missing_producer_id_rejected"] = (
        r6.passed is False
        and r6.failure_mode == VerificationFailure.UNVERIFIED_PRODUCER
    )
    if verbose:
        print(f"\n  [Case 6: Missing producer_id]")
        print(f"    passed={r6.passed}  failure_mode={r6.failure_mode}")
        print(f"    reason='{r6.reason}'")
        print(f"    pass={results['missing_producer_id_rejected']}")

    all_passed = all(results.values())

    if verbose:
        print(f"\n{'='*60}")
        status = "PASS" if all_passed else "FAIL"
        print(f"  TRUST VALIDATION PROOF - {status}")
        print(f"{'='*60}")
        for case, passed in results.items():
            mark = "[PASS]" if passed else "[FAIL]"
            print(f"  {mark}  {case}")
        print(f"{'='*60}\n")

    return {"passed": all_passed, "cases": results}


if __name__ == "__main__":
    proof = run_proof()
    sys.exit(0 if proof["passed"] else 1)
