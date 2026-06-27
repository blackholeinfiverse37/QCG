# TANTRA Integration Guide

This guide details how other BHIV products (NICAI, InsightFlow, Pravah, KESHAV, BHIV Core Runtime) can natively integrate with the Quantum Communication Gateway (QCG).

## 1. Attachment Topology

The QCG exposes a **lightweight Operational Readiness HTTP Server** serving as the primary attachment surface for the TANTRA ecosystem.

- **URL:** `http://<qcg-node-ip>:8080`
- **Protocol:** HTTP/1.1 REST over JSON
- **Authentication:** Standard BHIV Mutual TLS (not modeled in demo) + ECDSA Signed Contracts.

## 2. Standardized Integrations

### 2.1 NICAI / BHIV Core Runtime (Execution Invocation)
Products executing classical translations of quantum logic attach via the `/verify` endpoint.

**POST /verify**
```json
{
  "contract": {
    "trace_id": "tr-1234",
    "payload": {"task": "optimization"},
    "producer_id": "YOUR_NODE_ID",
    "contract_version": "2.0.0",
    "producer_type": "QUANTUM",
    "confidence": 0.99
  },
  "producer_public_key": "hex_encoded_ecdsa_pubkey",
  "issued_at": 1679090900.0
}
```
**Response:**
Returns a complete flow trace including replay verdict, trust verdict, runtime execution hash, and the final 3-node Byzantine consensus result.

### 2.2 InsightFlow (Audit & Provenance)
InsightFlow instances monitor operational stability and runtime hash integrity.
- Poll `GET /health` or `GET /health/live` to scrape metrics.
- Ingest `runtime_hash` and `final_hash` (Consensus) emitted in the `/verify` response payload.

### 2.3 Pravah (Stream Lineage)
Pravah attaches to the `sequence_number` generated during the **Replay Validation** stage. 
- QCG guarantees strictly monotonic sequence IDs per valid artifact. 
- The sequence number is returned in the `/verify` output under `trace_continuity`.

### 2.4 KESHAV (Identity & Trust)
QCG performs dynamic producer identity mapping. 
- In this reference implementation, the `producer_public_key` is synchronized inline. 
- In production, QCG syncs with KESHAV nodes to pre-populate its `ProducerRegistry`.

## 3. Handling Failure Boundaries

If a downstream product receives an HTTP `422 Unprocessable Entity`, examine the `halt_reason`:
- `REPLAY_DUPLICATE`: Artifact was already processed. Drop duplicate.
- `REPLAY_STALE`: Artifact is too old (exceeded TTL).
- `INVALID_SIGNATURE`: Cryptographic mismatch. Suspect payload tampering.
- `HALT:LOW_CONFIDENCE`: The contract was degraded beyond the acceptable floor.
