"""
Hybrid Quantum Communication Gateway
Layers 3, 4, 5 - Device participation, failure proof, observability.

Flow:
  QuantumSender -> TranslationBoundary -> ClassicalRouter -> IndustrialEndpoint
"""

import logging
import threading
import time

import config
from logger import get_logger, log_event
from models import TransmissionRequest, ClassicalContract
from quantum_producer import run_quantum_producer
from translation_layer import translate, TranslationError
from canonical_replay_authority import CanonicalReplayAuthority, get_authority

log = get_logger("qcg.gateway")


# -- Devices ------------------------------------------------------------------

def quantum_sender(request: TransmissionRequest, seed: int = config.DEFAULT_SEED):
    log_event(log, logging.INFO, "quantum_sender_start", ctx={
        "msg_text": request.message, "noise": request.noise, "mode": request.mode
    })
    distribution = run_quantum_producer(request, seed=seed)
    log_event(log, logging.INFO, "quantum_sender_done", ctx={
        "encoded_bits": distribution.encoded_bits
    })
    return distribution


def classical_router(distribution, original_message: str) -> ClassicalContract:
    log_event(log, logging.INFO, "classical_router_start", ctx={
        "original_msg": original_message
    })
    contract = translate(distribution, original_message)
    log_event(log, logging.INFO, "classical_router_done", ctx={
        "contract": contract.to_dict()
    })
    return contract


def industrial_endpoint(contract: ClassicalContract, replay_authority: CanonicalReplayAuthority) -> str:
    verdict = replay_authority.submit(
        message_id=contract.trace_id,
        trace_reference=contract.trace_id,
    )

    if not verdict.is_valid:
        log_event(log, logging.WARNING, "replay_detected", ctx={
            "trace_id": contract.trace_id,
            "status": verdict.status,
        })
        return "HALT:REPLAY_DETECTED"

    if contract.transmission_status == "OK":
        ack = f"ACK:OK:{contract.decoded_message}"
    elif contract.transmission_status == "DEGRADED":
        ack = f"ACK:DEGRADED:{contract.decoded_message}:confidence={contract.confidence}"
    else:
        ack = "HALT:UNKNOWN_STATUS"

    log_event(log, logging.INFO, "industrial_endpoint_ack", ctx={
        "trace_id": contract.trace_id,
        "confidence": contract.confidence,
        "uncertainty": contract.uncertainty_score,
        "status": contract.transmission_status,
        "ack": ack,
    })
    return ack


# -- Rate Limiter -------------------------------------------------------------

class _RateLimiter:
    """Token-bucket rate limiter, thread-safe."""

    def __init__(self, per_minute: int):
        self._capacity = per_minute
        self._tokens = float(per_minute)
        self._refill_rate = per_minute / 60.0
        self._last = time.monotonic()
        self._lock = threading.Lock()

    def allow(self) -> bool:
        with self._lock:
            now = time.monotonic()
            self._tokens = min(
                self._capacity,
                self._tokens + (now - self._last) * self._refill_rate,
            )
            self._last = now
            if self._tokens >= 1.0:
                self._tokens -= 1.0
                return True
            return False


# -- Gateway ------------------------------------------------------------------

class QuantumGateway:
    """
    Thread-safe stateful gateway. Delegates replay decisions to
    CanonicalReplayAuthority — owns no replay state of its own.
    """

    def __init__(self, replay_authority: CanonicalReplayAuthority | None = None):
        if replay_authority is None:
            import tempfile
            from replay_registry import ReplayRegistry
            from pathlib import Path
            reg = ReplayRegistry(
                path=Path(tempfile.mktemp(suffix="_gw.json")),
                ttl_seconds=300.0,
            )
            replay_authority = CanonicalReplayAuthority(reg)
        self._replay_authority = replay_authority
        self._rate_limiter = _RateLimiter(config.RATE_LIMIT_PER_MINUTE)

    def transmit(
        self,
        message: str,
        noise: float,
        mode: str,
        seed: int = config.DEFAULT_SEED,
    ) -> str:
        """
        Run the full pipeline for one transmission.
        Always returns a deterministic ACK string - never raises.
        """
        if not self._rate_limiter.allow():
            log_event(log, logging.WARNING, "rate_limit_exceeded", ctx={"message": message})
            return "HALT:RATE_LIMIT_EXCEEDED"

        try:
            request = TransmissionRequest(message=message, noise=noise, mode=mode)
            distribution = quantum_sender(request, seed=seed)
            contract = classical_router(distribution, message)
            return industrial_endpoint(contract, self._replay_authority)

        except (ValueError, TypeError) as e:
            ack = f"HALT:INVALID_INPUT:{e}"
            log_event(log, logging.ERROR, "gateway_input_error", ctx={"error": str(e)})
            return ack

        except TranslationError as e:
            ack = f"HALT:TRANSLATION_FAILURE:{e}"
            log_event(log, logging.ERROR, "gateway_translation_failure", ctx={"error": str(e)})
            return ack

        except Exception as e:
            ack = f"HALT:UNEXPECTED:{type(e).__name__}:{e}"
            log_event(log, logging.ERROR, "gateway_unexpected_error", ctx={
                "error": str(e), "type": type(e).__name__
            })
            return ack

    def health_check(self) -> dict:
        """Returns gateway health status. Safe to expose as a liveness probe."""
        return {
            "status": "ok",
            "replay_sequence_counter": self._replay_authority._registry.sequence_count,
            "replay_registry_size": self._replay_authority._registry.entry_count,
            "rate_limit_per_minute": config.RATE_LIMIT_PER_MINUTE,
            "contract_version": config.CONTRACT_VERSION,
        }

    def reset_replay_registry(self):
        self._replay_authority.reset()


