import argparse
import hashlib
import importlib.metadata
import json
import os
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

from packaging.requirements import Requirement


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        while chunk := file.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def expected_packages() -> dict[str, str]:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    expected = {}
    for value in project.get("dependencies", []):
        requirement = Requirement(value)
        if requirement.marker and not requirement.marker.evaluate():
            continue
        exact_versions = [item.version for item in requirement.specifier if item.operator == "=="]
        if len(exact_versions) != 1:
            raise RuntimeError(f"Runtime dependency must have one exact version: {value}")
        expected[requirement.name] = exact_versions[0]
    return expected


def check(condition: bool, message: str, failures: list[str]) -> None:
    marker = "OK" if condition else "FAIL"
    print(f"[{marker}] {message}")
    if not condition:
        failures.append(message)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the HaizFlow source/build runtime.")
    parser.add_argument("--for-build", action="store_true")
    args = parser.parse_args()
    failures: list[str] = []

    lock_check = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "verify-dependency-lock.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )
    check(
        lock_check.returncode == 0,
        lock_check.stdout.strip() or lock_check.stderr.strip() or "Hashed dependency lock",
        failures,
    )

    check((3, 11) <= sys.version_info[:2] <= (3, 13), f"Python {sys.version.split()[0]}", failures)
    expected_venv = (ROOT / ".venv").resolve()
    check(Path(sys.prefix).resolve() == expected_venv, f"Project virtual environment: {expected_venv}", failures)

    for distribution, expected in expected_packages().items():
        try:
            actual = importlib.metadata.version(distribution)
        except importlib.metadata.PackageNotFoundError:
            actual = "missing"
        check(actual == expected or actual.startswith(expected + "+"), f"{distribution} {actual} (expected {expected})", failures)

    if str(SRC) not in sys.path:
        sys.path.insert(0, str(SRC))
    from haizflow.config import HYMT2_CPU_MODEL_REVISION, HYMT2_MODEL_REVISION, WHISPER_MODEL_REVISION
    from haizflow.core.model_integrity import HYMT2_CPU_REVISION, HYMT2_GPU_REVISION, WHISPER_REVISION

    check(
        HYMT2_MODEL_REVISION == HYMT2_GPU_REVISION and len(HYMT2_GPU_REVISION) == 40,
        f"Pinned HY-MT2 GPU revision: {HYMT2_GPU_REVISION}",
        failures,
    )
    check(
        HYMT2_CPU_MODEL_REVISION == HYMT2_CPU_REVISION and len(HYMT2_CPU_REVISION) == 40,
        f"Pinned HY-MT2 CPU revision: {HYMT2_CPU_REVISION}",
        failures,
    )
    check(
        WHISPER_MODEL_REVISION == WHISPER_REVISION and len(WHISPER_REVISION) == 40,
        f"Pinned Whisper revision: {WHISPER_REVISION}",
        failures,
    )
    try:
        from PySide6 import QtCore, QtMultimedia, QtQml, QtQuick  # noqa: F401

        check(True, "Qt Core/QML/Quick/Multimedia imports", failures)
    except Exception as exc:
        check(False, f"Qt imports: {exc}", failures)

    try:
        import torch

        torch_build = "CUDA-capable" if torch.version.cuda else "CPU-only"
        check(bool(torch.version.cuda), f"Unified Torch build: {torch_build}", failures)
        print(f"[INFO] CUDA available: {torch.cuda.is_available()}")
        if torch.cuda.is_available():
            print(f"[INFO] CUDA device: {torch.cuda.get_device_name(0)}")
            tensor = torch.ones((16, 16), device="cuda", dtype=torch.float16)
            result = tensor @ tensor
            torch.cuda.synchronize()
            check(float(result.sum().item()) > 0, "CUDA allocation and FP16 compute", failures)
            print(f"[INFO] CUDA compute capability: {torch.cuda.get_device_capability(0)}")
            print(f"[INFO] CUDA BF16 supported: {torch.cuda.is_bf16_supported()}")
            del tensor, result
            torch.cuda.empty_cache()
    except Exception as exc:
        check(False, f"Torch import: {exc}", failures)

    try:
        import torchcodec  # noqa: F401

        print("[OK] Optional TorchCodec native decoder")
    except Exception:
        print(
            "[WARN] Optional TorchCodec decoder is unavailable because the bundled FFmpeg is a static build. "
            "The pipeline supplies preloaded waveforms to WhisperX and does not depend on this decoder."
        )

    from haizflow.config import HF_HOME, MODELS_DIR, RUNTIME_DATA_DIR, TMP_DIR, TORCH_HOME
    from haizflow.core.runtime_probe import probe_runtime

    check(Path(RUNTIME_DATA_DIR).is_absolute(), f"Runtime data: {RUNTIME_DATA_DIR}", failures)
    check(Path(HF_HOME).is_absolute(), f"Hugging Face cache: {HF_HOME}", failures)
    check(Path(TORCH_HOME).is_absolute(), f"Torch cache: {TORCH_HOME}", failures)
    check(Path(MODELS_DIR).is_absolute(), f"Installed models: {MODELS_DIR}", failures)
    for directory in (RUNTIME_DATA_DIR, MODELS_DIR, HF_HOME, TORCH_HOME, TMP_DIR):
        path = Path(directory)
        path.mkdir(parents=True, exist_ok=True)
        probe_path = path / f".runtime-write-{os.getpid()}"
        try:
            probe_path.write_text("ok", encoding="utf-8")
            probe_path.unlink()
            writable = True
        except OSError:
            writable = False
        check(writable, f"Writable runtime directory: {path}", failures)
    free_gib = shutil.disk_usage(RUNTIME_DATA_DIR).free / (1024 ** 3)
    check(free_gib >= 2, f"Runtime disk has {free_gib:.1f} GB free", failures)

    ffmpeg_manifest_path = ROOT / "runtime" / "ffmpeg-manifest.json"
    try:
        ffmpeg_manifest = json.loads(ffmpeg_manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        ffmpeg_manifest = {}
        check(False, f"FFmpeg runtime manifest: {exc}", failures)
    check(ffmpeg_manifest.get("version") == "8.1.2", "Pinned FFmpeg 8.1.2 manifest", failures)

    for executable in ("ffmpeg.exe", "ffprobe.exe"):
        path = ROOT / "runtime" / "bin" / executable
        check(path.is_file(), f"Bundled media tool: {path}", failures)
        if path.is_file():
            expected_hash = ffmpeg_manifest.get(executable.removesuffix(".exe") + "_sha256")
            check(bool(expected_hash) and sha256(path) == expected_hash, f"Pinned checksum: {path.name}", failures)
            media_probe = subprocess.run(
                [str(path), "-version"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=15,
                check=False,
            )
            version_matches = "8.1.2-essentials_build-www.gyan.dev" in media_probe.stdout
            check(media_probe.returncode == 0 and version_matches, f"Native media tool starts: {path.name}", failures)

    compliance_directory = ROOT / "runtime" / "compliance" / "ffmpeg"
    for filename, hash_key in (
        ("ffmpeg-8.1.2.tar.xz", "source_sha256"),
        ("ffmpeg-8.1.2.tar.xz.asc", "source_signature_sha256"),
    ):
        path = compliance_directory / filename
        expected_hash = ffmpeg_manifest.get(hash_key)
        check(path.is_file() and bool(expected_hash) and sha256(path) == expected_hash, f"FFmpeg compliance file: {filename}", failures)

    cpu_probe = probe_runtime("cpu")
    check(cpu_probe.ok, f"Isolated CPU model runtime: {cpu_probe.message}", failures)
    if "torch" in locals() and torch.cuda.is_available():
        gpu_probe = probe_runtime("gpu")
        check(gpu_probe.ok, f"Isolated GPU model runtime: {gpu_probe.message}", failures)

    pip_check = subprocess.run(
        [sys.executable, "-m", "pip", "check"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    check(pip_check.returncode == 0, pip_check.stdout.strip() or pip_check.stderr.strip() or "pip check", failures)

    if args.for_build:
        check((ROOT / "src" / "haizflow" / "desktop" / "qml" / "Main.qml").is_file(), "QML source tree", failures)
        check(importlib.metadata.version("pyinstaller") == "6.21.0", "PyInstaller 6.21.0", failures)

    if failures:
        print(f"Runtime verification failed with {len(failures)} issue(s).")
        return 1
    print("Runtime verification passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
