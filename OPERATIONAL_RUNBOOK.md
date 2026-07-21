# Operational Runbook

This guide is intended for the TANTRA Ecosystem on-call engineers.

## Common Alerts
### High Replay Failure Rate (`qcg_replay_invalid_total`)
- **Symptoms:** High rate of messages rejected with STALE or DUPLICATE.
- **Action:** Check Producer service clocks for NTP synchronization drift. Verify `QCG_REPLAY_TTL_SECONDS`.

### Execution Service Circuit Breaker Tripped
- **Symptoms:** Logs show `CircuitBreakerOpenException`, high `failures_total`.
- **Action:** 
    1. Confirm the downstream Trust or Replay services are running via `/health`.
    2. Restart the downstream service if it is deadlocked. 
    3. The breaker will automatically close 10 seconds after recovery.

### Consensus Failure (`qcg_consensus_failed_total`)
- **Symptoms:** Byzantine consensus engine halting execution.
- **Action:** Inspect `logs/consensus_output.log`. Determine if signatures mismatched, or node identities were not registered properly in `ProducerRegistry`.

### KESHAV Integration Issues
- **Symptoms:** `keshav_analysis` stage shows `status: FALLBACK` or `status: SKIPPED` in `/verify` responses.
- **Action:**
    1. Check KESHAV health: `curl https://keshav-cia7.onrender.com/health` — expect `{"status": "OK", "service": "KESHAV"}`.
    2. Check KESHAV metrics: `curl https://keshav-cia7.onrender.com/metrics/json` — inspect `request_errors` and `request_success_rate`.
    3. If KESHAV is down, QCG continues operating with local verification only. No data loss.
    4. Verify `QCG_KESHAV_ENABLED=true` and `QCG_KESHAV_API_URL` are set correctly.
    5. If latency is high (>5s), increase `QCG_KESHAV_TIMEOUT_SECONDS` or check network connectivity.

## Restarting Services
When restarting, you can safely kill processes using standard termination (SIGTERM). Do **NOT** forcefully kill (`SIGKILL`) unless the service hangs, to preserve the evidence ledger structure.

## Health Endpoints
| Endpoint | Purpose | Expected Response |
|----------|---------|-------------------|
| `GET /health` | QCG liveness check | JSON with process counts and error rates |
| `GET /health/live` | K8s liveness probe | Same as `/health` |
| `GET /health/ready` | K8s readiness probe | Same as `/health` |
| `GET /capabilities` | Ecosystem discovery | Capability manifest JSON |

## Evidence Collection
To collect live integration evidence at any time:
```bash
python live_integration_evidence.py
```
Evidence is saved to `review_packets/evidence/`.
