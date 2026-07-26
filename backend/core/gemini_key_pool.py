"""Persistent Gemini API-key pool with robust parsing and round-robin rotation.

Keys are stored only in the existing local Gemini settings file. Runtime state stores
fingerprints, never full keys.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from pathlib import Path
from typing import Any, Iterable

from backend.core.config import CONFIG_DIR

SETTINGS_FILE = CONFIG_DIR / "gemini.json"
STATE_FILE = CONFIG_DIR / "gemini_key_state.json"
API_KEY_PATTERN = re.compile(r"AIza[0-9A-Za-z_-]{20,}")


def _read_json(path: Path) -> dict[str, Any]:
    try:
        if path.exists():
            value = json.loads(path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
    except Exception:
        pass
    return {}


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def parse_keys(value: str | Iterable[str] | None) -> list[str]:
    """Extract complete Gemini keys from pasted lines, labels, JSON or separators."""
    if value is None:
        return []
    if not isinstance(value, str):
        value = "\n".join(str(item) for item in value)
    raw = value.replace("\ufeff", " ").replace("`", " ").strip()
    found = API_KEY_PATTERN.findall(raw)
    if not found:
        candidates = re.split(r"[\s,;|]+", raw)
        found = [item.strip("'\"[](){}<>،؛:") for item in candidates]
    valid: list[str] = []
    for item in found:
        key = str(item).strip()
        if len(key) < 20 or any(ch.isspace() for ch in key):
            continue
        if key not in valid:
            valid.append(key)
    return valid


def fingerprint(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]


def masked_key(key: str, number: int | None = None) -> str:
    prefix = f"#{number} " if number is not None else ""
    if len(key) < 10:
        return prefix + "••••"
    return f"{prefix}{key[:4]}••••••{key[-4:]}"


def load_config() -> dict[str, Any]:
    return _read_json(SETTINGS_FILE)


def load_keys() -> list[str]:
    data = load_config()
    values: list[str] = []
    values.extend(parse_keys(data.get("api_keys") or []))
    values.extend(parse_keys(data.get("api_key") or ""))
    values.extend(parse_keys(os.getenv("GEMINI_API_KEYS", "")))
    values.extend(parse_keys(os.getenv("GEMINI_API_KEY", "")))
    return list(dict.fromkeys(values))


def save_config(keys: list[str], model_id: str, voice_name: str) -> None:
    unique = list(dict.fromkeys(parse_keys(keys)))
    data = {
        "api_keys": unique,
        "model_id": model_id,
        "voice_name": voice_name,
    }
    _write_json(SETTINGS_FILE, data)
    apply_environment(unique, model_id)
    _sync_state(unique)


def append_keys(raw: str | Iterable[str], model_id: str, voice_name: str, replace: bool = False) -> list[str]:
    incoming = parse_keys(raw)
    existing = [] if replace else load_keys()
    keys = list(dict.fromkeys([*existing, *incoming]))
    save_config(keys, model_id, voice_name)
    return keys


def apply_environment(keys: list[str] | None = None, model_id: str | None = None) -> None:
    keys = list(keys if keys is not None else load_keys())
    if keys:
        os.environ["GEMINI_API_KEYS"] = "||".join(keys)
        os.environ["GEMINI_API_KEY"] = keys[0]
    else:
        os.environ.pop("GEMINI_API_KEYS", None)
        os.environ.pop("GEMINI_API_KEY", None)
    if model_id:
        os.environ["GEMINI_TTS_MODEL"] = model_id


def _sync_state(keys: list[str]) -> dict[str, Any]:
    state = _read_json(STATE_FILE)
    fingerprints = [fingerprint(key) for key in keys]
    records = state.get("records") if isinstance(state.get("records"), dict) else {}
    records = {fp: records.get(fp, {}) for fp in fingerprints}
    cursor = int(state.get("cursor", 0) or 0)
    state = {"cursor": cursor % max(1, len(keys)), "records": records, "updated_at": int(time.time())}
    _write_json(STATE_FILE, state)
    return state


def ordered_keys() -> list[str]:
    keys = load_keys()
    if not keys:
        return []
    state = _sync_state(keys)
    cursor = int(state.get("cursor", 0) or 0) % len(keys)
    rotated = keys[cursor:] + keys[:cursor]
    now = time.time()
    records = state.get("records", {})
    ready: list[str] = []
    cooling: list[str] = []
    for key in rotated:
        cooldown_until = float((records.get(fingerprint(key)) or {}).get("cooldown_until", 0) or 0)
        (ready if cooldown_until <= now else cooling).append(key)
    return ready + cooling


def record_result(key: str, status: str, detail: str = "") -> None:
    keys = load_keys()
    if key not in keys:
        return
    state = _sync_state(keys)
    fp = fingerprint(key)
    record = dict((state.get("records") or {}).get(fp) or {})
    now = time.time()
    record.update({"status": status, "detail": detail[:300], "checked_at": int(now)})
    if status == "working":
        record["cooldown_until"] = 0
        state["cursor"] = (keys.index(key) + 1) % len(keys)
    elif status == "quota":
        record["cooldown_until"] = int(now + 60)
        state["cursor"] = (keys.index(key) + 1) % len(keys)
    elif status in {"invalid", "forbidden"}:
        record["cooldown_until"] = int(now + 600)
        state["cursor"] = (keys.index(key) + 1) % len(keys)
    else:
        record["cooldown_until"] = int(now + 20)
    state.setdefault("records", {})[fp] = record
    state["updated_at"] = int(now)
    _write_json(STATE_FILE, state)


def key_statuses() -> list[dict[str, Any]]:
    keys = load_keys()
    state = _sync_state(keys) if keys else {"records": {}}
    records = state.get("records", {})
    result: list[dict[str, Any]] = []
    for number, key in enumerate(keys, start=1):
        record = dict(records.get(fingerprint(key)) or {})
        result.append({
            "number": number,
            "masked": masked_key(key, number),
            "status": record.get("status", "untested"),
            "detail": record.get("detail", ""),
            "checked_at": record.get("checked_at"),
        })
    return result
