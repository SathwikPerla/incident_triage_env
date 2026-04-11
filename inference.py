import os
import sys
import subprocess

# Auto-install required packages if the validator runs without pip install
_REQUIRED = ["openai", "pydantic"]
for _pkg in _REQUIRED:
    try:
        __import__(_pkg)
    except ImportError:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", _pkg, "-q"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

# Ensure project root is in path before any local imports
_root = os.path.dirname(os.path.abspath(__file__))
if _root not in sys.path:
    sys.path.insert(0, _root)

import asyncio
import json
from typing import List, Optional

from openai import OpenAI

from src.environment import IncidentEnv
from src.models import Action

# --- Credentials: strictly use validator-injected env vars ---
API_KEY = os.environ.get("API_KEY") or os.environ.get("HF_TOKEN")
API_BASE_URL = os.environ["API_BASE_URL"]
MODEL_NAME = os.environ.get("MODEL_NAME", "Qwen/Qwen2.5-72B-Instruct")

BENCHMARK = "incident_triage"
TASKS = ["disk_full_easy", "service_crash_medium", "cascading_failure_hard"]

SYSTEM_PROMPT = (
    "You are an expert SRE. Diagnose and fix system incidents.\n"
    "Available commands: df, ps, rm (args: /tmp), truncate, systemctl (args: restart <service>).\n"
    "If disk > 80%: use 'rm' with args '/tmp' OR 'truncate'.\n"
    "If a service is stopped/error: use 'systemctl' with args 'restart <service_name>'.\n"
    "Respond ONLY with valid JSON on a single line: {\"command\": \"...\", \"args\": \"...\"}"
)


# --- Logging helpers (exact format required by spec) ---

def log_start(task: str, env: str, model: str) -> None:
    print(f"[START] task={task} env={env} model={model}", flush=True)


def log_step(step: int, action: str, reward: float, done: bool, error: Optional[str]) -> None:
    error_val = error if error else "null"
    print(
        f"[STEP] step={step} action={action} reward={reward:.2f} done={str(done).lower()} error={error_val}",
        flush=True,
    )


def log_end(success: bool, steps: int, score: float, rewards: List[float]) -> None:
    rewards_str = ",".join(f"{r:.2f}" for r in rewards) if rewards else "0.00"
    print(
        f"[END] success={str(success).lower()} steps={steps} score={score:.3f} rewards={rewards_str}",
        flush=True,
    )


# --- LLM call (always goes through API_BASE_URL) ---

def get_action_from_llm(client: OpenAI, obs, step: int):
    """Call the LLM proxy and parse the action. Raises on network/auth errors."""
    user_prompt = f"Step {step}\nObservation: {obs.model_dump_json()}"
    completion = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.2,
        max_tokens=100,
        stream=False,
    )
    content = (completion.choices[0].message.content or "").strip()

    # Strip markdown code fences if present
    if content.startswith("```"):
        parts = content.split("```")
        content = parts[1].lstrip("json").strip() if len(parts) > 1 else content

    try:
        data = json.loads(content)
        return data.get("command", "df"), data.get("args", "")
    except json.JSONDecodeError:
        # LLM call was made (proxy saw it); fallback to safe diagnostic command
        return "df", ""


# --- Per-task episode runner ---

async def run_task(client: OpenAI, task_id: str) -> None:
    env = IncidentEnv()
    obs = await env.reset(task_id)

    log_start(task=task_id, env=BENCHMARK, model=MODEL_NAME)

    rewards: List[float] = []
    steps_taken = 0
    score = 0.0
    success = False

    try:
        for step in range(1, 11):
            steps_taken = step
            llm_error: Optional[str] = None

            # Always attempt the LLM call; catch errors and fall back gracefully
            try:
                command, args = get_action_from_llm(client, obs, step)
            except Exception as exc:
                llm_error = str(exc)
                command, args = "df", ""

            action = Action(command=command, args=args)
            action_str = f"{action.command} {action.args}".strip()

            try:
                obs, reward, done, _ = await env.step(action)
            except Exception as exc:
                log_step(step, action_str, 0.0, True, str(exc))
                break

            rewards.append(reward)
            log_step(step, action_str, reward, done, llm_error)

            if done:
                break

        total = sum(rewards)
        score = max(0.0, min(1.0, total))
        success = score > 0.0

    finally:
        log_end(success=success, steps=steps_taken, score=score, rewards=rewards)


# --- Entry point: run all 3 tasks sequentially ---

async def main() -> None:
    client = OpenAI(api_key=API_KEY, base_url=API_BASE_URL)
    for task_id in TASKS:
        await run_task(client, task_id)


if __name__ == "__main__":
    asyncio.run(main())
