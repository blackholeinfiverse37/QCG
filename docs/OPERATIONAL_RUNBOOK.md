# QCG Operational Runbook

## 1. Startup Procedures

### 1.1 Cold Start (Initial Boot)
```bash
# Ensure dependencies are installed
pip install -r requirements.txt

# Start the web server
python web_server.py
```
*Note: The web server binds to TCP port 8080 by default. Ensure this port is accessible to upstream TANTRA cluster nodes.*

### 1.2 Warm Restart
If the process dies, executing `python web_server.py` again will automatically load the last known stable state of the `ReplayRegistry` from the local `.json` artifact. 
*Note: In production deployments, this persistent store should be swapped for a distributed Redis/Valkey cache.*

## 2. Health & Monitoring

**Readiness and Liveness Probes (Kubernetes ready):**
```bash
curl -X GET http://127.0.0.1:8080/health/live
```
**Expected Response:**
```json
{
  "status": "UP",
  "version": "1.0.0",
  "readiness": "READY",
  "dependencies": {
    "replay_registry": "ONLINE",
    "consensus_nodes": "ONLINE"
  },
  "metrics": {
    "uptime_seconds": 120.4,
    "total_processed": 1500,
    "error_rate": 0.005,
    "registry_size": 1450
  }
}
```

## 3. Failure Reporting & Recovery

| Failure Scenario | Identification | Resolution |
|-----------------|----------------|------------|
| High Error Rate | `error_rate` > 0.10 in `/health` output | Check KESHAV public key synchronization. Large blocks of valid contracts may be failing trust verification. |
| Replay Rejection Surge | Upstream nodes report `422 HALT:REPLAY_DUPLICATE` | Check sequence numbers and message bus configurations. A downstream consumer might be infinitely retrying. |
| Process Crash | Port 8080 stops listening | Verify disk space. ReplayRegistry requires write access to persist state. Restart the process. |

## 4. End-to-End Validation
To continuously run a synthetic payload generation and validation suite:
```bash
python production_validation.py
```
This runs 5 test suites generating concrete proof of the cluster's health.
