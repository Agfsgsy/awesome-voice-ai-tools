"""إضافة تجريبية - مثال لنظام الإضافات"""
__version__ = "1.0.0"

PLUGIN_NAME = "Example Plugin"
PLUGIN_DESCRIPTION = "إضافة تجريبية لاختبار نظام الإضافات"


def register():
    """تسجيل الإضافة"""
    pass


def get_info():
    return {"name": PLUGIN_NAME, "version": __version__, "description": PLUGIN_DESCRIPTION}
