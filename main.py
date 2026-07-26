"""نقطة تشغيل التطبيق الرئيسية."""
from __future__ import annotations

import sys
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.api.routes import router
from backend.api.human_pro_routes import router as human_pro_router
from backend.api.gemini_routes import router as gemini_router
from backend.api.studio_routes import router as studio_router
from backend.api.studio_pro_routes import router as studio_pro_router
from backend.api.producer_routes import router as producer_router
from backend.api.interview_pro_routes import router as interview_pro_router
from backend.api.dialogue_ultra_routes import router as dialogue_ultra_router
from backend.api import dialogue_audio_runtime as _dialogue_audio_runtime
from backend.core.config import APP_DEBUG, APP_HOST, APP_NAME, APP_PORT, APP_VERSION, FRONTEND_DIR
from backend.core.logger import get_logger

logger = get_logger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting %s v%s", APP_NAME, APP_VERSION)
    yield
    logger.info("Shutting down %s", APP_NAME)


app = FastAPI(
    title=APP_NAME,
    description="استوديو ابن الواقدي: توليد وإنتاج صوت عربي، حوار طبيعي متعدد المتحدثين، تحرير النص، المواعظ، المؤثرات والموسيقى والاستنساخ المصرح به.",
    version=APP_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1", "http://localhost", "null"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)
app.include_router(human_pro_router)
app.include_router(gemini_router)
app.include_router(studio_router)
app.include_router(studio_pro_router)
app.include_router(producer_router)
app.include_router(interview_pro_router)
app.include_router(dialogue_ultra_router)

static_dir = FRONTEND_DIR / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


if __name__ == "__main__":
    logger.info("Running on http://%s:%s", APP_HOST, APP_PORT)
    target = app if getattr(sys, "frozen", False) else "main:app"
    uvicorn.run(target, host=APP_HOST, port=APP_PORT, reload=APP_DEBUG and not getattr(sys, "frozen", False), log_level="info")