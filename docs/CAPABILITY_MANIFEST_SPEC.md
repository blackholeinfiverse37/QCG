# Capability Manifest Specification

## Overview

The capability manifest is the canonical contract that defines everything a sovereign consumer needs to discover, validate, negotiate, and invoke a TANTRA Platform Service capability.

---

## Schema

### Top-Level Structure

```json
{
  "manifest_version": "1.0.0",
  "publication_timestamp": "ISO-8601",
  "publisher": "string",
  "services": [ <PlatformServiceEntry>, ... ]
}
```

### Platform Service Entry

| Field | Type | Required | Description |
|---|---|---|---|
| `platform_service_id` | string | Yes | Unique platform service identifier (e.g., `TANTRA-PSR-USF-001`) |
| `capability_id` | string (UUID-5) | Yes | Globally unique capability identifier |
| `service_name` | string | Yes | `SCREAMING_SNAKE_CASE` name |
| `version` | string (semver) | Yes | Semantic version |
| `provider` | string | Yes | Provider organisation |
| `owner` | object | Yes | `{team: string, contact: string}` |
| `runtime_type` | enum | Yes | `PROCESS` \| `CONTAINER` \| `SERVERLESS` \| `EMBEDDED` \| `HYBRID` |
| `service_classification` | enum | Yes | `PLATFORM_SERVICE` \| `DOMAIN_SERVICE` \| `INFRASTRUCTURE_SERVICE` |
| `capability_category` | enum | Yes | `OPTIMIZATION` \| `VERIFICATION` \| `CONSENSUS` \| `EXECUTION` \| `OBSERVABILITY` \| `GOVERNANCE` |
| `status` | enum | Yes | `DRAFT` \| `ACTIVE` \| `DEPRECATED` \| `RETIRED` |
| `description` | string | No | Human-readable description |
| `tags` | string[] | No | Discovery tags |
| `endpoints` | object | No | Map of endpoint names to URLs |
| `manifest` | ManifestObject | Yes | Capability manifest details |

### Manifest Object

| Field | Type | Required | Description |
|---|---|---|---|
| `manifest_id` | string | Yes | Unique manifest identifier |
| `supported_operations` | OperationContract[] | Yes | List of supported operations |
| `execution_modes` | string[] | Yes | `SYNCHRONOUS`, `ASYNCHRONOUS`, `STREAMING`, `BATCH` |
| `determinism_guarantees` | object | Yes | Determinism properties |
| `replay_guarantees` | object | Yes | Replay safety properties |
| `trust_requirements` | object | Yes | Authentication and authorization requirements |
| `evidence_guarantees` | object | Yes | Evidence generation properties |
| `runtime_dependencies` | Dependency[] | Yes | Required runtime components |
| `version_compatibility` | VersionMatrix | Yes | Compatible/deprecated/unsupported versions |
| `security_requirements` | object | Yes | Security and data classification |
| `resource_requirements` | object | Yes | Minimum resource requirements |

### Operation Contract

| Field | Type | Required | Description |
|---|---|---|---|
| `operation_name` | string | Yes | Unique operation identifier |
| `description` | string | Yes | What this operation does |
| `input_contract` | JSON Schema | Yes | Input parameter schema |
| `output_contract` | JSON Schema | Yes | Output parameter schema |
| `execution_modes` | string[] | Yes | Supported execution modes |
| `idempotent` | boolean | No | Whether repeated calls with same input produce same output |

### Determinism Guarantees

```json
{
  "deterministic_execution": true,
  "deterministic_selection": true,
  "deterministic_evidence": true,
  "note": "Human-readable explanation"
}
```

### Replay Guarantees

```json
{
  "replay_safe": true,
  "replay_authority": "CanonicalReplayAuthority",
  "replay_fields": ["trace_id", "replay_id", "provenance"],
  "note": "Human-readable explanation"
}
```

### Version Compatibility Matrix

```json
{
  "compatible": ["1.0.0", "1.1.0"],
  "deprecated": ["0.9.0"],
  "unsupported": ["0.1.0"],
  "minimum_consumer_version": "1.0.0"
}
```

---

## Published Manifests

The canonical manifest file is located at:
- [`platform_capability_manifest.json`](../platform_capability_manifest.json)

It contains manifests for:
1. **Universal Solver Fabric** (`TANTRA-PSR-USF-001`) — 3 operations
2. **QCG Trust Verification** (`TANTRA-PSR-QCG-001`) — 4 operations
