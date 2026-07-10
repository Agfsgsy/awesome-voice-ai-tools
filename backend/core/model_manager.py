"""مدير النماذج - إدارة تحميل وفحص نماذج TTS"""
from typing import Dict, List, Any
from pathlib import Path
from backend.core.logger import get_logger
from backend.core.config import MODELS_DIR

logger = get_logger("model_manager")


class ModelManager:
    """إدارة نماذج TTS - تحميل، فحص، قائمة"""

    def __init__(self):
        self.models_dir = MODELS_DIR

    def list_all_models(self) -> List[Dict]:
        """عرض جميع النماذج من جميع المحركات"""
        all_models = []
        plugins = self._get_plugins()
        for plugin in plugins:
            try:
                models = plugin.list_models()
                for m in models:
                    m["engine"] = plugin.name
                    all_models.append(m)
            except Exception as e:
                logger.warning(f"Failed to list models for {plugin.name}: {e}")
        return all_models

    def list_downloaded_models(self) -> List[Dict]:
        """عرض النماذج المحملة فقط"""
        return [m for m in self.list_all_models() if m.get("downloaded")]

    def download_model(self, engine: str, model_name: str = "default") -> Dict[str, Any]:
        """تحميل نموذج لمحرك معين"""
        plugin = self._get_plugin(engine)
        if not plugin:
            return {"success": False, "message": f"Engine '{engine}' not found"}
        try:
            return plugin.download_models(model_name)
        except Exception as e:
            return {"success": False, "message": str(e)}

    def get_model_info(self, engine: str, model_name: str) -> Dict:
        """معلومات عن نموذج معين"""
        plugin = self._get_plugin(engine)
        if not plugin:
            return {"found": False}
        models = plugin.list_models()
        for m in models:
            if m["name"] == model_name:
                return m
        return {"found": False}

    def delete_model(self, engine: str, model_name: str) -> Dict[str, Any]:
        """حذف نموذج"""
        plugin = self._get_plugin(engine)
        if not plugin:
            return {"success": False, "message": f"Engine '{engine}' not found"}
        # Find and delete model files
        engine_dir = self.models_dir / engine
        deleted = []
        if engine_dir.exists():
            for f in engine_dir.iterdir():
                if model_name in f.name:
                    f.unlink()
                    deleted.append(str(f))
        return {"success": True, "deleted": deleted}

    def _get_plugins(self) -> List:
        """الحصول على جميع إضافات TTS"""
        from backend.core.tts_registry import tts_registry
        return tts_registry.get_all_plugins()

    def _get_plugin(self, name: str):
        """الحصول على إضافة محددة"""
        from backend.core.tts_registry import tts_registry
        return tts_registry.get_plugin(name)


model_manager = ModelManager()
