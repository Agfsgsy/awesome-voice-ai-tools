"""Exception Handling - معالجة الأخطاء والاستثناءات"""

import traceback
import uuid
from typing import Any, Dict, Optional
from datetime import datetime, timezone

from fastapi import Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.core.logger import get_logger

logger = get_logger("exceptions")


class AppException(Exception):
    """Base application exception"""

    def __init__(
        self,
        message: str,
        status_code: int = 500,
        error_code: str = "internal_error",
        details: Optional[Dict] = None,
    ):
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        self.details = details or {}
        super().__init__(self.message)


class AuthenticationError(AppException):
    """Authentication failed"""
    def __init__(self, message: str = "Authentication failed", details: Optional[Dict] = None):
        super().__init__(message, 401, "authentication_error", details)


class AuthorizationError(AppException):
    """Not authorized"""
    def __init__(self, message: str = "Not authorized", details: Optional[Dict] = None):
        super().__init__(message, 403, "authorization_error", details)


class RateLimitError(AppException):
    """Rate limit exceeded"""
    def __init__(self, message: str = "Rate limit exceeded", details: Optional[Dict] = None):
        super().__init__(message, 429, "rate_limit_exceeded", details)


class ValidationError(AppException):
    """Validation failed"""
    def __init__(self, message: str = "Validation failed", details: Optional[Dict] = None):
        super().__init__(message, 422, "validation_error", details)


class ResourceNotFoundError(AppException):
    """Resource not found"""
    def __init__(self, message: str = "Resource not found", details: Optional[Dict] = None):
        super().__init__(message, 404, "not_found", details)


class FileUploadError(AppException):
    """File upload failed"""
    def __init__(self, message: str = "File upload failed", details: Optional[Dict] = None):
        super().__init__(message, 400, "upload_error", details)


class PluginError(AppException):
    """Plugin operation failed"""
    def __init__(self, message: str = "Plugin error", details: Optional[Dict] = None):
        super().__init__(message, 500, "plugin_error", details)


def generate_error_id() -> str:
    """Generate unique error ID for tracking"""
    return str(uuid.uuid4())[:12]


def log_error(error_id: str, exc: Exception, request: Optional[Request] = None) -> None:
    """Log error with context"""
    context = {
        "error_id": error_id,
        "type": type(exc).__name__,
        "message": str(exc),
    }
    if request:
        context.update({
            "method": request.method,
            "url": str(request.url),
            "client": request.client.host if request.client else "unknown",
            "user_agent": request.headers.get("user-agent", ""),
        })

    logger.error(
        f"Error [{error_id}] {context['type']}: {context['message']} | "
        f"{context.get('method', '')} {context.get('url', '')}",
        extra={"error_id": error_id},
    )


async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    """Handle custom application exceptions"""
    error_id = generate_error_id()
    log_error(error_id, exc, request)

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error": exc.message,
            "error_code": exc.error_code,
            "error_id": error_id,
            "details": exc.details,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Handle HTTP exceptions"""
    error_id = generate_error_id()

    # Don't log 404s as errors unless they're API endpoints
    if exc.status_code >= 500:
        log_error(error_id, exc, request)

    content: Dict[str, Any] = {
        "success": False,
        "error": exc.detail if isinstance(exc.detail, str) else str(exc.detail),
        "error_id": error_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    # Add error code for common status codes
    if exc.status_code == 404:
        content["error_code"] = "not_found"
    elif exc.status_code == 405:
        content["error_code"] = "method_not_allowed"
    elif exc.status_code == 429:
        content["error_code"] = "rate_limit_exceeded"
        retry_after = exc.headers.get("Retry-After") if exc.headers else None
        if retry_after:
            content["retry_after"] = int(retry_after)

    headers = dict(exc.headers) if exc.headers else {}
    return JSONResponse(
        status_code=exc.status_code,
        content=content,
        headers=headers,
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Handle request validation errors"""
    error_id = generate_error_id()

    # Format validation errors
    errors = []
    for error in exc.errors():
        errors.append({
            "field": ".".join(str(loc) for loc in error.get("loc", [])),
            "message": error.get("msg", ""),
            "type": error.get("type", ""),
        })

    logger.warning(
        f"Validation error [{error_id}]: {len(errors)} errors on {request.method} {request.url.path}"
    )

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "success": False,
            "error": "Request validation failed",
            "error_code": "validation_error",
            "error_id": error_id,
            "validation_errors": errors,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )


async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle unexpected exceptions"""
    error_id = generate_error_id()
    log_error(error_id, exc, request)

    # Log full traceback for debugging
    logger.error(f"Unexpected error [{error_id}] traceback:\n{traceback.format_exc()}")

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "success": False,
            "error": "An unexpected error occurred",
            "error_code": "internal_error",
            "error_id": error_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )


def register_exception_handlers(app) -> None:
    """Register all exception handlers with FastAPI app"""
    app.add_exception_handler(AppException, app_exception_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, general_exception_handler)
    logger.info("Exception handlers registered")
