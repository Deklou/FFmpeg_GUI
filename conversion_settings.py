"""Paramètres et construction des commandes FFmpeg (sans dépendance Qt)."""

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class ConversionSettings:
    codec: str = "libx265"
    crf: int = 28
    speed: str = "medium"
    audio: str = "copy"
    subtitles: str = "copy"
    container: str = "mkv"

    def validate(self):
        if self.codec not in {"libx264", "libx265"}:
            raise ValueError("Codec vidéo non reconnu.")
        if not 0 <= self.crf <= 51:
            raise ValueError("Le CRF doit être compris entre 0 et 51.")
        if self.speed not in {"ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow"}:
            raise ValueError("Preset de vitesse non reconnu.")
        if self.audio not in {"copy", "aac", "none"}:
            raise ValueError("Mode audio non reconnu.")
        if self.subtitles not in {"copy", "none"}:
            raise ValueError("Mode de sous-titres non reconnu.")
        if self.container not in {"mkv", "mp4"}:
            raise ValueError("Format de sortie non reconnu.")
        if self.container == "mp4" and self.subtitles == "copy":
            raise ValueError(
                "La copie des sous-titres vers MP4 n'est pas prise en charge. "
                "Choisis « Ignorer » pour les sous-titres ou le format MKV."
            )

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data):
        # Les anciens presets partiels héritent des valeurs historiques.
        defaults = cls().to_dict()
        defaults.update({key: value for key, value in data.items() if key in defaults})
        settings = cls(**defaults)
        settings.validate()
        return settings


def build_command(ffmpeg_path, source, target, settings):
    """Liste d'arguments prête pour subprocess, sans exécuter de commande shell."""
    settings.validate()
    command = [
        str(ffmpeg_path), "-hide_banner", "-nostdin", "-nostats", "-y",
        "-i", str(source), "-map", "0:v",
    ]
    if settings.audio != "none":
        command.extend(["-map", "0:a?"])
    if settings.subtitles == "copy":
        command.extend(["-map", "0:s?"])
    command.extend([
        "-c:v", settings.codec, "-crf", str(settings.crf),
        "-preset", settings.speed,
    ])
    if settings.audio == "copy":
        command.extend(["-c:a", "copy"])
    elif settings.audio == "aac":
        command.extend(["-c:a", "aac", "-b:a", "192k"])
    if settings.subtitles == "copy":
        command.extend(["-c:s", "copy"])
    command.extend(["-progress", "pipe:1", str(target)])
    return command
