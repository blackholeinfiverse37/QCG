"""
e2e_ecosystem_flow.py

Demonstrates the full Ecosystem Integration for Phase 2.
Flow: Producer -> Replay -> Trust -> Execution -> Consensus -> Telemetry -> Lineage -> Response
Integrates simulated: Dhiraj Runtime, Pritesh Quantum Engine, BHIV Runtime, InsightFlow, Pravah, KESHAV.
"""
import time
import json
from uuid import uuid5, NAMESPACE_DNS

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient
from web_server import app
from execution_contract import ComputationExecutionContract
from provenance import sign_contract
from node_identity import NodeSigner

client = TestClient(app)

def run_flow():
    print("--- TANTRA Ecosystem Flow Demonstration ---")
    
    # 1. Producer generates contract (Pritesh Quantum Engine)
    trace_id = str(uuid5(NAMESPACE_DNS, f"demo_flow_{time.time()}"))
    producer_id = "PRITESH_QUANTUM_ENGINE_01"
    
    signer = NodeSigner(node_id=producer_id, node_role="QUANTUM")
    
    contract = ComputationExecutionContract(
        producer_type="QUANTUM",
        payload={"operation": "shor_factorization", "input": 15},
        confidence=0.99,
        trace_id=trace_id,
        contract_version="2.0.0",
        timestamp=time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())
    )
    
    signed = sign_contract(contract, signer)
    
    req_body = {
        "contract": signed.to_dict(),
        "producer_public_key": signer.identity.public_key
    }
    
    print(f"[PRODUCER] Pritesh Quantum Engine sending contract to QCG (Trace: {trace_id})")
    
    # 2. Send Request to QCG (Simulates BHIV / Pravah ingestion)
    response = client.post("/verify", json=req_body)
    
    # Print the flow
    if response.status_code == 200:
        data = response.json()
        print("\n[QCG RUNTIME] Execution Successful!")
        print(f"Flow Status: {data['flow_status']}")
        
        stages = data['stages']
        print("\n--- Pipeline Stages ---")
        print(f"1. REPLAY    : Valid={stages['replay']['is_valid']} (Seq: {stages['replay']['sequence_number']})")
        print(f"2. TRUST     : Passed={stages['trust']['passed']} (Simulated KESHAV sync for {producer_id})")
        print(f"3. EXECUTION : ACK={stages['execution']['ack']} (Executed via Dhiraj Runtime)")
        print(f"4. CONSENSUS : Reached={stages['consensus']['consensus_reached']} (Quorum gathered)")
        
        print("\n--- Pravah Lineage Handoff ---")
        continuity = data['trace_continuity']
        print(json.dumps(continuity, indent=2))
        
        # 3. Telemetry check (InsightFlow)
        health = client.get("/health").json()
        print("\n--- InsightFlow Telemetry ---")
        print(f"System Operational: {health['status']}")
        print(f"Total processed requests: {health['metrics']['total_processed']}")
    else:
        print(f"Flow Failed! Status: {response.status_code}")
        print(response.text)

if __name__ == "__main__":
    run_flow()
