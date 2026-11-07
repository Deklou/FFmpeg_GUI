FFmpeg GUI V0.6.1 — Correctif import des vidéos

BUG CORRIGÉ
Quand le dossier de sortie était un dossier parent de la source
(ex. sortie = Bureau, source = Bureau/test), aucune vidéo n’apparaissait.
Le filtrage exclut maintenant les sorties uniquement si elles sont
contenues dans un sous-dossier du dossier source.

INSTALLATION
1. Fermer FFmpeg GUI.
2. Remplacer UNIQUEMENT output_planning.py par la version de ce ZIP.
3. Relancer python main.py.
4. Tester import Bureau/test avec sortie Bureau.

Le fichier test_output_planning.py est facultatif.
Aucun autre fichier ne change. Aucune modification de ton dépôt GitHub.
