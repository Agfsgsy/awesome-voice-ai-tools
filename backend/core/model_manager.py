"""Enhanced Model Manager - Full Model Lifecycle Management"""
import os
import json
import hashlib
import urllib.request
import urllib.error
from pathlib import Path
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
import asyncio

from backend.core.config import settings
from backend.core.logger import get_logger

logger = get_logger("model_manager")


class ModelStatus(str, Enum):
    AVAILABLE = "available"
    DOWNLOADING = "downloading"
    DOWNLOADED = "downloaded"
    ERROR = "error"
    VERIFYING = "verifying"
    OUTDATED = "outdated"
    IMPORTED = "imported"


@dataclass
class ModelInfo:
    """Comprehensive model information"""
    id: str
    name: str
    engine: str
    version: str = "1.0.0"
    description: str = ""
    language: str = "ar"
    size_mb: float = 0.0
    url: str = ""
    checksum: str = ""
    status: ModelStatus = ModelStatus.AVAILABLE
    downloaded_path: str = ""
    download_progress: float = 0.0
    download_speed: str = ""
    created_at: str = ""
    updated_at: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)
    is_default: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        return data


class ModelManager:
    """Production-grade model manager with download resume, checksums, and full lifecycle"""
    
    def __init__(self):
        self.models_dir = settings.MODELS_DIR
        self.registry_file = settings.MODEL_REGISTRY_FILE
        self.downloads_dir = settings.DOWNLOADS_DIR
        self.registry: Dict[str, ModelInfo] = {}
        self._callbacks: List[Callable] = []
        self._load_registry()
    
    def _load_registry(self):
        """Load model registry from file"""
        if self.registry_file.exists():
            try:
                with open(self.registry_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for model_id, info in data.items():
                    self.registry[model_id] = ModelInfo(**info)
            except Exception as e:
                logger.warning(f"Failed to load model registry: {e}")
    
    def _save_registry(self):
        """Save model registry to file"""
        try:
            self.registry_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.registry_file, "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self.registry.items()}, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to save model registry: {e}")
    
    def _compute_checksum(self, filepath: Path) -> str:
        """Compute SHA-256 checksum of file"""
        sha256 = hashlib.sha256()
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()
    
    def _verify_checksum(self, filepath: Path, expected: str) -> bool:
        """Verify file checksum"""
        if not expected:
            return True
        actual = self._compute_checksum(filepath)
        return actual.lower() == expected.lower()
    
    def register_model(self, model_info: ModelInfo) -> bool:
        """Register a model in the registry"""
        model_info.created_at = datetime.utcnow().isoformat()
        self.registry[model_info.id] = model_info
        self._save_registry()
        logger.info(f"Registered model: {model_info.id}")
        return True
    
    def unregister_model(self, model_id: str) -> bool:
        """Unregister a model"""
        if model_id in self.registry:
            del self.registry[model_id]
            self._save_registry()
            logger.info(f"Unregistered model: {model_id}")
            return True
        return False
    
    def list_all_models(self) -> List[Dict[str, Any]]:
        """List all registered models with plugin-discovered models"""
        all_models = []
        
        # Add plugin-discovered models
        try:
            from backend.core.tts_registry import tts_registry
            plugins = tts_registry.get_all_plugins()
            for plugin in plugins:
                try:
                    models = plugin.list_models()
                    for m in models:
                        m["engine"] = plugin.name
                        m["source"] = "plugin"
                        all_models.append(m)
                except Exception as e:
                    logger.warning(f"Failed to list models for {plugin.name}: {e}")
        except Exception:
            pass
        
        # Add registry models
        for model in self.registry.values():
            model_dict = model.to_dict()
            model_dict["source"] = "registry"
            all_models.append(model_dict)
        
        return all_models
    
    def list_downloaded_models(self) -> List[Dict[str, Any]]:
        """List only downloaded models"""
        all_models = self.list_all_models()
        return [m for m in all_models if m.get("downloaded") or m.get("status") == ModelStatus.DOWNLOADED.value]
    
    def search_models(self, query: str = "", engine: str = "", language: str = "", tags: List[str] = None) -> List[Dict[str, Any]]:
        """Search models with filters"""
        models = self.list_all_models()
        results = []
        
        query_lower = query.lower() if query else ""
        
        for model in models:
            # Text search
            if query_lower:
                searchable = f"{model.get('name', '')} {model.get('description', '')} {model.get('engine', '')}"
                if query_lower not in searchable.lower():
                    continue
            
            # Engine filter
            if engine and model.get("engine") != engine:
                continue
            
            # Language filter
            if language and model.get("language") != language:
                continue
            
            # Tags filter
            if tags:
                model_tags = model.get("tags", [])
                if not any(tag in model_tags for tag in tags):
                    continue
            
            results.append(model)
        
        return results
    
    def download_model(self, engine: str, model_name: str = "default", 
                       progress_callback: Optional[Callable] = None) -> Dict[str, Any]:
        """Download a model with progress tracking and resume support"""
        # Find the model
        model_id = f"{engine}/{model_name}"
        model_info = self.registry.get(model_id)
        
        if not model_info:
            # Try to find in plugin
            try:
                from backend.core.tts_registry import tts_registry
                plugin = tts_registry.get_plugin(engine)
                if plugin:
                    return plugin.download_models(model_name)
            except Exception:
                pass
            return {"success": False, "message": f"Model '{model_name}' for engine '{engine}' not found"}
        
        # Set downloading status
        model_info.status = ModelStatus.DOWNLOADING
        
        try:
            target_path = self.models_dir / engine / model_name
            target_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Check for partial download
            partial_path = target_path.with_suffix(target_path.suffix + ".part")
            resume_byte_pos = partial_path.stat().st_size if partial_path.exists() else 0
            
            # Download with progress
            headers = {}
            if resume_byte_pos > 0:
                headers["Range"] = f"bytes={resume_byte_pos}-"
                logger.info(f"Resuming download from byte {resume_byte_pos}")
            
            req = urllib.request.Request(model_info.url, headers=headers)
            
            with urllib.request.urlopen(req, timeout=300) as response:
                total_size = int(response.headers.get("Content-Length", 0)) + resume_byte_pos
                downloaded = resume_byte_pos
                
                with open(partial_path, "ab" if resume_byte_pos else "wb") as f:
                    while True:
                        chunk = response.read(8192)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)
                        
                        if total_size > 0:
                            progress = (downloaded / total_size) * 100
                            model_info.download_progress = round(progress, 1)
                            
                            if progress_callback:
                                progress_callback(model_id, progress)
            
            # Move from partial to final
            partial_path.rename(target_path)
            
            # Verify checksum
            if model_info.checksum:
                model_info.status = ModelStatus.VERIFYING
                if not self._verify_checksum(target_path, model_info.checksum):
                    target_path.unlink()
                    model_info.status = ModelStatus.ERROR
                    self._save_registry()
                    return {"success": False, "message": "Checksum verification failed"}
            
            model_info.status = ModelStatus.DOWNLOADED
            model_info.downloaded_path = str(target_path)
            model_info.download_progress = 100.0
            model_info.updated_at = datetime.utcnow().isoformat()
            self._save_registry()
            
            logger.info(f"Downloaded model: {model_id}")
            return {
                "success": True,
                "model": model_id,
                "path": str(target_path),
                "size_mb": round(target_path.stat().st_size / (1024*1024), 2),
                "verified": bool(model_info.checksum),
            }
            
        except Exception as e:
            model_info.status = ModelStatus.ERROR
            self._save_registry()
            logger.error(f"Download failed for {model_id}: {e}")
            return {"success": False, "model": model_id, "message": str(e)}
    
    async def download_model_async(self, engine: str, model_name: str = "default") -> Dict[str, Any]:
        """Async wrapper for model download"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.download_model, engine, model_name)
    
    def delete_model(self, engine: str, model_name: str) -> Dict[str, Any]:
        """Delete a downloaded model"""
        model_id = f"{engine}/{model_name}"
        model_info = self.registry.get(model_id)
        
        deleted_files = []
        
        # Delete from disk
        engine_dir = self.models_dir / engine
        if engine_dir.exists():
            for f in engine_dir.iterdir():
                if model_name in f.name:
                    f.unlink()
                    deleted_files.append(str(f))
        
        # Update registry
        if model_info:
            model_info.status = ModelStatus.AVAILABLE
            model_info.downloaded_path = ""
            model_info.download_progress = 0.0
            self._save_registry()
        
        logger.info(f"Deleted model: {model_id}")
        return {"success": True, "deleted": deleted_files}
    
    def verify_model(self, engine: str, model_name: str) -> Dict[str, Any]:
        """Verify a downloaded model's integrity"""
        model_id = f"{engine}/{model_name}"
        model_info = self.registry.get(model_id)
        
        if not model_info or not model_info.downloaded_path:
            return {"success": False, "message": "Model not downloaded"}
        
        filepath = Path(model_info.downloaded_path)
        if not filepath.exists():
            return {"success": False, "message": "Model file not found"}
        
        checksum = self._compute_checksum(filepath)
        
        return {
            "success": True,
            "model": model_id,
            "checksum": checksum,
            "expected": model_info.checksum,
            "verified": not model_info.checksum or checksum.lower() == model_info.checksum.lower(),
            "size_mb": round(filepath.stat().st_size / (1024*1024), 2),
        }
    
    def import_model(self, filepath: Path, engine: str, model_name: str, 
                     metadata: Optional[Dict] = None) -> Dict[str, Any]:
        """Import a model from local file"""
        if not filepath.exists():
            return {"success": False, "message": "File not found"}
        
        target_dir = self.models_dir / engine
        target_dir.mkdir(parents=True, exist_ok=True)
        
        target_path = target_dir / filepath.name
        
        # Copy file
        import shutil
        shutil.copy2(filepath, target_path)
        
        # Register
        model_id = f"{engine}/{model_name}"
        model_info = ModelInfo(
            id=model_id,
            name=model_name,
            engine=engine,
            status=ModelStatus.IMPORTED,
            downloaded_path=str(target_path),
            size_mb=round(target_path.stat().st_size / (1024*1024), 2),
            checksum=self._compute_checksum(target_path),
            metadata=metadata or {},
            created_at=datetime.utcnow().isoformat(),
        )
        self.register_model(model_info)
        
        logger.info(f"Imported model: {model_id}")
        return {"success": True, "model": model_id, "path": str(target_path)}
    
    def export_model(self, engine: str, model_name: str, export_dir: Optional[Path] = None) -> Dict[str, Any]:
        """Export a model to a directory"""
        model_id = f"{engine}/{model_name}"
        model_info = self.registry.get(model_id)
        
        if not model_info or not model_info.downloaded_path:
            return {"success": False, "message": "Model not downloaded"}
        
        source = Path(model_info.downloaded_path)
        if not source.exists():
            return {"success": False, "message": "Model file not found"}
        
        export_path = (export_dir or self.downloads_dir) / f"{engine}_{model_name}{source.suffix}"
        export_path.parent.mkdir(parents=True, exist_ok=True)
        
        import shutil
        shutil.copy2(source, export_path)
        
        # Export metadata
        meta_path = export_path.with_suffix(".json")
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(model_info.to_dict(), f, ensure_ascii=False, indent=2)
        
        logger.info(f"Exported model: {model_id} to {export_path}")
        return {"success": True, "model": model_id, "export_path": str(export_path)}
    
    def get_model_info(self, engine: str, model_name: str) -> Dict[str, Any]:
        """Get detailed model information"""
        model_id = f"{engine}/{model_name}"
        model_info = self.registry.get(model_id)
        
        if model_info:
            return model_info.to_dict()
        
        # Try plugin
        try:
            from backend.core.tts_registry import tts_registry
            plugin = tts_registry.get_plugin(engine)
            if plugin:
                models = plugin.list_models()
                for m in models:
                    if m.get("name") == model_name:
                        return m
        except Exception:
            pass
        
        return {"found": False}
    
    def update_model_metadata(self, engine: str, model_name: str, metadata: Dict[str, Any]) -> bool:
        """Update model metadata"""
        model_id = f"{engine}/{model_name}"
        if model_id not in self.registry:
            return False
        
        self.registry[model_id].metadata.update(metadata)
        self.registry[model_id].updated_at = datetime.utcnow().isoformat()
        self._save_registry()
        return True
    
    def get_stats(self) -> Dict[str, Any]:
        """Get model manager statistics"""
        total = len(self.registry)
        downloaded = sum(1 for m in self.registry.values() if m.status == ModelStatus.DOWNLOADED)
        downloading = sum(1 for m in self.registry.values() if m.status == ModelStatus.DOWNLOADING)
        errors = sum(1 for m in self.registry.values() if m.status == ModelStatus.ERROR)
        
        total_size_mb = 0
        for m in self.registry.values():
            if m.downloaded_path and Path(m.downloaded_path).exists():
                total_size_mb += Path(m.downloaded_path).stat().st_size / (1024**2)
        
        return {
            "total_registered": total,
            "downloaded": downloaded,
            "downloading": downloading,
            "errors": errors,
            "available": total - downloaded,
            "total_size_mb": round(total_size_mb, 2),
            "engines": list(set(m.engine for m in self.registry.values())),
        }


# Global model manager instance
model_manager = ModelManager()
