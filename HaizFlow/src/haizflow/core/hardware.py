"""Hardware-aware runtime policy shared by speech, translation, and rendering."""

from __future__ import annotations

import ctypes
import json
import os
import subprocess
import threading
import time
from dataclasses import dataclass
from functools import lru_cache


_GIB = 1024 ** 3
_MIN_CPU_RAM_BYTES = 5 * _GIB
_MIN_GPU_SYSTEM_RAM_BYTES = 8 * _GIB
_MIN_GPU_VRAM_BYTES = 7 * _GIB
_MIN_GPU_FREE_VRAM_BYTES = 5 * _GIB
_FULL_GPU_VRAM_BYTES = 12 * _GIB
_DEVICE_PREFERENCES = {"cpu", "gpu"}
_WINDOWS_INFO_CACHE: dict = {}
_WINDOWS_INFO_REFRESHING = False
_WINDOWS_INFO_LOCK = threading.Lock()
_WINDOWS_INFO_TTL_SECONDS = 2.0


@dataclass(frozen=True)
class HardwareCapabilities:
    cuda_available: bool
    cuda_name: str
    total_vram_bytes: int
    free_vram_bytes: int
    total_ram_bytes: int
    logical_cpu_count: int
    ac_powered: bool | None
    battery_percent: int | None
    active_display_gpu_name: str = ""
    active_display_gpu_driver: str = ""
    active_display_gpu_resolution: str = ""
    detected_graphics: tuple[str, ...] = ()
    cpu_name: str = ""
    cpu_manufacturer: str = ""
    cpu_physical_cores: int = 0
    cpu_max_mhz: int = 0
    cuda_compute_capability: tuple[int, int] = (0, 0)
    cuda_bf16_supported: bool = False

    @property
    def gpu_supported(self) -> bool:
        if not self.cuda_available or self.total_vram_bytes < _MIN_GPU_VRAM_BYTES:
            return False
        if self.ac_powered is False:
            return False
        if self.free_vram_bytes and self.free_vram_bytes < _MIN_GPU_FREE_VRAM_BYTES:
            return False
        return not self.total_ram_bytes or self.total_ram_bytes >= _MIN_GPU_SYSTEM_RAM_BYTES

    @property
    def cpu_supported(self) -> bool:
        return self.total_ram_bytes == 0 or self.total_ram_bytes >= _MIN_CPU_RAM_BYTES


@dataclass(frozen=True)
class RuntimeProfile:
    key: str
    label: str
    requested_device: str
    cuda_available: bool
    cuda_name: str
    total_vram_bytes: int
    total_ram_bytes: int
    logical_cpu_count: int
    cpu_threads: int
    whisper_batch_size: int
    hymt2_backend: str
    warm_whisper_on_startup: bool
    warm_hymt2_on_startup: bool
    translation_idle_seconds: int
    hymt2_dtype: str = "float16"

    @property
    def total_ram_gib(self) -> float:
        return self.total_ram_bytes / _GIB if self.total_ram_bytes else 0.0

    @property
    def total_vram_gib(self) -> float:
        return self.total_vram_bytes / _GIB if self.total_vram_bytes else 0.0

    @property
    def is_cpu_only(self) -> bool:
        return not self.cuda_available

    @property
    def summary(self) -> str:
        if self.cuda_available:
            vram = f", {self.total_vram_gib:.0f} GB VRAM" if self.total_vram_bytes else ""
            return f"GPU acceleration - {self.cuda_name or 'CUDA'}{vram}"
        ram = f"{self.total_ram_gib:.0f} GB RAM" if self.total_ram_bytes else "RAM unknown"
        return f"CPU mode - {ram}, {self.cpu_threads} threads"


