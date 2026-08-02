#!/usr/bin/env python3
"""فحص بيئة Android وتشغيل التحليل والاختبارات وبناء APK/AAB إلى dist/."""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MOBILE_DIR = ROOT / "mobile_app"
DIST_DIR = ROOT / "dist" / "mobile" / "android"


def _run(command: list[str], cwd: Path = MOBILE_DIR) -> None:
    print("+", " ".join(command))
    subprocess.run(command, cwd=cwd, check=True)


def _find_flutter() -> str:
    executable = shutil.which("flutter")
    if executable:
        return executable
    print("Flutter غير موجود في PATH. ثبّت Flutter stable ثم أعد المحاولة.", file=sys.stderr)
    raise SystemExit(2)


def _check_environment(flutter: str) -> None:
    if shutil.which("java") is None:
        raise SystemExit("Java غير موجود. ثبّت JDK 17.")
    android_home = os.environ.get("ANDROID_SDK_ROOT") or os.environ.get("ANDROID_HOME")
    if not android_home or not Path(android_home).is_dir():
        raise SystemExit("Android SDK غير مضبوط. عيّن ANDROID_SDK_ROOT إلى مجلد SDK.")
    _run([flutter, "--version"])
    _run(["java", "-version"])
    _run([flutter, "doctor", "-v"])


def _ensure_gradle_wrapper(flutter: str) -> None:
    wrapper_jar = MOBILE_DIR / "android" / "gradle" / "wrapper" / "gradle-wrapper.jar"
    gradlew = MOBILE_DIR / "android" / ("gradlew.bat" if sys.platform == "win32" else "gradlew")
    if wrapper_jar.exists() and gradlew.exists():
        return
    with tempfile.TemporaryDirectory(prefix="voice_ai_flutter_") as temporary:
        scaffold = Path(temporary) / "wrapper_scaffold"
        _run(
            [flutter, "create", "--platforms", "android", "--project-name", "wrapper_scaffold", str(scaffold)],
            cwd=ROOT,
        )
        source_android = scaffold / "android"
        target_android = MOBILE_DIR / "android"
        (target_android / "gradle" / "wrapper").mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_android / "gradle" / "wrapper" / "gradle-wrapper.jar", wrapper_jar)
        shutil.copy2(source_android / "gradlew", target_android / "gradlew")
        shutil.copy2(source_android / "gradlew.bat", target_android / "gradlew.bat")
        if sys.platform != "win32":
            (target_android / "gradlew").chmod(0o755)


def _copy_artifact(source: Path, name: str) -> Path:
    if not source.is_file():
        raise FileNotFoundError(f"لم يُنشأ الملف المتوقع: {source}")
    DIST_DIR.mkdir(parents=True, exist_ok=True)
    destination = DIST_DIR / name
    shutil.copy2(source, destination)
    digest = hashlib.sha256(destination.read_bytes()).hexdigest()
    (destination.with_suffix(destination.suffix + ".sha256")).write_text(
        f"{digest}  {destination.name}\n", encoding="utf-8"
    )
    print(f"النتيجة: {destination}")
    return destination


def main() -> int:
    parser = argparse.ArgumentParser(description="بناء تطبيق Voice AI Mobile لنظام Android")
    targets = parser.add_mutually_exclusive_group()
    targets.add_argument("--apk", action="store_true")
    targets.add_argument("--aab", action="store_true")
    targets.add_argument("--all", action="store_true")
    parser.add_argument("--debug", action="store_true", help="بناء APK debug قابل للتثبيت دون مفتاح release")
    parser.add_argument("--skip-checks", action="store_true")
    args = parser.parse_args()

    flutter = _find_flutter()
    _check_environment(flutter)
    _ensure_gradle_wrapper(flutter)
    _run([flutter, "pub", "get"])
    if not args.skip_checks:
        _run([flutter, "analyze", "--fatal-infos"])
        _run([flutter, "test"])

    build_apk = args.apk or args.all or (not args.apk and not args.aab and not args.all)
    build_aab = args.aab or args.all or (not args.apk and not args.aab and not args.all)
    mode = "debug" if args.debug else "release"
    if build_apk:
        _run([flutter, "build", "apk", f"--{mode}"])
        suffix = "debug" if args.debug else "release"
        _copy_artifact(
            MOBILE_DIR / "build" / "app" / "outputs" / "flutter-apk" / f"app-{suffix}.apk",
            f"voice-ai-mobile-{suffix}.apk",
        )
    if build_aab:
        if args.debug:
            raise SystemExit("AAB يُبنى بوضع release فقط؛ أزل --debug.")
        _run([flutter, "build", "appbundle", "--release"])
        _copy_artifact(
            MOBILE_DIR / "build" / "app" / "outputs" / "bundle" / "release" / "app-release.aab",
            "voice-ai-mobile-release.aab",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
