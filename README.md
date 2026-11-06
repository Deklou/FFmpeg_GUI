# FFmpeg GUI — V0.3

Application Windows en Python / PySide6 pour convertir des lots de vidéos MP4 et MKV sans ligne de commande.

## Installation et lancement

Depuis le dossier du projet :

```powershell
python -m pip install -r requirements.txt
python main.py
```

Sélectionner ensuite `ffmpeg.exe` si l'application ne l'a pas trouvé automatiquement. `ffprobe.exe` placé dans le même dossier permet d'afficher la progression par durée.

## Nouveautés V0.3

- Codecs H.265 (`libx265`) et H.264 (`libx264`).
- CRF personnalisable (0 à 51) et vitesse de compression.
- Audio : copie, AAC 192 kb/s, ou aucune piste.
- Sous-titres : copie (MKV), ou suppression.
- Conteneur : MKV ou MP4.
- Presets intégrés et personnalisés, sélection immédiatement appliquée.
- Les paramètres d'un lot sont figés au démarrage de la conversion.

Le preset **H.265 · Archivage MKV (habituel)** reproduit le réglage de ton script PowerShell : H.265, CRF 28, `medium`, audio et sous-titres copiés en MKV.

Les presets personnalisés sont enregistrés dans `~/.ffmpeg_gui/presets.json` ; ce fichier n'est pas stocké dans GitHub.

## Points à connaître

- Les fichiers de sortie déjà existants sont ignorés, même s'ils ont été produits avec d'autres paramètres. Pour comparer plusieurs encodages, utiliser un dossier de sortie distinct ou renommer les fichiers.
- Les pistes de sous-titres ne sont pas copiées vers MP4. L'application les désactive en passant de MKV à MP4.
- En MP4, copier une piste audio non compatible peut entraîner une erreur FFmpeg. Le mode AAC 192 kb/s est recommandé pour la compatibilité.
- Seuls les fichiers `.mkv` et `.mp4` sont importés ; l'ajout d'un dossier ne parcourt pas ses sous-dossiers.
- Un lot est traité séquentiellement et peut être annulé.

## Tests du moteur

```powershell
python -m unittest -v test_settings.py
```
