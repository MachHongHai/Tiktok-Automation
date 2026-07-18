"""Pinned HY-MT2 model revisions and local integrity verification."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path


HYMT2_GPU_REPO = "tencent/Hy-MT2-1.8B"
HYMT2_GPU_REVISION = "9a341cd1b679d3efd23b46e847b01745a71ed792"
HYMT2_CPU_REPO = "tencent/Hy-MT2-1.8B-GGUF"
HYMT2_CPU_REVISION = "1cd5208700acedef4ef93019b6cfc148b8522d45"
HYMT2_CPU_FILE = "Hy-MT2-1.8B-Q4_K_M.gguf"
HYMT2_CPU_SHA256 = "dc5f44fcf1fa496ee7ad725982c0c8c553a4de00259b53af84c4b89fb0c06699"
WHISPER_REPO = "Systran/faster-whisper-small"
WHISPER_REVISION = "536b0662742c02347bc0e980a01041f333bce120"

WHISPER_FILES = {
    "config.json": (2370, "b55496ac7940a7ae47d2c01eab40edfd8701feec1229d9cce3b40014383fb828"),
    "model.bin": (483546902, "3e305921506d8872816023e4c273e75d2419fb89b24da97b4fe7bce14170d671"),
    "tokenizer.json": (2203239, "fb7b63191e9bb045082c79fd742a3106a12c99513ab30df4a0d47fa6cb6fd0ab"),
    "vocabulary.txt": (459861, "34ce3fe1c5041027b3f8d42912270993f986dbc4bb34cf27f951e34a1e453913"),
}

HYMT2_GPU_FILES = {
    "chat_template.jinja": (654, "b7491ec0e9c869dfce20f2176758099bf248d979dd05530ede99deb21698acee"),
    "config.json": (1348, "da40c514cc74a5748a2e591b1b95fca4b7e94de05349abe4ea4164a82641de1a"),
    "generation_config.json": (221, "0e28667f1cb4c7b880b9223b2d87978f88e79ed7ae037de1021f826c18d4ed6f"),
    "model.safetensors": (4077072784, "29e9117a44c79f81857613601968ff482d8a23c2d6736a1710bba9e5ca4762e5"),
    "special_tokens_map.json": (488, "bb9f59990034dae326581b9c62471523975417869f78a244b7ae2ce8cbb085eb"),
    "tokenizer.json": (9527287, "b475bbef1b0b2fd57dcb865332b546475bd1ede2deb3bb91bafd0c047a8a530a"),
    "tokenizer_config.json": (165815, "53bd8581b601a8ee9caefeb988207de50b3fc0b733295bdf5ad68dec4cc0b07c"),
}

MARKER_NAME = ".haizflow-model-integrity.json"
MARKER_VERSION = 3
QUICK_SAMPLE_BYTES = 64 * 1024


class ModelIntegrityError(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        while chunk := file.read(16 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _manifest_id(kind: str, revision: str, files: dict[str, tuple[int, str]]) -> str:
    payload = json.dumps(
        {"kind": kind, "revision": revision, "files": files},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _quick_fingerprint(path: Path) -> str:
    """Detect same-size rewrites without hashing multi-gigabyte weights again."""
    size = path.stat().st_size
    offsets = {0, max(0, size // 2 - QUICK_SAMPLE_BYTES // 2), max(0, size - QUICK_SAMPLE_BYTES)}
    digest = hashlib.blake2b(digest_size=16)
    with path.open("rb") as file:
        for offset in sorted(offsets):
            file.seek(offset)
            digest.update(offset.to_bytes(8, "little"))
            digest.update(file.read(QUICK_SAMPLE_BYTES))
    return digest.hexdigest()


def _state(path: Path) -> dict[str, int | str]:
    stat = path.stat()
    return {
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
        "ctime_ns": stat.st_ctime_ns,
        "sample": _quick_fingerprint(path),
    }


def _marker_is_current(marker_path: Path, manifest_id: str, files: dict[str, Path]) -> bool:
    try:
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
        if marker.get("version") != MARKER_VERSION or marker.get("manifest_id") != manifest_id:
            return False
        recorded = marker.get("files") or {}
        return all(recorded.get(name) == _state(path) for name, path in files.items())
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return False


def _write_marker(marker_path: Path, manifest_id: str, files: dict[str, Path]) -> None:
    payload = {
        "version": MARKER_VERSION,
        "manifest_id": manifest_id,
        "files": {name: _state(path) for name, path in files.items()},
    }
    temporary = marker_path.with_name(f"{marker_path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, marker_path)
    except OSError:
        temporary.unlink(missing_ok=True)


def _verify(
    root: Path,
    *,
    kind: str,
    revision: str,
    expected: dict[str, tuple[int, str]],
) -> Path:
    root = root.expanduser().resolve()
    files = {name: root / name for name in expected}
    for name, path in files.items():
        expected_size, _expected_hash = expected[name]
        if not path.is_file() or path.stat().st_size != expected_size:
            raise ModelIntegrityError(f"{kind} file is missing or has the wrong size: {path}")

    manifest_id = _manifest_id(kind, revision, expected)
    marker_path = root / MARKER_NAME
    if _marker_is_current(marker_path, manifest_id, files):
        return root

    for name, path in files.items():
        _expected_size, expected_hash = expected[name]
        actual_hash = _sha256(path)
        if actual_hash != expected_hash:
            raise ModelIntegrityError(
                f"{kind} checksum mismatch for {name}: expected {expected_hash}, got {actual_hash}"
            )
    _write_marker(marker_path, manifest_id, files)
    return root


def verify_cpu_model(model_path: Path) -> Path:
    model_path = model_path.expanduser().resolve()
    _verify(
        model_path.parent,
        kind="cpu",
        revision=HYMT2_CPU_REVISION,
        expected={HYMT2_CPU_FILE: (1133080448, HYMT2_CPU_SHA256)},
    )
    return model_path


def verify_gpu_model(model_directory: Path) -> Path:
    return _verify(
        model_directory,
        kind="gpu",
        revision=HYMT2_GPU_REVISION,
        expected=HYMT2_GPU_FILES,
    )


def verify_whisper_model(model_directory: Path) -> Path:
    return _verify(
        model_directory,
        kind="Whisper small",
        revision=WHISPER_REVISION,
        expected=WHISPER_FILES,
    )
