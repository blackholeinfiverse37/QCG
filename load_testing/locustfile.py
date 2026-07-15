from locust import HttpUser, task, between
import time
import uuid

class TANTRAUser(HttpUser):
    wait_time = between(1, 2)

    @task(3)
    def verify_contract(self):
        trace_id = str(uuid.uuid4())
        payload = {
            "contract": {
                "producer_type": "QUANTUM",
                "payload": {"operation": "load_test", "data": 42},
                "confidence": 0.95,
                "trace_id": trace_id,
                "contract_version": "2.0.0",
                "timestamp": "2023-10-10T10:00:00Z"
            },
            "producer_public_key": "pub_key_123"
        }
        with self.client.post("/verify", json=payload, catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Failed with status {response.status_code}")

    @task(1)
    def health_check(self):
        self.client.get("/health/live")

    @task(1)
    def get_capabilities(self):
        self.client.get("/capabilities")
