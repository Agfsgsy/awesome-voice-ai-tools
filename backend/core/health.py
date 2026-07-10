"""System Health Monitoring - Comprehensive Checks"""
import os
import sys
import platform
import shutil
import socket
import time
import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime
from pathlib import Path

from backend.core.config import settings, GPUConfig
from backend.core.logger import get_logger

logger = get_logger("health")


class HealthChecker:
    """Comprehensive health checker with detailed diagnostics"""
    
    def __init__(self):
        self.checks: Dict[str, callable] = {
            "python": self._check_python,
            "pip": self._check_pip,
            "internet": self._check_internet,
            "disk": self._check_disk,
            "memory": self._check_memory,
            "port": self._check_port,
            "fastapi": self._check_fastapi,
            "uvicorn": self._check_uvicorn,
            "gpu": self._check_gpu,
            "models_dir": self._check_models_dir,
            "plugins_dir": self._check_plugins_dir,
            "critical_deps": self._check_critical_dependencies,
        }
    
    def _check_python(self) -> Dict:
        ver = sys.version_info
        ok = ver >= (3, 9)
        return {
            "name": "Python",
            "category": "runtime",
            "ok": ok,
            "detail": f"{ver.major}.{ver.minor}.{ver.micro}",
            "message": "OK" if ok else "Python 3.9+ required",
            "severity": "critical",
        }
    
    def _check_pip(self) -> Dict:
        try:
            import pip
            return {"name": "pip", "category": "runtime", "ok": True, "detail": pip.__version__, "message": "OK", "severity": "low"}
        except ImportError:
            return {"name": "pip", "category": "runtime", "ok": False, "detail": "not found", "message": "pip not installed", "severity": "medium"}
    
    def _check_internet(self) -> Dict:
        try:
            s = socket.create_connection(("8.8.8.8", 53), timeout=5)
            s.close()
            return {"name": "Internet", "category": "network", "ok": True, "detail": "reachable", "message": "OK", "severity": "medium"}
        except OSError:
            return {"name": "Internet", "category": "network", "ok": False, "detail": "unreachable", "message": "No internet connection", "severity": "medium"}
    
    def _check_disk(self) -> Dict:
        try:
            disk = shutil.disk_usage(str(settings.BASE_DIR))
            free_gb = disk.free / (1024**3)
            total_gb = disk.total / (1024**3)
            used_pct = (disk.used / disk.total) * 100
            ok = free_gb > 1.0
            return {
                "name": "Disk",
                "category": "system",
                "ok": ok,
                "detail": f"{free_gb:.1f} GB free / {total_gb:.1f} GB total ({used_pct:.1f}% used)",
                "message": "OK" if ok else "Low disk space",
                "severity": "critical" if not ok else "high",
                "free_gb": round(free_gb, 2),
                "total_gb": round(total_gb, 2),
                "used_percent": round(used_pct, 1),
            }
        except Exception as e:
            return {"name": "Disk", "category": "system", "ok": False, "detail": str(e), "message": "Cannot check disk", "severity": "high"}
    
    def _check_memory(self) -> Dict:
        try:
            import psutil
            mem = psutil.virtual_memory()
            return {
                "name": "Memory",
                "category": "system",
                "ok": mem.available > 512 * 1024 * 1024,  # 512MB
                "detail": f"{mem.available // (1024**2)} MB available / {mem.total // (1024**2)} MB total ({mem.percent}% used)",
                "message": "OK" if mem.available > 512 * 1024 * 1024 else "Low memory",
                "severity": "high",
                "available_mb": mem.available // (1024**2),
                "total_mb": mem.total // (1024**2),
                "used_percent": mem.percent,
            }
        except ImportError:
            return {"name": "Memory", "category": "system", "ok": True, "detail": "psutil not installed", "message": "Cannot check memory", "severity": "low"}
        except Exception as e:
            return {"name": "Memory", "category": "system", "ok": False, "detail": str(e), "message": "Cannot check memory", "severity": "medium"}
    
    def _check_port(self) -> Dict:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(1)
            result = s.connect_ex(("127.0.0.1", settings.APP_PORT))
            s.close()
            if result == 0:
                return {"name": f"Port {settings.APP_PORT}", "category": "network", "ok": False, "detail": "in use", "message": "Port already in use", "severity": "critical"}
            return {"name": f"Port {settings.APP_PORT}", "category": "network", "ok": True, "detail": "available", "message": "OK", "severity": "high"}
        except Exception as e:
            return {"name": f"Port {settings.APP_PORT}", "category": "network", "ok": False, "detail": str(e), "message": "Cannot check port", "severity": "medium"}
    
    def _check_fastapi(self) -> Dict:
        try:
            import fastapi
            return {"name": "FastAPI", "category": "deps", "ok": True, "detail": fastapi.__version__, "message": "OK", "severity": "critical"}
        except ImportError:
            return {"name": "FastAPI", "category": "deps", "ok": False, "detail": "not installed", "message": "pip install fastapi", "severity": "critical"}
    
    def _check_uvicorn(self) -> Dict:
        try:
            import uvicorn
            return {"name": "Uvicorn", "category": "deps", "ok": True, "detail": uvicorn.__version__, "message": "OK", "severity": "critical"}
        except ImportError:
            return {"name": "Uvicorn", "category": "deps", "ok": False, "detail": "not installed", "message": "pip install uvicorn", "severity": "critical"}
    
    def _check_gpu(self) -> Dict:
        info = GPUConfig.get_cuda_info()
        if info.get("available"):
            return {
                "name": "GPU (CUDA)",
                "category": "hardware",
                "ok": True,
                "detail": f"{info['device_name']} ({info['memory_total_mb']} MB)",
                "message": "OK",
                "severity": "low",
                "info": info,
            }
        if GPUConfig.has_mps():
            return {"name": "GPU (MPS)", "category": "hardware", "ok": True, "detail": "Apple Silicon MPS", "message": "OK", "severity": "low"}
        return {"name": "GPU", "category": "hardware", "ok": True, "detail": "No GPU - CPU only", "message": "Running on CPU", "severity": "low"}
    
    def _check_models_dir(self) -> Dict:
        models = list(settings.MODELS_DIR.iterdir()) if settings.MODELS_DIR.exists() else []
        model_files = [f for f in models if f.is_file() and not f.name.startswith(".")]
        model_dirs = [d for d in models if d.is_dir()]
        return {
            "name": "Models Directory",
            "category": "storage",
            "ok": True,
            "detail": f"{len(model_files)} files, {len(model_dirs)} directories",
            "message": "OK",
            "severity": "medium",
        }
    
    def _check_plugins_dir(self) -> Dict:
        try:
            plugins = [f for f in settings.PLUGINS_DIR.iterdir() if f.suffix == ".py" and not f.name.startswith("_")]
            return {"name": "Plugins Directory", "category": "storage", "ok": True, "detail": f"{len(plugins)} plugins", "message": "OK", "severity": "medium"}
        except Exception as e:
            return {"name": "Plugins Directory", "category": "storage", "ok": False, "detail": str(e), "message": "Plugin dir issue", "severity": "medium"}
    
    def _check_critical_dependencies(self) -> Dict:
        deps = ["fastapi", "uvicorn", "pydantic", "numpy"]
        missing = []
        for dep in deps:
            try:
                __import__(dep)
            except ImportError:
                missing.append(dep)
        
        if missing:
            return {
                "name": "Critical Dependencies",
                "category": "deps",
                "ok": False,
                "detail": f"Missing: {', '.join(missing)}",
                "message": f"Missing dependencies: {', '.join(missing)}",
                "severity": "critical",
            }
        return {"name": "Critical Dependencies", "category": "deps", "ok": True, "detail": f"All {len(deps)} OK", "message": "OK", "severity": "critical"}
    
    def run_checks(self, categories: Optional[List[str]] = None) -> Dict[str, Any]:
        """Run all or filtered health checks"""
        results = []
        start_time = time.time()
        
        for name, check_fn in self.checks.items():
            try:
                result = check_fn()
                if categories is None or result.get("category") in categories:
                    results.append(result)
            except Exception as e:
                results.append({
                    "name": name,
                    "category": "unknown",
                    "ok": False,
                    "detail": str(e),
                    "message": f"Check failed: {e}",
                    "severity": "medium",
                })
        
        critical_failures = [r for r in results if not r["ok"] and r.get("severity") == "critical"]
        high_failures = [r for r in results if not r["ok"] and r.get("severity") in ("high", "critical")]
        
        all_ok = len(critical_failures) == 0
        
        return {
            "status": "healthy" if all_ok else "unhealthy" if critical_failures else "warning",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "duration_ms": round((time.time() - start_time) * 1000, 2),
            "checks": results,
            "summary": {
                "total": len(results),
                "passed": len([r for r in results if r["ok"]]),
                "failed": len([r for r in results if not r["ok"]]),
                "critical_failures": len(critical_failures),
                "high_failures": len(high_failures),
            },
        }
    
    async def run_checks_async(self, categories: Optional[List[str]] = None) -> Dict[str, Any]:
        """Run checks asynchronously"""
        return self.run_checks(categories)


# Global health checker
health_checker = HealthChecker()


# Legacy compatibility
def check_python() -> Dict:
    return health_checker._check_python()


def check_pip() -> Dict:
    return health_checker._check_pip()


def check_internet() -> Dict:
    return health_checker._check_internet()


def check_disk() -> Dict:
    return health_checker._check_disk()


def check_port(port: int) -> Dict:
    return health_checker._check_port()


def check_fastapi() -> Dict:
    return health_checker._check_fastapi()


def check_uvicorn() -> Dict:
    return health_checker._check_uvicorn()


def check_models_dir() -> Dict:
    return health_checker._check_models_dir()


def check_plugins() -> Dict:
    return health_checker._check_plugins_dir()


def run_all_checks(port: int = 8000) -> List[Dict]:
    """Legacy compatibility"""
    result = health_checker.run_checks()
    return result["checks"]
