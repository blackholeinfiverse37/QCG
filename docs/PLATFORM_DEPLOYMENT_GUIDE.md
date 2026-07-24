# Platform Deployment Guide

## Overview

The TANTRA Platform Service layer is designed to deploy seamlessly alongside existing runtime components. It acts as an additive layer that does not interfere with core execution paths.

---

## Prerequisites

- Python 3.10+
- The core TANTRA ecosystem running (specifically the `CapabilityRegistryServer` on port 9000).

---

## Environment Variables

The platform layer respects existing configuration files (e.g., `config.py`) but can be overridden via environment variables if deployed in a containerized environment.

| Variable | Description | Default |
|---|---|---|
| `PLATFORM_DISCOVERY_HOST` | Host IP for discovery server | `127.0.0.1` |
| `PLATFORM_DISCOVERY_PORT` | Port for discovery server | `9010` |
| `CAPABILITY_REGISTRY_URL` | URL of canonical registry | `http://127.0.0.1:9000` |
| `EVIDENCE_DIR` | Directory for evidence logs | `./evidence/platform_registration` |

---

## Startup Sequence

In a production environment, the startup sequence should be:

1. **Boot Core Infrastructure**
   - Start `CapabilityRegistryServer` (:9000)
   - Start `CanonicalReplayAuthority`
   - Start `GovernanceLayer`

2. **Boot Platform Discovery Server**
   - Execute the platform initialization script to launch the discovery HTTP server (:9010).

3. **Register Services**
   - Execute the registration runner (or equivalent production initializer) to read `platform_capability_manifest.json` and publish records to the Discovery Server and Capability Registry.
   
```bash
python platform_service_registration_runner.py
```

4. **Boot Execution Nodes**
   - Start USF and QCG worker nodes.

---

## Containerization Notes

If deploying via Docker/Kubernetes:

1. **Port Mapping**: Ensure port `9010` (or configured override) is exposed for the Discovery Server.
2. **Persistent Volumes**: The `EVIDENCE_DIR` must be mapped to a persistent volume (e.g., PVC in Kubernetes). The deterministic hash chain breaks if the evidence directory is wiped on pod restart.
3. **Health Probes**: 
   - Liveness Probe: `GET /platform/v1/health`
   - Readiness Probe: `GET /platform/v1/readiness`

---

## Verification Post-Deployment

Verify the deployment was successful by hitting the top-level metrics and evidence endpoints:

```bash
# Check readiness
curl -s http://127.0.0.1:9010/platform/v1/readiness | jq .

# Verify evidence chain integrity
curl -s http://127.0.0.1:9010/platform/v1/evidence | jq .chain_valid
```
