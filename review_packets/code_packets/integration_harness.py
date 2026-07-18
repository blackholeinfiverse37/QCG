"""
integration_harness.py — Phase 3: Runtime Participation Harness

Executes one continuous flow representing a TANTRA ecosystem integration:
- Incoming BHIV contract
- Replay validation
<<<<<<< HEAD
- KESHAV live analysis (root-cause + severity)
=======
>>>>>>> 86f51a31442616a0759a9b57244d9d361d16197f
- Trust verification
- Runtime execution
- Consensus proof
- Structured output with trace continuity
"""

import tempfile
import time
<<<<<<< HEAD
import logging
=======
>>>>>>> 86f51a31442616a0759a9b57244d9d361d16197f
from pathlib import Path
from typing import Dict, Any, Tuple

from execution_contract import ComputationExecutionContract
from canonical_replay_authority import CanonicalReplayAuthority
from replay_registry import ReplayRegistry
from producer_verification import ProducerRegistry, ProducerVerificationLayer
from runtime_core import RuntimeCore
from consensus_simulation import ConsensusEngine, DistributedConsensusNode
from node_identity import NodeIdentity

from integration_interfaces import (
    ReplayVerifierInterface,
    TrustVerifierInterface,
    ExecutionValidatorInterface,
    ConsensusVerifierInterface,
    HealthStatusInterface
)

<<<<<<< HEAD
import config

logger = logging.getLogger("qcg.harness")

class TANTRAIntegrationHarness:
    """
    Continuous execution pipeline connecting all standard BHIV interfaces,
    including live KESHAV ecosystem integration.
=======
class TANTRAIntegrationHarness:
    """
    Simulates a continuous execution pipeline connecting all standard BHIV interfaces.
>>>>>>> 86f51a31442616a0759a9b57244d9d361d16197f
    """
    def __init__(self):
        # 1. Initialize persistent stores
        self.replay_registry = ReplayRegistry(path=Path(tempfile.mktemp(suffix="_tantra_registry.json")))
        self.trust_registry = ProducerRegistry()
<<<<<<< HEAD
=======
        from evidence_ledger import EvidenceLedger
        self.ledger = EvidenceLedger()
>>>>>>> 86f51a31442616a0759a9b57244d9d361d16197f
        
        # 2. Initialize Core Engines
        self.replay_auth = CanonicalReplayAuthority(self.replay_registry)
        self.verifier_layer = ProducerVerificationLayer(self.trust_registry)
        self.runtime_core = RuntimeCore()
        
        nodes = [
            DistributedConsensusNode("TANTRA_NODE_1"),
            DistributedConsensusNode("TANTRA_NODE_2"),
            DistributedConsensusNode("TANTRA_NODE_3"),
        ]
        self.consensus_engine = ConsensusEngine(nodes)
        
        # 3. Initialize Standard Interfaces
        self.replay_iface = ReplayVerifierInterface(self.replay_auth)
        self.trust_iface = TrustVerifierInterface(self.verifier_layer)
        self.execution_iface = ExecutionValidatorInterface(self.runtime_core)
        self.consensus_iface = ConsensusVerifierInterface(self.consensus_engine)
        self.health_iface = HealthStatusInterface(self.replay_registry)

<<<<<<< HEAD
        # 4. Initialize Live Ecosystem Clients
        self.keshav_client = None
        if config.KESHAV_ENABLED:
            try:
                from keshav_live_client import KeshavClient
                self.keshav_client = KeshavClient()
                logger.info("KESHAV live client initialized: %s", config.KESHAV_API_URL)
            except Exception as e:
                logger.warning("KESHAV client initialization failed: %s", e)

    def _run_keshav_analysis(self, trace_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Call KESHAV live /analyze endpoint for root-cause analysis.
        Returns analysis result dict or fallback if unavailable.
        """
        if self.keshav_client is None:
            return {
                "status": "SKIPPED",
                "reason": "KESHAV client not enabled",
                "live": False,
            }

        try:
            execution_id = payload.get("execution_id", f"exec-{trace_id}")
            resp = self.keshav_client.analyze_from_contract(
                trace_id=trace_id,
                execution_id=execution_id,
                payload=payload,
            )
            return {
                "status": "COMPLETED",
                "live": True,
                "trace_id": resp.trace_id,
                "root_cause": resp.root_cause,
                "resolution_signal": resp.resolution_signal,
                "impact_score": resp.impact_score,
                "severity": resp.severity,
                "timestamp": resp.timestamp,
            }
        except Exception as e:
            logger.warning("KESHAV analysis failed for trace %s: %s", trace_id, e)
            return {
                "status": "FALLBACK",
                "reason": str(e),
                "live": False,
            }

