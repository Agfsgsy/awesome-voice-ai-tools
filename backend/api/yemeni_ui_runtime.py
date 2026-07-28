"""Serve the preserved Yemeni Creative Pro page with a safe fetch guard.

The HTML, layout, controls and production routes remain unchanged. The injected guard
only prevents a failed JSON parse from consuming the response body before the page can
show the server's real text error.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

from backend.core.config import FRONTEND_DIR

router = APIRouter(tags=["Yemeni Creative UI Runtime"])


@router.get("/static/yemeni_creative_pro.html", response_class=HTMLResponse, include_in_schema=False)
async def yemeni_creative_preserved_ui():
    source = FRONTEND_DIR / "static" / "yemeni_creative_pro.html"
    if not source.exists():
        raise HTTPException(status_code=404, detail="واجهة الشيلات والإهداءات غير موجودة.")
    html = source.read_text(encoding="utf-8")
    script = '<script src="/static/response_body_guard.js?v=620-body-guard"></script>'
    if "response_body_guard.js" not in html:
        html = html.replace("<script>\n(() => {", script + "\n<script>\n(() => {")
    return HTMLResponse(html, headers={"Cache-Control": "no-store, max-age=0"})