def _total_memory_bytes() -> int:
    if os.name == "nt":
        class MemoryStatusEx(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        status = MemoryStatusEx()
        status.dwLength = ctypes.sizeof(MemoryStatusEx)
        try:
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return int(status.ullTotalPhys)
        except (AttributeError, OSError):
            return 0
        return 0

    try:
        pages = os.sysconf("SC_PHYS_PAGES")
        page_size = os.sysconf("SC_PAGE_SIZE")
        return int(pages * page_size)
    except (AttributeError, OSError, ValueError):
        return 0


def _cuda_details() -> tuple[bool, str]:
    try:
        import torch

        if torch.cuda.is_available():
            return True, torch.cuda.get_device_name(0)
    except Exception:
        pass
    return False, ""


def _cuda_memory_bytes() -> int:
    try:
        import torch

        if torch.cuda.is_available():
            return int(torch.cuda.get_device_properties(0).total_memory)
    except Exception:
        pass
    return 0


def _cuda_free_memory_bytes() -> int:
    """Return free VRAM without allocating a model; zero means unavailable."""
    try:
        import torch

        if torch.cuda.is_available() and hasattr(torch.cuda, "mem_get_info"):
            free_bytes, _total_bytes = torch.cuda.mem_get_info(0)
            return int(free_bytes)
    except Exception:
        pass
    return 0


def _cuda_precision_details() -> tuple[tuple[int, int], bool]:
    """Return the active CUDA architecture and its safe HY-MT2 precision."""
    try:
        import torch

        if not torch.cuda.is_available():
            return (0, 0), False
        capability = tuple(int(value) for value in torch.cuda.get_device_capability(0))
        bf16_supported = bool(getattr(torch.cuda, "is_bf16_supported", lambda: False)())
        return capability, bf16_supported
    except Exception:
        return (0, 0), False


def _power_status() -> tuple[bool | None, int | None]:
    """Return AC status and battery percentage when Windows exposes them."""
    if os.name != "nt":
        return None, None

    class SystemPowerStatus(ctypes.Structure):
        _fields_ = [
            ("ACLineStatus", ctypes.c_ubyte),
            ("BatteryFlag", ctypes.c_ubyte),
            ("BatteryLifePercent", ctypes.c_ubyte),
            ("SystemStatusFlag", ctypes.c_ubyte),
            ("BatteryLifeTime", ctypes.c_uint32),
            ("BatteryFullLifeTime", ctypes.c_uint32),
        ]

    status = SystemPowerStatus()
    try:
        if not ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(status)):
            return None, None
    except (AttributeError, OSError):
        return None, None
    ac_powered = {0: False, 1: True}.get(int(status.ACLineStatus))
    battery_percent = None if status.BatteryLifePercent == 255 else int(status.BatteryLifePercent)
    return ac_powered, battery_percent


def _normalize_cim_items(value) -> list[dict]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        return [value]
    return []


def _read_windows_system_info() -> dict:
    """Read display and CPU metadata without using CUDA's static device list."""
    if os.name != "nt":
        return {}
    command = (
        "$video = Get-CimInstance Win32_VideoController | Select-Object "
        "Name,VideoProcessor,CurrentHorizontalResolution,CurrentVerticalResolution,"
        "CurrentBitsPerPixel,DriverVersion,Availability; "
        "$cpu = Get-CimInstance Win32_Processor | Select-Object "
        "Name,Manufacturer,NumberOfCores,NumberOfLogicalProcessors,MaxClockSpeed; "
        "[pscustomobject]@{video=$video;cpu=$cpu} | ConvertTo-Json -Depth 4 -Compress"
    )
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=8,
            check=False,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return {}
        payload = json.loads(result.stdout.lstrip("\ufeff").strip())
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
        return {}

    adapters = _normalize_cim_items(payload.get("video"))
    active = next(
        (
            adapter for adapter in adapters
            if int(adapter.get("CurrentHorizontalResolution") or 0) > 0
            and int(adapter.get("CurrentVerticalResolution") or 0) > 0
        ),
        None,
    )
    if active is None:
        active = next((adapter for adapter in adapters if int(adapter.get("Availability") or 0) == 3), None)
    cpu_items = _normalize_cim_items(payload.get("cpu"))
    cpu = cpu_items[0] if cpu_items else {}
    width = int((active or {}).get("CurrentHorizontalResolution") or 0)
    height = int((active or {}).get("CurrentVerticalResolution") or 0)
    return {
        "active_display_gpu_name": str((active or {}).get("Name") or ""),
        "active_display_gpu_driver": str((active or {}).get("DriverVersion") or ""),
        "active_display_gpu_resolution": f"{width} x {height}" if width and height else "",
        "detected_graphics": tuple(str(adapter.get("Name") or "") for adapter in adapters if adapter.get("Name")),
        "cpu_name": str(cpu.get("Name") or ""),
        "cpu_manufacturer": str(cpu.get("Manufacturer") or ""),
        "cpu_physical_cores": int(cpu.get("NumberOfCores") or 0),
        "cpu_max_mhz": int(cpu.get("MaxClockSpeed") or 0),
    }


