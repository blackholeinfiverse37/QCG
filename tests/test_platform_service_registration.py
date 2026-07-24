"""
tests/test_platform_service_registration.py — Comprehensive Platform Service Test Suite

Tests covering:
- Platform service registration (deterministic)
- Capability discovery (zero-config)
- Manifest validation (schema completeness)
- Endpoint validation (all published endpoints respond correctly)
- Health & readiness verification
- Version negotiation (compatible, deprecated, unsupported, graceful rejection)
- Compatibility validation
- Registration replay (re-running produces identical evidence hashes)
- Lifecycle replay (full lifecycle produces deterministic event chains)
- Evidence chain integrity verification
"""

import json
import os
import sys
import time
import threading
import urllib.request
import urllib.error
import pytest

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from platform_service_registry import (
    PlatformServiceRecord,
    PlatformServiceRegistry,
    CapabilityManifest,
    OperationContract,
    RegistrationEvidenceRecorder,
    VersionNegotiator,
    PLATFORM_REGISTRY_VERSION,
)
from platform_lifecycle_manager import (
    LifecycleManager,
    LifecycleEvent,
    VALID_TRANSITIONS,
)
from platform_service_discovery import PlatformDiscoveryServer

from capability_registry import CapabilityRegistryServer


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def evidence_recorder():
    return RegistrationEvidenceRecorder()


@pytest.fixture
def registry(evidence_recorder):
    return PlatformServiceRegistry(evidence_recorder=evidence_recorder)


@pytest.fixture
def lifecycle():
    return LifecycleManager()


@pytest.fixture
def negotiator():
    return VersionNegotiator()


def _make_record(
    service_id: str = "TEST-SVC-001",
    service_name: str = "TEST_SERVICE",
    version: str = "1.0.0",
    status: str = "ACTIVE",
) -> PlatformServiceRecord:
    return PlatformServiceRecord(
        platform_service_id=service_id,
        capability_id="aaaaaaaa-bbbb-5ccc-9ddd-eeeeeeeeeeee",
        service_name=service_name,
        version=version,
        provider="Test Provider",
        owner={"team": "Test Team", "contact": "test@test.internal"},
        runtime_type="PROCESS",
        service_classification="PLATFORM_SERVICE",
        capability_category="OPTIMIZATION",
        status=status,
        endpoints={
            "execution": "http://127.0.0.1:9999/execute",
            "health": "http://127.0.0.1:9999/health",
        },
    )


def _make_manifest() -> CapabilityManifest:
    return CapabilityManifest(
        manifest_id="TEST-MANIFEST-001",
        service_name="TEST_SERVICE",
        version="1.0.0",
        supported_operations=[
            OperationContract(
                operation_name="test_operation",
                description="A test operation",
                input_contract={"type": "object", "properties": {"x": {"type": "integer"}}},
                output_contract={"type": "object", "properties": {"y": {"type": "integer"}}},
                execution_modes=["SYNCHRONOUS"],
                idempotent=True,
            ),
        ],
        execution_modes=["SYNCHRONOUS"],
        determinism_guarantees={"deterministic_execution": True},
        replay_guarantees={"replay_safe": True},
        trust_requirements={"authentication": "TANTRA_SERVICE_IDENTITY"},
        evidence_guarantees={"evidence_per_execution": True, "evidence_chain": True},
        runtime_dependencies=[{"name": "test_dep", "version": "1.0.0", "type": "INTERNAL"}],
        version_compatibility={"compatible": ["1.0.0"], "deprecated": [], "unsupported": []},
        security_requirements={"network_policy": "INTERNAL_ONLY"},
        resource_requirements={"memory_mb_min": 256, "cpu_cores_min": 1},
    )


# ===========================================================================
# TEST 1: Platform Service Registration
# ===========================================================================

