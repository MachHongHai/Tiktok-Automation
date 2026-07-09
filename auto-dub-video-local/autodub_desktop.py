from pathlib import Path
import os
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
VENV_PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"

if (
    VENV_PYTHON.exists()
    and Path(sys.executable).resolve() != VENV_PYTHON.resolve()
    and os.environ.get("AUTO_DUB_SKIP_VENV_RELAUNCH") != "1"
):
    env = os.environ.copy()
    env["AUTO_DUB_SKIP_VENV_RELAUNCH"] = "1"
    subprocess.Popen([str(VENV_PYTHON), str(Path(__file__).resolve())], env=env)
    raise SystemExit(0)

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autodub.desktop.main import main


if __name__ == "__main__":
    main()

