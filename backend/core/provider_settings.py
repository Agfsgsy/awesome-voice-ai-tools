"""Local provider settings with masked reads and atomic writes."""

from __future__ import annotations

import json
import os
from typing import Any

from backend.core.config import CONFIG_DIR
from backend.core.logger import get_logger

logger = get_logger("provider_settings")

SETTINGS_FILE = CONFIG_DIR / "voice_providers.json"
SECRET_FIELDS = {"api_key", "service_account_json"}
ALLOWED_FIELDS = {
    "api_key",
    "service_account_json",
    "region",
    "project_id",
    "model_id",
    "male_voice_id_ar",
    "female_voice_id_ar",
    "male_voice_id_en",
    "female_voice_id_en",
}

ENVIRONMENT_FIELDS = {
    "openai": {"api_key": "OPENAI_API_KEY", "model_id": "OPENAI_TTS_MODEL"},
    "azure": {"api_key": "AZURE_SPEECH_KEY", "region": "AZURE_SPEECH_REGION"},
    "google_cloud": {"api_key": "GOOGLE_CLOUD_TTS_API_KEY", "project_id": "GOOGLE_CLOUD_PROJECT"},
    "elevenlabs": {
        "api_key": "ELEVENLABS_API_KEY",
        "model_id": "ELEVENLABS_MODEL_ID",
        "male_voice_id_ar": "ELEVENLABS_VOICE_ID",
    },
}


def _read_all() -> dict[str, dict[str, str]]:
    if not SETTINGS_FILE.exists():
        return {}
    try:
        payload = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return {}
        result: dict[str, dict[str, str]] = {}
        for provider, values in payload.items():
            if not isinstance(values, dict):
                continue
            result[str(provider)] = {
                str(key): str(value)
                for key, value in values.items()
                if key in ALLOWED_FIELDS and isinstance(value, (str, int, float))
            }
        return result
    except Exception as exc:
        logger.warning("Provider settings could not be read: %s", exc)
        return {}


def _write_all(payload: dict[str, dict[str, str]]) -> None:
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary = SETTINGS_FILE.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary.replace(SETTINGS_FILE)
    try:
        SETTINGS_FILE.chmod(0o600)
    except OSError:
        pass


def provider_config(provider: str) -> dict[str, str]:
    values = dict(_read_all().get(provider, {}))
    for field, environment_name in ENVIRONMENT_FIELDS.get(provider, {}).items():
        environment_value = os.getenv(environment_name, "").strip()
        if environment_value and not values.get(field):
            values[field] = environment_value
    return values


def save_provider_config(
    provider: str,
    updates: dict[str, Any],
    *,
    clear_secret: bool = False,
) -> dict[str, str]:
    payload = _read_all()
    current = dict(payload.get(provider, {}))
    for field, value in updates.items():
        if field not in ALLOWED_FIELDS or value is None:
            continue
        clean = str(value).strip()
        if len(clean) > 12000:
            raise ValueError(f"Provider field is too long: {field}")
        if field in SECRET_FIELDS and not clean and not clear_secret:
            continue
        if clean:
            current[field] = clean
        elif clear_secret or field not in SECRET_FIELDS:
            current.pop(field, None)
    payload[provider] = current
    _write_all(payload)
    apply_provider_environment(provider)
    return current


def apply_provider_environment(provider: str | None = None) -> None:
    providers = [provider] if provider else list(ENVIRONMENT_FIELDS)
    for provider_name in providers:
        values = provider_config(provider_name)
        for field, environment_name in ENVIRONMENT_FIELDS.get(provider_name, {}).items():
            value = values.get(field, "").strip()
            if value:
                os.environ[environment_name] = value


def masked_provider_config(provider: str) -> dict[str, Any]:
    values = provider_config(provider)
    result: dict[str, Any] = {}
    for field, value in values.items():
        if field in SECRET_FIELDS:
            result[f"{field}_set"] = bool(value)
            if value:
                result[f"{field}_hint"] = f"{value[:3]}…{value[-3:]}" if len(value) > 8 else "••••••"
        else:
            result[field] = value
    return result


apply_provider_environment()
