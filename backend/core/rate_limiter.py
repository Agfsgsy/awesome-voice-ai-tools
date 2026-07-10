"""Rate Limiting - تقييد عدد الطلبات لمنع إساءة الاستخدام"""

import time
import threading
from typing import Dict, Optional, Tuple
from collections import defaultdict, deque
from functools import wraps

from backend.core.logger import get_logger

logger = get_logger("rate_limiter")


class RateLimiter:
    """Rate limiter using sliding window algorithm"""

    def __init__(self):
        # Per-client request tracking: {client_id: deque of timestamps}
        self._requests: Dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def is_allowed(self, client_id: str, max_requests: int, window_seconds: int) -> Tuple[bool, Dict]:
        """
        Check if a request is allowed for a client.
        Returns: (allowed, info_dict)
        """
        now = time.time()

        with self._lock:
            client_deque = self._requests[client_id]

            # Remove expired entries (outside the window)
            while client_deque and client_deque[0] < now - window_seconds:
                client_deque.popleft()

            current_count = len(client_deque)

            if current_count >= max_requests:
                retry_after = int(client_deque[0] + window_seconds - now) + 1
                return False, {
                    "allowed": False,
                    "limit": max_requests,
                    "remaining": 0,
                    "reset_after": retry_after,
                    "current": current_count,
                }

            # Record this request
            client_deque.append(now)
            remaining = max_requests - current_count - 1

            return True, {
                "allowed": True,
                "limit": max_requests,
                "remaining": max(0, remaining),
                "reset_after": window_seconds,
                "current": current_count + 1,
            }

    def reset(self, client_id: str) -> bool:
        """Reset rate limit for a client"""
        with self._lock:
            if client_id in self._requests:
                del self._requests[client_id]
                return True
        return False

    def cleanup(self, max_age_seconds: int = 3600) -> int:
        """Clean up old entries to prevent memory leaks"""
        now = time.time()
        removed = 0
        with self._lock:
            to_remove = []
            for client_id, client_deque in self._requests.items():
                # Remove all entries older than max_age
                while client_deque and client_deque[0] < now - max_age_seconds:
                    client_deque.popleft()
                if not client_deque:
                    to_remove.append(client_id)
            for client_id in to_remove:
                del self._requests[client_id]
                removed += 1
        if removed > 0:
            logger.debug(f"Rate limiter cleanup: removed {removed} empty clients")
        return removed


# Global rate limiter instance
_rate_limiter = RateLimiter()


def get_rate_limiter() -> RateLimiter:
    """Get the global rate limiter instance"""
    return _rate_limiter


# Default rate limits
DEFAULT_RATE_LIMITS = {
    "general": {"max_requests": 100, "window_seconds": 60},       # 100 req/min
    "tts": {"max_requests": 20, "window_seconds": 60},           # 20 TTS/min
    "upload": {"max_requests": 10, "window_seconds": 60},        # 10 uploads/min
    "auth": {"max_requests": 10, "window_seconds": 300},         # 10 auth/5min
    "sensitive": {"max_requests": 5, "window_seconds": 300},     # 5 sensitive/5min
    "health": {"max_requests": 30, "window_seconds": 60},        # 30 health/min
}


def get_client_id(request) -> str:
    """Extract client identifier from request (IP + User-Agent hash)"""
    import hashlib
    client_ip = ""
    try:
        # Try forwarded headers first
        forwarded = request.headers.get("X-Forwarded-For", "")
        if forwarded:
            client_ip = forwarded.split(",")[0].strip()
        else:
            real_ip = request.headers.get("X-Real-Ip", "")
            if real_ip:
                client_ip = real_ip
            else:
                client_ip = request.client.host if request.client else "unknown"
    except Exception:
        client_ip = "unknown"

    user_agent = request.headers.get("user-agent", "")
    client_hash = hashlib.sha256(f"{client_ip}:{user_agent}".encode()).hexdigest()[:16]
    return client_hash


from fastapi import Request, HTTPException, status


async def check_rate_limit(
    request: Request,
    limit_type: str = "general",
    custom_max: Optional[int] = None,
    custom_window: Optional[int] = None,
) -> Dict:
    """
    Check rate limit for a request.
    Raises HTTPException if limit exceeded.
    """
    rate_limiter = get_rate_limiter()
    client_id = get_client_id(request)

    # Get limit config
    config = DEFAULT_RATE_LIMITS.get(limit_type, DEFAULT_RATE_LIMITS["general"])
    max_requests = custom_max or config["max_requests"]
    window_seconds = custom_window or config["window_seconds"]

    # Add path-specific identifier
    path_key = f"{client_id}:{limit_type}"
    allowed, info = rate_limiter.is_allowed(path_key, max_requests, window_seconds)

    if not allowed:
        logger.warning(
            f"Rate limit exceeded: client={client_id[:8]}, type={limit_type}, "
            f"path={request.url.path}"
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": "Rate limit exceeded",
                "limit": max_requests,
                "window_seconds": window_seconds,
                "retry_after": info.get("reset_after", window_seconds),
            },
            headers={"Retry-After": str(info.get("reset_after", window_seconds))},
        )

    return info


def rate_limit(limit_type: str = "general"):
    """Decorator/dependency for rate limiting endpoints"""
    async def _rate_limit_dependency(request: Request):
        return await check_rate_limit(request, limit_type=limit_type)
    return _rate_limit_dependency
