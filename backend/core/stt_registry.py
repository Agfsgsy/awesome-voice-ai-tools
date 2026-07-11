"""سجل محركات STT - نظام كشف وتحديد تلقائي للمحركات المتاحة"""
from typing import Dict, List, Any, Optional
from pathlib import Path
from backend.core.logger import get_logger

logger = get_logger("stt_registry")

class STTRegistry:
    """سجل موحد لجميع محركات STT"""

    def __init__(self):
        self.plugins: Dict[str, Any] = {}
        self._initialized = False

    def register(self, name: str, plugin_instance) -> None:
        """تسجيل إضافة STT"""
        self.plugins[name] = plugin_instance
        logger.info(f"Registered STT plugin: {name}")

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

    def initialize(self):
        """اكتشاف وتحميل جميع إضافات STT"""
        if self._initialized:
            return

        from backend.core.config import BACKEND_DIR
        import importlib.util

        plugins_dir = BACKEND_DIR / "plugins"
        if not plugins_dir.exists():
            return

        for f in plugins_dir.iterdir():
            if f.suffix == ".py" and not f.name.startswith("_"):
                try:
                    spec = importlib.util.spec_from_file_location(f"stt_plugin_{f.stem}", f)
                    if spec and spec.loader:
                        module = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(module)
                        if hasattr(module, "PLUGIN_CLASS"):
                            plugin_class = getattr(module, "PLUGIN_CLASS")
                            from backend.plugins.stt_plugin_base import STTPluginBase
                            if issubclass(plugin_class, STTPluginBase) and plugin_class is not STTPluginBase:
                                instance = plugin_class()
                                self.register(instance.name, instance)
                except Exception as e:
                    logger.error(f"Error loading STT plugin {f.name}: {e}")

        self._initialized = True
        logger.info(f"STT Registry initialized with {len(self.plugins)} plugins: {list(self.plugins.keys())}")

stt_registry = STTRegistry()
