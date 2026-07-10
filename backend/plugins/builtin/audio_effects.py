"""إضافة المؤثرات الصوتية"""
__version__ = "1.0.0"
PLUGIN_NAME = "Audio Effects"
PLUGIN_DESCRIPTION = "معالجة الصوت: إزالة ضجيج، تغيير سرعة، طبقة، ضغط، ريفرب"

PRESETS = {
    "studio": {"noise_reduction": True, "compressor": True, "eq": True},
    "lecture": {"noise_reduction": True, "compressor": False, "reverb": "light"},
    "mosque": {"noise_reduction": True, "reverb": "heavy", "eq": "bass_boost"},
    "deep_voice": {"pitch": -3, "compressor": True},
    "podcast": {"noise_reduction": True, "compressor": True, "eq": True, "reverb": "none"},
    "video_commentary": {"noise_reduction": True, "compressor": True, "speed": 1.05},
}


def register():
    pass


def get_presets():
    return PRESETS
