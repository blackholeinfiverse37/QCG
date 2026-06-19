# REVIEW_PACKET.md

> Hybrid Quantum Communication Gateway — Full System Review Packet
> Phases 1–6 Complete
> Status: PRODUCTION HARDENED
> Owner: Pritesh
> Last verified: 2026-06-10

---

## 1. What This System Does

The Hybrid Quantum Communication Gateway (QCG) bridges probabilistic quantum output to
deterministic classical execution contracts. It guarantees:

- **Deterministic execution** — same input always produces the same deterministic output,
  regardless of wall-clock time or process identity.
- **Replay protection** — every message is accepted exactly once; duplicates and stale
  messages are rejected before execution.
- **Multi-process isolation** — producer, execution, and consensus run as independent OS
  processes with distinct PIDs.
- **Trust-aware communication** — no contract is executed without verified producer
  identity and ECDSA signature validation.
- **Durable replay state** — replay registry survives process restarts via file-backed
  persistence.

---

## 2. Architecture

```
TransmissionRequest
      |
      v
[Layer 1] QuantumProducer          quantum_producer.py      — Qiskit superdense coding
      |  QuantumDistribution
      v
[Layer 2] TranslationLayer         translation_layer.py     — Probabilistic → deterministic
      |  ClassicalContract
      v
[Layer 3] QuantumGateway           hybrid_gateway.py        — Orchestration + replay guard
      |
      v
[Communication Layer]
      |  CommunicationRequest → CommunicationGateway → CommunicationResponse
      |  communication_contract.py, gateway.py
      v
[Execution Pipeline — 3 OS Processes]
      |
      |  Process 1 (Producer)      producer_process.py
      |    └─ signs contract with ECDSA P-256
      |    └─ writes structured log → logs/process_1.log
      |
      |  multiprocessing.Queue  (q_prod_exec)
      |
      |  Process 2 (Execution)     execution_process.py
      |    └─ CanonicalReplayAuthority (sole replay verdict: VALID/DUPLICATE/STALE/FUTURE)
      |    └─ ProducerVerificationLayer (ECDSA identity + signature + type check)
      |    └─ RuntimeCore          (blind execution, ACK generation)
      |    └─ writes structured log → logs/process_2.log
      |
      |  multiprocessing.Queue  (q_exec_cons)
      |
      |  Process 3 (Consensus)     consensus_process.py
      |    └─ ConsensusEngine      (3 nodes, ECDSA attestations, 66% quorum)
      |    └─ writes structured log → logs/process_3.log
      |
      |  multiprocessing.Queue  (q_cons_out)
      |
      v
[Orchestrator]                     process_runner.py
      └─ joins all 3 processes, detects crashes, returns summary
```

---

## 3. Determinism

### Field Classification

Every field in the system is classified into one of three categories:

| Class | Meaning | Examples |
|-------|---------|---------|
| DETERMINISTIC | Identical for identical inputs, regardless of wall clock | `message_id`, `payload_hash`, `confidence`, `translation_status`, `transport_status` |
| OBSERVABILITY | Wall-clock timestamps — excluded from replay equality | `created_at`, `issued_at`, `trace_timestamp` |
| RUNTIME_ONLY | Internal execution artifacts, not part of contract | `runtime_hash`, `sequence_id` |

Full classification: `determinism_doctrine.py`, `DETERMINISM_DOCTRINE.md`.

### Timestamp Isolation Doctrine

Timestamps are **never** compared during replay verification. They are recorded for
audit purposes only. See `docs/timestamp_isolation_doctrine.md` for the full doctrine.

Replay equality is computed exclusively over DETERMINISTIC fields via:
- `ReplayContract.deterministic_projection()` — returns only the 5 deterministic fields
- `ReplayContract.deterministic_hash()` — SHA-256 of canonical JSON (`sort_keys=True`)
- `ReplayComparator.compare()` / `compare_many()` — compares projections, records
  observability diffs separately without affecting the verdict

### 20-Run Consistency Proof

`determinism_20_run_proof.py` — runs the same `CommunicationRequest` through 20
independent gateway instances. All 20 deterministic hashes must be identical.

```
python determinism_20_run_proof.py
# → 20-RUN DETERMINISM PROOF — PASS
# → All hashes identical: True
# → Mismatched fields: none
# → Observability diffs: N (timestamps — expected to differ)
```

Evidence: `TestDeterminism20Run::test_20_runs_identical`

---

## 4. Replay Enforcement

### Single Authority Model

`CanonicalReplayAuthority` is the **sole replay decision point** in QCG.
All components that previously made independent replay decisions have been
refactored to consume verdicts from this authority.

