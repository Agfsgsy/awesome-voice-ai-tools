"""Finish downloaded XTTS models quickly and avoid low-VRAM GPU stalls.

This additive patch preserves every profile, consent record, sample, partial model file,
generated audio file and existing interface. It changes only two runtime details:
1. setup validates the already-downloaded XTTS files without loading the 2 GB model;
2. the persistent worker uses CPU on GPUs with less than 6 GB VRAM.
"""
from __future__ import annotations

import importlib
import json
import os
import zipfile
from pathlib import Path
from typing import Any

resume = importlib.import_module("backend.api.voice_clone_download_resume_patch")
clone = importlib.import_module("backend.api.voice_clone_routes")
xtts = importlib.import_module("backend.api.voice_clone_xtts_runtime")

_ORIGINAL_RUN_SETUP = resume._run_resumable_model_setup
_ORIGINAL_SERVER_SOURCE = xtts._server_source


def _validate_downloaded_model(model_dir: Path) -> str:
    model = model_dir / "model.pth"
    config = model_dir / "config.json"
    vocab = model_dir / "vocab.json"
    missing = [path.name for path in (model, config, vocab) if not path.exists()]
    if missing:
        raise RuntimeError("XTTS download is incomplete; missing: " + ", ".join(missing))
    if model.stat().st_size < 500_000_000:
        raise RuntimeError("XTTS model.pth is incomplete.")
    if config.stat().st_size < 500 or vocab.stat().st_size < 10_000:
        raise RuntimeError("XTTS configuration files are incomplete.")
    try:
        parsed_config: dict[str, Any] = json.loads(config.read_text(encoding="utf-8"))
        json.loads(vocab.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RuntimeError(f"XTTS configuration validation failed: {type(exc).__name__}: {exc}") from exc
    if not isinstance(parsed_config, dict) or not parsed_config:
        raise RuntimeError("XTTS config.json is empty or invalid.")
    if zipfile.is_zipfile(model):
        try:
            with zipfile.ZipFile(model) as archive:
                if not archive.namelist():
                    raise RuntimeError("XTTS model archive is empty.")
        except Exception as exc:
            raise RuntimeError(f"XTTS model archive validation failed: {exc}") from exc
    size_mb = round(sum(path.stat().st_size for path in (model, config, vocab)) / (1024 * 1024), 1)
    return f"XTTS files validated without loading the full model ({size_mb} MB core files)."


def _light_download_worker_source(model_dir: Path) -> str:
    return f'''from __future__ import annotations
import json
import os
import zipfile
from pathlib import Path

model_dir = Path({str(model_dir)!r})
model_dir.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("COQUI_TOS_AGREED", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
os.environ.setdefault("HF_HUB_ETAG_TIMEOUT", "30")
os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "300")
os.environ["TTS_HOME"] = str(model_dir.parent)

from huggingface_hub import snapshot_download
kwargs = {{
    "repo_id": "coqui/XTTS-v2",
    "local_dir": str(model_dir),
    "max_workers": 2,
}}
try:
    snapshot_download(local_dir_use_symlinks=False, resume_download=True, **kwargs)
except TypeError:
    snapshot_download(**kwargs)

model = model_dir / "model.pth"
config = model_dir / "config.json"
vocab = model_dir / "vocab.json"
missing = [path.name for path in (model, config, vocab) if not path.exists()]
if missing:
    raise RuntimeError("XTTS download incomplete; missing: " + ", ".join(missing))
if model.stat().st_size < 500_000_000:
    raise RuntimeError("XTTS model.pth is incomplete")
if config.stat().st_size < 500 or vocab.stat().st_size < 10_000:
    raise RuntimeError("XTTS config files are incomplete")
json.loads(config.read_text(encoding="utf-8"))
json.loads(vocab.read_text(encoding="utf-8"))
if zipfile.is_zipfile(model):
    with zipfile.ZipFile(model) as archive:
        if not archive.namelist():
            raise RuntimeError("XTTS model archive is empty")
print(json.dumps({{"ready": True, "model_dir": str(model_dir), "validation": "files_only"}}, ensure_ascii=False))
'''


def _run_setup_without_heavy_load(python: str) -> tuple[Path, str]:
    model_dir = resume._model_dir()
    if resume._model_complete(model_dir):
        try:
            detail = _validate_downloaded_model(model_dir)
            resume._write_status(
                "installing",
                "اكتمل تنزيل XTTS. تم فحص الملفات بنجاح، وجاري إنهاء التجهيز...",
                99,
                downloaded_mb=round(resume._directory_bytes(model_dir) / (1024 * 1024), 1),
                phase="finalizing",
                resumable=True,
                model_dir=str(model_dir),
            )
            return model_dir, detail
        except Exception:
            pass
    model_dir, detail = _ORIGINAL_RUN_SETUP(python)
    validated = _validate_downloaded_model(model_dir)
    return model_dir, f"{detail}\n{validated}"


def _low_vram_server_source() -> str:
    source = _ORIGINAL_SERVER_SOURCE()
    old = 'device = "cuda" if torch.cuda.is_available() else "cpu"'
    replacement = '''gpu_bytes = 0
    if torch.cuda.is_available():
        try:
            gpu_bytes = int(torch.cuda.get_device_properties(0).total_memory)
        except Exception:
            gpu_bytes = 0
    device = "cuda" if torch.cuda.is_available() and gpu_bytes >= 6 * 1024**3 else "cpu"
    if device == "cpu":
        try:
            torch.set_num_threads(max(2, min(8, os.cpu_count() or 4)))
        except Exception:
            pass'''
    if old not in source:
        raise RuntimeError("XTTS generated server device selector was not found.")
    return source.replace(old, replacement)


resume._download_worker_source = _light_download_worker_source
resume._run_resumable_model_setup = _run_setup_without_heavy_load
xtts._server_source = _low_vram_server_source
clone.logger.info("XTTS 98-percent finalization and low-VRAM safety patch is active.")
