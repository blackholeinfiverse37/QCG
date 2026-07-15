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
    success, result = harness.process_incoming_contract(payload.contract, payload.producer_public_key)
    
    if success:
        return result
    else:
        # If verification fails, return 422 Unprocessable Entity
        raise HTTPException(status_code=422, detail=result)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("web_server:app", host="0.0.0.0", port=8080, reload=False)
