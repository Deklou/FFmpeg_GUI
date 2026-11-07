"""Identification conservative des renommages sur un même volume.

On ne devine jamais un renommage à partir d'un nom ou d'une taille seule.
"""

from pathlib import Path

VIDEO_EXTENSIONS = {'.mp4', '.mkv'}


def file_signature(path):
    """Signature de fichier, ou None si l'OS n'offre pas d'ID fiable.

    st_dev/st_ino identifient l'objet fichier sur un volume local. La taille et
    le mtime limitent le risque de confusion lors d'une suppression/recréation.
    """
    try:
        stat = Path(path).stat()
    except OSError:
        return None
    if not getattr(stat, 'st_ino', 0):
        return None
    return (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns)


def renamed_candidate(old_path, signature, occupied_paths=()):
    """Renvoie le nouveau chemin seulement si la correspondance est unique.

    Ne cherche que dans le dossier d'origine et ne traverse pas ses sous-dossiers.
    Cela protège contre la réassociation à un autre fichier homonyme ou semblable.
    """
    if signature is None or Path(old_path).exists():
        return None
    parent = Path(old_path).parent
    occupied = {str(Path(p).resolve()).casefold() for p in occupied_paths}
    matches = []
    try:
        for candidate in parent.iterdir():
            if (candidate.suffix.lower() in VIDEO_EXTENSIONS and
                    candidate.is_file() and
                    str(candidate.resolve()).casefold() not in occupied and
                    file_signature(candidate) == signature):
                matches.append(candidate)
                if len(matches) > 1:
                    return None
    except OSError:
        return None
    return str(matches[0]) if len(matches) == 1 else None
