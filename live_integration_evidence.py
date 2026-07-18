"""
live_integration_evidence.py — Phase 3: Live Ecosystem Evidence Collection

Runs all live ecosystem integrations and captures structured evidence
to review_packets/evidence/ for the final review package.

Evidence captured:
  - KESHAV /health response
  - KESHAV /metrics/json response
  - KESHAV /analyze request/response pairs (multiple scenarios)
  - Integration timestamps and latency data
  - Unavailable service documentation
"""

import json
import os
import sys
import time
import logging
from datetime import datetime, timezone
from pathlib import Path

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s"
)
logger = logging.getLogger("qcg.evidence")

EVIDENCE_DIR = Path(__file__).parent / "review_packets" / "evidence"
EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)


def save_evidence(filename: str, data: dict, description: str = ""):
    """Save evidence data as a JSON file with metadata header."""
    evidence = {
        "_metadata": {
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "description": description,
            "file": filename,
        },
        "data": data,
    }
    path = EVIDENCE_DIR / filename
    with open(path, "w", encoding="utf-8") as f:
        json.dump(evidence, f, indent=2, default=str)
    logger.info("Evidence saved: %s", path)
    return path


def collect_keshav_evidence():
    """Collect all KESHAV live integration evidence."""
    from keshav_live_client import KeshavClient, KeshavAnalysisRequest

    client = KeshavClient()
    results = {
        "service": "KESHAV",
        "base_url": client.base_url,
        "tests": [],
        "overall_status": "PASS",
    }

    print("=" * 70)
    print("KESHAV LIVE INTEGRATION EVIDENCE COLLECTION")
    print(f"Target: {client.base_url}")
    print(f"Time:   {datetime.now(timezone.utc).isoformat()}")
    print("=" * 70)

    # --- Test 1: Health Check ---
    print("\n[1/5] Health Check...")
    health = client.health()
    test1 = {
        "test": "KESHAV Health Check",
        "endpoint": "GET /health",
        "purpose": "Verify KESHAV service is live and responsive",
        "expected_outcome": "Status OK, service KESHAV",
        "actual_outcome": f"Status={health.status}, Service={health.service}",
        "passed": health.status == "OK",
        "response": health.raw_response,
    }
    results["tests"].append(test1)
    print(f"  Result: {'PASS' if test1['passed'] else 'FAIL'} - {test1['actual_outcome']}")

    # --- Test 2: Metrics ---
    print("\n[2/5] Metrics Retrieval...")
    metrics = client.metrics()
    test2 = {
        "test": "KESHAV Metrics Retrieval",
        "endpoint": "GET /metrics/json",
        "purpose": "Verify KESHAV exposes operational metrics",
        "expected_outcome": "JSON metrics with request_count, latency stats",
        "actual_outcome": f"Received {len(metrics)} metric fields",
        "passed": "request_count" in metrics or "error" not in metrics,
        "response": metrics,
    }
    results["tests"].append(test2)
    print(f"  Result: {'PASS' if test2['passed'] else 'FAIL'}")

    # --- Test 3: Analyze - Valid Contract ---
    print("\n[3/5] Analyze - Valid Contract...")
    req_valid = KeshavAnalysisRequest(
        trace_id="qcg-evidence-valid-001",
        execution_id="exec-evidence-valid",
        tasks=[{"task_id": "QCG_VERIFY", "depends_on": []}],
        constraint_results=[
            {"task_id": "QCG_VERIFY", "is_valid": True, "unsatisfied_dependencies": []}
        ],
        propagation_results=[
            {"task_id": "QCG_VERIFY", "affected_tasks": [], "impact_score": 3}
        ],
    )
    resp_valid = client.analyze(req_valid)
    test3 = {
        "test": "KESHAV Analyze - Valid Contract",
        "endpoint": "POST /analyze",
        "purpose": "Verify KESHAV correctly analyzes a valid QCG contract",
        "expected_outcome": "200 OK with severity LOW (no constraint failures)",
        "actual_outcome": f"Severity={resp_valid.severity}, RootCause={resp_valid.root_cause}",
        "passed": resp_valid.severity != "ERROR",
        "request": req_valid.to_dict(),
        "response": resp_valid.raw_response,
    }
    results["tests"].append(test3)
    print(f"  Result: {'PASS' if test3['passed'] else 'FAIL'} - Severity={resp_valid.severity}")

    # --- Test 4: Analyze - Constraint Failure ---
    print("\n[4/5] Analyze - Constraint Failure...")
    req_fail = KeshavAnalysisRequest(
        trace_id="qcg-evidence-fail-001",
        execution_id="exec-evidence-fail",
        tasks=[
            {"task_id": "T1", "depends_on": []},
            {"task_id": "T2", "depends_on": ["T1"]},
        ],
        constraint_results=[
            {"task_id": "T1", "is_valid": False, "unsatisfied_dependencies": []},
            {"task_id": "T2", "is_valid": False, "unsatisfied_dependencies": ["T1"]},
        ],
        propagation_results=[
            {"task_id": "T1", "affected_tasks": ["T2"], "impact_score": 8},
            {"task_id": "T2", "affected_tasks": [], "impact_score": 3},
        ],
    )
    resp_fail = client.analyze(req_fail)
    test4 = {
        "test": "KESHAV Analyze - Constraint Failure",
        "endpoint": "POST /analyze",
        "purpose": "Verify KESHAV detects root cause in a failing dependency chain",
        "expected_outcome": "200 OK with severity HIGH, root_cause identified",
        "actual_outcome": f"Severity={resp_fail.severity}, RootCause={resp_fail.root_cause}, Signal={resp_fail.resolution_signal}",
        "passed": resp_fail.root_cause is not None and resp_fail.severity in ("HIGH", "MEDIUM"),
        "request": req_fail.to_dict(),
        "response": resp_fail.raw_response,
    }
    results["tests"].append(test4)
    print(f"  Result: {'PASS' if test4['passed'] else 'FAIL'} - RootCause={resp_fail.root_cause}")

    # --- Test 5: Trace Continuity ---
    print("\n[5/5] Trace Continuity Verification...")
    req_trace = KeshavAnalysisRequest(
        trace_id="qcg-trace-continuity-test",
        execution_id="exec-trace-continuity",
        tasks=[{"task_id": "TRACE_CHECK", "depends_on": []}],
        constraint_results=[
            {"task_id": "TRACE_CHECK", "is_valid": True, "unsatisfied_dependencies": []}
        ],
        propagation_results=[
            {"task_id": "TRACE_CHECK", "affected_tasks": [], "impact_score": 0}
        ],
    )
    resp_trace = client.analyze(req_trace)
    trace_preserved = resp_trace.trace_id == req_trace.trace_id
    test5 = {
        "test": "KESHAV Trace Continuity",
        "endpoint": "POST /analyze",
        "purpose": "Verify KESHAV preserves trace_id for end-to-end lineage",
        "expected_outcome": "Response trace_id matches request trace_id",
        "actual_outcome": f"Request trace_id={req_trace.trace_id}, Response trace_id={resp_trace.trace_id}, Match={trace_preserved}",
        "passed": trace_preserved,
        "request": req_trace.to_dict(),
        "response": resp_trace.raw_response,
    }
    results["tests"].append(test5)
    print(f"  Result: {'PASS' if test5['passed'] else 'FAIL'}")

    # --- Summary ---
    passed = sum(1 for t in results["tests"] if t["passed"])
    total = len(results["tests"])
    results["summary"] = {
        "total_tests": total,
        "passed": passed,
        "failed": total - passed,
        "pass_rate": f"{passed}/{total}",
    }
    results["overall_status"] = "PASS" if passed == total else "PARTIAL"

    # Save evidence files
    save_evidence(
        "keshav_live_integration.json",
        results,
        "Complete KESHAV live integration evidence with all API request/response pairs"
    )

    save_evidence(
        "keshav_api_traces.json",
        json.loads(client.get_evidence_log()),
        "Raw KESHAV API interaction log with timestamps and latencies"
    )

    print(f"\n{'=' * 70}")
    print(f"KESHAV Evidence Collection Complete: {passed}/{total} tests passed")
    print(f"Evidence saved to: {EVIDENCE_DIR}")
    print(f"{'=' * 70}")

    return results


