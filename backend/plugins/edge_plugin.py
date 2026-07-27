"""Microsoft Edge neural TTS plugin with Arabic voices and humanized prosody."""

from __future__ import annotations

import asyncio
import hashlib
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Tuple

from backend.core.config import CACHE_DIR, OUTPUTS_DIR
from backend.core.logger import get_logger
from backend.plugins.tts_plugin_base import TTSPluginBase

logger = get_logger("plugin_edge")


class EdgeTTSPlugin(TTSPluginBase):
    name = "edge"
    label = "Microsoft Edge Neural TTS"
    description = "أصوات عربية عصبية مع تنغيم بشري متغير وأنماط للمواعظ والدعاء"
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
        "en-GB-RyanNeural": {"language": "en", "locale": "en-GB", "gender": "male", "label": "Ryan - British"},
        "en-GB-SoniaNeural": {"language": "en", "locale": "en-GB", "gender": "female", "label": "Sonia - British"},
        "en-AU-WilliamNeural": {"language": "en", "locale": "en-AU", "gender": "male", "label": "William - Australian"},
        "en-AU-NatashaNeural": {
            "language": "en",
            "locale": "en-AU",
            "gender": "female",
            "label": "Natasha - Australian",
        },
    }

    PROFILES = {
        "human_ultra": {
            "label": "بشري فائق",
            "rate": -4,
            "pitch": 0,
            "volume": 5,
            "pause": 190,
            "chunk": 340,
            "variation": True,
        },
        "natural": {
            "label": "طبيعي بشري",
            "rate": -1,
            "pitch": 0,
            "volume": 2,
            "pause": 170,
            "chunk": 500,
            "variation": False,
        },
        "sermon_calm": {
            "label": "واعظ هادئ",
            "rate": -13,
            "pitch": -2,
            "volume": 5,
            "pause": 340,
            "chunk": 310,
            "variation": True,
        },
        "sermon_powerful": {
            "label": "خطيب قوي",
            "rate": -7,
            "pitch": -4,
            "volume": 17,
            "pause": 270,
            "chunk": 300,
            "variation": True,
        },
        "dua_emotional": {
            "label": "دعاء مؤثر",
            "rate": -19,
            "pitch": -1,
            "volume": 0,
            "pause": 430,
            "chunk": 270,
            "variation": True,
        },
        "documentary": {
            "label": "وثائقي رزين",
            "rate": -6,
            "pitch": -3,
            "volume": 8,
            "pause": 240,
            "chunk": 360,
            "variation": True,
        },
        "energetic": {
            "label": "حماسي",
            "rate": 8,
            "pitch": 2,
            "volume": 11,
            "pause": 125,
            "chunk": 330,
            "variation": True,
        },
        "broadcast_power": {
            "label": "إذاعي قوي",
            "rate": -2,
            "pitch": -2,
            "volume": 13,
            "pause": 170,
            "chunk": 360,
            "variation": True,
        },
    }

    DEFAULT_BY_LANGUAGE = {"ar": "ar-SA-HamedNeural", "en": "en-US-GuyNeural"}
    MAX_TEXT_LENGTH = 8000

    def check(self) -> bool:
        try:
            import edge_tts  # noqa: F401

            return True
        except Exception:
            return False

    def install(self) -> Dict[str, Any]:
        import subprocess as sp
        import sys

        try:
            sp.check_call([sys.executable, "-m", "pip", "install", "edge-tts>=7,<8"])
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
        profile = "human_ultra"
        if "|" in raw:
            raw, requested_profile = raw.split("|", 1)
            if requested_profile in cls.PROFILES:
                profile = requested_profile
        voice = cls.DEFAULT_BY_LANGUAGE.get(language, cls.DEFAULT_BY_LANGUAGE["ar"]) if raw in {"", "default"} else raw
        return voice, profile

    @staticmethod
    def _prepare_text(text: str) -> str:
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
    def _split_words(text: str, limit: int) -> List[str]:
        chunks: List[str] = []
        current: List[str] = []
        length = 0
        for word in text.split():
            extra = len(word) + (1 if current else 0)
            if current and length + extra > limit:
                chunks.append(" ".join(current))
                current = [word]
                length = len(word)
            else:
                current.append(word)
                length += extra
        if current:
            chunks.append(" ".join(current))
        return chunks

    @classmethod
    def _split_segments(cls, text: str, limit: int) -> List[Tuple[str, int]]:
        result: List[Tuple[str, int]] = []
        paragraphs = [item.strip() for item in text.split("\n\n") if item.strip()]
        for paragraph_index, paragraph in enumerate(paragraphs):
            sentences = [item.strip() for item in re.split(r"(?<=[؟!.…؛])\s+", paragraph) if item.strip()]
            current = ""
            for sentence in sentences:
                pieces = cls._split_words(sentence, limit) if len(sentence) > limit else [sentence]
                for piece in pieces:
                    candidate = f"{current} {piece}".strip()
                    if current and len(candidate) > limit:
                        result.append((current, 115))
                        current = piece
                    else:
                        current = candidate
            if current:
                paragraph_pause = 0 if paragraph_index == len(paragraphs) - 1 else 1
                result.append((current, paragraph_pause))
        return result or [(text, 0)]

    @staticmethod
    def _friendly_error(exc: Exception) -> str:
        raw = str(exc)
        lowered = raw.lower()
        if any(
            token in lowered
            for token in ("getaddrinfo", "cannot connect", "speech.platform.bing.com", "ssl", "timed out")
        ):
            return "تعذر الاتصال بخدمة الصوت العصبي. افحص الإنترنت أو DNS أو VPN ثم أعد المحاولة."
        if "winerror 2" in lowered or "cannot find the file" in lowered:
            return "تعذر تشغيل أداة الصوت المرفقة. أعد بناء النسخة من آخر تحديث."
        return f"فشل إنشاء الصوت: {raw}"

    @staticmethod
    def _ffmpeg_executable() -> str | None:
        executable = shutil.which("ffmpeg")
        if executable:
            return executable
        try:
            import imageio_ffmpeg

            executable = imageio_ffmpeg.get_ffmpeg_exe()
            return executable if Path(executable).exists() else None
        except Exception:
            return None

    @classmethod
    def _segment_prosody(
        cls, segment: str, index: int, base_rate: int, base_pitch: int, base_volume: int, variation: bool
    ) -> Tuple[int, int, int]:
        if not variation:
            return base_rate, base_pitch, base_volume
        patterns = [(-2, 0, 0), (0, 1, 1), (-1, -1, 0), (1, 0, 2), (-2, 1, 0), (0, -1, 1)]
        rate_delta, pitch_delta, volume_delta = patterns[index % len(patterns)]
        if segment.endswith("؟"):
            pitch_delta += 2
            rate_delta -= 1
        if segment.endswith("!"):
            volume_delta += 2
            rate_delta += 1
        if any(word in segment for word in ("اللهم", "يا رب", "سبحانه", "رحمة الله")):
            rate_delta -= 2
            pitch_delta -= 1
        return (
            max(-50, min(100, base_rate + rate_delta)),
            max(-20, min(20, base_pitch + pitch_delta)),
            max(-50, min(50, base_volume + volume_delta)),
        )

    @staticmethod
    async def _render(edge_tts, text: str, path: Path, voice: str, rate: int, pitch: int, volume: int) -> None:
        if path.exists() and path.stat().st_size > 0:
            return
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                communicator = edge_tts.Communicate(
                    text=text,
                    voice=voice,
                    rate=f"{rate:+d}%",
                    pitch=f"{pitch:+d}Hz",
                    volume=f"{volume:+d}%",
                )
                await communicator.save(str(path))
                if path.exists() and path.stat().st_size > 0:
                    return
                raise RuntimeError("لم تُنشأ بيانات صوتية.")
            except Exception as exc:
                last_error = exc
                path.unlink(missing_ok=True)
                if attempt < 2:
                    await asyncio.sleep(1.1 * (2**attempt))
        raise last_error or RuntimeError("فشل إنشاء المقطع الصوتي.")

    @classmethod
    def _merge_with_ffmpeg(cls, parts: List[Tuple[Path, int]], output: Path, paragraph_pause_ms: int) -> bool:
        ffmpeg = cls._ffmpeg_executable()
        if not ffmpeg or len(parts) < 2:
            return False
        work_dir = Path(tempfile.mkdtemp(prefix="voice_ai_merge_"))
        try:
            list_path = work_dir / "concat.txt"
            entries: List[str] = []
            silence_cache: Dict[int, Path] = {}
            for index, (part, pause_kind) in enumerate(parts):
                safe = str(part.resolve()).replace("\\", "/").replace("'", "'\\''")
                entries.append(f"file '{safe}'")
                pause_ms = paragraph_pause_ms if pause_kind == 1 else pause_kind
                if pause_ms and index < len(parts) - 1:
                    if pause_ms not in silence_cache:
                        silence = work_dir / f"silence_{pause_ms}.mp3"
                        command = [
                            ffmpeg,
                            "-hide_banner",
                            "-loglevel",
                            "error",
                            "-y",
                            "-f",
                            "lavfi",
                            "-i",
                            "anullsrc=r=24000:cl=mono",
                            "-t",
                            f"{pause_ms / 1000:.3f}",
                            "-c:a",
                            "libmp3lame",
                            "-b:a",
                            "64k",
                            str(silence),
                        ]
                        completed = subprocess.run(command, capture_output=True, text=True, timeout=60, check=False)
                        if completed.returncode != 0:
                            raise RuntimeError(completed.stderr.strip() or "تعذر إنشاء الوقفة الصوتية")
                        silence_cache[pause_ms] = silence
                    safe_silence = str(silence_cache[pause_ms].resolve()).replace("\\", "/").replace("'", "'\\''")
                    entries.append(f"file '{safe_silence}'")
            list_path.write_text("\n".join(entries), encoding="utf-8")
            command = [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(list_path),
                "-vn",
                "-c:a",
                "libmp3lame",
                "-b:a",
                "192k",
                "-ar",
                "24000",
                "-ac",
                "1",
                str(output),
            ]
            completed = subprocess.run(command, capture_output=True, text=True, timeout=300, check=False)
            return completed.returncode == 0 and output.exists() and output.stat().st_size > 0
        finally:
            shutil.rmtree(work_dir, ignore_errors=True)

    async def generate(
        self, text: str, voice: str = "default", language: str = "ar", speed: float = 1.0
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
            return {
                "success": False,
                "engine": self.name,
                "message": "الصوت المحدد غير موجود في قائمة الأصوات المدعومة.",
            }

        profile = self.PROFILES[profile_name]
        base_rate = max(-50, min(100, round((speed - 1.0) * 100) + int(profile["rate"])))
        base_pitch = int(profile["pitch"])
        base_volume = int(profile["volume"])
        segments = self._split_segments(text, int(profile["chunk"]))
        digest = hashlib.sha256(
            f"v230|{selected_voice}|{profile_name}|{base_rate}|{base_pitch}|{base_volume}|{text}".encode("utf-8")
        ).hexdigest()[:18]
        output = OUTPUTS_DIR / f"edge_{profile_name}_{digest}.mp3"
        parts_dir = CACHE_DIR / "edge_human_parts"
        parts_dir.mkdir(parents=True, exist_ok=True)

        try:
            if not output.exists() or output.stat().st_size == 0:
                rendered: List[Tuple[Path, int]] = []
                for index, (segment, pause_kind) in enumerate(segments):
                    rate, pitch, volume = self._segment_prosody(
                        segment, index, base_rate, base_pitch, base_volume, bool(profile["variation"])
                    )
                    part_digest = hashlib.sha256(
                        f"{selected_voice}|{rate}|{pitch}|{volume}|{segment}".encode("utf-8")
                    ).hexdigest()[:18]
                    part_path = parts_dir / f"{part_digest}.mp3"
                    await self._render(edge_tts, segment, part_path, selected_voice, rate, pitch, volume)
                    rendered.append((part_path, pause_kind))

                merged = await asyncio.to_thread(self._merge_with_ffmpeg, rendered, output, int(profile["pause"]))
                if not merged:
                    output.unlink(missing_ok=True)
                    await self._render(edge_tts, text, output, selected_voice, base_rate, base_pitch, base_volume)

            return {
                "success": True,
                "engine": self.name,
                "voice": selected_voice,
                "profile": profile_name,
                "segments": len(segments),
                "humanized": bool(profile["variation"]),
                "file": str(output),
                "url": f"/api/downloads/{output.name}",
                "message": f"تم إنشاء الصوت بأسلوب {profile['label']} مع تنغيم ووقفات طبيعية.",
            }
        except Exception as exc:
            logger.exception("Edge TTS generation failed")
            return {"success": False, "engine": self.name, "message": self._friendly_error(exc)}


PLUGIN_CLASS = EdgeTTSPlugin
PLUGIN_NAME = "Microsoft Edge Neural TTS"
PLUGIN_DESCRIPTION = "أصوات عربية عصبية مع Human Ultra وأنماط احترافية للمواعظ والدعاء"
