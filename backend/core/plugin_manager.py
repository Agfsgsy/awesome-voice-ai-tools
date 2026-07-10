"""Enhanced Plugin Manager - Full CRUD with Dependencies, Health, Auto-Discovery"""
import importlib.util
import inspect
import json
import hashlib
import asyncio
from pathlib import Path
from typing import Dict, List, Any, Optional, Callable, Set
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum

from backend.core.config import settings
from backend.core.logger import get_logger

logger = get_logger("plugin_manager")


class PluginStatus(str, Enum):
    ACTIVE = "active"
    DISABLED = "disabled"
    ERROR = "error"
    INSTALLING = "installing"
    UNINSTALLING = "uninstalling"
    PENDING = "pending"
    INCOMPATIBLE = "incompatible"


class PluginType(str, Enum):
    TTS = "tts"
    ASR = "asr"
    VAD = "vad"
    EFFECTS = "effects"
    UTILITY = "utility"
    BUILTIN = "builtin"
    CUSTOM = "custom"


@dataclass
class PluginMetadata:
    """Plugin metadata with full information"""
    name: str
    version: str = "0.0.0"
    description: str = ""
    author: str = ""
    homepage: str = ""
    license: str = ""
    plugin_type: PluginType = PluginType.CUSTOM
    requires_gpu: bool = False
    is_open_source: bool = True
    min_app_version: str = "2.0.0"
    dependencies: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    categories: List[str] = field(default_factory=list)
    supported_languages: List[str] = field(default_factory=lambda: ["ar", "en"])
    config_schema: Dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class PluginState:
    """Plugin runtime state"""
    status: PluginStatus = PluginStatus.PENDING
    enabled: bool = True
    loaded: bool = False
    load_time_ms: float = 0.0
    last_error: str = ""
    load_count: int = 0
    call_count: int = 0
    error_count: int = 0
    last_used: Optional[str] = None
    health_status: str = "unknown"
    config: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PluginEntry:
    """Complete plugin entry with metadata and state"""
    metadata: PluginMetadata
    state: PluginState
    module_path: str = ""
    module_hash: str = ""
    instance: Any = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "metadata": self.metadata.to_dict(),
            "state": {
                "status": self.state.status.value,
                "enabled": self.state.enabled,
                "loaded": self.state.loaded,
                "health_status": self.state.health_status,
                "call_count": self.state.call_count,
                "error_count": self.state.error_count,
                "last_used": self.state.last_used,
            },
            "module_path": self.module_path,
        }


