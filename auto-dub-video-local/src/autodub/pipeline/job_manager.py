import os
import subprocess
import time
from typing import Dict, List, Set


_cancelled_jobs: Set[str] = set()
_active_processes: Dict[str, List[subprocess.Popen]] = {}


def start_job(job_id: str):
    if job_id in _cancelled_jobs:
        _cancelled_jobs.remove(job_id)
    _active_processes[job_id] = []


def _kill_process_tree(process: subprocess.Popen, timeout: float = 1.5):
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(process.pid)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    else:
        try:
            process.kill()
        except Exception:
            pass
    try:
        process.wait(timeout=timeout)
    except Exception:
        pass


def cancel_job(job_id: str):
    _cancelled_jobs.add(job_id)
    # Kill active subprocesses and their children so Windows releases job files.
    if job_id in _active_processes:
        for process in list(_active_processes[job_id]):
            try:
                if process.poll() is not None:
                    continue
                print(f"Stopping subprocess tree PID {process.pid} for job {job_id}")
                process.terminate()
                process.wait(timeout=0.8)
            except Exception:
                _kill_process_tree(process)
        _active_processes[job_id] = []
    time.sleep(0.1)


def is_cancelled(job_id: str) -> bool:
    return job_id in _cancelled_jobs


def check_cancellation(job_id: str):
    if is_cancelled(job_id):
        raise RuntimeError("Job cancelled by user.")


def register_process(job_id: str, process: subprocess.Popen):
    if is_cancelled(job_id):
        _kill_process_tree(process)
        raise RuntimeError("Job cancelled by user.")
    if job_id not in _active_processes:
        _active_processes[job_id] = []
    _active_processes[job_id].append(process)


def unregister_process(job_id: str, process: subprocess.Popen):
    if job_id in _active_processes:
        try:
            _active_processes[job_id].remove(process)
        except ValueError:
            pass


def clean_job(job_id: str):
    if job_id in _cancelled_jobs:
        _cancelled_jobs.remove(job_id)
    if job_id in _active_processes:
        del _active_processes[job_id]
