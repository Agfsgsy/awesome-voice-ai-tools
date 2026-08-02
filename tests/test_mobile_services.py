"""اختبارات خدمات الجوال المستقلة عن واجهة Flutter."""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

import pytest

import backend.mobile.security as security_module
from backend.mobile.documents import normalize_text_for_speech
from backend.mobile.jobs import MobileJobManager
from backend.mobile.security import MobileSecurityError, mobile_security


def test_expired_pairing_session_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    session = mobile_security.create_pairing_session("http://192.168.1.10:8000")
    current_time = time.time()
    monkeypatch.setattr(security_module.time, "time", lambda: current_time + session["expires_in"] + 1)
    with pytest.raises(MobileSecurityError, match="انتهت صلاحية جلسة الاقتران"):
        mobile_security.pair_device(
            session["pairing_id"],
            session["pairing_code"],
            "هاتف منتهي",
            "android",
            "1.0.0",
        )


def test_arabic_numbers_dates_and_currency_are_normalized() -> None:
    result = normalize_text_for_speech("المبلغ 125 SAR وتاريخ الاستحقاق 2026-08-15")
    assert "ريال سعودي" in result
    assert "أغسطس" in result
    assert "125" not in result
    assert "2026" not in result


@pytest.mark.asyncio
async def test_job_can_be_cancelled_and_persisted(tmp_path: Path) -> None:
    state_file = tmp_path / "jobs.json"
    manager = MobileJobManager(state_file)

    async def runner(context):
        for progress in range(5, 100, 5):
            await context.update(progress, "جارٍ تنفيذ اختبار طويل")
            await asyncio.sleep(0.01)
        return {"success": True}

    job = await manager.create("test_long_job", "device-test", runner)
    await asyncio.sleep(0.025)
    cancelled = await manager.cancel(job.job_id, "device-test")
    assert cancelled.cancel_requested is True

    for _ in range(100):
        current = manager.get(job.job_id, "device-test")
        if current.status == "cancelled":
            break
        await asyncio.sleep(0.01)
    assert current.status == "cancelled"
    persisted = json.loads(state_file.read_text(encoding="utf-8"))
    assert persisted["jobs"][0]["status"] == "cancelled"


def test_file_id_signature_cannot_be_tampered_with(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from backend.mobile.files import MobileFileError, MobileFileStore

    store = MobileFileStore()
    monkeypatch.setitem(store._scopes, "mobile", tmp_path)
    audio = tmp_path / "safe.wav"
    audio.write_bytes(b"RIFF-safe-test")
    file_id = store.encode_file_id("mobile", audio.name)
    assert store.resolve_file_id(file_id)[1] == audio
    altered = file_id[:-1] + ("A" if file_id[-1] != "A" else "B")
    with pytest.raises(MobileFileError, match="معرّف الملف غير صالح"):
        store.resolve_file_id(altered)
