"""نقطة تشغيل التطبيق الرئيسية"""
import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path

from backend.core.config import APP_NAME, APP_VERSION, APP_HOST, APP_PORT, APP_DEBUG, FRONTEND_DIR, OUTPUTS_DIR
from backend.core.logger import get_logger
from backend.api.routes import router

logger = get_logger("main")

app = FastAPI(
    title=APP_NAME,
    description="منصة صوتيات عربية لتوليد واستنساخ الصوت - مفتوحة المصدر",
    version=APP_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)

static_dir = FRONTEND_DIR / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

@app.on_event("startup")
async def startup_event():
    logger.info(f"Starting {APP_NAME} v{APP_VERSION}")

@app.on_event("shutdown")
async def shutdown_event():
    logger.info(f"Shutting down {APP_NAME}")

if __name__ == "__main__":
    logger.info(f"Running on http://{APP_HOST}:{APP_PORT}")
    uvicorn.run(
        "main:app",
        host=APP_HOST,
        port=APP_PORT,
        reload=APP_DEBUG,
        log_level="info",
    )
