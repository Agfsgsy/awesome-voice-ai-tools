"""Persistent Gemini API-key manager with real enable/disable and activation state."""
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
KEY_RE = re.compile(r"AIza[0-9A-Za-z_-]{20,}")
BLOCKED = {"quota", "invalid", "forbidden"}
DEFAULT_MODEL = "gemini-2.5-flash-preview-tts"
DEFAULT_VOICE = "Kore"


def _read(path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _write(path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def parse_keys(value: str | Iterable[str] | None) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, str):
        value = "\n".join(str(item) for item in value)
    raw = value.replace("\ufeff", " ").replace("`", " ").strip()
    found = KEY_RE.findall(raw)
    if not found:
        found = [part.strip("'\"[](){}<>،؛:") for part in re.split(r"[\s,;|]+", raw)]
    result: list[str] = []
    for key in found:
        key = str(key).strip()
        if len(key) >= 20 and not any(ch.isspace() for ch in key) and key not in result:
            result.append(key)
    return result


def fingerprint(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]


def masked_key(key: str, number: int | None = None) -> str:
    prefix = f"#{number} " if number is not None else ""
    return prefix + (f"{key[:4]}••••••{key[-4:]}" if len(key) >= 10 else "••••")


def load_config() -> dict[str, Any]:
    return _read(SETTINGS_FILE)


def _legacy_entries(data: dict[str, Any]) -> list[dict[str, Any]]:
    values: list[str] = []
    values.extend(parse_keys(data.get("api_keys") or []))
    values.extend(parse_keys(data.get("api_key") or ""))
    if not values:
        values.extend(parse_keys(os.getenv("GEMINI_API_KEYS", "")))
        values.extend(parse_keys(os.getenv("GEMINI_API_KEY", "")))
    return [{"key": key, "enabled": True, "label": f"المفتاح {index}", "added_at": int(time.time())} for index, key in enumerate(dict.fromkeys(values), start=1)]


def load_entries() -> list[dict[str, Any]]:
    data = load_config()
    raw = data.get("api_key_entries")
    if not isinstance(raw, list):
        return _legacy_entries(data)
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            continue
        keys = parse_keys(item.get("key") or "")
        if not keys or keys[0] in seen:
            continue
        key = keys[0]
        seen.add(key)
        result.append({"key": key, "enabled": bool(item.get("enabled", True)), "label": str(item.get("label") or f"المفتاح {index}")[:80], "added_at": int(item.get("added_at") or time.time())})
    return result or _legacy_entries(data)


def load_keys(enabled_only: bool = False) -> list[str]:
    return [item["key"] for item in load_entries() if not enabled_only or item.get("enabled", True)]


def _state(keys: list[str], save: bool = True) -> dict[str, Any]:
    previous = _read(STATE_FILE)
    ids = [fingerprint(key) for key in keys]
    old_records = previous.get("records") if isinstance(previous.get("records"), dict) else {}
    records = {key_id: old_records.get(key_id, {}) for key_id in ids}
    selected = str(previous.get("selected_fp") or previous.get("active_fp") or "")
    active = str(previous.get("active_fp") or "")
    if selected not in ids:
        selected = ids[0] if ids else ""
    if active not in ids or str((records.get(active) or {}).get("status")) != "working":
        active = ""
    value = {"selected_fp": selected, "active_fp": active, "records": records, "updated_at": int(time.time())}
    if save:
        _write(STATE_FILE, value)
    return value


def _save_entries(entries: list[dict[str, Any]], model_id: str | None = None, voice_name: str | None = None) -> None:
    previous = load_config()
    clean: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(entries, start=1):
        keys = parse_keys(item.get("key") if isinstance(item, dict) else item)
        if not keys or keys[0] in seen:
            continue
        key = keys[0]
        seen.add(key)
        clean.append({"key": key, "enabled": bool(item.get("enabled", True)) if isinstance(item, dict) else True, "label": str(item.get("label") or f"المفتاح {index}")[:80] if isinstance(item, dict) else f"المفتاح {index}", "added_at": int(item.get("added_at") or time.time()) if isinstance(item, dict) else int(time.time())})
    data = {"api_key_entries": clean, "api_keys": [item["key"] for item in clean], "model_id": model_id or str(previous.get("model_id") or DEFAULT_MODEL), "voice_name": voice_name or str(previous.get("voice_name") or DEFAULT_VOICE)}
    _write(SETTINGS_FILE, data)
    _state([item["key"] for item in clean])
    apply_environment(ordered_keys(), data["model_id"])


def save_config(keys: list[str] | list[dict[str, Any]], model_id: str, voice_name: str) -> None:
    entries = [item if isinstance(item, dict) else {"key": item, "enabled": True, "label": f"المفتاح {index}", "added_at": int(time.time())} for index, item in enumerate(keys, start=1)]
    _save_entries(entries, model_id, voice_name)


def append_keys(raw: str | Iterable[str], model_id: str, voice_name: str, replace: bool = False, label: str = "") -> list[str]:
    incoming = parse_keys(raw)
    entries = [] if replace else load_entries()
    by_key = {item["key"]: item for item in entries}
    for key in incoming:
        if key in by_key:
            by_key[key]["enabled"] = True
            if label:
                by_key[key]["label"] = label[:80]
        else:
            item = {"key": key, "enabled": True, "label": (label.strip() or f"المفتاح {len(entries) + 1}")[:80], "added_at": int(time.time())}
            entries.append(item)
            by_key[key] = item
    _save_entries(entries, model_id, voice_name)
    return [item["key"] for item in entries]


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


def _find(key_id: str) -> tuple[int, dict[str, Any]]:
    for index, item in enumerate(load_entries()):
        if fingerprint(item["key"]) == key_id:
            return index, item
    raise KeyError("key_not_found")


def set_key_enabled(key_id: str, enabled: bool) -> dict[str, Any]:
    entries = load_entries()
    index, _ = _find(key_id)
    entries[index]["enabled"] = bool(enabled)
    config = load_config()
    _save_entries(entries, str(config.get("model_id") or DEFAULT_MODEL), str(config.get("voice_name") or DEFAULT_VOICE))
    state = _state([item["key"] for item in entries])
    if not enabled:
        if state.get("selected_fp") == key_id:
            state["selected_fp"] = ""
        if state.get("active_fp") == key_id:
            state["active_fp"] = ""
    else:
        record = dict((state.get("records") or {}).get(key_id) or {})
        if record.get("status") in BLOCKED:
            record.update(status="untested", detail="تم تشغيل المفتاح ويحتاج اختبارًا صوتيًا.", checked_at=None)
            state.setdefault("records", {})[key_id] = record
    _write(STATE_FILE, state)
    apply_environment(ordered_keys(), str(config.get("model_id") or ""))
    return key_status_by_id(key_id)


def set_selected_key(key_id: str) -> dict[str, Any]:
    entries = load_entries()
    index, _ = _find(key_id)
    entries[index]["enabled"] = True
    config = load_config()
    _save_entries(entries, str(config.get("model_id") or DEFAULT_MODEL), str(config.get("voice_name") or DEFAULT_VOICE))
    state = _state([item["key"] for item in entries])
    state["selected_fp"] = key_id
    state["active_fp"] = key_id if str((state.get("records", {}).get(key_id) or {}).get("status")) == "working" else ""
    _write(STATE_FILE, state)
    apply_environment(ordered_keys(), str(config.get("model_id") or ""))
    return key_status_by_id(key_id)


set_active_key = set_selected_key


def delete_key(key_id: str) -> None:
    entries = load_entries()
    index, _ = _find(key_id)
    entries.pop(index)
    config = load_config()
    _save_entries(entries, str(config.get("model_id") or DEFAULT_MODEL), str(config.get("voice_name") or DEFAULT_VOICE))
    state = _state([item["key"] for item in entries])
    if state.get("selected_fp") == key_id:
        state["selected_fp"] = ""
    if state.get("active_fp") == key_id:
        state["active_fp"] = ""
    _write(STATE_FILE, state)
    apply_environment(ordered_keys(), str(config.get("model_id") or ""))


def ordered_keys() -> list[str]:
    entries = [item for item in load_entries() if item.get("enabled", True)]
    if not entries:
        return []
    all_keys = [item["key"] for item in load_entries()]
    state = _state(all_keys)
    records = state.get("records", {})
    selected_id = str(state.get("selected_fp") or "")
    selected = next((item for item in entries if fingerprint(item["key"]) == selected_id), None)
    ordered = ([selected] if selected else []) + [item for item in entries if item is not selected]
    return [item["key"] for item in ordered if str((records.get(fingerprint(item["key"])) or {}).get("status") or "untested") not in BLOCKED]


def record_result(key: str, status: str, detail: str = "") -> None:
    entries = load_entries()
    keys = [item["key"] for item in entries]
    if key not in keys:
        return
    if status == "working" and detail.startswith("Text model:"):
        status = "text_working"
    state = _state(keys)
    key_id = fingerprint(key)
    record = dict((state.get("records") or {}).get(key_id) or {})
    now = int(time.time())
    if status == "text_working":
        record.update(text_status="working", text_detail=detail[:500], text_checked_at=now)
        record.setdefault("status", "untested")
        state.setdefault("records", {})[key_id] = record
        _write(STATE_FILE, state)
        return
    record.update(status=status, detail=detail[:500], checked_at=now)
    state.setdefault("records", {})[key_id] = record
    if status == "working":
        state["selected_fp"] = key_id
        state["active_fp"] = key_id
    else:
        if state.get("active_fp") == key_id:
            state["active_fp"] = ""
        if status in BLOCKED:
            replacement = next((item for item in entries if item.get("enabled", True) and item["key"] != key and str((state.get("records", {}).get(fingerprint(item["key"])) or {}).get("status")) == "working"), None)
            if replacement:
                replacement_id = fingerprint(replacement["key"])
                state["selected_fp"] = replacement_id
                state["active_fp"] = replacement_id
            elif state.get("selected_fp") == key_id:
                state["selected_fp"] = ""
    _write(STATE_FILE, state)
    apply_environment(ordered_keys(), str(load_config().get("model_id") or ""))


def key_status_by_id(key_id: str) -> dict[str, Any]:
    item = next((item for item in key_statuses() if item["id"] == key_id), None)
    if not item:
        raise KeyError("key_not_found")
    return item


def key_statuses() -> list[dict[str, Any]]:
    entries = load_entries()
    keys = [item["key"] for item in entries]
    state = _state(keys) if keys else {"records": {}, "selected_fp": "", "active_fp": ""}
    records = state.get("records", {})
    result: list[dict[str, Any]] = []
    for number, item in enumerate(entries, start=1):
        key = item["key"]
        key_id = fingerprint(key)
        record = dict(records.get(key_id) or {})
        status = str(record.get("status") or "untested")
        enabled = bool(item.get("enabled", True))
        working = status == "working"
        result.append({"id": key_id, "number": number, "label": item.get("label") or f"المفتاح {number}", "masked": masked_key(key, number), "enabled": enabled, "selected": key_id == state.get("selected_fp") and enabled, "active": key_id == state.get("active_fp") and enabled and working, "usable": enabled and status not in BLOCKED, "working": working, "status": status, "detail": record.get("detail", ""), "checked_at": record.get("checked_at"), "text_status": record.get("text_status", "untested"), "text_detail": record.get("text_detail", ""), "text_checked_at": record.get("text_checked_at"), "added_at": item.get("added_at")})
    return result
