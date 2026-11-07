"""Découverte, planification des destinations, glisser-déposer et renommages."""
import os
import hashlib
from collections import Counter
from pathlib import Path
VIDEO_EXTENSIONS = {'.mkv', '.mp4'}

def path_identity(path):
    return os.path.normcase(os.path.abspath(str(path))).casefold()

def is_within(path, folder):
    try:
        Path(path).resolve().relative_to(Path(folder).resolve())
        return True
    except ValueError:
        return False

def discover_videos(folder, recursive=False, exclude_folder=None):
    """Fichiers vidéos trouvés ; les sorties éventuellement imbriquées sont exclues."""
    root = Path(folder)
    excluded = Path(exclude_folder) if exclude_folder and is_within(exclude_folder, root) and (Path(exclude_folder).resolve() != root.resolve()) else None
    iterator = root.rglob('*') if recursive else root.iterdir()
    return sorted((str(p) for p in iterator if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS and (excluded is None or not is_within(p, excluded))), key=str.casefold)

def plan_destinations(sources, roots, output_folder, extension, preserve_tree=True):
    """Renvoie des chemins de sortie pour chaque source, sans collision de lot.

    roots associe l'identité d'un fichier à son dossier racine d'import,
    ou None si le fichier a été ajouté individuellement.
    """
    output = Path(output_folder)
    proposals = []
    for source in sources:
        source_path = Path(source)
        relative_dir = Path()
        root = roots.get(path_identity(source))
        if preserve_tree and root:
            try:
                relative_dir = source_path.parent.resolve().relative_to(Path(root).resolve())
            except ValueError:
                relative_dir = Path()
        proposals.append(output / relative_dir / (source_path.stem + '.' + extension))
    keys = [path_identity(p) for p in proposals]
    duplicates = Counter(keys)
    destinations = []
    used = set()
    for source, proposal, key in zip(sources, proposals, keys):
        target = proposal
        if duplicates[key] > 1 or key in used:
            digest = hashlib.sha256(path_identity(source).encode('utf-8')).hexdigest()[:10]
            target = proposal.with_name(f'{proposal.stem}__{digest}{proposal.suffix}')
        candidate_key = path_identity(target)
        attempt = 2
        while candidate_key in used:
            target = proposal.with_name(f'{proposal.stem}__{digest}_{attempt}{proposal.suffix}')
            candidate_key = path_identity(target)
            attempt += 1
        used.add(candidate_key)
        destinations.append(target)
    return destinations


def classify_paths(paths):
    """Sépare vidéos et dossiers existants, sans doublons et sans scanner.

    Les fichiers contenus dans les dossiers seront ensuite gérés par le
    système de surveillance existant (et l'option 'sous-dossiers').
    """
    videos, folders = ([], [])
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
    return (videos, folders)


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
            if candidate.suffix.lower() in VIDEO_EXTENSIONS and candidate.is_file() and (str(candidate.resolve()).casefold() not in occupied) and (file_signature(candidate) == signature):
                matches.append(candidate)
                if len(matches) > 1:
                    return None
    except OSError:
        return None
    return str(matches[0]) if len(matches) == 1 else None