class TestPlatformRegistration:
    """Test canonical platform service registration."""

    def test_register_service_returns_registered(self, registry):
        record = _make_record()
        result = registry.register_service(record)
        assert result["status"] == "REGISTERED"
        assert result["service_id"] == "TEST-SVC-001"
        assert "registration_hash" in result
        assert "evidence" in result

    def test_register_with_manifest(self, registry):
        record = _make_record()
        manifest = _make_manifest()
        result = registry.register_service(record, manifest)
        assert result["status"] == "REGISTERED"

        # Verify manifest is stored
        fetched = registry.get_manifest("TEST-SVC-001")
        assert fetched is not None
        assert fetched["manifest_id"] == "TEST-MANIFEST-001"

    def test_idempotent_re_registration(self, registry):
        record = _make_record()
        registry.register_service(record)
        result = registry.register_service(record)
        assert result["status"] == "ALREADY_REGISTERED"

    def test_registration_evidence_generated(self, registry, evidence_recorder):
        record = _make_record()
        registry.register_service(record)
        evidence = evidence_recorder.get_all()
        assert len(evidence) >= 1
        assert evidence[0]["event_type"] == "SERVICE_REGISTERED"

    def test_registration_hash_is_deterministic(self):
        r1 = _make_record()
        r2 = _make_record()
        assert r1.deterministic_hash() == r2.deterministic_hash()


# ===========================================================================
# TEST 2: Capability Discovery
# ===========================================================================

class TestCapabilityDiscovery:
    """Test capability discovery through the registry."""

    def test_list_services_returns_all(self, registry):
        registry.register_service(_make_record("SVC-A", "SERVICE_A"))
        registry.register_service(_make_record("SVC-B", "SERVICE_B"))
        services = registry.list_services()
        assert len(services) == 2

    def test_get_service_by_id(self, registry):
        registry.register_service(_make_record("SVC-A", "SERVICE_A"))
        svc = registry.get_service("SVC-A")
        assert svc is not None
        assert svc["service_name"] == "SERVICE_A"

    def test_get_nonexistent_returns_none(self, registry):
        assert registry.get_service("DOES-NOT-EXIST") is None

    def test_get_endpoints(self, registry):
        registry.register_service(_make_record())
        endpoints = registry.get_endpoints("TEST-SVC-001")
        assert endpoints is not None
        assert "execution" in endpoints
        assert "health" in endpoints

    def test_get_metadata_includes_service_and_manifest(self, registry):
        registry.register_service(_make_record(), _make_manifest())
        metadata = registry.get_metadata("TEST-SVC-001")
        assert "service" in metadata
        assert "manifest" in metadata
        assert metadata["manifest"] is not None


# ===========================================================================
# TEST 3: Manifest Validation
# ===========================================================================

class TestManifestValidation:
    """Test capability manifest schema completeness."""

    def test_manifest_has_all_required_fields(self):
        m = _make_manifest()
        d = m.to_dict()
        required = [
            "manifest_id", "service_name", "version",
            "supported_operations", "execution_modes",
            "determinism_guarantees", "replay_guarantees",
            "trust_requirements", "evidence_guarantees",
            "runtime_dependencies", "version_compatibility",
            "security_requirements", "resource_requirements",
        ]
        for field in required:
            assert field in d, f"Missing required field: {field}"

    def test_operations_have_contracts(self):
        m = _make_manifest()
        for op in m.supported_operations:
            d = op.to_dict()
            assert "input_contract" in d
            assert "output_contract" in d
            assert "execution_modes" in d

    def test_manifest_hash_is_deterministic(self):
        m1 = _make_manifest()
        m2 = _make_manifest()
        assert m1.deterministic_hash() == m2.deterministic_hash()

    def test_static_manifest_file_valid(self):
        path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "platform_capability_manifest.json")
        with open(path) as f:
            data = json.load(f)
        assert "services" in data
        assert len(data["services"]) == 2

        for svc in data["services"]:
            assert "platform_service_id" in svc
            assert "capability_id" in svc
            assert "manifest" in svc
            manifest = svc["manifest"]
            assert "supported_operations" in manifest
            assert len(manifest["supported_operations"]) > 0


# ===========================================================================
# TEST 4: Version Negotiation
# ===========================================================================

