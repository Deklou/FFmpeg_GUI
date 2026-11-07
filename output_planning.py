"""Choix déterministe des destinations, indépendamment de l'interface Qt.

En mode plat, les noms en collision sont suffixés par une empreinte stable du
chemin source. Aucun fichier existant n'est écrasé par la planification.
"""
from collections import Counter
import hashlib
import os
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
    # Exclure les sorties uniquement si leur dossier se trouve DANS la
    # source. Si la sortie est un parent de la source (ex. Bureau), exclure
    # tous les fichiers ferait disparaître les vidéos importées.
    excluded = (
        Path(exclude_folder)
        if exclude_folder and is_within(exclude_folder, root)
        and Path(exclude_folder).resolve() != root.resolve()
        else None
    )
    iterator = root.rglob('*') if recursive else root.iterdir()
    return sorted(
        (str(p) for p in iterator
         if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS
         and (excluded is None or not is_within(p, excluded))),
        key=str.casefold,
    )


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
