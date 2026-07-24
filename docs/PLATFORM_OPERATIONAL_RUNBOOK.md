# Platform Operational Runbook

## Overview

This runbook provides operational procedures for monitoring, troubleshooting, and maintaining the TANTRA Platform Service layer.

---

## 1. Monitoring & Metrics

### InsightFlow / Prometheus Integration

The Discovery Server exposes metrics at `/platform/v1/metrics`. 

**Key Metrics to Alert On:**
- `tantra_platform_uptime_seconds` (Alert if resets unexpectedly)
- `tantra_platform_services_registered` (Alert if < expected count, indicating service drop)
- `tantra_platform_evidence_chain_length` (Monitor for continuous growth)

---

## 2. Evidence Chain Integrity

The Platform Service Registry and Lifecycle Manager maintain SHA-256 hash chains.

### Checking Integrity

```bash
curl -s http://127.0.0.1:9010/platform/v1/evidence | jq '{valid: .chain_valid, length: .chain_length}'
```

### Response to Chain Invalidity

If `chain_valid` returns `false`, a tamper event or corruption has occurred:
1. Halt platform registration capabilities immediately.
2. Extract the `evidence.json` file from the persistent volume.
3. Compare the hashes iteratively using `previous_evidence_hash` to locate the divergence point.
4. Escalate to the Governance team.

---

## 3. Service Lifecycle Management

Operators can manually transition a service's lifecycle state if an emergency deprecation or retirement is required.

*(Note: Currently executed via Python shell interacting with the `LifecycleManager` singleton, pending a dedicated admin CLI).*

```python
from platform_lifecycle_manager import LifecycleManager
# Assuming access to the running LifecycleManager instance
lifecycle.deprecate("TANTRA-PSR-USF-001", actor="OPERATOR_1", reason="Emergency deprecation")
```

---

## 4. Troubleshooting Common Issues

### Issue: Services not appearing in Discovery API

**Symptoms:** `GET /platform/v1/services` returns `count: 0`.

**Diagnosis:**
1. Check if the registration runner executed successfully.
2. Check `readiness` endpoint — if `ready: false`, the registry is not initialized.
3. Inspect `evidence/platform_registration/registration_evidence.json` for `SERVICE_REGISTERED` events.

### Issue: Consumers receiving UNSUPPORTED for valid versions

**Symptoms:** Negotiation returns `UNSUPPORTED` unexpectedly.

**Diagnosis:**
1. Check the compatibility matrix: `GET /platform/v1/services/{id}/compatibility`.
2. Ensure the version was properly registered via `VersionNegotiator.register_compatibility()`.
3. Verify the requested version string matches exactly (semver format).

### Issue: Registration runner fails with Connection Refused

**Symptoms:** `platform_service_registration_runner.py` throws `urllib.error.URLError: [WinError 10061]`.

**Diagnosis:**
1. Ensure the underlying `CapabilityRegistryServer` is actually running on port `9000`.
2. Ensure no firewall rules block local traffic on `9000` or `9010`.
