"""واجهات وخدمات تطبيق الجوال المعزولة عن واجهات سطح المكتب."""

from backend.mobile.admin import admin_router
from backend.mobile.routes import router

__all__ = ["admin_router", "router"]
