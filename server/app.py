import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, Optional

from src.environment import IncidentEnv
from src.models import Action, Observation

app = FastAPI(
    title="Incident Triage Environment",
    version="1.0.0",
    description="SRE Simulator for server incident response",
    docs_url="/docs",
    openapi_url="/openapi.json"
)

# Shared environment instance
env = IncidentEnv()

# --- MODELS ---
class HealthResponse(BaseModel):
    status: str = "healthy"

class ResetRequest(BaseModel):
    task_id: Optional[str] = "disk_full_easy"

# --- ENDPOINTS ---
@app.get("/")
async def root():
    return {"status": "online", "message": "API is running", "version": "1.0.0"}

@app.get("/health")
async def health():
    return HealthResponse()

@app.get("/metadata")
async def metadata():
    return {"name": "incident_triage", "description": "SRE cascading failure simulation"}

@app.get("/schema")
async def get_schema():
    return {
        "action": Action.model_json_schema(),
        "observation": Observation.model_json_schema(),
    }

@app.post("/reset")
async def reset(request: Optional[ResetRequest] = None):
    task_id = request.task_id if request else "disk_full_easy"
    obs = await env.reset(task_id)
    return {"status": "success", "observation": obs}

@app.post("/step")
async def step(action: Action):
    obs, reward, done, info = await env.step(action)
    return {
        "observation": obs,
        "reward": reward,
        "done": done,
        "info": info
    }

@app.get("/state")
async def get_state():
    state_data = await env.state()
    return state_data

def main():
    uvicorn.run("server.app:app", host="0.0.0.0", port=7860, reload=False)

if __name__ == "__main__":
    main()