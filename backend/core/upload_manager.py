"""Upload Manager - Validation, Processing, Organization"""
import os
import json
import hashlib
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum

from backend.core.config import settings
from backend.core.security import validate_audio_file, generate_secure_filename
from backend.core.logger import get_logger

logger = get_logger("upload_manager")


class UploadStatus(str, Enum):
    PENDING = "pending"
    VALIDATING = "validating"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class UploadEntry:
    """Upload entry with metadata"""
    id: str
    original_name: str
    stored_name: str
    filepath: str
    size_bytes: int
    content_type: str
    status: UploadStatus = UploadStatus.PENDING
    checksum: str = ""
    created_at: str = ""
    processed_at: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        data["size_human"] = self._human_size()
        return data
    
    def _human_size(self) -> str:
        size = self.size_bytes
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"


class UploadManager:
    """Upload manager with validation and processing pipeline"""
    
    def __init__(self):
        self.uploads_dir = settings.UPLOADS_DIR
        self.registry_file = settings.CONFIG_DIR / "uploads_registry.json"
        self.entries: Dict[str, UploadEntry] = {}
        self._load_registry()
    
    def _load_registry(self):
        """Load upload registry"""
        if self.registry_file.exists():
            try:
                with open(self.registry_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for edata in data.get("entries", []):
                    entry = UploadEntry(**edata)
                    entry.status = UploadStatus(edata.get("status", "pending"))
                    self.entries[entry.id] = entry
            except Exception as e:
                logger.warning(f"Failed to load upload registry: {e}")
    
    def _save_registry(self):
        """Save upload registry"""
        try:
            self.registry_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.registry_file, "w", encoding="utf-8") as f:
                json.dump({
                    "updated_at": datetime.utcnow().isoformat(),
                    "entries": [e.to_dict() for e in self.entries.values()],
                }, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to save upload registry: {e}")
    
    def _compute_checksum(self, filepath: Path) -> str:
        """Compute SHA-256 checksum"""
        sha256 = hashlib.sha256()
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()
    
    async def process_upload(self, filename: str, content: bytes, 
                            content_type: str = "") -> Dict[str, Any]:
        """Process an uploaded file"""
        import uuid
        
        # Validate
        if not validate_audio_file(filename):
            return {"success": False, "message": f"Unsupported file format. Supported: {settings.SUPPORTED_AUDIO_FORMATS}"}
        
        # Check size
        if len(content) > settings.MAX_UPLOAD_MB * 1024 * 1024:
            return {"success": False, "message": f"File too large. Max: {settings.MAX_UPLOAD_MB}MB"}
        
        # Generate secure filename
        stored_name = generate_secure_filename(filename)
        filepath = self.uploads_dir / stored_name
        
        # Save file
        with open(filepath, "wb") as f:
            f.write(content)
        
        # Create entry
        entry_id = str(uuid.uuid4())[:8]
        entry = UploadEntry(
            id=entry_id,
            original_name=filename,
            stored_name=stored_name,
            filepath=str(filepath),
            size_bytes=len(content),
            content_type=content_type,
            status=UploadStatus.COMPLETED,
            checksum=self._compute_checksum(filepath),
            created_at=datetime.utcnow().isoformat(),
        )
        
        self.entries[entry_id] = entry
        self._save_registry()
        
        logger.info(f"Upload processed: {entry_id} - {filename} ({entry._human_size()})")
        
        return {
            "success": True,
            "id": entry_id,
            "filename": stored_name,
            "original_name": filename,
            "path": str(filepath),
            "size": len(content),
            "size_human": entry._human_size(),
            "checksum": entry.checksum,
        }
    
    def get_entry(self, entry_id: str) -> Optional[Dict[str, Any]]:
        """Get upload entry"""
        entry = self.entries.get(entry_id)
        return entry.to_dict() if entry else None
    
    def list_entries(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """List upload entries"""
        results = []
        for entry in self.entries.values():
            if status and entry.status.value != status:
                continue
            results.append(entry.to_dict())
        
        # Sort by created_at descending
        results.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return results
    
    def delete_entry(self, entry_id: str) -> bool:
        """Delete an upload entry and file"""
        entry = self.entries.get(entry_id)
        if not entry:
            return False
        
        # Delete file
        filepath = Path(entry.filepath)
        if filepath.exists():
            filepath.unlink()
        
        del self.entries[entry_id]
        self._save_registry()
        
        logger.info(f"Upload deleted: {entry_id}")
        return True
    
    def get_stats(self) -> Dict[str, Any]:
        """Get upload statistics"""
        total_size = sum(e.size_bytes for e in self.entries.values())
        
        return {
            "total_files": len(self.entries),
            "total_size_mb": round(total_size / (1024*1024), 2),
            "uploads_dir": str(self.uploads_dir),
        }


# Global upload manager
upload_manager = UploadManager()
