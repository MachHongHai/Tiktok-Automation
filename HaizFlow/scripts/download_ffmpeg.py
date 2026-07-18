"""Install the pinned Windows FFmpeg runtime and its compliance sources."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import urllib.request
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BIN_DIR = ROOT / "runtime" / "bin"
COMPLIANCE_DIR = ROOT / "runtime" / "compliance" / "ffmpeg"
MANIFEST_PATH = ROOT / "runtime" / "ffmpeg-manifest.json"

VERSION = "8.1.2"
VARIANT = "essentials_build"
SOURCE_COMMIT = "38b88335f9"
BINARY_NAME = f"ffmpeg-{VERSION}-{VARIANT}.zip"
SOURCE_NAME = f"ffmpeg-{VERSION}.tar.xz"
SIGNATURE_NAME = f"{SOURCE_NAME}.asc"
BINARY_URL = f"https://github.com/GyanD/codexffmpeg/releases/download/{VERSION}/{BINARY_NAME}"
SOURCE_URL = f"https://ffmpeg.org/releases/{SOURCE_NAME}"
SIGNATURE_URL = f"{SOURCE_URL}.asc"
BINARY_SHA256 = "db580001caa24ac104c8cb856cd113a87b0a443f7bdf47d8c12b1d740584a2ec"
SOURCE_SHA256 = "464beb5e7bf0c311e68b45ae2f04e9cc2af88851abb4082231742a74d97b524c"
SIGNATURE_SHA256 = "0a0963fccd70597838073f3e31b20f4a4d8cc2b5e577472c9a5a1f22624246f8"

REQUIRED_CONFIGURATION = (
    "--enable-gpl",
    "--enable-libass",
    "--enable-librubberband",
    "--enable-libx264",
)
REQUIRED_FILTERS = ("adelay", "amix", "ass", "atempo")
REQUIRED_ENCODERS = ("libx264",)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        while chunk := file.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _verify(path: Path, expected_sha256: str) -> None:
    actual = _sha256(path)
    if actual != expected_sha256:
        raise RuntimeError(f"Checksum mismatch for {path.name}: expected {expected_sha256}, got {actual}")


def _download(url: str, destination: Path, expected_sha256: str) -> Path:
    request = urllib.request.Request(url, headers={"User-Agent": "HaizFlow-build/1"})
    print(f"Downloading {url}", flush=True)
    with urllib.request.urlopen(request, timeout=120) as response, destination.open("wb") as output:
        shutil.copyfileobj(response, output, length=1024 * 1024)
    _verify(destination, expected_sha256)
    return destination


def _input_or_download(
    supplied: Path | None,
    *,
    url: str,
    filename: str,
    expected_sha256: str,
    work_directory: Path,
) -> Path:
    if supplied is not None:
        path = supplied.expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(path)
        _verify(path, expected_sha256)
        return path
    return _download(url, work_directory / filename, expected_sha256)


def _extract_safely(archive: Path, destination: Path) -> Path:
    destination = destination.resolve()
    with zipfile.ZipFile(archive) as package:
        for member in package.infolist():
            target = (destination / member.filename).resolve()
            if target != destination and destination not in target.parents:
                raise RuntimeError(f"Unsafe ZIP member: {member.filename}")
        package.extractall(destination)
    roots = [path for path in destination.iterdir() if path.is_dir()]
    if len(roots) != 1:
        raise RuntimeError("FFmpeg archive must contain exactly one root directory")
    return roots[0]


def _run(executable: Path, *arguments: str) -> str:
    completed = subprocess.run(
        [str(executable), *arguments],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    output = f"{completed.stdout}\n{completed.stderr}"
    if completed.returncode != 0:
        raise RuntimeError(f"{executable.name} {' '.join(arguments)} failed:\n{output[-2000:]}")
    return output


def _validate_runtime(ffmpeg: Path, ffprobe: Path) -> str:
    version_output = _run(ffmpeg, "-hide_banner", "-version")
    first_line = version_output.splitlines()[0]
    if f"ffmpeg version {VERSION}-essentials_build-www.gyan.dev" not in first_line:
        raise RuntimeError(f"Unexpected FFmpeg version: {first_line}")
    missing_configuration = [item for item in REQUIRED_CONFIGURATION if item not in version_output]
    if missing_configuration:
        raise RuntimeError(f"FFmpeg is missing required configuration: {missing_configuration}")

    filters = _run(ffmpeg, "-hide_banner", "-filters")
    missing_filters = [name for name in REQUIRED_FILTERS if name not in filters]
    if missing_filters:
        raise RuntimeError(f"FFmpeg is missing required filters: {missing_filters}")

    encoders = _run(ffmpeg, "-hide_banner", "-encoders")
    missing_encoders = [name for name in REQUIRED_ENCODERS if name not in encoders]
    if missing_encoders:
        raise RuntimeError(f"FFmpeg is missing required encoders: {missing_encoders}")

    probe_output = _run(ffprobe, "-hide_banner", "-version")
    if f"ffprobe version {VERSION}-essentials_build-www.gyan.dev" not in probe_output.splitlines()[0]:
        raise RuntimeError("ffprobe does not match the pinned FFmpeg package")
    return first_line


def _atomic_copy(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f"{destination.name}.new")
    shutil.copy2(source, temporary)
    os.replace(temporary, destination)


def install(
    *,
    archive: Path | None,
    source_archive: Path | None,
    source_signature: Path | None,
) -> None:
    (ROOT / "build").mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="ffmpeg-install-", dir=ROOT / "build") as temporary:
        work = Path(temporary)
        binary_package = _input_or_download(
            archive,
            url=BINARY_URL,
            filename=BINARY_NAME,
            expected_sha256=BINARY_SHA256,
            work_directory=work,
        )
        source_package = _input_or_download(
            source_archive,
            url=SOURCE_URL,
            filename=SOURCE_NAME,
            expected_sha256=SOURCE_SHA256,
            work_directory=work,
        )
        signature = _input_or_download(
            source_signature,
            url=SIGNATURE_URL,
            filename=SIGNATURE_NAME,
            expected_sha256=SIGNATURE_SHA256,
            work_directory=work,
        )

        package_root = _extract_safely(binary_package, work / "extracted")
        ffmpeg = package_root / "bin" / "ffmpeg.exe"
        ffprobe = package_root / "bin" / "ffprobe.exe"
        license_file = package_root / "LICENSE"
        readme_file = package_root / "README.txt"
        for required in (ffmpeg, ffprobe, license_file, readme_file):
            if not required.is_file():
                raise RuntimeError(f"Required package file is missing: {required}")

        version_line = _validate_runtime(ffmpeg, ffprobe)
        _atomic_copy(ffmpeg, BIN_DIR / "ffmpeg.exe")
        _atomic_copy(ffprobe, BIN_DIR / "ffprobe.exe")
        _atomic_copy(license_file, COMPLIANCE_DIR / "LICENSE.txt")
        _atomic_copy(readme_file, COMPLIANCE_DIR / "README.txt")
        _atomic_copy(source_package, COMPLIANCE_DIR / SOURCE_NAME)
        _atomic_copy(signature, COMPLIANCE_DIR / SIGNATURE_NAME)

    manifest = {
        "version": VERSION,
        "variant": VARIANT,
        "architecture": "windows-x64",
        "license": "GPL-3.0-or-later configured build",
        "binary_url": BINARY_URL,
        "binary_sha256": BINARY_SHA256,
        "source_url": SOURCE_URL,
        "source_sha256": SOURCE_SHA256,
        "source_signature_url": SIGNATURE_URL,
        "source_signature_sha256": SIGNATURE_SHA256,
        "source_commit": SOURCE_COMMIT,
        "ffmpeg_sha256": _sha256(BIN_DIR / "ffmpeg.exe"),
        "ffprobe_sha256": _sha256(BIN_DIR / "ffprobe.exe"),
        "version_line": version_line,
        "required_configuration": list(REQUIRED_CONFIGURATION),
        "required_filters": list(REQUIRED_FILTERS),
        "required_encoders": list(REQUIRED_ENCODERS),
    }
    temporary_manifest = MANIFEST_PATH.with_suffix(".json.new")
    temporary_manifest.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary_manifest, MANIFEST_PATH)
    print(f"Installed {version_line}", flush=True)
    print(f"Runtime manifest: {MANIFEST_PATH}", flush=True)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--source-archive", type=Path)
    parser.add_argument("--source-signature", type=Path)
    args = parser.parse_args(argv)
    install(
        archive=args.archive,
        source_archive=args.source_archive,
        source_signature=args.source_signature,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
