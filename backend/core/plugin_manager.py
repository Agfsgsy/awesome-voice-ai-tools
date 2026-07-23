"""مدير الإضافات - اكتشاف وتحميل تلقائي"""
import importlib.util
from pathlib import Path
from typing import Dict, List, Any, Optional

from backend.core.logger import get_logger

logger = get_logger("plugin_manager")


class PluginManager:
    """مدير إضافات بسيط - يكتشف ويحمل ملفات Python تلقائياً"""

    def __init__(self, plugins_dir: Path):
        self.plugins_dir = Path(plugins_dir)
        self.registry: Dict[str, Dict] = {}
        self.loaded: Dict[str, Any] = {}

    def discover(self) -> List[str]:
        """اكتشاف جميع ملفات الإضافات"""
        if not self.plugins_dir.exists():
            logger.warning(f"Plugins dir not found: {self.plugins_dir}")
            return []
        plugins = []
        for f in self.plugins_dir.iterdir():
            if f.suffix == ".py" and not f.name.startswith("_"):
                plugins.append(f.stem)
        logger.info(f"Discovered {len(plugins)} plugins: {plugins}")
        return plugins

    def load_plugin(self, name: str) -> bool:
        """تحميل إضافة واحدة"""
        filepath = self.plugins_dir / f"{name}.py"
        if not filepath.exists():
            logger.error(f"Plugin file not found: {filepath}")
            return False
        try:
            spec = importlib.util.spec_from_file_location(f"plugin_{name}", filepath)
            if spec is None or spec.loader is None:
                logger.error(f"Cannot load spec for {name}")
                return False
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            info = {
                "name": getattr(module, "PLUGIN_NAME", name),
                "version": getattr(module, "__version__", "0.0.0"),
                "description": getattr(module, "PLUGIN_DESCRIPTION", ""),
                "module": name,
            }
            self.registry[name] = info
            if hasattr(module, "register"):
                module.register()
            self.loaded[name] = module
            logger.info(f"Loaded plugin: {name}")
            return True
        except Exception as e:
            logger.error(f"Failed to load plugin {name}: {e}")
            self.loaded[name] = None
            return False

    def load_all(self) -> None:
        """تحميل جميع الإضافات المكتشفة"""
        plugins = self.discover()
        for name in plugins:
            self.load_plugin(name)

    def reload_all(self) -> None:
        """إعادة اكتشاف وتحميل جميع الإضافات لتحديث السجل"""
        logger.info("Reloading all plugins...")
        self.registry.clear()
        self.loaded.clear()
        self.load_all()

    def get_info(self) -> List[Dict]:
        """معلومات عن جميع الإضافات"""
        result = []
        for name, info in self.registry.items():
            result.append({
                "name": info["name"],
                "version": info["version"],
                "description": info["description"],
                "module": name,
                "loaded": name in self.loaded and self.loaded[name] is not None,
            })
        return result


_plugin_manager: Optional[PluginManager] = None


def init_plugin_manager(plugins_dir: Path) -> PluginManager:
    global _plugin_manager
    if _plugin_manager is None:
        _plugin_manager = PluginManager(plugins_dir)
    return _plugin_manager
