from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.desktop.main import main


if __name__ == "__main__":
    main()
