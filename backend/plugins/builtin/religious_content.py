"""إضافة المحتوى الإسلامي"""
__version__ = "1.0.0"
PLUGIN_NAME = "Religious Content"
PLUGIN_DESCRIPTION = "قسم المحتوى الإسلامي: مواعظ، أدعية، أذكار، دروس"


def register():
    pass


CATEGORIES = ["موعظة", "دعاء", "أذكار", "درس", "تعليق إسلامي"]


def get_categories():
    return CATEGORIES
