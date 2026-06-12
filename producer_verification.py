"""
producer_verification.py — Phase 4: Trust-Aware Communication

Eliminates blind trust in producer declarations by verifying:
  1. Producer identity   — producer_id is registered and its public key is known
  2. Signature validity  — producer_signature and contract_signature are valid ECDSA
  3. Source authenticity — producer_type matches the registered role for that producer_id

Failure Modes
-------------
UNVERIFIED_PRODUCER  — producer_id missing or not registered; no key on record
INVALID_SIGNATURE    — signature present but ECDSA verification fails (tampered/forged)
TRUST_FAILURE        — identity known but source_type/role mismatch or provenance error

On any failure the gateway halts safely. No contract is executed for an
unverified producer.

Integration
-----------
ProducerVerificationLayer sits between the IPC queue and RuntimeCore in the
execution process. It is also usable standalone by the CommunicationGateway
for communication-layer trust enforcement.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from node_identity import NodeIdentity, verify_node_proof, NodeProof
from provenance import ProvenanceStatus, verify_contract_provenance
from execution_contract import ComputationExecutionContract

import hashlib
import json


# ---------------------------------------------------------------------------
# Failure mode constants
# ---------------------------------------------------------------------------

class VerificationFailure:
    UNVERIFIED_PRODUCER = "UNVERIFIED_PRODUCER"   # not registered / no key
    INVALID_SIGNATURE   = "INVALID_SIGNATURE"     # ECDSA verification failed
    TRUST_FAILURE       = "TRUST_FAILURE"         # role/type mismatch or provenance error


# ---------------------------------------------------------------------------
# ProducerRegistry
# ---------------------------------------------------------------------------

class ProducerRegistry:
    """
    In-memory registry of known producer identities.

    Maps producer_id -> (NodeIdentity, allowed_producer_types).
    The registry is the authority on which producer_ids are trusted and
    what producer_types they are permitted to emit.
    """

    def __init__(self):
        # producer_id -> (NodeIdentity, frozenset of allowed producer_types)
        self._registry: dict[str, tuple[NodeIdentity, frozenset[str]]] = {}

    def register(
        self,
        identity: NodeIdentity,
        allowed_types: set[str] | None = None,
    ) -> None:
        """
        Register a producer identity with its permitted producer_types.

        If allowed_types is None, the node_role is used to derive a default:
          QUANTUM_PRODUCER  → {"QUANTUM"}
          CLASSICAL_PRODUCER → {"CLASSICAL"}
          HYBRID_PRODUCER   → {"HYBRID", "QUANTUM", "CLASSICAL"}
          anything else     → {"CLASSICAL", "QUANTUM", "HYBRID"}
        """
        if allowed_types is None:
            role = identity.node_role.upper()
            if "QUANTUM" in role and "HYBRID" not in role:
                allowed_types = {"QUANTUM"}
            elif "CLASSICAL" in role and "HYBRID" not in role:
                allowed_types = {"CLASSICAL"}
            elif "HYBRID" in role:
                allowed_types = {"HYBRID", "QUANTUM", "CLASSICAL"}
            else:
                allowed_types = {"CLASSICAL", "QUANTUM", "HYBRID"}
        self._registry[identity.node_id] = (identity, frozenset(allowed_types))

    def lookup(self, producer_id: str) -> tuple[NodeIdentity, frozenset[str]] | None:
        return self._registry.get(producer_id)

    def is_registered(self, producer_id: str) -> bool:
        return producer_id in self._registry

    def public_key(self, producer_id: str) -> str | None:
        entry = self._registry.get(producer_id)
        return entry[0].public_key if entry else None

    def allowed_types(self, producer_id: str) -> frozenset[str]:
        entry = self._registry.get(producer_id)
        return entry[1] if entry else frozenset()


# ---------------------------------------------------------------------------
# VerificationResult
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class VerificationResult:
    """
    Outcome of a producer verification attempt.

    Fields
    ------
    passed          : True only when identity, signature, and role all verify.
    failure_mode    : One of VerificationFailure.* constants; empty string on pass.
    producer_id     : The producer_id from the contract (may be empty if absent).
    producer_type   : The producer_type from the contract.
    reason          : Human-readable explanation of the failure (empty on pass).
    """
    passed:        bool
    failure_mode:  str   # "" | UNVERIFIED_PRODUCER | INVALID_SIGNATURE | TRUST_FAILURE
    producer_id:   str
    producer_type: str
    reason:        str

    @property
    def is_trusted(self) -> bool:
        return self.passed

    def halt_signal(self) -> str:
        """Return the HALT string to embed in an ACK when verification fails."""
        return f"HALT:{self.failure_mode}:{self.reason}" if not self.passed else ""


# ---------------------------------------------------------------------------
# ProducerVerificationLayer
# ---------------------------------------------------------------------------

class ProducerVerificationLayer:
    """
    Verifies producer identity, signature, and source authenticity.

    Usage
    -----
    registry = ProducerRegistry()
    registry.register(producer.identity)

    verifier = ProducerVerificationLayer(registry)
    result = verifier.verify(contract)

    if not result.passed:
        return result.halt_signal()   # "HALT:INVALID_SIGNATURE:..."
    """

    def __init__(self, registry: ProducerRegistry):
        self._registry = registry

    def verify(self, contract: ComputationExecutionContract) -> VerificationResult:
        """
        Full three-step verification of a contract's producer.

        Steps
        -----
        1. Identity check  — producer_id present and registered
        2. Signature check — ECDSA verification of producer_signature + contract_signature
        3. Trust check     — producer_type within allowed types for this producer_id
        """
        pid = contract.producer_id
        ptype = contract.producer_type

        # ------------------------------------------------------------------
        # Step 1: Identity — producer_id must be present and registered
        # ------------------------------------------------------------------
        if not pid:
            return VerificationResult(
                passed=False,
                failure_mode=VerificationFailure.UNVERIFIED_PRODUCER,
                producer_id=pid,
                producer_type=ptype,
                reason="producer_id is missing from contract",
            )

        if not self._registry.is_registered(pid):
            return VerificationResult(
                passed=False,
                failure_mode=VerificationFailure.UNVERIFIED_PRODUCER,
                producer_id=pid,
                producer_type=ptype,
                reason=f"producer_id '{pid}' is not registered",
            )

        public_key = self._registry.public_key(pid)

        # ------------------------------------------------------------------
        # Step 2: Signature — ECDSA must verify
        # ------------------------------------------------------------------
        if not contract.producer_signature or not contract.contract_signature:
            return VerificationResult(
                passed=False,
                failure_mode=VerificationFailure.INVALID_SIGNATURE,
                producer_id=pid,
                producer_type=ptype,
                reason="producer_signature or contract_signature is missing",
            )

        provenance_status = verify_contract_provenance(contract, public_key)

        if provenance_status == ProvenanceStatus.TAMPERED:
            return VerificationResult(
                passed=False,
                failure_mode=VerificationFailure.INVALID_SIGNATURE,
                producer_id=pid,
                producer_type=ptype,
                reason="ECDSA signature verification failed — contract may be tampered",
            )

        if provenance_status == ProvenanceStatus.UNVERIFIED:
            return VerificationResult(
                passed=False,
                failure_mode=VerificationFailure.INVALID_SIGNATURE,
                producer_id=pid,
                producer_type=ptype,
                reason="provenance unverifiable — signatures absent or malformed",
            )

        # ------------------------------------------------------------------
        # Step 3: Trust — producer_type must match registered allowed types
        # ------------------------------------------------------------------
        allowed = self._registry.allowed_types(pid)
        if ptype not in allowed:
            return VerificationResult(
                passed=False,
                failure_mode=VerificationFailure.TRUST_FAILURE,
                producer_id=pid,
                producer_type=ptype,
                reason=(
                    f"producer_type '{ptype}' not permitted for producer '{pid}'. "
                    f"Allowed: {sorted(allowed)}"
                ),
            )

        return VerificationResult(
            passed=True,
            failure_mode="",
            producer_id=pid,
            producer_type=ptype,
            reason="",
        )
