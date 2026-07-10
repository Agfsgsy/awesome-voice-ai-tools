"""Task Manager - Queue, Scheduler, Batch Processing"""
import asyncio
import json
import uuid
from pathlib import Path
from typing import Dict, List, Any, Optional, Callable, Coroutine
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from enum import Enum
from queue import PriorityQueue
import threading
import time

from backend.core.config import settings
from backend.core.logger import get_logger

logger = get_logger("task_manager")


class TaskStatus(str, Enum):
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"


class TaskPriority(int, Enum):
    CRITICAL = 1
    HIGH = 2
    NORMAL = 3
    LOW = 4
    BACKGROUND = 5


class TaskType(str, Enum):
    TTS = "tts"
    CLONE = "clone"
    DOWNLOAD = "download"
    CONVERT = "convert"
    PROCESS = "process"
    BATCH = "batch"
    MAINTENANCE = "maintenance"
    CUSTOM = "custom"


@dataclass
class Task:
    """Task definition with full metadata"""
    id: str = ""
    name: str = ""
    task_type: TaskType = TaskType.CUSTOM
    priority: TaskPriority = TaskPriority.NORMAL
    status: TaskStatus = TaskStatus.PENDING
    params: Dict[str, Any] = field(default_factory=dict)
    result: Any = None
    error: str = ""
    created_at: str = ""
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    progress: float = 0.0
    duration_ms: float = 0.0
    max_retries: int = 3
    retry_count: int = 0
    timeout_seconds: int = 300
    depends_on: List[str] = field(default_factory=list)
    callback: Optional[str] = None
    
    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())[:8]
        if not self.created_at:
            self.created_at = datetime.utcnow().isoformat()
    
    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["task_type"] = self.task_type.value
        data["priority"] = self.priority.value
        data["status"] = self.status.value
        data["callback"] = self.callback
        return data


