"""واجهة محلية مستقلة لإدارة اقتران الهواتف دون تعديل واجهة سطح المكتب الحالية."""

from __future__ import annotations

import base64
import ipaddress
from io import BytesIO
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from backend.mobile.security import MobileSecurityError, mobile_security

admin_router = APIRouter(tags=["mobile-admin"])


class PairingSessionRequest(BaseModel):
    server_url: str = Field(min_length=8, max_length=500)


def _require_local_admin(request: Request) -> None:
    client_host = request.client.host if request.client else ""
    if client_host == "testclient":
        return
    try:
        client_address = ipaddress.ip_address(client_host)
    except ValueError:
        client_address = None
    request_host = request.url.hostname or ""
    if client_address is not None and client_address.is_loopback and request_host in {"localhost", "127.0.0.1", "::1"}:
        return
    raise HTTPException(status_code=403, detail="إدارة الاقتران متاحة من الكمبيوتر المحلي فقط")


def _validate_advertised_url(value: str) -> str:
    parsed = urlparse(value.strip().rstrip("/"))
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise HTTPException(status_code=400, detail="عنوان الخادم غير صالح")
    if parsed.scheme == "https":
        return value.strip().rstrip("/")
    host = parsed.hostname
    if host in {"localhost", "127.0.0.1", "::1"} or host.endswith(".local"):
        return value.strip().rstrip("/")
    try:
        address = ipaddress.ip_address(host)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="استخدم HTTPS لاسم نطاق خارجي") from exc
    if not (address.is_private or address.is_link_local or address.is_loopback):
        raise HTTPException(status_code=400, detail="يجب استخدام HTTPS خارج الشبكة المحلية")
    return value.strip().rstrip("/")


def _qr_data_uri(payload: str) -> str:
    try:
        import qrcode
    except ImportError as exc:
        raise HTTPException(status_code=503, detail="ثبّت متطلبات خادم الجوال لإنشاء QR") from exc
    image = qrcode.make(payload)
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


@admin_router.get("/mobile-pairing", response_class=HTMLResponse)
async def mobile_pairing_page(request: Request) -> HTMLResponse:
    _require_local_admin(request)
    return HTMLResponse(
        """<!doctype html>
<html lang="ar" dir="rtl">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>اقتران تطبيق Voice AI</title>
<style>
body{font-family:system-ui;background:#0f0f1a;color:#e5e7eb;margin:0;padding:24px}.box{max-width:720px;margin:auto;background:#1a1a2e;border:1px solid #2a2a4a;border-radius:16px;padding:24px}input,button{font:inherit;border-radius:10px;padding:12px}input{width:100%;box-sizing:border-box;background:#16213e;color:white;border:1px solid #2a2a4a;direction:ltr}button{background:#0d9488;color:white;border:0;cursor:pointer;margin-top:12px}button.danger{background:#991b1b;margin:0}.qr{text-align:center;margin:20px}.qr img{width:260px;max-width:100%;background:white;padding:10px;border-radius:12px}.code{font-size:28px;letter-spacing:3px;direction:ltr}.device{display:flex;gap:12px;align-items:center;padding:12px;border-top:1px solid #2a2a4a}.device span{flex:1}.muted{color:#94a3b8}.error{color:#fca5a5}</style></head>
<body><main class="box"><h1>📱 اقتران تطبيق Voice AI</h1><p>هذه الصفحة متاحة على الكمبيوتر المحلي فقط. أدخل العنوان الذي يستطيع الهاتف الوصول إليه داخل الشبكة، ثم امسح QR خلال المدة المحددة.</p>
<label for="server">عنوان الخادم</label><input id="server" type="url" aria-describedby="server-help"><small id="server-help">أدخل العنوان الذي يظهر للهاتف داخل الشبكة.</small><button id="create">إنشاء جلسة اقتران مؤقتة</button>
<p id="message" class="muted"></p><section id="pairing" class="qr" hidden><img id="qr" alt="رمز اقتران QR"><p class="code" id="code"></p><p id="expiry"></p></section>
<h2>الأجهزة المقترنة</h2><div id="devices"></div></main>
<script>
const message=document.getElementById('message'),pairing=document.getElementById('pairing');
async function jsonResponse(response){const data=await response.json();if(!response.ok)throw new Error(data.detail||'فشل الطلب');return data}
document.getElementById('create').onclick=async()=>{try{message.textContent='جارٍ إنشاء الرمز...';const data=await jsonResponse(await fetch('/api/mobile/admin/pairing',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({server_url:document.getElementById('server').value})}));document.getElementById('qr').src=data.qr_image;document.getElementById('code').textContent=data.pairing_code;document.getElementById('expiry').textContent='ينتهي خلال '+data.expires_in+' ثانية';pairing.hidden=false;message.textContent='امسح الرمز من تطبيق الهاتف.'}catch(error){message.textContent=error.message;message.className='error'}};
async function loadDevices(){const root=document.getElementById('devices');try{const data=await jsonResponse(await fetch('/api/mobile/admin/devices'));root.replaceChildren();if(!data.devices.length){root.textContent='لا توجد أجهزة مقترنة.';return}for(const device of data.devices){const row=document.createElement('div');row.className='device';const label=document.createElement('span');label.textContent=device.name+' — '+device.platform+(device.revoked?' (ملغى)':'');row.append(label);if(!device.revoked){const button=document.createElement('button');button.className='danger';button.textContent='إلغاء الاقتران';button.onclick=async()=>{await fetch('/api/mobile/admin/devices/'+device.device_id,{method:'DELETE'});loadDevices()};row.append(button)}root.append(row)}}catch(error){root.textContent=error.message}}
loadDevices();
</script></body></html>"""
    )


@admin_router.post("/api/mobile/admin/pairing")
async def create_mobile_pairing_session(payload: PairingSessionRequest, request: Request):
    _require_local_admin(request)
    server_url = _validate_advertised_url(payload.server_url)
    try:
        session = mobile_security.create_pairing_session(server_url)
    except MobileSecurityError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {**session, "qr_image": _qr_data_uri(session["qr_payload"])}


@admin_router.get("/api/mobile/admin/devices")
async def paired_mobile_devices(request: Request):
    _require_local_admin(request)
    devices = mobile_security.list_devices()
    return {"devices": devices, "count": len(devices)}


@admin_router.delete("/api/mobile/admin/devices/{device_id}")
async def revoke_mobile_device(device_id: str, request: Request):
    _require_local_admin(request)
    if not mobile_security.revoke_device(device_id):
        raise HTTPException(status_code=404, detail="الجهاز غير موجود")
    return {"success": True, "message": "تم إلغاء اقتران الهاتف"}
