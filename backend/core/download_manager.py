"""Download Manager - Resume Support, Progress Tracking"""
import os
import json
import urllib.request
import hashlib
from pathlib import Path
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
import asyncio

from backend.core.config import settings
from backend.core.logger import get_logger

logger = get_logger("download_manager")


class DownloadStatus(str, Enum):
    PENDING = "pending"
    DOWNLOADING = "downloading"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    VERIFYING = "verifying"


@dataclass
class DownloadTask:
    """Download task information"""
    id: str
    url: str
    target_path: str
    filename: str
    status: DownloadStatus = DownloadStatus.PENDING
    total_size: int = 0
    downloaded_size: int = 0
    progress: float = 0.0
    speed: str = ""
    error: str = ""
    checksum_expected: str = ""
    checksum_actual: str = ""
    created_at: str = ""
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    retries: int = 0
    max_retries: int = 3
    
    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        return data


class DownloadManager:
    """Download manager with resume support and progress tracking"""
    
    def __init__(self):
        self.downloads_dir = settings.DOWNLOADS_DIR
        self.state_file = settings.CONFIG_DIR / "downloads_state.json"
        self.tasks: Dict[str, DownloadTask] = {}
        self._callbacks: Dict[str, List[Callable]] = {}
        self._active_downloads: Dict[str, asyncio.Task] = {}
        self._load_state()
    
    def _load_state(self):
        """Load download state"""
        if self.state_file.exists():
            try:
                with open(self.state_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for tdata in data.get("tasks", []):
                    task = DownloadTask(**tdata)
                    task.status = DownloadStatus(tdata.get("status", "pending"))
                    self.tasks[task.id] = task
            except Exception as e:
                logger.warning(f"Failed to load download state: {e}")
    
    def _save_state(self):
        """Save download state"""
        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump({
                    "updated_at": datetime.utcnow().isoformat(),
                    "tasks": [t.to_dict() for t in self.tasks.values()],
                }, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to save download state: {e}")
    
    def create_task(self, url: str, filename: Optional[str] = None,
                    checksum: str = "", target_dir: Optional[Path] = None) -> str:
        """Create a new download task"""
        import uuid
        
        task_id = str(uuid.uuid4())[:8]
        
        if not filename:
            filename = url.split("/")[-1].split("?")[0] or "download"
        
        target = (target_dir or self.downloads_dir) / filename
        
        task = DownloadTask(
            id=task_id,
            url=url,
            target_path=str(target),
            filename=filename,
            checksum_expected=checksum,
            created_at=datetime.utcnow().isoformat(),
        )
        
        self.tasks[task_id] = task
        self._save_state()
        
        logger.info(f"Download task created: {task_id} - {filename}")
        return task_id
    
    async def start_download(self, task_id: str) -> Dict[str, Any]:
        """Start or resume a download"""
        if task_id not in self.tasks:
            return {"success": False, "message": "Task not found"}
        
        task = self.tasks[task_id]
        
        if task.status == DownloadStatus.DOWNLOADING:
            return {"success": False, "message": "Already downloading"}
        
        task.status = DownloadStatus.DOWNLOADING
        task.started_at = datetime.utcnow().isoformat()
        
        # Start download in background
        download_task = asyncio.create_task(self._download_worker(task_id))
        self._active_downloads[task_id] = download_task
        
        return {"success": True, "task_id": task_id, "status": "started"}
    
    async def _download_worker(self, task_id: str):
        """Download worker with resume support"""
        task = self.tasks[task_id]
        partial_path = Path(task.target_path + ".part")
        
        try:
            resume_byte_pos = partial_path.stat().st_size if partial_path.exists() else 0
            
            headers = {}
            if resume_byte_pos > 0:
                headers["Range"] = f"bytes={resume_byte_pos}-"
                logger.info(f"Resuming download from byte {resume_byte_pos}")
            
            req = urllib.request.Request(task.url, headers=headers)
            
            with urllib.request.urlopen(req, timeout=300) as response:
                task.total_size = int(response.headers.get("Content-Length", 0)) + resume_byte_pos
                
                with open(partial_path, "ab" if resume_byte_pos else "wb") as f:
                    downloaded = resume_byte_pos
                    last_update = datetime.utcnow()
                    
                    while True:
                        chunk = response.read(8192)
                        if not chunk:
                            break
                        
                        f.write(chunk)
                        downloaded += len(chunk)
                        task.downloaded_size = downloaded
                        
                        if task.total_size > 0:
                            task.progress = round((downloaded / task.total_size) * 100, 1)
                        
                        # Update speed
                        now = datetime.utcnow()
                        elapsed = (now - last_update).total_seconds()
                        if elapsed >= 1:
                            speed_bps = len(chunk) / elapsed if elapsed > 0 else 0
                            task.speed = self._format_speed(speed_bps)
                            last_update = now
                            self._save_state()
            
            # Move to final location
            final_path = Path(task.target_path)
            partial_path.rename(final_path)
            
            # Verify checksum
            if task.checksum_expected:
                task.status = DownloadStatus.VERIFYING
                task.checksum_actual = self._compute_checksum(final_path)
                if task.checksum_actual.lower() != task.checksum_expected.lower():
                    final_path.unlink()
                    task.status = DownloadStatus.FAILED
                    task.error = "Checksum verification failed"
                    self._save_state()
                    return
            
            task.status = DownloadStatus.COMPLETED
            task.progress = 100.0
            task.completed_at = datetime.utcnow().isoformat()
            self._save_state()
            
            logger.info(f"Download completed: {task_id} - {task.filename}")
            
        except Exception as e:
            task.retries += 1
            if task.retries < task.max_retries:
                task.status = DownloadStatus.PENDING
                logger.warning(f"Download retry {task.retries}/{task.max_retries}: {task_id}")
            else:
                task.status = DownloadStatus.FAILED
                task.error = str(e)
                logger.error(f"Download failed: {task_id} - {e}")
            self._save_state()
        finally:
            if task_id in self._active_downloads:
                del self._active_downloads[task_id]
    
    def _format_speed(self, bytes_per_second: float) -> str:
        """Format download speed"""
        if bytes_per_second < 1024:
            return f"{bytes_per_second:.1f} B/s"
        elif bytes_per_second < 1024**2:
            return f"{bytes_per_second/1024:.1f} KB/s"
        else:
            return f"{bytes_per_second/(1024**2):.1f} MB/s"
    
    def _compute_checksum(self, filepath: Path) -> str:
        """Compute SHA-256 checksum"""
        sha256 = hashlib.sha256()
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()
    
    async def pause_download(self, task_id: str) -> bool:
        """Pause an active download"""
        if task_id in self._active_downloads:
            self._active_downloads[task_id].cancel()
            del self._active_downloads[task_id]
        
        if task_id in self.tasks:
            self.tasks[task_id].status = DownloadStatus.PAUSED
            self._save_state()
            return True
        return False
    
    async def cancel_download(self, task_id: str) -> bool:
        """Cancel a download"""
        if task_id in self._active_downloads:
            self._active_downloads[task_id].cancel()
            del self._active_downloads[task_id]
        
        if task_id in self.tasks:
            self.tasks[task_id].status = DownloadStatus.CANCELLED
            # Clean up partial file
            partial = Path(self.tasks[task_id].target_path + ".part")
            if partial.exists():
                partial.unlink()
            self._save_state()
            return True
        return False
    
    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get download task information"""
        task = self.tasks.get(task_id)
        return task.to_dict() if task else None
    
    def list_tasks(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """List download tasks"""
        tasks = []
        for task in self.tasks.values():
            if status and task.status.value != status:
                continue
            tasks.append(task.to_dict())
        
        # Sort by created_at descending
        tasks.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return tasks
    
    def get_stats(self) -> Dict[str, Any]:
        """Get download statistics"""
        status_counts = {}
        total_downloaded = 0
        
        for task in self.tasks.values():
            status_counts[task.status.value] = status_counts.get(task.status.value, 0) + 1
            if task.status == DownloadStatus.COMPLETED:
                total_downloaded += task.total_size
        
        return {
            "total": len(self.tasks),
            "by_status": status_counts,
            "active_downloads": len(self._active_downloads),
            "total_downloaded_mb": round(total_downloaded / (1024*1024), 2),
        }


# Global download manager
download_manager = DownloadManager()