| Component | Previous Behaviour | Current Behaviour |
|-----------|-------------------|-----------------|
| `RuntimeCore` | Owned `_replay_registry` dict | No replay state — callers must consult authority first |
| `Receiver` (`gateway.py`) | Owned `_seen` dict | Delegates to `CanonicalReplayAuthority.submit()` |
| `QuantumGateway` | Owned `_replay_registry` dict | Delegates to `CanonicalReplayAuthority.submit()` |
| `execution_process` | Instantiated `ReplayEnforcer` directly | Delegates to `CanonicalReplayAuthority.submit()` |

### Decision States (canonical vocabulary)

- `VALID` — new message_id, within TTL, sequence assigned
- `DUPLICATE` — message_id already processed
- `STALE` — age > TTL (checked before duplicate)
- `FUTURE` — sequence gap exceeds `MAX_SEQUENCE_GAP` (1000)

No other component may introduce replay vocabulary.

### Stale-Before-Duplicate Ordering

Staleness is checked **before** duplicate detection. A message that is both stale
and duplicate is rejected as stale — the time window violation is the stronger signal.

Evidence: `TestReplayRegistry::test_stale_beats_duplicate`

### Replay Lineage

Every decision produces a `ReplayLineageRecord` with all Phase 5 fields:
`replay_id`, `message_id`, `sequence_number`, `decision`, `decision_timestamp`,
`origin_component`, `schema_version`, `trace_reference`, `parent_reference`,
`verification_hash`.

`CanonicalReplayAuthority.lineage()` returns all `VALID` records in sequence order.
Rejected decisions are excluded — they did not enter the record.

### Durable Persistence

`ReplayRegistry` writes atomically to disk on every `VALID` acceptance:
- Write to `.tmp` file
- `tmp.replace(path)` — atomic rename, no partial writes
- Load-on-start: new instance reads existing file automatically
- Corrupted file: starts fresh (no crash)

Evidence: `TestReplayRegistryPersistence::test_survives_restart`,
`TestReplayRegistryPersistence::test_duplicate_detected_after_restart`

### Canonical Replay Proof

```
python canonical_replay_proof.py
# → [PASS] Duplicate Detection
# → [PASS] Stale Detection
# → [PASS] Restart Persistence
# → [PASS] Sequence Monotonicity
# → [PASS] Concurrent Access
# → [PASS] Lineage Reconstruction
# → [PASS] Authority Exclusivity
# → CANONICAL REPLAY PROOF — PASS
```

---

## 5. Multi-Process Architecture

### IPC Topology

```
Process 1 (Producer)  --[q_prod_exec]--> Process 2 (Execution) --[q_exec_cons]--> Process 3 (Consensus) --[q_cons_out]--> Orchestrator
```

Transport: `multiprocessing.Queue` (shared memory). Upgrade path: Unix socket / gRPC.

Message schema: JSON-serialisable dicts with `"type"` discriminator field.

### Process Roles

| Process | File | Responsibilities |
|---------|------|-----------------|
| Producer | `producer_process.py` | Create signed `ComputationExecutionContract`, emit to queue |
| Execution | `execution_process.py` | Replay enforcement → provenance verification → RuntimeCore |
| Consensus | `consensus_process.py` | 3-node ECDSA consensus, 66% quorum |
| Orchestrator | `process_runner.py` | Spawn, join, crash detection |

### Crash Recovery

`crash_recovery_proof.py` proves:
1. Normal execution — ACK:OK
2. Registry survives crash — new instance loads same file, state intact
3. Duplicate blocked after restart — same trace_id rejected as DUPLICATE
4. New contract accepted after restart — sequence continues from last value
5. Registry isolation — two independent files share no state

```
python crash_recovery_proof.py
# → CRASH RECOVERY PROOF — PASS
```

### Crash Simulation

```bash
python process_runner.py --crash producer
python process_runner.py --crash execution
python process_runner.py --crash consensus
```

Each returns `crashes={"<stage>": exitcode}`, `pipeline_ok=False`.

Evidence: `TestIPCTopology::test_crash_producer_detected`,
`TestIPCTopology::test_crash_execution_detected`,
`TestIPCTopology::test_crash_consensus_detected`

### Structured Logs

Every process emits JSON log lines containing:

| Field | Type | Description |
|-------|------|-------------|
| `process_id` | int | OS PID |
| `message_id` | str | Contract trace_id |
| `sequence_number` | int | Replay sequence number |
| `status` | str | VALID / DUPLICATE / STALE / ACK:OK / etc. |
| `timestamp` | str | ISO-8601 wall-clock |

