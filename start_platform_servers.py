"""
start_platform_servers.py — Script to keep platform servers running for manual testing.
"""

import time
import threading
import sys
import os
import json

from capability_registry import CapabilityRegistryServer, CapabilityRegistryClient
from platform_service_registry import PlatformServiceRegistry, PlatformServiceRecord, CapabilityManifest, RegistrationEvidenceRecorder, OperationContract
from platform_lifecycle_manager import LifecycleManager
from platform_service_discovery import PlatformDiscoveryServer
import config

def _load_manifest_json():
    manifest_path = os.path.join(os.path.dirname(__file__), "platform_capability_manifest.json")
    with open(manifest_path) as f:
        return json.load(f)

def _build_usf_manifest(manifest_data):
    usf = manifest_data["services"][0]["manifest"]
    ops = [OperationContract(
        operation_name=op["operation_name"],
        description=op["description"],
        input_contract=op["input_contract"],
        output_contract=op["output_contract"],
        execution_modes=op["execution_modes"],
        idempotent=op.get("idempotent", False),
    ) for op in usf["supported_operations"]]
    return CapabilityManifest(
        manifest_id=usf["manifest_id"],
        service_name="UNIVERSAL_SOLVER_FABRIC",
        version="1.0.0",
        supported_operations=ops,
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

def _build_qcg_manifest(manifest_data):
    qcg = manifest_data["services"][1]["manifest"]
    ops = [OperationContract(
        operation_name=op["operation_name"],
        description=op["description"],
        input_contract=op["input_contract"],
        output_contract=op["output_contract"],
        execution_modes=op["execution_modes"],
        idempotent=op.get("idempotent", False),
    ) for op in qcg["supported_operations"]]
    return CapabilityManifest(
        manifest_id=qcg["manifest_id"],
        service_name="QCG_TRUST_VERIFICATION",
        version="1.0.0",
        supported_operations=ops,
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

def main():
    print("Starting Capability Registry Server (Port 9000)...")
    cap_server = CapabilityRegistryServer("127.0.0.1", config.REGISTRY_PORT)
    cap_server.start()
    time.sleep(0.5)

    print("Starting Platform Discovery Server (Port 9010)...")
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
    time.sleep(0.5)

    print("Registering capabilities...")
    manifest_data = _load_manifest_json()

    # USF
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
        status=usf_data["status"]
    )
    platform_registry.register_service(usf_record, _build_usf_manifest(manifest_data))
    
    # QCG
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
        status=qcg_data["status"]
    )
    platform_registry.register_service(qcg_record, _build_qcg_manifest(manifest_data))

    print("\nServers are running! Press Ctrl+C to exit.")
    print("--------------------------------------------------")
    print("Platform Discovery API:")
    print("  List Services:    http://127.0.0.1:9010/platform/v1/services")
    print("  Server Health:    http://127.0.0.1:9010/platform/v1/health")
    print("  Server Metrics:   http://127.0.0.1:9010/platform/v1/metrics")
    print("  Evidence Chain:   http://127.0.0.1:9010/platform/v1/evidence")
    print("")
    print("Legacy Capability Registry API:")
    print("  List Legacy:      http://127.0.0.1:9000/capabilities")
    print("--------------------------------------------------")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping servers...")
        discovery_server.stop()
        cap_server.stop()
        print("Done.")

if __name__ == "__main__":
    main()
