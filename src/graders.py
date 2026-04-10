from typing import Dict


def grade_episode(
    rewards: list,
    final_services: Dict[str, str],
    final_disk_usage: float,
    steps_taken: int,
    max_steps: int,
) -> float:
    """
    Grade a completed incident triage episode.

    Returns a float in [0.0, 1.0] based on:
    - Whether all services are running
    - Whether disk usage is below the critical threshold
    - Efficiency bonus for solving quickly

    Never returns a constant — score depends on agent behaviour.
    """
    if not rewards:
        return 0.0

    all_services_ok = all(s == "running" for s in final_services.values())
    disk_ok = final_disk_usage < 90.0

    base_score = sum(rewards)
    score = max(0.0, min(1.0, base_score))

    # Efficiency bonus: only if fully resolved, up to 0.1 extra
    if all_services_ok and disk_ok and steps_taken < max_steps:
        efficiency = ((max_steps - steps_taken) / max_steps) * 0.1
        score = min(1.0, score + efficiency)

    # Penalty if not resolved at all
    if not all_services_ok or not disk_ok:
        score *= 0.5

    return round(max(0.0, min(1.0, score)), 4)
