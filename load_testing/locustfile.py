from locust import HttpUser, task, between
import time
import json
from uuid import uuid5, NAMESPACE_DNS
from execution_contract import ComputationExecutionContract
from provenance import sign_contract
from node_identity import NodeSigner

class TANTRAEcosystemUser(HttpUser):
    wait_time = between(0.1, 1.0)
    
    def on_start(self):
        self.signer = NodeSigner(node_id="LOCUST_LOAD_NODE", node_role="QUANTUM")
    
    @task(3)
    def test_verify_contract(self):
        trace_id = str(uuid5(NAMESPACE_DNS, f"load_test_{time.time()}_{id(self)}"))
        
        contract = ComputationExecutionContract(
            producer_type="QUANTUM",
            payload={"operation": "qkd_key_exchange", "bits": 256},
            confidence=0.99,
            trace_id=trace_id,
            contract_version="2.0.0",
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())
        )
        
        signed = sign_contract(contract, self.signer)
        
        payload = {
            "contract": signed.to_dict(),
            "producer_public_key": self.signer.identity.public_key
        }
        
        with self.client.post("/verify", json=payload, catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Failed with status {response.status_code}")

    @task(1)
    def test_health(self):
        self.client.get("/health/live")

    @task(1)
    def test_capabilities(self):
        self.client.get("/capabilities")
