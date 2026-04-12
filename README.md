---
title: Incident Triage Env
emoji: 🚨
colorFrom: red
sdk: docker
app_port: 7860
tags:
  - openenv
pinned: false
---

# Incident Triage Environment

An **OpenEnv-compliant** reinforcement learning environment that simulates real-world **SRE (Site Reliability Engineering) incident response**. An AI agent must diagnose and resolve server incidents — disk pressure, crashed services, and cascading failures — using the same command-line tools a human on-call engineer would use in production.

---

## Motivation

Every engineering organization running production software maintains an on-call rotation. When alerts fire, engineers must:

1. **Identify** what is failing (disk? service? network?)
2. **Diagnose** the root cause from system signals
3. **Remediate** in the correct order — wrong steps make things worse

Training and evaluating AI agents on these scenarios produces systems that can:
- Assist on-call engineers during active incidents
- Triage alerts faster and reduce escalations
- Measurably lower **Mean Time To Recovery (MTTR)**

This environment models real SRE runbooks. Tasks mirror actual incident patterns documented by major engineering teams: disk pressure filling before log rotation runs, services failing to restart due to missing disk space, and database crashes causing cascading application failures. This is not a toy — the action vocabulary, failure modes, and remediation steps are drawn directly from production incident playbooks.

---

## Environment Overview

| Property | Value |
|----------|-------|
| **Domain** | Site Reliability Engineering (SRE) / DevOps |
| **Task type** | Sequential decision-making, agentic tool use |
| **Episode length** | Up to 10 steps |
| **Action space** | Structured JSON (command + args) |
| **Observation space** | Structured JSON (stdout, stderr, exit code, system metrics, service states) |
| **Reward signal** | Dense — partial credit at every step, not just episode end |
| **Number of tasks** | 3 (easy → medium → hard) |
| **OpenEnv spec** | Fully compliant — `reset()`, `step()`, `state()`, typed Pydantic models |

---

## Action Space

Actions are structured JSON objects with two fields, submitted to the `POST /step` endpoint.

| Field | Type | Description |
|-------|------|-------------|
| `command` | `str` | The shell command to execute |
| `args` | `str` | Arguments passed to the command (empty string if none) |

### Available Commands

| Command | Example Args | Effect on Environment State |
|---------|-------------|----------------------------|
| `df` | `-h` or `""` | Returns current disk usage percentage in stdout |
| `ps` | `aux` or `""` | Returns CPU load and process list in stdout |
| `rm` | `/tmp` | Clears temporary files; reduces `disk_usage_percent` by ~40pp (only if disk > 20%) |
| `truncate` | `/var/log/app.log` | Truncates log files; reduces `disk_usage_percent` by ~30pp |
| `systemctl` | `restart nginx` | Attempts to restart a named service; succeeds only when `disk_usage_percent` < 90% |

**Invalid commands** (unrecognized command or wrong args) return `exit_code: 127` and a −0.10 reward penalty.

**Example action:**
```json
{"command": "systemctl", "args": "restart nginx"}
```

**Pydantic schema (`Action`):**
```python
class Action(BaseModel):
    command: str  # One of: df, ps, rm, truncate, systemctl
    args: str     # e.g. "/tmp", "restart nginx", "-h"
```

---

## Observation Space

Each call to `step()` and `reset()` returns an `Observation` object representing the full current system snapshot.

| Field | Type | Range / Values | Description |
|-------|------|---------------|-------------|
| `stdout` | `str` | Any string | Standard output from the last command |
| `stderr` | `str` | Any string | Standard error output (empty string if no error) |
| `exit_code` | `int` | `0` = success, `1` = failure, `127` = not found | Exit status of last command |
| `system_load` | `float` | `0.0` – `∞` (healthy: < 1.0) | CPU load average |
| `disk_usage_percent` | `float` | `0.0` – `100.0` | Disk usage as a percentage; critical at > 90% |
| `services_status` | `dict[str, str]` | `"running"`, `"stopped"`, `"error"` | Map of service name → current status |

**Example observation after a `df` command:**
```json
{
  "stdout": "Filesystem Use%\n/dev/sda1 95%",
  "stderr": "",
  "exit_code": 0,
  "system_load": 0.5,
  "disk_usage_percent": 95.0,
  "services_status": {"nginx": "running"}
}
```

