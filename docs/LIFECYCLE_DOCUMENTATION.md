# Lifecycle Documentation

## Overview

Platform Services follow a strict, auditable lifecycle managed by the `LifecycleManager`. Every state transition generates deterministic, replay-safe evidence linked via a SHA-256 hash chain.

---

## State Machine

The lifecycle consists of four primary states:

1. **DRAFT** — The service is registered but not actively accepting traffic. Effectively "disabled".
2. **ACTIVE** — The service is fully operational and discoverable.
3. **DEPRECATED** — The service is functional but slated for retirement. Consumers should migrate.
4. **RETIRED** — Terminal state. The service is permanently decommissioned.

### Valid Transitions

```text
DRAFT      → ACTIVE
ACTIVE     → DRAFT
ACTIVE     → DEPRECATED
DEPRECATED → ACTIVE
DEPRECATED → RETIRED
RETIRED    → (Terminal — No further transitions allowed)
```

Attempting an invalid transition (e.g., `DRAFT → RETIRED`) will raise a `ValueError` and will not be recorded in the evidence chain.

---

## Overlay States

The system also maintains a boolean `enabled` overlay state.
- `enable(service_id)`: Transitions a DRAFT or DEPRECATED service back to ACTIVE. If already ACTIVE, simply ensures the enabled flag is true.
- `disable(service_id)`: Transitions an ACTIVE service to DRAFT.

---

## Lifecycle Evidence Chain

Every lifecycle action is appended to the `LifecycleManager`'s internal evidence chain. This chain is identical in structure to the registration evidence chain, providing a tamper-evident audit trail of all operational changes.

### Event Record

```json
{
  "event_id": "uuid-v4",
  "service_id": "TANTRA-PSR-USF-001",
  "action": "DEPRECATE",
  "previous_state": "ACTIVE",
  "new_state": "DEPRECATED",
  "actor": "SYSTEM_OPERATOR",
  "reason": "Superseded by USF v2",
  "timestamp": "ISO-8601",
  "event_hash": "sha256...",
  "previous_event_hash": "sha256...",
  "replay_metadata": {
    "chain_length": 4,
    "head_hash_before": "sha256..."
  }
}
```

### Chain Integrity Verification

The `verify_chain()` method recalculates all hashes from the genesis block (`LIFECYCLE_GENESIS`) to the current head, ensuring no events have been inserted, modified, or deleted.

---

## API Integration

While the `LifecycleManager` operates internally, its effects are visible via the Discovery API:

1. **Service Status**: `GET /platform/v1/services/{id}` includes the current `status` field.
2. **Health Checks**: `GET /platform/v1/services/{id}/health` returns `UP` for `ACTIVE` services and `DOWN` for all other states (including `DEPRECATED`).
3. **Evidence**: While the discovery API `/platform/v1/evidence` currently exposes registration evidence, lifecycle evidence is persisted to disk alongside it during the registration runner's execution (`lifecycle_evidence.json`).
