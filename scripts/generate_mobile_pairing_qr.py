#!/usr/bin/env python3
"""إنشاء QR مؤقت أو عرض/إلغاء الأجهزة المقترنة من سطر الأوامر."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description="إدارة اقتران تطبيق Voice AI Mobile")
    parser.add_argument("server_url", nargs="?", help="مثال: http://voice-ai.local:8000")
    parser.add_argument("--output", type=Path, default=ROOT / ".mobile_data" / "pairing_qr.png")
    parser.add_argument("--list-devices", action="store_true")
    parser.add_argument("--revoke", metavar="DEVICE_ID")
    args = parser.parse_args()

    from backend.mobile.security import mobile_security

    if args.list_devices:
        devices = mobile_security.list_devices()
        if not devices:
            print("لا توجد أجهزة مقترنة.")
        for device in devices:
            state = "ملغى" if device.get("revoked") else "نشط"
            print(f"{device['device_id']}  {device['name']}  {device['platform']}  {state}")
        return 0
    if args.revoke:
        if not mobile_security.revoke_device(args.revoke):
            print("الجهاز غير موجود.", file=sys.stderr)
            return 1
        print("تم إلغاء اقتران الهاتف.")
        return 0
    if not args.server_url:
        parser.error("server_url مطلوب عند إنشاء QR")

    import qrcode

    session = mobile_security.create_pairing_session(args.server_url)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    qrcode.make(session["qr_payload"]).save(args.output)
    print(f"رمز الاقتران: {session['pairing_code']}")
    print(f"ينتهي خلال: {session['expires_in']} ثانية")
    print(f"QR: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
