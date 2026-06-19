# QCG_REPLAY_ALIGNMENT.md

> Phase 7 — TANTRA Ecosystem Alignment
> Replay authority boundary declaration for QCG within the TANTRA ecosystem.

---

## Authority Owned

`CanonicalReplayAuthority` (backed by `ReplayRegistry`) is the sole replay authority in QCG.

It owns:

- **Occurrence registration** — recording that an artifact has been seen
- **Duplicate detection** — rejecting any artifact already in the registry
- **Stale detection** — rejecting artifacts outside the TTL window
- **Sequence tracking** — assigning monotonically increasing sequence numbers
- **Replay lineage** — producing `ReplayLineageRecord` for every decision
- **Persistence** — surviving process restarts via file-backed atomic writes
- **Verdict vocabulary** — `VALID`, `DUPLICATE`, `STALE`, `FUTURE` are the only valid replay states

---

## Authority Not Owned

`CanonicalReplayAuthority` does **not** own and must not acquire:

- Payload validation — belongs to `GovernanceLayer`
- Producer authorization — belongs to `ProducerVerificationLayer`
- Contract version enforcement — belongs to `GovernanceLayer`
- Execution decisions — belongs to `RuntimeCore`
- Consensus — belongs to `ConsensusEngine`
- Signature verification — belongs to `NodeSigner` / `verify_contract_provenance`
- Trust chain evaluation — belongs to `TrustChain`
- Semantic meaning of a message — not a replay concern

---

## Execution Rights

| Component | Replay Right | Basis |
|-----------|-------------|-------|
| `CanonicalReplayAuthority` | **Decide** | Sole authority |
| `Receiver` (`gateway.py`) | **Consume verdict only** | Calls `get_authority().submit()` |
| `QuantumGateway` (`hybrid_gateway.py`) | **Consume verdict only** | Calls `replay_authority.submit()` |
| `execution_process.py` | **Consume verdict only** | Instantiates `CanonicalReplayAuthority`, calls `submit()` |
| `RuntimeCore` | **None** | Must not own replay state |
| `ReplayEnforcer` | **Deprecated** | Superseded; callers redirect to authority |

No component may maintain a local seen-set, replay cache, or sequence counter.

---

## Authority Ceiling

`CanonicalReplayAuthority` answers exactly one question per artifact:

> Has this artifact been seen before, and is it within its valid window?

It does **not** answer:

- Is this producer legitimate?
- Is this payload correct?
- Should this execution be trusted?
- Is this message semantically valid?

**Replay proves occurrence. Replay does NOT prove legitimacy.**

---

## Upstream Inputs

| Source | What it submits | Field used |
|--------|----------------|-----------|
| `Receiver` | `message_id` from `TranslationContract` | `translation_contract.message_id` |
| `QuantumGateway` / `industrial_endpoint` | `trace_id` from `ClassicalContract` | `contract.trace_id` |
| `execution_process` | `trace_id` from IPC contract dict | `raw["trace_id"]` |

All callers use `CanonicalReplayAuthority.submit()`. No caller bypasses this interface.

---

## Downstream Consumers

| Consumer | On `VALID` | On non-`VALID` |
|----------|-----------|----------------|
| `Receiver` | Resolve transport status and proceed | Return `transport_status="HALT:REPLAY_{status}"` |
| `QuantumGateway` | Proceed to endpoint delivery | Return `"HALT:REPLAY_{status}"` |
| `execution_process` | Proceed to trust verification + execution | Put `{"ack": "HALT:REPLAY_{status}"}` to output queue |

---

## GC Concerns

The Governance Constitutional (GC) layer interacts with replay at one surface:

- **Boundary**: `GovernanceLayer.enforce()` is called **after** a `VALID` verdict.
  A non-`VALID` verdict short-circuits before governance is ever consulted.
- **Non-interference**: `CanonicalReplayAuthority` has no knowledge of governance
  policy and must not be modified to serve governance concerns.
- **Audit**: All replay decisions are surfaced via `verification_report()` and
  `lineage()` for GC audit attachment.

---

## MDU Concerns

The Message Dispatch Unit (MDU) attaches to replay at one surface:

- **Lineage attachment point**: `ReplayLineageRecord` is the natural MDU attachment.
  Each record contains `replay_id`, `message_id`, `sequence_number`, `trace_reference`,
  `parent_reference`, and `verification_hash` — sufficient for MDU lineage tracking.
- **Non-modification rule**: MDU must read `ReplayLineageRecord` as produced.
  It must not request modifications to `CanonicalReplayAuthority` to serve
  MDU-specific concerns.
- **Access path**: `CanonicalReplayAuthority.lineage()` returns all `VALID` records
  in sequence order. `verification_report()` returns aggregate state.

---

## TMS Placement

`CanonicalReplayAuthority` sits between the transport layer and the execution layer:

```
[Transport / Producer]
        |
        v
  CanonicalReplayAuthority.submit()   ← single replay decision point
        |
   VALID verdict
        |
        v
[GovernanceLayer + RuntimeCore]
```

The authority is called after message receipt and before any governance or execution logic.
A non-`VALID` verdict short-circuits the pipeline immediately — governance and runtime
are never reached for rejected artifacts.

For TMS field classification purposes:

| Field | Classification |
|-------|---------------|
| `message_id` | DETERMINISTIC |
| `sequence_number` | DETERMINISTIC |
| `status` (VALID/DUPLICATE/STALE/FUTURE) | DETERMINISTIC |
| `decision_timestamp` | OBSERVABILITY |
| `verification_hash` | DETERMINISTIC |
| `replay_id` | DETERMINISTIC |
| `parent_reference` | DETERMINISTIC |

---

## Explicit Statement

> **Replay proves occurrence.**
> **Replay does NOT prove legitimacy.**

Occurrence: this artifact was received, it is within its valid window, and it has not been seen before.

Legitimacy: the artifact's producer is authorized, the payload is uncorrupted, and the execution is policy-compliant.

These are distinct claims. `CanonicalReplayAuthority` is the authority for the first.
It has no opinion on the second.
