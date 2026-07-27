"""نقطة تشغيل استوديو ابن الواقدي — الإصدار الموحد الثابت."""

from __future__ import annotations

import sys
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute
from fastapi.staticfiles import StaticFiles

from backend.api.routes import router
from backend.api.human_pro_routes import router as human_pro_router
from backend.api.gemini_routes import router as gemini_router
from backend.api.studio_routes import router as studio_router
from backend.api.studio_pro_routes import router as studio_pro_router
from backend.api.producer_routes import router as producer_router
from backend.api.dialogue_ultra_routes import router as dialogue_ultra_router
from backend.api import dialogue_audio_runtime as _dialogue_audio_runtime
from backend.api.dialogue_safe_routes import router as dialogue_safe_router
from backend.api import gemini_rotation_runtime as _gemini_rotation_runtime
from backend.api.dashboard_routes import router as dashboard_router
from backend.api.ultimate_studio_routes import router as ultimate_studio_router
from backend.api.yemeni_creative_routes import router as yemeni_creative_router
from backend.api.yemeni_creative_hotfix import router as yemeni_creative_safe_router
from backend.api.voice_clone_routes import router as voice_clone_router
from backend.api import voice_clone_repair_runtime as _voice_clone_repair_runtime
from backend.api import gemini_stability_runtime as _gemini_stability_runtime
from backend.api import gemini_retry_window_runtime as _gemini_retry_window_runtime
from backend.api import gemini_cloud_control_runtime as _gemini_cloud_control_runtime
from backend.api import gemini_cloud_control_patch as _gemini_cloud_control_patch
from backend.api import gemini_session_runtime as _gemini_session_runtime
from backend.api import gemini_session_patch as _gemini_session_patch
from backend.api import gemini_single_probe_runtime as _gemini_single_probe_runtime
from backend.api.gemini_session_runtime import router as gemini_session_router
from backend.api.unified_studio_routes import (
    interview_router as unified_interview_router,
    studio_router as unified_studio_router,
)
from backend.api.download_export_runtime import install_download_export_runtime
from backend.core.config import (
    APP_DEBUG,
    APP_HOST,
    APP_NAME,
    APP_PORT,
    APP_RELEASE,
    APP_VERSION,
    FRONTEND_DIR,
)
from backend.core.logger import get_logger

logger = get_logger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting %s v%s — %s", APP_NAME, APP_VERSION, APP_RELEASE)
    yield
    logger.info("Shutting down %s", APP_NAME)


app = FastAPI(
    title=APP_NAME,
    description=(
        "استوديو ابن الواقدي: صوت عربي احترافي، كتابة إبداعية، أعمال يمنية أصلية، "
        "استنساخ صوت مصرح به، مقابلات قابلة للاستكمال، وحفظ منظم على سطح المكتب."
    ),
    version=APP_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)
app.state.release_channel = "voice-clone-pro"

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
app.include_router(gemini_session_router)
app.include_router(studio_router)
app.include_router(studio_pro_router)
app.include_router(producer_router)
app.include_router(unified_interview_router)
app.include_router(unified_studio_router)
app.include_router(dialogue_ultra_router)
app.include_router(dialogue_safe_router)
app.include_router(dashboard_router)
app.include_router(ultimate_studio_router)
app.include_router(yemeni_creative_router)
app.include_router(yemeni_creative_safe_router)
app.include_router(voice_clone_router)

# Replace only the existing GET audio-download handler. No generated file is
# deleted, moved, renamed, or overwritten; a verified copy is added to Desktop.
install_download_export_runtime(app)


def _validate_api_contracts() -> None:
    """Fail fast if a future change breaks one of the unified JSON contracts."""
    required_body_routes = {
        ("/api/tts", "POST"),
        ("/api/speech", "POST"),
        ("/api/interview-pro/scenario", "POST"),
        ("/api/interview-pro/render", "POST"),
        ("/api/studio/v1/interviews/scenario", "POST"),
        ("/api/studio/v1/interviews/render", "POST"),
        ("/api/ultimate/synthesize", "POST"),
        ("/api/ultimate/creative", "POST"),
        ("/api/ultimate/dialogue", "POST"),
        ("/api/yemeni-creative/write", "POST"),
        ("/api/yemeni-creative/produce", "POST"),
        ("/api/yemeni-creative-safe/write", "POST"),
        ("/api/yemeni-creative-safe/produce", "POST"),
        ("/api/voice-clone/generate", "POST"),
    }
    found: set[tuple[str, str]] = set()

    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        for method in route.methods or set():
            key = (route.path, method.upper())
            if key not in required_body_routes:
                continue
            if key in found:
                raise RuntimeError(f"Duplicate unified API route detected: {method} {route.path}")
            found.add(key)
            query_names = {field.name for field in route.dependant.query_params}
            if query_names.intersection({"req", "payload", "body"}):
                raise RuntimeError(f"Invalid query-body contract: {method} {route.path}")
            if not route.dependant.body_params:
                raise RuntimeError(f"Missing JSON body contract: {method} {route.path}")

    missing = required_body_routes - found
    if missing:
        raise RuntimeError(f"Missing unified API routes: {sorted(missing)}")


_validate_api_contracts()

static_dir = FRONTEND_DIR / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


if __name__ == "__main__":
    logger.info("Running on http://%s:%s", APP_HOST, APP_PORT)
    target = app if getattr(sys, "frozen", False) else "main:app"
    uvicorn.run(
        target,
        host=APP_HOST,
        port=APP_PORT,
        reload=APP_DEBUG and not getattr(sys, "frozen", False),
        log_level="info",
    )
