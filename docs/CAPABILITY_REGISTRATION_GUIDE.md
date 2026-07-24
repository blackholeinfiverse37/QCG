# Capability Registration Guide

## Overview

This guide explains how to register a new capability as a TANTRA Platform Service. The registration process publishes the capability into the canonical registry, making it discoverable by any sovereign system without manual configuration.

---

## Prerequisites

1. The capability must already exist as working runtime code
2. The capability must have clearly defined inputs, outputs, and authority boundaries
3. The existing `CapabilityRegistryServer` must be running (port 9000 by default)

---

## Step 1: Define the Platform Service Record

Create a `PlatformServiceRecord` with all required fields:

```python
from platform_service_registry import PlatformServiceRecord

record = PlatformServiceRecord(
    platform_service_id="TANTRA-PSR-YOUR-001",   # Unique platform service ID
    capability_id="<UUID-5>",                      # Globally unique capability ID
    service_name="YOUR_SERVICE_NAME",              # SCREAMING_SNAKE_CASE
    version="1.0.0",                               # Semantic version
    provider="Your Team Name",                     # Provider organisation
    owner={
        "team": "Your Team",
        "contact": "your-team@tantra.internal",
    },
    runtime_type="PROCESS",                        # PROCESS | CONTAINER | SERVERLESS | EMBEDDED | HYBRID
    service_classification="PLATFORM_SERVICE",     # PLATFORM_SERVICE | DOMAIN_SERVICE | INFRASTRUCTURE_SERVICE
    capability_category="OPTIMIZATION",            # OPTIMIZATION | VERIFICATION | CONSENSUS | EXECUTION | OBSERVABILITY | GOVERNANCE
    status="ACTIVE",                               # DRAFT | ACTIVE | DEPRECATED | RETIRED
    description="Human-readable description of your capability.",
    tags=["relevant", "tags"],
    endpoints={
        "execution": "http://host:port/execute",
        "health": "http://host:port/health",
    },
)
```

---

## Step 2: Define the Capability Manifest

Create a `CapabilityManifest` describing all supported operations:

```python
from platform_service_registry import CapabilityManifest, OperationContract

manifest = CapabilityManifest(
    manifest_id="YOUR-MANIFEST-001",
    service_name="YOUR_SERVICE_NAME",
    version="1.0.0",
    supported_operations=[
        OperationContract(
            operation_name="your_operation",
            description="What this operation does.",
            input_contract={
                "type": "object",
                "required": ["field_1"],
                "properties": {
                    "field_1": {"type": "string"},
                },
            },
            output_contract={
                "type": "object",
                "properties": {
                    "result": {"type": "object"},
                },
            },
            execution_modes=["SYNCHRONOUS"],
            idempotent=True,
        ),
    ],
    execution_modes=["SYNCHRONOUS"],
    determinism_guarantees={"deterministic_execution": True},
    replay_guarantees={"replay_safe": True},
    trust_requirements={"authentication": "TANTRA_SERVICE_IDENTITY"},
    evidence_guarantees={"evidence_per_execution": True, "evidence_chain": True},
    runtime_dependencies=[],
    version_compatibility={"compatible": ["1.0.0"], "deprecated": [], "unsupported": []},
    security_requirements={"network_policy": "INTERNAL_ONLY"},
    resource_requirements={"memory_mb_min": 256, "cpu_cores_min": 1},
)
```

---

## Step 3: Register the Service

```python
from platform_service_registry import PlatformServiceRegistry, RegistrationEvidenceRecorder

evidence = RegistrationEvidenceRecorder()
registry = PlatformServiceRegistry(evidence_recorder=evidence)

result = registry.register_service(record, manifest)
print(result)
# {'status': 'REGISTERED', 'service_id': '...', 'registration_hash': '...', 'evidence': {...}}
```

---

## Step 4: Register Version Compatibility

```python
registry.negotiator.register_compatibility(
    "TANTRA-PSR-YOUR-001",
    compatible=["1.0.0"],
    deprecated=["0.9.0"],
    unsupported=["0.1.0"],
)
```

---

## Step 5: Register in Lifecycle Manager

```python
from platform_lifecycle_manager import LifecycleManager

lifecycle = LifecycleManager()
lifecycle.register("TANTRA-PSR-YOUR-001", "ACTIVE", "YOUR_TEAM", "Initial registration")
```

---

## Step 6: Publish to Existing Capability Registry

```python
from capability_registry import CapabilityRegistryClient

client = CapabilityRegistryClient("http://127.0.0.1:9000")
client.register({
    "capability_id": "<UUID-5>",
    "capability_name": "YOUR_SERVICE_NAME",
    "owner": {"team": "Your Team", "contact": "your-team@tantra.internal"},
    "version": "1.0.0",
    "status": "ACTIVE",
    "scope": "SYSTEM",
    "dependencies": [],
    "attachment_rules": {
        "attachment_type": "api_linked",
        "protocol": "http_rest",
        "endpoint": "http://host:port/platform/v1/services/TANTRA-PSR-YOUR-001",
    },
    "authority_limits": {
        "owns": ["your", "owned", "responsibilities"],
        "does_not_own": ["things", "you", "delegate"],
    },
    "inputs": [],
    "outputs": [],
    "consumers": [],
    "documentation_reference": {"primary": "docs/YOUR_DOC.md"},
})
```

---

## Step 7: Verify Registration

```bash
# Check via platform discovery API
curl http://127.0.0.1:9010/platform/v1/services/TANTRA-PSR-YOUR-001

# Check via capability registry
curl http://127.0.0.1:9000/discover/YOUR_SERVICE_NAME

# Check health
curl http://127.0.0.1:9010/platform/v1/services/TANTRA-PSR-YOUR-001/health
```

---

## Registration Evidence

Every registration generates a `RegistrationEvidence` record chained via SHA-256:

```json
{
  "evidence_id": "uuid",
  "event_type": "SERVICE_REGISTERED",
  "service_id": "TANTRA-PSR-YOUR-001",
  "timestamp": "2026-07-24T08:00:00Z",
  "details": {
    "service_name": "YOUR_SERVICE_NAME",
    "version": "1.0.0",
    "registration_hash": "sha256..."
  },
  "evidence_hash": "sha256...",
  "previous_evidence_hash": "sha256..."
}
```
