"""Download the official HY-MT2 Q4 model into the configured offline data directory."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from haizflow.config import (  # noqa: E402
    HYMT2_CPU_MODEL_FILE,
    HYMT2_CPU_MODEL_REPO,
    HYMT2_CPU_MODEL_REVISION,
    MODELS_DIR,
)
from haizflow.core.model_integrity import verify_cpu_model  # noqa: E402
from huggingface_hub import hf_hub_download  # noqa: E402


def main() -> int:
    destination = Path(MODELS_DIR) / "hymt2-gguf"
    destination.mkdir(parents=True, exist_ok=True)
    model_path = hf_hub_download(
        repo_id=HYMT2_CPU_MODEL_REPO,
        filename=HYMT2_CPU_MODEL_FILE,
        revision=HYMT2_CPU_MODEL_REVISION,
        local_dir=str(destination),
    )
    verify_cpu_model(Path(model_path))
    print(f"HY-MT2 CPU model ready at pinned revision {HYMT2_CPU_MODEL_REVISION}: {model_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
