"""اختبارات تكامل طبقة API المخصصة لتطبيق الجوال."""

from __future__ import annotations

import io
import math
import struct
import uuid
import wave

from fastapi.testclient import TestClient

from backend.mobile.security import mobile_security
from main import app

client = TestClient(app)


def _paired_headers() -> tuple[dict[str, str], str]:
    session = mobile_security.create_pairing_session("http://127.0.0.1:8000")
    pair_response = client.post(
        "/api/mobile/pair",
        json={
            "pairing_id": session["pairing_id"],
            "pairing_code": session["pairing_code"],
            "device_name": "هاتف الاختبار",
            "platform": "android",
            "app_version": "1.0.0-test",
        },
    )
    assert pair_response.status_code == 200, pair_response.text
    paired = pair_response.json()
    auth_response = client.post(
        "/api/mobile/auth",
        json={"device_id": paired["device_id"], "device_token": paired["device_token"]},
    )
    assert auth_response.status_code == 200, auth_response.text
    return {"Authorization": f"Bearer {auth_response.json()['access_token']}"}, paired["device_id"]


def _speech_like_wav(seconds: float = 3.0, sample_rate: int = 24_000) -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(sample_rate)
        frames = bytearray()
        for index in range(int(seconds * sample_rate)):
            carrier = math.sin(2 * math.pi * 180 * index / sample_rate)
            harmonic = 0.35 * math.sin(2 * math.pi * 360 * index / sample_rate)
            envelope = 0.55 + 0.25 * math.sin(2 * math.pi * 3 * index / sample_rate)
            sample = int(max(-1.0, min(1.0, (carrier + harmonic) * envelope * 0.28)) * 32767)
            frames.extend(struct.pack("<h", sample))
        audio.writeframes(frames)
    return output.getvalue()


def test_mobile_status_and_desktop_routes_coexist() -> None:
    status_response = client.get("/api/mobile/status")
    assert status_response.status_code == 200
    assert status_response.json()["capabilities"]["pairing"] is True

    route_paths = {route.path for route in app.routes}
    old_paths = {
        "/health",
        "/status",
        "/api/info",
        "/api/tts",
        "/api/speech",
        "/api/audio/clone",
        "/api/audio/upload",
        "/api/effects/apply",
        "/api/stt",
    }
    assert old_paths <= route_paths
    assert client.get("/mobile-pairing").status_code == 200


def test_pair_auth_and_protected_engines() -> None:
    assert client.get("/api/mobile/engines").status_code == 401
    headers, device_id = _paired_headers()
    response = client.get("/api/mobile/engines", headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["count"] >= 2
    files_response = client.get("/api/mobile/files", headers=headers)
    assert files_response.status_code == 200
    assert all(item["name"] != "upload_state.json" for item in files_response.json()["files"])
    assert all("token_hash" not in device for device in mobile_security.list_devices())
    assert mobile_security.revoke_device(device_id) is True
    assert client.get("/api/mobile/engines", headers=headers).status_code == 401


def test_reference_analysis_and_clone_consent_gate() -> None:
    headers, _ = _paired_headers()
    response = client.post(
        "/api/mobile/reference/analyze",
        headers=headers,
        files={"file": ("reference.wav", _speech_like_wav(), "audio/wav")},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    analysis = payload["analysis"]
    assert analysis["duration_seconds"] >= 2.9
    assert 0 <= analysis["quality_score"] <= 100
    assert {"noise_floor_dbfs", "silence_percent", "clipping_percent", "sample_quality"} <= analysis.keys()

    rejected = client.post(
        "/api/mobile/voice/clone",
        headers=headers,
        json={
            "reference_file_id": payload["file_id"],
            "text": "هذا اختبار للموافقة الصريحة",
            "engine": "auto",
            "language": "ar",
            "candidate_count": 2,
            "consent_confirmed": False,
            "voice_rights": "self",
            "consent_statement": "أنا صاحب هذا الصوت وأوافق على استخدامه.",
        },
    )
    assert rejected.status_code == 403
    assert "تأكيد" in rejected.json()["detail"]


def test_reference_acceptance_uses_ffmpeg_content_probe_not_filename_extension() -> None:
    headers, _ = _paired_headers()
    response = client.post(
        "/api/mobile/reference/analyze",
        headers=headers,
        files={"file": ("reference.customaudio", _speech_like_wav(), "application/octet-stream")},
    )
    assert response.status_code == 200, response.text
    assert response.json()["analysis"]["format"] == "wav"


def test_resumable_upload_and_large_chunk_rejection() -> None:
    headers, _ = _paired_headers()
    content = b"mobile-resumable-upload"
    upload_id = uuid.uuid4().hex
    first = content[:9]
    second = content[9:]

    response = client.post(
        "/api/mobile/uploads",
        headers=headers,
        data={"upload_id": upload_id, "filename": "sample.txt", "offset": "0", "total_size": str(len(content))},
        files={"file": ("chunk.bin", first, "application/octet-stream")},
    )
    assert response.status_code == 200, response.text
    assert response.json()["next_offset"] == len(first)
    status_response = client.get(f"/api/mobile/uploads/{upload_id}", headers=headers)
    assert status_response.json()["next_offset"] == len(first)

    response = client.post(
        "/api/mobile/uploads",
        headers=headers,
        data={
            "upload_id": upload_id,
            "filename": "sample.txt",
            "offset": str(len(first)),
            "total_size": str(len(content)),
        },
        files={"file": ("chunk.bin", second, "application/octet-stream")},
    )
    assert response.status_code == 200, response.text
    assert response.json()["completed"] is True

    oversized = b"x" * (6 * 1024 * 1024 + 1)
    rejected = client.post(
        "/api/mobile/uploads",
        headers=headers,
        data={
            "upload_id": uuid.uuid4().hex,
            "filename": "large.bin",
            "offset": "0",
            "total_size": str(len(oversized)),
        },
        files={"file": ("large.bin", oversized, "application/octet-stream")},
    )
    assert rejected.status_code == 413
    assert "6" in rejected.json()["detail"]


def test_large_file_upload_completes_across_multiple_chunks() -> None:
    headers, _ = _paired_headers()
    upload_id = uuid.uuid4().hex
    total_size = 7 * 1024 * 1024
    first_size = 5 * 1024 * 1024
    first = client.post(
        "/api/mobile/uploads",
        headers=headers,
        data={"upload_id": upload_id, "filename": "large.flac", "offset": "0", "total_size": str(total_size)},
        files={"file": ("chunk.bin", b"a" * first_size, "application/octet-stream")},
    )
    assert first.status_code == 200, first.text
    assert first.json()["next_offset"] == first_size
    assert first.json()["completed"] is False

    second = client.post(
        "/api/mobile/uploads",
        headers=headers,
        data={
            "upload_id": upload_id,
            "filename": "large.flac",
            "offset": str(first_size),
            "total_size": str(total_size),
        },
        files={"file": ("chunk.bin", b"b" * (total_size - first_size), "application/octet-stream")},
    )
    assert second.status_code == 200, second.text
    assert second.json()["completed"] is True
    assert client.delete(f"/api/mobile/files/{second.json()['file_id']}", headers=headers).status_code == 200
