# Platform Integration Guide

## Overview

This guide explains how external sovereign systems (e.g., NICAI, InsightFlow, Pravah) interact with TANTRA Platform Services without manual configuration.

The integration model relies entirely on **dynamic discovery** and **contract negotiation**.

---

## Integration Workflow

### 1. Discovery

The consumer system starts by querying the Platform Discovery Server. The URL of the discovery server is the *only* hardcoded configuration required.

```bash
# Get all available services
curl http://127.0.0.1:9010/platform/v1/services
```

The consumer identifies the required service via `service_name` (e.g., `UNIVERSAL_SOLVER_FABRIC`) and extracts its `platform_service_id`.

### 2. Metadata & Manifest Fetching

The consumer fetches the complete metadata and capability manifest for the service:

```bash
curl http://127.0.0.1:9010/platform/v1/services/TANTRA-PSR-USF-001/metadata
```

This returns:
- **Operations:** The `supported_operations` array containing `input_contract` and `output_contract` JSON schemas.
- **Guarantees:** Determinism, replay, trust, and evidence guarantees.
- **Endpoints:** The actual URLs to invoke for execution, health, etc.

### 3. Version Negotiation

Before invoking any endpoints, the consumer *must* negotiate a compatible version:

```bash
curl -X POST http://127.0.0.1:9010/platform/v1/negotiate \
  -H "Content-Type: application/json" \
  -d '{"service_id": "TANTRA-PSR-USF-001", "requested_version": "1.0.0"}'
```

The consumer evaluates the response:
- `COMPATIBLE`: Proceed.
- `DEPRECATED`: Proceed, but log a warning to upgrade.
- `UNSUPPORTED`: Abort integration.

### 4. Health Verification

The consumer verifies the service is healthy and `ACTIVE` before sending traffic:

```bash
curl http://127.0.0.1:9010/platform/v1/services/TANTRA-PSR-USF-001/health
```

Expected response: `{"status": "UP", ...}`

### 5. Execution

The consumer extracts the `execution` endpoint from the metadata (Step 2) and formats a request matching the `input_contract` JSON schema for the target operation.

*(Note: The platform discovery layer does not execute the logic itself; it routes the consumer to the existing canonical runtime components like `RuntimeCore` or `SolverRegistry`.)*

---

## Observability Integration

Monitoring systems (e.g., InsightFlow) can auto-discover platform metrics by scraping the standard Prometheus endpoint:

```bash
curl http://127.0.0.1:9010/platform/v1/metrics
```

This returns system-wide metrics like `tantra_platform_uptime_seconds` and `tantra_platform_services_registered`.

---

## Zero-Config Principle

By strictly following this workflow, sovereign systems achieve **zero-config integration**:
1. No hardcoded ports or IPs (other than the discovery gateway).
2. No assumptions about input/output payloads (schemas are downloaded dynamically).
3. No assumptions about version compatibility (negotiated dynamically).
4. No assumptions about service availability (checked dynamically).
