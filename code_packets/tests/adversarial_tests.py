"""
adversarial_tests.py

Phase 4: Adversarial Testing
Simulates: Replay attacks, Signature tampering, Byzantine disagreement, Consensus failure, Invalid producer identities.
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

def _generate_signed_contract_payload(trace_id: str, producer_id: str = "ADV_NODE", conf: float = 0.95, override_payload_hash: str = None):
    signer = NodeSigner(node_id=producer_id, node_role="CLASSICAL")
    
    c = {
        "producer_type": "CLASSICAL",
        "payload": {"malicious": "payload"},
        "confidence": conf,
        "trace_id": trace_id,
        "contract_version": "2.0.0",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())
    }
    if override_payload_hash:
        c["payload_hash"] = override_payload_hash
        
    contract = ComputationExecutionContract(**c)
    signed = sign_contract(contract, signer)
    return signed.to_dict(), signer.identity.public_key

def test_adversarial_replay_attack():
    trace_id = str(uuid5(NAMESPACE_DNS, f"adv_replay_{time.time()}"))
    contract, pub_key = _generate_signed_contract_payload(trace_id)
    
    # Send once (success)
    resp1 = client.post("/verify", json={"contract": contract, "producer_public_key": pub_key})
    assert resp1.status_code == 200
    
    # Replay attack
    resp2 = client.post("/verify", json={"contract": contract, "producer_public_key": pub_key})
    assert resp2.status_code == 422
    assert "REPLAY_DUPLICATE" in resp2.json()["detail"]["halt_reason"]

def test_signature_tampering():
    trace_id = str(uuid5(NAMESPACE_DNS, f"adv_tamper_{time.time()}"))
    # The payload hash doesn't match the payload
    contract, pub_key = _generate_signed_contract_payload(trace_id, override_payload_hash="invalidhash")
    resp = client.post("/verify", json={"contract": contract, "producer_public_key": pub_key})
    assert resp.status_code == 422
    # either fails at HTTP validation or at signature missing because payload_hash was overriden 
    # but sign_contract recomputes or uses it. Actually, if payload_hash is wrong, verify_contract_provenance returns TAMPERED.
    assert "payload_hash mismatch" in str(resp.json()) or "INVALID_SIGNATURE" in str(resp.json())

def test_invalid_producer_identity():
    # To properly simulate this we might need an invalid node role or unregistered type,
    # but the harness auto-registers right now. Let's send an invalid schema completely
    trace_id = str(uuid5(NAMESPACE_DNS, f"adv_invalid_producer_{time.time()}"))
    # The signature will be invalid because we change the contract without resigning
    contract, pub_key = _generate_signed_contract_payload(trace_id)
    contract["producer_type"] = "HACKER_TYPE"
    resp = client.post("/verify", json={"contract": contract, "producer_public_key": pub_key})
    assert resp.status_code == 422
    assert "tampered" in str(resp.json()) or "Unauthorized producer type" in str(resp.json())

def test_low_confidence_rejection():
    # Simulates a Byzantine disagreement / low confidence rejection in RuntimeCore
    trace_id = str(uuid5(NAMESPACE_DNS, f"adv_low_conf_{time.time()}"))
    contract, pub_key = _generate_signed_contract_payload(trace_id, conf=0.1)
    resp = client.post("/verify", json={"contract": contract, "producer_public_key": pub_key})
    assert resp.status_code == 422
    assert "HALT" in str(resp.json())

if __name__ == "__main__":
    pytest.main(["-v", __file__])
