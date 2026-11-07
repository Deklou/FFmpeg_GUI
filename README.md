# FFmpeg GUI

Logiciel Windows pour convertir des vidéos MP4 et MKV avec FFmpeg.

Il permet de convertir plusieurs vidéos à la fois, de choisir entre H.264 et H.265, de régler la qualité et de suivre la progression. On peut aussi glisser-déposer des fichiers ou des dossiers dans la fenêtre.

## Télécharger

Récupérer `FFmpeg_GUI.exe` dans les [Releases](https://github.com/Deklou/FFmpeg_GUI/releases).

FFmpeg reste nécessaire : [télécharger FFmpeg](https://ffmpeg.org/download.html), puis sélectionner `ffmpeg.exe` dans le logiciel (dans le dossier `bin` du téléchargement).

## Lancer depuis le code source

```powershell
python -m pip install -r requirements.txt
python main.py
```