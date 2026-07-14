from pathlib import Path
import os
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
VENV_DIR = ROOT / ".venv"
VENV_PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"


def _running_in_project_venv() -> bool:
    try:
        return Path(sys.prefix).resolve() == VENV_DIR.resolve()
    except OSError:
        return False


if not getattr(sys, "frozen", False) and VENV_PYTHON.exists() and not _running_in_project_venv():
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    subprocess.Popen(
        [str(VENV_PYTHON), str(Path(__file__).resolve()), *sys.argv[1:]],
        cwd=str(ROOT),
        env=env,
        creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
    )
    raise SystemExit(0)

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

if "--hymt2-worker" in sys.argv:
    from autodub.services.hymt2_worker import main as run_hymt2_worker

    worker_args = [argument for argument in sys.argv[1:] if argument != "--hymt2-worker"]
    raise SystemExit(run_hymt2_worker(worker_args))

from autodub.desktop.main import main


if __name__ == "__main__":
    main()

