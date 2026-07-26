"""Persistent Gemini API-key manager with enable/disable and sticky active-key rotation.

The settings file stores full keys locally on the user's device. API responses expose only
masked values and stable fingerprints. A manually selected key remains active while it works;
rotation happens only when it is paused, rejected, or out of quota.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from typing import Any, Iterable

from backend.core.config import CONFIG_DIR

SETTINGS_FILE = CONFIG_DIR / "gemini.json"
STATE_FILE = CONFIG_DIR / "gemini_key_state.json"
API_KEY_PATTERN = re.compile(r"AIza[0-9A-Za-z_-]{20,}")


def _read_json(path) -> dict[str, Any]:
    try:
        if path.exists():
            value = json.loads(path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
    except Exception:
        pass
    return {}


def _write_json(path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def parse_keys(value: str | Iterable[str] | None) -> list[str]:
    """Extract complete Gemini keys from pasted lines, labels, JSON, or separators."""
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


def _normalise_entries(data: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    data = data if data is not None else load_config()
    raw_entries = data.get("api_key_entries")
    entries: list[dict[str, Any]] = []
    seen: set[str] = set()

    if isinstance(raw_entries, list):
        for index, item in enumerate(raw_entries, start=1):
            if not isinstance(item, dict):
                continue
            candidates = parse_keys(item.get("key") or "")
            if not candidates:
                continue
            key = candidates[0]
            if key in seen:
                continue
            seen.add(key)
            entries.append({
                "key": key,
                "enabled": bool(item.get("enabled", True)),
                "label": str(item.get("label") or f"المفتاح {index}")[:80],
                "added_at": int(item.get("added_at") or time.time()),
            })

    if not entries:
        legacy: list[str] = []
        legacy.extend(parse_keys(data.get("api_keys") or []))
        legacy.extend(parse_keys(data.get("api_key") or ""))
        # Import environment keys only during first migration. Once a local list exists,
        # stale environment values are never merged back into it.
        if not legacy:
            legacy.extend(parse_keys(os.getenv("GEMINI_API_KEYS", "")))
            legacy.extend(parse_keys(os.getenv("GEMINI_API_KEY", "")))
        for index, key in enumerate(dict.fromkeys(legacy), start=1):
            entries.append({"key": key, "enabled": True, "label": f"المفتاح {index}", "added_at": int(time.time())})
    return entries


def load_entries() -> list[dict[str, Any]]:
    return _normalise_entries()


def load_keys(enabled_only: bool = False) -> list[str]:
    entries = load_entries()
    return [entry["key"] for entry in entries if not enabled_only or entry.get("enabled", True)]


def _save_entries(entries: list[dict[str, Any]], model_id: str | None = None, voice_name: str | None = None) -> None:
    previous = load_config()
    cleaned: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, entry in enumerate(entries, start=1):
        candidates = parse_keys(entry.get("key") if isinstance(entry, dict) else entry)
        if not candidates:
            continue
        key = candidates[0]
        if key in seen:
            continue
        seen.add(key)
        cleaned.append({
            "key": key,
            "enabled": bool(entry.get("enabled", True)) if isinstance(entry, dict) else True,
            "label": str(entry.get("label") or f"المفتاح {index}")[:80] if isinstance(entry, dict) else f"المفتاح {index}",
            "added_at": int(entry.get("added_at") or time.time()) if isinstance(entry, dict) else int(time.time()),
        })
    data = {
        "api_key_entries": cleaned,
        "api_keys": [entry["key"] for entry in cleaned],
        "model_id": model_id or str(previous.get("model_id") or "gemini-2.5-flash-preview-tts"),
        "voice_name": voice_name or str(previous.get("voice_name") or "Kore"),
    }
    _write_json(SETTINGS_FILE, data)
    apply_environment([entry["key"] for entry in cleaned if entry.get("enabled", True)], data["model_id"])
    _sync_state([entry["key"] for entry in cleaned])


def save_config(keys: list[str] | list[dict[str, Any]], model_id: str, voice_name: str) -> None:
    entries: list[dict[str, Any]] = []
    for index, item in enumerate(keys, start=1):
        if isinstance(item, dict):
            entries.append(item)
        else:
            entries.append({"key": item, "enabled": True, "label": f"المفتاح {index}", "added_at": int(time.time())})
    _save_entries(entries, model_id, voice_name)


def append_keys(raw: str | Iterable[str], model_id: str, voice_name: str, replace: bool = False, label: str = "") -> list[str]:
    incoming = parse_keys(raw)
    entries = [] if replace else load_entries()
    by_key = {entry["key"]: entry for entry in entries}
    for key in incoming:
        if key in by_key:
            by_key[key]["enabled"] = True
            if label:
                by_key[key]["label"] = label[:80]
            continue
        entry = {
            "key": key,
            "enabled": True,
            "label": (label.strip() or f"المفتاح {len(entries) + 1}")[:80],
            "added_at": int(time.time()),
        }
        entries.append(entry)
        by_key[key] = entry
    _save_entries(entries, model_id, voice_name)
    state = _sync_state([entry["key"] for entry in entries])
    if entries and not state.get("active_fp"):
        state["active_fp"] = fingerprint(entries[0]["key"])
        state["cursor"] = 0
        _write_json(STATE_FILE, state)
    return [entry["key"] for entry in entries]


def apply_environment(keys: list[str] | None = None, model_id: str | None = None) -> None:
    keys = list(keys if keys is not None else load_keys(enabled_only=True))
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
    active_fp = str(state.get("active_fp") or "")
    if active_fp not in fingerprints:
        active_fp = fingerprints[0] if fingerprints else ""
    state = {
        "cursor": cursor % max(1, len(keys)),
        "active_fp": active_fp,
        "records": records,
        "updated_at": int(time.time()),
    }
    _write_json(STATE_FILE, state)
    return state


def set_key_enabled(key_id: str, enabled: bool) -> dict[str, Any]:
    entries = load_entries()
    target = next((entry for entry in entries if fingerprint(entry["key"]) == key_id), None)
    if not target:
        raise KeyError("key_not_found")
    target["enabled"] = bool(enabled)
    data = load_config()
    _save_entries(entries, str(data.get("model_id") or "gemini-2.5-flash-preview-tts"), str(data.get("voice_name") or "Kore"))
    state = _sync_state([entry["key"] for entry in entries])
    if not enabled and state.get("active_fp") == key_id:
        next_enabled = next((entry for entry in entries if entry.get("enabled", True)), None)
        state["active_fp"] = fingerprint(next_enabled["key"]) if next_enabled else ""
        _write_json(STATE_FILE, state)
    apply_environment(load_keys(enabled_only=True), str(data.get("model_id") or ""))
    return key_status_by_id(key_id)


def set_active_key(key_id: str) -> dict[str, Any]:
    entries = load_entries()
    target_index = next((i for i, entry in enumerate(entries) if fingerprint(entry["key"]) == key_id), None)
    if target_index is None:
        raise KeyError("key_not_found")
    entries[target_index]["enabled"] = True
    data = load_config()
    _save_entries(entries, str(data.get("model_id") or "gemini-2.5-flash-preview-tts"), str(data.get("voice_name") or "Kore"))
    keys = [entry["key"] for entry in entries]
    state = _sync_state(keys)
    state["active_fp"] = key_id
    state["cursor"] = target_index
    record = dict((state.get("records") or {}).get(key_id) or {})
    record["cooldown_until"] = 0
    state.setdefault("records", {})[key_id] = record
    _write_json(STATE_FILE, state)
    ordered = ordered_keys()
    apply_environment(ordered, str(data.get("model_id") or ""))
    return key_status_by_id(key_id)


def ordered_keys() -> list[str]:
    entries = [entry for entry in load_entries() if entry.get("enabled", True)]
    if not entries:
        return []
    all_keys = [entry["key"] for entry in load_entries()]
    state = _sync_state(all_keys)
    active_fp = str(state.get("active_fp") or "")
    active = next((entry for entry in entries if fingerprint(entry["key"]) == active_fp), None)
    remaining = [entry for entry in entries if entry is not active]
    ordered_entries = ([active] if active else []) + remaining
    now = time.time()
    ready: list[str] = []
    cooling: list[str] = []
    records = state.get("records", {})
    for entry in ordered_entries:
        key = entry["key"]
        cooldown_until = float((records.get(fingerprint(key)) or {}).get("cooldown_until", 0) or 0)
        (ready if cooldown_until <= now else cooling).append(key)
    return ready + cooling


def record_result(key: str, status: str, detail: str = "") -> None:
    entries = load_entries()
    all_keys = [entry["key"] for entry in entries]
    if key not in all_keys:
        return
    state = _sync_state(all_keys)
    fp = fingerprint(key)
    record = dict((state.get("records") or {}).get(fp) or {})
    now = time.time()
    record.update({"status": status, "detail": detail[:300], "checked_at": int(now)})
    if status == "working":
        record["cooldown_until"] = 0
        # Sticky behaviour: keep the successful key active until it fails or is paused.
        state["active_fp"] = fp
        state["cursor"] = all_keys.index(key)
    elif status == "quota":
        record["cooldown_until"] = int(now + 60)
        enabled = [entry for entry in entries if entry.get("enabled", True) and entry["key"] != key]
        if enabled:
            next_entry = enabled[0]
            state["active_fp"] = fingerprint(next_entry["key"])
            state["cursor"] = all_keys.index(next_entry["key"])
    elif status in {"invalid", "forbidden"}:
        record["cooldown_until"] = int(now + 600)
        enabled = [entry for entry in entries if entry.get("enabled", True) and entry["key"] != key]
        if enabled:
            next_entry = enabled[0]
            state["active_fp"] = fingerprint(next_entry["key"])
            state["cursor"] = all_keys.index(next_entry["key"])
    else:
        record["cooldown_until"] = int(now + 20)
    state.setdefault("records", {})[fp] = record
    state["updated_at"] = int(now)
    _write_json(STATE_FILE, state)


def key_status_by_id(key_id: str) -> dict[str, Any]:
    item = next((item for item in key_statuses() if item["id"] == key_id), None)
    if not item:
        raise KeyError("key_not_found")
    return item


def key_statuses() -> list[dict[str, Any]]:
    entries = load_entries()
    keys = [entry["key"] for entry in entries]
    state = _sync_state(keys) if keys else {"records": {}, "active_fp": ""}
    records = state.get("records", {})
    active_fp = str(state.get("active_fp") or "")
    result: list[dict[str, Any]] = []
    for number, entry in enumerate(entries, start=1):
        key = entry["key"]
        fp = fingerprint(key)
        record = dict(records.get(fp) or {})
        result.append({
            "id": fp,
            "number": number,
            "label": entry.get("label") or f"المفتاح {number}",
            "masked": masked_key(key, number),
            "enabled": bool(entry.get("enabled", True)),
            "active": fp == active_fp and bool(entry.get("enabled", True)),
            "status": record.get("status", "untested"),
            "detail": record.get("detail", ""),
            "checked_at": record.get("checked_at"),
        })
    return result
