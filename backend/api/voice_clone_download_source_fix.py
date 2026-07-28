"""Correct indentation when the resumable patch rewrites generated XTTS workers."""
from __future__ import annotations

from pathlib import Path

from backend.api import voice_clone_download_resume_patch as resume
from backend.api import voice_clone_routes as clone
from backend.api import voice_clone_xtts_runtime as xtts


def _patched_model_source(source: str, model_dir: Path) -> str:
    needle = 'model = TTS("tts_models/multilingual/multi-dataset/xtts_v2", progress_bar=False).to(device)'
    for indent in ("        ", "    "):
        old = indent + needle
        if old not in source:
            continue
        new = (
            indent
            + f"model_dir = Path({str(model_dir)!r})\n"
            + indent
            + "model = TTS(model_path=str(model_dir / 'model.pth'), "
            + "config_path=str(model_dir / 'config.json'), progress_bar=False).to(device)"
        )
        return source.replace(old, new)
    raise RuntimeError("تعذر ربط نموذج XTTS المحلي داخل ملف التشغيل المولد.")


resume._patched_model_source = _patched_model_source
clone._worker_source = resume._worker_source_resumable
xtts._server_source = resume._server_source_resumable
