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

An OpenEnv environment that simulates real-world SRE (Site Reliability Engineering) incident response. An AI agent must diagnose and resolve server incidents — disk pressure, crashed services, and cascading failures — using the same command-line tools a human engineer would reach for.

## Real-World Use Case

SRE teams respond to production incidents daily: disks fill up, services crash, and one failure cascades into another. Training and evaluating AI agents on these scenarios produces systems that can assist on-call engineers, triage alerts faster, and reduce mean time to recovery (MTTR).

## Action Space

Actions are structured JSON objects submitted to `POST /step`:

| Field | Type | Description |
|-------|------|-------------|
| `command` | `str` | Shell command: `df`, `ps`, `rm`, `truncate`, `systemctl` |
| `args` | `str` | Arguments: e.g. `/tmp`, `restart nginx`, `-h` |

Example: `{"command": "systemctl", "args": "restart nginx"}`

## Observation Space

Each step returns a JSON object with:

| Field | Type | Description |
|-------|------|-------------|
| `stdout` | `str` | Command stdout output |
| `stderr` | `str` | Command stderr (empty if success) |
| `exit_code` | `int` | 0 = success, non-zero = error |
| `system_load` | `float` | Current CPU load average |
| `disk_usage_percent` | `float` | Disk usage as a percentage |
| `services_status` | `dict[str, str]` | Map of service name → status (`running`, `stopped`, `error`) |

## Tasks

| Task ID | Difficulty | Description |
|---------|-----------|-------------|
| `disk_full_easy` | Easy | Disk at 95%. Clear `/tmp` to free space and restore service. |
| `service_crash_medium` | Medium | Nginx has crashed. Diagnose the state and restart the service. |
| `cascading_failure_hard` | Hard | Disk full caused DB crash. Clear logs AND restart both postgres and app. |

## Reward Design

Rewards are **dense and partial** — the agent receives signal at every step:

| Action | Reward |
|--------|--------|
| Each step taken | −0.01 (time penalty) |
| `rm /tmp` (clears disk) | +0.30 |
| `truncate` (clears logs) | +0.30 |
| `systemctl restart <svc>` (success) | +0.50 |
| `systemctl restart` when disk full | −0.10 |
| Unknown/invalid command | −0.10 |
| Episode fully resolved (bonus) | +0.50 |

Scores are normalized to `[0.0, 1.0]`.

## Setup

```bash
pip install -r requirements.txt
```

Set environment variables:
```bash
export API_BASE_URL="https://router.huggingface.co/v1"
export MODEL_NAME="Qwen/Qwen2.5-72B-Instruct"
export API_KEY="your-hf-token"
```

## Run

**Local:**
```bash
python inference.py
```

**Docker:**
```bash
docker build -t incident-triage .
docker run -p 7860:7860 incident-triage
```

**API endpoints:**
- `POST /reset` — reset environment to a task's initial state
- `POST /step` — submit an action, receive observation + reward
- `GET /state` — inspect current environment state

## Baseline Scores

Scores from a single run of `Qwen/Qwen2.5-72B-Instruct` via the HF router:

| Task | Score | Steps |
|------|-------|-------|
| `disk_full_easy` | 0.790 | 1 |
| `service_crash_medium` | 0.990 | 1 |
| `cascading_failure_hard` | 1.000 | 3 |
