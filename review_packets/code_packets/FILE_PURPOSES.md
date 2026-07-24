# Code Packets — File Purposes

This directory contains references to the critical modified files and new files created during the Ecosystem Convergence integration phase.

## Critical Modified Files
- `web_server.py`: Exposes HTTP interfaces for contract verification (`/verify`) and provenance querying (`/evidence/certificate/{execution_id}`).
- `integration_harness.py`: The main controller that processes incoming contracts, calls live APIs for Replay/GC, invokes Dhiraj runtime, runs consensus, and records evidence to the Evidence Ledger.
- `integration_interfaces.py`: Defines the translation layer from Python objects to standard HTTP requests targeting external (simulated via live endpoints) systems like Dhiraj, GC, and Replay Authority.

## Integration Files (Phase 1 Ecosystem Federation)
- `keshav_live_client.py`: Implementation of the live KESHAV Identity and Analysis integration client.
- `pritesh_live_client.py`: Client for submitting simulated payloads to the Pritesh Quantum runtime capability.
- `live_integration_evidence.py`: Script to generate all API request/response pairs and dump evidence.
- `tests/e2e_ecosystem_flow.py`: Full Phase 2 Flow integration test demonstrating all nodes acting together.

## Local Simulation Nodes
- `dhiraj_runtime_server.py`: Dedicated live endpoint representing Dhiraj Runtime for local simulation.
- `replay_and_gc_server.py`: Dedicated live endpoint representing Replay Auth and GC Governance for local simulation.

## Deployment Files
- `k8s/deployment.yaml`: Primary deployment manifest for the QCG web server.
- `k8s/service.yaml`: Service definition for QCG load balancer.
- `k8s/hpa.yaml`: Horizontal Pod Autoscaler for scaling under load.
- `load_testing/locustfile.py`: Locust file used for swarm load testing.
