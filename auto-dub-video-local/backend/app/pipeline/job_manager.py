import os
import subprocess
from typing import Dict, List, Set

# Global states
_cancelled_jobs: Set[str] = set()
_active_processes: Dict[str, List[subprocess.Popen]] = {}

def start_job(job_id: str):
    if job_id in _cancelled_jobs:
        _cancelled_jobs.remove(job_id)
    _active_processes[job_id] = []

def cancel_job(job_id: str):
    _cancelled_jobs.add(job_id)
    # Kill any active subprocesses
    if job_id in _active_processes:
        for p in _active_processes[job_id]:
            try:
                print(f"Terminating subprocess PID {p.pid} for job {job_id}")
                p.terminate()
                p.wait(timeout=2)
            except Exception as e:
                # If terminate doesn't work, try kill
                try:
                    p.kill()
                except:
                    pass
        _active_processes[job_id] = []

def is_cancelled(job_id: str) -> bool:
    return job_id in _cancelled_jobs

def check_cancellation(job_id: str):
    if is_cancelled(job_id):
        raise RuntimeError("Job cancelled by user.")

def register_process(job_id: str, p: subprocess.Popen):
    if is_cancelled(job_id):
        try:
            p.terminate()
        except:
            pass
        raise RuntimeError("Job cancelled by user.")
    if job_id not in _active_processes:
        _active_processes[job_id] = []
    _active_processes[job_id].append(p)

def unregister_process(job_id: str, p: subprocess.Popen):
    if job_id in _active_processes:
        try:
            _active_processes[job_id].remove(p)
        except ValueError:
            pass

def clean_job(job_id: str):
    if job_id in _cancelled_jobs:
        _cancelled_jobs.remove(job_id)
    if job_id in _active_processes:
        del _active_processes[job_id]
