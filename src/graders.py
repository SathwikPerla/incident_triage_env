from typing import Dict


def grade_episode(
    rewards: list,
    final_services: Dict[str, str],
    final_disk_usage: float,
    steps_taken: int,
    max_steps: int,
) -> float:
    if not rewards:
        return 0.01  # 🔥 FIX

    all_services_ok = all(s == "running" for s in final_services.values())
    disk_ok = final_disk_usage < 90.0

    base_score = sum(rewards)
    score = max(0.0, min(1.0, base_score))

    if all_services_ok and disk_ok and steps_taken < max_steps:
        efficiency = ((max_steps - steps_taken) / max_steps) * 0.1
        score = min(1.0, score + efficiency)

    if not all_services_ok or not disk_ok:
        score *= 0.5

    # 🔥 FINAL FIX (INSIDE function)
    score = max(0.01, min(0.99, score))

    return round(score, 4)