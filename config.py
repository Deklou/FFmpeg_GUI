"""Réglages de conversion et presets locaux."""
import json
import os
import tempfile
from pathlib import Path
from dataclasses import asdict, dataclass
@dataclass(frozen=True)
class ConversionSettings:
    codec: str = 'libx265'
    crf: int = 28
    speed: str = 'medium'
    audio: str = 'copy'
    subtitles: str = 'copy'
    container: str = 'mkv'

    def validate(self):
        if self.codec not in {'libx264', 'libx265'}:
            raise ValueError('Codec vidéo non reconnu.')
        if not 0 <= self.crf <= 51:
            raise ValueError('Le CRF doit être compris entre 0 et 51.')
        if self.speed not in {'ultrafast', 'superfast', 'veryfast', 'faster', 'fast', 'medium', 'slow', 'slower', 'veryslow'}:
            raise ValueError('Preset de vitesse non reconnu.')
        if self.audio not in {'copy', 'aac', 'none'}:
            raise ValueError('Mode audio non reconnu.')
        if self.subtitles not in {'copy', 'none'}:
            raise ValueError('Mode de sous-titres non reconnu.')
        if self.container not in {'mkv', 'mp4'}:
            raise ValueError('Format de sortie non reconnu.')
        if self.container == 'mp4' and self.subtitles == 'copy':
            raise ValueError("La copie des sous-titres vers MP4 n'est pas prise en charge. Choisis « Ignorer » pour les sous-titres ou le format MKV.")

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data):
        defaults = cls().to_dict()
        defaults.update({key: value for key, value in data.items() if key in defaults})
        settings = cls(**defaults)
        settings.validate()
        return settings

def build_command(ffmpeg_path, source, target, settings):
    """Liste d'arguments prête pour subprocess, sans exécuter de commande shell."""
    settings.validate()
    command = [str(ffmpeg_path), '-hide_banner', '-nostdin', '-nostats', '-y', '-i', str(source), '-map', '0:v']
    if settings.audio != 'none':
        command.extend(['-map', '0:a?'])
    if settings.subtitles == 'copy':
        command.extend(['-map', '0:s?'])
    command.extend(['-c:v', settings.codec, '-crf', str(settings.crf), '-preset', settings.speed])
    if settings.audio == 'copy':
        command.extend(['-c:a', 'copy'])
    elif settings.audio == 'aac':
        command.extend(['-c:a', 'aac', '-b:a', '192k'])
    if settings.subtitles == 'copy':
        command.extend(['-c:s', 'copy'])
    command.extend(['-progress', 'pipe:1', str(target)])
    return command

BUILTIN_PRESETS = {'H.265 · Archivage MKV (habituel)': ConversionSettings().to_dict(), 'H.264 · Compatible MP4': ConversionSettings(codec='libx264', crf=23, speed='medium', audio='aac', subtitles='none', container='mp4').to_dict(), 'H.265 · MP4 compact': ConversionSettings(codec='libx265', crf=28, speed='medium', audio='aac', subtitles='none', container='mp4').to_dict()}

def default_preset_path():
    """Stockage utilisateur de l'application, sans chemin personnel embarqué."""
    base = Path(os.environ.get('APPDATA') or (Path.home() / '.config'))
    return base / 'FFmpegGUI' / 'presets.json'


class PresetStore:

    def __init__(self, path=None):
        self.path = Path(path) if path else default_preset_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.custom = self.load()

    def load(self):
        if not self.path.exists():
            return {}
        try:
            data = json.loads(self.path.read_text(encoding='utf-8'))
            if not isinstance(data, dict):
                raise ValueError('Le JSON doit contenir un objet.')
            return {name: ConversionSettings.from_dict(values).to_dict() for name, values in data.items() if isinstance(name, str) and isinstance(values, dict)}
        except (OSError, ValueError, TypeError) as exc:
            raise ValueError(f'Impossible de lire les presets ({self.path}) : {exc}') from exc

    def all_presets(self):
        return {**BUILTIN_PRESETS, **self.custom}

    def save(self):
        payload = json.dumps(self.custom, ensure_ascii=False, indent=2)
        fd, temporary = tempfile.mkstemp(prefix='.presets_', suffix='.tmp', dir=self.path.parent)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as file:
                file.write(payload)
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary, self.path)
        finally:
            Path(temporary).unlink(missing_ok=True)

    def set(self, name, values):
        name = name.strip()
        if not name:
            raise ValueError('Nom de preset vide.')
        if name in BUILTIN_PRESETS:
            raise ValueError('Un preset intégré ne peut pas être remplacé.')
        valid = ConversionSettings.from_dict(values).to_dict()
        self.custom[name] = valid
        self.save()

    def delete(self, name):
        if name in self.custom:
            del self.custom[name]
            self.save()