Evidence: `TestStructuredLogs::test_process_2_log_has_required_fields`,
`TestStructuredLogs::test_process_ids_are_distinct_across_logs`

---

## 6. Trust Validation

### Verification Steps

`ProducerVerificationLayer.verify()` performs three sequential checks:

1. **Identity** — `producer_id` is present and registered in `ProducerRegistry`
2. **Signature** — ECDSA P-256 verification of `contract_signature` via `verify_contract_provenance()`
3. **Trust** — `producer_type` is within the registered `allowed_types` for that `producer_id`

### Failure Modes

| Mode | Condition | Halt Signal |
|------|-----------|-------------|
| `UNVERIFIED_PRODUCER` | Missing or unregistered `producer_id` | `HALT:UNVERIFIED_PRODUCER:...` |
| `INVALID_SIGNATURE` | ECDSA verification fails or signature absent | `HALT:INVALID_SIGNATURE:...` |
| `TRUST_FAILURE` | `producer_type` not in `allowed_types` for producer | `HALT:TRUST_FAILURE:...` |

Any failure halts execution safely. No contract is forwarded to RuntimeCore.

### Role → Allowed Types Inference

| Registered Role | Default Allowed Types |
|----------------|----------------------|
| `QUANTUM_PRODUCER` | `{"QUANTUM"}` |
| `CLASSICAL_PRODUCER` | `{"CLASSICAL"}` |
| `HYBRID_PRODUCER` | `{"HYBRID", "QUANTUM", "CLASSICAL"}` |
| Any other role | `{"CLASSICAL", "QUANTUM", "HYBRID"}` |

### Trust Validation Proof

```
python trust_validation_proof.py
# → TRUST VALIDATION PROOF — PASS
# → [PASS] valid_producer_accepted
# → [PASS] tampered_payload_rejected
# → [PASS] forged_signature_rejected
# → [PASS] unregistered_producer_rejected
# → [PASS] type_mismatch_rejected
# → [PASS] missing_producer_id_rejected
```

---

## 7. Cryptography

All signatures use **ECDSA P-256 (secp256r1)** via the `cryptography` package.

| Operation | Algorithm | Location |
|-----------|-----------|----------|
| Key generation | ECDSA P-256, fresh per NodeSigner | `node_identity.NodeSigner.__init__` |
| Signing | `ec.ECDSA(hashes.SHA256())` over payload bytes | `NodeSigner.sign_payload` |
| Verification | Standard ECDSA verify, public key only | `verify_node_proof` |
| Public key format | DER SubjectPublicKeyInfo, hex-serialised | `NodeIdentity.public_key` |
| Signature format | DER-encoded ECDSA signature, hex-serialised | `NodeProof.signature` |

Private keys never leave the `NodeSigner` instance. Verification uses only
the public key — no shared secret, no HMAC.

---

## 8. Testing

### Test Count

| Suite | File | Tests |
|-------|------|-------|
| Core pipeline + Phase 1–4 | `tests/test_all.py` | 213 |
| Phase 5 hardening | `tests/test_phase5.py` | ~100 |
| Communication layer | `tests/test_communication_layer.py` | 74 |
| Adapter layer | `tests/test_adapter_layer.py` | 74 |
| **Total** | | **250+** |

### Run

```bash
pytest tests/ -v      # full suite, 0 failures
```

### Coverage by Phase

| Phase | Area | Key Test Classes |
|-------|------|-----------------|
| 1 | Determinism hardening | `TestReplayContract`, `TestReplayComparator`, `TestDeterminism20Run` |
| 2 | Durable replay | `TestReplayRegistry`, `TestReplayRegistryPersistence`, `TestReplayEnforcementProof` |
| 3 | Multi-process | `TestCrashRecoveryProof`, `TestProcessIsolation`, `TestIPCTopology`, `TestStructuredLogs` |
| 4 | Trust validation | `TestProducerRegistry`, `TestProducerVerificationLayer`, `TestTrustValidationProof` |
| 5 | Gap coverage | `TestReplayRegistryExtended`, `TestReplayEnforcerExtended`, `TestReplayContractExtended`, `TestProducerRegistryExtended`, `TestProducerVerificationLayerExtended`, `TestConcurrentReplayExtended` |

---

## 9. Quick Start

