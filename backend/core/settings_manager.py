"""Settings Manager - Persistent Configuration Management"""
import json
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field, asdict
from datetime import datetime

from backend.core.config import settings
from backend.core.logger import get_logger

logger = get_logger("settings_manager")


class SettingsManager:
    """Persistent settings manager with validation"""
    
    # Default settings schema
    DEFAULTS: Dict[str, Any] = {
        "app": {
            "theme": "dark",
            "language": "ar",
            "rtl": True,
            "auto_save": True,
            "confirm_deletions": True,
        },
        "tts": {
            "default_engine": "kokoro",
            "default_language": "ar",
            "default_voice": "default",
            "default_speed": 1.0,
            "default_pitch": 0.0,
            "auto_play": True,
            "cache_results": True,
        },
        "audio": {
            "default_format": "wav",
            "default_sample_rate": 22050,
            "normalization": True,
            "trim_silence": False,
        },
        "plugins": {
            "auto_update": False,
            "allow_custom": True,
            "show_builtin": True,
        },
        "downloads": {
            "default_location": str(settings.DOWNLOADS_DIR),
            "auto_resume": True,
            "verify_checksums": True,
        },
        "security": {
            "enable_auth": False,
            "api_key": "",
            "allowed_hosts": ["*"],
        },
        "advanced": {
            "max_concurrent_tasks": 4,
            "max_memory_cache_mb": 100,
            "log_level": "INFO",
            "debug_mode": False,
        },
    }
    
    def __init__(self):
        self.settings_file = settings.SETTINGS_FILE
        self._settings: Dict[str, Any] = {}
        self._load()
    
    def _load(self):
        """Load settings from file"""
        if self.settings_file.exists():
            try:
                with open(self.settings_file, "r", encoding="utf-8") as f:
                    self._settings = json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load settings: {e}")
                self._settings = {}
        
        # Merge with defaults
        self._merge_defaults()
    
    def _merge_defaults(self):
        """Ensure all default settings exist"""
        for section, values in self.DEFAULTS.items():
            if section not in self._settings:
                self._settings[section] = {}
            for key, default_value in values.items():
                if key not in self._settings[section]:
                    self._settings[section][key] = default_value
    
    def _save(self):
        """Save settings to file"""
        try:
            self.settings_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.settings_file, "w", encoding="utf-8") as f:
                json.dump(self._settings, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to save settings: {e}")
    
    def get(self, section: str, key: str, default: Any = None) -> Any:
        """Get a setting value"""
        return self._settings.get(section, {}).get(key, default)
    
    def set(self, section: str, key: str, value: Any) -> bool:
        """Set a setting value"""
        if section not in self._settings:
            self._settings[section] = {}
        
        self._settings[section][key] = value
        self._save()
        logger.info(f"Setting updated: {section}.{key}")
        return True
    
    def get_section(self, section: str) -> Dict[str, Any]:
        """Get all settings in a section"""
        return self._settings.get(section, {}).copy()
    
    def update_section(self, section: str, values: Dict[str, Any]) -> bool:
        """Update multiple settings in a section"""
        if section not in self._settings:
            self._settings[section] = {}
        
        self._settings[section].update(values)
        self._save()
        logger.info(f"Section updated: {section}")
        return True
    
    def reset_section(self, section: str) -> bool:
        """Reset a section to defaults"""
        if section in self.DEFAULTS:
            self._settings[section] = self.DEFAULTS[section].copy()
            self._save()
            logger.info(f"Section reset: {section}")
            return True
        return False
    
    def reset_all(self) -> bool:
        """Reset all settings to defaults"""
        self._settings = {}
        self._merge_defaults()
        self._save()
        logger.info("All settings reset to defaults")
        return True
    
    def get_all(self) -> Dict[str, Any]:
        """Get all settings"""
        return self._settings.copy()
    
    def export_settings(self, export_path: Optional[Path] = None) -> Dict[str, Any]:
        """Export settings to file"""
        export_file = export_path or (settings.OUTPUTS_DIR / f"settings_export_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json")
        
        try:
            with open(export_file, "w", encoding="utf-8") as f:
                json.dump({
                    "exported_at": datetime.utcnow().isoformat(),
                    "settings": self._settings,
                }, f, ensure_ascii=False, indent=2)
            
            return {"success": True, "path": str(export_file)}
        except Exception as e:
            return {"success": False, "message": str(e)}
    
    def import_settings(self, import_path: Path) -> Dict[str, Any]:
        """Import settings from file"""
        if not import_path.exists():
            return {"success": False, "message": "File not found"}
        
        try:
            with open(import_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            imported = data.get("settings", {})
            self._settings.update(imported)
            self._merge_defaults()
            self._save()
            
            return {"success": True, "imported_sections": list(imported.keys())}
        except Exception as e:
            return {"success": False, "message": str(e)}


# Global settings manager
settings_manager = SettingsManager()
