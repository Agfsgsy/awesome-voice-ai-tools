#!/usr/bin/env python3
"""Install Voice Clone Pro 7 engines into isolated runtimes.

XTTS is installed through the studio's proven local-engine installer. Other
projects are cloned from their official repositories and receive independent
virtual environments so conflicting Torch/Transformers versions cannot damage
Ibn Al-Waqadi Studio. Model weights remain governed by each project's license.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.api import voice_clone_v7_setup_runtime as _voice_clone_v7_setup_runtime  # noqa: E402,F401
from backend.core.config import DATA_DIR  # noqa: E402

PACK_ROOT = DATA_DIR / "voice_engine_pack_v7"
STATUS_FILE = PACK_ROOT / "install_report.json"

ENGINE_SOURCES: dict[str, dict[str, Any]] = {
    "openvoice": {
        "repo": "https://github.com/myshell-ai/OpenVoice.git",
        "tasks": ["speech_clone", "voice_conversion"],
        "port": 8101,
    },
    "f5tts": {
        "repo": "https://github.com/SWivid/F5-TTS.git",
        "tasks": ["speech_clone"],
        "port": 8102,
    },
    "gpt_sovits": {
        "repo": "https://github.com/RVC-Boss/GPT-SoVITS.git",
        "tasks": ["speech_clone", "few_shot_clone"],
        "port": 8103,
    },
    "cosyvoice": {
        "repo": "https://github.com/FunAudioLLM/CosyVoice.git",
        "tasks": ["speech_clone", "streaming"],
        "port": 8104,
    },
    "rvc": {
        "repo": "https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI.git",
        "tasks": ["voice_conversion", "singing_conversion"],
        "port": 8110,
    },
    "ace_step": {
        "repo": "https://github.com/ace-step/ACE-Step.git",
        "tasks": ["song_generation", "sheilah_generation"],
        "port": 8120,
    },
    "yue": {
        "repo": "https://github.com/multimodal-art-projection/YuE.git",
        "tasks": ["song_generation", "sheilah_generation"],
        "port": 8121,
    },
}


def _run(command: list[str], cwd: Path | None = None, timeout: int = 7200) -> subprocess.CompletedProcess[str]:
    print("+", " ".join(command), flush=True)
    return subprocess.run(
        command,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )


def _venv_python(venv: Path) -> Path:
    return venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def _write_report(report: dict[str, Any]) -> None:
    PACK_ROOT.mkdir(parents=True, exist_ok=True)
    report["updated_at"] = time.time()
    STATUS_FILE.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


def _python_ok() -> None:
    if sys.version_info[:2] != (3, 11):
        raise RuntimeError(
            f"هذا المثبت يحتاج Python 3.11، والإصدار الحالي {sys.version_info.major}.{sys.version_info.minor}. "
            "شغّله بواسطة: py -3.11 scripts\\install_voice_clone_engine_pack.py"
        )


def install_xtts(report: dict[str, Any]) -> None:
    from backend.api.voice_clone_routes import _read_status, _setup_local_engine

    print("\n=== XTTS-v2 Local Pro ===", flush=True)
    _setup_local_engine()
    status = _read_status()
    ready = status.get("state") == "ready"
    report["engines"]["xtts"] = {"installed": ready, "status": status}
    _write_report(report)
    if not ready:
        raise RuntimeError("فشل تجهيز XTTS: " + str(status.get("error") or status.get("message")))


def _requirements_candidates(source: Path) -> list[Path]:
    return [
        source / "requirements.txt",
        source / "requirements" / "requirements.txt",
        source / "requirements" / "requirements-windows.txt",
        source / "requirements_win.txt",
    ]


def install_source(name: str, definition: dict[str, Any], report: dict[str, Any], install_dependencies: bool) -> None:
    print(f"\n=== {name} ===", flush=True)
    engine_root = PACK_ROOT / name
    source = engine_root / "source"
    venv = engine_root / "venv"
    engine_root.mkdir(parents=True, exist_ok=True)
    if not source.exists():
        completed = _run(["git", "clone", "--depth", "1", definition["repo"], str(source)], timeout=3600)
        if completed.returncode != 0:
            raise RuntimeError((completed.stderr or completed.stdout or "git clone failed")[-3000:])
    else:
        completed = _run(["git", "pull", "--ff-only"], cwd=source, timeout=900)
        if completed.returncode != 0:
            print("تحذير: تعذر تحديث المصدر؛ سيتم استخدام النسخة الموجودة.")

    if not venv.exists():
        completed = _run([sys.executable, "-m", "venv", str(venv)], timeout=900)
        if completed.returncode != 0:
            raise RuntimeError((completed.stderr or completed.stdout or "venv failed")[-3000:])
    python = _venv_python(venv)
    completed = _run([str(python), "-m", "pip", "install", "--upgrade", "pip", "wheel", "setuptools"], timeout=1200)
    if completed.returncode != 0:
        raise RuntimeError((completed.stderr or completed.stdout or "pip upgrade failed")[-3000:])

    dependency_state = "source_only"
    if install_dependencies:
        requirement = next((item for item in _requirements_candidates(source) if item.exists()), None)
        if requirement:
            completed = _run([str(python), "-m", "pip", "install", "-r", str(requirement)], cwd=source, timeout=6 * 3600)
            if completed.returncode != 0:
                raise RuntimeError((completed.stderr or completed.stdout or "requirements failed")[-4000:])
            dependency_state = "requirements_installed"
        elif (source / "pyproject.toml").exists() or (source / "setup.py").exists():
            completed = _run([str(python), "-m", "pip", "install", "-e", "."], cwd=source, timeout=6 * 3600)
            if completed.returncode != 0:
                raise RuntimeError((completed.stderr or completed.stdout or "editable install failed")[-4000:])
            dependency_state = "package_installed"

    runtime = {
        "name": name,
        "official_repository": definition["repo"],
        "source": str(source),
        "python": str(python),
        "port": definition["port"],
        "tasks": definition["tasks"],
        "dependency_state": dependency_state,
        "installed_at": time.time(),
        "note": "راجع ترخيص الكود والأوزان، ثم شغّل واجهة runtime المتوافقة مع /health و/clone أو /song/generate.",
    }
    (engine_root / "runtime.json").write_text(json.dumps(runtime, ensure_ascii=False, indent=2), encoding="utf-8")
    report["engines"][name] = {"installed": True, **runtime}
    _write_report(report)


def main() -> int:
    parser = argparse.ArgumentParser(description="Install Voice Clone Pro 7 engine pack")
    parser.add_argument("--all", action="store_true", help="Install all speech-cloning sources")
    parser.add_argument("--engine", action="append", choices=sorted(ENGINE_SOURCES))
    parser.add_argument("--include-music", action="store_true", help="Include RVC, ACE-Step and YuE")
    parser.add_argument("--accept-licenses", action="store_true")
    parser.add_argument("--source-only", action="store_true", help="Clone sources and create venvs without heavy dependencies")
    parser.add_argument("--skip-xtts", action="store_true")
    args = parser.parse_args()

    _python_ok()
    if not args.accept_licenses:
        print("يجب إضافة --accept-licenses بعد مراجعة تراخيص كل أداة ونموذج.")
        return 2
    if not shutil.which("git"):
        print("Git غير مثبت. ثبّت Git for Windows ثم أعد المحاولة.")
        return 2
    if not shutil.which("ffmpeg"):
        print("تحذير: FFmpeg غير موجود في PATH. سيحتاجه تحليل الصوت والمزج.")

    PACK_ROOT.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {
        "version": "7.0.0",
        "python": sys.version,
        "root": str(PACK_ROOT),
        "engines": {},
        "failures": {},
    }
    _write_report(report)

    if not args.skip_xtts:
        try:
            install_xtts(report)
        except Exception as exc:
            report["failures"]["xtts"] = str(exc)
            _write_report(report)
            print("XTTS ERROR:", exc)

    requested = list(args.engine or [])
    if args.all:
        requested = ["openvoice", "f5tts", "gpt_sovits", "cosyvoice"]
        if args.include_music:
            requested += ["rvc", "ace_step", "yue"]
    elif args.include_music:
        requested += ["rvc", "ace_step", "yue"]
    requested = list(dict.fromkeys(requested))

    for name in requested:
        try:
            install_source(name, ENGINE_SOURCES[name], report, install_dependencies=not args.source_only)
        except Exception as exc:
            report["failures"][name] = str(exc)
            _write_report(report)
            print(f"{name} ERROR:", exc)

    report["completed"] = True
    _write_report(report)
    print("\nتقرير التثبيت:", STATUS_FILE)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if "xtts" in report["failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
