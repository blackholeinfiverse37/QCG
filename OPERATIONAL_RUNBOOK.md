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

## Restarting Services
When restarting, you can safely kill processes using standard termination (SIGTERM). Do **NOT** forcefully kill (`SIGKILL`) unless the service hangs, to preserve the evidence ledger structure.