class TestVersionNegotiation:
    """Test version compatibility negotiation."""

    def test_compatible_version(self, negotiator):
        negotiator.register_compatibility("SVC-1", ["1.0.0", "1.1.0"])
        result = negotiator.negotiate("SVC-1", "1.0.0")
        assert result["status"] == "COMPATIBLE"
        assert result["negotiated_version"] == "1.0.0"

    def test_deprecated_version(self, negotiator):
        negotiator.register_compatibility("SVC-1", ["1.0.0"], deprecated=["0.9.0"])
        result = negotiator.negotiate("SVC-1", "0.9.0")
        assert result["status"] == "DEPRECATED"
        assert result["negotiated_version"] == "0.9.0"
        assert "suggested_versions" in result

    def test_unsupported_version(self, negotiator):
        negotiator.register_compatibility("SVC-1", ["1.0.0"], unsupported=["0.1.0"])
        result = negotiator.negotiate("SVC-1", "0.1.0")
        assert result["status"] == "UNSUPPORTED"
        assert result["negotiated_version"] is None

    def test_unknown_version_graceful_rejection(self, negotiator):
        negotiator.register_compatibility("SVC-1", ["1.0.0"])
        result = negotiator.negotiate("SVC-1", "99.0.0")
        assert result["status"] == "UNSUPPORTED"
        assert "suggested_versions" in result

    def test_unknown_service(self, negotiator):
        result = negotiator.negotiate("DOES-NOT-EXIST", "1.0.0")
        assert result["status"] == "UNKNOWN_SERVICE"

    def test_negotiate_via_registry(self, registry):
        registry.register_service(_make_record())
        registry.negotiator.register_compatibility("TEST-SVC-001", ["1.0.0"], deprecated=["0.9.0"])
        result = registry.negotiate_version("TEST-SVC-001", "0.9.0")
        assert result["status"] == "DEPRECATED"


# ===========================================================================
# TEST 5: Lifecycle Management
# ===========================================================================

class TestLifecycleManagement:
    """Test capability lifecycle state machine and evidence."""

    def test_register_sets_initial_state(self, lifecycle):
        lifecycle.register("SVC-1", "ACTIVE")
        assert lifecycle.get_state("SVC-1") == "ACTIVE"

    def test_valid_transition_active_to_deprecated(self, lifecycle):
        lifecycle.register("SVC-1", "ACTIVE")
        event = lifecycle.deprecate("SVC-1")
        assert event.new_state == "DEPRECATED"
        assert lifecycle.get_state("SVC-1") == "DEPRECATED"

    def test_valid_transition_deprecated_to_retired(self, lifecycle):
        lifecycle.register("SVC-1", "ACTIVE")
        lifecycle.deprecate("SVC-1")
        event = lifecycle.retire("SVC-1")
        assert event.new_state == "RETIRED"

    def test_invalid_transition_raises(self, lifecycle):
        lifecycle.register("SVC-1", "ACTIVE")
        lifecycle.deprecate("SVC-1")
        lifecycle.retire("SVC-1")
        with pytest.raises(ValueError, match="Invalid transition"):
            lifecycle.transition("SVC-1", "ACTIVE")

    def test_disable_moves_to_draft(self, lifecycle):
        lifecycle.register("SVC-1", "ACTIVE")
        event = lifecycle.disable("SVC-1")
        assert event.new_state == "DRAFT"

    def test_enable_moves_to_active(self, lifecycle):
        lifecycle.register("SVC-1", "DRAFT")
        event = lifecycle.enable("SVC-1")
        assert event.new_state == "ACTIVE"

    def test_lifecycle_evidence_chain_valid(self, lifecycle):
        lifecycle.register("SVC-1", "ACTIVE")
        lifecycle.deprecate("SVC-1")
        lifecycle.retire("SVC-1")
        assert lifecycle.verify_chain() is True

    def test_lifecycle_events_recorded(self, lifecycle):
        lifecycle.register("SVC-1", "ACTIVE")
        lifecycle.deprecate("SVC-1")
        events = lifecycle.get_events("SVC-1")
        assert len(events) == 2  # REGISTER + DEPRECATE

    def test_lifecycle_event_has_replay_metadata(self, lifecycle):
        event = lifecycle.register("SVC-1", "ACTIVE")
        assert "replay_metadata" in event.to_dict()
        assert "chain_length" in event.replay_metadata


