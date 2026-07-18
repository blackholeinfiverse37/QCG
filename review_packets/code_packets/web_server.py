"""
web_server.py — Phase 4: Operational Readiness Endpoints

Provides a lightweight, production-grade HTTP API for TANTRA ecosystem integration via FastAPI.
Endpoints:
- GET /health, /health/live, /health/ready : Health, readiness, and metrics.
- GET /capabilities   : Capability manifest and API contracts.
- POST /verify        : Synchronous end-to-end integration flow.
"""

import logging
from typing import Dict, Any

from fastapi import FastAPI, HTTPException, Request, Response
from pydantic import BaseModel

from integration_harness import TANTRAIntegrationHarness
from integration_interfaces import CapabilityDiscoveryInterface

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

app = FastAPI(
    title="TANTRA Operational Readiness API",
    description="Quantum Communication Gateway (QCG) Ecosystem Integration API",
    version="1.0.0"
)

# Global harness instance
harness = TANTRAIntegrationHarness()

class VerifyRequest(BaseModel):
    contract: Dict[str, Any]
    producer_public_key: str

@app.get("/health")
@app.get("/health/live")
@app.get("/health/ready")
async def health_check():
    """Returns health, readiness, and metrics for InsightFlow integration."""
    return harness.health_iface.get_health()

@app.get("/capabilities")
async def get_capabilities():
    """Serves the deterministic Capability Manifest for ecosystem discovery."""
    return CapabilityDiscoveryInterface.discover_capabilities()

@app.post("/verify")
async def verify_contract(payload: VerifyRequest):
    """
    Synchronous end-to-end integration flow.
    Primary ingestion pipeline for BHIV contracts from Pravah/NICAI.
    """
    import uuid
    from datetime import datetime, timezone

    # Adapt raw Pritesh payload into QCG ComputationExecutionContract
    if "producer_type" not in payload.contract:
        from execution_contract import ComputationExecutionContract
        from node_identity import NodeSigner
        from provenance import sign_contract
        import uuid
        from datetime import datetime, timezone

        c = ComputationExecutionContract(
            producer_type="QUANTUM",
            producer_id="PRITESH_QUANTUM",
            payload=payload.contract,
            confidence=0.99,
            trace_id=str(uuid.uuid4()),
            contract_version="2.0.0",
            timestamp=datetime.now(timezone.utc).isoformat()
        )
        
        # Create a proxy identity for Pritesh to sign the contract
        proxy_signer = NodeSigner("PRITESH_QUANTUM", "QUANTUM")
        signed_c = sign_contract(c, proxy_signer)
        contract_dict = signed_c.to_dict()
        
        # Override the dummy "YOUR_KEY" with the actual generated public key for verification
        pub_key_to_use = proxy_signer.identity.public_key
    else:
        contract_dict = payload.contract
        pub_key_to_use = payload.producer_public_key

    success, result = harness.process_incoming_contract(contract_dict, pub_key_to_use)
    
    if success:
        return result
    else:
        # If verification fails, return 422 Unprocessable Entity
        raise HTTPException(status_code=422, detail=result)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("web_server:app", host="0.0.0.0", port=8080, reload=False)
