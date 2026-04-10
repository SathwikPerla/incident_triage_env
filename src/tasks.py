TASKS = {
    "disk_full_easy": {
        "description": "Disk is at 95%. Clear /tmp to restore service.",
        "initial_state": {
            "disk_usage": 95.0,
            "system_load": 0.5,
            "services": {"nginx": "running"},
            "last_stdout": "", "last_stderr": "", "last_exit_code": 0
        }
    },
    "service_crash_medium": {
        "description": "Nginx has crashed. Diagnose and restart.",
        "initial_state": {
            "disk_usage": 40.0,
            "system_load": 0.1,
            "services": {"nginx": "stopped"},
            "last_stdout": "", "last_stderr": "", "last_exit_code": 0
        }
    },
    "cascading_failure_hard": {
        "description": "Disk full caused DB crash. Clear logs AND restart DB.",
        "initial_state": {
            "disk_usage": 99.0,
            "system_load": 2.5,
            "services": {"postgres": "stopped", "app": "error"},
            "last_stdout": "", "last_stderr": "", "last_exit_code": 0
        }
    }
}