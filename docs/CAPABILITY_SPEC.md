# QCG Capability Specification

This document outlines the specific, bounded capabilities offered by the Quantum Communication Gateway (QCG) to the TANTRA ecosystem, exposed via the `/capabilities` manifest endpoint.

## 1. ReplayVerification (cap-replay-verif)

**Scope:** SYSTEM
**Status:** ACTIVE
**Owner:** QCG_TRUST_LAYER

**Description:**
Provides a deterministic decision on whether an incoming artifact has been seen before or if its sequence is out of bounds.

**Interface:**
- **Inputs:** `message_id` (string), `issued_at` (float)
- **Outputs:** `is_valid` (boolean), `status` (string), `sequence_number` (int), `verification_hash` (string)

**Authority Limits:**
- ONLY owns occurrence registration and duplicate/stale rejection.
- DOES NOT own payload validation or semantic verification.

## 2. TrustVerification (cap-trust-verif)

**Scope:** SYSTEM
**Status:** ACTIVE
**Owner:** QCG_TRUST_LAYER

**Description:**
Validates the ECDSA cryptographic signature attached to the contract against registered public identities, ensuring the producer is authorized for the declared execution role.

**Interface:**
- **Inputs:** `contract_dict` (JSON)
- **Outputs:** `passed` (boolean), `halt_signal` (string), `reason` (string)

**Authority Limits:**
- ONLY owns identity validation, signature checking, and role authorization.
- DOES NOT issue keys or revoke identities natively (delegated to KESHAV).

## 3. DeterministicExecution (cap-execution)

**Scope:** SYSTEM
**Status:** ACTIVE
**Owner:** QCG_TRUST_LAYER

**Description:**
Provides a strictly deterministic "blind execution" engine that processes valid contracts to produce an immutable runtime path hash.

**Interface:**
- **Inputs:** `contract_dict` (JSON)
- **Outputs:** `ack` (string), `runtime_hash` (string), `contract_trace_id` (string)

**Authority Limits:**
- ONLY owns blind execution logic and hash result derivation.
- DOES NOT govern policy or authorization.

## 4. ByzantineConsensus (cap-consensus)

**Scope:** SYSTEM
**Status:** ACTIVE
**Owner:** QCG_TRUST_LAYER

**Description:**
Aggregates independent simulated distributed nodes to perform Byzantine consensus over the execution results, requiring a 66% quorum to emit a `final_hash`.

**Interface:**
- **Inputs:** `contract_dict` (JSON), `producer_public_key` (string)
- **Outputs:** `consensus_reached` (boolean), `agreement_percentage` (float), `final_hash` (string)

**Authority Limits:**
- ONLY owns quorum calculation and node attestation logic.
- DOES NOT perform state mutation outside of the consensus ledger.
