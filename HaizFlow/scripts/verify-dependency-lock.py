"""Validate the hashed Windows/Python 3.13 release dependency lock."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import platform
import re
import sys
import tomllib
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
from packaging.version import Version


ROOT = Path(__file__).resolve().parents[1]
LOCK_PATH = ROOT / "requirements-lock-py313-win64.txt"
MANIFEST_PATH = ROOT / "dependency-lock-manifest.json"
INPUT_PATHS = (ROOT / "pyproject.toml", ROOT / "requirements-build.in")
HASH_PATTERN = re.compile(r"--hash=sha256:([0-9a-f]{64})(?:\s|$)")
REQUIRED_INDEX_DIRECTIVES = (
    "--index-url https://pypi.org/simple",
    "--extra-index-url https://download.pytorch.org/whl/cu128",
    "--extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        while chunk := file.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _logical_requirements(path: Path) -> list[str]:
    logical: list[str] = []
    current = ""
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if current:
            current += " " + stripped
        elif raw_line[:1].isspace():
            continue
        else:
            current = stripped
        if current.endswith("\\"):
            current = current[:-1].rstrip()
            continue
        if current.startswith("--"):
            current = ""
            continue
        logical.append(current)
        current = ""
    if current:
        logical.append(current)
    return logical


def _locked_requirements() -> dict[str, tuple[Requirement, str]]:
    locked: dict[str, tuple[Requirement, str]] = {}
    for logical in _logical_requirements(LOCK_PATH):
        requirement_text = logical.split(" --hash=", 1)[0].strip()
        requirement = Requirement(requirement_text)
        if requirement.marker and not requirement.marker.evaluate():
            continue
        exact_versions = [item.version for item in requirement.specifier if item.operator == "=="]
        if len(exact_versions) != 1 or len(list(requirement.specifier)) != 1:
            raise RuntimeError(f"Lock entry is not exact: {requirement_text}")
        if not HASH_PATTERN.search(logical):
            raise RuntimeError(f"Lock entry has no SHA-256 hash: {requirement_text}")
        name = canonicalize_name(requirement.name)
        if name in locked:
            raise RuntimeError(f"Duplicate lock entry: {requirement.name}")
        locked[name] = (requirement, exact_versions[0])
    if not locked:
        raise RuntimeError("Dependency lock contains no installable requirements.")
    return locked


def _expected_direct_requirements() -> dict[str, Requirement]:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    values = list(project.get("dependencies", []))
    values.extend(
        line.strip()
        for line in (ROOT / "requirements-build.in").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    )
    expected = {}
    for value in values:
        requirement = Requirement(value)
        if requirement.marker and not requirement.marker.evaluate():
            continue
        expected[canonicalize_name(requirement.name)] = requirement
    return expected


def _manifest_payload() -> dict[str, object]:
    return {
        "schema_version": 1,
        "target": "windows-x86_64-python-3.13",
        "generator": "uv==0.11.19",
        "inputs": {path.name: _sha256(path) for path in INPUT_PATHS},
        "lock_file": LOCK_PATH.name,
        "lock_sha256": _sha256(LOCK_PATH),
    }


def _verify_platform() -> None:
    if sys.platform != "win32" or sys.version_info[:2] != (3, 13):
        raise RuntimeError("This release lock is valid only for Windows with Python 3.13.")
    if platform.machine().lower() not in {"amd64", "x86_64"}:
        raise RuntimeError("This release lock is valid only for Windows x64.")


def verify(*, write_manifest: bool, check_installed: bool) -> dict[str, object]:
    _verify_platform()
    if not LOCK_PATH.is_file():
        raise RuntimeError(f"Dependency lock is missing: {LOCK_PATH}")
    lock_lines = {line.strip() for line in LOCK_PATH.read_text(encoding="utf-8").splitlines()}
    missing_indexes = [item for item in REQUIRED_INDEX_DIRECTIVES if item not in lock_lines]
    if missing_indexes:
        raise RuntimeError(
            "Dependency lock is missing required package indexes: " + ", ".join(missing_indexes)
        )
    locked = _locked_requirements()
    expected = _expected_direct_requirements()
    missing = sorted(set(expected) - set(locked))
    if missing:
        raise RuntimeError(f"Direct dependencies are missing from the lock: {', '.join(missing)}")
    for name, requirement in expected.items():
        locked_version = locked[name][1]
        if Version(locked_version) not in requirement.specifier:
            raise RuntimeError(f"Locked {name}=={locked_version} does not satisfy {requirement.specifier}.")

    payload = _manifest_payload()
    if write_manifest:
        MANIFEST_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    else:
        try:
            saved_manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Dependency lock manifest is missing or unreadable: {MANIFEST_PATH}") from exc
        if saved_manifest != payload:
            raise RuntimeError("Dependency lock or its source inputs changed. Regenerate the lock.")

    if check_installed:
        mismatches = []
        for name, (_requirement, locked_version) in locked.items():
            try:
                installed_version = importlib.metadata.version(name)
            except importlib.metadata.PackageNotFoundError:
                mismatches.append(f"{name}: missing (locked {locked_version})")
                continue
            if Version(installed_version) != Version(locked_version):
                mismatches.append(f"{name}: {installed_version} (locked {locked_version})")
        if mismatches:
            raise RuntimeError("Installed environment differs from the dependency lock:\n" + "\n".join(mismatches))
    return {"locked_packages": len(locked), **payload}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write-manifest", action="store_true")
    parser.add_argument("--no-installed-check", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = verify(write_manifest=args.write_manifest, check_installed=not args.no_installed_check)
    except Exception as exc:
        print(f"Dependency lock verification failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
