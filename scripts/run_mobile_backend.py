#!/usr/bin/env python3
"""تشغيل FastAPI مع إعلان mDNS لاكتشاف الخادم من تطبيق الهاتف."""

from __future__ import annotations

import argparse
import ipaddress
import socket
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _local_ipv4() -> str:
    candidates: list[str] = []
    try:
        addresses = socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)
    except OSError:
        addresses = []
    for item in addresses:
        candidates.append(item[4][0])
    for candidate in candidates:
        try:
            address = ipaddress.ip_address(candidate)
            if address.is_private and not address.is_loopback:
                return candidate
        except ValueError:
            continue
    return "127.0.0.1"


def main() -> int:
    parser = argparse.ArgumentParser(description="تشغيل خادم Voice AI المخصص للجوال")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", default=8000, type=int)
    parser.add_argument("--advertise-host", help="عنوان LAN الذي يظهر في QR وmDNS")
    parser.add_argument("--ssl-certfile")
    parser.add_argument("--ssl-keyfile")
    args = parser.parse_args()
    if bool(args.ssl_certfile) != bool(args.ssl_keyfile):
        parser.error("يجب تمرير شهادة TLS ومفتاحها معًا")

    import uvicorn
    from zeroconf import ServiceInfo, Zeroconf

    advertised = args.advertise_host or _local_ipv4()
    scheme = "https" if args.ssl_certfile else "http"
    server_url = f"{scheme}://{advertised}:{args.port}"
    service_type = "_voiceai._tcp.local."
    service_name = f"Voice AI Studio-{socket.gethostname()}.{service_type}"
    try:
        packed_address = socket.inet_aton(advertised)
    except OSError:
        resolved = socket.gethostbyname(advertised)
        packed_address = socket.inet_aton(resolved)
    info = ServiceInfo(
        service_type,
        service_name,
        addresses=[packed_address],
        port=args.port,
        properties={"path": "/api/mobile/status", "version": "1", "scheme": scheme},
        server=f"{socket.gethostname()}.local.",
    )
    zeroconf = Zeroconf()
    zeroconf.register_service(info)
    print(f"خادم الجوال: {server_url}")
    print(f"صفحة الاقتران على الكمبيوتر: http://127.0.0.1:{args.port}/mobile-pairing")
    if advertised == "127.0.0.1":
        print("تنبيه: لم يُكتشف عنوان LAN تلقائيًا؛ استخدم --advertise-host بعنوان الكمبيوتر داخل الشبكة.")
    try:
        uvicorn.run(
            "main:app",
            host=args.host,
            port=args.port,
            ssl_certfile=args.ssl_certfile,
            ssl_keyfile=args.ssl_keyfile,
            log_level="info",
        )
    finally:
        zeroconf.unregister_service(info)
        zeroconf.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
