"""Voice AI Studio Arabic - Main Application Entry Point v3.0"""
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.core.config import settings
from backend.core.logger import get_logger, set_request_id
from backend.core.security import (
    SecurityHeadersMiddleware, RequestLoggingMiddleware, rate_limiter
)
from backend.core.health import health_checker
from backend.core.cache_manager import cache_manager
from backend.core.output_manager import output_manager
from backend.api.routes import router

logger = get_logger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan management"""
    logger.info(f"=== Starting {settings.APP_NAME} v{settings.APP_VERSION} ===")
    logger.info(f"Environment: {settings.APP_ENV}")
    logger.info(f"Device: {settings.GPUConfig.get_device()}")
    logger.info(f"Debug: {settings.APP_DEBUG}")

    # Startup tasks
    try:
        # Clean old output files
        cleaned = output_manager.cleanup_old_files()
        if cleaned > 0:
            logger.info(f"Cleaned {cleaned} old output files")

        # Clean expired cache
        expired = await cache_manager.cleanup_expired()
        if expired > 0:
            logger.info(f"Cleaned {expired} expired cache entries")
    except Exception as e:
        logger.warning(f"Startup cleanup error: {e}")

    yield

    # Shutdown tasks
    logger.info(f"=== Shutting down {settings.APP_NAME} ===")


# Create FastAPI application
app = FastAPI(
    title=settings.APP_NAME,
    description="Professional open-source voice AI platform - TTS, voice cloning, audio processing",
    version=settings.APP_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# Security headers middleware
app.add_middleware(SecurityHeadersMiddleware)

# Request logging middleware
app.add_middleware(RequestLoggingMiddleware)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS_LIST,
    allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
    allow_methods=settings.CORS_ALLOW_METHODS.split(","),
    allow_headers=settings.CORS_ALLOW_HEADERS.split(","),
)

# Include all API routes
app.include_router(router, prefix="")

# Static files
static_dir = settings.FRONTEND_DIR / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler"""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "request_id": request.headers.get("X-Request-ID", "")},
    )


if __name__ == "__main__":
    logger.info(f"Server running on http://{settings.APP_HOST}:{settings.APP_PORT}")
    uvicorn.run(
        "main:app",
        host=settings.APP_HOST,
        port=settings.APP_PORT,
        reload=settings.APP_DEBUG,
        log_level="info",
        access_log=False,  # We handle access logging via middleware
    )
