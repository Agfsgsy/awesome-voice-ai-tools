"""مدير الإضافات - اكتشاف وتحميل تلقائي (مؤمن ضد Path Traversal)"""

import os
import re
import importlib.util
import inspect
from pathlib import Path
from typing import Dict, List, Any, Optional

from backend.core.logger import get_logger

logger = get_logger("plugin_manager")

# Allowed plugin name pattern (alphanumeric, underscore, dash only)
PLUGIN_NAME_PATTERN = re.compile(r'^[a-zA-Z0-9_\-]+$')


def validate_plugin_name(name: str) -> bool:
    """Validate plugin name to prevent path traversal and injection"""
    if not name or len(name) > 100:
        return False
    if not PLUGIN_NAME_PATTERN.match(name):
        return False
    # Block path traversal attempts
    if ".." in name or "/" in name or "\\" in name or "\x00" in name:
        return False
    return True


class PluginManager:
    """مدير إضافات بسيط - يكتشف ويحمل ملفات Python تلقائياً (مؤمن)"""

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
                name = f.stem
                if validate_plugin_name(name):
                    plugins.append(name)
                else:
                    logger.warning(f"Skipping invalid plugin name: {name}")
        logger.info(f"Discovered {len(plugins)} plugins: {plugins}")
        return plugins

    def load_plugin(self, name: str) -> bool:
        """تحميل إضافة واحدة (بتحقق من الاسم)"""
        # Validate plugin name
        if not validate_plugin_name(name):
            logger.error(f"Invalid plugin name: {name}")
            return False

        filepath = self.plugins_dir / f"{name}.py"

        # Verify file exists and is within plugins directory (path traversal protection)
        try:
            filepath_resolved = filepath.resolve()
            plugins_resolved = self.plugins_dir.resolve()
            filepath_resolved.relative_to(plugins_resolved)
        except (ValueError, RuntimeError):
            logger.error(f"Path traversal attempt blocked: {filepath}")
            return False

        if not filepath.exists() or not filepath.is_file():
            logger.error(f"Plugin file not found: {filepath}")
            return False

        # Check file size (max 5MB per plugin file)
        try:
            file_size = filepath.stat().st_size
            if file_size > 5 * 1024 * 1024:
                logger.error(f"Plugin file too large: {name} ({file_size} bytes)")
                return False
        except OSError:
            logger.error(f"Cannot stat plugin file: {filepath}")
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

    def unload_plugin(self, name: str) -> bool:
        """Unload a plugin"""
        if name in self.loaded:
            self.loaded.pop(name, None)
            self.registry.pop(name, None)
            logger.info(f"Unloaded plugin: {name}")
            return True
        return False


_plugin_manager: Optional[PluginManager] = None


def init_plugin_manager(plugins_dir: Path) -> PluginManager:
    global _plugin_manager
    if _plugin_manager is None:
        _plugin_manager = PluginManager(plugins_dir)
    return _plugin_manager
