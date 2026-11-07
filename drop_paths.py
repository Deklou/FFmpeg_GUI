"""Classification sûre des chemins glissés dans FFmpeg GUI (sans Qt)."""
from pathlib import Path

VIDEO_EXTENSIONS = {".mp4", ".mkv"}


def classify_paths(paths):
    """Sépare vidéos et dossiers existants, sans doublons et sans scanner.

    Les fichiers contenus dans les dossiers seront ensuite gérés par le
    système de surveillance existant (et l'option 'sous-dossiers').
    """
    videos, folders = [], []
    seen = set()
    for value in paths:
        path = Path(value)
        try:
            if not path.exists():
                continue
            identity = str(path.resolve()).casefold()
            if identity in seen:
                continue
            if path.is_dir():
                folders.append(str(path))
                seen.add(identity)
            elif path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS:
                videos.append(str(path))
                seen.add(identity)
        except OSError:
            continue
    return videos, folders
