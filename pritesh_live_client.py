import urllib.request
import urllib.error
import json
import time

class PriteshClient:
    def __init__(self, base_url="http://localhost:8080"):
        self.base_url = base_url

    def verify_quantum_capability(self, payload):
        req = urllib.request.Request(
            f"{self.base_url}/verify",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        start_time = time.time()
        try:
            with urllib.request.urlopen(req) as response:
                latency = time.time() - start_time
                status = response.getcode()
                response_data = json.loads(response.read().decode("utf-8"))
                return {"status": status, "data": response_data, "latency": latency, "error": None}
        except urllib.error.HTTPError as e:
            latency = time.time() - start_time
            err_body = e.read().decode("utf-8")
            return {"status": e.code, "data": err_body, "latency": latency, "error": str(e)}
        except Exception as e:
            latency = time.time() - start_time
            return {"status": None, "data": None, "latency": latency, "error": str(e)}

if __name__ == "__main__":
    client = PriteshClient()
    payload = {
        "contract": { "operation": "quantum_simulation", "parameters": { "qubits": 4, "depth": 2 } },
        "producer_public_key": "YOUR_KEY"
    }
    print("Sending payload to /verify...")
    res = client.verify_quantum_capability(payload)
    print(json.dumps(res, indent=2))