**Example observation after a failed `systemctl restart` (disk full):**
```json
{
  "stdout": "",
  "stderr": "Failed to start postgres: No space left on device.",
  "exit_code": 1,
  "system_load": 2.5,
  "disk_usage_percent": 99.0,
  "services_status": {"postgres": "stopped", "app": "error"}
}
```

**Pydantic schema (`Observation`):**
```python
class Observation(BaseModel):
    stdout: str
    stderr: str
    exit_code: int
    system_load: float
    disk_usage_percent: float
    services_status: Dict[str, str]
```

---

## Tasks

Three tasks span the full difficulty spectrum. Each defines a concrete objective with a deterministic programmatic grader that scores performance from `0.0` to `1.0`.

---

### Task 1 — `disk_full_easy` · Difficulty: Easy

**Scenario:** The disk has filled to 95% capacity. The system is at imminent risk of failure. No services have crashed yet, but any write-heavy operation could tip it over.

**Objective:** Clear temporary files to bring disk usage below 90%.

**Initial state:**
```json
{
  "disk_usage": 95.0,
  "system_load": 0.5,
  "services": {"nginx": "running"}
}
```

**Optimal solution:** `rm /tmp` — solves the task in a single step.

**Why it is easy:** One failure mode, one service, one corrective action. The observation directly tells the agent disk is high. Any agent that reads `disk_usage_percent` and maps it to `rm /tmp` solves this immediately.

**Episode boundary:** Done when disk < 90% and all services running, or after 10 steps.

**Expected baseline score:** `0.75 – 0.99`

---

### Task 2 — `service_crash_medium` · Difficulty: Medium

**Scenario:** Nginx has crashed unexpectedly. Disk usage is normal. The web service is completely down.

**Objective:** Identify that the service — not the disk — is the root cause, then restart nginx.

**Initial state:**
```json
{
  "disk_usage": 40.0,
  "system_load": 0.1,
  "services": {"nginx": "stopped"}
}
```

**Optimal solution:** `systemctl restart nginx` — optionally preceded by `ps` or `df` for diagnosis.

**Why it is medium:** The disk is healthy (40%), so the agent must avoid the reflexive "disk is the problem" pattern. It must read `services_status` from the observation, identify the stopped service, and issue the correct restart command. Agents that `rm /tmp` first waste steps and incur time penalties.

**Episode boundary:** Done when all services are running, or after 10 steps.

**Expected baseline score:** `0.70 – 0.99`

---

### Task 3 — `cascading_failure_hard` · Difficulty: Hard

**Scenario:** The disk filled to 99%, which caused postgres to crash, which caused the application server to enter an error state. Two services are down simultaneously. Neither can be restarted while disk remains full — the OS has no space to write PID files or logs during startup.

**Objective:** Resolve the cascading failure in the correct dependency order:
1. Free disk space (`rm /tmp` or `truncate`)
2. Restart `postgres`
3. Restart `app`

**Initial state:**
```json
{
  "disk_usage": 99.0,
  "system_load": 2.5,
  "services": {"postgres": "stopped", "app": "error"}
}
```

**Why it is hard:**
- Restarting any service while `disk_usage_percent > 90%` **fails** and incurs a −0.10 penalty
- Requires correctly sequencing disk remediation *before* service restarts
- Two services must be restarted in dependency order (postgres before app)
- The high `system_load` (2.5) and dual service failures increase diagnostic complexity
- Weak agents that pattern-match on service status and restart immediately will fail and score poorly

**Expected score for weak agents:** `0.10 – 0.40` (attempt restart before clearing disk, accumulate penalties)

**Expected score for strong agents:** `0.60 – 0.99` (correctly sequence all three steps)

**Episode boundary:** Done when all services running and disk < 90%, or after 10 steps.

---

## Reward Function

The reward signal is **dense** — the agent receives feedback at every step throughout the trajectory, not only at episode end. This enables credit assignment for partial progress and meaningful learning signal across the full episode.

### Per-Step Rewards

| Event | Reward | Notes |
|-------|--------|-------|
| Any step taken | `−0.01` | Time penalty — encourages efficiency |
| `rm /tmp` (disk cleared) | `+0.30` | Only when `disk_usage_percent > 20%` |
| `truncate` (logs cleared) | `+0.30` | Always applies |
| `systemctl restart <svc>` succeeds | `+0.50` | Requires `disk_usage_percent < 90%` |
| `systemctl restart` when disk full | `−0.10` | Penalizes incorrect ordering |
| Invalid or unrecognized command | `−0.10` | Penalizes hallucinated commands |
| Episode fully resolved (completion bonus) | `+0.50` | All services running and disk < 90% |

