# FFmpeg GUI — Étape 2

Interface Windows en Python / PySide6, construite progressivement.

## Lancement

```powershell
python -m pip install -r requirements.txt
python main.py
```

Configurer le chemin vers `ffmpeg.exe` si le programme n'est pas retrouvé automatiquement.

## Fonctions disponibles

- Import manuel de vidéos `.mkv` et `.mp4` ou import d'un dossier (non récursif).
- File d'attente, suppression des entrées, affichage des dossiers et mémorisation des chemins via `QSettings`.
- Conversion **séquentielle** vers **MKV / H.265** (`libx265`, CRF 28, preset `medium`).
- Copie des pistes audio et sous-titres avec `-map 0:v -map 0:a? -map 0:s? -c:a copy -c:s copy`.
- Progression par vidéo (si `ffprobe` disponible) et globale, annulation, messages d'erreur.
- Ignore toute destination `.mkv` déjà existante.
- Écrit d'abord dans un fichier temporaire `.part.mkv`; ne publie le MKV final qu'après succès.

## Précautions

- **La source n'est jamais effacée.** Choisir un dossier de sortie distinct est recommandé.
- Des sources `exemple.mp4` et `exemple.mkv` ont toutes deux pour cible `exemple.mkv` : seule la première sera convertie, la seconde sera ignorée. Cette collision de noms sera mieux signalée dans une version ultérieure.
- Tout MKV existant est considéré comme déjà converti (comme dans le script PowerShell d'origine) : ce n'est pas une vérification approfondie du contenu.
- Si `ffprobe.exe` manque, la conversion fonctionne mais l'avancement intermédiaire ne peut pas être estimé.
- Les paramètres d'encodage sont volontairement **fixes dans cette étape**. Les presets et options suivront une fois le moteur validé.
- L'annulation arrête le processus courant et supprime la sortie temporaire, mais n'efface pas les conversions déjà terminées.