# ===========================================================================
# TEST 6: Evidence Chain Integrity
# ===========================================================================

class TestEvidenceChain:
    """Test registration evidence chain integrity."""

    def test_evidence_chain_valid_after_multiple_records(self, evidence_recorder):
        for i in range(10):
            evidence_recorder.record(f"EVENT_{i}", f"SVC-{i}", {"index": i})
        assert evidence_recorder.verify_chain() is True

    def test_evidence_chain_length(self, evidence_recorder):
        evidence_recorder.record("A", "SVC-1", {})
        evidence_recorder.record("B", "SVC-1", {})
        assert evidence_recorder.get_chain_length() == 2

    def test_evidence_records_have_hash_chain(self, evidence_recorder):
        e1 = evidence_recorder.record("A", "SVC-1", {})
        e2 = evidence_recorder.record("B", "SVC-1", {})
        assert e2.previous_evidence_hash == e1.evidence_hash

    def test_evidence_head_hash_advances(self, evidence_recorder):
        initial = evidence_recorder.get_head_hash()
        evidence_recorder.record("A", "SVC-1", {})
        assert evidence_recorder.get_head_hash() != initial


# ===========================================================================
# TEST 7: Registration Replay Determinism
# ===========================================================================

class TestRegistrationReplay:
    """Test that registration is deterministic and replay-safe."""

    def test_record_hash_deterministic(self):
        r1 = _make_record()
        r2 = _make_record()
        assert r1.deterministic_hash() == r2.deterministic_hash()

    def test_different_versions_different_hash(self):
        r1 = _make_record(version="1.0.0")
        r2 = _make_record(version="2.0.0")
        assert r1.deterministic_hash() != r2.deterministic_hash()

    def test_manifest_hash_deterministic(self):
        m1 = _make_manifest()
        m2 = _make_manifest()
        assert m1.deterministic_hash() == m2.deterministic_hash()


# ===========================================================================
# TEST 8: Health & Readiness
# ===========================================================================

class TestHealthReadiness:
    """Test health and readiness reporting."""

    def test_health_for_active_service(self, registry):
        registry.register_service(_make_record(status="ACTIVE"))
        health = registry.get_health("TEST-SVC-001")
        assert health["status"] == "UP"

    def test_health_for_deprecated_service(self, registry):
        record = _make_record(status="DEPRECATED")
        registry.register_service(record)
        health = registry.get_health("TEST-SVC-001")
        assert health["status"] == "DOWN"

    def test_health_for_nonexistent_service(self, registry):
        health = registry.get_health("DOES-NOT-EXIST")
        assert health["status"] == "UNKNOWN"


# ===========================================================================
# TEST 9: Compatibility Validation
# ===========================================================================

class TestCompatibility:
    """Test compatibility matrix reporting."""

    def test_compatibility_includes_version_matrix(self, registry):
        registry.register_service(_make_record())
        registry.negotiator.register_compatibility(
            "TEST-SVC-001", ["1.0.0"], deprecated=["0.9.0"], unsupported=["0.1.0"]
        )
        compat = registry.get_compatibility("TEST-SVC-001")
        assert "version_matrix" in compat
        assert compat["current_version"] == "1.0.0"
        assert "1.0.0" in compat["version_matrix"]["compatible"]
        assert "0.9.0" in compat["version_matrix"]["deprecated"]
        assert "0.1.0" in compat["version_matrix"]["unsupported"]


# ===========================================================================
# TEST 10: Discovery Server (HTTP Integration)
# ===========================================================================

