# Deployment Guide

This guide details the deployment model for the QCG within the TANTRA Ecosystem.

## Quick Start (Local)

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure environment
cp .env.example .env
# Edit .env if needed (KESHAV integration is enabled by default)

# 3. Run the gateway
python hybrid_gateway.py

# 4. Run the web server
python web_server.py
# API available at http://localhost:8080
```

## Docker Deployment

```bash
# Build the image
docker build -t qcg-gateway:latest .

# Run with Docker Compose
docker-compose up --build

# API available at http://localhost:8080
# Health check: curl http://localhost:8080/health
```

## Kubernetes Deployment

```bash
# Apply manifests
kubectl apply -f k8s/

# Verify deployment
kubectl get pods -l app=qcg-service
kubectl get svc qcg-service
```

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

### Core Settings
- `QCG_CONFIDENCE_THRESHOLD`: Minimum confidence for OK status (default: `0.70`)
- `QCG_REPLAY_TTL_SECONDS`: Replay cache TTL in seconds (default: `300`)
- `QCG_GOVERNANCE_STRICT`: Enable strict governance mode (default: `true`)
- `QCG_TRANSPORT_TYPE`: Choose `tcp`, `uds`, `http`, or `grpc`

### Ecosystem Integration
- `QCG_KESHAV_API_URL`: KESHAV API base URL (default: `https://keshav-cia7.onrender.com`)
- `QCG_KESHAV_TIMEOUT_SECONDS`: HTTP timeout for KESHAV calls (default: `15`)
- `QCG_KESHAV_ENABLED`: Enable/disable KESHAV live integration (default: `true`)

### Port Configuration
Ports for all services (`QCG_REGISTRY_PORT` etc.) can be overridden via environment variables.

## Containerization
Each service should be packaged in its own minimal Python container. Ensure network boundaries permit routing to the Registry port for discovery, and ensure health endpoints (`<port> + 100`) are accessible to monitoring agents.

## Verification

```bash
# Run test suite
pytest tests/ -v

# Test KESHAV live integration
python keshav_live_client.py

# Collect full evidence package
python live_integration_evidence.py

# Run determinism proof
python determinism_proof.py
```
