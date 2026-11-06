# FFmpeg GUI

Interface de bureau Python / PySide6 pour préparer des conversions vidéo FFmpeg.

## Étape 1

- Ajouter une ou plusieurs vidéos MKV/MP4.
- Importer les vidéos MKV/MP4 d'un dossier (sans sous-dossiers).
- Afficher la liste des vidéos et leurs dossiers source.
- Choisir un dossier de sortie.
- Mémoriser les derniers dossiers utilisés.
- Retirer une vidéo ou vider la liste.

**Aucune conversion n'est encore implémentée.**

## Lancer

```powershell
python -m pip install -r requirements.txt
python main.py
```

## Étape suivante

Ajouter FFmpeg, les paramètres H.265 et la gestion de la file de conversion.
