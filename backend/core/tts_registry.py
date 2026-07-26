"""سجل محركات TTS - نظام كشف وتحديد تلقائي للمحركات المتاحة"""
from typing import Dict, List, Any, Optional
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
        self.plugins[name] = plugin_instance
        logger.info(f"Registered TTS plugin: {name}")

    def get_all_plugins(self) -> List:
        if not self._initialized:
            self.initialize()
        return list(self.plugins.values())

    def get_plugin(self, name: str):
        if not self._initialized:
            self.initialize()
        return self.plugins.get(name)

    def get_available_engines(self) -> List[Dict]:
        if not self._initialized:
            self.initialize()
        available = []
        for name, plugin in self.plugins.items():
            try:
                if plugin.check():
                    available.append({
                        "name": plugin.name,
                        "label": plugin.label,
                        "installed": True,
                        "models": plugin.list_models(),
                        "voices": plugin.list_voices(),
                    })
            except Exception as exc:
                logger.warning(f"Error checking {name}: {exc}")
        return available

    def auto_select_engine(self) -> Optional[str]:
        if not self._initialized:
            self.initialize()
        for name in self.priority:
            plugin = self.plugins.get(name)
            if not plugin:
                continue
            try:
                if not plugin.check():
                    continue
                models = plugin.list_models()
                if any(model.get("downloaded") for model in models):
                    logger.info(f"Auto-selected engine: {name}")
                    return name
            except Exception as exc:
                logger.warning(f"Engine selection failed for {name}: {exc}")
        logger.warning("No usable TTS engine is available")
        return None

    def initialize(self) -> None:
        if self._initialized:
            return

        plugin_specs = [
            ("elevenlabs", "backend.plugins.elevenlabs_plugin", "ElevenLabsPlugin"),
            ("edge", "backend.plugins.edge_plugin", "EdgeTTSPlugin"),
            ("piper", "backend.plugins.piper_plugin", "PiperPlugin"),
            ("coqui", "backend.plugins.coqui_plugin", "CoquiPlugin"),
            ("kokoro", "backend.plugins.kokoro_plugin", "KokoroPlugin"),
            ("melotts", "backend.plugins.melotts_plugin", "MeloTTSPlugin"),
            ("styletts2", "backend.plugins.styletts2_plugin", "StyleTTS2Plugin"),
        ]
        for name, module_name, class_name in plugin_specs:
            try:
                module = __import__(module_name, fromlist=[class_name])
                plugin_class = getattr(module, class_name)
                self.register(name, plugin_class())
            except Exception as exc:
                logger.warning(f"Failed to register {name}: {exc}")

        self._initialized = True
        logger.info(
            f"TTS Registry initialized with {len(self.plugins)} plugins: {list(self.plugins.keys())}"
        )


tts_registry = TTSRegistry()