class PluginManager:
    """Production-grade plugin manager with full lifecycle management"""
    
    def __init__(self, plugins_dir: Path, state_file: Optional[Path] = None):
        self.plugins_dir = Path(plugins_dir)
        self.state_file = state_file or settings.PLUGINS_STATE_FILE
        self.registry: Dict[str, PluginEntry] = {}
        self.hooks: Dict[str, List[Callable]] = {}
        self._initialized = False
        self._load_state()
    
    def _load_state(self):
        """Load plugin state from persistent storage"""
        if self.state_file.exists():
            try:
                with open(self.state_file, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                for name, data in saved.items():
                    if "enabled" in data:
                        pass  # Will be applied when plugin is loaded
            except Exception as e:
                logger.warning(f"Failed to load plugin state: {e}")
    
    def _save_state(self):
        """Save plugin state to persistent storage"""
        try:
            state = {}
            for name, entry in self.registry.items():
                state[name] = {
                    "enabled": entry.state.enabled,
                    "status": entry.state.status.value,
                    "config": entry.state.config,
                }
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to save plugin state: {e}")
    
    def _compute_hash(self, filepath: Path) -> str:
        """Compute SHA-256 hash of plugin file"""
        sha256 = hashlib.sha256()
        with open(filepath, "rb") as f:
            sha256.update(f.read())
        return sha256.hexdigest()[:16]
    
    def discover(self, plugins_dir: Optional[Path] = None) -> List[Dict[str, str]]:
        """Auto-discover all plugin files in directory"""
        directory = plugins_dir or self.plugins_dir
        if not directory.exists():
            logger.warning(f"Plugins dir not found: {directory}")
            return []
        
        plugins = []
        for f in directory.iterdir():
            if f.suffix == ".py" and not f.name.startswith("_"):
                plugins.append({
                    "name": f.stem,
                    "path": str(f),
                    "hash": self._compute_hash(f),
                    "modified": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
                })
        
        logger.info(f"Discovered {len(plugins)} plugins in {directory}")
        return plugins
    
    def load_plugin(self, name: str, force: bool = False) -> bool:
        """Load a single plugin with full lifecycle"""
        filepath = self.plugins_dir / f"{name}.py"
        if not filepath.exists():
            logger.error(f"Plugin file not found: {filepath}")
            return False
        
        # Check if already loaded
        if name in self.registry and self.registry[name].state.loaded and not force:
            return True
        
        start_time = asyncio.get_event_loop().time() if asyncio.get_event_loop().is_running() else 0
        
        try:
            # Load module
            spec = importlib.util.spec_from_file_location(f"plugin_{name}", filepath)
            if spec is None or spec.loader is None:
                logger.error(f"Cannot load spec for {name}")
                self._set_error(name, "Failed to load module spec")
                return False
            
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            # Extract metadata
            metadata = PluginMetadata(
                name=getattr(module, "PLUGIN_NAME", name),
                version=getattr(module, "__version__", "0.0.0"),
                description=getattr(module, "PLUGIN_DESCRIPTION", ""),
                author=getattr(module, "PLUGIN_AUTHOR", ""),
                homepage=getattr(module, "PLUGIN_HOMEPAGE", ""),
                license=getattr(module, "PLUGIN_LICENSE", "MIT"),
                plugin_type=PluginType(getattr(module, "PLUGIN_TYPE", "custom")) if hasattr(module, "PLUGIN_TYPE") else PluginType.CUSTOM,
                requires_gpu=getattr(module, "REQUIRES_GPU", False),
                is_open_source=getattr(module, "IS_OPEN_SOURCE", True),
                min_app_version=getattr(module, "MIN_APP_VERSION", "2.0.0"),
                dependencies=getattr(module, "PLUGIN_DEPENDENCIES", []),
                tags=getattr(module, "PLUGIN_TAGS", []),
                categories=getattr(module, "PLUGIN_CATEGORIES", []),
                supported_languages=getattr(module, "SUPPORTED_LANGUAGES", ["ar", "en"]),
                config_schema=getattr(module, "CONFIG_SCHEMA", {}),
                created_at=datetime.utcnow().isoformat(),
            )
            
            # Check version compatibility
            if not self._check_compatibility(metadata.min_app_version):
                state = PluginState(
                    status=PluginStatus.INCOMPATIBLE,
                    last_error=f"Requires app version {metadata.min_app_version}+"
                )
                self.registry[name] = PluginEntry(metadata=metadata, state=state, module_path=str(filepath))
                logger.warning(f"Plugin {name} incompatible: requires {metadata.min_app_version}")
                return False
            
            # Create entry
            state = PluginState(status=PluginStatus.ACTIVE, loaded=True, load_count=1)
            
            # Restore saved state
            if self.state_file.exists():
                try:
                    with open(self.state_file, "r") as f:
                        saved = json.load(f)
                    if name in saved:
                        state.enabled = saved[name].get("enabled", True)
                        state.config = saved[name].get("config", {})
                        if not state.enabled:
                            state.status = PluginStatus.DISABLED
                except Exception:
                    pass
            
            entry = PluginEntry(
                metadata=metadata,
                state=state,
                module_path=str(filepath),
                module_hash=self._compute_hash(filepath),
                instance=module,
            )
            
            self.registry[name] = entry
            
            # Run register hook if available
            if hasattr(module, "register"):
                try:
                    module.register()
                except Exception as e:
                    logger.warning(f"Plugin {name} register() failed: {e}")
            
            # Execute hooks
            self._execute_hooks("plugin_loaded", name, entry)
            
            load_time = (asyncio.get_event_loop().time() - start_time) * 1000 if start_time else 0
            entry.state.load_time_ms = round(load_time, 2)
            
            logger.info(f"Loaded plugin: {name} v{metadata.version} ({load_time:.1f}ms)")
            return True
            
        except Exception as e:
            logger.error(f"Failed to load plugin {name}: {e}")
            self._set_error(name, str(e))
            return False
    
    def load_all(self) -> Dict[str, bool]:
        """Load all discovered plugins"""
        discovered = self.discover()
        results = {}
        for plugin_info in discovered:
            name = plugin_info["name"]
            results[name] = self.load_plugin(name)
        
        self._initialized = True
        self._save_state()
        logger.info(f"Plugin loading complete: {sum(results.values())}/{len(results)} loaded")
        return results
    
    def unload_plugin(self, name: str) -> bool:
        """Unload a plugin"""
        if name not in self.registry:
            return False
        
        entry = self.registry[name]
        
        # Run unregister hook if available
        if entry.instance and hasattr(entry.instance, "unregister"):
            try:
                entry.instance.unregister()
            except Exception as e:
                logger.warning(f"Plugin {name} unregister() failed: {e}")
        
        entry.state.loaded = False
        entry.state.status = PluginStatus.PENDING
        entry.instance = None
        
        self._execute_hooks("plugin_unloaded", name, entry)
        logger.info(f"Unloaded plugin: {name}")
        return True
    
    def reload_plugin(self, name: str) -> bool:
        """Reload a plugin"""
        logger.info(f"Reloading plugin: {name}")
        self.unload_plugin(name)
        return self.load_plugin(name, force=True)
    
    def enable_plugin(self, name: str) -> bool:
        """Enable a plugin"""
        if name not in self.registry:
            return False
        self.registry[name].state.enabled = True
        self.registry[name].state.status = PluginStatus.ACTIVE
        self._save_state()
        logger.info(f"Enabled plugin: {name}")
        return True
    
    def disable_plugin(self, name: str) -> bool:
        """Disable a plugin"""
        if name not in self.registry:
            return False
        self.registry[name].state.enabled = False
        self.registry[name].state.status = PluginStatus.DISABLED
        self._save_state()
        logger.info(f"Disabled plugin: {name}")
        return True
    
    def delete_plugin(self, name: str) -> Dict[str, Any]:
        """Delete a plugin completely"""
        if name not in self.registry:
            return {"success": False, "message": f"Plugin '{name}' not found"}
        
        # Check if it's a builtin plugin
        entry = self.registry[name]
        if entry.metadata.plugin_type == PluginType.BUILTIN:
            return {"success": False, "message": "Cannot delete builtin plugins"}
        
        # Unload first
        self.unload_plugin(name)
        
        # Delete file
        filepath = self.plugins_dir / f"{name}.py"
        if filepath.exists():
            filepath.unlink()
        
        # Remove from registry
        del self.registry[name]
        self._save_state()
        
        logger.info(f"Deleted plugin: {name}")
        return {"success": True, "message": f"Plugin '{name}' deleted"}
    
    def install_plugin(self, source: str) -> Dict[str, Any]:
        """Install a plugin from various sources"""
        # Could be: file path, URL, or plugin name from registry
        result = {"success": False, "message": "Installation method not implemented"}
        logger.info(f"Plugin install requested: {source}")
        return result
    
    def update_plugin(self, name: str) -> Dict[str, Any]:
        """Update a plugin to latest version"""
        if name not in self.registry:
            return {"success": False, "message": f"Plugin '{name}' not found"}
        
        # For now, just reload
        success = self.reload_plugin(name)
        return {
            "success": success,
            "message": f"Plugin '{name}' updated and reloaded" if success else f"Failed to update '{name}'"
        }
    
    def check_dependencies(self, name: str) -> Dict[str, Any]:
        """Check if all dependencies for a plugin are met"""
        if name not in self.registry:
            return {"success": False, "message": "Plugin not found", "missing": []}
        
        deps = self.registry[name].metadata.dependencies
        missing = []
        for dep in deps:
            if dep not in self.registry:
                try:
                    __import__(dep)
                except ImportError:
                    missing.append(dep)
        
        return {
            "success": len(missing) == 0,
            "message": "All dependencies met" if not missing else f"Missing: {', '.join(missing)}",
            "missing": missing,
            "dependencies": deps,
        }
    
    def health_check(self, name: str) -> Dict[str, Any]:
        """Run health check on a specific plugin"""
        if name not in self.registry:
            return {"name": name, "status": "not_found", "healthy": False}
        
        entry = self.registry[name]
        
        # Basic checks
        file_exists = Path(entry.module_path).exists()
        is_loaded = entry.state.loaded
        is_enabled = entry.state.enabled
        deps_ok = self.check_dependencies(name)["success"]
        
        healthy = file_exists and is_loaded and is_enabled and deps_ok
        
        result = {
            "name": name,
            "label": entry.metadata.name,
            "version": entry.metadata.version,
            "status": entry.state.status.value,
            "healthy": healthy,
            "checks": {
                "file_exists": file_exists,
                "loaded": is_loaded,
                "enabled": is_enabled,
                "dependencies_ok": deps_ok,
            },
            "metadata": entry.metadata.to_dict(),
        }
        
        entry.state.health_status = "healthy" if healthy else "unhealthy"
        return result
    
    def health_check_all(self) -> List[Dict[str, Any]]:
        """Run health check on all plugins"""
        return [self.health_check(name) for name in self.registry.keys()]
    
    def get_info(self) -> List[Dict[str, Any]]:
        """Get information about all plugins"""
        return [entry.to_dict() for entry in self.registry.values()]
    
    def get_plugin(self, name: str) -> Optional[PluginEntry]:
        """Get a plugin entry"""
        return self.registry.get(name)
    
    def get_plugin_instance(self, name: str) -> Any:
        """Get a plugin's module instance"""
        entry = self.registry.get(name)
        return entry.instance if entry else None
    
    def call_plugin_method(self, name: str, method: str, *args, **kwargs) -> Any:
        """Call a method on a plugin"""
        entry = self.registry.get(name)
        if not entry or not entry.instance:
            raise ValueError(f"Plugin '{name}' not loaded")
        
        if not entry.state.enabled:
            raise RuntimeError(f"Plugin '{name}' is disabled")
        
        func = getattr(entry.instance, method, None)
        if not func:
            raise AttributeError(f"Plugin '{name}' has no method '{method}'")
        
        entry.state.call_count += 1
        entry.state.last_used = datetime.utcnow().isoformat()
        
        try:
            return func(*args, **kwargs)
        except Exception as e:
            entry.state.error_count += 1
            raise
    
    def register_hook(self, event: str, callback: Callable):
        """Register a hook for plugin events"""
        if event not in self.hooks:
            self.hooks[event] = []
        self.hooks[event].append(callback)
    
    def _execute_hooks(self, event: str, *args, **kwargs):
        """Execute all hooks for an event"""
        for hook in self.hooks.get(event, []):
            try:
                hook(*args, **kwargs)
            except Exception as e:
                logger.warning(f"Hook error for {event}: {e}")
    
    def _set_error(self, name: str, message: str):
        """Set error state for a plugin"""
        if name not in self.registry:
            # Create minimal entry for error tracking
            metadata = PluginMetadata(name=name)
            state = PluginState(status=PluginStatus.ERROR, last_error=message)
            self.registry[name] = PluginEntry(metadata=metadata, state=state)
        else:
            self.registry[name].state.status = PluginStatus.ERROR
            self.registry[name].state.last_error = message
    
    def _check_compatibility(self, min_version: str) -> bool:
        """Check if plugin is compatible with current app version"""
        current = tuple(map(int, settings.APP_VERSION.split(".")[:2]))
        required = tuple(map(int, min_version.split(".")[:2]))
        return current >= required
    
    def get_stats(self) -> Dict[str, Any]:
        """Get plugin system statistics"""
        total = len(self.registry)
        loaded = sum(1 for e in self.registry.values() if e.state.loaded)
        enabled = sum(1 for e in self.registry.values() if e.state.enabled)
        active = sum(1 for e in self.registry.values() if e.state.status == PluginStatus.ACTIVE)
        errors = sum(1 for e in self.registry.values() if e.state.status == PluginStatus.ERROR)
        
        return {
            "total": total,
            "loaded": loaded,
            "enabled": enabled,
            "active": active,
            "disabled": total - enabled,
            "errors": errors,
            "by_type": {},
            "total_calls": sum(e.state.call_count for e in self.registry.values()),
            "total_errors": sum(e.state.error_count for e in self.registry.values()),
        }


# Global plugin manager instance
_plugin_manager: Optional[PluginManager] = None


def init_plugin_manager(plugins_dir: Optional[Path] = None) -> PluginManager:
    """Initialize the global plugin manager"""
    global _plugin_manager
    if _plugin_manager is None:
        directory = plugins_dir or settings.PLUGINS_DIR
        _plugin_manager = PluginManager(directory)
    return _plugin_manager


def get_plugin_manager() -> Optional[PluginManager]:
    """Get the global plugin manager instance"""
    return _plugin_manager
