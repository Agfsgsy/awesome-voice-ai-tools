"""Additive Voice Clone Pro precision-reference runtime.

It upgrades the existing profile endpoint without deleting the preserved routes or
interface. Every FFmpeg-readable audio/video recording is decoded by content,
scored, ranked, and only the strongest references are sent to the clone engine.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import re
import shutil
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile

import backend.api.voice_clone_routes as clone
import backend.api.voice_engine_suite_routes as suite
from backend.core.config import CACHE_DIR
from backend.core.voice_reference_pipeline import (
    COMMON_MEDIA_SUFFIXES,
    probe_media,
    score_generated_media,
    select_best_references,
    transcode_reference,
)

router = APIRouter(prefix="/api/voice-ai/audio/reference", tags=["Voice Reference Precision 7.1"])
MAX_FILE_BYTES = 160 * 1024 * 1024
MAX_TOTAL_BYTES = 600 * 1024 * 1024
MAX_FILES = 10


def _suffix(filename: str) -> str:
    suffix = Path(filename or "").suffix.lower()
    if re.fullmatch(r"\.[a-z0-9]{1,8}", suffix):
        return suffix
    return ".media"


async def _save_upload(upload: UploadFile, target: Path, remaining: int) -> tuple[int, str]:
    digest = hashlib.sha256()
    total = 0
    with target.open("wb") as handle:
        while True:
            chunk = await upload.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_FILE_BYTES or total > remaining:
                target.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail="حجم التسجيل أكبر من الحد المسموح.")
            digest.update(chunk)
            handle.write(chunk)
    if total < 512:
        target.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="التسجيل فارغ أو تالف.")
    return total, digest.hexdigest()


def _public_metrics(record: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "container", "codec", "sample_rate", "channels", "bit_rate",
        "duration", "rms", "peak", "clipping_ratio", "silence_ratio",
        "voiced_ratio", "snr_db_estimate", "dc_offset", "zero_crossing_rate",
        "crest_factor_db", "quality_score", "quality_label", "warnings",
        "processing_mode", "selected_for_clone",
    )
    result: dict[str, Any] = {}
    for key in keys:
        value = record.get(key)
        if isinstance(value, float):
            result[key] = round(value, 6)
        else:
            result[key] = value
    return result


async def advanced_create_profile_from_uploads(
    samples: list[UploadFile],
    *,
    name: str,
    owner_name: str,
    consent: bool,
    consent_statement: str,
) -> dict[str, Any]:
    if not consent:
        raise HTTPException(status_code=400, detail="يجب تأكيد ملكية الصوت أو وجود إذن صريح من صاحبه.")
    if len((consent_statement or "").strip()) < 8:
        raise HTTPException(status_code=400, detail="اكتب نصًا واضحًا لتأكيد الموافقة.")
    if not samples or len(samples) > MAX_FILES:
        raise HTTPException(status_code=400, detail=f"اختر من تسجيل واحد إلى {MAX_FILES} تسجيلات.")

    profile_id = uuid.uuid4().hex[:16]
    directory = clone._profile_path(profile_id)
    originals = directory / "originals"
    processed = directory / "processed"
    originals.mkdir(parents=True, exist_ok=False)
    processed.mkdir(parents=True, exist_ok=True)

    total_bytes = 0
    all_records: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    try:
        for index, upload in enumerate(samples, start=1):
            original_name = Path(upload.filename or f"recording_{index}").name
            original = originals / f"sample_{index}{_suffix(original_name)}"
            size, digest = await _save_upload(upload, original, MAX_TOTAL_BYTES - total_bytes)
            total_bytes += size
            normalized = processed / f"sample_{index}.wav"
            try:
                analysis = await asyncio.to_thread(transcode_reference, original, normalized)
                record: dict[str, Any] = {
                    "sample_index": index,
                    "original_name": original_name,
                    "original_file": original.name,
                    "processed_file": normalized.name,
                    "sha256": digest,
                    "source_bytes": size,
                    **analysis,
                }
                record["eligible"] = bool(
                    float(record.get("duration") or 0) >= 2.0
                    and float(record.get("voiced_ratio") or 0) >= 0.08
                    and int(record.get("quality_score") or 0) >= 25
                )
                all_records.append(record)
            except Exception as exc:
                normalized.unlink(missing_ok=True)
                rejected.append(
                    {
                        "sample_index": index,
                        "original_name": original_name,
                        "sha256": digest,
                        "reason": str(exc),
                    }
                )

        eligible = [item for item in all_records if item.get("eligible")]
        selected = select_best_references(eligible, max_files=5, max_total_seconds=150.0)
        selected_indexes = {int(item["sample_index"]) for item in selected}
        for item in all_records:
            item["selected_for_clone"] = int(item["sample_index"]) in selected_indexes

        total_duration = sum(float(item.get("duration") or 0) for item in selected)
        if total_duration < 8.0:
            reasons = [item.get("reason") for item in rejected if item.get("reason")]
            message = "لم تتوفر ثماني ثوانٍ على الأقل من الكلام الصالح بعد التحليل."
            if reasons:
                message += " السبب: " + " | ".join(str(item) for item in reasons[:3])
            raise HTTPException(status_code=400, detail=message)

        weighted_score = round(
            sum(float(item.get("quality_score") or 0) * float(item.get("duration") or 0) for item in selected)
            / max(total_duration, 0.001)
        )
        warnings: list[str] = []
        for item in selected:
            for warning in item.get("warnings") or []:
                if warning not in warnings:
                    warnings.append(str(warning))
        if rejected:
            warnings.append(f"تم استبعاد {len(rejected)} تسجيل/تسجيلات لعدم صلاحيتها.")
        if len(eligible) > len(selected):
            warnings.append("اختار النظام أفضل التسجيلات فقط لمنع تراجع بصمة المتحدث.")

        label = "ممتازة" if weighted_score >= 88 else "جيدة جدًا" if weighted_score >= 76 else "جيدة" if weighted_score >= 62 else "مقبولة"
        clone_samples = []
        for item in selected:
            clone_samples.append(
                {
                    "original_name": item["original_name"],
                    "sha256": item["sha256"],
                    "processed_file": item["processed_file"],
                    "duration": round(float(item.get("duration") or 0), 2),
                    "rms": round(float(item.get("rms") or 0), 6),
                    "clipping_ratio": round(float(item.get("clipping_ratio") or 0), 7),
                    "silence_ratio": round(float(item.get("silence_ratio") or 0), 6),
                    "voiced_ratio": round(float(item.get("voiced_ratio") or 0), 6),
                    "snr_db_estimate": round(float(item.get("snr_db_estimate") or 0), 2),
                    "quality_score": int(item.get("quality_score") or 0),
                    "container": item.get("container"),
                    "codec": item.get("codec"),
                }
            )

        created_at = clone._now()
        manifest = {
            "id": profile_id,
            "name": clone._safe_name(name, "صوتي"),
            "owner_name": clone._safe_name(owner_name, "صاحب الصوت"),
            "created_at": created_at,
            "consent_confirmed": True,
            "consent_statement": consent_statement.strip()[:500],
            "consent_record_sha256": hashlib.sha256(
                f"{owner_name}|{consent_statement}|{profile_id}|{created_at}".encode("utf-8")
            ).hexdigest(),
            "synthetic_use_only": True,
            "pipeline": "precision-reference-v7.1",
            "input_support": "any FFmpeg-readable audio or video container with a valid audio stream",
            "samples": clone_samples,
            "all_sample_analysis": [_public_metrics(item) | {"original_name": item["original_name"]} for item in all_records],
            "rejected_samples": rejected,
            "selected_sample_count": len(selected),
            "uploaded_sample_count": len(samples),
            "total_duration": round(total_duration, 2),
            "quality_score": int(weighted_score),
            "quality_label": label,
            "quality_notes": warnings,
            "elevenlabs_voice_id": "",
        }
        clone._save_manifest(profile_id, manifest)
        (directory / "reference_analysis.json").write_text(
            json.dumps(
                {
                    "profile_id": profile_id,
                    "pipeline": manifest["pipeline"],
                    "selected": [item["sample_index"] for item in selected],
                    "all_samples": all_records,
                    "rejected": rejected,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return manifest
    except Exception:
        shutil.rmtree(directory, ignore_errors=True)
        raise


@router.get("/formats")
async def supported_reference_formats():
    return {
        "success": True,
        "mode": "content-based-ffmpeg-detection",
        "message": "يقبل النظام أي ملف يستطيع FFmpeg فك صوته، حتى لو كان داخل فيديو.",
        "common_suffixes": sorted(COMMON_MEDIA_SUFFIXES),
        "max_files": MAX_FILES,
        "max_file_mb": MAX_FILE_BYTES // (1024 * 1024),
    }


@router.post("/analyze")
async def analyze_reference_files(files: list[UploadFile] = File(...)):
    if not files or len(files) > MAX_FILES:
        raise HTTPException(status_code=400, detail=f"اختر من ملف واحد إلى {MAX_FILES} ملفات.")
    work = CACHE_DIR / "reference_analysis" / uuid.uuid4().hex
    work.mkdir(parents=True, exist_ok=False)
    results: list[dict[str, Any]] = []
    total_bytes = 0
    try:
        for index, upload in enumerate(files, start=1):
            name = Path(upload.filename or f"recording_{index}").name
            source = work / f"source_{index}{_suffix(name)}"
            size, digest = await _save_upload(upload, source, MAX_TOTAL_BYTES - total_bytes)
            total_bytes += size
            canonical = work / f"canonical_{index}.wav"
            try:
                metadata = await asyncio.to_thread(transcode_reference, source, canonical)
                results.append(
                    {
                        "success": True,
                        "filename": name,
                        "sha256": digest,
                        **_public_metrics(metadata),
                    }
                )
            except Exception as exc:
                results.append({"success": False, "filename": name, "sha256": digest, "error": str(exc)})
        return {
            "success": any(item.get("success") for item in results),
            "pipeline": "precision-reference-v7.1",
            "files": results,
        }
    finally:
        shutil.rmtree(work, ignore_errors=True)


# Install the additive upgrade for both the preserved profile API and the v7
# ensemble route, whose imported function reference would otherwise remain old.
clone.SUPPORTED_SAMPLE_FORMATS = set(COMMON_MEDIA_SUFFIXES)
clone.create_profile_from_uploads = advanced_create_profile_from_uploads
suite.create_profile_from_uploads = advanced_create_profile_from_uploads
suite._candidate_quality = lambda result: score_generated_media(Path(str(result.get("file") or "")))
