# Failure Recovery Guide

This document maps out circuit breaking, failure conditions, and recovery logic in the QCG Distributed Runtime.

## 1. Network Disconnection
If a downstream dependency (e.g. `Trust Service`) crashes, the upstream service (`Execution Service`) will attempt exponential backoff for 10 cycles when trying to send data via the `TCPTransportSender`.

## 2. Circuit Breaker Behavior
After 5 consecutive connection or socket errors, the `CircuitBreaker` class transitions into the **OPEN** state.
- **Result:** Fast failures. The system rejects requests instantly instead of blocking on network timeouts.
- **Recovery:** After a timeout (default 10s), the breaker shifts to **HALF_OPEN**. If the next connection succeeds, it closes. If it fails, it resets the timer.

## 3. Heartbeat Monitoring
The runtime services employ a heartbeat background thread. If the dependent registry or services fail to respond, the heartbeat thread logs a warning. Operational dashboards should track these logs via `/metrics` `failures_total`.

## 4. Graceful Shutdown
Upon receiving `SIGINT` or `SIGTERM`, a `_shutdown_event` triggers.
- Services finish processing their in-flight message.
- Loop bounds are cleanly exited instead of forcibly tearing down sockets mid-stream.
- This prevents corrupted execution states in the `EvidenceLedger`.
