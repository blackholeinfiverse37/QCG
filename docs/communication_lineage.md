# Communication Lineage

## Purpose
This document answers: **What exactly happened to a message from creation to acknowledgement?**
Every hop is traceable. The full lineage is reconstructable from `trace_reference` alone.

---

## Lineage Chain

```
[1] Message Lineage
      Producer creates raw output
      ↓ trace anchor: producer-type + seed + content hash

[2] Translation Lineage
      Adapter converts raw output → CommunicationRequest
      ↓ trace anchor: message_id = UUID-5(source_type, content, seed)

[3] Gateway Lineage
      CommunicationGateway.send() receives CommunicationRequest
      ↓ trace anchor: message_id logged at gateway_send event

[4] Translation Contract Lineage
      TranslationContract.from_request() creates immutable contract
      ↓ trace anchor: payload_hash = SHA-256(payload)
      ↓ translation_status assigned (OK | DEGRADED | REJECTED)

[5] Acknowledgement Lineage
      Receiver.receive() issues AcknowledgementContract
      ↓ trace anchor: message_id marked as seen in replay guard
      ↓ transport_status assigned (ACK:OK | ACK:DEGRADED | HALT:*)

[6] Response Lineage
      CommunicationResponse bundles translation_contract + acknowledgement
      ↓ trace anchor: message_id ties all hops together
```

---

## Message Lineage

| Field | Source | Purpose |
|-------|--------|---------|
| `message_id` | `make_message_id(source_type, content, seed)` | Primary trace key |
| `source_type` | Declared by producer | Identifies origin class |
| `payload` | Raw producer output | Content being communicated |
| `confidence` | Derived (quantum) or asserted (classical) | Quality signal |
| `trace_reference` | Upstream contract trace_id | Links to prior hop |

Reconstruction: Given `message_id`, look up the `gateway_send` log event → retrieve full request context.

---

## Translation Lineage

| Field | Source | Purpose |
|-------|--------|---------|
| `payload_hash` | `SHA-256(payload)` | Content-addressed fingerprint |
| `translation_status` | Confidence thresholds | OK / DEGRADED / REJECTED |
| `uncertainty` | `1.0 - confidence` | Noise contribution |
| `created_at` | UTC timestamp | Temporal anchor |

Reconstruction: Given `payload_hash`, verify the payload was not modified between request and contract.

---

## Acknowledgement Lineage

| Field | Source | Purpose |
|-------|--------|---------|
| `transport_status` | `resolve_transport_status()` | Final disposition |
| `is_accepted` | `transport_status.startswith("ACK:")` | Boolean acceptance |
| `is_halted` | `transport_status.startswith("HALT:")` | Boolean halt |
| `issued_at` | UTC timestamp | When ACK was issued |

Reconstruction: Given `message_id`, look up the `gateway_response` log event → retrieve transport_status.

---

## Gateway Lineage

| Event | File | What is logged |
|-------|------|----------------|
| `gateway_send` | `gateway.py` | message_id, source_type, destination_type, confidence |
| `gateway_response` | `gateway.py` | message_id, transport_status, translation_status |
| `quantum_adapter_complete` | `adapters.py` | trace_id, confidence |
| `classical_adapter_complete` | `adapters.py` | trace_id, confidence |
| `hybrid_adapter_complete` | `adapters.py` | trace_id, primary_producer, confidence |
| `translation_complete` | `translation_layer.py` | trace_id, dominant_bits, confidence, status |

---

## Full Reconstruction Example

Given only `message_id = "a3f1..."`:

1. Search logs for `"message_id": "a3f1..."` at `gateway_send` → get `source_type`, `confidence`
2. Search for `"message_id": "a3f1..."` at `gateway_response` → get `transport_status`
3. Use `trace_reference` from the request to look up the adapter log → get `payload_hash`
4. Use `payload_hash` to verify payload integrity
5. Check if `message_id` appears twice in `gateway_response` → replay detected

**Result:** Full message lifecycle is reconstructable from logs alone, without querying any runtime state.

---

## Lineage Guarantees

- Every message that enters the gateway has a `message_id` logged.
- Every response has the same `message_id` logged.
- `payload_hash` is computed deterministically — same payload always produces the same hash.
- `trace_reference` chains back to the producing adapter's trace_id.
- Replay detection is the only gateway-side state mutation, and it is logged.

## Lineage Does NOT Cover

- What happened before the producer called `produce()` (pre-gateway state is caller responsibility).
- Network-level delivery confirmation (the gateway is in-process).
- Cross-process or cross-node lineage (would require distributed trace propagation).
