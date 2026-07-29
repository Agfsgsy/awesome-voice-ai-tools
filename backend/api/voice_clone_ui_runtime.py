"""Serve preserved studio pages with additive Voice Clone Pro 7 patches.

Stored HTML files are not deleted or redesigned. Runtime responses only update the
visible release label and inject safe JavaScript helpers before StaticFiles.
Build marker: Professional Studio 7.0.0.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

from backend.core.config import APP_RELEASE, APP_VERSION, FRONTEND_DIR

router = APIRouter(tags=["Voice Clone UI Runtime"])


def _release_text(html: str) -> str:
    html = html.replace("الإصدار 6.2.0 • Voice Clone Pro", f"الإصدار {APP_VERSION} • {APP_RELEASE}")
    html = html.replace(
        "Professional Studio 6.2.0 — Preserved UI",
        f"Professional Studio {APP_VERSION} — Preserved UI + {APP_RELEASE}",
    )
    html = html.replace(
        "Professional Studio 6.2.0 — Voice Clone Pro",
        f"Professional Studio {APP_VERSION} — {APP_RELEASE}",
    )
    return html


@router.get("/static/voice_clone.html", response_class=HTMLResponse, include_in_schema=False)
async def voice_clone_preserved_ui():
    source = FRONTEND_DIR / "static" / "voice_clone.html"
    if not source.exists():
        raise HTTPException(status_code=404, detail="واجهة استنساخ الصوت غير موجودة.")
    html = _release_text(source.read_text(encoding="utf-8"))
    scripts = (
        '<script src="/static/response_body_guard.js?v=700-body-guard"></script>\n'
        '<script src="/static/voice_clone_fast_patch.js?v=700-fast-clone-resume"></script>\n'
        '<script src="/static/voice_clone_v7_patch.js?v=700-engine-pack"></script>'
    )
    if "voice_clone_v7_patch.js" not in html:
        html = html.replace("</body>", scripts + "\n</body>")
    return HTMLResponse(html, headers={"Cache-Control": "no-store, max-age=0"})


@router.get("/static/studio_shell_preserved.html", response_class=HTMLResponse, include_in_schema=False)
async def studio_shell_preserved_v7():
    source = FRONTEND_DIR / "static" / "studio_shell_preserved.html"
    if not source.exists():
        raise HTTPException(status_code=404, detail="واجهة الاستوديو المحفوظة غير موجودة.")
    html = _release_text(source.read_text(encoding="utf-8"))
    return HTMLResponse(html, headers={"Cache-Control": "no-store, max-age=0"})
