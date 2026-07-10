"""Output Manager - File Organization and Management"""
import os
import json
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta

from backend.core.config import settings
from backend.core.logger import get_logger

logger = get_logger("output_manager")


class OutputManager:
    """Output file manager with organization and cleanup"""
    
    def __init__(self):
        self.outputs_dir = settings.OUTPUTS_DIR
        self.temp_dir = settings.TEMP_DIR
        self.max_age_days = 30
        self.max_size_gb = 10
    
    def list_outputs(self, pattern: str = "", sort_by: str = "modified") -> List[Dict[str, Any]]:
        """List output files with optional filtering"""
        files = []
        
        if not self.outputs_dir.exists():
            return files
        
        for f in self.outputs_dir.iterdir():
            if not f.is_file() or f.name.startswith("."):
                continue
            
            if pattern and pattern.lower() not in f.name.lower():
                continue
            
            stat = f.stat()
            files.append({
                "name": f.name,
                "path": str(f),
                "size": stat.st_size,
                "size_human": self._human_size(stat.st_size),
                "created": datetime.fromtimestamp(stat.st_ctime).isoformat(),
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "extension": f.suffix.lower(),
            })
        
        # Sort
        if sort_by == "name":
            files.sort(key=lambda x: x["name"])
        elif sort_by == "size":
            files.sort(key=lambda x: x["size"], reverse=True)
        else:  # modified
            files.sort(key=lambda x: x["modified"], reverse=True)
        
        return files
    
    def delete_output(self, filename: str) -> bool:
        """Delete an output file"""
        filepath = self.outputs_dir / filename
        if not filepath.exists():
            return False
        
        filepath.unlink()
        logger.info(f"Output deleted: {filename}")
        return True
    
    def rename_output(self, old_name: str, new_name: str) -> Dict[str, Any]:
        """Rename an output file"""
        old_path = self.outputs_dir / old_name
        if not old_path.exists():
            return {"success": False, "message": "File not found"}
        
        new_path = self.outputs_dir / new_name
        old_path.rename(new_path)
        
        logger.info(f"Output renamed: {old_name} -> {new_name}")
        return {"success": True, "new_path": str(new_path)}
    
    def cleanup_old_files(self, max_age_days: Optional[int] = None) -> int:
        """Clean up files older than max_age_days"""
        max_age = max_age_days or self.max_age_days
        cutoff = datetime.now() - timedelta(days=max_age)
        deleted = 0
        
        if not self.outputs_dir.exists():
            return 0
        
        for f in self.outputs_dir.iterdir():
            if f.is_file() and not f.name.startswith("."):
                modified = datetime.fromtimestamp(f.stat().st_mtime)
                if modified < cutoff:
                    f.unlink()
                    deleted += 1
        
        if deleted > 0:
            logger.info(f"Cleaned up {deleted} old output files")
        
        return deleted
    
    def cleanup_by_size(self, max_size_gb: Optional[float] = None) -> int:
        """Clean up files if total size exceeds max_size_gb"""
        max_size = (max_size_gb or self.max_size_gb) * 1024**3
        
        files = self.list_outputs()
        total_size = sum(f["size"] for f in files)
        
        if total_size <= max_size:
            return 0
        
        # Sort by modification time, delete oldest first
        files.sort(key=lambda x: x["modified"])
        
        deleted = 0
        for f in files:
            if total_size <= max_size:
                break
            filepath = self.outputs_dir / f["name"]
            if filepath.exists():
                total_size -= f["size"]
                filepath.unlink()
                deleted += 1
        
        logger.info(f"Cleaned up {deleted} files to free space")
        return deleted
    
    def get_stats(self) -> Dict[str, Any]:
        """Get output directory statistics"""
        files = self.list_outputs()
        total_size = sum(f["size"] for f in files)
        
        by_extension = {}
        for f in files:
            ext = f["extension"] or "no_extension"
            by_extension[ext] = by_extension.get(ext, 0) + 1
        
        return {
            "total_files": len(files),
            "total_size_mb": round(total_size / (1024*1024), 2),
            "total_size_human": self._human_size(total_size),
            "by_extension": by_extension,
            "directory": str(self.outputs_dir),
        }
    
    def _human_size(self, size_bytes: int) -> str:
        """Convert bytes to human readable"""
        size = size_bytes
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"


# Global output manager
output_manager = OutputManager()
