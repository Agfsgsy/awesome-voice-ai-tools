"""StyleTTS2 Plugin - Open Source high-quality TTS by yl4579"""
from typing import Dict, List, Any
from pathlib import Path
from backend.plugins.tts_plugin_base import TTSPluginBase
from backend.core.logger import get_logger

logger = get_logger("plugin_styletts2")


class StyleTTS2Plugin(TTSPluginBase):
    name = "styletts2"
    label = "StyleTTS2"
    description = "High-quality style-based TTS, requires GPU for best results"
    homepage = "https://github.com/yl4579/StyleTTS2"
    is_open_source = True
    requires_gpu = True

    STYLETTS2_MODELS = {
        "LibriTTS": {
            "repo": "https://github.com/yl4579/StyleTTS2",
            "config_path": "Models/Config/config.yml",
            "model_path": "Models/LibriTTS",
            "language": "en",
        },
        "LJSpeech": {
            "repo": "https://github.com/yl4579/StyleTTS2",
            "config_path": "Models/Config/config.yml",
            "model_path": "Models/LJSpeech",
            "language": "en",
        },
    }

    def check(self) -> bool:
        try:
            import torch
            import styles
            return True
        except ImportError:
            return False
        except Exception:
            return False

    def install(self) -> Dict[str, Any]:
        import subprocess, sys
        try:
            # Clone the repo
            repo_path = self.models_dir / "StyleTTS2_repo"
            if not repo_path.exists():
                subprocess.check_call(["git", "clone", "https://github.com/yl4579/StyleTTS2.git", str(repo_path)])
            subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "-r", str(repo_path / "requirements.txt")])
            import sys as sys_module
            if str(repo_path) not in sys_module.path:
                sys_module.path.insert(0, str(repo_path))
            installed = self.check()
            return {"success": installed, "engine": self.name, "message": "Installed StyleTTS2" if installed else "Install partial"}
        except Exception as e:
            return {"success": False, "engine": self.name, "message": str(e)}

    def download_models(self, model_name: str = "LibriTTS") -> Dict[str, Any]:
        import urllib.request
        if model_name not in self.STYLETTS2_MODELS:
            return {"success": False, "message": f"Unknown model: {model_name}"}

        meta = self.STYLETTS2_MODELS[model_name]
        repo_path = self.models_dir / "StyleTTS2_repo"

        try:
            # Pre-trained model URLs from the official repo
            model_urls = {
                "LibriTTS": "https://huggingface.co/yl4579/StyleTTS2-LibriTTS/resolve/main/models",
                "LJSpeech": "https://huggingface.co/yl4579/StyleTTS2-LJSpeech/resolve/main/models",
            }

            model_dir = repo_path / "Models" / model_name
            model_dir.mkdir(parents=True, exist_ok=True)

            # Download config and model files
            base_url = model_urls.get(model_name, "")
            if base_url:
                for fname in ["config.yml", "epoch_2nd_00100.pth"]:
                    filepath = model_dir / fname
                    if not filepath.exists():
                        urllib.request.urlretrieve(f"{base_url}/{fname}", str(filepath))

            marker = self.models_dir / f"{model_name}.installed"
            marker.write_text(f"StyleTTS2 {model_name} model ready")
            return {"success": True, "model": model_name, "path": str(model_dir)}
        except Exception as e:
            return {"success": False, "model": model_name, "message": str(e)}

    def list_models(self) -> List[Dict]:
        models = []
        for name, meta in self.STYLETTS2_MODELS.items():
            marker = self.models_dir / f"{name}.installed"
            models.append({
                "name": name,
                "language": meta["language"],
                "downloaded": marker.exists(),
            })
        return models

    def list_voices(self) -> List[Dict]:
        return [
            {"name": "default", "model": "LibriTTS", "language": "en"},
            {"name": "default", "model": "LJSpeech", "language": "en"},
        ]

    async def generate(self, text: str, voice: str = "default",
                       language: str = "en", speed: float = 1.0) -> Dict[str, Any]:
        if not self.check():
            return {"success": False, "engine": self.name, "message": "StyleTTS2 not installed. Run install()."}
        try:
            import sys as sys_module
            repo_path = self.models_dir / "StyleTTS2_repo"
            if str(repo_path) not in sys_module.path:
                sys_module.path.insert(0, str(repo_path))

            import torch
            import styles
            import yaml
            from pathlib import Path as P

            config_path = repo_path / "Models" / "Config" / "config.yml"
            model_path = repo_path / "Models" / "LibriTTS" / "epoch_2nd_00100.pth"

            with open(config_path, "r") as f:
                config = yaml.safe_load(f)

            model = styles.load_model(config, model_path, device="cpu")
            audio = model.inference(text, speed=speed)
            filepath = self._save_wav(audio, text, 24000)
            return {
                "success": True,
                "engine": self.name,
                "file": str(filepath),
                "url": f"/api/downloads/{filepath.name}",
                "message": f"Generated with StyleTTS2",
            }
        except Exception as e:
            logger.error(f"StyleTTS2 generate failed: {e}")
            auto_install_msg = "StyleTTS2 requires manual setup. Clone the repo, download models from HuggingFace, and install requirements."
            return {"success": False, "engine": self.name, "message": f"{auto_install_msg} Error: {e}"}


PLUGIN_CLASS = StyleTTS2Plugin
PLUGIN_NAME = "StyleTTS2"
PLUGIN_DESCRIPTION = "High-quality style-based TTS, requires GPU for best results"
