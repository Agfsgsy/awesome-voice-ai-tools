# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

from PyInstaller.utils.hooks import (
    collect_data_files,
    collect_dynamic_libs,
    collect_submodules,
)

project_root = Path(SPEC).resolve().parent.parent

datas = [(str(project_root / "frontend"), "frontend")]
for optional_dir in ("config",):
    source = project_root / optional_dir
    if source.exists():
        datas.append((str(source), optional_dir))

datas += collect_data_files("edge_tts")
datas += collect_data_files("imageio_ffmpeg")
datas += collect_data_files("webview")

binaries = collect_dynamic_libs("imageio_ffmpeg")

hiddenimports = sorted(set(
    collect_submodules("backend.plugins")
    + collect_submodules("uvicorn")
    + [
        "edge_tts",
        "imageio_ffmpeg",
        "multipart",
        "pydub",
        "webview",
        "webview.platforms.winforms",
    ]
))

a = Analysis(
    [str(project_root / "desktop_app.py")],
    pathex=[str(project_root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest", "notebook", "jupyter", "matplotlib"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="VoiceAIStudioArabic",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    uac_admin=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="VoiceAIStudioArabic",
)
