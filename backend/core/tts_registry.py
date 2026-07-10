"""Enhanced TTS Registry - Auto-Discovery, Health Checks, Priority System"""
from typing import Dict, List, Any, Optional
from pathlib import Path
from backend.core.logger import get_logger
from backend.core.config import settings

logger = get_logger("tts_registry")


class TTSRegistry:
    """Enhanced TTS registry with health checks and auto-selection"""

    def __init__(self):
        self.plugins: Dict[str, Any] = {}
        self.priority = settings.ENGINE_PRIORITY
        self._initialized = False
        self._health_cache: Dict[str, Dict] = {}

    def register(self, name: str, plugin_instance) -> None:
        """Register a TTS plugin"""
        self.plugins[name] = plugin_instance
        logger.info(f"Registered TTS plugin: {name}")

    def unregister(self, name: str) -> bool:
        """Unregister a TTS plugin"""
        if name in self.plugins:
            del self.plugins[name]
            logger.info(f"Unregistered TTS plugin: {name}")
            return True
        return False

    def get_all_plugins(self) -> List:
        """Get all registered plugins"""
        if not self._initialized:
            self.initialize()
        return list(self.plugins.values())

    def get_plugin(self, name: str):
        """Get a specific plugin"""
        if not self._initialized:
            self.initialize()
        return self.plugins.get(name)

    def get_available_engines(self) -> List[Dict]:
        """Get all available engines with health info"""
        if not self._initialized:
            self.initialize()

        available = []
        for name, plugin in self.plugins.items():
            try:
                health = self._get_plugin_health(name, plugin)
                if health.get("installed"):
                    available.append(health)
            except Exception as e:
                logger.warning(f"Health check failed for {name}: {e}")

        # Sort by priority
        priority_map = {name: i for i, name in enumerate(self.priority)}
        available.sort(key=lambda e: priority_map.get(e["name"], 999))

        return available

    def _get_plugin_health(self, name: str, plugin) -> Dict:
        """Get comprehensive health info for a plugin"""
        try:
            installed = plugin.check()
            models = plugin.list_models() if hasattr(plugin, "list_models") else []
            voices = plugin.list_voices() if hasattr(plugin, "list_voices") else []
            downloaded_models = [m for m in models if m.get("downloaded")]

            return {
                "name": plugin.name,
                "label": plugin.label,
                "installed": installed,
                "models_count": len(models),
                "downloaded_models": len(downloaded_models),
                "voices_count": len(voices),
                "ready": installed and len(downloaded_models) > 0,
                "requires_gpu": getattr(plugin, "requires_gpu", False),
                "is_open_source": getattr(plugin, "is_open_source", True),
                "description": getattr(plugin, "description", ""),
                "homepage": getattr(plugin, "homepage", ""),
            }
        except Exception as e:
            return {
                "name": name,
                "label": name,
                "installed": False,
                "error": str(e),
                "ready": False,
            }

    def auto_select_engine(self) -> Optional[str]:
        """Auto-select best available engine"""
        if not self._initialized:
            self.initialize()

        for name in self.priority:
            plugin = self.plugins.get(name)
            if plugin:
                try:
                    if plugin.check():
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
        """Initialize and register all TTS plugins"""
        if self._initialized:
            return

        plugins_to_register = [
            ("piper", "backend.plugins.piper_plugin", "PiperPlugin"),
            ("coqui", "backend.plugins.coqui_plugin", "CoquiPlugin"),
            ("kokoro", "backend.plugins.kokoro_plugin", "KokoroPlugin"),
            ("melotts", "backend.plugins.melotts_plugin", "MeloTTSPlugin"),
            ("styletts2", "backend.plugins.styletts2_plugin", "StyleTTS2Plugin"),
            ("f5", "backend.plugins.f5_plugin", "F5Plugin"),
            ("fish", "backend.plugins.fish_plugin", "FishPlugin"),
            ("cosyvoice", "backend.plugins.cosyvoice_plugin", "CosyVoicePlugin"),
            ("parler", "backend.plugins.parler_plugin", "ParlerPlugin"),
            ("openvoice", "backend.plugins.openvoice_plugin", "OpenVoicePlugin"),
        ]

        for name, module_path, class_name in plugins_to_register:
            try:
                module = __import__(module_path, fromlist=[class_name])
                plugin_class = getattr(module, class_name)
                self.register(name, plugin_class())
            except Exception as e:
                logger.debug(f"Plugin {name} not available: {e}")

        self._initialized = True
        logger.info(f"TTS Registry initialized: {len(self.plugins)} plugins")

    def get_stats(self) -> Dict[str, Any]:
        """Get registry statistics"""
        return {
            "total_plugins": len(self.plugins),
            "available": len(self.get_available_engines()),
            "plugins": list(self.plugins.keys()),
            "priority": self.priority,
        }


tts_registry = TTSRegistry()
