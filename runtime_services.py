"""
runtime_services.py - Distributed Production Services for QCG.
Can be started individually using:
  python runtime_services.py --service [replay|trust|producer|execution|consensus|registry]
"""

import sys
import os
import json
import time
import uuid
import socket
import hashlib
import argparse
import threading
import signal
from urllib import request
from urllib.error import URLError
from http.server import BaseHTTPRequestHandler, HTTPServer

import config
from transport import create_transport_sender, create_transport_receiver
from capability_registry import CapabilityRegistryServer, CapabilityRegistryClient

# -- Core QCG Imports ---------------------------------------------------------
from execution_contract import ComputationExecutionContract
from runtime_core import RuntimeCore
from canonical_replay_authority import CanonicalReplayAuthority
from replay_registry import ReplayRegistry
from producer_verification import ProducerRegistry, ProducerVerificationLayer
from consensus_simulation import ConsensusEngine, DistributedConsensusNode
from node_identity import NodeIdentity, NodeSigner
from provenance import sign_contract
from evidence_ledger import EvidenceLedger
from execution_record import ExecutionRecord

# -- Instrumentation & Metrics Registry ----------------------------------------
_metrics = {
    "requests_total": 0,
    "failures_total": 0,
    "execution_throughput": 0.0,
    "last_latency_ms": 0.0,
    "replay_valid_total": 0,
    "replay_invalid_total": 0,
    "consensus_reached_total": 0,
    "consensus_failed_total": 0,
}
_metrics_lock = threading.Lock()
_start_time = time.time()
_shutdown_event = threading.Event()

def signal_handler(sig, frame):
    print(f"\n[Service] Received termination signal {sig}. Initiating graceful shutdown...", flush=True)
    _shutdown_event.set()

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# -- Dynamic Health & Metrics HTTP Server -------------------------------------

class HealthMetricsHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass # Suppress logging

    def do_GET(self):
        if self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            uptime = time.time() - _start_time
            with _metrics_lock:
                health_status = {
                    "status": "UP",
                    "uptime_seconds": round(uptime, 2),
                    "total_requests": _metrics["requests_total"],
                    "failures": _metrics["failures_total"],
                }
            self.wfile.write(json.dumps(health_status).encode("utf-8"))

        elif self.path == "/metrics":
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
            self.end_headers()
            uptime = time.time() - _start_time
            with _metrics_lock:
                metrics_data = (
                    f"# HELP qcg_service_uptime_seconds Uptime of the service in seconds\n"
                    f"# TYPE qcg_service_uptime_seconds gauge\n"
                    f"qcg_service_uptime_seconds {uptime:.2f}\n"
                    f"# HELP qcg_requests_total Total requests processed by the service\n"
                    f"# TYPE qcg_requests_total counter\n"
                    f"qcg_requests_total {_metrics['requests_total']}\n"
                    f"# HELP qcg_failures_total Total failed requests in the service\n"
                    f"# TYPE qcg_failures_total counter\n"
                    f"qcg_failures_total {_metrics['failures_total']}\n"
                    f"# HELP qcg_last_latency_ms Last request latency in milliseconds\n"
                    f"# TYPE qcg_last_latency_ms gauge\n"
                    f"qcg_last_latency_ms {_metrics['last_latency_ms']:.2f}\n"
                    f"# HELP qcg_replay_valid_total Total valid replays\n"
                    f"# TYPE qcg_replay_valid_total counter\n"
                    f"qcg_replay_valid_total {_metrics['replay_valid_total']}\n"
                    f"# HELP qcg_replay_invalid_total Total invalid replays\n"
                    f"# TYPE qcg_replay_invalid_total counter\n"
                    f"qcg_replay_invalid_total {_metrics['replay_invalid_total']}\n"
                    f"# HELP qcg_consensus_reached_total Total consensus reached\n"
                    f"# TYPE qcg_consensus_reached_total counter\n"
                    f"qcg_consensus_reached_total {_metrics['consensus_reached_total']}\n"
                    f"# HELP qcg_consensus_failed_total Total consensus failed\n"
                    f"# TYPE qcg_consensus_failed_total counter\n"
                    f"qcg_consensus_failed_total {_metrics['consensus_failed_total']}\n"
                )
            self.wfile.write(metrics_data.encode("utf-8"))
        elif self.path == "/discovery":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            payload = getattr(self.server, 'capability_payload', {})
            payload_copy = dict(payload)
            with _metrics_lock:
                payload_copy["health"] = {
                    "status": "UP",
                    "uptime_seconds": round(time.time() - _start_time, 2)
                }
            self.wfile.write(json.dumps(payload_copy).encode("utf-8"))
        elif self.path.startswith("/otel/v1/traces/"):
            trace_id = self.path.split("/")[-1]
            try:
                from observability import TraceStore
                # For demo purposes, we create an empty store or read if it exists globally
                store = getattr(self.server, 'trace_store', TraceStore())
                spans = store.export_opentelemetry(trace_id)
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"resourceSpans": spans}).encode("utf-8"))
            except Exception as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(str(e).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

def heartbeat_monitor(dependencies: list):
    """Periodically check downstream capabilities and log failures."""
    while not _shutdown_event.is_set():
        if dependencies:
            reg_client = CapabilityRegistryClient(f"http://127.0.0.1:{config.REGISTRY_PORT}")
            for dep_id in dependencies:
                # We could query the registry for endpoint by ID, or just check registry
                # For simplicity, we just ping the registry to ensure it's alive.
                try:
                    request.urlopen(f"http://127.0.0.1:{config.REGISTRY_PORT}/capabilities", timeout=2)
                except Exception as e:
                    print(f"[Heartbeat] Failed to reach registry: {e}", flush=True)
        _shutdown_event.wait(10.0)

def start_health_server(port: int, capability_payload: dict = None, trace_store = None):
    server = HTTPServer(("127.0.0.1", port), HealthMetricsHandler)
    server.capability_payload = capability_payload or {}
    server.trace_store = trace_store
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    
    deps = server.capability_payload.get("dependencies", [])
    if deps:
        hb = threading.Thread(target=heartbeat_monitor, args=(deps,), daemon=True)
        hb.start()
        
    return server

# -- Registry Helper Functions ------------------------------------------------

def register_capability(client: CapabilityRegistryClient, cap_name: str, cap_id: str, endpoint: str, owns: list, does_not_own: list, dependencies: list = None):
    payload = {
        "capability_id": cap_id,
        "capability_name": cap_name,
        "owner": {
            "team": "TANTRA Sovereign Core",
            "contact": "sovereign-node@tantra.internal"
        },
        "version": "1.0.0",
        "status": "ACTIVE",
        "scope": "SYSTEM",
        "dependencies": dependencies or [],
        "attachment_rules": {
            "attachment_type": "api_linked",
            "protocol": config.TRANSPORT_TYPE,
            "endpoint": endpoint
        },
        "authority_limits": {
            "owns": owns,
            "does_not_own": does_not_own
        },
        "inputs": [],
        "outputs": [],
        "consumers": [],
        "documentation_reference": {
            "primary": "ARCHITECTURE.md"
        }
    }
    client.register(payload)
    return payload

# -- Replay Authority Service -------------------------------------------------

def run_replay_service():
    # Initialize Replay Registry and Authority
    db_path = f"logs/replay_authority_db.json"
    if os.path.exists(db_path):
        try: os.unlink(db_path)
        except OSError: pass
    registry = ReplayRegistry(path=db_path)
    authority = CanonicalReplayAuthority(registry)

    # Register in registry
    reg_client = CapabilityRegistryClient(f"http://127.0.0.1:{config.REGISTRY_PORT}")
    endpoint = f"127.0.0.1:{config.REPLAY_PORT}" if config.TRANSPORT_TYPE != "uds" else f"./logs/uds_replay.sock"
    payload = register_capability(
        reg_client,
        "REPLAY_ENFORCEMENT",
        "a1b2c3d4-e5f6-5a7b-8c9d-0e1f2a3b4c5d",
        endpoint=str(endpoint),
        owns=["sequence_id assignment", "duplicate detection", "stale detection", "lineage"],
        does_not_own=["contract validation", "execution logic"]
    )

    print("[Service] Replay Authority starting...", flush=True)
    health_port = config.REPLAY_PORT + 100
    start_health_server(health_port, capability_payload=payload)

    receiver = create_transport_receiver(config.TRANSPORT_TYPE, endpoint)
    print(f"[Service] Replay Authority listening on {endpoint}...", flush=True)

    while not _shutdown_event.is_set():
        try:
            req = receiver.get(timeout=1.0)
            if not req:
                continue
            if req.get("type") == "DONE":
                break
            
            with _metrics_lock:
                _metrics["requests_total"] += 1
                
            start = time.time()
            action = req.get("action")
            reply_address = req.get("reply_address")

            response = {}
            if action == "submit":
                msg_id = req["message_id"]
                issued_at = req.get("issued_at", time.time())
                verdict = authority.submit(msg_id, issued_at)
                with _metrics_lock:
                    if verdict.is_valid:
                        _metrics["replay_valid_total"] += 1
                    else:
                        _metrics["replay_invalid_total"] += 1
                response = {
                    "is_valid": verdict.is_valid,
                    "status": verdict.status,
                    "sequence_number": verdict.sequence_number,
                    "verification_hash": verdict.lineage_record.verification_hash if verdict.is_valid else ""
                }
            elif action == "lookup":
                msg_id = req["message_id"]
                lk = authority.lookup(msg_id)
                response = {"found": lk is not None, "status": lk.status if lk else None}
            elif action == "lineage":
                lin = authority.lineage()
                response = {"lineage": [l.__dict__ for l in lin]}

            if reply_address:
                try:
                    sender = create_transport_sender(config.TRANSPORT_TYPE, reply_address)
                    sender.connect()
                    sender.put(response)
                    sender.close()
                except Exception as e:
                    print(f"[Service] Replay failed reply: {e}", flush=True)

            with _metrics_lock:
                _metrics["last_latency_ms"] = (time.time() - start) * 1000

        except Exception as e:
            with _metrics_lock:
                _metrics["failures_total"] += 1
            print(f"[Service] Replay error: {e}", flush=True)

    receiver.close()
    print("[Service] Replay Authority stopped.", flush=True)

# -- Trust Service ------------------------------------------------------------

def run_trust_service():
    trust_registry = ProducerRegistry()
    verifier = ProducerVerificationLayer(trust_registry)

    reg_client = CapabilityRegistryClient(f"http://127.0.0.1:{config.REGISTRY_PORT}")
    endpoint = f"127.0.0.1:{config.TRUST_PORT}" if config.TRANSPORT_TYPE != "uds" else f"./logs/uds_trust.sock"
    payload = register_capability(
        reg_client,
        "TRUST_VERIFICATION",
        "b2c3d4e5-f6a7-5b8c-9d0e-1f2a3b4c5d6e",
        endpoint=str(endpoint),
        owns=["ECDSA validation", "identity validation", "key-swap check"],
        does_not_own=["replay detection", "execution"]
    )

    print("[Service] Trust Service starting...", flush=True)
    health_port = config.TRUST_PORT + 100
    start_health_server(health_port, capability_payload=payload)

    receiver = create_transport_receiver(config.TRANSPORT_TYPE, endpoint)
    print(f"[Service] Trust Service listening on {endpoint}...", flush=True)

    while not _shutdown_event.is_set():
        try:
            req = receiver.get(timeout=1.0)
            if not req:
                continue
            if req.get("type") == "DONE":
                break
            
            with _metrics_lock:
                _metrics["requests_total"] += 1
                
            start = time.time()
            action = req.get("action")
            reply_address = req.get("reply_address")

            response = {}
            if action == "verify":
                contract_raw = req["contract"]
                pub_key = req["producer_public_key"]
                
                try:
                    contract = ComputationExecutionContract(**contract_raw)
                    # Register dynamically if needed
                    if not trust_registry.is_registered(contract.producer_id):
                        identity = NodeIdentity(
                            node_id=contract.producer_id,
                            public_key=pub_key,
                            node_role="PRODUCER",
                            version="1.0.0"
                        )
                        trust_registry.register(identity, allowed_types={contract.producer_type})
                    else:
                        registered_key = trust_registry.public_key(contract.producer_id)
                        if registered_key != pub_key:
                            response = {"passed": False, "halt_signal": "HALT:INVALID_SIGNATURE:key_mismatch", "reason": "key_mismatch"}
                            
                    if not response:
                        res = verifier.verify(contract)
                        response = {
                            "passed": res.passed,
                            "halt_signal": res.halt_signal(),
                            "reason": res.reason
                        }
                except Exception as ex:
                    response = {"passed": False, "halt_signal": f"HALT:INVALID_CONTRACT:{ex}", "reason": str(ex)}

            if reply_address:
                try:
                    sender = create_transport_sender(config.TRANSPORT_TYPE, reply_address)
                    sender.connect()
                    sender.put(response)
                    sender.close()
                except Exception as e:
                    print(f"[Service] Trust failed reply: {e}", flush=True)

            with _metrics_lock:
                _metrics["last_latency_ms"] = (time.time() - start) * 1000

        except Exception as e:
            with _metrics_lock:
                _metrics["failures_total"] += 1
            print(f"[Service] Trust error: {e}", flush=True)

    receiver.close()
    print("[Service] Trust Service stopped.", flush=True)

# -- Producer Service ---------------------------------------------------------

def run_producer_service():
    # Register in capability registry
    reg_client = CapabilityRegistryClient(f"http://127.0.0.1:{config.REGISTRY_PORT}")
    endpoint = f"127.0.0.1:{config.PRODUCER_PORT}" if config.TRANSPORT_TYPE != "uds" else f"./logs/uds_producer.sock"
    payload = register_capability(
        reg_client,
        "PRODUCER_SERVICE",
        "d4e5f6a7-b8c9-5d0e-bf2a-3b4c5d6e7f8a",
        endpoint=str(endpoint),
        owns=["contract generation", "ECDSA signing"],
        does_not_own=["replay checking", "byzantine consensus"]
    )

    print("[Service] Producer Service starting...", flush=True)
    health_port = config.PRODUCER_PORT + 100
    start_health_server(health_port, capability_payload=payload)

    producer = NodeSigner("PROC_DIST_PRODUCER", "QUANTUM_PRODUCER")

    # Dynamic lookup: Wait for Execution Service to register
    print("[Service] Producer querying Execution Service address...", flush=True)
    execution_addr = None
    for _ in range(100):
        res = reg_client.discover("EXECUTION_SERVICE")
        if res:
            execution_addr = res["attachment_rules"]["endpoint"]
            break
        time.sleep(0.1)

    if not execution_addr:
        print("[Service] Producer failed to resolve Execution Service, exiting", flush=True)
        return

    # In a real environment, the service waits for requests.
    # Here we simulate sending a signed contract to the Execution endpoint.
    contract = ComputationExecutionContract(
        producer_type="QUANTUM",
        payload={"data": "process_distributed_entangled_pair", "source": "distributed_producer"},
        confidence=0.98,
        trace_id="dist-trace-001",
        contract_version="2.0.0",
    )
    signed = sign_contract(contract, producer)

    msg = {
        "type": "CONTRACT",
        "contract": signed.to_dict(),
        "producer_public_key": producer.identity.public_key,
        "issued_at": time.time(),
    }

    try:
        sender = create_transport_sender(config.TRANSPORT_TYPE, execution_addr)
        sender.connect()
        sender.put(msg)
        sender.put({"type": "DONE"})
        sender.close()
        print("[Service] Producer sent contract to Execution Service.", flush=True)
    except Exception as e:
        print(f"[Service] Producer failed to send contract: {e}", flush=True)

    print("[Service] Producer Service finished.", flush=True)

# -- Execution Service --------------------------------------------------------

def run_execution_service():
    runtime = RuntimeCore()
    ledger = EvidenceLedger()

    reg_client = CapabilityRegistryClient(f"http://127.0.0.1:{config.REGISTRY_PORT}")
    endpoint = f"127.0.0.1:{config.EXECUTION_PORT}" if config.TRANSPORT_TYPE != "uds" else f"./logs/uds_execution.sock"
    payload = register_capability(
        reg_client,
        "EXECUTION_SERVICE",
        "e5f6a7b8-c9d0-5e1f-8a3b-4c5d6e7f8a9b",
        endpoint=str(endpoint),
        owns=["blind runtime execution", "ledger updates"],
        does_not_own=["replay detection", "ECDSA verification"],
        dependencies=["a1b2c3d4-e5f6-5a7b-8c9d-0e1f2a3b4c5d", "b2c3d4e5-f6a7-5b8c-9d0e-1f2a3b4c5d6e"]
    )

    print("[Service] Execution Service starting...", flush=True)
    health_port = config.EXECUTION_PORT + 100
    
    # We create a local trace store to simulate telemetry
    from observability import TraceStore
    store = TraceStore()
    start_health_server(health_port, capability_payload=payload, trace_store=store)

    # Lookup Replay and Trust addresses
    replay_addr = None
    trust_addr = None
    consensus_addr = None

    for _ in range(100):
        if not replay_addr:
            res = reg_client.discover("REPLAY_ENFORCEMENT")
            if res: replay_addr = res["attachment_rules"]["endpoint"]
        if not trust_addr:
            res = reg_client.discover("TRUST_VERIFICATION")
            if res: trust_addr = res["attachment_rules"]["endpoint"]
        if not consensus_addr:
            res = reg_client.discover("CONSENSUS_SERVICE")
            if res: consensus_addr = res["attachment_rules"]["endpoint"]
        if replay_addr and trust_addr and consensus_addr:
            break
        time.sleep(0.1)

    if not (replay_addr and trust_addr and consensus_addr):
        print("[Service] Execution Service missing dependencies. Exiting.", flush=True)
        return

    receiver = create_transport_receiver(config.TRANSPORT_TYPE, endpoint)
    print(f"[Service] Execution Service listening on {endpoint}...", flush=True)

    # Ephemeral return port/path for request-reply coordination
    local_reply_port = config.EXECUTION_PORT + 10
    local_reply_addr = f"127.0.0.1:{local_reply_port}" if config.TRANSPORT_TYPE != "uds" else f"./logs/uds_exec_reply.sock"

    while not _shutdown_event.is_set():
        try:
            msg = receiver.get(timeout=1.0)
            if not msg:
                continue
            if msg.get("type") == "DONE":
                # Propagate DONE
                try:
                    c_send = create_transport_sender(config.TRANSPORT_TYPE, consensus_addr)
                    c_send.connect()
                    c_send.put({"type": "DONE"})
                    c_send.close()
                except Exception:
                    pass
                break

            if msg.get("type") != "CONTRACT":
                continue

            with _metrics_lock:
                _metrics["requests_total"] += 1
            start = time.time()

            raw = msg["contract"]
            pub_key = msg["producer_public_key"]
            issued_at_wall = msg.get("issued_at", time.time())

            # 1. Call Replay Service
            reply_rec = create_transport_receiver(config.TRANSPORT_TYPE, local_reply_addr)
            
            replay_req = {
                "action": "submit",
                "message_id": raw["trace_id"],
                "issued_at": issued_at_wall,
                "reply_address": local_reply_addr
            }
            
            rep_sender = create_transport_sender(config.TRANSPORT_TYPE, replay_addr)
            rep_sender.connect()
            rep_sender.put(replay_req)
            rep_sender.close()

            verdict_raw = reply_rec.get(timeout=5)
            reply_rec.close()

            if not verdict_raw.get("is_valid"):
                # Halt replay duplicate
                c_send = create_transport_sender(config.TRANSPORT_TYPE, consensus_addr)
                c_send.connect()
                c_send.put({
                    "type": "EXECUTION_RESULT",
                    "result": {"ack": f"HALT:REPLAY_{verdict_raw.get('status')}", "trace_id": raw["trace_id"]},
                    "issued_at": time.time(),
                })
                c_send.close()
                continue

            # 2. Call Trust Service
            reply_rec = create_transport_receiver(config.TRANSPORT_TYPE, local_reply_addr)
            trust_req = {
                "action": "verify",
                "contract": raw,
                "producer_public_key": pub_key,
                "reply_address": local_reply_addr
            }
            trust_sender = create_transport_sender(config.TRANSPORT_TYPE, trust_addr)
            trust_sender.connect()
            trust_sender.put(trust_req)
            trust_sender.close()

            trust_res = reply_rec.get(timeout=5)
            reply_rec.close()

            if not trust_res.get("passed"):
                c_send = create_transport_sender(config.TRANSPORT_TYPE, consensus_addr)
                c_send.connect()
                c_send.put({
                    "type": "EXECUTION_RESULT",
                    "result": {"ack": trust_res.get("halt_signal", "HALT:TRUST_FAILURE"), "trace_id": raw["trace_id"]},
                    "issued_at": time.time(),
                })
                c_send.close()
                continue

            # 3. Execution
            contract = ComputationExecutionContract(**raw)
            exec_result = runtime.execute(contract)

            # Record in Ledger
            exec_id = str(uuid.uuid4())
            record = ExecutionRecord(
                execution_id=exec_id,
                trace_id=contract.trace_id,
                replay_reference=verdict_raw.get("verification_hash", ""),
                execution_sequence=verdict_raw.get("sequence_number", 0),
                producer_identity=contract.producer_id,
                runtime_identity="RUNTIME_CORE_DIST",
                governance_identity="GOVERNANCE_LAYER_DIST",
                execution_status=exec_result.ack,
                runtime_hash=exec_result.runtime_hash,
                execution_hash=hashlib.sha256(exec_id.encode()).hexdigest(),
                previous_execution_hash=ledger._current_head,
                execution_root_hash="",
                schema_version="1.0.0"
            )
            snapshot = ledger.append(record)

            # 4. Forward to Consensus
            c_send = create_transport_sender(config.TRANSPORT_TYPE, consensus_addr)
            c_send.connect()
            c_send.put({
                "type": "EXECUTION_RESULT",
                "result": exec_result.to_dict(),
                "contract": raw,
                "producer_public_key": pub_key,
                "issued_at": time.time(),
                "execution_certificate": {
                    "execution_record": record.__dict__,
                    "ledger_snapshot": snapshot.__dict__
                }
            })
            c_send.close()

            with _metrics_lock:
                _metrics["last_latency_ms"] = (time.time() - start) * 1000

        except Exception as e:
            with _metrics_lock:
                _metrics["failures_total"] += 1
            print(f"[Service] Execution error: {e}", flush=True)

    receiver.close()
    print("[Service] Execution Service stopped.", flush=True)

# -- Consensus Service --------------------------------------------------------

def run_consensus_service():
    nodes = [
        DistributedConsensusNode("CONS_NODE_A_DIST"),
        DistributedConsensusNode("CONS_NODE_B_DIST"),
        DistributedConsensusNode("CONS_NODE_C_DIST"),
    ]
    engine = ConsensusEngine(nodes)

    reg_client = CapabilityRegistryClient(f"http://127.0.0.1:{config.REGISTRY_PORT}")
    endpoint = f"127.0.0.1:{config.CONSENSUS_PORT}" if config.TRANSPORT_TYPE != "uds" else f"./logs/uds_consensus.sock"
    payload = register_capability(
        reg_client,
        "CONSENSUS_SERVICE",
        "f6a7b8c9-d0e1-5f2a-8b3c-4d5e6f7a8b9c",
        endpoint=str(endpoint),
        owns=["Byzantine agreement", "attestation check"],
        does_not_own=["execution", "signing"]
    )

    print("[Service] Consensus Service starting...", flush=True)
    health_port = config.CONSENSUS_PORT + 100
    start_health_server(health_port, capability_payload=payload)

    receiver = create_transport_receiver(config.TRANSPORT_TYPE, endpoint)
    print(f"[Service] Consensus Service listening on {endpoint}...", flush=True)

    # Collect proofs to output file for validation
    os.makedirs("logs", exist_ok=True)
    out_file = "logs/consensus_output.log"
    with open(out_file, "w") as f:
        pass

    while not _shutdown_event.is_set():
        try:
            msg = receiver.get(timeout=1.0)
            if not msg:
                continue
            if msg.get("type") == "DONE":
                break

            if msg.get("type") != "EXECUTION_RESULT":
                continue

            with _metrics_lock:
                _metrics["requests_total"] += 1
            start = time.time()

            result_raw = msg["result"]
            if "HALT" in result_raw.get("ack", ""):
                proof_dict = {"consensus_reached": False, "reason": result_raw.get("ack")}
                with _metrics_lock:
                    _metrics["consensus_failed_total"] += 1
            else:
                contract_raw = msg["contract"]
                pub_key = msg["producer_public_key"]
                contract = ComputationExecutionContract(**contract_raw)
                proof = engine.run_consensus(contract, pub_key)
                proof_dict = proof.to_dict()
                with _metrics_lock:
                    if proof.consensus_reached:
                        _metrics["consensus_reached_total"] += 1
                    else:
                        _metrics["consensus_failed_total"] += 1

            with open(out_file, "a") as f:
                f.write(json.dumps(proof_dict) + "\n")

            print(f"[Service] Consensus reached: {proof_dict.get('consensus_reached')}", flush=True)

            with _metrics_lock:
                _metrics["last_latency_ms"] = (time.time() - start) * 1000

        except Exception as e:
            with _metrics_lock:
                _metrics["failures_total"] += 1
            print(f"[Service] Consensus error: {e}", flush=True)

    receiver.close()
    print("[Service] Consensus Service stopped.", flush=True)

# -- Main Entry Point ----------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="QCG Distributed Service Launcher")
    parser.add_argument("--service", required=True, choices=["registry", "replay", "trust", "producer", "execution", "consensus"])
    args = parser.parse_args()

    service_name = args.service.lower()
    if service_name == "registry":
        server = CapabilityRegistryServer("127.0.0.1", config.REGISTRY_PORT)
        server.start()
        try:
            while True: time.sleep(1)
        except KeyboardInterrupt:
            server.stop()
    elif service_name == "replay":
        run_replay_service()
    elif service_name == "trust":
        run_trust_service()
    elif service_name == "producer":
        run_producer_service()
    elif service_name == "execution":
        run_execution_service()
    elif service_name == "consensus":
        run_consensus_service()
