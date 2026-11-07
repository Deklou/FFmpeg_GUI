# FFmpeg GUI V0.10 — Glisser-déposer et préférences d'affichage

## Installation

1. Fermer FFmpeg GUI.
2. Copier `main.py` à la racine du projet, en remplaçant l'ancien.
3. Ajouter `interface_v10.py` et `drop_paths.py` dans ce même dossier.
4. Ne pas supprimer les autres fichiers, notamment `interface_v09.py`, `interface_v08.py`, `interface_v07.py`, `interface.py`, `parallel_converter.py`, `converter.py`, etc.
5. Lancer `python main.py`.

`test_drop_paths.py` est facultatif : `python -m unittest test_drop_paths.py -v`.

## Nouveautés

- Glisser un ou plusieurs `.mp4` / `.mkv` directement dans la fenêtre ou dans le tableau.
- Glisser un ou plusieurs dossiers : ils sont importés et surveillés comme avec « Ajouter un dossier ».
- Les dossiers glissés respectent « Inclure les sous-dossiers » et « Conserver l'arborescence en sortie ».
- Les fichiers glissés directement sont considérés comme ajoutés manuellement.
- Les mêmes chemins ne sont pas ajoutés en double.
- Les dépôts sont désactivés pendant une conversion pour garantir la stabilité du lot.
- Mémorisation à la fermeture de la position et taille de la fenêtre, des largeurs/ordre des colonnes du tableau et de l'état ouvert/fermé des réglages avancés.
- Les données de disposition sont conservées localement par `QSettings`, pas dans GitHub.

## Checklist Windows

1. Déposer deux vidéos MP4/MKV sur le tableau : les deux sont importées.
2. Redéposer les mêmes vidéos : aucune ligne en doublon.
3. Déposer un dossier : ses vidéos sont importées et surveillées.
4. Cocher/décocher « Inclure les sous-dossiers » : la liste se synchronise immédiatement.
5. Déposer une vidéo manuellement située dans un sous-dossier, puis décocher la récursivité : elle reste présente.
6. Déposer un fichier non vidéo ou un lien Web : aucune vidéo n'est importée.
7. Ajouter ou renommer une vidéo dans un dossier glissé : après environ 3 secondes, le tableau se met à jour.
8. Redimensionner et déplacer la fenêtre, modifier des largeurs de colonnes, ouvrir les réglages avancés. Fermer puis rouvrir l'application : retrouver ces préférences.
9. Lancer une conversion puis tenter un dépôt : il doit être refusé pendant l'encodage.
10. Vérifier les conversions parallèles, les presets, les tailles de sortie et l'annulation : comportement inchangé.

## Remarques

- Pas de gestion des URL distantes : le glisser-déposer vise les chemins locaux visibles dans l'Explorateur Windows.
- Les choix de taille/colonnes sont stockés par utilisateur dans les paramètres locaux de l'application. La configuration personnelle d'un utilisateur ne sera pas intégrée à un futur exécutable « vanilla ».
- Les conversions et la synchronisation continuent à utiliser les modules V0.9 et précédents.
