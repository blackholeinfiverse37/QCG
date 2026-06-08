# Communication Taxonomy

## 1. Participant Definitions

### Quantum Producer
A participant whose output originates from a probabilistic quantum simulation (Qiskit/Aer).
Produces a `QuantumDistribution` — a count map over bitstrings.
Cannot guarantee deterministic output. Confidence is derived, not asserted.

### Classical Producer
A participant whose output originates from a deterministic classical computation.
Produces a structured dict with `result`, `confidence`, and optional `metadata`.
Confidence is asserted directly by the producer.

### Hybrid Producer
A participant that merges a quantum contract and a classical contract into a single contract.
Uses a confidence-weighted selection strategy.
Producer type is `HYBRID`; the gateway treats it identically to any other producer.

### Receiver
A participant that consumes a `CommunicationResponse` and issues an `AcknowledgementContract`.
The receiver does not care about source type — it only reads the normalized contract.

### Translator
The component that converts producer-specific output into a `CommunicationRequest`.
In this system: `QuantumAdapter`, `ClassicalAdapter`, `HybridAdapter` in `adapters.py`.

### Gateway
The component that accepts any `CommunicationRequest`, normalizes it, routes it to the receiver,
and returns a `CommunicationResponse`. Source-type agnostic.
Implemented in `gateway.py`.

### Contract
An immutable, versioned, schema-validated record that carries communication state across boundaries.
Two contract types exist:
- `TranslationContract` — the normalized form produced by translation.
- `AcknowledgementContract` — the deterministic receipt issued by the receiver.

### Acknowledgement
A deterministic, structured receipt from the receiver confirming the message disposition.
Status values: `ACK:OK`, `ACK:DEGRADED`, `HALT:*`.

### Confidence
A float in `[0.0, 1.0]` representing certainty in the decoded message.
- `>= 0.70` → OK
- `[0.40, 0.70)` → DEGRADED
- `< 0.40` → REJECTED

### Uncertainty
`1.0 - confidence`. Quantifies the noise contribution to the decoded output.

---

## 2. Communication Lifecycle

```
[Producer]
    │  raw output (QuantumDistribution | dict | hybrid pair)
    ▼
[Translator / Adapter]
    │  CommunicationRequest (normalized, source-type-erased)
    ▼
[Gateway]
    │  validates schema, checks replay guard, applies rate limit
    ▼
[Translation]
    │  TranslationContract (confidence scored, status assigned)
    ▼
[Contract]
    │  immutable, versioned, trace-identified
    ▼
[Receiver]
    │  consumes contract, issues structured acknowledgement
    ▼
[AcknowledgementContract]
    │  transport_status, translation_status, confidence, trace_reference
    ▼
[Replay Surface]
    │  trace_reference → deterministic replay key
    │  duplicate trace_reference → HALT:REPLAY_DETECTED
    ▼
[Observability]
    │  structured log event per hop
    │  full lineage reconstructable from trace_reference
```

### Hop Summary

| Hop | Name | What crosses the boundary |
|-----|------|--------------------------|
| 1 | Message | Raw producer output |
| 2 | Transport | Normalized `CommunicationRequest` |
| 3 | Translation | `TranslationContract` with confidence |
| 4 | Contract | Immutable, versioned, hash-identified |
| 5 | Acknowledgement | `AcknowledgementContract` with status |
| 6 | Replay surface | `trace_reference` used as idempotency key |
| 7 | Observability | Structured log at every hop |