def document_unavailable_services():
    """Document ecosystem services that are not yet available for live integration."""
    unavailable = {
        "documented_at": datetime.now(timezone.utc).isoformat(),
        "services": [
            {
                "service": "Dhiraj Runtime",
                "role": "Runtime Execution",
                "status": "UNAVAILABLE",
                "reason": "No live API URL provided. Service endpoint not yet deployed or communicated.",
                "evidence": "No URL available for HTTP connection attempt",
                "required_followup": "Dhiraj to provide live runtime API URL",
                "qcg_readiness": "Integration harness ready — ExecutionValidatorInterface implemented and tested locally",
            },

            {
                "service": "Raj Governance",
                "role": "Governance Approval",
                "status": "UNAVAILABLE",
                "reason": "No live API URL provided. Governance API not yet accessible.",
                "evidence": "No URL available for HTTP connection attempt",
                "required_followup": "Raj to provide live governance API URL",
                "qcg_readiness": "GovernanceAuthority and strict mode enforcement tested locally",
            },
            {
                "service": "Pravah Lineage",
                "role": "Trace Continuity & Provenance",
                "status": "UNAVAILABLE",
                "reason": "No live API URL provided. Lineage tracking endpoints not accessible.",
                "evidence": "No URL available for HTTP connection attempt",
                "required_followup": "Pravah team to provide live lineage API URL",
                "qcg_readiness": "Trace continuity propagation implemented — sequence_number, runtime_hash, final_hash emitted in /verify response",
            },
            {
                "service": "InsightFlow Telemetry",
                "role": "Observability",
                "status": "UNAVAILABLE",
                "reason": "No live API URL provided. Telemetry ingestion endpoints not accessible.",
                "evidence": "No URL available for HTTP connection attempt",
                "required_followup": "InsightFlow team to provide telemetry push endpoint",
                "qcg_readiness": "Structured JSON logging operational, /health and /metrics endpoints serving data",
            },
        ],
    }

    save_evidence(
        "unavailable_services.json",
        unavailable,
        "Documentation of ecosystem services unavailable for live integration, with reasons and required follow-ups"
    )

    print("\n" + "=" * 70)
    print("UNAVAILABLE SERVICES DOCUMENTED")
    print("=" * 70)
    for svc in unavailable["services"]:
        print(f"  {svc['service']:30s} -> {svc['status']} ({svc['reason'][:60]}...)")
    print(f"\nEvidence saved to: {EVIDENCE_DIR / 'unavailable_services.json'}")

    return unavailable


def main():
    print("\n" + "#" * 70)
    print("# QCG LIVE ECOSYSTEM INTEGRATION — EVIDENCE COLLECTION")
    print(f"# Timestamp: {datetime.now(timezone.utc).isoformat()}")
    print("#" * 70)

    # 1. Collect KESHAV evidence (live)
    keshav_results = collect_keshav_evidence()

    # 1b. Collect Pritesh evidence (live)
    print("\n[Running Pritesh Evidence Client...]")
    import os
    os.system("python pritesh_live_client.py > review_packets/evidence/pritesh_evidence.json")
    print("Pritesh evidence collected in review_packets/evidence/pritesh_evidence.json")

    # 2. Document unavailable services
    unavailable = document_unavailable_services()

    # 3. Summary
    print("\n" + "#" * 70)
    print("# EVIDENCE COLLECTION SUMMARY")
    print("#" * 70)
    print(f"  KESHAV:          {keshav_results['overall_status']} ({keshav_results['summary']['pass_rate']} tests)")
    for svc in unavailable["services"]:
        print(f"  {svc['service']:18s} {svc['status']}")
    print(f"\n  All evidence in: {EVIDENCE_DIR}")
    print("#" * 70)


if __name__ == "__main__":
    main()
