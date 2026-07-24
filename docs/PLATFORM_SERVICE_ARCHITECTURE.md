# Platform Service Architecture

## Overview

The TANTRA Platform Service layer exposes the Universal Solver Fabric (USF) and QCG Trust Verification as canonical, discoverable capabilities that any sovereign system can consume without manual configuration.

This architecture adds a **registration, discovery, and lifecycle** layer on top of the existing runtime infrastructure. **No execution logic, solver algorithms, or orchestration is modified.**

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                    Sovereign Consumer System                     │
│  (Any TANTRA component that needs optimization or verification) │
└───────────┬─────────────────────────────────────┬───────────────┘
            │ Discovery (HTTP GET)                │ Negotiation (HTTP POST)
            ▼                                     ▼
┌─────────────────────────────────────────────────────────────────┐
│              Platform Discovery Server (:9010)                   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  GET  /platform/v1/services                              │   │
│  │  GET  /platform/v1/services/{id}                         │   │
│  │  GET  /platform/v1/services/{id}/metadata                │   │
│  │  GET  /platform/v1/services/{id}/contracts               │   │
│  │  GET  /platform/v1/services/{id}/endpoints               │   │
│  │  GET  /platform/v1/services/{id}/health                  │   │
│  │  GET  /platform/v1/services/{id}/compatibility           │   │
│  │  GET  /platform/v1/services/{id}/versions                │   │
│  │  POST /platform/v1/negotiate                             │   │
│  │  GET  /platform/v1/health | readiness | metrics | ...    │   │
│  └──────────────────────────────────────────────────────────┘   │
└───────────┬─────────────────────────────────────┬───────────────┘
            │                                     │
            ▼                                     ▼
┌───────────────────────┐         ┌───────────────────────────────┐
│  PlatformService      │         │  LifecycleManager              │
│  Registry             │         │  ─────────────────             │
│  ─────────────────    │         │  DRAFT → ACTIVE → DEPRECATED  │
│  Service Records      │         │                  → RETIRED     │
│  Capability Manifests │         │  Evidence Hash Chain           │
│  Version Negotiator   │         └───────────────────────────────┘
│  Evidence Recorder    │
└───────────┬───────────┘
            │ Publishes into
            ▼
┌───────────────────────────────────────────────┐
│  Capability Registry Server (:9000)           │
│  (Existing infrastructure — NOT modified)     │
│  ─────────────────────────────────────        │
│  GET  /capabilities                           │
│  GET  /capabilities/{id}                      │
│  GET  /discover/{name}                        │
│  POST /register                               │
└───────────┬───────────────────────┬───────────┘
            │                       │
            ▼                       ▼
┌───────────────────┐   ┌───────────────────────┐
│  Universal Solver  │   │  QCG Trust             │
│  Fabric            │   │  Verification          │
│  ────────────────  │   │  ──────────────────    │
│  SolverRegistry    │   │  ReplayAuthority       │
│  SelectionEngine   │   │  RuntimeCore           │
│  ExecutionAdapter  │   │  ProducerVerification  │
│  (unchanged)       │   │  ConsensusEngine       │
│                    │   │  EvidenceLedger         │
│                    │   │  (unchanged)            │
└────────────────────┘   └────────────────────────┘
```

---

## Component Responsibilities

| Component | Owns | Does NOT Own |
|---|---|---|
| `PlatformServiceRegistry` | Service record storage, manifest storage, version negotiation, evidence recording | Solver execution, contract validation, replay detection |
| `PlatformDiscoveryServer` | HTTP endpoint publication, REST API, metrics | Service registration logic, lifecycle management |
| `LifecycleManager` | State transitions, lifecycle evidence chain | Service records, manifests, version negotiation |
| `RegistrationEvidenceRecorder` | Evidence hash chain, tamper detection | Execution evidence (owned by EvidenceLedger) |
| `VersionNegotiator` | Compatibility matrix, negotiation responses | Service metadata, registration |

---

## Data Flow: Service Registration

```
1. Registration Runner starts
2. CapabilityRegistryServer starts on :9000
3. PlatformServiceRegistry initialised (in-memory)
4. PlatformDiscoveryServer starts on :9010
5. USF PlatformServiceRecord created from manifest JSON
6. USF CapabilityManifest created from manifest JSON
7. PlatformServiceRegistry.register_service(record, manifest)
   → Evidence recorded: SERVICE_REGISTERED
   → Version compatibility registered
   → LifecycleManager.register() called
8. CapabilityRegistryClient.register() publishes to existing registry
9. Steps 5-8 repeated for QCG
10. Discovery server now serves both services via REST
```

---

## Data Flow: Service Discovery (Zero-Config)

```
1. Consumer sends GET /platform/v1/services
2. Discovery server returns list of registered services
3. Consumer picks a service and sends GET /platform/v1/services/{id}/metadata
4. Consumer receives full metadata + manifest + version info
5. Consumer sends POST /platform/v1/negotiate with requested_version
6. Discovery server returns COMPATIBLE / DEPRECATED / UNSUPPORTED
7. If COMPATIBLE, consumer reads endpoints from metadata
8. Consumer invokes the capability directly (existing runtime endpoints)
```

---

## Evidence Model

All evidence uses SHA-256 hash chains:

```
GENESIS → Evidence₁ → Evidence₂ → ... → Evidenceₙ

Each Evidenceᵢ contains:
  - evidence_id (UUID)
  - event_type (e.g., SERVICE_REGISTERED, VERSION_NEGOTIATION)
  - service_id
  - timestamp
  - details (event-specific data)
  - evidence_hash = SHA256(evidence_id + event_type + details + previous_hash)
  - previous_evidence_hash
```

The chain is append-only and tamper-evident. `verify_chain()` recomputes every hash from genesis and validates the sequence.

---

## File Inventory

| File | Purpose |
|---|---|
| `platform_service_registry.py` | Core registration module (records, manifests, negotiation, evidence) |
| `platform_service_discovery.py` | HTTP discovery server |
| `platform_lifecycle_manager.py` | Lifecycle state machine with evidence |
| `platform_capability_manifest.json` | Canonical manifest for USF + QCG |
| `platform_service_registration_runner.py` | End-to-end registration + evidence runner |
| `tests/test_platform_service_registration.py` | Comprehensive test suite |
