# REVIEW PACKET - Execution Provenance Capability

## System Startup Path

To stand up the complete Live Ecosystem Capability:

1. **Start the Replay & GC Governance API:**
   ```bash
   python replay_and_gc_server.py
   ```
2. **Start the Dhiraj Runtime API:**
   ```bash
   python dhiraj_runtime_server.py
   ```
3. **Start the main QCG Web Server (Operational Readiness API):**
   ```bash
   python web_server.py
   ```
4. **Execute End-to-End Test (Ecosystem Flow):**
   ```bash
   python tests/e2e_ecosystem_flow.py
   ```

## Entry Points

* **Backend Entry:** `web_server.py`
* **Flow Controller:** `integration_harness.py`
* **APIs exposed via:** `web_server.py`, `replay_and_gc_server.py`, `dhiraj_runtime_server.py`

## Three Critical Execution Files

1. `web_server.py`: Exposes HTTP interfaces for contract verification (`/verify`) and provenance querying (`/evidence/certificate/{execution_id}`).
2. `integration_harness.py`: The main controller that processes incoming contracts, calls live APIs for Replay/GC, invokes Dhiraj runtime, runs consensus, and records evidence to the Evidence Ledger.
3. `integration_interfaces.py`: Defines the translation layer from Python objects to standard HTTP requests targeting external (simulated via live endpoints) systems like Dhiraj, GC, and Replay Authority.

## Live Execution Flow

1. **Pritesh Quantum Engine** generates a signed computation contract.
2. The contract is submitted to QCG via `POST /verify`.
3. QCG calls the **Replay API** via HTTP to validate trace freshness.
4. QCG calls the **GC Governance API** via HTTP to authorize the producer.
5. QCG calls the **Dhiraj Runtime API** via HTTP to execute the logic blindly.
6. Local Byzantine Consensus generates the final proof.
7. An `ExecutionRecord` is generated and hashed into the `EvidenceLedger`.
8. The final Trace Continuity payload is returned.

## Real Request JSON (Payload to /verify)

```json
{
  "contract": {
    "producer_type": "QUANTUM",
    "payload": {
      "operation": "shor_factorization",
      "input": 15
    },
    "confidence": 0.99,
    "trace_id": "test-trace-1234",
    "contract_version": "2.0.0",
    "timestamp": "2023-10-10T10:00:00Z"
  },
  "producer_public_key": "abc123xyz"
}
```

## Real Response JSON (From /verify)

```json
{
  "trace_id": "test-trace-1234",
  "parent_trace_id": null,
  "flow_status": "COMPLETED",
  "stages": {
    "replay": {
      "is_valid": true,
      "status": "OK",
      "sequence_number": 1,
      "verification_hash": null
    },
    "trust": {
      "passed": true,
      "halt_signal": "OK",
      "reason": "Contract authorized"
    },
    "execution": {
      "contract_trace_id": "test-trace-1234",
      "producer_type": "QUANTUM",
      "ack": "ACK:OK",
      "confidence": 0.99,
      "runtime_hash": "a1b2c3d4e5f6...",
      "execution_timestamp": "1696932000.123",
      "runtime": "DHIRAJ_RUNTIME_v1"
    },
    "consensus": {
      "consensus_reached": true,
      "agreement_percentage": 100.0,
      "final_hash": "f9e8d7c6b5a4..."
    }
  },
  "trace_continuity": {
    "sequence_number": 1,
    "runtime_hash": "a1b2c3d4e5f6...",
    "final_hash": "f9e8d7c6b5a4..."
  }
}
```

## Files Modified
* `web_server.py`: Replaced Python instantiation with REST API and added `GET /evidence/certificate/{execution_id}`.
* `integration_harness.py`: Wired `EvidenceLedger` to persist verified contracts.
* `integration_interfaces.py`: Modified interfaces to execute remote HTTP calls.
* `Dockerfile`: Replaced single-stage with multi-stage non-root build.

## Files Added
* `dhiraj_runtime_server.py`: Dedicated live endpoint representing Dhiraj Runtime.
* `replay_and_gc_server.py`: Dedicated live endpoint representing Replay Auth and GC Governance.
* `k8s/deployment.yaml`, `k8s/service.yaml`, `k8s/hpa.yaml`: Kubernetes deployment manifests.
* `load_testing/locustfile.py`: Distributed load testing script for the APIs.

## Files Untouched
* `canonical_replay_authority.py`, `consensus_simulation.py`, `evidence_ledger.py` logic remains intact.

## Failure Cases
1. **Low Confidence:** Rejected by `dhiraj_runtime_server.py` with `HALT:LOW_CONFIDENCE`.
2. **Unauthorized Producer:** Rejected by `replay_and_gc_server.py` with `HALT:UNAUTHORIZED_PRODUCER`.
3. **Duplicate Trace:** Rejected by `replay_and_gc_server.py` with `DUPLICATE_TRACE`.

## Runtime Evidence Index
Evidence is collected in `/review_packets/evidence/`:
* Kubernetes resource configurations (`/k8s/`).
* Docker build configuration (`Dockerfile`).
* Load testing script (`load_testing/locustfile.py`).

## Known Unknowns & Remaining Dependencies
- Production ECDSA key distribution mechanism (KESHAV sync) is currently simulated using trusted public keys in memory.
- Dhiraj runtime logic here represents a mock deterministic endpoint. Real logic would need actual physics/computational payloads.
- MDU endpoint push vs pull: We implemented a pull API (`GET /evidence/certificate/{execution_id}`), but MDU may require streaming Kafka push in the future.
