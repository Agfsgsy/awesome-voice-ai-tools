#!/usr/bin/env python3
"""Install, inspect, and manage isolated official voice/music engine runtimes.

The script never downloads every multi-gigabyte model without an explicit
engine selection. It creates isolated environments and clones only official
repositories selected by the user.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parents[1]
RUNTIMES = ROOT / "runtimes"

ENGINES: Dict[str, Dict[str, str]] = {
    "xtts": {"repo": "https://github.com/coqui-ai/TTS", "env": "XTTS_ENDPOINT", "port": "8100"},
    "openvoice": {"repo": "https://github.com/myshell-ai/OpenVoice", "env": "OPENVOICE_ENDPOINT", "port": "8101"},
    "f5tts": {"repo": "https://github.com/SWivid/F5-TTS", "env": "F5TTS_ENDPOINT", "port": "8102"},
    "gpt_sovits": {"repo": "https://github.com/RVC-Boss/GPT-SoVITS", "env": "GPT_SOVITS_ENDPOINT", "port": "8103"},
    "cosyvoice": {"repo": "https://github.com/FunAudioLLM/CosyVoice", "env": "COSYVOICE_ENDPOINT", "port": "8104"},
    "rvc": {"repo": "https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI", "env": "RVC_ENDPOINT", "port": "8110"},
    "ace_step": {"repo": "https://github.com/ace-step/ACE-Step", "env": "ACE_STEP_ENDPOINT", "port": "8120"},
    "yue": {"repo": "https://github.com/multimodal-art-projection/YuE", "env": "YUE_ENDPOINT", "port": "8121"},
}


def run(command: List[str], cwd: Path | None = None) -> None:
    print("+", " ".join(command))
    subprocess.run(command, cwd=str(cwd) if cwd else None, check=True)


def doctor() -> int:
    report = {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "ffmpeg": shutil.which("ffmpeg"),
        "ffprobe": shutil.which("ffprobe"),
        "git": shutil.which("git"),
        "torch": importlib.util.find_spec("torch") is not None,
        "coqui_tts": importlib.util.find_spec("TTS") is not None,
        "soundfile": importlib.util.find_spec("soundfile") is not None,
        "librosa": importlib.util.find_spec("librosa") is not None,
        "speechbrain": importlib.util.find_spec("speechbrain") is not None,
        "faster_whisper": importlib.util.find_spec("faster_whisper") is not None,
        "runtime_dirs": {name: (RUNTIMES / name).exists() for name in ENGINES},
    }
    try:
        import torch
        report["cuda_available"] = torch.cuda.is_available()
        report["cuda_device"] = torch.cuda.get_device_name(0) if torch.cuda.is_available() else None
    except Exception:
        report["cuda_available"] = False
        report["cuda_device"] = None
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ffmpeg"] and report["ffprobe"] else 1


def install(engine: str) -> None:
    if engine not in ENGINES:
        raise SystemExit(f"Unknown engine: {engine}")
    if not shutil.which("git"):
        raise SystemExit("git is required")
    destination = RUNTIMES / engine
    RUNTIMES.mkdir(parents=True, exist_ok=True)
    if not destination.exists():
        run(["git", "clone", "--depth", "1", ENGINES[engine]["repo"], str(destination)])
    venv = destination / ".venv"
    if not venv.exists():
        run([sys.executable, "-m", "venv", str(venv)])
    python = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    run([str(python), "-m", "pip", "install", "--upgrade", "pip", "wheel", "setuptools"])
    requirement_candidates = [destination / "requirements.txt", destination / "requirements" / "requirements.txt"]
    requirement = next((path for path in requirement_candidates if path.exists()), None)
    if requirement:
        run([str(python), "-m", "pip", "install", "-r", str(requirement)], cwd=destination)
    elif (destination / "pyproject.toml").exists() or (destination / "setup.py").exists():
        run([str(python), "-m", "pip", "install", "-e", "."], cwd=destination)
    print(f"Installed source/runtime for {engine} in {destination}")
    print("Review the official engine and model license before production or commercial use.")
    print(f"Expected unified adapter endpoint: http://127.0.0.1:{ENGINES[engine]['port']}")


def write_env() -> None:
    path = ROOT / ".env.voice-ai.example"
    lines = [
        f"{data['env']}=http://127.0.0.1:{data['port']}"
        for name, data in ENGINES.items()
        if name != "xtts"
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Voice AI runtime manager")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("doctor")
    install_parser = subparsers.add_parser("install")
    install_parser.add_argument("engine", choices=sorted(ENGINES))
    subparsers.add_parser("write-env")
    args = parser.parse_args()
    if args.command == "doctor":
        return doctor()
    if args.command == "install":
        install(args.engine)
        return 0
    if args.command == "write-env":
        write_env()
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
