"""موفرو الصوت السحابيون باستخدام مفاتيح الطلب دون حفظها أو تسجيلها."""

from __future__ import annotations

import base64
import wave
from pathlib import Path
from urllib.parse import quote


class ProviderError(RuntimeError):
    """خطأ موفر صوت سحابي قابل للعرض دون كشف بيانات حساسة."""


async def synthesize_elevenlabs(
    *,
    text: str,
    api_key: str,
    voice_id: str,
    model_id: str,
    output_path: Path,
) -> Path:
    if not api_key.strip():
        raise ProviderError("مفتاح ElevenLabs غير مضبوط")
    if not voice_id.strip():
        raise ProviderError("معرّف صوت ElevenLabs مطلوب")
    try:
        import httpx
    except ImportError as exc:
        raise ProviderError("مكتبة HTTP الخاصة بموفري الصوت غير مثبتة") from exc
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{quote(voice_id.strip(), safe='')}"
    try:
        async with httpx.AsyncClient(timeout=180.0, follow_redirects=False) as client:
            response = await client.post(
                url,
                params={"output_format": "mp3_44100_128"},
                headers={"xi-api-key": api_key.strip(), "Content-Type": "application/json", "Accept": "audio/mpeg"},
                json={"text": text, "model_id": model_id or "eleven_multilingual_v2"},
            )
    except httpx.RequestError as exc:
        raise ProviderError("تعذر الاتصال بخدمة ElevenLabs") from exc
    if response.status_code >= 400:
        if response.status_code in {401, 403}:
            raise ProviderError("مفتاح ElevenLabs غير صالح أو لا يملك الصلاحية")
        if response.status_code == 429:
            raise ProviderError("تم تجاوز حد استخدام ElevenLabs مؤقتًا")
        raise ProviderError(f"فشلت خدمة ElevenLabs برمز {response.status_code}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(response.content)
    if output_path.stat().st_size < 512:
        output_path.unlink(missing_ok=True)
        raise ProviderError("الملف الناتج من ElevenLabs غير صالح")
    return output_path


async def synthesize_gemini(
    *,
    text: str,
    api_key: str,
    voice_name: str,
    model_id: str,
    output_path: Path,
) -> Path:
    if not api_key.strip():
        raise ProviderError("مفتاح Gemini غير مضبوط")
    try:
        import httpx
    except ImportError as exc:
        raise ProviderError("مكتبة HTTP الخاصة بموفري الصوت غير مثبتة") from exc
    model = model_id.strip() or "gemini-3.1-flash-tts-preview"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{quote(model, safe='')}:generateContent"
    payload = {
        "contents": [{"parts": [{"text": text}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice_name.strip() or "Kore"}}},
        },
    }
    try:
        async with httpx.AsyncClient(timeout=180.0, follow_redirects=False) as client:
            response = await client.post(
                url,
                headers={"x-goog-api-key": api_key.strip(), "Content-Type": "application/json"},
                json=payload,
            )
    except httpx.RequestError as exc:
        raise ProviderError("تعذر الاتصال بخدمة Gemini") from exc
    if response.status_code >= 400:
        if response.status_code in {400, 401, 403}:
            raise ProviderError("مفتاح Gemini أو اسم النموذج غير صالح")
        if response.status_code == 429:
            raise ProviderError("تم تجاوز حد استخدام Gemini مؤقتًا")
        raise ProviderError(f"فشلت خدمة Gemini برمز {response.status_code}")
    try:
        body = response.json()
        parts = body["candidates"][0]["content"]["parts"]
        inline = next(
            part.get("inlineData") or part.get("inline_data")
            for part in parts
            if part.get("inlineData") or part.get("inline_data")
        )
        audio_bytes = base64.b64decode(inline["data"], validate=True)
        mime_type = str(inline.get("mimeType") or inline.get("mime_type") or "audio/L16")
    except Exception as exc:
        raise ProviderError("لم تُرجع Gemini ملفًا صوتيًا صالحًا") from exc
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if "wav" in mime_type.lower():
        output_path.write_bytes(audio_bytes)
    else:
        with wave.open(str(output_path), "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(_sample_rate_from_mime(mime_type) or 24000)
            wav_file.writeframes(audio_bytes)
    if not output_path.is_file() or output_path.stat().st_size < 64:
        output_path.unlink(missing_ok=True)
        raise ProviderError("الملف الناتج من Gemini غير صالح")
    return output_path


def _sample_rate_from_mime(mime_type: str) -> int | None:
    for part in mime_type.split(";"):
        key, _, value = part.strip().partition("=")
        if key.lower() in {"rate", "samplerate", "sample_rate"}:
            try:
                return int(value)
            except ValueError:
                return None
    return None