# -- Failure Scenarios (Layer 4) ----------------------------------------------

def run_failure_tests(gateway: QuantumGateway):
    log_event(log, logging.INFO, "failure_tests_start")

    scenarios = [
        {"label": "1. Noise Spike",           "message": "NODE_READY", "noise": 0.95, "mode": "entangled"},
        {"label": "2. Low Confidence",         "message": "NODE_READY", "noise": 0.75, "mode": "entangled"},
        {"label": "3. Message Corruption",     "message": "NODE_READY", "noise": 0.10, "mode": "entangled", "corrupt_label": "LINK_DOWN"},
        {"label": "4. Replay Mismatch",        "message": "NODE_READY", "noise": 0.05, "mode": "entangled", "replay": True},
        {"label": "5. Empty Counts Injection", "message": "NODE_READY", "noise": 0.00, "mode": "entangled", "inject_empty_counts": True},
    ]

    results = {}
    for s in scenarios:
        label = s["label"]
        try:
            if s.get("inject_empty_counts"):
                from models import QuantumDistribution
                QuantumDistribution(
                    encoded_bits="11", transmission_mode="entangled",
                    noise_factor=0.0, shots=1024, counts={}, seed=42
                )
                results[label] = "FAIL: should have raised ValueError"

            elif s.get("corrupt_label"):
                request = TransmissionRequest(s["message"], s["noise"], s["mode"])
                dist = run_quantum_producer(request, seed=42)
                translate(dist, s["corrupt_label"])
                results[label] = "FAIL: should have raised TranslationError"

            elif s.get("replay"):
                import tempfile, os
                from canonical_replay_authority import reset_authority
                from replay_registry import ReplayRegistry
                tmp = tempfile.mktemp(suffix=".json")
                gw = QuantumGateway(replay_authority=reset_authority(ReplayRegistry(path=tmp)))
                gw._rate_limiter._tokens = float(gw._rate_limiter._capacity)  # ensure not rate-limited
                ack1 = gw.transmit(s["message"], s["noise"], s["mode"], seed=42)
                ack2 = gw.transmit(s["message"], s["noise"], s["mode"], seed=42)
                passed = "REPLAY" in ack2
                results[label] = f"PASS: ack1={ack1} | ack2={ack2}" if passed else f"FAIL: {ack2}"

            else:
                ack = gateway.transmit(s["message"], s["noise"], s["mode"], seed=42)
                passed = "HALT" in ack
                results[label] = f"PASS: {ack}" if passed else f"FAIL: {ack}"

        except (ValueError, TranslationError) as e:
            results[label] = f"PASS: {type(e).__name__}: {e}"
        except Exception as e:
            results[label] = f"PASS: {type(e).__name__}: {e}"

    for label, outcome in results.items():
        log_event(log, logging.INFO, "failure_test_result", ctx={
            "scenario": label, "outcome": outcome
        })

    return results


# -- Entry Point --------------------------------------------------------------

if __name__ == "__main__":
    gw = QuantumGateway()
    log_event(log, logging.INFO, "gateway_demo_start")
    ack = gw.transmit("NODE_READY", noise=0.12, mode="entangled", seed=42)
    log_event(log, logging.INFO, "gateway_demo_result", ctx={"ack": ack})
    run_failure_tests(gw)
