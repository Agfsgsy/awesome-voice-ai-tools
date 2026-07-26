"""Microsoft Edge neural TTS plugin with Arabic voices and sermon profiles."""
from __future__ import annotations

import asyncio
import hashlib
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

from backend.core.config import OUTPUTS_DIR
from backend.core.logger import get_logger
from backend.plugins.tts_plugin_base import TTSPluginBase

logger = get_logger("plugin_edge")


class EdgeTTSPlugin(TTSPluginBase):
    name = "edge"
    label = "Microsoft Edge Neural TTS"
    description = "أصوات عربية عصبية عالية الجودة مع أنماط للمواعظ والدعاء"
    homepage = "https://github.com/rany2/edge-tts"
    is_open_source = True
    requires_gpu = False

    VOICES = {
        "ar-SA-HamedNeural": {"language": "ar", "locale": "ar-SA", "gender": "male", "label": "حامد - سعودي"},
        "ar-SA-ZariyahNeural": {"language": "ar", "locale": "ar-SA", "gender": "female", "label": "زارية - سعودية"},
        "ar-YE-SalehNeural": {"language": "ar", "locale": "ar-YE", "gender": "male", "label": "صالح - يمني"},
        "ar-YE-MaryamNeural": {"language": "ar", "locale": "ar-YE", "gender": "female", "label": "مريم - يمنية"},
        "ar-EG-ShakirNeural": {"language": "ar", "locale": "ar-EG", "gender": "male", "label": "شاكر - مصري"},
        "ar-EG-SalmaNeural": {"language": "ar", "locale": "ar-EG", "gender": "female", "label": "سلمى - مصرية"},
        "ar-AE-HamdanNeural": {"language": "ar", "locale": "ar-AE", "gender": "male", "label": "حمدان - إماراتي"},
        "ar-AE-FatimaNeural": {"language": "ar", "locale": "ar-AE", "gender": "female", "label": "فاطمة - إماراتية"},
        "ar-IQ-BasselNeural": {"language": "ar", "locale": "ar-IQ", "gender": "male", "label": "باسل - عراقي"},
        "ar-IQ-RanaNeural": {"language": "ar", "locale": "ar-IQ", "gender": "female", "label": "رنا - عراقية"},
        "ar-JO-TaimNeural": {"language": "ar", "locale": "ar-JO", "gender": "male", "label": "تيم - أردني"},
        "ar-JO-SanaNeural": {"language": "ar", "locale": "ar-JO", "gender": "female", "label": "سناء - أردنية"},
        "ar-KW-FahedNeural": {"language": "ar", "locale": "ar-KW", "gender": "male", "label": "فهد - كويتي"},
        "ar-KW-NouraNeural": {"language": "ar", "locale": "ar-KW", "gender": "female", "label": "نورة - كويتية"},
        "ar-LB-RamiNeural": {"language": "ar", "locale": "ar-LB", "gender": "male", "label": "رامي - لبناني"},
        "ar-LB-LaylaNeural": {"language": "ar", "locale": "ar-LB", "gender": "female", "label": "ليلى - لبنانية"},
        "ar-MA-JamalNeural": {"language": "ar", "locale": "ar-MA", "gender": "male", "label": "جمال - مغربي"},
        "ar-MA-MounaNeural": {"language": "ar", "locale": "ar-MA", "gender": "female", "label": "منى - مغربية"},
        "ar-OM-AbdullahNeural": {"language": "ar", "locale": "ar-OM", "gender": "male", "label": "عبدالله - عُماني"},
        "ar-OM-AyshaNeural": {"language": "ar", "locale": "ar-OM", "gender": "female", "label": "عائشة - عُمانية"},
        "ar-QA-MoazNeural": {"language": "ar", "locale": "ar-QA", "gender": "male", "label": "معاذ - قطري"},
        "ar-QA-AmalNeural": {"language": "ar", "locale": "ar-QA", "gender": "female", "label": "أمل - قطرية"},
        "ar-SY-LaithNeural": {"language": "ar", "locale": "ar-SY", "gender": "male", "label": "ليث - سوري"},
        "ar-SY-AmanyNeural": {"language": "ar", "locale": "ar-SY", "gender": "female", "label": "أماني - سورية"},
        "ar-DZ-IsmaelNeural": {"language": "ar", "locale": "ar-DZ", "gender": "male", "label": "إسماعيل - جزائري"},
        "ar-DZ-AminaNeural": {"language": "ar", "locale": "ar-DZ", "gender": "female", "label": "أمينة - جزائرية"},
        "ar-TN-HediNeural": {"language": "ar", "locale": "ar-TN", "gender": "male", "label": "الهادي - تونسي"},
        "ar-TN-ReemNeural": {"language": "ar", "locale": "ar-TN", "gender": "female", "label": "ريم - تونسية"},
        "ar-BH-AliNeural": {"language": "ar", "locale": "ar-BH", "gender": "male", "label": "علي - بحريني"},
        "ar-BH-LailaNeural": {"language": "ar", "locale": "ar-BH", "gender": "female", "label": "ليلى - بحرينية"},
        "ar-LY-OmarNeural": {"language": "ar", "locale": "ar-LY", "gender": "male", "label": "عمر - ليبي"},
        "ar-LY-ImanNeural": {"language": "ar", "locale": "ar-LY", "gender": "female", "label": "إيمان - ليبية"},
        "en-US-GuyNeural": {"language": "en", "locale": "en-US", "gender": "male", "label": "Guy - English"},
        "en-US-JennyNeural": {"language": "en", "locale": "en-US", "gender": "female", "label": "Jenny - English"},
    }

    PROFILES = {
        "natural": {"label": "طبيعي بشري", "rate": -1, "pitch": 0, "volume": 2},
        "sermon_calm": {"label": "واعظ هادئ", "rate": -12, "pitch": -2, "volume": 4},
        "sermon_powerful": {"label": "خطيب قوي", "rate": -7, "pitch": -5, "volume": 16},
        "dua_emotional": {"label": "دعاء مؤثر", "rate": -18, "pitch": 0, "volume": -2},
        "documentary": {"label": "وثائقي رزين", "rate": -6, "pitch": -3, "volume": 7},
        "energetic": {"label": "حماسي", "rate": 8, "pitch": 2, "volume": 10},
    }

    DEFAULT_BY_LANGUAGE = {"ar": "ar-SA-HamedNeural", "en": "en-US-GuyNeural"}
    MAX_TEXT_LENGTH = 5000

    def check(self) -> bool:
        try:
            import edge_tts  # noqa: F401
            return True
        except Exception:
            return False

    def install(self) -> Dict[str, Any]:
        import subprocess
        import sys

        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "edge-tts>=7,<8"])
            return {"success": self.check(), "engine": self.name, "message": "edge-tts installed successfully"}
        except Exception as exc:
            return {"success": False, "engine": self.name, "message": str(exc)}

    def download_models(self, model_name: str = "default") -> Dict[str, Any]:
        return {
            "success": self.check(),
            "model": "cloud-neural",
            "message": "لا يحتاج إلى تنزيل نموذج، لكنه يحتاج الإنترنت.",
        }

    def list_models(self) -> List[Dict[str, Any]]:
        return [{"name": "cloud-neural", "language": "multi", "downloaded": self.check()}]

    def list_voices(self) -> List[Dict[str, str]]:
        return [{"name": name, **metadata} for name, metadata in self.VOICES.items()]

    @classmethod
    def _parse_voice_profile(cls, value: str, language: str) -> Tuple[str, str]:
        raw = value or "default"
        profile = "natural"
        if "|" in raw:
            raw, requested_profile = raw.split("|", 1)
            if requested_profile in cls.PROFILES:
                profile = requested_profile
        voice = cls.DEFAULT_BY_LANGUAGE.get(language, cls.DEFAULT_BY_LANGUAGE["ar"]) if raw in {"", "default"} else raw
        return voice, profile

    @staticmethod
    def _prepare_text(text: str) -> str:
        """تنظيم النص وعلامات الوقف لإلقاء عربي أكثر طبيعية."""
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\s*([،؛:؟!.…])\s*", r"\1 ", text)
        text = re.sub(r"([؟!.…]){2,}", r"\1", text)
        paragraphs: List[str] = []
        for raw in re.split(r"\n+", text):
            paragraph = raw.strip()
            if not paragraph:
                continue
            if paragraph[-1] not in "؟!.…":
                paragraph += "."
            paragraphs.append(paragraph)
        return "\n\n".join(paragraphs)

    @staticmethod
    def _friendly_error(exc: Exception) -> str:
        raw = str(exc)
        lowered = raw.lower()
        if any(token in lowered for token in ("getaddrinfo", "cannot connect", "speech.platform.bing.com", "ssl", "timed out")):
            return "تعذر الاتصال بخدمة الصوت العصبي. افحص الإنترنت أو DNS أو VPN ثم أعد المحاولة."
        if "winerror 2" in lowered or "cannot find the file" in lowered:
            return "تعذر تشغيل أحد مكونات الصوت داخل النسخة الحالية. ثبّت آخر تحديث للبرنامج."
        return f"فشل إنشاء الصوت: {raw}"

    @staticmethod
    async def _generate_audio(edge_tts, text: str, filepath: Path, voice: str, rate: int, pitch: int, volume: int) -> None:
        """إنشاء ملف MP3 واحد؛ مكتبة Edge تقسّم الرسائل الطويلة داخليًا دون FFmpeg."""
        if filepath.exists() and filepath.stat().st_size > 0:
            return

        last_error: Exception | None = None
        for attempt in range(3):
            try:
                communication = edge_tts.Communicate(
                    text=text,
                    voice=voice,
                    rate=f"{rate:+d}%",
                    pitch=f"{pitch:+d}Hz",
                    volume=f"{volume:+d}%",
                )
                await communication.save(str(filepath))
                if filepath.exists() and filepath.stat().st_size > 0:
                    return
                raise RuntimeError("لم تُنشأ بيانات صوتية.")
            except Exception as exc:
                last_error = exc
                filepath.unlink(missing_ok=True)
                if attempt < 2:
                    await asyncio.sleep(1.2 * (2 ** attempt))
        raise last_error or RuntimeError("فشل إنشاء الصوت.")

    async def generate(
        self,
        text: str,
        voice: str = "default",
        language: str = "ar",
        speed: float = 1.0,
    ) -> Dict[str, Any]:
        if not self.check():
            return {"success": False, "engine": self.name, "message": "محرك الصوت العصبي غير موجود داخل البرنامج."}

        text = self._prepare_text((text or "").strip())
        if not text:
            return {"success": False, "engine": self.name, "message": "النص فارغ."}
        if len(text) > self.MAX_TEXT_LENGTH:
            return {"success": False, "engine": self.name, "message": f"النص أطول من {self.MAX_TEXT_LENGTH} حرف."}
        if not 0.5 <= speed <= 2.0:
            return {"success": False, "engine": self.name, "message": "السرعة يجب أن تكون بين 0.5 و2.0."}

        import edge_tts

        selected_voice, profile_name = self._parse_voice_profile(voice, language)
        if selected_voice not in self.VOICES:
            return {"success": False, "engine": self.name, "message": "الصوت المحدد غير موجود في قائمة الأصوات المدعومة."}

        profile = self.PROFILES[profile_name]
        rate = max(-50, min(100, round((speed - 1.0) * 100) + int(profile["rate"])))
        pitch = int(profile["pitch"])
        volume = int(profile["volume"])
        digest = hashlib.sha256(
            f"{selected_voice}|{profile_name}|{rate}|{pitch}|{volume}|{text}".encode("utf-8")
        ).hexdigest()[:16]
        filepath = OUTPUTS_DIR / f"edge_{profile_name}_{digest}.mp3"

        try:
            await self._generate_audio(edge_tts, text, filepath, selected_voice, rate, pitch, volume)
            return {
                "success": True,
                "engine": self.name,
                "voice": selected_voice,
                "profile": profile_name,
                "segments": 1,
                "file": str(filepath),
                "url": f"/api/downloads/{filepath.name}",
                "message": f"تم إنشاء الصوت بنجاح بأسلوب {profile['label']}.",
            }
        except Exception as exc:
            logger.exception("Edge TTS generation failed")
            return {"success": False, "engine": self.name, "message": self._friendly_error(exc)}


PLUGIN_CLASS = EdgeTTSPlugin
PLUGIN_NAME = "Microsoft Edge Neural TTS"
PLUGIN_DESCRIPTION = "أصوات عربية عصبية وأنماط احترافية للمواعظ والدعاء"
