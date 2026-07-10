"""Security Module - Rate Limiting, Headers, Validation"""
import time
import hashlib
import secrets
import re
from typing import Optional, Dict, List, Callable
from functools import wraps
from pathlib import Path

from fastapi import HTTPException, Request, status
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from backend.core.config import settings
from backend.core.logger import get_logger

logger = get_logger("security")


class RateLimiter:
    """In-memory rate limiter with IP-based tracking"""
    
    def __init__(self):
        self.requests: Dict[str, List[float]] = {}
        self.blocked: Dict[str, float] = {}
        self.max_requests = settings.RATE_LIMIT_REQUESTS
        self.window = settings.RATE_LIMIT_WINDOW
    
    def _get_key(self, request: Request) -> str:
        """Get client identifier"""
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"
    
    def is_allowed(self, request: Request) -> bool:
        """Check if request is within rate limit"""
        if not settings.RATE_LIMIT_ENABLED:
            return True
        
        key = self._get_key(request)
        now = time.time()
        
        # Check if blocked
        if key in self.blocked:
            if now - self.blocked[key] < self.window * 2:
                return False
            del self.blocked[key]
        
        # Clean old requests
        if key in self.requests:
            self.requests[key] = [t for t in self.requests[key] if now - t < self.window]
        else:
            self.requests[key] = []
        
        # Check limit
        if len(self.requests[key]) >= self.max_requests:
            self.blocked[key] = now
            logger.warning(f"Rate limit exceeded for {key}")
            return False
        
        self.requests[key].append(now)
        return True
    
    def get_remaining(self, request: Request) -> Dict:
        """Get remaining requests info"""
        key = self._get_key(request)
        now = time.time()
        
        if key in self.requests:
            self.requests[key] = [t for t in self.requests[key] if now - t < self.window]
            remaining = max(0, self.max_requests - len(self.requests[key]))
        else:
            remaining = self.max_requests
        
        return {
            "limit": self.max_requests,
            "remaining": remaining,
            "window": self.window,
        }


# Global rate limiter
rate_limiter = RateLimiter()


def rate_limit() -> Callable:
    """Decorator for rate limiting endpoints"""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Find request in args/kwargs
            request = None
            for arg in args:
                if isinstance(arg, Request):
                    request = arg
                    break
            if not request:
                for v in kwargs.values():
                    if isinstance(v, Request):
                        request = v
                        break
            
            if request and not rate_limiter.is_allowed(request):
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Rate limit exceeded. Please try again later.",
                    headers={"Retry-After": str(settings.RATE_LIMIT_WINDOW)},
                )
            return await func(*args, **kwargs)
        return wrapper
    return decorator


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all responses"""
    
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        
        # Security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(self), camera=()"
        
        if settings.APP_ENV == "production":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        
        return response


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log all requests with timing"""
    
    async def dispatch(self, request: Request, call_next):
        start = time.time()
        
        # Generate request ID
        request_id = secrets.token_hex(8)
        from backend.core.logger import set_request_id
        set_request_id(request_id)
        
        response = await call_next(request)
        
        duration = (time.time() - start) * 1000
        
        response.headers["X-Request-ID"] = request_id
        
        logger.info(
            f"{request.method} {request.url.path} - {response.status_code} - {duration:.1f}ms",
            extra={
                "request_id": request_id,
                "duration_ms": duration,
                "status_code": response.status_code,
                "ip": request.client.host if request.client else "unknown",
            }
        )
        
        return response


def sanitize_filename(filename: str) -> str:
    """Sanitize a filename for safe storage"""
    filename = re.sub(r'[^\w\-. ]', '_', filename)
    filename = filename.strip("._")
    if not filename:
        filename = "unnamed"
    return filename


def validate_audio_file(filename: str) -> bool:
    """Validate audio file extension"""
    ext = Path(filename).suffix.lower()
    return ext in settings.SUPPORTED_AUDIO_FORMATS


def generate_secure_filename(original_name: str) -> str:
    """Generate a secure unique filename"""
    timestamp = str(int(time.time()))
    random_part = secrets.token_hex(4)
    ext = Path(original_name).suffix.lower()
    if ext not in settings.SUPPORTED_AUDIO_FORMATS:
        ext = ".wav"
    name_hash = hashlib.sha256(f"{original_name}{timestamp}{random_part}".encode()).hexdigest()[:12]
    return f"{name_hash}_{timestamp}{ext}"


def hash_file(filepath: Path) -> str:
    """Calculate SHA-256 hash of a file"""
    sha256 = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()
