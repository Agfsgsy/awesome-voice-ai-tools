import sys
import os
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_tts_registry_initialization():
    from backend.core.tts_registry import TTSRegistry
    registry = TTSRegistry()
    registry.initialize()
    plugins = registry.get_all_plugins()
    assert isinstance(plugins, list)

def test_plugin_manager_reloading():
    from backend.core.plugin_manager import init_plugin_manager
    from backend.core.config import PLUGINS_DIR
    pm = init_plugin_manager(PLUGINS_DIR)
    pm.load_all()
    initial_count = len(pm.get_info())
    pm.reload_all()
    assert len(pm.get_info()) >= initial_count
