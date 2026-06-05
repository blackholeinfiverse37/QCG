"""
contract_semantics.py — Phase 2: Contract Determinism vs Quantum Behaviour

Proves two things:
  1. DETERMINISM: same seed + same inputs + same translation policy
                  → identical operational contract every time.
  2. CONVERGENCE: different probabilistic quantum distributions
                  can still map to the SAME operational contract
                  because the contract doctrine absorbs bounded variance.

This is the key philosophical/technical objective:
  Quantum behaviour is variable. Contract doctrine is not.
"""

from dataclasses import dataclass

import config
from models import TransmissionRequest, QuantumDistribution
from quantum_producer import run_quantum_producer
from translation_layer import translate, TranslationError


# ---------------------------------------------------------------------------
# Contract identity — the fields that define "same contract"
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ContractIdentity:
    """
    Minimal fingerprint of a contract for semantic comparison.
    Two contracts are semantically equivalent if their identity matches.
    """
    transmission_status: str    # OK | DEGRADED
    decoded_message:     str
    contract_version:    str

    def __str__(self) -> str:
        return f"{self.transmission_status}:{self.decoded_message}:{self.contract_version}"


# ---------------------------------------------------------------------------
# Proof 1 — Determinism
# ---------------------------------------------------------------------------

def prove_determinism(
    message: str = "NODE_READY",
    noise: float = 0.12,
    mode: str = "entangled",
    seed: int = config.DEFAULT_SEED,
    runs: int = 5,
) -> dict:
    """
    Run the full pipeline N times with identical inputs.
    Proves: same seed → identical contract every run.

    Returns
    -------
    {
        "passed": bool,
        "runs": int,
        "reference_identity": str,
        "all_identities": list[str],
        "mismatches": list[int],   # run indices that differed (1-based)
    }
    """
    request = TransmissionRequest(message=message, noise=noise, mode=mode)
    identities = []

    for _ in range(runs):
        dist = run_quantum_producer(request, seed=seed)
        try:
            contract = translate(dist, message)
            identity = ContractIdentity(
                transmission_status=contract.transmission_status,
                decoded_message=contract.decoded_message,
                contract_version=contract.contract_version,
            )
        except TranslationError:
            identity = ContractIdentity("REJECTED", "REJECTED", config.CONTRACT_VERSION)
        identities.append(str(identity))

    reference  = identities[0]
    mismatches = [i + 1 for i, v in enumerate(identities) if v != reference]

    return {
        "passed":             len(mismatches) == 0,
        "runs":               runs,
        "reference_identity": reference,
        "all_identities":     identities,
        "mismatches":         mismatches,
    }


# ---------------------------------------------------------------------------
# Proof 2 — Convergence
# ---------------------------------------------------------------------------

def _make_distribution(counts: dict, noise_factor: float, seed: int) -> QuantumDistribution:
    """Build a synthetic QuantumDistribution with given counts."""
    return QuantumDistribution(
        encoded_bits="11",  # correct encoding for NODE_READY (sha256 hash mod 4 = 3 = "11")
        transmission_mode="entangled",
        noise_factor=noise_factor,
        shots=sum(counts.values()),
        counts=counts,
        seed=seed,
    )


def prove_convergence(message: str = "NODE_READY") -> dict:
    """
    Prove that two DIFFERENT quantum distributions produce the SAME contract.

    Distribution A: high-confidence, low noise   (counts strongly peaked)
    Distribution B: lower-confidence, more noise (counts more spread)

    Both decode to the same dominant bitstring → same ContractIdentity.

    Returns
    -------
    {
        "passed":        bool,
        "identity_A":    str,
        "identity_B":    str,
        "same_contract": bool,
        "explanation":   str,
    }
    """
    # Both distributions peak on "11" (the correct encoding for NODE_READY).
    # Distribution A: 920/1024 — high confidence, low noise
    dist_A = _make_distribution({"11": 920, "00": 40, "01": 34, "10": 30}, noise_factor=0.05, seed=1)
    # Distribution B: 760/1024 — lower confidence, more noise (still above threshold)
    dist_B = _make_distribution({"11": 760, "00": 100, "01": 90, "10": 74}, noise_factor=0.30, seed=2)

    def _identity(dist: QuantumDistribution) -> ContractIdentity:
        try:
            contract = translate(dist, message)
            return ContractIdentity(
                transmission_status=contract.transmission_status,
                decoded_message=contract.decoded_message,
                contract_version=contract.contract_version,
            )
        except TranslationError:
            return ContractIdentity("REJECTED", "REJECTED", config.CONTRACT_VERSION)

    id_A = _identity(dist_A)
    id_B = _identity(dist_B)
    same = str(id_A) == str(id_B)

    return {
        "passed":        same,
        "identity_A":    str(id_A),
        "identity_B":    str(id_B),
        "same_contract": same,
        "explanation":   (
            "Contract doctrine absorbed bounded variance: "
            "both distributions mapped to the same operational identity."
            if same else
            "Distributions produced different contract identities."
        ),
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("\n=== PROOF 1: DETERMINISM ===")
    det = prove_determinism()
    for k, v in det.items():
        print(f"  {k}: {v}")
    print(f"  VERDICT: {'PASS' if det['passed'] else 'FAIL'}")

    print("\n=== PROOF 2: CONVERGENCE ===")
    conv = prove_convergence()
    for k, v in conv.items():
        print(f"  {k}: {v}")
    print(f"  VERDICT: {'PASS' if conv['passed'] else 'FAIL'}")
