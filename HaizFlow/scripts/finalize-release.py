"""Create release metadata and a SHA-256 manifest for a frozen artifact."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tomllib
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"


def _git_value(*arguments: str) -> str:
    try:
        completed = subprocess.run(
            ["git", *arguments],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    return completed.stdout.strip() if completed.returncode == 0 else "unknown"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        while chunk := file.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def finalize(artifact_directory: Path, *, cpu_model: bool, gpu_model: bool, whisper_model: bool) -> None:
    artifact = artifact_directory.resolve()
    executable = artifact / "HaizFlow.exe"
    if not executable.is_file():
        raise RuntimeError(f"Frozen executable is missing: {executable}")

    if str(SRC) not in sys.path:
        sys.path.insert(0, str(SRC))
    from haizflow.core.model_integrity import HYMT2_CPU_REVISION, HYMT2_GPU_REVISION, WHISPER_REVISION

    version = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    build_info = {
        "application": "HaizFlow",
        "version": version,
        "built_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "git_commit": _git_value("rev-parse", "HEAD"),
        "git_branch": _git_value("branch", "--show-current"),
        "git_dirty": bool(_git_value("status", "--porcelain")),
        "python": sys.version.split()[0],
        "bundled_cpu_model": cpu_model,
        "bundled_gpu_model": gpu_model,
        "bundled_whisper_model": whisper_model,
        "hymt2_cpu_revision": HYMT2_CPU_REVISION,
        "hymt2_gpu_revision": HYMT2_GPU_REVISION,
        "whisper_revision": WHISPER_REVISION,
        "packaging": "PyInstaller onedir",
    }
    (artifact / "BUILD-INFO.json").write_text(
        json.dumps(build_info, ensure_ascii=True, indent=2) + "\n",
        encoding="utf-8",
    )

    manifest_path = artifact / "SHA256SUMS.txt"
    files = sorted(
        (path for path in artifact.rglob("*") if path.is_file() and path != manifest_path),
        key=lambda path: path.relative_to(artifact).as_posix().lower(),
    )
    lines = []
    for index, path in enumerate(files, start=1):
        relative = path.relative_to(artifact).as_posix()
        lines.append(f"{_sha256(path)} *{relative}")
        if index % 500 == 0:
            print(f"Hashed {index}/{len(files)} release files", flush=True)
    manifest_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Release metadata finalized: {len(files)} files", flush=True)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--cpu-model", action="store_true")
    parser.add_argument("--gpu-model", action="store_true")
    parser.add_argument("--whisper-model", action="store_true")
    args = parser.parse_args(argv)
    finalize(
        args.artifact,
        cpu_model=args.cpu_model,
        gpu_model=args.gpu_model,
        whisper_model=args.whisper_model,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