```bash
pip install -r requirements.txt
cp .env.example .env   # optional: tune thresholds

# Full test suite
pytest tests/ -v

# Determinism proof (20 runs)
python determinism_20_run_proof.py

# Replay enforcement proof
python replay_enforcement_proof.py

# Crash recovery proof
python crash_recovery_proof.py

# Trust validation proof
python trust_validation_proof.py

# Three-process pipeline
python process_runner.py

# Crash simulation
python process_runner.py --crash producer
python process_runner.py --crash execution
python process_runner.py --crash consensus
```

---

## 10. Production Hardening Applied

The following bugs were identified and fixed:

| # | File | Bug | Fix |
|---|------|-----|-----|
| 1 | `replay_registry.py` | `json.loads("")` crash on empty file | Strip + early-return before parse |
| 2 | `replay_registry.py` | Path and sequence gap hardcoded | Now driven by `QCG_REPLAY_REGISTRY_PATH` / `QCG_MAX_SEQUENCE_GAP` via `config` |
| 3 | `replay_enforcer.py` | Cache grew unbounded when all entries within TTL at eviction | Fallback to oldest-by-issued_at eviction when no expired entries found |
| 4 | `runtime_core.py` | `_replay_registry` dict caused authority drift — RuntimeCore was a second independent replay decider | Removed entirely; callers must obtain a `VALID` verdict from `CanonicalReplayAuthority` before calling `execute()` |
| 5 | `gateway.py` | `Receiver._seen` used `set` — FIFO eviction was non-deterministic | Replaced with insertion-ordered `dict` for guaranteed FIFO |
| 6 | `logger.py` | `makedirs(dirname("qcg.log"))` → `makedirs("")` crash when log file in CWD | `abspath` before `dirname` |
| 7 | `execution_process.py` | Producer self-registers with any claimed type on first IPC contact (trust escalation) | Key-swap check: different public key for same `producer_id` → `HALT:INVALID_SIGNATURE` |
| 8 | `process_runner.py` | Serial `join(timeout=30)` — hung P1 blocked P2/P3 crash detection for up to 60s | Concurrent joins via threads; stragglers terminated after timeout |

---

## 11. Known Limitations

1. **IPC transport** — `multiprocessing.Queue` uses shared OS memory, not a real
   network socket. Real deployment requires ZeroMQ, gRPC, or equivalent.

2. **NodeRegistry is ephemeral** — in-memory only. Production requires persistent
   storage with certificate rotation and revocation.

3. **ReplayRegistry uses file-backed persistence** — while it persists across process restarts,
   it requires disk IO. True high-throughput multi-process coordination requires a
   shared cache (e.g. Redis/Valkey).

4. **`issued_at` is producer-reported** — wall-clock time from the producer, not a
   cryptographically signed timestamp from a trusted time authority.

5. **Consensus nodes share OS process memory** — logically independent but not
   network-separated. True Byzantine isolation requires real network transport.

6. **MerkleAuditTrail rebuilds on append** — not suitable for high-throughput
   production without a persistent incremental tree backend.

7. **Cache eviction is insert-triggered** — fires only when cache exceeds 10,000
   entries. A high-volume short-TTL scenario could briefly exceed this.

8. **ProducerRegistry is in-memory** — no persistence, no revocation. A
   compromised producer_id cannot be revoked without restarting the process.

---

## 12. Remaining Risks

| Risk | Severity | Mitigation Path |
|------|----------|----------------|
| No network-level IPC | Medium | Replace Queue with Unix socket / gRPC |
| In-memory NodeRegistry | Medium | Add file-backed registry with revocation list |
| Producer-reported `issued_at` | Low-Medium | Signed timestamps from trusted time authority |
| No heartbeat on process crash detection | Low | Add health-check polling alongside exit-code check |
| File-backed ReplayRegistry | Medium | Synchronise via Redis for high-throughput multi-process deployments |
| Merkle tree O(n) append | Low | Persistent incremental tree (append-only log) |
| No cross-process replay coordination | Medium | Shared durable cache (Redis/Valkey) |

---

## 13. Production Readiness

