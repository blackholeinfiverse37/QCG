# QCG Ecosystem Integration Guide

This guide explains how external systems (e.g., KESHAV Identity Managers, InsightFlow telemetry pipelines, NICAI nodes, and Pravah orchestration layers) can seamlessly integrate with the Quantum Communication Gateway (QCG).

## Overview

The QCG acts as an independent execution proxy with standardized boundaries. Systems interacting with the QCG interact primarily via two routes:
1. `GET /capabilities` - For capability discovery.
2. `POST /verify` - The main ingress for Computation Execution Contracts.

## Identity and Cryptographic Provenance

QCG enforces **cryptographic provenance** on all incoming contracts.

External producer nodes MUST register their public keys with the Trust Registry (simulated via KESHAV identity management sync). All incoming requests to QCG must contain:
1. A base `ComputationExecutionContract`.
2. A `producer_signature` covering the contract payload.
3. A `contract_signature` covering the deterministic full-state representation of the contract.

QCG exposes a helper module `provenance.py` that provides a `sign_contract` method compatible with the QCG standard.

## 1. Submitting Contracts to QCG

External engines (such as Pritesh's Quantum Engine) can construct and sign a `ComputationExecutionContract` payload and send it to QCG for validation and execution.

### Request Format
```json
POST /verify
{
  "contract": {
    "producer_type": "QUANTUM",
    "payload": {
      "operation": "shor_factorization",
      "input": 15
    },
    "confidence": 0.99,
    "trace_id": "93655843-67f7-54db-b0d0-f1903994c696",
    "contract_version": "2.0.0",
    "producer_id": "PRITESH_QUANTUM_ENGINE_01",
    "timestamp": "2026-07-01T07:05:19+00:00",
    "payload_hash": "...",
    "producer_signature": "...",
    "contract_signature": "..."
  },
  "producer_public_key": "<ECDSA_P256_PUBLIC_KEY>"
}
```

### Standard Responses
If the contract is successfully verified through all phases (Replay, Trust, Execution, Consensus), you receive a HTTP `200 OK`:
```json
{
  "trace_id": "93655843-67f7-54db-b0d0-f1903994c696",
  "parent_trace_id": null,
  "flow_status": "COMPLETED",
  "stages": { ... },
  "trace_continuity": {
    "sequence_number": 1,
    "runtime_hash": "ff115c97...",
    "final_hash": "ff115c97..."
  }
}
```

If it fails validation (e.g., bad signature, unregistered producer, duplicate trace), you will receive `422 Unprocessable Entity` with details about the HALT signal.

## 2. Telemetry and InsightFlow

To support centralized telemetry (InsightFlow), QCG uses unified structured logging. All events, validations, and executions output logs with contextual traces.

For health status, poll the `GET /health` endpoint:
```json
{
  "status": "UP",
  "version": "1.0.0",
  "readiness": "READY",
  "dependencies": {
    "replay_registry": "ONLINE",
    "consensus_nodes": "ONLINE"
  },
  "metrics": {
    "uptime_seconds": 3600.5,
    "total_processed": 500,
    "error_rate": 0.002,
    "registry_size": 499
  }
}
```

## 3. Extending the QCG

QCG utilizes Standardized Interfaces defined in `integration_interfaces.py`. If a new external integration layer requires integration, build a wrapper conforming to `StandardizedInterface` and mount it within the `TANTRAIntegrationHarness`.
