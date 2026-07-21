# Code Packets — File Purposes

## New Files (Ecosystem Convergence Phase)

| File | Purpose |
|------|---------|
| `keshav_live_client.py` | Production HTTP client for live KESHAV API with structured logging and evidence collection |
| `live_integration_evidence.py` | Script that runs all live integrations, captures evidence, and documents unavailable services |

## Modified Files

| File | Purpose |
|------|---------|
| `integration_harness.py` | TANTRA pipeline harness — added KESHAV live analysis step after replay validation |
| `config.py` | Central config — added KESHAV API URL, timeout, and enable/disable settings |
| `web_server.py` | FastAPI server exposing /health, /capabilities, and /verify endpoints |

## Integration Files

| File | Purpose |
|------|---------|
| `integration_interfaces.py` | Standard BHIV interfaces for replay, trust, execution, consensus, and health |
| `ecosystem_participation.py` | 6 ecosystem participants through universal trust pipeline |

## Critical Core Files (Unchanged)

| File | Purpose |
|------|---------|
| `execution_contract.py` | ComputationExecutionContract data model — uniform producer envelope |
| `canonical_replay_authority.py` | Replay registration, duplicate/stale detection, lineage |
| `producer_verification.py` | ECDSA-based producer identity verification |
| `runtime_core.py` | Blind deterministic execution engine |
| `consensus_simulation.py` | 3-node Byzantine consensus with signed attestations |
