# FFmpeg GUI

FFmpeg GUI est une application Windows avec interface graphique pour convertir des vidéos MP4 et MKV avec **FFmpeg**.

Glissez vos vidéos ou dossiers dans la fenêtre, choisissez le codec H.264/H.265, la qualité et le format de sortie. L'application permet les conversions simultanées, conserve les arborescences et affiche la progression et les statistiques de compression.

## Installation (version Python)

1. Téléchargez **[FFmpeg](https://ffmpeg.org/download.html)**, puis sélectionnez `ffmpeg.exe` dans l'application (ou placez-le dans le `PATH` Windows, à côté de `main.py` ou dans `bin/`). `ffprobe.exe` est conseillé pour les estimations de durée.
2. Installez Python 3.10+ et exécutez `python -m pip install -r requirements.txt`.
3. Lancez `python main.py`.

Les fichiers source sont conservés et les sorties déjà présentes ne sont pas écrasées. Les préférences et presets sont stockés sur le PC de l'utilisateur, hors du dépôt.
