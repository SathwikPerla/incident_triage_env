import asyncio
import copy
from typing import Dict, Any, Tuple
from .models import Action, Observation
from .tasks import TASKS

class IncidentEnv:
    def __init__(self):
        self.state_data = {}
        self.current_task_id = "disk_full_easy"
        self.steps = 0
        self.max_steps = 10

    async def reset(self, task_id: str = "disk_full_easy") -> Observation:
        self.current_task_id = task_id
        self.state_data = copy.deepcopy(TASKS[task_id]["initial_state"])
        self.steps = 0
        return self._get_obs()

    def _get_obs(self) -> Observation:
        return Observation(
            stdout=self.state_data.get("last_stdout", ""),
            stderr=self.state_data.get("last_stderr", ""),
            exit_code=self.state_data.get("last_exit_code", 0),
            system_load=self.state_data["system_load"],
            disk_usage_percent=self.state_data["disk_usage"],
            services_status=self.state_data["services"]
        )

    async def step(self, action: Action) -> Tuple[Observation, float, bool, dict]:
        self.steps += 1
        reward_val = -0.01  
        
        cmd = action.command.lower()
        arg = action.args.strip()
        
        self.state_data["last_stdout"] = ""
        self.state_data["last_stderr"] = ""
        self.state_data["last_exit_code"] = 0

        if cmd == "df":
            self.state_data["last_stdout"] = f"Filesystem Use%\n/dev/sda1 {self.state_data['disk_usage']}%"
            
        elif cmd == "ps":
            self.state_data["last_stdout"] = f"USER PID %CPU %MEM COMMAND\nroot 1 {self.state_data['system_load']} 1.0 /sbin/init"
            
        elif cmd == "rm" and "tmp" in arg:
            if self.state_data["disk_usage"] > 20:
                self.state_data["disk_usage"] = max(10.0, self.state_data["disk_usage"] - 40)
                self.state_data["last_stdout"] = "Removed temporary files."
                reward_val += 0.3
            else:
                self.state_data["last_stdout"] = "No files removed."

        elif cmd == "truncate":
            self.state_data["disk_usage"] = max(10.0, self.state_data["disk_usage"] - 30)
            self.state_data["last_stdout"] = "Logs truncated."
            reward_val += 0.3

        elif cmd == "systemctl" and "restart" in arg:
            service = arg.replace("restart ", "").strip()
            if service in self.state_data["services"]:
                if self.state_data["disk_usage"] < 90:
                    self.state_data["services"][service] = "running"
                    self.state_data["last_stdout"] = f"Service {service} restarted successfully."
                    reward_val += 0.5
                else:
                    self.state_data["last_stderr"] = f"Failed to start {service}: No space left on device."
                    self.state_data["last_exit_code"] = 1
                    reward_val -= 0.1
            else:
                self.state_data["last_stderr"] = f"Unit {service}.service not found."
                self.state_data["last_exit_code"] = 1
                
        else:
            self.state_data["last_stderr"] = f"{cmd}: command not found or invalid arguments"
            self.state_data["last_exit_code"] = 127
            reward_val -= 0.1

        all_services_running = all(status == "running" for status in self.state_data["services"].values())
        disk_ok = self.state_data["disk_usage"] < 90
        
        done = self.steps >= self.max_steps or (all_services_running and disk_ok)
        
        if done and all_services_running and disk_ok:
            reward_val += 0.5

        obs = self._get_obs()
        return obs, reward_val, done, {}

    async def state(self) -> Dict[str, Any]:
        return self.state_data