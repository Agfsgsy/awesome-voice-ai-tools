"""فهرسة الملفات الآمنة والرفع المجزأ القابل للاستئناف."""

from __future__ import annotations

import base64
import hmac
import json
import mimetypes
import os
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, ClassVar

from backend.core.config import OUTPUTS_DIR, UPLOADS_DIR
from backend.mobile.config import MOBILE_MAX_UPLOAD_MB, MOBILE_UPLOAD_STATE_FILE, MOBILE_UPLOADS_DIR
from backend.mobile.security import mobile_security


class MobileFileError(ValueError):
    """خطأ ملف متوقع يعاد للمستخدم برسالة واضحة."""


def _encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


class MobileFileStore:
    _scopes: ClassVar[dict[str, Path]] = {
        "output": OUTPUTS_DIR,
        "upload": UPLOADS_DIR,
        "mobile": MOBILE_UPLOADS_DIR,
    }

    def __init__(self) -> None:
        self._lock = threading.RLock()
        if not MOBILE_UPLOAD_STATE_FILE.exists():
            self._write_upload_state({"uploads": {}})

    def encode_file_id(self, scope: str, filename: str) -> str:
        if scope not in self._scopes:
            raise MobileFileError("نطاق الملف غير معروف")
        safe_name = Path(filename).name
        payload = _encode(json.dumps({"s": scope, "n": safe_name}, separators=(",", ":")).encode("utf-8"))
        return f"f1.{payload}.{mobile_security.sign(payload)}"

    def resolve_file_id(self, file_id: str) -> tuple[str, Path]:
        try:
            version, payload, signature = file_id.split(".", 2)
            if version != "f1" or not hmac.compare_digest(signature, mobile_security.sign(payload)):
                raise MobileFileError("معرّف الملف غير صالح")
            value = json.loads(_decode(payload).decode("utf-8"))
            scope = str(value["s"])
            filename = Path(str(value["n"])).name
            root = self._scopes[scope].resolve()
            path = (root / filename).resolve()
            if path.parent != root:
                raise MobileFileError("مسار الملف غير صالح")
        except MobileFileError:
            raise
        except Exception as exc:
            raise MobileFileError("معرّف الملف غير صالح") from exc
        if not path.is_file():
            raise MobileFileError("الملف غير موجود")
        return scope, path

    def metadata(self, scope: str, path: Path) -> dict[str, Any]:
        stat = path.stat()
        file_id = self.encode_file_id(scope, path.name)
        return {
            "file_id": file_id,
            "name": path.name,
            "size": stat.st_size,
            "modified_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
            "scope": scope,
            "mime_type": mimetypes.guess_type(path.name)[0] or "application/octet-stream",
            "download_url": f"/api/mobile/files/{file_id}",
        }

    def list_files(self) -> list[dict[str, Any]]:
        files: list[dict[str, Any]] = []
        for scope, root in self._scopes.items():
            if not root.exists():
                continue
            for path in root.iterdir():
                if (
                    path.is_file()
                    and path.resolve() != MOBILE_UPLOAD_STATE_FILE.resolve()
                    and not path.name.startswith(".")
                    and path.suffix != ".part"
                ):
                    files.append(self.metadata(scope, path))
        return sorted(files, key=lambda item: item["modified_at"], reverse=True)

    def delete(self, file_id: str) -> dict[str, Any]:
        _, path = self.resolve_file_id(file_id)
        if path.resolve() == MOBILE_UPLOAD_STATE_FILE.resolve():
            raise MobileFileError("ملف حالة النظام لا يمكن حذفه")
        name = path.name
        path.unlink()
        return {"success": True, "message": "تم حذف الملف", "name": name}

    def append_upload(
        self,
        *,
        upload_id: str,
        owner_device_id: str,
        filename: str,
        offset: int,
        total_size: int,
        chunk: bytes,
    ) -> dict[str, Any]:
        if not re.fullmatch(r"[A-Za-z0-9_-]{12,100}", upload_id):
            raise MobileFileError("معرّف الرفع غير صالح")
        if total_size <= 0 or total_size > MOBILE_MAX_UPLOAD_MB * 1024 * 1024:
            raise MobileFileError(f"حجم الملف يتجاوز الحد الأقصى ({MOBILE_MAX_UPLOAD_MB} ميجابايت)")
        if offset < 0 or offset > total_size:
            raise MobileFileError("موضع استئناف الرفع غير صالح")
        safe_name = Path(filename).name.strip()
        if not safe_name:
            raise MobileFileError("اسم الملف غير صالح")
        partial_path = MOBILE_UPLOADS_DIR / f"{upload_id}.part"

        with self._lock:
            state = self._read_upload_state()
            uploads = state.setdefault("uploads", {})
            entry = uploads.get(upload_id)
            if entry:
                if entry.get("owner_device_id") != owner_device_id:
                    raise MobileFileError("لا تملك صلاحية استئناف هذا الرفع")
                if int(entry.get("total_size", 0)) != total_size:
                    raise MobileFileError("حجم الملف لا يطابق جلسة الرفع")
                if entry.get("completed"):
                    return dict(entry)
            else:
                if offset != 0:
                    raise MobileFileError("جلسة الرفع غير موجودة؛ ابدأ من الصفر")
                entry = {
                    "upload_id": upload_id,
                    "owner_device_id": owner_device_id,
                    "filename": safe_name,
                    "total_size": total_size,
                    "next_offset": 0,
                    "completed": False,
                }
                uploads[upload_id] = entry

            current_size = partial_path.stat().st_size if partial_path.exists() else 0
            if offset < current_size:
                entry["next_offset"] = current_size
                self._write_upload_state(state)
                return dict(entry)
            if offset != current_size:
                raise MobileFileError(f"يجب استئناف الرفع من البايت {current_size}")
            if current_size + len(chunk) > total_size:
                raise MobileFileError("حجم الجزء يتجاوز الحجم المعلن للملف")

            mode = "ab" if partial_path.exists() else "wb"
            with partial_path.open(mode) as handle:
                handle.write(chunk)
                handle.flush()
                os.fsync(handle.fileno())

            next_offset = current_size + len(chunk)
            entry["next_offset"] = next_offset
            entry["updated_at"] = datetime.now(timezone.utc).isoformat()
            if next_offset == total_size:
                extension = Path(safe_name).suffix.lower()
                final_name = f"mobile_{upload_id}{extension}"
                final_path = MOBILE_UPLOADS_DIR / final_name
                os.replace(partial_path, final_path)
                entry.update(
                    {
                        "completed": True,
                        "file_id": self.encode_file_id("mobile", final_name),
                        "stored_name": final_name,
                        "message": "اكتمل رفع الملف",
                    }
                )
            else:
                entry["message"] = "تم حفظ الجزء ويمكن استئناف الرفع"
            self._write_upload_state(state)
            return dict(entry)

    def upload_status(self, upload_id: str, owner_device_id: str) -> dict[str, Any]:
        with self._lock:
            state = self._read_upload_state()
            entry = state.get("uploads", {}).get(upload_id)
            if not entry or entry.get("owner_device_id") != owner_device_id:
                raise MobileFileError("جلسة الرفع غير موجودة")
            return dict(entry)

    @staticmethod
    def _read_upload_state() -> dict[str, Any]:
        try:
            value = json.loads(MOBILE_UPLOAD_STATE_FILE.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {"uploads": {}}
        except (OSError, json.JSONDecodeError):
            return {"uploads": {}}

    @staticmethod
    def _write_upload_state(value: dict[str, Any]) -> None:
        MOBILE_UPLOAD_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        temporary = MOBILE_UPLOAD_STATE_FILE.with_suffix(".tmp")
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, MOBILE_UPLOAD_STATE_FILE)


mobile_file_store = MobileFileStore()