### Episode Grader (`grade_episode`)

At the end of each episode, the grader computes a final normalized score:

1. **Base score** = sum of all per-step rewards, clamped to `[0.0, 1.0]`
2. **Efficiency bonus** = up to `+0.10` when the task is solved before the step limit: `(max_steps − steps_taken) / max_steps × 0.1`
3. **Failure penalty** = `× 0.5` if any service remains down or disk is still ≥ 90% at episode end
4. **Final clamp** = score is clamped to the open interval `(0.01, 0.99)` — scores of exactly `0.0` or `1.0` are not returned

**Score interpretation:**

| Score Range | Meaning |
|-------------|---------|
| `0.01 – 0.15` | Agent took mostly wrong actions; made things worse |
| `0.16 – 0.40` | Partial progress; some correct steps but failed to resolve |
| `0.41 – 0.70` | Task partially resolved; inefficient path or one service left down |
| `0.71 – 0.99` | Task fully resolved; score reflects efficiency |

**Why this design:**
- An agent that does nothing accumulates only time penalties → scores near `0.01`
- An agent that solves the task in one step scores near `0.85–0.99`
- An agent that acts incorrectly (restarts before clearing disk) scores `0.10–0.40`
- The grader is **deterministic and reproducible**: same trajectory always produces the same score

---

## OpenEnv Interface

This environment implements the full OpenEnv specification.

### Python Interface

```python
from src.environment import IncidentEnv
from src.models import Action

env = IncidentEnv()

# Reset to a specific task — returns Observation
obs = await env.reset("disk_full_easy")

# Submit an action — returns (Observation, float, bool, dict)
action = Action(command="rm", args="/tmp")
obs, reward, done, info = await env.step(action)

# Inspect raw state dict
state = await env.state()
```

### Method Signatures

| Method | Signature | Returns |
|--------|-----------|---------|
| `reset(task_id)` | `async (str) → Observation` | Initial observation for the given task |
| `step(action)` | `async (Action) → (Observation, float, bool, dict)` | Observation, reward, done flag, info dict |
| `state()` | `async () → Dict[str, Any]` | Current raw environment state |

### Typed Models (Pydantic v2)

| Model | Fields | Purpose |
|-------|--------|---------|
| `Action` | `command: str`, `args: str` | Agent's action at each step |
| `Observation` | `stdout`, `stderr`, `exit_code`, `system_load`, `disk_usage_percent`, `services_status` | Full system snapshot returned after each step |
| `Reward` | `value: float`, `reason: str` | Reward with human-readable explanation |

---

## API Endpoints

The environment runs as a **FastAPI server** on port `7860`. All endpoints accept and return JSON.

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | Health check — returns `{"status": "online"}` |
| `GET` | `/health` | Liveness probe — returns `{"status": "healthy"}` |
| `GET` | `/metadata` | Environment metadata (name, description) |
| `GET` | `/schema` | JSON schemas for `Action` and `Observation` models |
| `POST` | `/reset` | Reset to a task's initial state; returns initial observation |
| `POST` | `/step` | Submit an action; returns observation, reward, done, info |
| `GET` | `/state` | Inspect current raw environment state |
| `GET` | `/docs` | Interactive Swagger UI for manual testing |

**Reset request:**
```json
POST /reset
{"task_id": "cascading_failure_hard"}
```

**Step request:**
```json
POST /step
{"command": "rm", "args": "/tmp"}
```

**Step response:**
```json
{
  "observation": {
    "stdout": "Removed temporary files.",
    "stderr": "",
    "exit_code": 0,
    "system_load": 2.5,
    "disk_usage_percent": 59.0,
    "services_status": {"postgres": "stopped", "app": "error"}
  },
  "reward": 0.29,
  "done": false,
  "info": {}
}
```

---

## Setup & Usage

### Prerequisites

- Python 3.10+
- An OpenAI-compatible API endpoint and key (HF Router, OpenAI, Together, etc.)

### Install

```bash
pip install -r requirements.txt
```

