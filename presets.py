"""Sauvegarde locale de presets, indépendante de GitHub et du dépôt."""

import json
import os
import tempfile
from pathlib import Path

from conversion_settings import ConversionSettings


BUILTIN_PRESETS = {
    "H.265 · Archivage MKV (habituel)": ConversionSettings().to_dict(),
    "H.264 · Compatible MP4": ConversionSettings(
        codec="libx264", crf=23, speed="medium",
        audio="aac", subtitles="none", container="mp4"
    ).to_dict(),
    "H.265 · MP4 compact": ConversionSettings(
        codec="libx265", crf=28, speed="medium",
        audio="aac", subtitles="none", container="mp4"
    ).to_dict(),
}


class PresetStore:
    def __init__(self, path=None):
        self.path = Path(path) if path else Path.home() / ".ffmpeg_gui" / "presets.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.custom = self.load()

    def load(self):
        if not self.path.exists():
            return {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("Le JSON doit contenir un objet.")
            return {
                name: ConversionSettings.from_dict(values).to_dict()
                for name, values in data.items()
                if isinstance(name, str) and isinstance(values, dict)
            }
        except (OSError, ValueError, TypeError) as exc:
            raise ValueError(f"Impossible de lire les presets ({self.path}) : {exc}") from exc

    def all_presets(self):
        return {**BUILTIN_PRESETS, **self.custom}

    def save(self):
        payload = json.dumps(self.custom, ensure_ascii=False, indent=2)
        fd, temporary = tempfile.mkstemp(prefix=".presets_", suffix=".tmp", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as file:
                file.write(payload)
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary, self.path)
        finally:
            Path(temporary).unlink(missing_ok=True)

    def set(self, name, values):
        name = name.strip()
        if not name:
            raise ValueError("Nom de preset vide.")
        if name in BUILTIN_PRESETS:
            raise ValueError("Un preset intégré ne peut pas être remplacé.")
        valid = ConversionSettings.from_dict(values).to_dict()
        self.custom[name] = valid
        self.save()

    def delete(self, name):
        if name in self.custom:
            del self.custom[name]
            self.save()