=======
>>>>>>> 86f51a31442616a0759a9b57244d9d361d16197f
    def process_incoming_contract(self, payload: Dict[str, Any], pub_key: str) -> Tuple[bool, Dict[str, Any]]:
        """
        Main continuous flow for incoming TANTRA contracts.
        """
        trace_id = payload.get("trace_id", "unknown")
        parent_trace = payload.get("parent_trace_id", None)
        issued_at = payload.get("issued_at", time.time())
        
        response = {
            "trace_id": trace_id,
            "parent_trace_id": parent_trace,
            "flow_status": "STARTED",
            "stages": {}
        }
        
        try:
            # 1. Replay Validation
            replay_res = self.replay_iface.verify_replay(trace_id, issued_at)
            response["stages"]["replay"] = replay_res
            if not replay_res["is_valid"]:
                response["flow_status"] = "HALTED"
                response["halt_reason"] = f"REPLAY_{replay_res['status']}"
                self.health_iface.record_process(False)
                return False, response
<<<<<<< HEAD

            # 2. KESHAV Live Analysis (new ecosystem integration step)
            keshav_res = self._run_keshav_analysis(trace_id, payload)
            response["stages"]["keshav_analysis"] = keshav_res
=======
>>>>>>> 86f51a31442616a0759a9b57244d9d361d16197f
                
            # Parse Contract (Governance Boundary)
            try:
                contract = ComputationExecutionContract(**payload)
            except Exception as e:
                response["flow_status"] = "HALTED"
                response["halt_reason"] = f"INVALID_CONTRACT: {e}"
                self.health_iface.record_process(False)
                return False, response

            # Auto-register producer for testing if not exists (simulates KESHAV identity sync)
            if not self.trust_registry.is_registered(contract.producer_id):
                identity = NodeIdentity(
                    node_id=contract.producer_id,
                    public_key=pub_key,
                    node_role="PRODUCER",
                    version="1.0.0"
                )
                self.trust_registry.register(identity, allowed_types={contract.producer_type})
                
<<<<<<< HEAD
            # 3. Trust Verification
=======
            # 2. Trust Verification
>>>>>>> 86f51a31442616a0759a9b57244d9d361d16197f
            trust_res = self.trust_iface.verify_trust(contract)
            response["stages"]["trust"] = trust_res
            if not trust_res["passed"]:
                response["flow_status"] = "HALTED"
                response["halt_reason"] = trust_res["halt_signal"]
                self.health_iface.record_process(False)
                return False, response
                
<<<<<<< HEAD
            # 4. Runtime Execution
=======
            # 3. Runtime Execution
>>>>>>> 86f51a31442616a0759a9b57244d9d361d16197f
            exec_res = self.execution_iface.validate_execution(contract)
            response["stages"]["execution"] = exec_res
            if "HALT" in exec_res["ack"]:
                response["flow_status"] = "HALTED"
                response["halt_reason"] = exec_res["ack"]
                self.health_iface.record_process(False)
                return False, response
                
<<<<<<< HEAD
            # 5. Consensus Proof
=======
            # 4. Consensus Proof
>>>>>>> 86f51a31442616a0759a9b57244d9d361d16197f
            cons_res = self.consensus_iface.verify_consensus(contract, pub_key)
            response["stages"]["consensus"] = cons_res
            
            # Trace Continuity propagation
            response["trace_continuity"] = {
                "sequence_number": replay_res["sequence_number"],
                "runtime_hash": exec_res["runtime_hash"],
<<<<<<< HEAD
                "final_hash": cons_res.get("final_hash"),
                "keshav_severity": keshav_res.get("severity"),
            }
            
=======
                "final_hash": cons_res.get("final_hash")
            }
            
            # Record Evidence
            from execution_record import ExecutionRecord
            import uuid
            import hashlib
            record = ExecutionRecord(
                execution_id=str(uuid.uuid4()),
                trace_id=trace_id,
                replay_reference=replay_res["sequence_number"],
                execution_sequence=len(self.ledger._records) + 1,
                producer_identity=contract.producer_id,
                runtime_identity="DHIRAJ_RUNTIME_v1",
                governance_identity="TANTRA_GOVERNANCE",
                execution_status=response["flow_status"],
                runtime_hash=exec_res["runtime_hash"],
                previous_execution_hash=self.ledger._current_head,
                execution_hash=hashlib.sha256(f"{trace_id}:{exec_res['runtime_hash']}".encode()).hexdigest(),
                schema_version="1.0.0"
            )
            self.ledger.append(record)
            
>>>>>>> 86f51a31442616a0759a9b57244d9d361d16197f
            response["flow_status"] = "COMPLETED"
            self.health_iface.record_process(True)
            return True, response
            
        except Exception as e:
            response["flow_status"] = "ERROR"
            response["error"] = str(e)
            self.health_iface.record_process(False)
            return False, response
<<<<<<< HEAD

    def get_keshav_evidence(self) -> str:
        """Return KESHAV integration evidence log as JSON."""
        if self.keshav_client:
            return self.keshav_client.get_evidence_log()
        return "[]"

=======
>>>>>>> 86f51a31442616a0759a9b57244d9d361d16197f
