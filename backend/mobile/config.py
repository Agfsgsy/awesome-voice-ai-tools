"""إعدادات طبقة الجوال دون تغيير إعدادات نسخة سطح المكتب."""

from __future__ import annotations

import os
from pathlib import Path

from backend.core.config import BASE_DIR, MAX_UPLOAD_MB

MOBILE_DATA_DIR = Path(os.getenv("MOBILE_DATA_DIR", str(BASE_DIR / ".mobile_data"))).expanduser().resolve()
MOBILE_UPLOADS_DIR = MOBILE_DATA_DIR / "uploads"
MOBILE_JOBS_DIR = MOBILE_DATA_DIR / "jobs"
MOBILE_PAIRING_DIR = MOBILE_DATA_DIR / "pairing"

for directory in (MOBILE_DATA_DIR, MOBILE_UPLOADS_DIR, MOBILE_JOBS_DIR, MOBILE_PAIRING_DIR):
    directory.mkdir(parents=True, exist_ok=True)

MOBILE_SECRET_FILE = MOBILE_DATA_DIR / "server_secret"
MOBILE_DEVICES_FILE = MOBILE_DATA_DIR / "devices.json"
MOBILE_PAIRING_FILE = MOBILE_PAIRING_DIR / "sessions.json"
MOBILE_JOBS_FILE = MOBILE_JOBS_DIR / "jobs.json"
MOBILE_UPLOAD_STATE_FILE = MOBILE_UPLOADS_DIR / "upload_state.json"

MOBILE_PAIRING_TTL_SECONDS = max(60, int(os.getenv("MOBILE_PAIRING_TTL_SECONDS", "300")))
MOBILE_ACCESS_TOKEN_SECONDS = max(300, int(os.getenv("MOBILE_ACCESS_TOKEN_SECONDS", "3600")))
MOBILE_SHARE_TOKEN_SECONDS = max(30, int(os.getenv("MOBILE_SHARE_TOKEN_SECONDS", "300")))
MOBILE_MAX_UPLOAD_MB = max(1, int(os.getenv("MOBILE_MAX_UPLOAD_MB", str(MAX_UPLOAD_MB))))
MOBILE_REQUIRE_HTTPS_EXTERNAL = os.getenv("MOBILE_REQUIRE_HTTPS_EXTERNAL", "true").lower() == "true"
MOBILE_TRUST_PROXY_HEADERS = os.getenv("MOBILE_TRUST_PROXY_HEADERS", "false").lower() == "true"
MOBILE_SERVICE_NAME = os.getenv("MOBILE_SERVICE_NAME", "Voice AI Studio")
MOBILE_SERVICE_TYPE = "_voiceai._tcp.local."

SUPPORTED_MOBILE_AUDIO_EXTENSIONS = {
    ".wav",
    ".mp3",
    ".m4a",
    ".aac",
    ".flac",
    ".ogg",
    ".opus",
    ".webm",
    ".amr",
    ".3gp",
    ".mp4",
    ".mkv",
    ".aiff",
    ".wma",
}

SUPPORTED_DOCUMENT_EXTENSIONS = {".pdf", ".docx", ".txt"}
