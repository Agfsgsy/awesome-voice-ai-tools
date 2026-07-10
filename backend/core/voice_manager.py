"""Enhanced Voice Manager - Complete Voice Library Management"""
import json
import hashlib
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum

from backend.core.config import settings
from backend.core.logger import get_logger

logger = get_logger("voice_manager")


class VoiceGender(str, Enum):
    MALE = "male"
    FEMALE = "female"
    UNKNOWN = "unknown"


class VoiceCategory(str, Enum):
    NARRATION = "narration"
    CONVERSATIONAL = "conversational"
    PROFESSIONAL = "professional"
    RELIGIOUS = "religious"
    CHILD = "child"
    ELDERLY = "elderly"
    CUSTOM = "custom"


@dataclass
class VoiceInfo:
    """Complete voice information"""
    id: str
    name: str
    engine: str
    language: str = "ar"
    gender: str = VoiceGender.UNKNOWN.value
    category: str = VoiceCategory.NARRATION.value
    description: str = ""
    tags: List[str] = field(default_factory=list)
    is_favorite: bool = False
    is_default: bool = False
    sample_rate: int = 22050
    preview_url: str = ""
    preview_path: str = ""
    cloned_from: str = ""
    created_at: str = ""
    usage_count: int = 0
    quality_score: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class VoiceManager:
    """Production-grade voice manager with full voice library features"""
    
    def __init__(self):
        self.voices_dir = settings.VOICES_DIR
        self.library_file = settings.VOICE_LIBRARY_FILE
        self.voices: Dict[str, VoiceInfo] = {}
        self._favorites: set = set()
        self._load_library()
    
    def _load_library(self):
        """Load voice library from file"""
        if self.library_file.exists():
            try:
                with open(self.library_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                
                voices_data = data.get("voices", {})
                for vid, vdata in voices_data.items():
                    self.voices[vid] = VoiceInfo(**vdata)
                
                self._favorites = set(data.get("favorites", []))
            except Exception as e:
                logger.warning(f"Failed to load voice library: {e}")
    
    def _save_library(self):
        """Save voice library to file"""
        try:
            self.library_file.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "voices": {vid: v.to_dict() for vid, v in self.voices.items()},
                "favorites": list(self._favorites),
                "updated_at": datetime.utcnow().isoformat(),
            }
            with open(self.library_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to save voice library: {e}")
    
    def add_voice(self, voice: VoiceInfo) -> bool:
        """Add a voice to the library"""
        voice.created_at = datetime.utcnow().isoformat()
        self.voices[voice.id] = voice
        self._save_library()
        logger.info(f"Added voice: {voice.id}")
        return True
    
    def remove_voice(self, voice_id: str) -> bool:
        """Remove a voice from the library"""
        if voice_id in self.voices:
            del self.voices[voice_id]
            self._favorites.discard(voice_id)
            self._save_library()
            logger.info(f"Removed voice: {voice_id}")
            return True
        return False
    
    def list_all_voices(self) -> List[Dict[str, Any]]:
        """List all voices including plugin-discovered voices"""
        all_voices = []
        seen_ids = set()
        
        # Add plugin voices
        try:
            from backend.core.tts_registry import tts_registry
            plugins = tts_registry.get_all_plugins()
            for plugin in plugins:
                try:
                    voices = plugin.list_voices()
                    for v in voices:
                        vid = f"{plugin.name}/{v.get('name', 'unknown')}"
                        if vid not in seen_ids:
                            v["engine"] = plugin.name
                            v["id"] = vid
                            v["source"] = "plugin"
                            all_voices.append(v)
                            seen_ids.add(vid)
                except Exception as e:
                    logger.warning(f"Failed to list voices for {plugin.name}: {e}")
        except Exception:
            pass
        
        # Add library voices
        for vid, voice in self.voices.items():
            if vid not in seen_ids:
                vdict = voice.to_dict()
                vdict["source"] = "library"
                vdict["is_favorite"] = vid in self._favorites
                all_voices.append(vdict)
                seen_ids.add(vid)
        
        return all_voices
    
    def list_voices_by_language(self, language: str) -> List[Dict[str, Any]]:
        """List voices filtered by language"""
        return [v for v in self.list_all_voices() if v.get("language") == language]
    
    def list_voices_by_engine(self, engine: str) -> List[Dict[str, Any]]:
        """List voices for a specific engine"""
        return [v for v in self.list_all_voices() if v.get("engine") == engine]
    
    def list_voices_by_category(self, category: str) -> List[Dict[str, Any]]:
        """List voices by category"""
        return [v for v in self.list_all_voices() if v.get("category") == category]
    
    def list_voices_by_tag(self, tag: str) -> List[Dict[str, Any]]:
        """List voices by tag"""
        return [v for v in self.list_all_voices() if tag in v.get("tags", [])]
    
    def list_arabic_voices(self) -> List[Dict[str, Any]]:
        """List Arabic voices"""
        return self.list_voices_by_language("ar")
    
    def search_voices(self, query: str = "", language: str = "", engine: str = "",
                      gender: str = "", category: str = "", tags: List[str] = None) -> List[Dict[str, Any]]:
        """Search voices with multiple filters"""
        voices = self.list_all_voices()
        results = []
        query_lower = query.lower() if query else ""
        
        for voice in voices:
            # Text search
            if query_lower:
                searchable = f"{voice.get('name', '')} {voice.get('description', '')}"
                if query_lower not in searchable.lower():
                    continue
            
            # Filters
            if language and voice.get("language") != language:
                continue
            if engine and voice.get("engine") != engine:
                continue
            if gender and voice.get("gender") != gender:
                continue
            if category and voice.get("category") != category:
                continue
            if tags:
                voice_tags = voice.get("tags", [])
                if not any(t in voice_tags for t in tags):
                    continue
            
            results.append(voice)
        
        return results
    
    def get_voice(self, voice_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific voice"""
        if voice_id in self.voices:
            result = self.voices[voice_id].to_dict()
            result["is_favorite"] = voice_id in self._favorites
            return result
        
        # Search in all voices
        for v in self.list_all_voices():
            if v.get("id") == voice_id:
                return v
        
        return None
    
    def toggle_favorite(self, voice_id: str) -> bool:
        """Toggle favorite status"""
        if voice_id in self._favorites:
            self._favorites.discard(voice_id)
            is_fav = False
        else:
            self._favorites.add(voice_id)
            is_fav = True
        
        self._save_library()
        logger.info(f"Voice {voice_id} favorite: {is_fav}")
        return is_fav
    
    def list_favorites(self) -> List[Dict[str, Any]]:
        """List favorite voices"""
        all_voices = self.list_all_voices()
        return [v for v in all_voices if v.get("id") in self._favorites]
    
    def set_default_voice(self, voice_id: str) -> bool:
        """Set a voice as default for its engine/language"""
        voice = self.voices.get(voice_id)
        if not voice:
            return False
        
        # Unset other defaults for same engine/language
        for vid, v in self.voices.items():
            if v.engine == voice.engine and v.language == voice.language:
                v.is_default = False
        
        voice.is_default = True
        self._save_library()
        logger.info(f"Set default voice: {voice_id}")
        return True
    
    def get_default_voice(self, engine: str = "", language: str = "ar") -> Optional[Dict[str, Any]]:
        """Get default voice for engine/language"""
        for vid, voice in self.voices.items():
            if voice.is_default:
                if (not engine or voice.engine == engine) and voice.language == language:
                    return voice.to_dict()
        
        # Fallback: first voice matching criteria
        voices = self.list_all_voices()
        for v in voices:
            if (not engine or v.get("engine") == engine) and v.get("language") == language:
                return v
        
        return None
    
    def update_voice_tags(self, voice_id: str, tags: List[str]) -> bool:
        """Update voice tags"""
        if voice_id not in self.voices:
            return False
        self.voices[voice_id].tags = tags
        self._save_library()
        return True
    
    def clone_voice(self, source_voice_id: str, new_name: str, 
                    reference_audio: str = "") -> Dict[str, Any]:
        """Clone a voice configuration"""
        source = self.voices.get(source_voice_id)
        if not source:
            return {"success": False, "message": "Source voice not found"}
        
        new_id = f"{source.engine}/{new_name}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
        
        cloned = VoiceInfo(
            id=new_id,
            name=new_name,
            engine=source.engine,
            language=source.language,
            gender=source.gender,
            category=VoiceCategory.CUSTOM.value,
            description=f"Cloned from {source.name}",
            tags=source.tags + ["cloned"],
            cloned_from=source_voice_id,
            metadata={"source": source_voice_id, "reference_audio": reference_audio},
        )
        
        self.add_voice(cloned)
        logger.info(f"Cloned voice: {source_voice_id} -> {new_id}")
        
        return {"success": True, "voice_id": new_id, "message": f"Voice cloned as {new_name}"}
    
    def import_voice_pack(self, pack_path: Path) -> Dict[str, Any]:
        """Import a voice pack (JSON file with multiple voices)"""
        if not pack_path.exists():
            return {"success": False, "message": "Pack file not found"}
        
        try:
            with open(pack_path, "r", encoding="utf-8") as f:
                pack = json.load(f)
            
            imported = 0
            for vdata in pack.get("voices", []):
                voice = VoiceInfo(**vdata)
                self.add_voice(voice)
                imported += 1
            
            logger.info(f"Imported voice pack: {imported} voices")
            return {"success": True, "imported": imported}
            
        except Exception as e:
            return {"success": False, "message": str(e)}
    
    def export_voice_pack(self, voice_ids: List[str], export_path: Optional[Path] = None) -> Dict[str, Any]:
        """Export voices as a voice pack"""
        voices = []
        for vid in voice_ids:
            if vid in self.voices:
                voices.append(self.voices[vid].to_dict())
        
        if not voices:
            return {"success": False, "message": "No voices found to export"}
        
        export_file = export_path or (settings.OUTPUTS_DIR / f"voice_pack_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json")
        
        try:
            with open(export_file, "w", encoding="utf-8") as f:
                json.dump({
                    "name": "Voice Pack Export",
                    "exported_at": datetime.utcnow().isoformat(),
                    "count": len(voices),
                    "voices": voices,
                }, f, ensure_ascii=False, indent=2)
            
            return {"success": True, "path": str(export_file), "count": len(voices)}
        except Exception as e:
            return {"success": False, "message": str(e)}
    
    def get_stats(self) -> Dict[str, Any]:
        """Get voice library statistics"""
        all_voices = self.list_all_voices()
        
        languages = {}
        engines = {}
        categories = {}
        genders = {}
        
        for v in all_voices:
            lang = v.get("language", "unknown")
            languages[lang] = languages.get(lang, 0) + 1
            
            eng = v.get("engine", "unknown")
            engines[eng] = engines.get(eng, 0) + 1
            
            cat = v.get("category", "unknown")
            categories[cat] = categories.get(cat, 0) + 1
            
            gen = v.get("gender", "unknown")
            genders[gen] = genders.get(gen, 0) + 1
        
        return {
            "total": len(all_voices),
            "library_count": len(self.voices),
            "favorites": len(self._favorites),
            "by_language": languages,
            "by_engine": engines,
            "by_category": categories,
            "by_gender": genders,
        }


# Global voice manager instance
voice_manager = VoiceManager()
