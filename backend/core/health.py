"""فحوصات صحة النظام"""
import os
import sys
import platform
import shutil
import socket
from typing import List, Dict

from backend.core.config import APP_PORT, BASE_DIR
from backend.core.logger import get_logger

logger = get_logger("health")


def check_python() -> Dict:
    ver = sys.version_info
    ok = ver >= (3, 9)
    return {
        "name": "Python",
        "ok": ok,
        "detail": f"{ver.major}.{ver.minor}.{ver.micro}",
        "message": "Python 3.9+ required" if not ok else "OK",
    }


def check_pip() -> Dict:
    try:
        import pip
        return {"name": "pip", "ok": True, "detail": pip.__version__, "message": "OK"}
    except ImportError:
        return {"name": "pip", "ok": False, "detail": "not found", "message": "pip not installed"}


def check_internet() -> Dict:
    try:
        s = socket.create_connection(("8.8.8.8", 53), timeout=5)
        s.close()
        return {"name": "Internet", "ok": True, "detail": "reachable", "message": "OK"}
    except OSError:
        return {"name": "Internet", "ok": False, "detail": "unreachable", "message": "No internet"}


def check_disk() -> Dict:
    try:
        disk = shutil.disk_usage(str(BASE_DIR))
        free_gb = disk.free / (1024**3)
        ok = free_gb > 0.5
        return {"name": "Disk", "ok": ok, "detail": f"{free_gb:.1f} GB free", "message": "OK" if ok else "Low disk"}
    except Exception as e:
        return {"name": "Disk", "ok": False, "detail": str(e), "message": "Cannot check disk"}


def check_port(port: int) -> Dict:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(1)
        result = s.connect_ex(("127.0.0.1", port))
        s.close()
        if result == 0:
            return {"name": f"Port {port}", "ok": False, "detail": "in use", "message": "Port already in use"}
        return {"name": f"Port {port}", "ok": True, "detail": "available", "message": "OK"}
    except Exception as e:
        return {"name": f"Port {port}", "ok": False, "detail": str(e), "message": "Cannot check port"}


def check_fastapi() -> Dict:
    try:
        import fastapi
        return {"name": "FastAPI", "ok": True, "detail": fastapi.__version__, "message": "OK"}
    except ImportError:
        return {"name": "FastAPI", "ok": False, "detail": "not installed", "message": "pip install fastapi"}


def check_uvicorn() -> Dict:
    try:
        import uvicorn
        return {"name": "Uvicorn", "ok": True, "detail": uvicorn.__version__, "message": "OK"}
    except ImportError:
        return {"name": "Uvicorn", "ok": False, "detail": "not installed", "message": "pip install uvicorn"}


def check_gradio() -> Dict:
    try:
        import gradio
        return {"name": "Gradio", "ok": True, "detail": gradio.__version__, "message": "OK"}
    except ImportError:
        return {"name": "Gradio", "ok": False, "detail": "not installed", "message": "pip install gradio"}


def check_models_dir() -> Dict:
    from backend.core.config import MODELS_DIR
    models = list(MODELS_DIR.iterdir())
    model_files = [f for f in models if f.is_file() and not f.name.startswith(".")]
    return {
        "name": "Models Dir",
        "ok": True,
        "detail": f"{len(model_files)} files",
        "message": "OK",
    }


def check_plugins() -> Dict:
    try:
        from backend.core.config import PLUGINS_DIR
        plugins = [f for f in PLUGINS_DIR.iterdir() if f.suffix == ".py" and not f.name.startswith("_")]
        return {"name": "Plugins", "ok": True, "detail": f"{len(plugins)} plugins", "message": "OK"}
    except Exception as e:
        return {"name": "Plugins", "ok": False, "detail": str(e), "message": "Plugin dir issue"}


def run_all_checks(port: int = 8000) -> List[Dict]:
    checks = []
    for check_fn in [
        check_python, check_pip, check_internet, check_disk,
        check_port, check_fastapi, check_uvicorn,
        check_models_dir, check_plugins,
    ]:
        try:
            if check_fn == check_port:
                checks.append(check_fn(port))
            else:
                checks.append(check_fn())
        except Exception as e:
            checks.append({"name": check_fn.__name__, "ok": False, "detail": str(e), "message": "Check failed"})
    return checks
