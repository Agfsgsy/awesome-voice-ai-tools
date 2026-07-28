"""Serve the preserved Voice Clone Pro page with additive JavaScript patches.

The stored HTML is not replaced or deleted. A response-body guard is injected before
the fast-clone patch so non-JSON server errors can be displayed without the browser
exception "body stream already read".
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

from backend.core.config import FRONTEND_DIR

router = APIRouter(tags=["Voice Clone UI Runtime"])


@router.get("/static/voice_clone.html", response_class=HTMLResponse, include_in_schema=False)
async def voice_clone_preserved_ui():
    source = FRONTEND_DIR / "static" / "voice_clone.html"
    if not source.exists():
        raise HTTPException(status_code=404, detail="واجهة استنساخ الصوت غير موجودة.")
    html = source.read_text(encoding="utf-8")
    scripts = (
        '<script src="/static/response_body_guard.js?v=620-body-guard"></script>\n'
        '<script src="/static/voice_clone_fast_patch.js?v=620-fast-clone-resume"></script>'
    )
    if "response_body_guard.js" not in html:
        html = html.replace("</body>", scripts + "\n</body>")
    return HTMLResponse(html, headers={"Cache-Control": "no-store, max-age=0"})
