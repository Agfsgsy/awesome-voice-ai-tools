#!/usr/bin/env bash
set -euo pipefail
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"
command -v python3 >/dev/null || { echo "Python 3 غير موجود." >&2; exit 2; }
command -v flutter >/dev/null || { echo "Flutter غير موجود في PATH." >&2; exit 2; }
command -v java >/dev/null || { echo "Java JDK 17 غير موجود." >&2; exit 2; }
if [[ -z "${ANDROID_SDK_ROOT:-}" && -z "${ANDROID_HOME:-}" ]]; then
  echo "اضبط ANDROID_SDK_ROOT إلى مجلد Android SDK." >&2
  exit 2
fi
python3 scripts/setup_mobile_backend.py
flutter doctor -v
cd mobile_app
flutter pub get
echo "اكتمل إعداد تطبيق الجوال."
