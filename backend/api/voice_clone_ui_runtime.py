"""Serve the existing Voice Clone Pro page with one additive JavaScript patch.

The stored HTML file is not replaced or deleted. The route reads it as-is and injects
the fast-clone script before </body>, preserving the designed 6.2.0 interface.
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
    script = '<script src="/static/voice_clone_fast_patch.js?v=620-fast-clone"></script>'
    if script not in html:
        html = html.replace("</body>", script + "\n</body>")
    return HTMLResponse(html, headers={"Cache-Control": "no-store, max-age=0"})
