"""
simulation.py — Phase 5: Cross-System Communication Simulation

Demonstrates all four communication paths through the same gateway:
  1. Quantum  → Classical
  2. Classical → Quantum
  3. Hybrid   → Classical
  4. Hybrid   → Quantum

All paths use CommunicationGateway.send() with no special-case logic.
Produces a structured communication trace to stdout.
"""

import json
from gateway import CommunicationGateway, QuantumProducer, ClassicalProducer, HybridProducer, Receiver

SEED = 42


def _print_trace(label: str, response):
    trace = {
        "scenario":           label,
        "message_id":         response.message_id,
        "source_type":        response.source_type,
        "destination_type":   response.destination_type,
        "translation_status": response.translation_contract.translation_status,
        "confidence":         response.translation_contract.confidence,
        "uncertainty":        response.translation_contract.uncertainty,
        "payload_hash":       response.translation_contract.payload_hash[:16] + "...",
        "transport_status":   response.acknowledgement.transport_status,
        "is_accepted":        response.acknowledgement.is_accepted,
    }
    print(json.dumps(trace, indent=2))


def run_simulation():
    receiver = Receiver()
    gateway  = CommunicationGateway(receiver=receiver)

    quantum_producer   = QuantumProducer()
    classical_producer = ClassicalProducer()
    hybrid_producer    = HybridProducer()

    print("=" * 70)
    print("  CROSS-SYSTEM COMMUNICATION SIMULATION")
    print("  All paths traverse the same CommunicationGateway.send()")
    print("=" * 70)

    # ── Scenario 1: Quantum → Classical ─────────────────────────────────────
    print("\n[1] Quantum -> Classical")
    req = quantum_producer.produce(
        message="NODE_READY", noise=0.10, mode="entangled",
        seed=SEED, destination_type="CLASSICAL"
    )
    resp = gateway.send(req)
    _print_trace("Quantum->Classical", resp)

    # ── Scenario 2: Classical → Quantum ─────────────────────────────────────
    print("\n[2] Classical -> Quantum")
    req = classical_producer.produce(
        result={"status": "OPTIMIZED", "value": 42},
        confidence=0.95,
        destination_type="QUANTUM"
    )
    resp = gateway.send(req)
    _print_trace("Classical->Quantum", resp)

    # ── Scenario 3: Hybrid → Classical ──────────────────────────────────────
    print("\n[3] Hybrid -> Classical")
    q_req = quantum_producer.produce(
        message="SYNC", noise=0.08, mode="entangled",
        seed=SEED, destination_type="CLASSICAL"
    )
    c_req = classical_producer.produce(
        result={"mode": "SYNC", "priority": 1},
        confidence=0.88,
        destination_type="CLASSICAL"
    )
    req = hybrid_producer.produce(q_req, c_req, destination_type="CLASSICAL")
    resp = gateway.send(req)
    _print_trace("Hybrid->Classical", resp)

    # ── Scenario 4: Hybrid → Quantum ────────────────────────────────────────
    print("\n[4] Hybrid -> Quantum")
    q_req2 = quantum_producer.produce(
        message="LINK_UP", noise=0.05, mode="entangled",
        seed=SEED, destination_type="QUANTUM"
    )
    c_req2 = classical_producer.produce(
        result={"link": "UP", "latency_ms": 12},
        confidence=0.91,
        destination_type="QUANTUM"
    )
    req = hybrid_producer.produce(q_req2, c_req2, destination_type="QUANTUM")
    resp = gateway.send(req)
    _print_trace("Hybrid->Quantum", resp)

    print("\n" + "=" * 70)
    print("  SIMULATION COMPLETE - all 4 paths used the same gateway.send()")
    print("=" * 70)


if __name__ == "__main__":
    run_simulation()
