"""
integration_interfaces.py — Phase 2: Standardized Integration Interfaces

Provides deterministic, versioned, and reusable interfaces for external systems
(e.g., NICAI, InsightFlow, Pravah) to attach to the QCG trust layer.
"""

import time
import json
import hashlib
from typing import Dict, Any, List

import config
from canonical_replay_authority import CanonicalReplayAuthority
from execution_contract import ComputationExecutionContract
from producer_verification import ProducerVerificationLayer, VerificationResult
from runtime_core import RuntimeCore
from consensus_simulation import ConsensusEngine, DistributedConsensusNode
from replay_registry import ReplayRegistry

class StandardizedInterface:
    """Base class ensuring all interfaces are versioned and deterministic."""
    VERSION = "1.0.0"


class CapabilityDiscoveryInterface(StandardizedInterface):
    """Provides a deterministic capability manifest for BHIV attachment."""
    
    @classmethod
    def discover_capabilities(cls) -> Dict[str, Any]:
        return {
            "owner": "QCG_TRUST_LAYER",
            "version": cls.VERSION,
            "capabilities": [
                {
                    "capability_id": "cap-replay-verif",
                    "capability_name": "ReplayVerification",
                    "scope": "SYSTEM",
                    "status": "ACTIVE",
                    "interface": {
                        "inputs": ["message_id", "issued_at"],
                        "outputs": ["is_valid", "status", "sequence_number", "verification_hash"]
                    },
                    "authority_limits": ["Occurrence registration", "Duplicate/stale rejection"]
                },
                {
                    "capability_id": "cap-trust-verif",
                    "capability_name": "TrustVerification",
                    "scope": "SYSTEM",
                    "status": "ACTIVE",
                    "interface": {
                        "inputs": ["contract_dict"],
                        "outputs": ["passed", "halt_signal", "reason"]
                    },
                    "authority_limits": ["Identity validation", "Signature check", "Role authorization"]
                },
                {
                    "capability_id": "cap-execution",
                    "capability_name": "DeterministicExecution",
                    "scope": "SYSTEM",
                    "status": "ACTIVE",
                    "interface": {
                        "inputs": ["contract_dict"],
                        "outputs": ["ack", "runtime_hash", "contract_trace_id"]
                    },
                    "authority_limits": ["Blind execution", "Result derivation"]
                },
                {
                    "capability_id": "cap-consensus",
                    "capability_name": "ByzantineConsensus",
                    "scope": "SYSTEM",
                    "status": "ACTIVE",
                    "interface": {
                        "inputs": ["contract_dict", "producer_public_key"],
                        "outputs": ["consensus_reached", "agreement_percentage", "final_hash"]
                    },
                    "authority_limits": ["Quorum calculation", "Node attestation"]
                }
            ]
        }


class HealthStatusInterface(StandardizedInterface):
    """Provides structured health, readiness, and dependency metrics."""
    
    def __init__(self, registry: ReplayRegistry):
        self.registry = registry
        self.start_time = time.time()
        self.processed_count = 0
        self.error_count = 0

    def record_process(self, success: bool):
        self.processed_count += 1
        if not success:
            self.error_count += 1

    def get_health(self) -> Dict[str, Any]:
        uptime = time.time() - self.start_time
        return {
            "status": "UP",
            "version": self.VERSION,
            "readiness": "READY",
            "dependencies": {
                "replay_registry": "ONLINE",
                "consensus_nodes": "ONLINE"
            },
            "metrics": {
                "uptime_seconds": round(uptime, 2),
                "total_processed": self.processed_count,
                "error_rate": round(self.error_count / max(1, self.processed_count), 4),
                "registry_size": self.registry.entry_count
            }
        }


class ReplayVerifierInterface(StandardizedInterface):
    """Interface for Replay Validation via Live API."""
    
    def __init__(self, authority=None):
        self.authority = authority
        self.replay_endpoint = "http://127.0.0.1:8002/replay/verify"

    def verify_replay(self, message_id: str, issued_at: float) -> Dict[str, Any]:
        import requests
        try:
            req_data = {"trace_id": message_id, "issued_at": issued_at}
            resp = requests.post(self.replay_endpoint, json=req_data, timeout=5)
            resp.raise_for_status()
            data = resp.json()
            return {
                "is_valid": data["is_valid"],
                "status": data["status"],
                "sequence_number": data["sequence_number"],
                "verification_hash": None
            }
        except requests.RequestException as e:
            if self.authority:
                verdict = self.authority.submit(message_id, issued_at)
                return {
                    "is_valid": verdict.is_valid,
                    "status": verdict.status,
                    "sequence_number": verdict.sequence_number,
                    "verification_hash": verdict.lineage_record.verification_hash if verdict.is_valid else None
                }
            return {"is_valid": False, "status": f"API_ERROR: {str(e)}", "sequence_number": -1, "verification_hash": None}


class TrustVerifierInterface(StandardizedInterface):
    """Interface for Trust and GC Governance Verification via Live API."""
    
    def __init__(self, verifier=None):
        self.verifier = verifier
        self.gc_endpoint = "http://127.0.0.1:8002/governance/verify"

    def verify_trust(self, contract: ComputationExecutionContract) -> Dict[str, Any]:
        import requests
        try:
            req_data = {"contract": contract.to_dict()}
            resp = requests.post(self.gc_endpoint, json=req_data, timeout=5)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            if self.verifier:
                result = self.verifier.verify(contract)
                return {
                    "passed": result.passed,
                    "halt_signal": result.halt_signal(),
                    "reason": result.reason
                }
            return {"passed": False, "halt_signal": f"HALT:API_ERROR", "reason": str(e)}


class ExecutionValidatorInterface(StandardizedInterface):
    """Interface for Deterministic Execution via live API."""
    
    def __init__(self, runtime=None):
        self.runtime = runtime
        self.dhiraj_endpoint = "http://127.0.0.1:8001/execute"

    def validate_execution(self, contract: ComputationExecutionContract) -> Dict[str, Any]:
        import requests
        try:
            req_data = {
                "trace_id": contract.trace_id,
                "producer_type": contract.producer_type,
                "payload": contract.payload,
                "confidence": contract.confidence
            }
            resp = requests.post(self.dhiraj_endpoint, json=req_data, timeout=5)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            # Fallback to local if live server is not reachable for some tests
            if self.runtime:
                result = self.runtime.execute(contract)
                return result.to_dict()
            return {
                "contract_trace_id": contract.trace_id,
                "producer_type": contract.producer_type,
                "ack": f"HALT:LIVE_EXECUTION_FAILED:{str(e)}",
                "confidence": contract.confidence,
                "runtime_hash": ""
            }


class ConsensusVerifierInterface(StandardizedInterface):
    """Interface for Byzantine Consensus Generation."""
    
    def __init__(self, engine: ConsensusEngine):
        self.engine = engine

    def verify_consensus(self, contract: ComputationExecutionContract, pub_key: str) -> Dict[str, Any]:
        proof = self.engine.run_consensus(contract, pub_key)
        return proof.to_dict()
