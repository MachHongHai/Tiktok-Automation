"""Isolated native-runtime validation for model backends."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import subprocess
import sys
from dataclasses import asdict, dataclass, field

from haizflow.core.paths import is_frozen, project_root


@dataclass(frozen=True)
class RuntimeProbeResult:
    device: str
    ok: bool
    details: dict[str, object] = field(default_factory=dict)
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    @property
    def message(self) -> str:
        if self.ok:
            return f"{self.device.upper()} model runtime is ready."
        return "; ".join(self.errors) or f"{self.device.upper()} model runtime is unavailable."


def _distribution_version(name: str) -> str:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return "missing"


def run_runtime_probe(device: str) -> RuntimeProbeResult:
    """Exercise native libraries in this disposable process."""
    requested_device = "gpu" if device == "gpu" else "cpu"
    os.environ["HAIZFLOW_PROCESSING_DEVICE"] = requested_device
    os.environ.pop("HAIZFLOW_FORCE_CPU", None)

    # Importing config first pins every mutable cache and temp path before a
    # third-party package gets a chance to use the system drive.
    from haizflow import config  # noqa: F401

    details: dict[str, object] = {
        "python": sys.version.split()[0],
        "device": requested_device,
    }
    errors: list[str] = []
    warnings: list[str] = []

    try:
        import torch

        details.update(
            {
                "torch": str(torch.__version__),
                "torch_cuda_build": str(torch.version.cuda or "none"),
            }
        )
        cpu_tensor = torch.ones((8,), dtype=torch.float32)
        details["torch_cpu_sum"] = float(cpu_tensor.sum().item())
        if requested_device == "gpu":
            if not torch.version.cuda:
                errors.append("Installed Torch build does not include CUDA support.")
            elif not torch.cuda.is_available():
                errors.append("Torch cannot initialize an NVIDIA CUDA device or compatible driver.")
            else:
                cuda_tensor = torch.ones((16, 16), device="cuda", dtype=torch.float16)
                result = cuda_tensor @ cuda_tensor
                torch.cuda.synchronize()
                details.update(
                    {
                        "cuda_device": torch.cuda.get_device_name(0),
                        "cuda_compute_capability": ".".join(map(str, torch.cuda.get_device_capability(0))),
                        "cuda_bf16_supported": bool(
                            getattr(torch.cuda, "is_bf16_supported", lambda: False)()
                        ),
                        "cuda_test_sum": float(result.sum().item()),
                    }
                )
                del cuda_tensor, result
                torch.cuda.empty_cache()
    except Exception as exc:
        errors.append(f"Torch native runtime failed: {type(exc).__name__}: {exc}")

    try:
        import ctranslate2

        ct2_device = "cuda" if requested_device == "gpu" else "cpu"
        compute_types = sorted(ctranslate2.get_supported_compute_types(ct2_device))
        details["ctranslate2"] = _distribution_version("ctranslate2")
        details["ctranslate2_compute_types"] = compute_types
        required_compute = "float16" if requested_device == "gpu" else "int8"
        if required_compute not in compute_types:
            errors.append(f"CTranslate2 does not support {required_compute} on {ct2_device}.")
    except Exception as exc:
        errors.append(f"CTranslate2 native runtime failed: {type(exc).__name__}: {exc}")

    for module_name, distribution_name in (
        ("torchaudio", "torchaudio"),
        ("torchvision", "torchvision"),
        ("whisperx", "whisperx"),
    ):
        try:
            __import__(module_name)
            details[distribution_name] = _distribution_version(distribution_name)
        except Exception as exc:
            errors.append(f"{distribution_name} failed to import: {type(exc).__name__}: {exc}")

    backend_modules = (
        (("transformers", "transformers"), ("accelerate", "accelerate"))
        if requested_device == "gpu"
        else (("llama_cpp", "llama-cpp-python"),)
    )
    for module_name, distribution_name in backend_modules:
        try:
            __import__(module_name)
            details[distribution_name] = _distribution_version(distribution_name)
        except Exception as exc:
            errors.append(f"{distribution_name} failed to import: {type(exc).__name__}: {exc}")

    try:
        import torchcodec  # noqa: F401

        details["torchcodec"] = _distribution_version("torchcodec")
    except Exception as exc:
        warnings.append(f"Optional TorchCodec decoder is unavailable: {type(exc).__name__}: {exc}")

    return RuntimeProbeResult(
        device=requested_device,
        ok=not errors,
        details=details,
        errors=tuple(errors),
        warnings=tuple(warnings),
    )


def _probe_command(device: str) -> list[str]:
    if is_frozen():
        return [sys.executable, "--runtime-probe", device]
    return [sys.executable, "-m", "haizflow.core.runtime_probe", "--child", device]


def _native_exit_message(return_code: int) -> str:
    unsigned_code = int(return_code) & 0xFFFFFFFF
    classifications = {
        0xC0000005: "native access violation in Torch, CUDA, or another model dependency",
        0xC0000017: "insufficient virtual memory",
        0xC000001D: "CPU instruction not supported by this processor",
        0xC000007B: "32-bit/64-bit native DLL mismatch",
        0xC000012D: "Windows commit limit reached",
        0xC0000135: "required native DLL not found",
        0xC0000142: "native DLL initialization failed",
    }
    return classifications.get(unsigned_code, "runtime probe terminated unexpectedly")


def probe_runtime(device: str, timeout_seconds: int = 240) -> RuntimeProbeResult:
    """Validate a model runtime in a child process so native crashes stay isolated."""
    requested_device = "gpu" if device == "gpu" else "cpu"
    environment = os.environ.copy()
    environment["HAIZFLOW_PROCESSING_DEVICE"] = requested_device
    environment.pop("HAIZFLOW_FORCE_CPU", None)
    environment["PYTHONIOENCODING"] = "utf-8"
    environment["PYTHONUTF8"] = "1"
    if not is_frozen():
        source_path = str(project_root() / "src")
        environment["PYTHONPATH"] = source_path + os.pathsep + environment.get("PYTHONPATH", "")
    startupinfo = None
    creationflags = 0
    if os.name == "nt":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = getattr(subprocess, "SW_HIDE", 0)
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        completed = subprocess.run(
            _probe_command(requested_device),
            cwd=str(project_root()),
            env=environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
            check=False,
            startupinfo=startupinfo,
            creationflags=creationflags,
        )
    except subprocess.TimeoutExpired:
        return RuntimeProbeResult(
            device=requested_device,
            ok=False,
            errors=(f"Runtime validation timed out after {timeout_seconds} seconds.",),
        )
    except OSError as exc:
        return RuntimeProbeResult(
            device=requested_device,
            ok=False,
            errors=(f"Runtime validation could not start: {exc}",),
        )

    payload = None
    for line in reversed(completed.stdout.splitlines()):
        try:
            candidate = json.loads(line)
        except json.JSONDecodeError:
            continue
        if candidate.get("event") == "runtime_probe":
            payload = candidate
            break
    if payload is not None:
        return RuntimeProbeResult(
            device=str(payload.get("device") or requested_device),
            ok=bool(payload.get("ok")),
            details=dict(payload.get("details") or {}),
            errors=tuple(str(item) for item in payload.get("errors") or ()),
            warnings=tuple(str(item) for item in payload.get("warnings") or ()),
        )

    classification = _native_exit_message(completed.returncode)
    output = (completed.stderr or completed.stdout).strip()[-1600:]
    return RuntimeProbeResult(
        device=requested_device,
        ok=False,
        errors=(
            f"Runtime validation exited with code {completed.returncode} "
            f"(0x{(completed.returncode & 0xFFFFFFFF):08X}): {classification}. "
            f"{output or 'No diagnostic output was produced.'}",
        ),
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--child", choices=("cpu", "gpu"), required=True)
    args = parser.parse_args(argv)
    result = run_runtime_probe(args.child)
    print(json.dumps({"event": "runtime_probe", **asdict(result)}, ensure_ascii=True), flush=True)
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
