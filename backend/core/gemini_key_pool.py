"""Persistent Gemini API-key manager with real per-key control.

Full keys are stored only in the local app config. API responses expose masked values
and stable fingerprints. A key is reported as active only after a successful real TTS
test. Disabled, exhausted, invalid, or forbidden keys are never sent to Gemini.
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
BLOCKED_STATUSES = {"quota", "invalid", "forbidden"}
DEFAULT_MODEL = "gemini-2.5-flash-preview-tts"
DEFAULT_VOICE = "Kore"


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
    entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    raw_entries = data.get("api_key_entries")
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


def _state_for_keys(keys: list[str]) -> dict[str, Any]:
    old = _read_json(STATE_FILE)
    fps = [fingerprint(key) for key in keys]
    records = old.get("records") if isinstance(old.get("records"), dict) else {}
    records = {fp: records.get(fp, {}) for fp in fps}
    selected_fp = str(old.get("selected_fp") or old.get("active_fp") or "")
    active_fp = str(old.get("active_fp") or "")
    if selected_fp not in fps:
        selected_fp = fps[0] if fps else ""
    if active_fp not in fps:
        active_fp = ""
    if active_fp and str((records.get(active_fp) or {}).get("status")) != "working":
        active_fp = ""
    return {"selected_fp": selected_fp, "active_fp": active_fp, "records": records, "updated_at": int(time.time())}


def _save_state(state: dict[str, Any]) -> None:
    state["updated_at"] = int(time.time())
    _write_json(STATE_FILE, state)


def _sync_state(keys: list[str]) -> dict[str, Any]:
    state = _state_for_keys(keys)
    _save_state(state)
    return state


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
        "model_id": model_id or str(previous.get("model_id") or DEFAULT_MODEL),
        "voice_name": voice_name or str(previous.get("voice_name") or DEFAULT_VOICE),
    }
    _write_json(SETTINGS_FILE, data)
    _sync_state([entry["key"] for entry in cleaned])
    apply_environment(ordered_keys(), data["model_id"])


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
        entry = {"key": key, "enabled": True, "label": (label.strip() or f"المفتاح {len(entries) + 1}")[:80], "added_at": int(time.time())}
        entries.append(entry)
        by_key[key] = entry
    _save_entries(entries, model_id, voice_name)
    state = _sync_state([entry["key"] for entry in entries])
    if entries and not state.get("selected_fp"):
        state["selected_fp"] = fingerprint(entries[0]["key"])
        _save_state(state)
    return [entry["key"] for entry in entries]


def apply_environment(keys: list[str] | None = None, model_id: str | None = None) -> None:
    keys = list(keys if keys is not None else ordered_keys())
    if keys:
        os.environ["GEMINI_API_KEYS"] = "||".join(keys)
        os.environ["GEMINI_API_KEY"] = keys[0]
    else:
        os.environ.pop("GEMINI_API_KEYS", None)
        os.environ.pop("GEMINI_API_KEY", None)
    if model_id:
        os.environ["GEMINI_TTS_MODEL"] = model_id


def _entry_by_id(key_id: str) -> tuple[int, dict[str, Any]]:
    entries = load_entries()
    for index, entry in enumerate(entries):
        if fingerprint(entry["key"]) == key_id:
            return index, entry
    raise KeyError("key_not_found")


def set_key_enabled(key_id: str, enabled: bool) -> dict[str, Any]:
    entries = load_entries()
    index, _ = _entry_by_id(key_id)
    entries[index]["enabled"] = bool(enabled)
    data = load_config()
    _save_entries(entries, str(data.get("model_id") or DEFAULT_MODEL), str(data.get("voice_name") or DEFAULT_VOICE))
    keys = [entry["key"] for entry in entries]
    state = _sync_state(keys)
    if not enabled:
        if state.get("selected_fp") == key_id:
            state["selected_fp"] = ""
        if state.get("active_fp") == key_id:
            state["active_fp"] = ""
    else:
        record = dict((state.get("records") or {}).get(key_id) or {})
        if record.get("status") in BLOCKED_STATUSES:
            record["status"] = "untested"
            record["detail"] = "تم تشغيل المفتاح ويحتاج اختبارًا صوتيًا."
            record["checked_at"] = None
            state.setdefault("records", {})[key_id] = record
    _save_state(state)
    apply_environment(ordered_keys(), str(data.get("model_id") or ""))
    return key_status_by_id(key_id)


def set_selected_key(key_id: str) -> dict[str, Any]:
    entries = load_entries()
    index, _ = _entry_by_id(key_id)
    entries[index]["enabled"] = True
    data = load_config()
    _save_entries(entries, str(data.get("model_id") or DEFAULT_MODEL), str(data.get("voice_name") or DEFAULT_VOICE))
    state = _sync_state([entry["key"] for entry in entries])
    state["selected_fp"] = key_id
    record = dict((state.get("records") or {}).get(key_id) or {})
    state["active_fp"] = key_id if record.get("status") == "working" else ""
    _save_state(state)
    apply_environment(ordered_keys(), str(data.get("model_id") or ""))
    return key_status_by_id(key_id)


set_active_key = set_selected_key


def delete_key(key_id: str) -> None:
    entries = load_entries()
    index, _ = _entry_by_id(key_id)
    entries.pop(index)
    data = load_config()
    _save_entries(entries, str(data.get("model_id") or DEFAULT_MODEL), str(data.get("voice_name") or DEFAULT_VOICE))
    state = _sync_state([entry["key"] for entry in entries])
    if state.get("selected_fp") == key_id:
        state["selected_fp"] = ""
    if state.get("active_fp") == key_id:
        state["active_fp"] = ""
    _save_state(state)
    apply_environment(ordered_keys(), str(data.get("model_id") or ""))


def ordered_keys() -> list[str]:
    entries = [entry for entry in load_entries() if entry.get("enabled", True)]
    if not entries:
        return []
    all_entries = load_entries()
    all_keys = [entry["key"] for entry in all_entries]
    state = _sync_state(all_keys)
    selected_fp = str(state.get("selected_fp") or "")
    records = state.get("records", {})
    selected = next((entry for entry in entries if fingerprint(entry["key"]) == selected_fp), None)
    remaining = [entry for entry in entries if entry is not selected]
    ordered_entries = ([selected] if selected else []) + remaining
    eligible: list[str] = []
    for entry in ordered_entries:
        key = entry["key"]
        status = str((records.get(fingerprint(key)) or {}).get("status") or "untested")
        if status in BLOCKED_STATUSES:
            continue
        eligible.append(key)
    return eligible


def record_result(key: str, status: str, detail: str = "") -> None:
    entries = load_entries()
    all_keys = [entry["key"] for entry in entries]
    if key not in all_keys:
        return
    state = _sync_state(all_keys)
    fp = fingerprint(key)
    record = dict((state.get("records") or {}).get(fp) or {})
    record.update({"status": status, "detail": detail[:500], "checked_at": int(time.time())})
    state.setdefault("records", {})[fp] = record
    if status == "working":
        state["selected_fp"] = fp
        state["active_fp"] = fp
    else:
        if state.get("active_fp") == fp:
            state["active_fp"] = ""
        if status in BLOCKED_STATUSES:
            next_working = next((entry for entry in entries if entry.get("enabled", True) and entry["key"] != key and str((state.get("records", {}).get(fingerprint(entry["key"])) or {}).get("status")) == "working"), None)
            if next_working:
                next_fp = fingerprint(next_working["key"])
                state["selected_fp"] = next_fp
                state["active_fp"] = next_fp
            elif state.get("selected_fp") == fp:
                state["selected_fp"] = ""
    _save_state(state)
    data = load_config()
    apply_environment(ordered_keys(), str(data.get("model_id") or ""))


def key_status_by_id(key_id: str) -> dict[str, Any]:
    item = next((item for item in key_statuses() if item["id"] == key_id), None)
    if not item:
        raise KeyError("key_not_found")
    return item


def key_statuses() -> list[dict[str, Any]]:
    entries = load_entries()
    keys = [entry["key"] for entry in entries]
    state = _sync_state(keys) if keys else {"records": {}, "selected_fp": "", "active_fp": ""}
    records = state.get("records", {})
    selected_fp = str(state.get("selected_fp") or "")
    active_fp = str(state.get("active_fp") or "")
    result: list[dict[str, Any]] = []
    for number, entry in enumerate(entries, start=1):
        key = entry["key"]
        fp = fingerprint(key)
        record = dict(records.get(fp) or {})
        status = str(record.get("status") or "untested")
        enabled = bool(entry.get("enabled", True))
        working = status == "working"
        result.append({
            "id": fp,
            "number": number,
            "label": entry.get("label") or f"المفتاح {number}",
            "masked": masked_key(key, number),
            "enabled": enabled,
            "selected": fp == selected_fp and enabled,
            "active": fp == active_fp and enabled and working,
            "usable": enabled and status not in BLOCKED_STATUSES,
            "working": working,
            "status": status,
            "detail": record.get("detail", ""),
            "checked_at": record.get("checked_at"),
            "added_at": entry.get("added_at"),
        })
    return result
