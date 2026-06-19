# ARCHITECTURE.md

> Phase 3 Trust Layer — Structural Reference

---

## Layer Map

```
[Producer Process]          producer_process.py
      |  Queue (CONTRACT)
      v
[Execution Process]         execution_process.py
      |  canonical_replay_authority.py (Canonical Replay Spine, VALID/DUPLICATE/STALE)
      |  runtime_core.py    (blind execution, ACK generation)
      |  Queue (EXECUTION_RESULT)
      v
[Consensus Process]         consensus_process.py
      |  consensus_simulation.py (3 nodes, 66% quorum, signed attestations)
      |  Queue (CONSENSUS_PROOF)
      v
[Orchestrator]              process_runner.py
```

---

## Component Responsibilities

| Component | Owns | Does NOT Own |
|-----------|------|--------------|
| `CanonicalReplayAuthority` | Replay registration, duplicate/stale detection, lineage, persistence | Contract validation, execution logic |
| `RuntimeCore` | Blind execution, ACK, runtime_hash | Producer type routing, governance policy, Replay state |
| `ConsensusEngine` | Attestation verification, quorum math | Contract authorship, execution |
| `TrustChain` | Chain-of-custody handoff signatures | Identity issuance |
| `MerkleAuditTrail` | Tamper-evident append-only log, inclusion proofs | Log rotation, persistence |
| `NodeRegistry` | Identity lookup | Certificate rotation |
| `DeterminismOracle` | Field classification, projection extraction | Execution |

---

## IPC Topology

```
producer_process --> q_prod_exec --> execution_process --> q_exec_cons --> consensus_process --> q_cons_out
```

- Transport: `multiprocessing.Queue` (shared memory; upgrade path: socket/gRPC)
- Message schema: JSON-serialisable dicts with `"type"` discriminator field
- `EXECUTION_RESULT` message forwards the original signed `contract` dict and
  `producer_public_key` so consensus verifies the same payload that was executed
- All processes are real OS processes with independent PIDs

---

## Determinism Boundary

Fields are classified as DETERMINISTIC or OBSERVABILITY in `determinism_doctrine.py`.

- DETERMINISTIC fields: identical for identical inputs regardless of wall clock
- OBSERVABILITY fields: wall-clock timestamps, excluded from replay comparison

Replay comparison uses `DeterminismOracle.extract_deterministic_projection()`.

---

## Replay Protection Layers

| Layer | Mechanism | Rejection Signal |
|-------|-----------|-----------------|
| Single Replay Spine | `CanonicalReplayAuthority.submit()` (backed by `ReplayRegistry`) | `VALID`, `DUPLICATE`, `STALE`, `FUTURE` |
| Duplicate / Stale | `ReplayRegistry` logic | `DUPLICATE` / `STALE` |
| Sequence | Monotonic counter in `ReplayRegistry` | Visible in `sequence_number` field |
| Runtime replay guard | DELEGATED | Calls `CanonicalReplayAuthority` (RuntimeCore owns no replay state) |

---

## Trust Verification Chain

```
NodeIdentity (public_key)
      |
      v
TrustChain.add_handoff()  -- sender signs handoff dict
      |
      v
TrustChain.verify_chain() -- checks registration + signature + continuity
      |
      v
ReplayBundle.verify()     -- bundle sig + producer sig + consensus + audit root + chain
```

---

## Known Limitations

- IPC transport is `multiprocessing.Queue` (shared memory), not a real network socket
- `NodeRegistry` is ephemeral (in-memory only)
- Consensus nodes share the same OS process memory; true isolation requires network transport
- `MerkleAuditTrail` rebuilds tree on each append (not production-scale)
- `ReplayRegistry` file backing requires IO (production-scale requires Redis/Valkey)

---

## Capability Attachment Surfaces (not integrations)

| Future Consumer | Attachment Point | Protocol |
|-----------------|-----------------|----------|
| NICAI | `execution_process.queue_out` | Queue / socket |
| InsightFlow | `MerkleAuditTrail.root_hash()` | Merkle proof API |
| Pravah | `ReplayBundle.verification_report()` | JSON |
| Sampada | `TrustChain.to_dict_list()` | REST / gRPC |
| TMS | `DeterminismOracle` field registry | In-process import |
