"""
web_server.py — Phase 4: Operational Readiness Endpoints

Provides a lightweight, production-grade HTTP API for TANTRA ecosystem integration via FastAPI.
Endpoints:
- GET /health, /health/live, /health/ready : Health, readiness, and metrics.
- GET /capabilities   : Capability manifest and API contracts.
- POST /verify        : Synchronous end-to-end integration flow.
<<<<<<< HEAD
=======
- GET /evidence/certificate/{execution_id} : Retrieves execution certificate for a given trace.
>>>>>>> 86f51a31442616a0759a9b57244d9d361d16197f
"""

import logging
from typing import Dict, Any

from fastapi import FastAPI, HTTPException, Request, Response
from pydantic import BaseModel

from integration_harness import TANTRAIntegrationHarness
from integration_interfaces import CapabilityDiscoveryInterface
<<<<<<< HEAD
=======
from provenance_api import execution_certificate, execution_history
>>>>>>> 86f51a31442616a0759a9b57244d9d361d16197f

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

<<<<<<< HEAD
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
=======
@app.get("/health", tags=["Health"])
@app.get("/health/live", tags=["Health"])
@app.get("/health/ready", tags=["Health"])
async def get_health():
    """Get health, readiness, and metrics data."""
    return harness.health_iface.get_health()

@app.get("/capabilities", tags=["Capabilities"])
async def get_capabilities():
    """Get capability manifest and API contracts."""
    return CapabilityDiscoveryInterface.discover_capabilities()

@app.post("/verify", tags=["Integration"])
async def verify_contract(req: VerifyRequest):
    """Synchronous end-to-end integration flow verification."""
    success, result = harness.process_incoming_contract(req.contract, req.producer_public_key)
    if not success:
        raise HTTPException(status_code=422, detail=result)
    return result

@app.get("/evidence/certificate/{execution_id}", tags=["Provenance"])
async def get_certificate(execution_id: str):
    """Retrieves execution certificate with Merkle proof for MDU retrieval."""
    # Find record
    record = None
    for r in harness.ledger._records:
        if r.execution_id == execution_id:
            record = r
            break
            
    if not record:
        raise HTTPException(status_code=404, detail="Execution record not found in ledger")
        
    try:
        cert = execution_certificate(record, harness.ledger)
        return cert
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate certificate: {str(e)}")

@app.get("/evidence/trace/{trace_id}", tags=["Provenance"])
async def get_trace_history(trace_id: str):
    """Retrieves execution history for a given trace."""
    history = execution_history(harness.ledger, trace_id)
    if not history:
        raise HTTPException(status_code=404, detail="No execution records found for this trace ID")
    return {"trace_id": trace_id, "history": [h.__dict__ for h in history]}

if __name__ == "__main__":
    import uvicorn
    logging.info("Starting FastAPI Operational Readiness API on port 8080...")
>>>>>>> 86f51a31442616a0759a9b57244d9d361d16197f
    uvicorn.run("web_server:app", host="0.0.0.0", port=8080, reload=False)