def _windows_system_info() -> dict:
    """Return cached platform telemetry and refresh it off the UI thread."""
    global _WINDOWS_INFO_REFRESHING
    if os.name != "nt":
        return {}
    now = time.monotonic()
    with _WINDOWS_INFO_LOCK:
        cached_at = float(_WINDOWS_INFO_CACHE.get("timestamp", 0.0))
        stale = now - cached_at >= _WINDOWS_INFO_TTL_SECONDS
        if stale and not _WINDOWS_INFO_REFRESHING:
            _WINDOWS_INFO_REFRESHING = True

            def refresh():
                global _WINDOWS_INFO_REFRESHING
                details = _read_windows_system_info()
                with _WINDOWS_INFO_LOCK:
                    if details:
                        _WINDOWS_INFO_CACHE.clear()
                        _WINDOWS_INFO_CACHE.update(details)
                        _WINDOWS_INFO_CACHE["timestamp"] = time.monotonic()
                    _WINDOWS_INFO_REFRESHING = False

            threading.Thread(target=refresh, name="hardware-telemetry", daemon=True).start()
        return {key: value for key, value in _WINDOWS_INFO_CACHE.items() if key != "timestamp"}


def detect_hardware_capabilities() -> HardwareCapabilities:
    """Probe live hardware telemetry without changing the active runtime profile."""
    cuda_available, cuda_name = _cuda_details()
    cuda_compute_capability, cuda_bf16_supported = (
        _cuda_precision_details() if cuda_available else ((0, 0), False)
    )
    ac_powered, battery_percent = _power_status()
    system_info = _windows_system_info()
    return HardwareCapabilities(
        cuda_available=cuda_available,
        cuda_name=cuda_name,
        total_vram_bytes=_cuda_memory_bytes() if cuda_available else 0,
        free_vram_bytes=_cuda_free_memory_bytes() if cuda_available else 0,
        total_ram_bytes=_total_memory_bytes(),
        logical_cpu_count=max(1, os.cpu_count() or 1),
        ac_powered=ac_powered,
        battery_percent=battery_percent,
        active_display_gpu_name=system_info.get("active_display_gpu_name", ""),
        active_display_gpu_driver=system_info.get("active_display_gpu_driver", ""),
        active_display_gpu_resolution=system_info.get("active_display_gpu_resolution", ""),
        detected_graphics=tuple(system_info.get("detected_graphics", ())),
        cpu_name=system_info.get("cpu_name", ""),
        cpu_manufacturer=system_info.get("cpu_manufacturer", ""),
        cpu_physical_cores=int(system_info.get("cpu_physical_cores", 0)),
        cpu_max_mhz=int(system_info.get("cpu_max_mhz", 0)),
        cuda_compute_capability=cuda_compute_capability,
        cuda_bf16_supported=cuda_bf16_supported,
    )


def processing_device_preference() -> str:
    if os.getenv("HAIZFLOW_FORCE_CPU", "").strip().lower() in {"1", "true", "yes"}:
        return "cpu"
    preference = os.getenv("HAIZFLOW_PROCESSING_DEVICE", "cpu").strip().lower()
    return preference if preference in _DEVICE_PREFERENCES else "cpu"


@lru_cache(maxsize=1)
def hardware_capabilities() -> HardwareCapabilities:
    return detect_hardware_capabilities()


def recommended_processing_device(capabilities: HardwareCapabilities | None = None) -> str:
    """Choose the fastest safe device for the current live hardware state."""
    capabilities = capabilities or detect_hardware_capabilities()
    return "gpu" if capabilities.gpu_supported else "cpu"


def validate_processing_device(
    preference: str,
    capabilities: HardwareCapabilities | None = None,
) -> tuple[bool, str]:
    preference = preference if preference in _DEVICE_PREFERENCES else "cpu"
    capabilities = capabilities or detect_hardware_capabilities()
    if preference == "gpu":
        if not capabilities.cuda_available:
            return False, "CUDA-compatible NVIDIA GPU was not detected."
        if capabilities.ac_powered is False:
            return False, "GPU mode requires AC power for stable processing. Connect the charger and try again."
        if capabilities.total_vram_bytes < _MIN_GPU_VRAM_BYTES:
            available = capabilities.total_vram_bytes / _GIB
            return False, f"GPU mode requires at least 7 GB VRAM; detected {available:.1f} GB."
        if capabilities.free_vram_bytes and capabilities.free_vram_bytes < _MIN_GPU_FREE_VRAM_BYTES:
            available = capabilities.free_vram_bytes / _GIB
            return False, f"GPU mode requires at least 5 GB free VRAM; detected {available:.1f} GB free."
        if capabilities.total_ram_bytes and capabilities.total_ram_bytes < _MIN_GPU_SYSTEM_RAM_BYTES:
            available = capabilities.total_ram_bytes / _GIB
            return False, f"GPU mode requires at least 8 GB system RAM; detected {available:.1f} GB."
        return True, f"GPU ready: {capabilities.cuda_name}, {capabilities.total_vram_bytes / _GIB:.0f} GB VRAM."
    if preference == "cpu":
        if not capabilities.cpu_supported:
            available = capabilities.total_ram_bytes / _GIB
            return False, f"CPU mode requires approximately 6 GB RAM; detected {available:.1f} GB."
        ram = capabilities.total_ram_bytes / _GIB
        return True, f"CPU ready: {ram:.0f} GB RAM, {capabilities.logical_cpu_count} logical processors."
    if capabilities.cpu_supported:
        return True, f"CPU ready: {capabilities.total_ram_bytes / _GIB:.0f} GB RAM, {capabilities.logical_cpu_count} logical processors."
    return False, "This computer does not meet the minimum CPU or GPU memory requirement."


