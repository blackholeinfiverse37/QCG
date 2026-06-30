# Deployment Guide

This guide details the deployment model for the QCG Distributed Runtime within the TANTRA Ecosystem.

## Service Deployment Topology
The runtime consists of six primary sovereign services:
1. **Capability Registry:** (`capability_registry.py`)
2. **Replay Authority:** (`runtime_services.py --service replay`)
3. **Trust & Verification:** (`runtime_services.py --service trust`)
4. **Producer Service:** (`runtime_services.py --service producer`)
5. **Execution Core:** (`runtime_services.py --service execution`)
6. **Consensus Engine:** (`runtime_services.py --service consensus`)

## Startup Sequence
To ensure services successfully bind their dependencies via the discovery layer, follow this order:
1. Start the **Registry** first (Port `9000`).
2. Start the **Replay** and **Trust** services (Ports `9001`, `9002`).
3. Start the **Execution** service, which will wait until Replay and Trust are discoverable.
4. Start the **Producer** service, which awaits Execution.
5. Start the **Consensus** service.

## Configuration
Configure the `.env` or set environment variables according to `config.py`:
- `QCG_TRANSPORT_TYPE`: Choose `tcp`, `uds`, `http`, or `grpc`.
- Ports for all services (`QCG_REGISTRY_PORT` etc.) can be overridden.

## Containerization
Each service should be packaged in its own minimal Python container. Ensure network boundaries permit routing to the Registry port for discovery, and ensure health endpoints (`<port> + 100`) are accessible to monitoring agents.