class TaskManager:
    """Production-grade task manager with queue, scheduler, and batch processing"""
    
    def __init__(self, max_workers: int = 4):
        self.max_workers = max_workers
        self.tasks: Dict[str, Task] = {}
        self.queue: asyncio.PriorityQueue = asyncio.PriorityQueue()
        self.running: Dict[str, asyncio.Task] = {}
        self._workers: List[asyncio.Task] = []
        self._handlers: Dict[TaskType, Callable] = {}
        self._callbacks: Dict[str, List[Callable]] = {}
        self._running = False
        self._lock = asyncio.Lock()
        self._db_file = settings.TASKS_DB_FILE
        self._load_tasks()
    
    def _load_tasks(self):
        """Load persisted tasks"""
        if self._db_file.exists():
            try:
                with open(self._db_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for tdata in data.get("tasks", []):
                    task = Task(
                        id=tdata.get("id", ""),
                        name=tdata.get("name", ""),
                        task_type=TaskType(tdata.get("task_type", "custom")),
                        priority=TaskPriority(tdata.get("priority", 3)),
                        status=TaskStatus(tdata.get("status", "pending")),
                        params=tdata.get("params", {}),
                        created_at=tdata.get("created_at", ""),
                        max_retries=tdata.get("max_retries", 3),
                        timeout_seconds=tdata.get("timeout_seconds", 300),
                        depends_on=tdata.get("depends_on", []),
                    )
                    self.tasks[task.id] = task
            except Exception as e:
                logger.warning(f"Failed to load tasks: {e}")
    
    def _save_tasks(self):
        """Persist tasks"""
        try:
            self._db_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self._db_file, "w", encoding="utf-8") as f:
                json.dump({
                    "updated_at": datetime.utcnow().isoformat(),
                    "tasks": [t.to_dict() for t in self.tasks.values()],
                }, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to save tasks: {e}")
    
    def register_handler(self, task_type: TaskType, handler: Callable):
        """Register a handler for a task type"""
        self._handlers[task_type] = handler
        logger.info(f"Registered handler for {task_type.value}")
    
    async def submit(self, task: Task) -> str:
        """Submit a task to the queue"""
        async with self._lock:
            self.tasks[task.id] = task
            task.status = TaskStatus.QUEUED
            
            # Add to priority queue
            await self.queue.put((task.priority.value, time.time(), task.id))
            
            self._save_tasks()
        
        logger.info(f"Task submitted: {task.id} ({task.name}) priority={task.priority.name}")
        
        # Start workers if not running
        if not self._running:
            self.start()
        
        return task.id
    
    async def submit_batch(self, tasks: List[Task]) -> List[str]:
        """Submit multiple tasks as a batch"""
        task_ids = []
        for task in tasks:
            tid = await self.submit(task)
            task_ids.append(tid)
        logger.info(f"Batch submitted: {len(tasks)} tasks")
        return task_ids
    
    async def cancel(self, task_id: str) -> bool:
        """Cancel a task"""
        if task_id not in self.tasks:
            return False
        
        task = self.tasks[task_id]
        
        # Cancel if running
        if task_id in self.running:
            self.running[task_id].cancel()
            del self.running[task_id]
        
        task.status = TaskStatus.CANCELLED
        self._save_tasks()
        logger.info(f"Task cancelled: {task_id}")
        return True
    
    async def pause(self, task_id: str) -> bool:
        """Pause a running task"""
        if task_id not in self.tasks:
            return False
        self.tasks[task_id].status = TaskStatus.PAUSED
        self._save_tasks()
        return True
    
    async def resume(self, task_id: str) -> bool:
        """Resume a paused task"""
        if task_id not in self.tasks:
            return False
        task = self.tasks[task_id]
        task.status = TaskStatus.QUEUED
        await self.queue.put((task.priority.value, time.time(), task.id))
        self._save_tasks()
        return True
    
    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get task information"""
        task = self.tasks.get(task_id)
        return task.to_dict() if task else None
    
    def list_tasks(self, status: Optional[TaskStatus] = None, 
                   task_type: Optional[TaskType] = None) -> List[Dict[str, Any]]:
        """List tasks with optional filters"""
        results = []
        for task in self.tasks.values():
            if status and task.status != status:
                continue
            if task_type and task.task_type != task_type:
                continue
            results.append(task.to_dict())
        
        # Sort by created_at descending
        results.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return results
    
    def get_stats(self) -> Dict[str, Any]:
        """Get task manager statistics"""
        status_counts = {}
        type_counts = {}
        
        for task in self.tasks.values():
            status_counts[task.status.value] = status_counts.get(task.status.value, 0) + 1
            type_counts[task.task_type.value] = type_counts.get(task.task_type.value, 0) + 1
        
        return {
            "total": len(self.tasks),
            "by_status": status_counts,
            "by_type": type_counts,
            "running": len(self.running),
            "queued": self.queue.qsize(),
            "max_workers": self.max_workers,
        }
    
    def start(self):
        """Start task workers"""
        if self._running:
            return
        
        self._running = True
        for i in range(self.max_workers):
            worker = asyncio.create_task(self._worker_loop(f"worker-{i}"))
            self._workers.append(worker)
        
        logger.info(f"Task manager started with {self.max_workers} workers")
    
    def stop(self):
        """Stop task workers"""
        self._running = False
        for worker in self._workers:
            worker.cancel()
        self._workers.clear()
        logger.info("Task manager stopped")
    
    async def _worker_loop(self, worker_id: str):
        """Worker loop that processes tasks"""
        while self._running:
            try:
                # Get task from queue
                priority, _, task_id = await self.queue.get()
                
                if task_id not in self.tasks:
                    continue
                
                task = self.tasks[task_id]
                
                # Check dependencies
                if task.depends_on:
                    deps_ok = all(
                        self.tasks.get(dep_id, Task()).status == TaskStatus.COMPLETED
                        for dep_id in task.depends_on
                    )
                    if not deps_ok:
                        # Re-queue with delay
                        await asyncio.sleep(5)
                        await self.queue.put((task.priority.value, time.time(), task.id))
                        continue
                
                # Execute task
                await self._execute_task(task)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Worker {worker_id} error: {e}")
                await asyncio.sleep(1)
    
    async def _execute_task(self, task: Task):
        """Execute a single task"""
        task.status = TaskStatus.RUNNING
        task.started_at = datetime.utcnow().isoformat()
        start_time = time.time()
        
        logger.info(f"Executing task: {task.id} ({task.name})")
        
        try:
            # Get handler
            handler = self._handlers.get(task.task_type)
            
            if handler:
                # Execute with timeout
                result = await asyncio.wait_for(
                    handler(task.params) if asyncio.iscoroutinefunction(handler) 
                    else asyncio.get_event_loop().run_in_executor(None, handler, task.params),
                    timeout=task.timeout_seconds,
                )
                task.result = result
                task.status = TaskStatus.COMPLETED
                logger.info(f"Task completed: {task.id}")
            else:
                task.status = TaskStatus.FAILED
                task.error = f"No handler registered for {task.task_type.value}"
                logger.warning(f"No handler for task: {task.id}")
            
        except asyncio.TimeoutError:
            task.status = TaskStatus.TIMEOUT
            task.error = "Task timed out"
            logger.warning(f"Task timeout: {task.id}")
        except Exception as e:
            task.retry_count += 1
            if task.retry_count < task.max_retries:
                task.status = TaskStatus.QUEUED
                await self.queue.put((task.priority.value, time.time(), task.id))
                logger.info(f"Task retry {task.retry_count}/{task.max_retries}: {task.id}")
            else:
                task.status = TaskStatus.FAILED
                task.error = str(e)
                logger.error(f"Task failed: {task.id} - {e}")
        
        finally:
            task.duration_ms = (time.time() - start_time) * 1000
            task.completed_at = datetime.utcnow().isoformat()
            
            if task_id := task.id in self.running:
                del self.running[task.id]
            
            self._save_tasks()


# Global task manager
task_manager = TaskManager()