Or with `uv` (recommended, used in Docker):
```bash
uv sync
```

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `API_KEY` | Yes | — | API key (`HF_TOKEN` also accepted for HF Router) |
| `API_BASE_URL` | Yes | — | Base URL of the OpenAI-compatible API |
| `MODEL_NAME` | No | `Qwen/Qwen2.5-72B-Instruct` | Model identifier |

```bash
export API_KEY="your-api-key"
export API_BASE_URL="https://router.huggingface.co/v1"
export MODEL_NAME="Qwen/Qwen2.5-72B-Instruct"
```

### Run the Baseline Agent

Runs the agent against all 3 tasks sequentially and prints step-by-step structured logs and final scores:

```bash
python inference.py
```

### Start the Server

```bash
python -m uvicorn server.app:app --host 0.0.0.0 --port 7860
```

---

## Baseline Scores

**Agent:** `Qwen/Qwen2.5-72B-Instruct` via HF Router
**Settings:** temperature `0.2` · max tokens `100` · max steps per episode `10`

| Task | Score | Steps | Outcome |
|------|-------|-------|---------|
| `disk_full_easy` | **0.790** | 1 | Solved in one command: `rm /tmp` |
| `service_crash_medium` | **0.990** | 1 | Solved in one command: `systemctl restart nginx` |
| `cascading_failure_hard` | **0.999** | 3 | Full multi-step: `truncate` → `restart postgres` → `restart app` |

### Baseline Log Format

Each task produces structured logs in this exact format:

```
[START] task=disk_full_easy env=incident_triage model=Qwen/Qwen2.5-72B-Instruct
[STEP] step=1 action=rm /tmp reward=0.79 done=true error=null
[END] success=true steps=1 score=0.790 rewards=0.79

[START] task=service_crash_medium env=incident_triage model=Qwen/Qwen2.5-72B-Instruct
[STEP] step=1 action=systemctl restart nginx reward=0.99 done=true error=null
[END] success=true steps=1 score=0.990 rewards=0.99

[START] task=cascading_failure_hard env=incident_triage model=Qwen/Qwen2.5-72B-Instruct
[STEP] step=1 action=truncate /var/log/app.log reward=0.29 done=false error=null
[STEP] step=2 action=systemctl restart postgres reward=0.49 done=false error=null
[STEP] step=3 action=systemctl restart app reward=0.99 done=true error=null
[END] success=true steps=3 score=0.999 rewards=0.29,0.49,0.99
```

---

## Project Structure

```
incident-triage-env/
├── src/
│   ├── __init__.py
│   ├── environment.py    # IncidentEnv — reset(), step(), state() implementation
│   ├── models.py         # Pydantic v2 models: Action, Observation, Reward
│   ├── tasks.py          # Task definitions and initial states
│   └── graders.py        # grade_episode() — deterministic 0.0–1.0 scorer
├── server/
│   ├── __init__.py
│   └── app.py            # FastAPI server — all HTTP endpoints
├── inference.py          # Baseline agent script (OpenAI-compatible)
├── main.py               # FastAPI app alias
├── openenv.yaml          # OpenEnv metadata and task registry
├── pyproject.toml        # Project config, dependencies, entrypoints
├── Dockerfile            # Container definition for HF Space deployment
└── requirements.txt      # Direct dependency list
```

---

## OpenEnv Spec (`openenv.yaml`)

```yaml
name: incident_triage
version: "1.0.0"
description: "SRE Simulator for server incident response"
entry_point: "src.environment:IncidentEnv"
tasks:
  - id: disk_full_easy
    difficulty: easy
  - id: service_crash_medium
    difficulty: medium
  - id: cascading_failure_hard
    difficulty: hard
```

---

## Why This Environment is Valuable for the Agent Community

**For RL researchers:** Dense reward signal over a structured action vocabulary enables policy gradient and Q-learning methods to learn meaningful behavior from trajectory data.

**For LLM agent evaluators:** The three tasks form a natural benchmark for measuring tool-use capability, multi-step planning, and the ability to avoid a common failure mode (restarting services before fixing the underlying resource issue).

**For the SRE community:** A well-performing agent on this benchmark is directly applicable to building alert triage assistants, runbook automation, and on-call copilots — real infrastructure use cases with measurable business value.

The environment fills a gap in the current OpenEnv ecosystem: most existing environments focus on text manipulation, coding, or game domains. Incident triage represents a high-stakes, time-sensitive operational domain where agent errors have real costs and multi-step dependency reasoning is required to succeed.
