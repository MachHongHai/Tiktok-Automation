# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

from PyInstaller.utils.hooks import collect_all


ROOT = Path(SPECPATH).resolve()
datas = []
runtime_bin = ROOT / "runtime" / "bin"
qml_root = ROOT / "src" / "haizflow" / "desktop" / "qml"
if runtime_bin.is_dir():
    datas.append((str(runtime_bin), "bin"))
datas.append((str(qml_root), "haizflow/desktop/qml"))

binaries = []
hiddenimports = [
    "haizflow.services.douyin_channel_worker",
    "haizflow.vendor.douyin_xbogus",
]
for package in ("llama_cpp", "accelerate", "yt_dlp"):
    package_datas, package_binaries, package_hiddenimports = collect_all(package)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hiddenimports

a = Analysis(
    [str(ROOT / "haizflow_desktop.py")],
    pathex=[str(ROOT / "src")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "bokeh", "cupy", "dash", "dask", "distributed", "django", "flask",
        "IPython", "ipywidgets", "jupyter", "jupyterlab", "notebook", "plotly",
        "pytest", "sqlalchemy", "tensorboard", "tensorflow", "torch.utils.tensorboard", "tornado",
    ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="HaizFlow",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="HaizFlow",
)
