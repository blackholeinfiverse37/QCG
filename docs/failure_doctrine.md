# Communication Failure Doctrine

## Governing Principle
Every failure produces a structured `HALT:*` acknowledgement.
The gateway never raises an unhandled exception to the caller.
The system never silently swallows a failure.

---

## Failure Catalogue

### 1. Translation Failure
**What it is:** The adapter or translation layer cannot produce a valid contract from the producer output (e.g., noise spike destroys all signal, malformed input).

**Detection:** `TranslationError` raised by `translation_layer.translate()`, or adapter raises `ValueError`.

**Response:** `HALT:TRANSLATION_FAILURE:{reason}`

**Recovery posture:** Caller must retry with a new message or adjusted noise parameters. No state is mutated.

**Safe halt behavior:** The replay registry is not updated. The message_id is not marked as seen. Retry is safe.

---

### 2. Confidence Failure
**What it is:** The dominant bitstring confidence falls below `CORRUPTION_THRESHOLD` (0.40). The decoded message cannot be trusted.

**Detection:** `confidence < CORRUPTION_THRESHOLD` in `translation_layer.translate()` → `status = REJECTED`.

**Response:** `HALT:TRANSLATION_REJECTED:confidence={value}`

**Recovery posture:** Retry with lower noise or a different seed. The contract is never issued.

**Safe halt behavior:** No contract reaches the receiver. No replay entry is created.

---

### 3. Schema Mismatch
**What it is:** A `CommunicationRequest` or adapter output fails schema validation (missing fields, wrong types, empty payload, out-of-range confidence).

**Detection:** `ValueError` raised in `CommunicationRequest.__post_init__` or adapter `adapt()`.

**Response:** `HALT:GATEWAY_ERROR:ValueError`

**Recovery posture:** Caller must fix the input schema before retrying.

**Safe halt behavior:** Request is rejected before any state is touched.

---

### 4. Replay Detection
**What it is:** A `message_id` that has already been acknowledged is submitted again.

**Detection:** `message_id in self._seen` inside `Receiver.receive()`.

**Response:** `HALT:REPLAY_DETECTED`

**Recovery posture:** Do not retry with the same message_id. Generate a new request with a new message_id.

**Safe halt behavior:** The duplicate is silently rejected. The original acknowledgement is the system of record.

---

### 5. Unsupported Producer Type
**What it is:** `source_type` or `destination_type` is not one of `{QUANTUM, CLASSICAL, HYBRID}`.

**Detection:** `ValueError` in `CommunicationRequest.__post_init__`.

**Response:** `HALT:GATEWAY_ERROR:ValueError`

**Recovery posture:** Caller must use a supported producer type.

**Safe halt behavior:** No contract is created.

---

### 6. Transport Interruption
**What it is:** An unexpected exception occurs inside the gateway during translation or acknowledgement (e.g., internal bug, corrupted state).

**Detection:** Bare `except Exception` in `CommunicationGateway.send()`.

**Response:** `HALT:GATEWAY_ERROR:{ExceptionType}`

**Recovery posture:** Treat as a fatal error for that message. Log the exception type for diagnosis.

**Safe halt behavior:** The gateway remains operational for subsequent requests. No partial state is committed.

---

## Status Code Reference

| Status | Meaning | Retryable |
|--------|---------|-----------|
| `ACK:OK` | Accepted, confidence ≥ 0.70 | N/A |
| `ACK:DEGRADED:confidence=X` | Accepted, confidence in [0.40, 0.70) | N/A |
| `HALT:TRANSLATION_REJECTED:confidence=X` | Confidence < 0.40 | Yes (fix noise) |
| `HALT:TRANSLATION_FAILURE:*` | Adapter/translation exception | Yes (fix input) |
| `HALT:REPLAY_DETECTED` | Duplicate message_id | No |
| `HALT:GATEWAY_ERROR:*` | Schema or unexpected error | Yes (fix caller) |

---

## What the Gateway Guarantees

- A response is always returned (no unhandled exception).
- `HALT` responses are final for that message_id.
- Replay detection is idempotent and thread-safe.
- No partial contracts are committed to any registry.

## What the Gateway Does NOT Guarantee

- Quantum output correctness (probabilistic by nature).
- Message ordering across concurrent callers.
- Delivery retry (caller is responsible for retry logic).
- Persistence across process restarts.
