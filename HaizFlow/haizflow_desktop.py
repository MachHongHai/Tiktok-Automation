from pathlib import Path
import os
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
VENV_DIR = ROOT / ".venv"
VENV_PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"


def _restore_internal_standard_streams() -> None:
    """Recreate inherited pipes hidden by a PyInstaller windowed bootloader."""
    if os.name != "nt" or not getattr(sys, "frozen", False):
        return
    import ctypes
    import msvcrt

    stream_specs = (
        ("stdin", -10, os.O_RDONLY, "r"),
        ("stdout", -11, os.O_WRONLY, "w"),
        ("stderr", -12, os.O_WRONLY, "w"),
    )
    for name, handle_id, flags, mode in stream_specs:
        if getattr(sys, name) is not None:
            continue
        handle = ctypes.windll.kernel32.GetStdHandle(handle_id)
        stream = None
        if handle not in (0, -1):
            try:
                descriptor = msvcrt.open_osfhandle(handle, flags)
                stream = os.fdopen(descriptor, mode, encoding="utf-8", buffering=1, closefd=False)
            except OSError:
                stream = None
        if stream is None:
            fallback_mode = "r" if name == "stdin" else "w"
            stream = open(os.devnull, fallback_mode, encoding="utf-8")
        setattr(sys, name, stream)


def _running_in_project_venv() -> bool:
    try:
        return Path(sys.prefix).resolve() == VENV_DIR.resolve()
    except OSError:
        return False


if not getattr(sys, "frozen", False) and VENV_PYTHON.exists() and not _running_in_project_venv():
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    subprocess.Popen(
        [str(VENV_PYTHON), str(Path(__file__).resolve()), *sys.argv[1:]],
        cwd=str(ROOT),
        env=env,
        creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
    )
    raise SystemExit(0)

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

_INTERNAL_STREAM_MODES = {
    "--douyin-channel-worker",
    "--hymt2-worker",
    "--runtime-probe",
    "--release-smoke",
}
if any(mode in sys.argv for mode in _INTERNAL_STREAM_MODES):
    _restore_internal_standard_streams()

if "--hymt2-worker" in sys.argv:
    from haizflow.services.hymt2_worker import main as run_hymt2_worker

    worker_args = [argument for argument in sys.argv[1:] if argument != "--hymt2-worker"]
    raise SystemExit(run_hymt2_worker(worker_args))

if "--douyin-channel-worker" in sys.argv:
    from haizflow.services.douyin_channel_worker import main as run_douyin_channel_worker

    raise SystemExit(run_douyin_channel_worker())

if "--runtime-probe" in sys.argv:
    from haizflow.core.runtime_probe import main as run_runtime_probe

    probe_index = sys.argv.index("--runtime-probe")
    probe_device = sys.argv[probe_index + 1] if len(sys.argv) > probe_index + 1 else "cpu"
    raise SystemExit(run_runtime_probe(["--child", probe_device]))

if "--release-smoke" in sys.argv:
    from haizflow.core.release_smoke import main as run_release_smoke

    smoke_index = sys.argv.index("--release-smoke")
    raise SystemExit(run_release_smoke(sys.argv[smoke_index + 1 :]))

if "--ui-smoke-test" in sys.argv:
    os.environ["HAIZFLOW_SMOKE_TEST"] = "1"
    from haizflow.desktop.main import main as run_desktop_smoke

    run_desktop_smoke(smoke_test=True)
    raise SystemExit(0)

from haizflow.desktop.main import main


if __name__ == "__main__":
    main()

