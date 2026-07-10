"""نقطة تشغيل التطبيق الرئيسية"""

import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from backend.core.config import (
    APP_NAME, APP_VERSION, APP_HOST, APP_PORT, APP_DEBUG,
    FRONTEND_DIR, ALLOWED_ORIGINS, CORS_ALLOW_CREDENTIALS,
    CORS_ALLOW_METHODS, CORS_ALLOW_HEADERS, DOCS_ENABLED,
)
from backend.core.logger import get_logger
from backend.core.exceptions import register_exception_handlers
from backend.core.security_headers import SecurityHeadersMiddleware
from backend.api.routes import router

logger = get_logger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Starting {APP_NAME} v{APP_VERSION}")
    yield
    logger.info(f"Shutting down {APP_NAME}")


# Configure docs URLs based on environment
docs_url = "/docs" if DOCS_ENABLED else None
redoc_url = "/redoc" if DOCS_ENABLED else None

_app = FastAPI(
    title=APP_NAME,
    description="منصة صوتيات عربية لتوليد واستنساخ الصوت - مفتوحة المصدر",
    version=APP_VERSION,
    docs_url=docs_url,
    redoc_url=redoc_url,
    lifespan=lifespan,
)

# Register exception handlers
register_exception_handlers(_app)

# Configure CORS - restricted origins
_app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=CORS_ALLOW_CREDENTIALS,
    allow_methods=CORS_ALLOW_METHODS,
    allow_headers=CORS_ALLOW_HEADERS,
    expose_headers=["X-RateLimit-Limit", "X-RateLimit-Remaining", "X-RateLimit-Reset"],
    max_age=600,
)

# Include API routes
_app.include_router(router)

# Mount static files
static_dir = FRONTEND_DIR / "static"
if static_dir.exists():
    _app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Apply ASGI security headers middleware (outermost layer)
app = SecurityHeadersMiddleware(_app)

if __name__ == "__main__":
    logger.info(f"Running on http://{APP_HOST}:{APP_PORT}")
    uvicorn.run(
        "main:app",
        host=APP_HOST,
        port=APP_PORT,
        reload=APP_DEBUG,
        log_level="info",
    )