| Capability | Status |
|-----------|--------|
| Deterministic execution (same input → same output) | ✅ Proven (20-run proof) |
| Replay protection — duplicate rejection | ✅ Proven (in-memory + durable) |
| Replay protection — stale rejection | ✅ Proven |
| Replay registry survives process restart | ✅ Proven (file-backed) |
| Multi-process execution (3 independent OS processes) | ✅ Proven (distinct PIDs) |
| Crash detection | ✅ Proven (exit-code based) |
| Producer identity verification | ✅ Proven (ECDSA P-256) |
| Signature tamper detection | ✅ Proven |
| Type mismatch rejection | ✅ Proven |
| Structured execution logs | ✅ Proven (JSON, 5 required fields) |
| Concurrent thread safety | ✅ Proven (threading.Lock throughout) |
| 250+ passing tests, 0 failures | ✅ |
| Memory-bounded caches (replay, gateway, runtime) | ✅ Fixed |
| FIFO eviction correctness | ✅ Fixed |
| Logger crash on bare filename | ✅ Fixed |
| Trust escalation via key-swap | ✅ Fixed |
| Concurrent process join (no serial stall) | ✅ Fixed |
| Network-level IPC | ❌ Queue only (upgrade needed) |
| Persistent NodeRegistry | ❌ In-memory only |
| Signed timestamps | ❌ Producer-reported only |

---

## 14. Ecosystem Alignment

| System | Attachment Point | Status |
|--------|-----------------|--------|
| TMS | `DeterminismOracle` field registry | Alignment needed — field classification schema |
| GC | Replay enforcement as execution-affecting authority | Alignment needed — constitutional boundary |
| MDU | Replay registries, sequence ledgers, provenance metadata | Alignment needed — governed schema ownership |
| NICAI | `execution_process.queue_out` | Attachment surface defined |
| InsightFlow | `MerkleAuditTrail.root_hash()` | Attachment surface defined |
| Pravah | `ReplayBundle.verification_report()` | Attachment surface defined |
| Sampada | `TrustChain.to_dict_list()` | Attachment surface defined |

---

## 15. File Reference

```
# Phase 1 — Determinism Hardening
deterministic_replay.py        ReplayContract, ReplayComparator, DeterministicComparisonResult
determinism_20_run_proof.py    20-run consistency proof
docs/timestamp_isolation_doctrine.md   Timestamp isolation doctrine
determinism_doctrine.py        DeterminismOracle, field classification
DETERMINISM_DOCTRINE.md        Field classification reference table

# Phase 2 — Durable Replay
replay_registry.py             Persistent file-backed replay registry
replay_enforcement_proof.py    Duplicate, stale, sequence, persistence proof
replay_enforcer.py             In-memory sequence + TTL enforcer

# Phase 3 — Multi-Process
producer_process.py            OS process: contract production
execution_process.py           OS process: replay + provenance + execution
consensus_process.py           OS process: consensus verification
process_runner.py              Orchestrator: spawn, join, crash detection
crash_recovery_proof.py        Crash recovery + process isolation proof
logs/process_1.log             Producer process structured log
logs/process_2.log             Execution process structured log
logs/process_3.log             Consensus process structured log

# Phase 4 — Trust
producer_verification.py       ProducerRegistry, ProducerVerificationLayer, VerificationResult
trust_validation_proof.py      6-case trust validation proof
node_identity.py               NodeIdentity, NodeSigner, NodeProof
provenance.py                  sign_contract, verify_contract_provenance

# Phase 5 — Tests
tests/test_all.py              213 tests (Phases 1–4 core)
tests/test_phase5.py           ~100 tests (Phase 5 gap coverage)
tests/test_communication_layer.py   74 tests (communication contracts + gateway)
tests/test_adapter_layer.py    74 tests (adapters, runtime, governance, distributed)

# Communication Layer
communication_contract.py      CommunicationRequest, TranslationContract, AcknowledgementContract
gateway.py                     CommunicationGateway, QuantumProducer, ClassicalProducer, HybridProducer
simulation.py                  All 4 cross-system paths

# Core Pipeline
config.py                      All constants, env-overridable
models.py                      TransmissionRequest, QuantumDistribution, ClassicalContract
quantum_producer.py            Qiskit quantum simulation
translation_layer.py           QuantumDistribution → ClassicalContract
hybrid_gateway.py              QuantumGateway (Layers 3+4+5)
runtime_core.py                Blind execution, ACK generation (no replay state)
execution_contract.py          ComputationExecutionContract, validation
adapters.py                    QuantumAdapter, ClassicalAdapter, HybridAdapter

# Canonical Replay Spine
canonical_replay_authority.py  CanonicalReplayAuthority, ReplayLineageRecord, ReplayVerdict
replay_registry.py             Persistent file-backed registry (sole replay state store)
REPLAY_AUTHORITY_AUDIT.md      Phase 1: audit of all former replay decision points
REPLAY_DOCTRINE.md             Phase 2: doctrine — authority, vocabulary, failure modes
QCG_REPLAY_ALIGNMENT.md        Phase 7: TANTRA ecosystem alignment
canonical_replay_proof.py      Phase 6: 7-proof suite — exits 0 on PASS
```
