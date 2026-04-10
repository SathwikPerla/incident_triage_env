from pydantic import BaseModel, Field
from typing import Dict

class Action(BaseModel):
    command: str = Field(..., description="The shell command to execute: 'ls', 'ps', 'df', 'systemctl', 'truncate', 'rm'")
    args: str = Field("", description="Arguments for the command (e.g., PID, file path, or service name)")

class Observation(BaseModel):
    stdout: str
    stderr: str
    exit_code: int
    system_load: float
    disk_usage_percent: float
    services_status: Dict[str, str]

class Reward(BaseModel):
    value: float
    reason: str