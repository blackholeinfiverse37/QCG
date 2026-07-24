"""
platform_service_registry.py — Canonical TANTRA Platform Service Registration

Provides the full Platform Service registration layer on top of the existing
capability_registry.py infrastructure.  Every registration, lifecycle event,
and version negotiation produces replay-safe, deterministic evidence.

RESPONSIBILITY BOUNDARY
-----------------------
PlatformServiceRegistry OWNS:
    - Platform Service ID management
    - Capability manifest storage & publication
    - Version negotiation
    - Registration evidence generation
    - Lifecycle state tracking (delegates transitions to LifecycleManager)

PlatformServiceRegistry does NOT OWN:
    - Solver algorithm execution        → Universal Solver Fabric
    - Contract validation / execution   → RuntimeCore
    - Replay detection                  → CanonicalReplayAuthority
    - Governance policy                 → GovernanceLayer
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PLATFORM_REGISTRY_VERSION = "1.0.0"

VALID_STATUSES = {"DRAFT", "ACTIVE", "DEPRECATED", "RETIRED"}
VALID_RUNTIME_TYPES = {"PROCESS", "CONTAINER", "SERVERLESS", "EMBEDDED", "HYBRID"}
VALID_SERVICE_CLASSIFICATIONS = {"PLATFORM_SERVICE", "DOMAIN_SERVICE", "INFRASTRUCTURE_SERVICE"}
VALID_CAPABILITY_CATEGORIES = {
    "OPTIMIZATION", "VERIFICATION", "CONSENSUS",
    "EXECUTION", "OBSERVABILITY", "GOVERNANCE",
}
VALID_EXECUTION_MODES = {"SYNCHRONOUS", "ASYNCHRONOUS", "STREAMING", "BATCH"}

COMPATIBLE = "COMPATIBLE"
DEPRECATED_COMPAT = "DEPRECATED"
UNSUPPORTED = "UNSUPPORTED"


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class PlatformServiceRecord:
    """
    Canonical Platform Service registration record.

    Every field is deterministic and replay-safe.  The registration_timestamp
    is set once at creation time and never mutated.
    """
    platform_service_id: str
    capability_id: str
    service_name: str
    version: str
    provider: str
    owner: Dict[str, str]
    runtime_type: str
    service_classification: str
    capability_category: str
    status: str
    registration_timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    # Additional metadata
    description: str = ""
    tags: List[str] = field(default_factory=list)
    endpoints: Dict[str, str] = field(default_factory=dict)
    dependencies: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    def deterministic_hash(self) -> str:
        """SHA-256 over the deterministic projection (excludes mutable state)."""
        seed = json.dumps({
            "platform_service_id": self.platform_service_id,
            "capability_id": self.capability_id,
            "service_name": self.service_name,
            "version": self.version,
            "provider": self.provider,
            "owner": self.owner,
            "runtime_type": self.runtime_type,
            "service_classification": self.service_classification,
            "capability_category": self.capability_category,
        }, sort_keys=True)
        return hashlib.sha256(seed.encode()).hexdigest()


@dataclass
class OperationContract:
    """Describes a single supported operation with its input/output contracts."""
    operation_name: str
    description: str
    input_contract: Dict[str, Any]
    output_contract: Dict[str, Any]
    execution_modes: List[str]
    idempotent: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class CapabilityManifest:
    """
    Canonical capability manifest published alongside a Platform Service.

    Contains everything a sovereign consumer needs to validate, negotiate,
    and invoke the capability without manual configuration.
    """
    manifest_id: str
    service_name: str
    version: str
    supported_operations: List[OperationContract]
    execution_modes: List[str]
    determinism_guarantees: Dict[str, Any]
    replay_guarantees: Dict[str, Any]
    trust_requirements: Dict[str, Any]
    evidence_guarantees: Dict[str, Any]
    runtime_dependencies: List[Dict[str, str]]
    version_compatibility: Dict[str, Any]
    security_requirements: Dict[str, Any]
    resource_requirements: Dict[str, Any]
    publication_timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict:
        d = asdict(self)
        # OperationContracts are already handled by asdict
        return d

    def deterministic_hash(self) -> str:
        """SHA-256 over the manifest content (excludes timestamps)."""
        seed = json.dumps({
            "manifest_id": self.manifest_id,
            "service_name": self.service_name,
            "version": self.version,
            "operations": [op.to_dict() for op in self.supported_operations],
            "execution_modes": self.execution_modes,
            "determinism_guarantees": self.determinism_guarantees,
            "replay_guarantees": self.replay_guarantees,
        }, sort_keys=True)
        return hashlib.sha256(seed.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Version Negotiation
# ---------------------------------------------------------------------------

def _parse_semver(version_str: str) -> tuple:
    """Parse 'major.minor.patch' into a tuple of ints."""
    parts = version_str.strip().split(".")
    if len(parts) != 3:
        raise ValueError(f"Invalid semver: {version_str}")
    return tuple(int(p) for p in parts)


class VersionNegotiator:
    """
    Handles version compatibility negotiation for Platform Services.

    Maintains a compatibility matrix and provides deterministic
    negotiation responses with graceful rejection.
    """

    def __init__(self):
        self._compatible_versions: Dict[str, List[str]] = {}
        self._deprecated_versions: Dict[str, List[str]] = {}
        self._unsupported_versions: Dict[str, List[str]] = {}

    def register_compatibility(
        self,
        service_id: str,
        compatible: List[str],
        deprecated: List[str] = None,
        unsupported: List[str] = None,
    ):
        """Register version compatibility for a service."""
        self._compatible_versions[service_id] = list(compatible)
        self._deprecated_versions[service_id] = list(deprecated or [])
        self._unsupported_versions[service_id] = list(unsupported or [])

    def negotiate(self, service_id: str, requested_version: str) -> Dict[str, Any]:
        """
        Negotiate a requested version against the compatibility matrix.

        Returns a deterministic negotiation response:
        - COMPATIBLE: version is fully supported
        - DEPRECATED: version works but consumers should migrate
        - UNSUPPORTED: version is rejected with suggested alternatives
        - UNKNOWN_SERVICE: service not found in negotiation registry
        """
        if service_id not in self._compatible_versions:
            return {
                "status": "UNKNOWN_SERVICE",
                "requested_version": requested_version,
                "service_id": service_id,
                "message": f"Service '{service_id}' is not registered for version negotiation.",
                "suggested_versions": [],
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        compatible = self._compatible_versions[service_id]
        deprecated = self._deprecated_versions.get(service_id, [])
        unsupported = self._unsupported_versions.get(service_id, [])

        if requested_version in compatible:
            return {
                "status": COMPATIBLE,
                "requested_version": requested_version,
                "service_id": service_id,
                "message": f"Version {requested_version} is fully supported.",
                "negotiated_version": requested_version,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        if requested_version in deprecated:
            latest = compatible[-1] if compatible else requested_version
            return {
                "status": DEPRECATED_COMPAT,
                "requested_version": requested_version,
                "service_id": service_id,
                "message": (
                    f"Version {requested_version} is deprecated. "
                    f"Please migrate to {latest}."
                ),
                "negotiated_version": requested_version,
                "suggested_versions": compatible,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        if requested_version in unsupported:
            return {
                "status": UNSUPPORTED,
                "requested_version": requested_version,
                "service_id": service_id,
                "message": (
                    f"Version {requested_version} is no longer supported. "
                    f"Request rejected."
                ),
                "negotiated_version": None,
                "suggested_versions": compatible,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        # Version not found in any list — graceful rejection
        return {
            "status": UNSUPPORTED,
            "requested_version": requested_version,
            "service_id": service_id,
            "message": (
                f"Version {requested_version} is not recognised. "
                f"Available versions: {compatible}"
            ),
            "negotiated_version": None,
            "suggested_versions": compatible,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def get_version_info(self, service_id: str) -> Dict[str, Any]:
        """Return the full version matrix for a service."""
        return {
            "service_id": service_id,
            "compatible": self._compatible_versions.get(service_id, []),
            "deprecated": self._deprecated_versions.get(service_id, []),
            "unsupported": self._unsupported_versions.get(service_id, []),
        }


# ---------------------------------------------------------------------------
# Registration Evidence
# ---------------------------------------------------------------------------

@dataclass
class RegistrationEvidence:
    """A single replay-safe evidence record."""
    evidence_id: str
    event_type: str
    service_id: str
    timestamp: str
    details: Dict[str, Any]
    evidence_hash: str = ""
    previous_evidence_hash: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class RegistrationEvidenceRecorder:
    """
    Generates and stores replay-safe, deterministic evidence for every
    platform registration action.

    Evidence records form a hash chain: each record's evidence_hash
    incorporates the previous record's hash, creating an append-only,
    tamper-evident log.
    """

    def __init__(self):
        self._evidence: List[RegistrationEvidence] = []
        self._lock = threading.Lock()
        self._head_hash = hashlib.sha256(b"EVIDENCE_GENESIS").hexdigest()

    def record(
        self,
        event_type: str,
        service_id: str,
        details: Dict[str, Any],
    ) -> RegistrationEvidence:
        """Record an evidence entry and chain it."""
        with self._lock:
            evidence_id = str(uuid.uuid4())
            timestamp = datetime.now(timezone.utc).isoformat()

            # Compute deterministic hash for this evidence entry
            hash_seed = json.dumps({
                "evidence_id": evidence_id,
                "event_type": event_type,
                "service_id": service_id,
                "details": details,
                "previous_hash": self._head_hash,
            }, sort_keys=True)
            evidence_hash = hashlib.sha256(hash_seed.encode()).hexdigest()

            entry = RegistrationEvidence(
                evidence_id=evidence_id,
                event_type=event_type,
                service_id=service_id,
                timestamp=timestamp,
                details=details,
                evidence_hash=evidence_hash,
                previous_evidence_hash=self._head_hash,
            )

            self._evidence.append(entry)
            self._head_hash = evidence_hash

            return entry

    def get_all(self) -> List[Dict[str, Any]]:
        """Return all evidence records."""
        with self._lock:
            return [e.to_dict() for e in self._evidence]

    def get_head_hash(self) -> str:
        """Return the current head of the evidence chain."""
        with self._lock:
            return self._head_hash

    def verify_chain(self) -> bool:
        """Verify the integrity of the evidence chain."""
        with self._lock:
            head = hashlib.sha256(b"EVIDENCE_GENESIS").hexdigest()
            for entry in self._evidence:
                if entry.previous_evidence_hash != head:
                    return False
                # Recompute hash
                hash_seed = json.dumps({
                    "evidence_id": entry.evidence_id,
                    "event_type": entry.event_type,
                    "service_id": entry.service_id,
                    "details": entry.details,
                    "previous_hash": head,
                }, sort_keys=True)
                expected = hashlib.sha256(hash_seed.encode()).hexdigest()
                if entry.evidence_hash != expected:
                    return False
                head = entry.evidence_hash
            return head == self._head_hash

    def get_chain_length(self) -> int:
        with self._lock:
            return len(self._evidence)


# ---------------------------------------------------------------------------
# Central Platform Service Registry
# ---------------------------------------------------------------------------

class PlatformServiceRegistry:
    """
    Canonical Platform Service Registry.

    Stores PlatformServiceRecords and CapabilityManifests with thread-safe
    lifecycle management.  Every mutation is recorded as evidence.

    This registry is the canonical source of truth for Platform Service
    metadata.  It delegates transport-level registration to the existing
    CapabilityRegistryClient where needed.
    """

    def __init__(self, evidence_recorder: RegistrationEvidenceRecorder = None):
        self._services: Dict[str, PlatformServiceRecord] = {}
        self._manifests: Dict[str, CapabilityManifest] = {}
        self._lock = threading.RLock()
        self.evidence = evidence_recorder or RegistrationEvidenceRecorder()
        self.negotiator = VersionNegotiator()

    # -- Registration -------------------------------------------------------

    def register_service(
        self,
        record: PlatformServiceRecord,
        manifest: CapabilityManifest = None,
    ) -> Dict[str, Any]:
        """
        Register a new Platform Service.

        Returns a registration receipt with evidence.
        """
        with self._lock:
            sid = record.platform_service_id

            if sid in self._services:
                existing = self._services[sid]
                if existing.version == record.version:
                    # Idempotent re-registration — return existing receipt
                    evidence = self.evidence.record(
                        "REGISTRATION_IDEMPOTENT",
                        sid,
                        {"message": "Service already registered with same version."},
                    )
                    return {
                        "status": "ALREADY_REGISTERED",
                        "service_id": sid,
                        "evidence": evidence.to_dict(),
                    }

            self._services[sid] = record

            if manifest:
                self._manifests[sid] = manifest

            evidence = self.evidence.record(
                "SERVICE_REGISTERED",
                sid,
                {
                    "service_name": record.service_name,
                    "version": record.version,
                    "capability_id": record.capability_id,
                    "status": record.status,
                    "registration_hash": record.deterministic_hash(),
                    "has_manifest": manifest is not None,
                },
            )

            return {
                "status": "REGISTERED",
                "service_id": sid,
                "registration_hash": record.deterministic_hash(),
                "evidence": evidence.to_dict(),
            }

    def update_service(
        self,
        service_id: str,
        updates: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Update a registered service's mutable fields."""
        with self._lock:
            if service_id not in self._services:
                return {"status": "NOT_FOUND", "service_id": service_id}

            record = self._services[service_id]
            before = record.to_dict().copy()

            for key, value in updates.items():
                if hasattr(record, key) and key not in (
                    "platform_service_id", "registration_timestamp"
                ):
                    setattr(record, key, value)

            evidence = self.evidence.record(
                "SERVICE_UPDATED",
                service_id,
                {"before": before, "after": record.to_dict()},
            )

            return {
                "status": "UPDATED",
                "service_id": service_id,
                "evidence": evidence.to_dict(),
            }

    # -- Lifecycle actions --------------------------------------------------

    def set_status(self, service_id: str, new_status: str, reason: str = "") -> Dict[str, Any]:
        """Change the lifecycle status of a service."""
        with self._lock:
            if service_id not in self._services:
                return {"status": "NOT_FOUND", "service_id": service_id}

            if new_status not in VALID_STATUSES:
                return {
                    "status": "INVALID_STATUS",
                    "service_id": service_id,
                    "message": f"Status must be one of {VALID_STATUSES}",
                }

            record = self._services[service_id]
            old_status = record.status
            record.status = new_status

            event_type = f"SERVICE_{new_status}"
            evidence = self.evidence.record(
                event_type,
                service_id,
                {
                    "previous_status": old_status,
                    "new_status": new_status,
                    "reason": reason,
                },
            )

            return {
                "status": "STATUS_CHANGED",
                "service_id": service_id,
                "previous_status": old_status,
                "new_status": new_status,
                "evidence": evidence.to_dict(),
            }

    def enable_service(self, service_id: str) -> Dict[str, Any]:
        return self.set_status(service_id, "ACTIVE", "Service enabled")

    def disable_service(self, service_id: str) -> Dict[str, Any]:
        return self.set_status(service_id, "DRAFT", "Service disabled")

    def deprecate_service(self, service_id: str, reason: str = "") -> Dict[str, Any]:
        return self.set_status(service_id, "DEPRECATED", reason or "Deprecated by operator")

    def retire_service(self, service_id: str, reason: str = "") -> Dict[str, Any]:
        return self.set_status(service_id, "RETIRED", reason or "Retired by operator")

    # -- Query interface ----------------------------------------------------

    def list_services(self) -> List[Dict[str, Any]]:
        """List all registered services."""
        with self._lock:
            return [s.to_dict() for s in self._services.values()]

    def get_service(self, service_id: str) -> Optional[Dict[str, Any]]:
        """Fetch a single service by ID."""
        with self._lock:
            record = self._services.get(service_id)
            return record.to_dict() if record else None

    def get_manifest(self, service_id: str) -> Optional[Dict[str, Any]]:
        """Fetch the capability manifest for a service."""
        with self._lock:
            manifest = self._manifests.get(service_id)
            return manifest.to_dict() if manifest else None

    def get_versions(self, service_id: str) -> Dict[str, Any]:
        """Fetch version information for a service."""
        return self.negotiator.get_version_info(service_id)

    def get_endpoints(self, service_id: str) -> Optional[Dict[str, str]]:
        """Fetch published endpoints for a service."""
        with self._lock:
            record = self._services.get(service_id)
            return dict(record.endpoints) if record else None

    def get_metadata(self, service_id: str) -> Optional[Dict[str, Any]]:
        """Fetch combined metadata (record + manifest)."""
        with self._lock:
            record = self._services.get(service_id)
            if not record:
                return None
            manifest = self._manifests.get(service_id)
            return {
                "service": record.to_dict(),
                "manifest": manifest.to_dict() if manifest else None,
                "versions": self.negotiator.get_version_info(service_id),
            }

    def negotiate_version(self, service_id: str, requested_version: str) -> Dict[str, Any]:
        """Negotiate a version for a service."""
        result = self.negotiator.negotiate(service_id, requested_version)

        self.evidence.record(
            "VERSION_NEGOTIATION",
            service_id,
            {
                "requested_version": requested_version,
                "negotiation_status": result["status"],
                "negotiated_version": result.get("negotiated_version"),
            },
        )

        return result

    def get_health(self, service_id: str) -> Dict[str, Any]:
        """Get health status for a service."""
        with self._lock:
            record = self._services.get(service_id)
            if not record:
                return {"status": "UNKNOWN", "service_id": service_id}
            return {
                "status": "UP" if record.status == "ACTIVE" else "DOWN",
                "service_id": service_id,
                "service_status": record.status,
                "version": record.version,
                "registration_timestamp": record.registration_timestamp,
            }

    def get_compatibility(self, service_id: str) -> Dict[str, Any]:
        """Get compatibility matrix for a service."""
        version_info = self.negotiator.get_version_info(service_id)
        with self._lock:
            record = self._services.get(service_id)
            if not record:
                return {"status": "UNKNOWN", "service_id": service_id}
            return {
                "service_id": service_id,
                "current_version": record.version,
                "version_matrix": version_info,
                "runtime_type": record.runtime_type,
                "capability_category": record.capability_category,
            }
