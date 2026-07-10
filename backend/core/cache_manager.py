"""Cache Manager - TTL, Eviction Policies, Statistics"""
import os
import json
import time
import hashlib
import threading
from pathlib import Path
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from enum import Enum
import asyncio

from backend.core.config import settings
from backend.core.logger import get_logger

logger = get_logger("cache_manager")


class EvictionPolicy(str, Enum):
    LRU = "lru"
    LFU = "lfu"
    FIFO = "fifo"
    TTL_ONLY = "ttl_only"


@dataclass
class CacheEntry:
    """Cache entry with metadata"""
    key: str
    value: Any
    created_at: float
    expires_at: float
    access_count: int = 0
    last_accessed: float = 0
    size_bytes: int = 0
    content_type: str = ""
    tags: List[str] = field(default_factory=list)
    
    def is_expired(self) -> bool:
        return time.time() > self.expires_at
    
    def touch(self):
        self.last_accessed = time.time()
        self.access_count += 1


class CacheManager:
    """Production-grade cache manager with TTL, eviction, and statistics"""
    
    def __init__(self):
        self.cache_dir = settings.CACHE_DIR
        self.memory_cache: Dict[str, CacheEntry] = {}
        self.max_memory_items = 1000
        self.max_memory_size_mb = 100
        self.max_disk_size_mb = 500
        self.default_ttl_seconds = 3600
        self.eviction_policy = EvictionPolicy.LRU
        self._lock = asyncio.Lock()
        self._cleanup_task: Optional[asyncio.Task] = None
        self._hits = 0
        self._misses = 0
        self._evictions = 0
        self._start_cleanup_task()
    
    def _start_cleanup_task(self):
        """Start background cleanup task"""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        except Exception:
            pass
    
    async def _cleanup_loop(self):
        """Periodic cleanup of expired entries"""
        while True:
            try:
                await asyncio.sleep(300)  # Every 5 minutes
                await self.cleanup_expired()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Cache cleanup error: {e}")
    
    def _compute_key(self, *args, **kwargs) -> str:
        """Compute cache key from arguments"""
        key_data = json.dumps({"args": args, "kwargs": kwargs}, sort_keys=True, default=str)
        return hashlib.sha256(key_data.encode()).hexdigest()[:16]
    
    def _get_memory_usage_mb(self) -> float:
        """Get current memory cache usage"""
        total = sum(e.size_bytes for e in self.memory_cache.values())
        return total / (1024 * 1024)
    
    def _get_disk_usage_mb(self) -> float:
        """Get current disk cache usage"""
        total = 0
        if self.cache_dir.exists():
            for f in self.cache_dir.iterdir():
                if f.is_file():
                    total += f.stat().st_size
        return total / (1024 * 1024)
    
    async def _evict_if_needed(self):
        """Evict entries if cache is over capacity"""
        # Memory eviction
        while len(self.memory_cache) > self.max_memory_items or self._get_memory_usage_mb() > self.max_memory_size_mb:
            if not self.memory_cache:
                break
            
            if self.eviction_policy == EvictionPolicy.LRU:
                key = min(self.memory_cache.keys(), key=lambda k: self.memory_cache[k].last_accessed)
            elif self.eviction_policy == EvictionPolicy.LFU:
                key = min(self.memory_cache.keys(), key=lambda k: self.memory_cache[k].access_count)
            elif self.eviction_policy == EvictionPolicy.FIFO:
                key = min(self.memory_cache.keys(), key=lambda k: self.memory_cache[k].created_at)
            else:
                # TTL only - remove expired
                expired = [k for k, v in self.memory_cache.items() if v.is_expired()]
                if expired:
                    key = expired[0]
                else:
                    break
            
            del self.memory_cache[key]
            self._evictions += 1
        
        # Disk eviction
        while self._get_disk_usage_mb() > self.max_disk_size_mb:
            files = [(f, f.stat().st_atime) for f in self.cache_dir.iterdir() if f.is_file()]
            if not files:
                break
            oldest = min(files, key=lambda x: x[1])
            oldest[0].unlink()
            self._evictions += 1
    
    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache"""
        async with self._lock:
            entry = self.memory_cache.get(key)
            
            if entry:
                if entry.is_expired():
                    del self.memory_cache[key]
                    self._misses += 1
                    return None
                
                entry.touch()
                self._hits += 1
                return entry.value
            
            # Try disk cache
            disk_path = self.cache_dir / f"{key}.cache"
            if disk_path.exists():
                try:
                    with open(disk_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    
                    if data.get("expires_at", 0) > time.time():
                        # Restore to memory
                        entry = CacheEntry(
                            key=key,
                            value=data["value"],
                            created_at=data["created_at"],
                            expires_at=data["expires_at"],
                            size_bytes=len(json.dumps(data["value"]).encode()),
                        )
                        entry.touch()
                        self.memory_cache[key] = entry
                        self._hits += 1
                        return data["value"]
                    else:
                        disk_path.unlink()
                except Exception:
                    pass
            
            self._misses += 1
            return None
    
    async def set(self, key: str, value: Any, ttl_seconds: Optional[int] = None,
                  tags: List[str] = None, persist: bool = False) -> bool:
        """Set value in cache"""
        async with self._lock:
            ttl = ttl_seconds or self.default_ttl_seconds
            now = time.time()
            
            entry = CacheEntry(
                key=key,
                value=value,
                created_at=now,
                expires_at=now + ttl,
                last_accessed=now,
                size_bytes=len(json.dumps(value, default=str).encode()),
                tags=tags or [],
            )
            
            self.memory_cache[key] = entry
            
            # Persist to disk if requested
            if persist:
                await self._persist_to_disk(key, entry)
            
            # Evict if needed
            await self._evict_if_needed()
            
            return True
    
    async def _persist_to_disk(self, key: str, entry: CacheEntry):
        """Persist cache entry to disk"""
        try:
            disk_path = self.cache_dir / f"{key}.cache"
            with open(disk_path, "w", encoding="utf-8") as f:
                json.dump({
                    "key": entry.key,
                    "value": entry.value,
                    "created_at": entry.created_at,
                    "expires_at": entry.expires_at,
                    "tags": entry.tags,
                }, f, default=str)
        except Exception as e:
            logger.warning(f"Failed to persist cache to disk: {e}")
    
    async def delete(self, key: str) -> bool:
        """Delete a cache entry"""
        async with self._lock:
            if key in self.memory_cache:
                del self.memory_cache[key]
            
            disk_path = self.cache_dir / f"{key}.cache"
            if disk_path.exists():
                disk_path.unlink()
            
            return True
    
    async def clear(self) -> int:
        """Clear all cache entries"""
        async with self._lock:
            count = len(self.memory_cache)
            self.memory_cache.clear()
            
            # Clear disk cache
            if self.cache_dir.exists():
                for f in self.cache_dir.iterdir():
                    if f.is_file() and f.suffix == ".cache":
                        f.unlink()
                        count += 1
            
            self._hits = 0
            self._misses = 0
            
            logger.info(f"Cache cleared: {count} entries")
            return count
    
    async def cleanup_expired(self) -> int:
        """Remove expired entries"""
        async with self._lock:
            expired_keys = [k for k, v in self.memory_cache.items() if v.is_expired()]
            for key in expired_keys:
                del self.memory_cache[key]
            
            # Check disk cache
            disk_expired = 0
            if self.cache_dir.exists():
                for f in self.cache_dir.iterdir():
                    if f.is_file() and f.suffix == ".cache":
                        try:
                            with open(f, "r", encoding="utf-8") as fp:
                                data = json.load(fp)
                            if data.get("expires_at", 0) < time.time():
                                f.unlink()
                                disk_expired += 1
                        except Exception:
                            f.unlink()
                            disk_expired += 1
            
            total = len(expired_keys) + disk_expired
            if total > 0:
                logger.info(f"Cleaned up {total} expired cache entries")
            return total
    
    async def get_by_tag(self, tag: str) -> List[Dict[str, Any]]:
        """Get all cache entries with a specific tag"""
        results = []
        for entry in self.memory_cache.values():
            if tag in entry.tags:
                results.append({
                    "key": entry.key,
                    "expires_at": entry.expires_at,
                    "access_count": entry.access_count,
                    "size_bytes": entry.size_bytes,
                })
        return results
    
    async def delete_by_tag(self, tag: str) -> int:
        """Delete all cache entries with a specific tag"""
        keys_to_delete = [k for k, v in self.memory_cache.items() if tag in v.tags]
        for key in keys_to_delete:
            del self.memory_cache[key]
        return len(keys_to_delete)
    
    def get_info(self) -> Dict[str, Any]:
        """Get cache information"""
        total_size = sum(e.size_bytes for e in self.memory_cache.values())
        
        return {
            "memory_items": len(self.memory_cache),
            "memory_size_mb": round(total_size / (1024*1024), 2),
            "disk_size_mb": round(self._get_disk_usage_mb(), 2),
            "max_memory_items": self.max_memory_items,
            "max_memory_size_mb": self.max_memory_size_mb,
            "max_disk_size_mb": self.max_disk_size_mb,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(self._hits / (self._hits + self._misses), 4) if (self._hits + self._misses) > 0 else 0,
            "evictions": self._evictions,
            "eviction_policy": self.eviction_policy.value,
            "default_ttl_seconds": self.default_ttl_seconds,
        }
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        return self.get_info()
    
    def decorator(self, ttl_seconds: Optional[int] = None, key_func: Optional[Callable] = None):
        """Decorator for caching function results"""
        def wrapper(func: Callable) -> Callable:
            async def async_wrapper(*args, **kwargs):
                cache_key = key_func(*args, **kwargs) if key_func else self._compute_key(func.__name__, *args, **kwargs)
                
                result = await self.get(cache_key)
                if result is not None:
                    return result
                
                result = await func(*args, **kwargs) if asyncio.iscoroutinefunction(func) else func(*args, **kwargs)
                await self.set(cache_key, result, ttl_seconds)
                return result
            
            return async_wrapper
        return wrapper


# Global cache manager
cache_manager = CacheManager()