class TestDiscoveryServerHTTP:
    """Integration tests for the HTTP discovery server."""

    @pytest.fixture(autouse=True)
    def setup_server(self):
        """Start and stop the discovery server for each test."""
        self.evidence_recorder = RegistrationEvidenceRecorder()
        self.registry = PlatformServiceRegistry(evidence_recorder=self.evidence_recorder)
        self.lifecycle = LifecycleManager()

        # Register a test service
        self.registry.register_service(_make_record(), _make_manifest())
        self.registry.negotiator.register_compatibility(
            "TEST-SVC-001", ["1.0.0"], deprecated=["0.9.0"]
        )

        self.server = PlatformDiscoveryServer(
            host="127.0.0.1",
            port=9011,  # Use different port to avoid conflicts
            registry=self.registry,
            lifecycle=self.lifecycle,
        )
        self.server.start()
        time.sleep(0.2)
        self.base = "http://127.0.0.1:9011"

        yield

        self.server.stop()

    def _get(self, path: str):
        url = f"{self.base}{path}"
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _post(self, path: str, data: dict):
        url = f"{self.base}{path}"
        payload = json.dumps(data).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def test_list_services_endpoint(self):
        resp = self._get("/platform/v1/services")
        assert "services" in resp
        assert resp["count"] >= 1

    def test_get_service_endpoint(self):
        resp = self._get("/platform/v1/services/TEST-SVC-001")
        assert resp["service_name"] == "TEST_SERVICE"

    def test_get_service_not_found(self):
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            self._get("/platform/v1/services/NONEXISTENT")
        assert exc_info.value.code == 404

    def test_get_versions_endpoint(self):
        resp = self._get("/platform/v1/services/TEST-SVC-001/versions")
        assert "compatible" in resp

    def test_get_metadata_endpoint(self):
        resp = self._get("/platform/v1/services/TEST-SVC-001/metadata")
        assert "service" in resp
        assert "manifest" in resp

    def test_get_contracts_endpoint(self):
        resp = self._get("/platform/v1/services/TEST-SVC-001/contracts")
        assert "contracts" in resp
        assert resp["count"] >= 1

    def test_get_endpoints_endpoint(self):
        resp = self._get("/platform/v1/services/TEST-SVC-001/endpoints")
        assert "endpoints" in resp

    def test_get_health_endpoint(self):
        resp = self._get("/platform/v1/services/TEST-SVC-001/health")
        assert resp["status"] == "UP"

    def test_get_compatibility_endpoint(self):
        resp = self._get("/platform/v1/services/TEST-SVC-001/compatibility")
        assert "version_matrix" in resp

    def test_server_health_endpoint(self):
        resp = self._get("/platform/v1/health")
        assert resp["status"] == "UP"
        assert "uptime_seconds" in resp

    def test_server_readiness_endpoint(self):
        resp = self._get("/platform/v1/readiness")
        assert resp["ready"] is True
        assert resp["services_registered"] >= 1

    def test_server_evidence_endpoint(self):
        resp = self._get("/platform/v1/evidence")
        assert "evidence" in resp
        assert resp["chain_valid"] is True

    def test_server_version_endpoint(self):
        resp = self._get("/platform/v1/version")
        assert "discovery_server_version" in resp
        assert resp["api_version"] == "v1"

    def test_negotiate_endpoint(self):
        resp = self._post(
            "/platform/v1/negotiate",
            {"service_id": "TEST-SVC-001", "requested_version": "1.0.0"},
        )
        assert resp["status"] == "COMPATIBLE"

    def test_negotiate_deprecated(self):
        resp = self._post(
            "/platform/v1/negotiate",
            {"service_id": "TEST-SVC-001", "requested_version": "0.9.0"},
        )
        assert resp["status"] == "DEPRECATED"

    def test_metrics_endpoint(self):
        url = f"{self.base}/platform/v1/metrics"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=5) as resp:
            text = resp.read().decode("utf-8")
        assert "tantra_platform_uptime_seconds" in text
        assert "tantra_platform_requests_total" in text

    def test_404_for_unknown_path(self):
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            self._get("/platform/v1/nonexistent")
        assert exc_info.value.code == 404
