"""Download the pinned Whisper speech model for the offline installer."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from haizflow.config import MODELS_DIR, WHISPER_MODEL_REPO, WHISPER_MODEL_REVISION  # noqa: E402
from haizflow.core.model_integrity import verify_whisper_model  # noqa: E402
from huggingface_hub import snapshot_download  # noqa: E402


def main() -> int:
    destination = Path(MODELS_DIR) / "whisper" / "small"
    destination.mkdir(parents=True, exist_ok=True)
    snapshot_download(
        repo_id=WHISPER_MODEL_REPO,
        revision=WHISPER_MODEL_REVISION,
        local_dir=str(destination),
    )
    verify_whisper_model(destination)
    print(f"Whisper model ready at pinned revision {WHISPER_MODEL_REVISION}: {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
