"""
web_server.py — Phase 4: Operational Readiness Endpoints

Provides a lightweight, production-grade HTTP API for TANTRA ecosystem integration.
Endpoints:
- GET /health         : Health, readiness, and metrics.
- GET /capabilities   : Capability manifest and API contracts.
- POST /verify        : Synchronous end-to-end integration flow.
"""

import logging
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from typing import Dict, Any

from integration_harness import TANTRAIntegrationHarness
from integration_interfaces import CapabilityDiscoveryInterface

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Global harness instance
harness = TANTRAIntegrationHarness()

app = FastAPI(
    title="Execution Provenance API",
    description="Operational readiness and evidence retrieval APIs for Phase 2",
    version="1.0.0"
)

class VerifyRequest(BaseModel):
    contract: Dict[str, Any]
    producer_public_key: str

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

if __name__ == "__main__":
    import uvicorn
    logging.info("Starting FastAPI Operational Readiness API on port 8080...")
    uvicorn.run("web_server:app", host="127.0.0.1", port=8080, reload=True)
