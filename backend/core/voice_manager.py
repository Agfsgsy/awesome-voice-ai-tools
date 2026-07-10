"""مدير الأصوات - إدارة الأصوات المتاحة من جميع المحركات"""
from typing import Dict, List, Any
from pathlib import Path
from backend.core.logger import get_logger
from backend.core.config import VOICES_DIR

logger = get_logger("voice_manager")


class VoiceManager:
    """إدارة الأصوات من جميع محركات TTS"""

    def __init__(self):
        self.voices_dir = VOICES_DIR

    def list_all_voices(self) -> List[Dict]:
        """عرض جميع الأصوات من جميع المحركات"""
        all_voices = []
        plugins = self._get_plugins()
        for plugin in plugins:
            try:
                voices = plugin.list_voices()
                for v in voices:
                    v["engine"] = plugin.name
                    all_voices.append(v)
            except Exception as e:
                logger.warning(f"Failed to list voices for {plugin.name}: {e}")
        return all_voices

    def list_voices_by_language(self, language: str) -> List[Dict]:
        """عرض الأصوات بلغة معينة"""
        return [v for v in self.list_all_voices() if v.get("language") == language]

    def list_arabic_voices(self) -> List[Dict]:
        """عرض الأصوات العربية"""
        return self.list_voices_by_language("ar")

    def list_voices_by_engine(self, engine: str) -> List[Dict]:
        """عرض أصوات محرك معين"""
        plugin = self._get_plugin(engine)
        if not plugin:
            return []
        try:
            return plugin.list_voices()
        except Exception as e:
            logger.warning(f"Failed to list voices for {engine}: {e}")
            return []

    def _get_plugins(self) -> List:
        from backend.core.tts_registry import tts_registry
        return tts_registry.get_all_plugins()

    def _get_plugin(self, name: str):
        from backend.core.tts_registry import tts_registry
        return tts_registry.get_plugin(name)


voice_manager = VoiceManager()
