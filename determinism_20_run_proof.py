"""
determinism_20_run_proof.py — Phase 1: 20-Run Consistency Proof

Runs the same CommunicationRequest through the gateway 20 times and
proves that all deterministic fields are identical across every run.

Observability fields (timestamps) are allowed to differ — this is expected
and recorded in the proof output.

Exit codes:
    0 — all 20 runs deterministically identical
    1 — deterministic mismatch detected
"""

from __future__ import annotations

import json
import sys

from communication_contract import make_message_id, CommunicationRequest
from deterministic_replay import ReplayContract, ReplayComparator


RUNS = 20
FIXED_MESSAGE_ID = make_message_id("determinism-proof", "20-run", "fixed")


def _make_request() -> CommunicationRequest:
    """Fixed, deterministic request used for every run."""
    return CommunicationRequest(
        message_id=FIXED_MESSAGE_ID,
        source_type="CLASSICAL",
        destination_type="QUANTUM",
        payload={"status": "NODE_READY", "value": 42},
        confidence=0.95,
    )


def run_20_run_proof(runs: int = RUNS, verbose: bool = True) -> dict:
    """
    Execute the same request `runs` times through independent gateway
    instances and compare deterministic fields.

    Returns a proof dict with:
        passed          : bool
        runs            : int
        deterministic_hash : str (must be identical across all runs)
        observability_diffs_count : int (timestamps that differ — expected)
        evidence        : list of per-run hashes
    """
    from gateway import CommunicationGateway

    comparator = ReplayComparator()
    contracts: list[ReplayContract] = []

    # Fixed request — same message_id every run proves determinism
    request = _make_request()

    for i in range(runs):
        # Fresh gateway with its own isolated registry — no cross-run state
        gw = CommunicationGateway()
        response = gw.send(request)
        rc = ReplayContract.from_response(response)
        contracts.append(rc)

    result = comparator.compare_many(contracts)

    # All deterministic hashes must match
    det_hashes = [c.deterministic_hash() for c in contracts]
    all_hashes_match = len(set(det_hashes)) == 1

    proof = {
        "passed": result.passed and all_hashes_match,
        "runs": runs,
        "deterministic_hash": det_hashes[0],
        "all_hashes_identical": all_hashes_match,
        "deterministic_match": result.deterministic_match,
        "mismatched_fields": list(result.mismatched_fields),
        "observability_diffs_count": len(result.observability_diffs),
        "evidence": det_hashes,
    }

    if verbose:
        _print_proof(proof)

    return proof


def _print_proof(proof: dict) -> None:
    status = "PASS" if proof["passed"] else "FAIL"
    print(f"\n{'='*60}")
    print(f"  20-RUN DETERMINISM PROOF — {status}")
    print(f"{'='*60}")
    print(f"  Runs executed          : {proof['runs']}")
    print(f"  Deterministic hash     : {proof['deterministic_hash'][:16]}...")
    print(f"  All hashes identical   : {proof['all_hashes_identical']}")
    print(f"  Deterministic match    : {proof['deterministic_match']}")
    print(f"  Mismatched fields      : {proof['mismatched_fields'] or 'none'}")
    print(f"  Observability diffs    : {proof['observability_diffs_count']} "
          f"(timestamps — expected to differ)")
    print(f"{'='*60}\n")
    if not proof["passed"]:
        print("  EVIDENCE (hashes):")
        for i, h in enumerate(proof["evidence"]):
            print(f"    run {i+1:02d}: {h[:32]}...")


if __name__ == "__main__":
    proof = run_20_run_proof()
    sys.exit(0 if proof["passed"] else 1)
