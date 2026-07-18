"""Acceptance checks executed by the frozen release artifact itself."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

from haizflow.core.paths import bundle_root, project_root


def _check(condition: bool, message: str, failures: list[str], details: list[str]) -> None:
    details.append(message)
    if not condition:
        failures.append(message)


def _run_native_tool(path: Path) -> bool:
    try:
        completed = subprocess.run(
            [str(path), "-version"],
            capture_output=True,
            timeout=20,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return completed.returncode == 0


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        while chunk := file.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def run_release_smoke(
    *, require_cpu_model: bool, require_gpu_model: bool, require_whisper_model: bool = False
) -> dict[str, object]:
    failures: list[str] = []
    details: list[str] = []
    bundle = bundle_root()
    artifact = project_root()

    _check(bool(getattr(sys, "frozen", False)), "Running from a frozen executable", failures, details)
    _check((bundle / "haizflow" / "desktop" / "qml" / "Main.qml").is_file(), "QML bundle", failures, details)

    for executable in ("ffmpeg.exe", "ffprobe.exe"):
        path = bundle / "bin" / executable
        _check(path.is_file(), f"Bundled {executable}", failures, details)
        if path.is_file():
            _check(_run_native_tool(path), f"Executable {executable}", failures, details)

    ffmpeg_manifest_path = artifact / "FFMPEG-MANIFEST.json"
    try:
        ffmpeg_manifest = json.loads(ffmpeg_manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        ffmpeg_manifest = {}
        failures.append(f"FFmpeg manifest failed: {type(exc).__name__}: {exc}")
    _check(ffmpeg_manifest.get("version") == "8.1.2", "Pinned FFmpeg 8.1.2", failures, details)
    for executable in ("ffmpeg.exe", "ffprobe.exe"):
        path = bundle / "bin" / executable
        expected = ffmpeg_manifest.get(executable.removesuffix(".exe") + "_sha256")
        _check(path.is_file() and bool(expected) and _sha256(path) == expected, f"Checksum {executable}", failures, details)
    for filename, hash_key in (
        ("ffmpeg-8.1.2.tar.xz", "source_sha256"),
        ("ffmpeg-8.1.2.tar.xz.asc", "source_signature_sha256"),
    ):
        path = artifact / "sources" / "ffmpeg" / filename
        expected = ffmpeg_manifest.get(hash_key)
        _check(path.is_file() and bool(expected) and _sha256(path) == expected, f"FFmpeg source: {filename}", failures, details)

    for path, label in (
        (artifact / "LICENSE.txt", "Application license"),
        (artifact / "NOTICE.txt", "Application notice"),
        (artifact / "THIRD_PARTY_NOTICES.md", "Third-party notices"),
        (artifact / "licenses", "Third-party license directory"),
        (artifact / "BUILD-INFO.json", "Build metadata"),
        (artifact / "SHA256SUMS.txt", "Artifact checksum manifest"),
        (artifact / "sources" / "ffmpeg" / "LICENSE.txt", "FFmpeg package license"),
        (artifact / "sources" / "ffmpeg" / "README.txt", "FFmpeg package build information"),
    ):
        _check(path.exists(), label, failures, details)

    try:
        from PySide6 import QtCore, QtMultimedia, QtQml, QtQuick  # noqa: F401

        details.append("Qt Core/QML/Quick/Multimedia imports")
    except Exception as exc:
        failures.append(f"Qt runtime import failed: {type(exc).__name__}: {exc}")

    if require_cpu_model:
        from haizflow.config import HYMT2_CPU_MODEL_FILE
        from haizflow.core.model_integrity import verify_cpu_model

        cpu_model = bundle / "models" / "hymt2-gguf" / HYMT2_CPU_MODEL_FILE
        try:
            verify_cpu_model(cpu_model)
            cpu_model_valid = True
        except Exception as exc:
            cpu_model_valid = False
            failures.append(f"Bundled HY-MT2 CPU model integrity failed: {type(exc).__name__}: {exc}")
        _check(cpu_model_valid, "Bundled pinned HY-MT2 CPU model", failures, details)

    if require_gpu_model:
        from haizflow.core.model_integrity import verify_gpu_model

        gpu_model = bundle / "models" / "hymt2-transformers"
        try:
            verify_gpu_model(gpu_model)
            gpu_model_valid = True
        except Exception as exc:
            gpu_model_valid = False
            failures.append(f"Bundled HY-MT2 GPU model integrity failed: {type(exc).__name__}: {exc}")
        _check(gpu_model_valid, "Bundled pinned HY-MT2 GPU model", failures, details)

    if require_whisper_model:
        from haizflow.core.model_integrity import verify_whisper_model

        whisper_model = bundle / "models" / "whisper" / "small"
        try:
            verify_whisper_model(whisper_model)
            whisper_model_valid = True
        except Exception as exc:
            whisper_model_valid = False
            failures.append(f"Bundled Whisper model integrity failed: {type(exc).__name__}: {exc}")
        _check(whisper_model_valid, "Bundled pinned Whisper model", failures, details)

    return {
        "event": "release_smoke",
        "ok": not failures,
        "failures": failures,
        "details": details,
        "artifact": str(artifact),
        "bundle": str(bundle),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--require-cpu-model", action="store_true")
    parser.add_argument("--require-gpu-model", action="store_true")
    parser.add_argument("--require-whisper-model", action="store_true")
    args = parser.parse_args(argv)
    result = run_release_smoke(
        require_cpu_model=args.require_cpu_model,
        require_gpu_model=args.require_gpu_model,
        require_whisper_model=args.require_whisper_model,
    )
    if sys.stdout is not None:
        print(json.dumps(result, ensure_ascii=True), flush=True)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
