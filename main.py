from fastapi import FastAPI
from src.environment import IncidentEnv

app = FastAPI()
env = IncidentEnv()


@app.post("/reset")
async def reset():
    obs = await env.reset()
    return obs.model_dump()


@app.get("/state")
async def state():
    return await env.state()