"""سجل محركات TTS - نظام كشف وتحديد تلقائي للمحركات المتاحة"""
from typing import Dict, List, Any, Optional
from pathlib import Path
from backend.core.logger import get_logger
from backend.core.config import ENGINE_PRIORITY

logger = get_logger("tts_registry")


class TTSRegistry:
    """سجل موحد لجميع محركات TTS - يكتشف ويختار المحرك المتاح تلقائياً"""

    def __init__(self):
        self.plugins: Dict[str, Any] = {}
        self.priority = ENGINE_PRIORITY
        self._initialized = False

    def register(self, name: str, plugin_instance) -> None:
        """تسجيل إضافة TTS"""
        self.plugins[name] = plugin_instance
        logger.info(f"Registered TTS plugin: {name}")

    def get_all_plugins(self) -> List:
        """الحصول على جميع الإضافات المسجلة"""
        if not self._initialized:
            self.initialize()
        return list(self.plugins.values())

    def get_plugin(self, name: str):
        """الحصول على إضافة محددة"""
        if not self._initialized:
            self.initialize()
        return self.plugins.get(name)

    def get_available_engines(self) -> List[Dict]:
        """الحصول على المحركات المتاحة فعلياً"""
        if not self._initialized:
            self.initialize()
        available = []
        for name, plugin in self.plugins.items():
            try:
                installed = plugin.check()
                if installed:
                    available.append({
                        "name": plugin.name,
                        "label": plugin.label,
                        "installed": True,
                        "models": plugin.list_models(),
                    })
            except Exception as e:
                logger.warning(f"Error checking {name}: {e}")
        return available

    def auto_select_engine(self) -> Optional[str]:
        """اختيار المحرك المتاح تلقائياً حسب الأولوية"""
        if not self._initialized:
            self.initialize()
        for name in self.priority:
            plugin = self.plugins.get(name)
            if plugin:
                try:
                    if plugin.check():
                        # Verify at least one model is downloaded
                        models = plugin.list_models()
                        downloaded = [m for m in models if m.get("downloaded")]
                        if downloaded:
                            logger.info(f"Auto-selected engine: {name}")
                            return name
                except Exception:
                    continue
        logger.warning("No TTS engine available with downloaded models")
        return None

    def initialize(self) -> None:
        """تهيئة وتسجيل جميع إضافات TTS"""
        if self._initialized:
            return
        try:
            from backend.plugins.piper_plugin import PiperPlugin
            self.register("piper", PiperPlugin())
        except Exception as e:
            logger.warning(f"Failed to register Piper: {e}")
        try:
            from backend.plugins.coqui_plugin import CoquiPlugin
            self.register("coqui", CoquiPlugin())
        except Exception as e:
            logger.warning(f"Failed to register Coqui: {e}")
        try:
            from backend.plugins.kokoro_plugin import KokoroPlugin
            self.register("kokoro", KokoroPlugin())
        except Exception as e:
            logger.warning(f"Failed to register Kokoro: {e}")
        try:
            from backend.plugins.melotts_plugin import MeloTTSPlugin
            self.register("melotts", MeloTTSPlugin())
        except Exception as e:
            logger.warning(f"Failed to register MeloTTS: {e}")
        try:
            from backend.plugins.styletts2_plugin import StyleTTS2Plugin
            self.register("styletts2", StyleTTS2Plugin())
        except Exception as e:
            logger.warning(f"Failed to register StyleTTS2: {e}")

        self._initialized = True
        logger.info(f"TTS Registry initialized with {len(self.plugins)} plugins: {list(self.plugins.keys())}")


tts_registry = TTSRegistry()
