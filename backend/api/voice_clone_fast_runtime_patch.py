"""Small runtime hardening patch for the additive fast voice-clone router."""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

from backend.api import voice_clone_fast_routes as fast
from backend.api import voice_clone_xtts_runtime as xtts
from backend.core.provider_settings import provider_config

_ORIGINAL_PRODUCE = fast._produce_with_provider


def _gemini_config() -> dict[str, str]:
    values = provider_config("google_cloud")
    configured_model = str(values.get("model_id") or "").strip()
    model_id = (
        configured_model
        if configured_model.startswith("gemini-") and "tts" in configured_model.lower()
        else "gemini-2.5-flash-tts-eap-11-2025"
    )
    return {
        "project_id": str(values.get("project_id") or os.getenv("GOOGLE_CLOUD_PROJECT", "")).strip(),
        "service_account_json": str(values.get("service_account_json") or "").strip(),
        "model_id": model_id,
    }


def _google_access_token() -> tuple[str, str]:
    import google.auth
    from google.auth.transport.requests import Request
    from google.oauth2 import service_account

    config = _gemini_config()
    scopes = ["https://www.googleapis.com/auth/cloud-platform"]
    raw = config["service_account_json"].strip()
    project_id = config["project_id"]
    if raw:
        if raw.startswith("{"):
            credentials = service_account.Credentials.from_service_account_info(json.loads(raw), scopes=scopes)
        else:
            try:
                candidate = Path(raw).expanduser()
                is_file = candidate.exists() and candidate.is_file()
            except OSError:
                is_file = False
            if is_file:
                credentials = service_account.Credentials.from_service_account_file(str(candidate), scopes=scopes)
            else:
                credentials = service_account.Credentials.from_service_account_info(json.loads(raw), scopes=scopes)
    else:
        credentials, detected_project = google.auth.default(scopes=scopes)
        project_id = project_id or str(detected_project or "")
    credentials.refresh(Request())
    if not credentials.token or not project_id:
        raise RuntimeError("تعذر الحصول على رمز Google Cloud أو Project ID.")
    return str(credentials.token), project_id


async def _bounded_produce(provider, request, manifest, references, raw):
    if provider == "local":
        if not fast.MODEL_MARKER.exists():
            raise RuntimeError("نموذج XTTS الكامل غير مجهز. اضغط تجهيز المحرك مرة واحدة قبل الإنتاج المحلي.")
        return await asyncio.to_thread(
            xtts.generate,
            request.profile_id,
            manifest,
            references,
            request.text.strip(),
            request.language,
            raw,
        )

    timeout = 300.0 if provider == "elevenlabs" else 420.0
    try:
        return await asyncio.wait_for(
            _ORIGINAL_PRODUCE(provider, request, manifest, references, raw),
            timeout=timeout,
        )
    except asyncio.TimeoutError as exc:
        label = "ElevenLabs" if provider == "elevenlabs" else "Gemini Voice Replication"
        raise RuntimeError(f"انتهت مهلة {label} ولم يبق الطلب معلقًا.") from exc


fast._gemini_config = _gemini_config
fast._google_access_token = _google_access_token
fast._local_generate_fast = xtts.generate
fast._produce_with_provider = _bounded_produce