def configure_processing_device(preference: str) -> str:
    normalized = preference if preference in _DEVICE_PREFERENCES else "cpu"
    os.environ["HAIZFLOW_PROCESSING_DEVICE"] = normalized
    os.environ.pop("HAIZFLOW_FORCE_CPU", None)
    clear_runtime_profile_cache()
    return normalized


@lru_cache(maxsize=1)
def runtime_profile() -> RuntimeProfile:
    """Detect a conservative profile that remains usable on CPU-only PCs."""
    capabilities = hardware_capabilities()
    preference = processing_device_preference()
    use_cuda = capabilities.gpu_supported and preference == "gpu"
    total_ram = capabilities.total_ram_bytes
    logical_cpus = capabilities.logical_cpu_count

    if use_cuda:
        low_vram = capabilities.total_vram_bytes < _FULL_GPU_VRAM_BYTES
        return RuntimeProfile(
            key="cuda_low_memory" if low_vram else "cuda",
            label="GPU low memory" if low_vram else "GPU accelerated",
            requested_device=preference,
            cuda_available=True,
            cuda_name=capabilities.cuda_name,
            total_vram_bytes=capabilities.total_vram_bytes,
            total_ram_bytes=total_ram,
            logical_cpu_count=logical_cpus,
            cpu_threads=max(1, min(8, logical_cpus - 1 if logical_cpus > 2 else logical_cpus)),
            whisper_batch_size=8 if low_vram else 16,
            # CUDA keeps the official checkpoint. Precision is selected from
            # the active GPU architecture without changing model quality.
            hymt2_backend="transformers",
            warm_whisper_on_startup=True,
            warm_hymt2_on_startup=True,
            translation_idle_seconds=0,
            hymt2_dtype="bfloat16" if capabilities.cuda_bf16_supported else "float16",
        )

    total_gib = total_ram / _GIB if total_ram else 16
    # Windows reports usable physical RAM below the marketed capacity (for
    # example, a 16 GB PC is commonly reported as roughly 15 GiB).
    if total_gib >= 14:
        key = "cpu_balanced"
        label = "CPU balanced"
        batch_size = 4
        cpu_threads = max(1, min(8, logical_cpus - 1 if logical_cpus > 2 else logical_cpus))
        idle_seconds = 300
    elif total_gib >= 7:
        key = "cpu_low_memory"
        label = "CPU low memory"
        batch_size = 2
        cpu_threads = max(1, min(4, logical_cpus - 1 if logical_cpus > 2 else logical_cpus))
        idle_seconds = 90
    else:
        key = "cpu_minimum"
        label = "CPU minimum memory"
        batch_size = 1
        cpu_threads = max(1, min(2, logical_cpus))
        idle_seconds = 30

    return RuntimeProfile(
        key=key,
        label=label,
        requested_device=preference,
        cuda_available=False,
        cuda_name="",
        total_vram_bytes=capabilities.total_vram_bytes,
        total_ram_bytes=total_ram,
        logical_cpu_count=logical_cpus,
        cpu_threads=cpu_threads,
        whisper_batch_size=batch_size,
        hymt2_backend="llama_cpp",
        # Avoid competing with the desktop and OS on constrained RAM. The
        # model will still load on demand when the user starts a project.
        warm_whisper_on_startup=key == "cpu_balanced",
        warm_hymt2_on_startup=False,
        translation_idle_seconds=idle_seconds,
        hymt2_dtype="float32",
    )


def clear_runtime_profile_cache() -> None:
    """Test helper for environment-forced hardware profiles."""
    runtime_profile.cache_clear()
    hardware_capabilities.cache_clear()
