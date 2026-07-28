"""Create the XTTS ready marker automatically when all downloaded files are valid."""
from __future__ import annotations

import importlib

finalizer = importlib.import_module("backend.api.voice_clone_98_finalize_patch")
resume = importlib.import_module("backend.api.voice_clone_download_resume_patch")
repair = importlib.import_module("backend.api.voice_clone_repair_runtime")


def _finalize_existing_download() -> None:
    if repair.MODEL_MARKER.exists():
        return
    model_dir = resume._model_dir()
    if not resume._model_complete(model_dir):
        return
    try:
        detail = finalizer._validate_downloaded_model(model_dir)
        resume._write_marker(model_dir, detail)
        resume._write_status(
            "ready",
            "اكتمل تنزيل نموذج XTTS وتم فحص ملفاته. المحرك جاهز، وسيُحمّل النموذج في الذاكرة عند أول استخدام.",
            100,
            downloaded_mb=round(resume._directory_bytes(model_dir) / (1024 * 1024), 1),
            phase="ready",
            resumable=True,
            model_dir=str(model_dir),
        )
    except Exception as exc:
        resume._write_status(
            "needs_model",
            "ملفات XTTS موجودة لكنها تحتاج استكمالًا أو إصلاحًا.",
            0,
            str(exc),
            downloaded_mb=round(resume._directory_bytes(model_dir) / (1024 * 1024), 1),
            resumable=True,
            model_dir=str(model_dir),
        )


_finalize_existing_download()
