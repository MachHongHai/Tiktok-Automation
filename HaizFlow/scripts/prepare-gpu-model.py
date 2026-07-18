"""Download the official HY-MT2 Transformers checkpoint for an offline installer."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from huggingface_hub import snapshot_download  # noqa: E402

from haizflow.config import HYMT2_MODEL, HYMT2_MODEL_REVISION, MODELS_DIR  # noqa: E402
from haizflow.core.model_integrity import verify_gpu_model  # noqa: E402


def main() -> int:
    destination = Path(MODELS_DIR) / "hymt2-transformers"
    destination.mkdir(parents=True, exist_ok=True)
    snapshot_download(
        repo_id=HYMT2_MODEL,
        revision=HYMT2_MODEL_REVISION,
        local_dir=str(destination),
    )
    verify_gpu_model(destination)
    print(f"HY-MT2 GPU model ready at pinned revision {HYMT2_MODEL_REVISION}: {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
