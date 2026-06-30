# Network Architecture

The QCG runtime abstracts network connectivity using a plugin architecture in `transport.py`. This ensures high performance, resilience, and adaptability to deployment constraints.

## Transport Modes
Controlled by `QCG_TRANSPORT_TYPE` in configuration:
- **tcp**: High throughput socket-based communication. Uses binary length-prefixing.
- **uds**: Unix Domain Sockets for ultra-low latency intra-host operations (falls back to local TCP on Windows).
- *(Planned)*: `grpc`, `http`, `nats`, `zeromq`.

## Circuit Breaking & Resilience
The transport layer utilizes an exponential backoff policy and a **Circuit Breaker** to prevent cascading failures.
- **Max Retries**: Transport connection logic attempts 10 exponential backoff retries.
- **Breaker Threshold**: Fails open after 5 consecutive failures, halting local execution and surfacing errors fast.

## Observability & Health
Each service runs a secondary HTTP daemon on `<port> + 100` serving:
- `/health`: Liveliness and uptime probe.
- `/discovery`: Full capability payload including dependencies and endpoints.
- `/metrics`: Prometheus metrics strings exposing internal queue states and domain metrics.
- `/otel/v1/traces/{trace_id}`: OpenTelemetry standard resource spans.
