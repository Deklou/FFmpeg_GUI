# FFmpeg GUI

FFmpeg GUI est une application Windows avec interface graphique pour convertir des vidéos MP4 et MKV avec **FFmpeg**.

Elle permet de choisir le codec H.264/H.265, la qualité et les presets, de convertir plusieurs vidéos simultanément, de conserver les sous-dossiers et de suivre la progression, le temps restant et les économies d'espace disque. Glissez simplement vos vidéos ou dossiers dans la fenêtre.

## Installation (version Python)

1. Installez **[FFmpeg](https://ffmpeg.org/download.html)** : rendez `ffmpeg.exe` accessible dans le `PATH` Windows ou placez-le à côté de `main.py` (ou dans un dossier `bin/`). `ffprobe.exe` est conseillé pour les durées et estimations.
2. Installez Python 3.10+ puis exécutez `pip install -r requirements.txt`.
3. Lancez `python main.py`.

Les fichiers source ne sont jamais supprimés. Les sorties existantes ne sont pas écrasées. Les préférences et presets sont stockés localement, en dehors du dépôt.

## Licence

Aucune licence n'est encore déclarée pour ce dépôt. À définir avant la distribution publique.
