"""
platform_service_registration_runner.py — End-to-End Registration & Evidence Runner

Performs the complete Platform Service registration lifecycle:

1. Starts the capability registry server (existing infrastructure)
2. Starts the platform discovery server (new)
3. Registers Universal Solver Fabric as a Platform Service
4. Registers QCG as a Platform Service
5. Publishes capability manifests
6. Validates all endpoints
7. Performs version negotiation tests
8. Executes lifecycle transitions
9. Discovers services through the canonical API
10. Generates deterministic evidence for every step
11. Saves complete evidence packet to evidence/platform_registration/

Usage:
    python platform_service_registration_runner.py
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from typing import Any, Dict, List

# -- Project imports --------------------------------------------------------
from capability_registry import CapabilityRegistryServer, CapabilityRegistryClient
from platform_service_registry import (
    PlatformServiceRegistry,
    PlatformServiceRecord,
    CapabilityManifest,
    OperationContract,
    RegistrationEvidenceRecorder,
    VersionNegotiator,
)
from platform_lifecycle_manager import LifecycleManager
from platform_service_discovery import PlatformDiscoveryServer

import config


# ---------------------------------------------------------------------------
# Evidence packet directory
# ---------------------------------------------------------------------------

EVIDENCE_DIR = os.path.join("evidence", "platform_registration")
os.makedirs(EVIDENCE_DIR, exist_ok=True)


def _save_evidence(filename: str, data: Any):
    """Save a JSON evidence file to the evidence directory."""
    path = os.path.join(EVIDENCE_DIR, filename)
    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)
    print(f"  [EVIDENCE] Saved: {path}")


def _http_get(url: str, timeout: int = 5) -> Dict[str, Any]:
    """Perform an HTTP GET request and return JSON response."""
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _http_get_text(url: str, timeout: int = 5) -> str:
    """Perform an HTTP GET and return text response."""
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8")


def _http_post(url: str, data: dict, timeout: int = 5) -> Dict[str, Any]:
    """Perform an HTTP POST request and return JSON response."""
    payload = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


# ---------------------------------------------------------------------------
# Build manifests from the static JSON file
# ---------------------------------------------------------------------------

def _load_manifest_json() -> Dict[str, Any]:
    """Load the canonical manifest JSON."""
    manifest_path = os.path.join(os.path.dirname(__file__), "platform_capability_manifest.json")
    with open(manifest_path) as f:
        return json.load(f)


def _build_usf_manifest(manifest_data: Dict) -> CapabilityManifest:
    """Build the Universal Solver Fabric CapabilityManifest from JSON data."""
    usf = manifest_data["services"][0]["manifest"]
    operations = [
        OperationContract(
            operation_name=op["operation_name"],
            description=op["description"],
            input_contract=op["input_contract"],
            output_contract=op["output_contract"],
            execution_modes=op["execution_modes"],
            idempotent=op.get("idempotent", False),
        )
        for op in usf["supported_operations"]
    ]
    return CapabilityManifest(
        manifest_id=usf["manifest_id"],
        service_name="UNIVERSAL_SOLVER_FABRIC",
        version="1.0.0",
        supported_operations=operations,
        execution_modes=usf["execution_modes"],
        determinism_guarantees=usf["determinism_guarantees"],
        replay_guarantees=usf["replay_guarantees"],
        trust_requirements=usf["trust_requirements"],
        evidence_guarantees=usf["evidence_guarantees"],
        runtime_dependencies=usf["runtime_dependencies"],
        version_compatibility=usf["version_compatibility"],
        security_requirements=usf["security_requirements"],
        resource_requirements=usf["resource_requirements"],
    )


def _build_qcg_manifest(manifest_data: Dict) -> CapabilityManifest:
    """Build the QCG CapabilityManifest from JSON data."""
    qcg = manifest_data["services"][1]["manifest"]
    operations = [
        OperationContract(
            operation_name=op["operation_name"],
            description=op["description"],
            input_contract=op["input_contract"],
            output_contract=op["output_contract"],
            execution_modes=op["execution_modes"],
            idempotent=op.get("idempotent", False),
        )
        for op in qcg["supported_operations"]
    ]
    return CapabilityManifest(
        manifest_id=qcg["manifest_id"],
        service_name="QCG_TRUST_VERIFICATION",
        version="1.0.0",
        supported_operations=operations,
        execution_modes=qcg["execution_modes"],
        determinism_guarantees=qcg["determinism_guarantees"],
        replay_guarantees=qcg["replay_guarantees"],
        trust_requirements=qcg["trust_requirements"],
        evidence_guarantees=qcg["evidence_guarantees"],
        runtime_dependencies=qcg["runtime_dependencies"],
        version_compatibility=qcg["version_compatibility"],
        security_requirements=qcg["security_requirements"],
        resource_requirements=qcg["resource_requirements"],
    )


# ---------------------------------------------------------------------------
# Registration runner
# ---------------------------------------------------------------------------

def run():
    print("=" * 72)
    print("  TANTRA Platform Service Registration -- Full Lifecycle Runner")
    print("=" * 72)

    run_start = datetime.now(timezone.utc).isoformat()
    all_evidence: Dict[str, Any] = {"run_started": run_start, "steps": []}

    # ------------------------------------------------------------------
    # STEP 1: Start existing Capability Registry Server
    # ------------------------------------------------------------------
    print("\n[STEP 1] Starting Capability Registry Server...")
    cap_server = CapabilityRegistryServer("127.0.0.1", config.REGISTRY_PORT)
    cap_server.start()
    time.sleep(0.3)
    print(f"  Registry server running on http://127.0.0.1:{config.REGISTRY_PORT}")

    # ------------------------------------------------------------------
    # STEP 2: Initialise Platform Registry & Discovery Server
    # ------------------------------------------------------------------
    print("\n[STEP 2] Initialising Platform Service Registry & Discovery Server...")
    evidence_recorder = RegistrationEvidenceRecorder()
    platform_registry = PlatformServiceRegistry(evidence_recorder=evidence_recorder)
    lifecycle_mgr = LifecycleManager()

    discovery_port = 9010
    discovery_server = PlatformDiscoveryServer(
        host="127.0.0.1",
        port=discovery_port,
        registry=platform_registry,
        lifecycle=lifecycle_mgr,
    )
    discovery_server.start()
    time.sleep(0.3)
    print(f"  Discovery server running on http://127.0.0.1:{discovery_port}/platform/v1/")

    base_url = f"http://127.0.0.1:{discovery_port}"

    # ------------------------------------------------------------------
    # STEP 3: Register Universal Solver Fabric
    # ------------------------------------------------------------------
    print("\n[STEP 3] Registering Universal Solver Fabric as Platform Service...")
    manifest_data = _load_manifest_json()
    usf_data = manifest_data["services"][0]

    usf_record = PlatformServiceRecord(
        platform_service_id=usf_data["platform_service_id"],
        capability_id=usf_data["capability_id"],
        service_name=usf_data["service_name"],
        version=usf_data["version"],
        provider=usf_data["provider"],
        owner=usf_data["owner"],
        runtime_type=usf_data["runtime_type"],
        service_classification=usf_data["service_classification"],
        capability_category=usf_data["capability_category"],
        status=usf_data["status"],
        description=usf_data["description"],
        tags=usf_data["tags"],
        endpoints=usf_data["endpoints"],
    )
    usf_manifest = _build_usf_manifest(manifest_data)

    usf_result = platform_registry.register_service(usf_record, usf_manifest)
    print(f"  USF Registration: {usf_result['status']}")
    all_evidence["steps"].append({"step": "USF_REGISTRATION", "result": usf_result})

    # Register version compatibility
    platform_registry.negotiator.register_compatibility(
        usf_data["platform_service_id"],
        compatible=["1.0.0"],
        deprecated=["0.9.0"],
        unsupported=["0.1.0", "0.5.0"],
    )

    # Register in lifecycle manager
    lifecycle_mgr.register(usf_data["platform_service_id"], "ACTIVE", "SYSTEM", "Initial registration")

    # Also register with existing capability registry
    cap_client = CapabilityRegistryClient(f"http://127.0.0.1:{config.REGISTRY_PORT}")
    cap_client.register({
        "capability_id": usf_data["capability_id"],
        "capability_name": usf_data["service_name"],
        "owner": usf_data["owner"],
        "version": usf_data["version"],
        "status": usf_data["status"],
        "scope": "SYSTEM",
        "dependencies": [],
        "attachment_rules": {
            "attachment_type": "api_linked",
            "protocol": "http_rest",
            "endpoint": f"http://127.0.0.1:{discovery_port}/platform/v1/services/{usf_data['platform_service_id']}",
        },
        "authority_limits": {
            "owns": ["solver discovery", "solver selection", "evidence-wrapped execution"],
            "does_not_own": ["contract validation", "replay detection", "governance policy"],
        },
        "inputs": [
            {"name": "problem_schema", "type": "object", "required": True, "description": "Optimization problem definition"},
        ],
        "outputs": [
            {"name": "evidence_package", "type": "object", "description": "Replay-safe execution evidence"},
        ],
        "consumers": [],
        "documentation_reference": {
            "primary": "docs/PLATFORM_SERVICE_ARCHITECTURE.md",
            "schema_file": "platform_capability_manifest.json",
        },
    })
    print("  USF registered in canonical Capability Registry")

    # ------------------------------------------------------------------
    # STEP 4: Register QCG
    # ------------------------------------------------------------------
    print("\n[STEP 4] Registering QCG as Platform Service...")
    qcg_data = manifest_data["services"][1]

    qcg_record = PlatformServiceRecord(
        platform_service_id=qcg_data["platform_service_id"],
        capability_id=qcg_data["capability_id"],
        service_name=qcg_data["service_name"],
        version=qcg_data["version"],
        provider=qcg_data["provider"],
        owner=qcg_data["owner"],
        runtime_type=qcg_data["runtime_type"],
        service_classification=qcg_data["service_classification"],
        capability_category=qcg_data["capability_category"],
        status=qcg_data["status"],
        description=qcg_data["description"],
        tags=qcg_data["tags"],
        endpoints=qcg_data["endpoints"],
    )
    qcg_manifest = _build_qcg_manifest(manifest_data)

    qcg_result = platform_registry.register_service(qcg_record, qcg_manifest)
    print(f"  QCG Registration: {qcg_result['status']}")
    all_evidence["steps"].append({"step": "QCG_REGISTRATION", "result": qcg_result})

    # Register version compatibility
    platform_registry.negotiator.register_compatibility(
        qcg_data["platform_service_id"],
        compatible=["1.0.0"],
        deprecated=["0.8.0"],
        unsupported=["0.1.0"],
    )

    lifecycle_mgr.register(qcg_data["platform_service_id"], "ACTIVE", "SYSTEM", "Initial registration")

    cap_client.register({
        "capability_id": qcg_data["capability_id"],
        "capability_name": qcg_data["service_name"],
        "owner": qcg_data["owner"],
        "version": qcg_data["version"],
        "status": qcg_data["status"],
        "scope": "SYSTEM",
        "dependencies": [],
        "attachment_rules": {
            "attachment_type": "api_linked",
            "protocol": "http_rest",
            "endpoint": f"http://127.0.0.1:{discovery_port}/platform/v1/services/{qcg_data['platform_service_id']}",
        },
        "authority_limits": {
            "owns": ["replay verification", "trust validation", "deterministic execution", "Byzantine consensus"],
            "does_not_own": ["solver selection", "problem formulation", "budget approval"],
        },
        "inputs": [
            {"name": "contract", "type": "object", "required": True, "description": "ComputationExecutionContract"},
        ],
        "outputs": [
            {"name": "verification_result", "type": "object", "description": "Trust verification result"},
        ],
        "consumers": [],
        "documentation_reference": {
            "primary": "docs/PLATFORM_SERVICE_ARCHITECTURE.md",
            "schema_file": "platform_capability_manifest.json",
        },
    })
    print("  QCG registered in canonical Capability Registry")

    # ------------------------------------------------------------------
    # STEP 5: Validate all discovery endpoints
    # ------------------------------------------------------------------
    print("\n[STEP 5] Validating Discovery API Endpoints...")
    endpoint_results = {}

    endpoints_to_validate = [
        ("list_services",          f"{base_url}/platform/v1/services"),
        ("get_usf",                f"{base_url}/platform/v1/services/{usf_data['platform_service_id']}"),
        ("get_qcg",                f"{base_url}/platform/v1/services/{qcg_data['platform_service_id']}"),
        ("usf_versions",           f"{base_url}/platform/v1/services/{usf_data['platform_service_id']}/versions"),
        ("usf_metadata",           f"{base_url}/platform/v1/services/{usf_data['platform_service_id']}/metadata"),
        ("usf_contracts",          f"{base_url}/platform/v1/services/{usf_data['platform_service_id']}/contracts"),
        ("usf_endpoints",          f"{base_url}/platform/v1/services/{usf_data['platform_service_id']}/endpoints"),
        ("usf_health",             f"{base_url}/platform/v1/services/{usf_data['platform_service_id']}/health"),
        ("usf_compatibility",      f"{base_url}/platform/v1/services/{usf_data['platform_service_id']}/compatibility"),
        ("qcg_versions",           f"{base_url}/platform/v1/services/{qcg_data['platform_service_id']}/versions"),
        ("qcg_metadata",           f"{base_url}/platform/v1/services/{qcg_data['platform_service_id']}/metadata"),
        ("qcg_contracts",          f"{base_url}/platform/v1/services/{qcg_data['platform_service_id']}/contracts"),
        ("qcg_endpoints",          f"{base_url}/platform/v1/services/{qcg_data['platform_service_id']}/endpoints"),
        ("qcg_health",             f"{base_url}/platform/v1/services/{qcg_data['platform_service_id']}/health"),
        ("qcg_compatibility",      f"{base_url}/platform/v1/services/{qcg_data['platform_service_id']}/compatibility"),
        ("server_health",          f"{base_url}/platform/v1/health"),
        ("server_readiness",       f"{base_url}/platform/v1/readiness"),
        ("server_evidence",        f"{base_url}/platform/v1/evidence"),
        ("server_version",         f"{base_url}/platform/v1/version"),
    ]

    all_ok = True
    for name, url in endpoints_to_validate:
        try:
            resp = _http_get(url)
            endpoint_results[name] = {"url": url, "status": "OK", "response": resp}
            print(f"  [OK] {name}: OK")
        except Exception as e:
            endpoint_results[name] = {"url": url, "status": "FAILED", "error": str(e)}
            print(f"  [FAIL] {name}: FAILED -- {e}")
            all_ok = False

    # Metrics endpoint (text/plain)
    try:
        metrics_text = _http_get_text(f"{base_url}/platform/v1/metrics")
        endpoint_results["server_metrics"] = {"url": f"{base_url}/platform/v1/metrics", "status": "OK", "response_length": len(metrics_text)}
        print(f"  [OK] server_metrics: OK ({len(metrics_text)} bytes)")
    except Exception as e:
        endpoint_results["server_metrics"] = {"url": f"{base_url}/platform/v1/metrics", "status": "FAILED", "error": str(e)}
        print(f"  [FAIL] server_metrics: FAILED -- {e}")
        all_ok = False

    all_evidence["steps"].append({"step": "ENDPOINT_VALIDATION", "all_ok": all_ok, "results": endpoint_results})

    # Save endpoint-specific evidence files
    _save_evidence("endpoint_validation.json", endpoint_results)
    _save_evidence("health_validation.json", {
        "usf_health": endpoint_results.get("usf_health", {}),
        "qcg_health": endpoint_results.get("qcg_health", {}),
        "server_health": endpoint_results.get("server_health", {}),
    })
    _save_evidence("readiness_validation.json", endpoint_results.get("server_readiness", {}))

    # ------------------------------------------------------------------
    # STEP 6: Version negotiation tests
    # ------------------------------------------------------------------
    print("\n[STEP 6] Testing Version Negotiation...")
    negotiation_results = []

    negotiation_tests = [
        (usf_data["platform_service_id"], "1.0.0", "COMPATIBLE"),
        (usf_data["platform_service_id"], "0.9.0", "DEPRECATED"),
        (usf_data["platform_service_id"], "0.1.0", "UNSUPPORTED"),
        (usf_data["platform_service_id"], "99.0.0", "UNSUPPORTED"),
        (qcg_data["platform_service_id"], "1.0.0", "COMPATIBLE"),
        (qcg_data["platform_service_id"], "0.8.0", "DEPRECATED"),
        (qcg_data["platform_service_id"], "0.1.0", "UNSUPPORTED"),
        ("NONEXISTENT-SERVICE", "1.0.0", "UNKNOWN_SERVICE"),
    ]

    for svc_id, version, expected_status in negotiation_tests:
        try:
            result = _http_post(
                f"{base_url}/platform/v1/negotiate",
                {"service_id": svc_id, "requested_version": version},
            )
            actual_status = result.get("status", "UNKNOWN")
            passed = actual_status == expected_status
            negotiation_results.append({
                "service_id": svc_id,
                "requested_version": version,
                "expected": expected_status,
                "actual": actual_status,
                "passed": passed,
                "response": result,
            })
            symbol = "[OK]" if passed else "[FAIL]"
            print(f"  {symbol} {svc_id} v{version}: {actual_status} (expected {expected_status})")
        except Exception as e:
            negotiation_results.append({
                "service_id": svc_id,
                "requested_version": version,
                "expected": expected_status,
                "actual": "ERROR",
                "passed": False,
                "error": str(e),
            })
            print(f"  [FAIL] {svc_id} v{version}: ERROR -- {e}")

    all_evidence["steps"].append({"step": "VERSION_NEGOTIATION", "results": negotiation_results})
    _save_evidence("version_negotiation_evidence.json", negotiation_results)

    # ------------------------------------------------------------------
    # STEP 7: Lifecycle management test
    # ------------------------------------------------------------------
    print("\n[STEP 7] Testing Lifecycle Management...")
    lifecycle_results = []

    # Use a test service for lifecycle demonstration
    test_svc_id = "TANTRA-PSR-TEST-LIFECYCLE"
    test_record = PlatformServiceRecord(
        platform_service_id=test_svc_id,
        capability_id="00000000-0000-5000-a000-000000000001",
        service_name="LIFECYCLE_TEST_SERVICE",
        version="1.0.0",
        provider="TANTRA Platform Engineering",
        owner={"team": "TANTRA Test", "contact": "test@tantra.internal"},
        runtime_type="PROCESS",
        service_classification="PLATFORM_SERVICE",
        capability_category="VERIFICATION",
        status="ACTIVE",
    )
    platform_registry.register_service(test_record)
    lifecycle_mgr.register(test_svc_id, "ACTIVE", "RUNNER", "Lifecycle test registration")

    # Cycle: ACTIVE -> DRAFT (disable) -> ACTIVE (enable) -> DEPRECATED -> RETIRED
    transitions = [
        ("disable",    "DRAFT"),
        ("enable",     "ACTIVE"),
        ("deprecate",  "DEPRECATED"),
        ("retire",     "RETIRED"),
    ]

    for action, expected_state in transitions:
        try:
            if action == "disable":
                event = lifecycle_mgr.disable(test_svc_id, actor="RUNNER")
            elif action == "enable":
                event = lifecycle_mgr.enable(test_svc_id, actor="RUNNER")
            elif action == "deprecate":
                event = lifecycle_mgr.deprecate(test_svc_id, actor="RUNNER", reason="Test deprecation")
            elif action == "retire":
                event = lifecycle_mgr.retire(test_svc_id, actor="RUNNER", reason="Test retirement")

            actual = event.new_state
            passed = actual == expected_state
            lifecycle_results.append({
                "action": action,
                "expected_state": expected_state,
                "actual_state": actual,
                "passed": passed,
                "event": event.to_dict(),
            })
            symbol = "[OK]" if passed else "[FAIL]"
            print(f"  {symbol} {action}: {event.previous_state} -> {actual}")
        except Exception as e:
            lifecycle_results.append({
                "action": action,
                "expected_state": expected_state,
                "error": str(e),
                "passed": False,
            })
            print(f"  [FAIL] {action}: ERROR -- {e}")

    # Verify lifecycle chain integrity
    chain_valid = lifecycle_mgr.verify_chain()
    lifecycle_results.append({"chain_valid": chain_valid})
    print(f"  Lifecycle evidence chain valid: {chain_valid}")

    all_evidence["steps"].append({"step": "LIFECYCLE_MANAGEMENT", "results": lifecycle_results})
    _save_evidence("lifecycle_evidence.json", {
        "lifecycle_transitions": lifecycle_results,
        "all_lifecycle_events": lifecycle_mgr.get_all_events(),
    })

    # Clean up: remove test service
    platform_registry.retire_service(test_svc_id, "Lifecycle test complete")

    # ------------------------------------------------------------------
    # STEP 8: Discovery validation (zero-config)
    # ------------------------------------------------------------------
    print("\n[STEP 8] Validating Zero-Config Discovery...")
    discovery_results = {}

    # Discover via platform API
    services = _http_get(f"{base_url}/platform/v1/services")
    discovery_results["platform_discovery"] = services
    print(f"  Platform API: {services['count']} services discovered")

    # Discover via existing capability registry
    try:
        cap_services = _http_get(f"http://127.0.0.1:{config.REGISTRY_PORT}/capabilities")
        discovery_results["capability_registry_discovery"] = cap_services
        print(f"  Capability Registry: {len(cap_services)} capabilities found")
    except Exception as e:
        discovery_results["capability_registry_discovery"] = {"error": str(e)}
        print(f"  Capability Registry: ERROR -- {e}")

    # Discover USF by name via capability registry
    try:
        usf_cap = _http_get(f"http://127.0.0.1:{config.REGISTRY_PORT}/discover/UNIVERSAL_SOLVER_FABRIC")
        discovery_results["usf_name_discovery"] = usf_cap
        print(f"  USF name discovery: OK")
    except Exception as e:
        discovery_results["usf_name_discovery"] = {"error": str(e)}
        print(f"  USF name discovery: ERROR -- {e}")

    # Discover QCG by name via capability registry
    try:
        qcg_cap = _http_get(f"http://127.0.0.1:{config.REGISTRY_PORT}/discover/QCG_TRUST_VERIFICATION")
        discovery_results["qcg_name_discovery"] = qcg_cap
        print(f"  QCG name discovery: OK")
    except Exception as e:
        discovery_results["qcg_name_discovery"] = {"error": str(e)}
        print(f"  QCG name discovery: ERROR -- {e}")

    all_evidence["steps"].append({"step": "DISCOVERY_VALIDATION", "results": discovery_results})
    _save_evidence("discovery_responses.json", discovery_results)

    # ------------------------------------------------------------------
    # STEP 9: Registration replay determinism test
    # ------------------------------------------------------------------
    print("\n[STEP 9] Validating Registration Replay Determinism...")

    # Re-create identical records and verify hashes match
    usf_record_2 = PlatformServiceRecord(
        platform_service_id=usf_data["platform_service_id"],
        capability_id=usf_data["capability_id"],
        service_name=usf_data["service_name"],
        version=usf_data["version"],
        provider=usf_data["provider"],
        owner=usf_data["owner"],
        runtime_type=usf_data["runtime_type"],
        service_classification=usf_data["service_classification"],
        capability_category=usf_data["capability_category"],
        status=usf_data["status"],
    )

    hash_1 = usf_record.deterministic_hash()
    hash_2 = usf_record_2.deterministic_hash()
    replay_deterministic = (hash_1 == hash_2)

    replay_evidence = {
        "registration_hash_1": hash_1,
        "registration_hash_2": hash_2,
        "hashes_match": replay_deterministic,
        "deterministic": replay_deterministic,
    }

    # Manifest hash replay
    usf_manifest_2 = _build_usf_manifest(manifest_data)
    manifest_hash_1 = usf_manifest.deterministic_hash()
    manifest_hash_2 = usf_manifest_2.deterministic_hash()
    manifest_replay = (manifest_hash_1 == manifest_hash_2)

    replay_evidence["manifest_hash_1"] = manifest_hash_1
    replay_evidence["manifest_hash_2"] = manifest_hash_2
    replay_evidence["manifest_hashes_match"] = manifest_replay

    print(f"  Registration hash replay: {'[OK] MATCH' if replay_deterministic else '[FAIL] MISMATCH'}")
    print(f"  Manifest hash replay:     {'[OK] MATCH' if manifest_replay else '[FAIL] MISMATCH'}")

    all_evidence["steps"].append({"step": "REPLAY_DETERMINISM", "results": replay_evidence})
    _save_evidence("replay_evidence.json", replay_evidence)

    # ------------------------------------------------------------------
    # STEP 10: Collect and save all evidence
    # ------------------------------------------------------------------
    print("\n[STEP 10] Collecting Final Evidence Packet...")

    # Registration evidence chain
    reg_evidence = evidence_recorder.get_all()
    chain_valid = evidence_recorder.verify_chain()
    _save_evidence("registration_evidence.json", {
        "evidence_chain": reg_evidence,
        "chain_length": len(reg_evidence),
        "chain_valid": chain_valid,
        "head_hash": evidence_recorder.get_head_hash(),
    })

    # Capability manifest (copy)
    _save_evidence("capability_manifest.json", manifest_data)

    # Registration metadata
    registration_metadata = {
        "run_started": run_start,
        "run_completed": datetime.now(timezone.utc).isoformat(),
        "services_registered": [
            usf_data["platform_service_id"],
            qcg_data["platform_service_id"],
        ],
        "discovery_server_url": base_url,
        "capability_registry_url": f"http://127.0.0.1:{config.REGISTRY_PORT}",
        "evidence_chain_length": len(reg_evidence),
        "evidence_chain_valid": chain_valid,
        "lifecycle_chain_valid": lifecycle_mgr.verify_chain(),
        "platform_registry_version": "1.0.0",
        "discovery_server_version": "1.0.0",
    }
    _save_evidence("registration_metadata.json", registration_metadata)

    # API samples
    api_samples = {
        "list_services": {
            "method": "GET",
            "url": f"{base_url}/platform/v1/services",
            "response": endpoint_results.get("list_services", {}).get("response"),
        },
        "get_service": {
            "method": "GET",
            "url": f"{base_url}/platform/v1/services/{usf_data['platform_service_id']}",
            "response": endpoint_results.get("get_usf", {}).get("response"),
        },
        "get_metadata": {
            "method": "GET",
            "url": f"{base_url}/platform/v1/services/{usf_data['platform_service_id']}/metadata",
            "response": endpoint_results.get("usf_metadata", {}).get("response"),
        },
        "negotiate_version": {
            "method": "POST",
            "url": f"{base_url}/platform/v1/negotiate",
            "request": {"service_id": usf_data["platform_service_id"], "requested_version": "1.0.0"},
            "response": negotiation_results[0].get("response") if negotiation_results else None,
        },
        "get_health": {
            "method": "GET",
            "url": f"{base_url}/platform/v1/services/{usf_data['platform_service_id']}/health",
            "response": endpoint_results.get("usf_health", {}).get("response"),
        },
    }
    _save_evidence("api_samples.json", api_samples)

    # Complete evidence collection
    all_evidence["run_completed"] = datetime.now(timezone.utc).isoformat()
    _save_evidence("complete_evidence_packet.json", all_evidence)

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    print("\n" + "=" * 72)
    print("  Registration Complete — Summary")
    print("=" * 72)
    print(f"  Services registered:        2 (USF + QCG)")
    print(f"  Endpoints validated:        {len(endpoint_results)}")
    print(f"  Negotiation tests:          {len(negotiation_results)}")
    print(f"  Lifecycle transitions:       {len(transitions)}")
    print(f"  Evidence chain length:      {len(reg_evidence)}")
    print(f"  Evidence chain valid:       {chain_valid}")
    print(f"  Lifecycle chain valid:      {lifecycle_mgr.verify_chain()}")
    print(f"  Registration deterministic: {replay_deterministic}")
    print(f"  Manifest deterministic:     {manifest_replay}")
    print(f"  Evidence directory:         {os.path.abspath(EVIDENCE_DIR)}")
    print("=" * 72)

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------
    print("\n[CLEANUP] Stopping servers...")
    discovery_server.stop()
    cap_server.stop()
    print("Done.")

    return all_evidence


if __name__ == "__main__":
    run()
