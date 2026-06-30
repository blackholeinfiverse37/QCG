"""
distributed_runner.py — Phase 6: Distributed Production Orchestrator

Spawns the six sovereign services as independent processes to emulate a fully 
distributed TANTRA ecosystem integration.

Services started:
1. Capability Registry
2. Replay Authority
3. Trust Verification
4. Consensus Engine
5. Execution Service
6. Producer Service

This runner collects health/metrics and captures execution evidence.
"""

import sys
import time
import json
import subprocess
import os
import signal
from urllib import request

import config

def start_process(service_name: str) -> subprocess.Popen:
    """Start a runtime service as an independent subprocess."""
    print(f"[*] Starting {service_name.upper()} service...")
    env = os.environ.copy()
    # Ensure they use TCP transport for the demo
    env["QCG_TRANSPORT_TYPE"] = "tcp"
    proc = subprocess.Popen(
        [sys.executable, "runtime_services.py", "--service", service_name],
        env=env,
        stdout=sys.stdout,
        stderr=sys.stderr
    )
    return proc

def wait_for_health(port: int, service_name: str, timeout: int = 15):
    """Poll the /health endpoint until it is up."""
    url = f"http://127.0.0.1:{port}/health"
    start = time.time()
    while time.time() - start < timeout:
        try:
            with request.urlopen(url, timeout=1) as response:
                if response.status == 200:
                    data = json.loads(response.read().decode())
                    if data.get("status") == "UP":
                        print(f"[+] {service_name.upper()} is HEALTHY.")
                        return True
        except Exception:
            pass
        time.sleep(0.5)
    print(f"[-] {service_name.upper()} health check failed.")
    return False

def main():
    print("\n" + "=" * 70)
    print("  QCG DISTRIBUTED RUNTIME ORCHESTRATOR")
    print("=" * 70)
    
    os.makedirs("logs", exist_ok=True)
    out_file = "logs/consensus_output.log"
    with open(out_file, "w") as f:
        pass # Clear previous runs

    procs = []
    
    try:
        # 1. Start Registry
        p_reg = start_process("registry")
        procs.append(p_reg)
        time.sleep(2) # Give registry time to start
        
        # 2. Start core services
        p_replay = start_process("replay")
        procs.append(p_replay)
        p_trust = start_process("trust")
        procs.append(p_trust)
        p_cons = start_process("consensus")
        procs.append(p_cons)
        
        # 3. Wait for their health checks
        wait_for_health(config.REPLAY_PORT + 100, "Replay")
        wait_for_health(config.TRUST_PORT + 100, "Trust")
        wait_for_health(config.CONSENSUS_PORT + 100, "Consensus")
        
        # 4. Start Execution (depends on Replay, Trust, Consensus)
        p_exec = start_process("execution")
        procs.append(p_exec)
        wait_for_health(config.EXECUTION_PORT + 100, "Execution")
        
        # 5. Start Producer (triggers execution flow)
        p_prod = start_process("producer")
        procs.append(p_prod)
        wait_for_health(config.PRODUCER_PORT + 100, "Producer")
        
        print("\n[*] All services running. Waiting for distributed consensus output...")
        
        # Wait up to 10 seconds for consensus output
        start = time.time()
        consensus_reached = False
        while time.time() - start < 10:
            if os.path.exists(out_file) and os.path.getsize(out_file) > 0:
                with open(out_file, "r") as f:
                    for line in f:
                        if line.strip():
                            data = json.loads(line)
                            if data.get("consensus_reached") is not None:
                                consensus_reached = True
                                print("\n[+] Execution Evidence Received!")
                                print(json.dumps(data, indent=2))
                                break
            if consensus_reached:
                break
            time.sleep(1)
            
        if not consensus_reached:
            print("\n[-] Timeout waiting for consensus.")

    except KeyboardInterrupt:
        print("\n[*] Stopping distributed cluster...")
    finally:
        for p in procs:
            p.send_signal(signal.SIGTERM)
            try:
                p.wait(timeout=3)
            except subprocess.TimeoutExpired:
                p.kill()
        print("[*] Distributed runtime stopped.")

if __name__ == "__main__":
    main()
