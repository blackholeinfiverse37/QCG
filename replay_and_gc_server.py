import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Dict, Any
import time

app = FastAPI(title="Replay & GC Governance API")

class ReplayRequest(BaseModel):
    trace_id: str
    issued_at: float

class GovernanceRequest(BaseModel):
    contract: Dict[str, Any]

# Simulated in-memory storage for replay sequences
replay_sequences = {}
sequence_counter = 0

@app.post("/replay/verify")
async def verify_replay(req: ReplayRequest):
    """
    Simulates Replay Authority validation.
    Checks for duplicates and issues sequence numbers.
    """
    global sequence_counter
    if req.trace_id in replay_sequences:
        return {
            "is_valid": False,
            "status": "DUPLICATE_TRACE",
            "sequence_number": replay_sequences[req.trace_id]
        }
    
    sequence_counter += 1
    replay_sequences[req.trace_id] = sequence_counter
    
    return {
        "is_valid": True,
        "status": "OK",
        "sequence_number": sequence_counter
    }

@app.post("/governance/verify")
async def verify_governance(req: GovernanceRequest):
    """
    Simulates Constitutional GC validation.
    """
    producer_type = req.contract.get("producer_type", "UNKNOWN")
    
    if producer_type not in ["QUANTUM", "CLASSICAL", "HYBRID"]:
        return {
            "passed": False,
            "halt_signal": "HALT:UNAUTHORIZED_PRODUCER",
            "reason": f"Producer type {producer_type} not authorized by GC policy"
        }
        
    return {
        "passed": True,
        "halt_signal": "OK",
        "reason": "Contract authorized"
    }

@app.get("/health")
async def health_check():
    return {"status": "UP", "service": "Replay_GC"}

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8002)
