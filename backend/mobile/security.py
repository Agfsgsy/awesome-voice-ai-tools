"""اقتران الأجهزة وإصدار رموز وصول قصيرة العمر دون اعتماد خارجي."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import os
import secrets
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from backend.mobile.config import (
    MOBILE_ACCESS_TOKEN_SECONDS,
    MOBILE_DEVICES_FILE,
    MOBILE_PAIRING_FILE,
    MOBILE_PAIRING_TTL_SECONDS,
    MOBILE_SECRET_FILE,
    MOBILE_SHARE_TOKEN_SECONDS,
)


class MobileSecurityError(ValueError):
    """خطأ مصادقة آمن يمكن تحويله إلى رسالة عربية واضحة."""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, timezone.utc).isoformat()


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


class MobileSecurity:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._secret = self._load_or_create_secret()
        self._ensure_json_file(MOBILE_DEVICES_FILE, {"devices": {}})
        self._ensure_json_file(MOBILE_PAIRING_FILE, {"sessions": {}})

    @staticmethod
    def _ensure_json_file(path: Path, default: dict[str, Any]) -> None:
        if path.exists():
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(default, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, path)

    @staticmethod
    def _read_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else default
        except (OSError, json.JSONDecodeError):
            return default

    @staticmethod
    def _write_json(path: Path, value: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, path)

    @staticmethod
    def _load_or_create_secret() -> bytes:
        if MOBILE_SECRET_FILE.exists():
            raw = MOBILE_SECRET_FILE.read_bytes().strip()
            try:
                decoded = base64.urlsafe_b64decode(raw)
            except Exception as exc:
                raise RuntimeError("ملف سر خادم الجوال غير صالح") from exc
            if len(decoded) < 32:
                raise RuntimeError("سر خادم الجوال أقصر من الحد الآمن")
            return decoded
        secret = secrets.token_bytes(48)
        MOBILE_SECRET_FILE.parent.mkdir(parents=True, exist_ok=True)
        MOBILE_SECRET_FILE.write_bytes(base64.urlsafe_b64encode(secret))
        try:
            MOBILE_SECRET_FILE.chmod(0o600)
        except OSError:
            # أنظمة Windows لا تطبق صلاحيات POSIX؛ يبقى الملف داخل مجلد بيانات خاص.
            os.stat(MOBILE_SECRET_FILE)
        return secret

    def sign(self, value: str) -> str:
        return _b64encode(hmac.new(self._secret, value.encode("utf-8"), hashlib.sha256).digest())

    def create_pairing_session(self, server_url: str) -> dict[str, Any]:
        normalized_url = server_url.strip().rstrip("/")
        if not normalized_url.startswith(("http://", "https://")):
            raise MobileSecurityError("عنوان الخادم يجب أن يبدأ بـ http:// أو https://")
        now = time.time()
        pairing_id = str(uuid.uuid4())
        code = "-".join("".join(secrets.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(4)) for _ in range(2))
        record = {
            "pairing_id": pairing_id,
            "code_hash": self._hash_secret(code),
            "server_url": normalized_url,
            "created_at": _iso(now),
            "expires_at": now + MOBILE_PAIRING_TTL_SECONDS,
            "used": False,
        }
        with self._lock:
            data = self._read_json(MOBILE_PAIRING_FILE, {"sessions": {}})
            sessions = data.setdefault("sessions", {})
            sessions = {
                key: item
                for key, item in sessions.items()
                if float(item.get("expires_at", 0)) > now and not item.get("used", False)
            }
            sessions[pairing_id] = record
            data["sessions"] = sessions
            self._write_json(MOBILE_PAIRING_FILE, data)
        query = urlencode({"server": normalized_url, "id": pairing_id, "code": code})
        return {
            "pairing_id": pairing_id,
            "pairing_code": code,
            "server_url": normalized_url,
            "expires_at": _iso(record["expires_at"]),
            "expires_in": MOBILE_PAIRING_TTL_SECONDS,
            "qr_payload": f"voiceai://pair?{query}",
        }

    def pair_device(
        self,
        pairing_id: str,
        code: str,
        device_name: str,
        platform_name: str,
        app_version: str,
    ) -> dict[str, Any]:
        now = time.time()
        with self._lock:
            data = self._read_json(MOBILE_PAIRING_FILE, {"sessions": {}})
            sessions = data.setdefault("sessions", {})
            session = sessions.get(pairing_id)
            if not session:
                raise MobileSecurityError("انتهت صلاحية جلسة الاقتران")
            if session.get("used") or float(session.get("expires_at", 0)) <= now:
                sessions.pop(pairing_id, None)
                self._write_json(MOBILE_PAIRING_FILE, data)
                raise MobileSecurityError("انتهت صلاحية جلسة الاقتران")
            if not hmac.compare_digest(str(session.get("code_hash", "")), self._hash_secret(code.strip().upper())):
                raise MobileSecurityError("رمز الاقتران غير صحيح")

            device_id = str(uuid.uuid4())
            device_token = secrets.token_urlsafe(48)
            devices_data = self._read_json(MOBILE_DEVICES_FILE, {"devices": {}})
            devices = devices_data.setdefault("devices", {})
            devices[device_id] = {
                "device_id": device_id,
                "name": (device_name.strip() or "هاتف غير مسمى")[:120],
                "platform": platform_name.strip()[:60],
                "app_version": app_version.strip()[:40],
                "token_hash": self._hash_secret(device_token),
                "paired_at": _utc_now().isoformat(),
                "last_seen_at": _utc_now().isoformat(),
                "revoked": False,
            }
            session["used"] = True
            sessions.pop(pairing_id, None)
            self._write_json(MOBILE_DEVICES_FILE, devices_data)
            self._write_json(MOBILE_PAIRING_FILE, data)

        return {
            "device_id": device_id,
            "device_token": device_token,
            "server_url": session["server_url"],
        }

    def authenticate_device(self, device_id: str, device_token: str) -> dict[str, Any]:
        with self._lock:
            data = self._read_json(MOBILE_DEVICES_FILE, {"devices": {}})
            device = data.get("devices", {}).get(device_id)
            if not device or device.get("revoked"):
                raise MobileSecurityError("هذا الجهاز غير مقترن أو تم إلغاء اقترانه")
            if not hmac.compare_digest(str(device.get("token_hash", "")), self._hash_secret(device_token)):
                raise MobileSecurityError("بيانات الجهاز غير صحيحة")
            device["last_seen_at"] = _utc_now().isoformat()
            self._write_json(MOBILE_DEVICES_FILE, data)
        return self._issue_access_token(device_id)

    def _issue_access_token(self, device_id: str) -> dict[str, Any]:
        now = int(time.time())
        payload = {
            "sub": device_id,
            "iat": now,
            "exp": now + MOBILE_ACCESS_TOKEN_SECONDS,
            "jti": secrets.token_hex(12),
            "scope": "mobile",
        }
        encoded_payload = _b64encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
        signature = self.sign(encoded_payload)
        return {
            "access_token": f"v1.{encoded_payload}.{signature}",
            "token_type": "bearer",
            "expires_in": MOBILE_ACCESS_TOKEN_SECONDS,
            "expires_at": _iso(payload["exp"]),
        }

    def verify_access_token(self, token: str) -> str:
        try:
            version, encoded_payload, signature = token.split(".", 2)
            if version != "v1" or not hmac.compare_digest(signature, self.sign(encoded_payload)):
                raise MobileSecurityError("جلسة الدخول غير صالحة")
            payload = json.loads(_b64decode(encoded_payload).decode("utf-8"))
            if int(payload.get("exp", 0)) <= int(time.time()):
                raise MobileSecurityError("انتهت جلسة الدخول؛ أعد الاتصال")
            device_id = str(payload.get("sub", ""))
        except MobileSecurityError:
            raise
        except Exception as exc:
            raise MobileSecurityError("جلسة الدخول غير صالحة") from exc

        with self._lock:
            data = self._read_json(MOBILE_DEVICES_FILE, {"devices": {}})
            device = data.get("devices", {}).get(device_id)
            if not device or device.get("revoked"):
                raise MobileSecurityError("تم إلغاء اقتران هذا الجهاز")
        return device_id

    def create_share_token(self, file_id: str) -> str:
        payload = {
            "file_id": file_id,
            "exp": int(time.time()) + MOBILE_SHARE_TOKEN_SECONDS,
            "nonce": secrets.token_hex(8),
        }
        encoded = _b64encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
        return f"s1.{encoded}.{self.sign(encoded)}"

    def verify_share_token(self, token: str, file_id: str) -> bool:
        try:
            version, encoded, signature = token.split(".", 2)
            if version != "s1" or not hmac.compare_digest(signature, self.sign(encoded)):
                return False
            payload = json.loads(_b64decode(encoded).decode("utf-8"))
            return payload.get("file_id") == file_id and int(payload.get("exp", 0)) > int(time.time())
        except (ValueError, TypeError, UnicodeDecodeError, binascii.Error):
            return False

    def list_devices(self) -> list[dict[str, Any]]:
        with self._lock:
            data = self._read_json(MOBILE_DEVICES_FILE, {"devices": {}})
        result = []
        for item in data.get("devices", {}).values():
            public_item = {key: value for key, value in item.items() if key != "token_hash"}
            result.append(public_item)
        return sorted(result, key=lambda item: str(item.get("paired_at", "")), reverse=True)

    def revoke_device(self, device_id: str) -> bool:
        with self._lock:
            data = self._read_json(MOBILE_DEVICES_FILE, {"devices": {}})
            device = data.get("devices", {}).get(device_id)
            if not device:
                return False
            device["revoked"] = True
            device["revoked_at"] = _utc_now().isoformat()
            self._write_json(MOBILE_DEVICES_FILE, data)
        return True

    def _hash_secret(self, value: str) -> str:
        return hmac.new(self._secret, value.encode("utf-8"), hashlib.sha256).hexdigest()


mobile_security = MobileSecurity()
