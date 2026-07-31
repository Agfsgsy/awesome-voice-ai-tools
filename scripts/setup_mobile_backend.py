#!/usr/bin/env python3
"""إنشاء بيئة خادم الجوال والتحقق من الأدوات اللازمة."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENV_DIR = ROOT / ".venv"


def _run(command: list[str]) -> None:
    print("+", " ".join(command))
    subprocess.run(command, cwd=ROOT, check=True)


def _venv_python() -> Path:
    return VENV_DIR / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")


def main() -> int:
    parser = argparse.ArgumentParser(description="إعداد خادم FastAPI لتطبيق Voice AI على الجوال")
    parser.add_argument("--check-only", action="store_true", help="فحص الأدوات دون تثبيت")
    args = parser.parse_args()

    if sys.version_info < (3, 9):  # noqa: UP036 - السكربت قد يُشغّل قبل تثبيت حزمة المشروع.
        print("يلزم Python 3.9 أو أحدث.", file=sys.stderr)
        return 2
    missing = [name for name in ("ffmpeg", "ffprobe") if shutil.which(name) is None]
    if missing:
        print(f"الأدوات غير الموجودة: {', '.join(missing)}. ثبّت FFmpeg ثم أعد المحاولة.", file=sys.stderr)
        return 2
    print(f"Python: {sys.version.split()[0]}")
    print(f"FFmpeg: {shutil.which('ffmpeg')}")
    if args.check_only:
        return 0
    if not _venv_python().exists():
        print(f"إنشاء البيئة الافتراضية: {VENV_DIR}")
        venv.EnvBuilder(with_pip=True).create(VENV_DIR)
    python = str(_venv_python())
    _run([python, "-m", "pip", "install", "--upgrade", "pip"])
    _run([python, "-m", "pip", "install", "-r", "requirements.txt", "-r", "requirements-mobile-backend.txt"])
    print("اكتمل إعداد خادم الجوال.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
