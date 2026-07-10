"""Language Manager - Multi-language Support and Detection"""
import re
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from enum import Enum

from backend.core.logger import get_logger

logger = get_logger("language_manager")


class LanguageCode(str, Enum):
    AR = "ar"
    EN = "en"
    FR = "fr"
    DE = "de"
    ES = "es"
    IT = "it"
    PT = "pt"
    RU = "ru"
    ZH = "zh"
    JA = "ja"
    KO = "ko"
    HI = "hi"
    TR = "tr"
    PL = "pl"
    NL = "nl"
    SV = "sv"
    DA = "da"
    NO = "no"
    FI = "fi"
    CS = "cs"
    HU = "hu"
    RO = "ro"
    BG = "bg"
    UK = "uk"
    HE = "he"
    FA = "fa"
    UR = "ur"
    MS = "ms"
    ID = "id"
    TH = "th"
    VI = "vi"


@dataclass
class Language:
    code: str
    name: str
    name_native: str
    rtl: bool = False
    supported_engines: List[str] = field(default_factory=list)
    is_beta: bool = False


class LanguageManager:
    """Multi-language support with detection capabilities"""
    
    # Language definitions
    LANGUAGES: Dict[str, Language] = {
        "ar": Language("ar", "Arabic", "العربية", True, ["piper", "coqui", "kokoro", "melotts", "gemini"]),
        "en": Language("en", "English", "English", False, ["piper", "coqui", "kokoro", "melotts", "bark", "gemini", "styletts2"]),
        "fr": Language("fr", "French", "Français", False, ["coqui", "melotts", "gemini"]),
        "de": Language("de", "German", "Deutsch", False, ["coqui", "melotts", "gemini"]),
        "es": Language("es", "Spanish", "Español", False, ["coqui", "melotts", "gemini"]),
        "it": Language("it", "Italian", "Italiano", False, ["coqui", "melotts", "gemini"]),
        "pt": Language("pt", "Portuguese", "Português", False, ["coqui", "melotts", "gemini"]),
        "ru": Language("ru", "Russian", "Русский", False, ["coqui", "melotts"]),
        "zh": Language("zh", "Chinese", "中文", False, ["coqui", "melotts", "gemini"]),
        "ja": Language("ja", "Japanese", "日本語", False, ["coqui", "melotts"]),
        "ko": Language("ko", "Korean", "한국어", False, ["coqui", "melotts"]),
        "hi": Language("hi", "Hindi", "हिन्दी", False, ["coqui"]),
        "tr": Language("tr", "Turkish", "Türkçe", False, ["coqui", "melotts"]),
        "pl": Language("pl", "Polish", "Polski", False, ["coqui", "melotts"]),
        "nl": Language("nl", "Dutch", "Nederlands", False, ["coqui", "melotts"]),
        "fa": Language("fa", "Persian", "فارسی", True, ["piper"]),
        "ur": Language("ur", "Urdu", "اردو", True, []),
        "id": Language("id", "Indonesian", "Bahasa Indonesia", False, ["melotts"]),
        "th": Language("th", "Thai", "ไทย", False, ["melotts"]),
        "vi": Language("vi", "Vietnamese", "Tiếng Việt", False, ["melotts"]),
    }
    
    # Script patterns for detection
    SCRIPT_PATTERNS = {
        "ar": re.compile(r'[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]'),
        "he": re.compile(r'[\u0590-\u05FF]'),
        "fa": re.compile(r'[\u0600-\u06FF\u0750-\u077F]'),
        "ur": re.compile(r'[\u0600-\u06FF]'),
        "zh": re.compile(r'[\u4E00-\u9FFF\u3400-\u4DBF]'),
        "ja": re.compile(r'[\u3040-\u309F\u30A0-\u30FF]'),
        "ko": re.compile(r'[\uAC00-\uD7AF]'),
        "ru": re.compile(r'[\u0400-\u04FF]'),
        "hi": re.compile(r'[\u0900-\u097F]'),
        "th": re.compile(r'[\u0E00-\u0E7F]'),
        "el": re.compile(r'[\u0370-\u03FF]'),
    }
    
    def __init__(self):
        self._active_languages = set(["ar", "en"])
    
    def list_languages(self) -> List[Dict[str, Any]]:
        """List all supported languages"""
        return [
            {
                "code": lang.code,
                "name": lang.name,
                "name_native": lang.name_native,
                "rtl": lang.rtl,
                "supported_engines": lang.supported_engines,
                "is_beta": lang.is_beta,
                "is_active": lang.code in self._active_languages,
            }
            for lang in self.LANGUAGES.values()
        ]
    
    def get_language(self, code: str) -> Optional[Dict[str, Any]]:
        """Get language information"""
        lang = self.LANGUAGES.get(code)
        if lang:
            return {
                "code": lang.code,
                "name": lang.name,
                "name_native": lang.name_native,
                "rtl": lang.rtl,
                "supported_engines": lang.supported_engines,
            }
        return None
    
    def is_rtl(self, code: str) -> bool:
        """Check if language is RTL"""
        lang = self.LANGUAGES.get(code)
        return lang.rtl if lang else False
    
    def detect_language(self, text: str) -> Dict[str, Any]:
        """Detect language from text"""
        if not text or not text.strip():
            return {"code": "en", "confidence": 0, "method": "empty"}
        
        text = text.strip()
        
        # Check script patterns
        for lang_code, pattern in self.SCRIPT_PATTERNS.items():
            if pattern.search(text):
                confidence = min(100, len(pattern.findall(text)) / len(text) * 200)
                return {
                    "code": lang_code,
                    "confidence": round(confidence, 1),
                    "method": "script",
                    "language": self.LANGUAGES.get(lang_code, Language(lang_code, lang_code, lang_code)).name,
                }
        
        # Fallback to Latin script languages
        # Simple heuristic: check for common words
        text_lower = text.lower()
        
        # Arabic words commonly used in Latin script
        arabic_words = ["marhaba", "salam", "shukran", "inshallah", "habibi", "al"]
        if any(word in text_lower for word in arabic_words):
            return {"code": "ar", "confidence": 60, "method": "keyword", "language": "Arabic"}
        
        # Default to English for Latin script
        return {"code": "en", "confidence": 50, "method": "default", "language": "English"}
    
    def get_supported_engines(self, language_code: str) -> List[str]:
        """Get engines supporting a language"""
        lang = self.LANGUAGES.get(language_code)
        return lang.supported_engines if lang else []
    
    def get_best_engine(self, language_code: str) -> Optional[str]:
        """Get the best engine for a language"""
        engines = self.get_supported_engines(language_code)
        if not engines:
            return None
        
        # Priority order
        priority = ["kokoro", "piper", "coqui", "melotts", "gemini"]
        for eng in priority:
            if eng in engines:
                return eng
        
        return engines[0]
    
    def activate_language(self, code: str) -> bool:
        """Activate a language"""
        if code in self.LANGUAGES:
            self._active_languages.add(code)
            return True
        return False
    
    def deactivate_language(self, code: str) -> bool:
        """Deactivate a language"""
        self._active_languages.discard(code)
        return True
    
    def get_active_languages(self) -> List[str]:
        """Get list of active languages"""
        return list(self._active_languages)
    
    def validate_text(self, text: str, language_code: str) -> Dict[str, Any]:
        """Validate text for a language"""
        detected = self.detect_language(text)
        
        is_match = detected["code"] == language_code
        
        return {
            "valid": is_match or detected["confidence"] < 70,
            "detected_language": detected["code"],
            "detected_confidence": detected["confidence"],
            "expected_language": language_code,
            "is_match": is_match,
            "text_length": len(text),
            "word_count": len(text.split()),
        }


# Global language manager
language_manager = LanguageManager()
