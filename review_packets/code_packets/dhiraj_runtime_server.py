import uvicorn
import hashlib
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import time

app = FastAPI(title="Dhiraj Runtime API")

class ExecutionRequest(BaseModel):
    trace_id: str
    producer_type: str
    payload: dict
    confidence: float

@app.post("/execute")
async def execute_task(req: ExecutionRequest):
    """
    Simulates remote execution by the Dhiraj Runtime.
    Returns deterministic status and an acknowledgment payload.
    """
    if req.confidence < 0.3:
        status = "HALT:LOW_CONFIDENCE"
    elif req.confidence < 0.7:
        status = "ACK:DEGRADED"
    else:
        status = "ACK:OK"
        
    # Create deterministic runtime hash based on input payload
    hasher = hashlib.sha256()
    hasher.update(req.trace_id.encode())
    hasher.update(str(req.confidence).encode())
    runtime_hash = hasher.hexdigest()

    return {
        "contract_trace_id": req.trace_id,
        "producer_type": req.producer_type,
        "ack": status,
        "confidence": req.confidence,
        "runtime_hash": runtime_hash,
        "execution_timestamp": str(time.time()),
        "runtime": "DHIRAJ_RUNTIME_v1"
    }

@app.get("/health")
async def health_check():
    return {"status": "UP", "runtime": "Dhiraj"}

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8001)
