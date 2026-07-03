"""
production_validation_suite.py

Phase 3: Production Validation Suite
Validates:
- API validation
- Multi-node execution
- Multi-product execution
- Capability discovery validation
- Health endpoint validation
- Replay validation
- Trust validation
- Consensus validation
"""

import time
import pytest
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

def _generate_signed_contract_payload(trace_id: str, producer_type: str, producer_id: str):
    signer = NodeSigner(node_id=producer_id, node_role=producer_type)
    
    contract = ComputationExecutionContract(
        producer_type=producer_type,
        payload={"data": "test"},
        confidence=0.95,
        trace_id=trace_id,
        contract_version="2.0.0",
        timestamp=time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())
    )
    
    signed = sign_contract(contract, signer)
    return signed.to_dict(), signer.identity.public_key

def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert data["status"] == "UP"

def test_capability_discovery():
    response = client.get("/capabilities")
    assert response.status_code == 200
    data = response.json()
    assert "capabilities" in data

def test_api_validation_invalid_payload():
    # Missing producer_public_key
    response = client.post("/verify", json={"contract": {}})
    assert response.status_code == 422

def test_trust_validation_failure():
    trace_id = str(uuid5(NAMESPACE_DNS, f"trust_test_{time.time()}"))
    producer_id = f"NODE_TRUST_{time.time()}"
    # INVALID_TYPE is not allowed
    contract, pub_key = _generate_signed_contract_payload(trace_id, "CLASSICAL", producer_id)
    # tamper type
    contract["producer_type"] = "INVALID_TYPE"
    response = client.post("/verify", json={"contract": contract, "producer_public_key": pub_key})
    
    assert response.status_code == 422
    data = response.json()
    assert "HALTED" in data.get("detail", {}).get("flow_status", "") or "INVALID_CONTRACT" in data.get("detail", {}).get("halt_reason", "") or "TRUST_FAILURE" in data.get("detail", {}).get("halt_reason", "")

def test_replay_validation_duplicate():
    trace_id = str(uuid5(NAMESPACE_DNS, f"replay_test_{time.time()}"))
    producer_id = f"NODE_REPLAY_{time.time()}"
    contract, pub_key = _generate_signed_contract_payload(trace_id, "CLASSICAL", producer_id)
    
    # First request should pass
    resp1 = client.post("/verify", json={"contract": contract, "producer_public_key": pub_key})
    assert resp1.status_code == 200
    
    # Second request with same trace_id should fail replay validation
    resp2 = client.post("/verify", json={"contract": contract, "producer_public_key": pub_key})
    assert resp2.status_code == 422
    data = resp2.json()
    assert data["detail"]["flow_status"] == "HALTED"
    assert "REPLAY_DUPLICATE" in data["detail"]["halt_reason"]

def test_multi_node_execution():
    for i in range(1, 4):
        trace_id = str(uuid5(NAMESPACE_DNS, f"multinode_test_{i}_{time.time()}"))
        producer_id = f"NODE_MULTI_{i}_{time.time()}"
        contract, pub_key = _generate_signed_contract_payload(trace_id, "CLASSICAL", producer_id)
        resp = client.post("/verify", json={"contract": contract, "producer_public_key": pub_key})
        assert resp.status_code == 200
        assert resp.json()["flow_status"] == "COMPLETED"

def test_multi_product_execution():
    for prod_type in ["CLASSICAL", "QUANTUM", "HYBRID"]:
        trace_id = str(uuid5(NAMESPACE_DNS, f"multiproduct_{prod_type}_{time.time()}"))
        producer_id = f"NODE_PROD_{prod_type}_{time.time()}"
        contract, pub_key = _generate_signed_contract_payload(trace_id, prod_type, producer_id)
        resp = client.post("/verify", json={"contract": contract, "producer_public_key": pub_key})
        assert resp.status_code == 200
        assert resp.json()["flow_status"] == "COMPLETED"

def test_consensus_validation():
    trace_id = str(uuid5(NAMESPACE_DNS, f"consensus_test_{time.time()}"))
    producer_id = f"NODE_CONSENSUS_{time.time()}"
    contract, pub_key = _generate_signed_contract_payload(trace_id, "CLASSICAL", producer_id)
    resp = client.post("/verify", json={"contract": contract, "producer_public_key": pub_key})
    assert resp.status_code == 200
    
    data = resp.json()
    assert data["stages"]["consensus"]["consensus_reached"] == True
    assert len(data["stages"]["consensus"]["node_attestations"]) >= 2
    assert "final_hash" in data["trace_continuity"]

if __name__ == "__main__":
    pytest.main(["-v", __file__])
