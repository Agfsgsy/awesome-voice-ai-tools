# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

from PyInstaller.utils.hooks import (
    collect_all,
    collect_submodules,
)

project_root = Path(SPEC).resolve().parent

datas = [(str(project_root / "frontend"), "frontend")]
binaries = []
hiddenimports = collect_submodules("backend.plugins") + collect_submodules("uvicorn")

for package in ("edge_tts", "imageio_ffmpeg"):
    package_datas, package_binaries, package_hidden = collect_all(package)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hidden


def piper_runtime_module(name):
    return not name.startswith(
        ("piper.train", "piper.http_server", "piper.download_voices", "piper.__main__")
    )


# Keep the Arabic inference runtime and omit Piper's unrelated training/server assets.
piper_datas, piper_binaries, piper_hidden = collect_all(
    "piper",
    filter_submodules=piper_runtime_module,
    exclude_datas=["train/**", "hebrew/**", "img/**", "templates/**"],
)
datas += piper_datas
binaries += piper_binaries
hiddenimports += piper_hidden


def windows_webview_module(name):
    return not name.startswith(
        (
            "webview.platforms.android",
            "webview.platforms.cef",
            "webview.platforms.cocoa",
            "webview.platforms.gtk",
            "webview.platforms.qt",
        )
    )


webview_datas, webview_binaries, webview_hidden = collect_all(
    "webview",
    filter_submodules=windows_webview_module,
)
datas += webview_datas
binaries += webview_binaries
hiddenimports += webview_hidden

hiddenimports += [
    "multipart",
    "pydub",
    "piper",
    "piper.config",
    "piper.voice",
    "webview.platforms.winforms",
    "google.auth",
    "google.auth.transport.requests",
    "google.oauth2.service_account",
]

a = Analysis(
    [str(project_root / "desktop_app.py")],
    pathex=[str(project_root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=sorted(set(hiddenimports)),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "pytest",
        "notebook",
        "jupyter",
        "matplotlib",
        "onnx",
        "torch",
        "tensorflow",
    ],
    noarchive=False,
    optimize=1,
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
