"""مدير مهام طويلة قابل للمتابعة والإلغاء من تطبيق الجوال."""

from __future__ import annotations

import asyncio
import json
import os
import threading
import uuid
from collections.abc import Awaitable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from backend.mobile.config import MOBILE_JOBS_FILE


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class JobCancelledError(RuntimeError):
    """يرفعه المنفذ عندما يطلب المستخدم إلغاء المهمة."""


@dataclass
class MobileJob:
    job_id: str
    kind: str
    owner_device_id: str
    status: str = "queued"
    progress: int = 0
    message: str = "تمت إضافة المهمة إلى قائمة الانتظار"
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)
    cancel_requested: bool = False

    def to_dict(self, include_owner: bool = False) -> dict[str, Any]:
        value = {
            "job_id": self.job_id,
            "kind": self.kind,
            "status": self.status,
            "progress": self.progress,
            "message": self.message,
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "cancel_requested": self.cancel_requested,
            "can_cancel": self.status in {"queued", "running"},
        }
        if include_owner:
            value["owner_device_id"] = self.owner_device_id
        return value


class JobContext:
    def __init__(self, manager: MobileJobManager, job_id: str) -> None:
        self._manager = manager
        self.job_id = job_id

    async def update(self, progress: int, message: str) -> None:
        await self._manager.update(self.job_id, progress=progress, message=message)
        self.raise_if_cancelled()

    def raise_if_cancelled(self) -> None:
        job = self._manager.get_unscoped(self.job_id)
        if job.cancel_requested:
            raise JobCancelledError("المهمة أُلغيت")


Runner = Callable[[JobContext], Awaitable[dict[str, Any]]]


class MobileJobManager:
    def __init__(self, state_file: Path = MOBILE_JOBS_FILE) -> None:
        self._state_file = state_file
        self._lock = threading.RLock()
        self._jobs: dict[str, MobileJob] = {}
        self._tasks: dict[str, asyncio.Task[Any]] = {}
        self._load_state()

    def _load_state(self) -> None:
        if not self._state_file.exists():
            return
        try:
            raw = json.loads(self._state_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        for item in raw.get("jobs", []):
            if item.get("status") in {"queued", "running"}:
                item["status"] = "failed"
                item["error"] = "توقفت المهمة بسبب إعادة تشغيل الخادم"
                item["message"] = item["error"]
            try:
                job = MobileJob(**{key: value for key, value in item.items() if key in MobileJob.__dataclass_fields__})
                self._jobs[job.job_id] = job
            except TypeError:
                continue
        self._persist()

    def _persist(self) -> None:
        self._state_file.parent.mkdir(parents=True, exist_ok=True)
        temporary = self._state_file.with_suffix(".tmp")
        payload = {"jobs": [job.to_dict(include_owner=True) for job in self._jobs.values()]}
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, self._state_file)

    async def create(self, kind: str, owner_device_id: str, runner: Runner) -> MobileJob:
        job = MobileJob(job_id=str(uuid.uuid4()), kind=kind, owner_device_id=owner_device_id)
        with self._lock:
            self._jobs[job.job_id] = job
            self._persist()
        self._tasks[job.job_id] = asyncio.create_task(self._run(job.job_id, runner), name=f"mobile-job-{job.job_id}")
        return job

    async def _run(self, job_id: str, runner: Runner) -> None:
        await self.update(job_id, status="running", progress=1, message="بدأ تنفيذ المهمة")
        try:
            result = await runner(JobContext(self, job_id))
            job = self.get_unscoped(job_id)
            if job.cancel_requested:
                raise JobCancelledError("المهمة أُلغيت")
            await self.update(
                job_id,
                status="completed",
                progress=100,
                message="اكتملت المهمة بنجاح",
                result=result,
            )
        except (JobCancelledError, asyncio.CancelledError):
            await self.update(
                job_id,
                status="cancelled",
                message="المهمة أُلغيت",
                error="المهمة أُلغيت",
            )
        # حدود تنفيذ المهام يجب أن تحوّل أخطاء المحركات الخارجية غير المتوقعة إلى حالة قابلة للعرض.
        except Exception as exc:  # noqa: BLE001
            await self.update(
                job_id,
                status="failed",
                message=str(exc) or "فشلت المهمة",
                error=str(exc) or "فشلت المهمة",
            )
        finally:
            self._tasks.pop(job_id, None)

    async def update(self, job_id: str, **changes: Any) -> MobileJob:
        with self._lock:
            job = self.get_unscoped(job_id)
            for key, value in changes.items():
                if hasattr(job, key) and value is not None:
                    setattr(job, key, value)
            job.progress = max(0, min(100, int(job.progress)))
            job.updated_at = _now_iso()
            self._persist()
        return job

    def get(self, job_id: str, owner_device_id: str) -> MobileJob:
        job = self.get_unscoped(job_id)
        if job.owner_device_id != owner_device_id:
            raise KeyError(job_id)
        return job

    def get_unscoped(self, job_id: str) -> MobileJob:
        job = self._jobs.get(job_id)
        if job is None:
            raise KeyError(job_id)
        return job

    async def cancel(self, job_id: str, owner_device_id: str) -> MobileJob:
        with self._lock:
            job = self.get(job_id, owner_device_id)
            if job.status not in {"queued", "running"}:
                return job
            job.cancel_requested = True
            job.message = "جارٍ إلغاء المهمة"
            job.updated_at = _now_iso()
            self._persist()
        task = self._tasks.get(job_id)
        if task and not task.done():
            task.cancel()
        return job


mobile_job_manager = MobileJobManager()
