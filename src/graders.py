from typing import Dict


def grade_episode(
    rewards: list,
    final_services: Dict[str, str],
    final_disk_usage: float,
    steps_taken: int,
    max_steps: int,
) -> float:

    # 🔥 NEVER return 0.0
    if not rewards:
        return 0.01

    all_services_ok = all(s == "running" for s in final_services.values())
    disk_ok = final_disk_usage < 90.0

    base_score = sum(rewards)

    # initial clamp
    score = max(0.0, min(1.0, base_score))

    # efficiency bonus
    if all_services_ok and disk_ok and steps_taken < max_steps:
        efficiency = ((max_steps - steps_taken) / max_steps) * 0.1
        score += efficiency  # ← IMPORTANT: don't clamp yet

    # penalty
    if not all_services_ok or not disk_ok:
        score *= 0.5

    # 🔥 FINAL GUARANTEED CLAMP (ONLY HERE)
    if score <= 0.0:
        score = 0.01
    elif score >= 1.0:
        score = 0.99

    return round(score, 4)