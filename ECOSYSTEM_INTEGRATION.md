# Ecosystem Integration Document

This document outlines the federation of the Quantum Communication Gateway (QCG) into the TANTRA Distributed Ecosystem.

## 1. Integration Scope
The QCG acts as a sovereign node that produces and verifies deterministic execution contracts derived from probabilistic quantum state output. It integrates with six primary external ecosystem services to form a complete production topology.

## 2. Integrated Services & Status

| Service Role | Owner | Interaction Description | Status |
|---|---|---|---|
| **Identity / Analysis** | KESHAV | Root-cause analysis, severity classification, trace continuity via live `/analyze` API. | **Validated (Live)** |
| **Runtime** | Dhiraj | Validate live runtime execution through actual endpoints. | Implemented / Pending Live URL |
| **Quantum Capability** | Pritesh | Validate computation execution against live quantum interfaces. | **Validated (Live)** |
| **Governance** | Raj | Verify governance approval and policy enforcement via APIs. | Implemented / Pending Live URL |
| **Lineage** | Pravah | Verify trace continuity and provenance propagation. | Implemented / Pending Live URL |
| **Observability** | InsightFlow | Publish and verify operational telemetry/metrics. | Implemented / Pending Live URL |

### Status Legend
- **Validated (Live)**: Integration tested against live production API with real request/response evidence.
- **Implemented / Pending Live URL**: Integration code written and tested locally. Awaiting live API URL from service owner.

## 3. KESHAV Live Integration (Validated)

**Live API**: `https://keshav-cia7.onrender.com`

### Endpoints Used

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `POST` | `/analyze` | Submit QCG contracts for root-cause analysis and severity classification |
| `GET` | `/health` | Liveness/readiness verification |
| `GET` | `/metrics/json` | Operational metrics retrieval |

### Request Schema (POST /analyze)
```json
{
  "trace_id": "qcg-trace-001",
  "execution_id": "exec-qcg-001",
  "tasks": [
    { "task_id": "QCG_VERIFY", "depends_on": [] }
  ],
  "constraint_results": [
    { "task_id": "QCG_VERIFY", "is_valid": true, "unsatisfied_dependencies": [] }
  ],
  "propagation_results": [
    { "task_id": "QCG_VERIFY", "affected_tasks": [], "impact_score": 0 }
  ]
}
```

### Response Schema (200 OK)
```json
{
  "trace_id": "qcg-trace-001",
  "execution_id": "exec-qcg-001",
  "root_cause": null,
  "resolution_signal": null,
  "impact_score": 0,
  "severity": "LOW",
  "timestamp": "2026-07-15T11:09:42Z"
}
```

### Integration Point in QCG
- **Client**: `keshav_live_client.py` — production HTTP client with structured logging
- **Pipeline**: `integration_harness.py` — KESHAV analysis runs after replay validation, before trust verification
- **Config**: `QCG_KESHAV_API_URL`, `QCG_KESHAV_TIMEOUT_SECONDS`, `QCG_KESHAV_ENABLED` in `.env`
- **Evidence**: `review_packets/evidence/keshav_live_integration.json`

### Validated Scenarios
1. Health check — Service responds `{"status": "OK", "service": "KESHAV"}`
2. Metrics retrieval — Returns request count, latency percentiles, severity distribution
7. Valid contract analysis — Returns severity `LOW`, no root cause
4. Constraint failure analysis — Correctly identifies root cause task and resolution signal
5. Trace continuity — `trace_id` preserved end-to-end through analysis

## 4. Pritesh Quantum Capability Live Integration (Validated)

**Live API**: `http://localhost:8080/verify` (Simulated local endpoint receiving remote payloads)

### Endpoints Used
| Method | Endpoint | Purpose |
|--------|----------|---------|
| `POST` | `/verify` | Validate computation execution through live quantum interfaces |

### Request Schema (POST /verify)
```json
{
    "contract": { "operation": "quantum_simulation", "parameters": { "qubits": 4, "depth": 2 } },
    "producer_public_key": "YOUR_KEY"
}
```

### Response Schema (200 OK)
```json
{
  "trace_id": "8c825bee-9c9c-4904-8169-8689f619cee4",
  "parent_trace_id": null,
  "flow_status": "COMPLETED",
  "stages": { ... },
  "trace_continuity": { ... }
}
```

### Integration Point in QCG
- **Client**: `pritesh_live_client.py` — production HTTP client with structured logging
- **Adapter**: `web_server.py` — Adapts the raw external quantum capability payload into a strict `ComputationExecutionContract`, signing it with a dynamic NodeSigner, before executing the standard TANTRA harness.
- **Evidence**: `review_packets/evidence/pritesh_evidence.json`

## 5. Interaction Mechanics

All integrations are facilitated by `integration_harness.py`, which implements standard TANTRA network interfaces:
- **Capability Discovery:** Emits JSON metadata matching `capability_registry_schema.json`.
- **Identity Trust:** Utilizes `NodeSigner` and PKI to authenticate outbound and inbound requests.
- **KESHAV Analysis:** Live HTTP calls to KESHAV `/analyze` for root-cause and severity classification.
- **Lineage Tracing:** Attaches a deterministic `trace_id` (UUIDv5) to all payloads, propagating it downstream.
- **Governance Halts:** Governance policy enforcement in strict mode halts execution on any violation.

## 5. Configuration

Set the following environment variables (or in `.env`):
```env
# KESHAV (Live — Validated)
QCG_KESHAV_API_URL=https://keshav-cia7.onrender.com
QCG_KESHAV_TIMEOUT_SECONDS=15
QCG_KESHAV_ENABLED=true

# Other services (Pending Live URLs)
# QCG_RUNTIME_URL=https://api.runtime.tantra.local
# QCG_QUANTUM_URL=https://api.quantum.tantra.local
# QCG_GOVERNANCE_URL=https://api.governance.tantra.local
# QCG_LINEAGE_URL=https://api.lineage.tantra.local
# QCG_TELEMETRY_URL=https://api.telemetry.tantra.local
```

## 6. Unavailable Services

The following services are not yet available for live integration. Evidence of unavailability is documented in `review_packets/evidence/unavailable_services.json`.

| Service | Status | Required Follow-up |
|---------|--------|--------------------|
| Dhiraj Runtime | No live URL provided | Dhiraj to provide runtime API URL |
| Raj Governance | No live URL provided | Raj to provide governance API URL |
| Pravah Lineage | No live URL provided | Pravah team to provide lineage API URL |
| InsightFlow | No live URL provided | InsightFlow team to provide telemetry endpoint |

QCG integration code is ready for all services — only the live URLs are pending.
