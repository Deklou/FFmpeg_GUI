FFmpeg GUI V0.10.1 — Correctif : renommage des vidéos déposées individuellement

Installation :
1. Fermer FFmpeg GUI.
2. Remplacer main.py dans votre dossier projet.
3. Ajouter interface_v101.py et rename_tracking.py.
4. Conserver tous les autres fichiers (notamment interface_v10.py).
5. Exécuter : python main.py

Comportement :
- Une vidéo ajoutée par glisser-déposer ou « Ajouter des vidéos », puis renommée
  dans son dossier d'origine, conserve sa ligne après la synchronisation (~3 s).
- Le suivi repose sur l'identifiant du fichier exposé par le système de fichiers
  et sur ses métadonnées. Il ne s'agit PAS d'une comparaison approximative des
  noms ou des tailles. Si le support ne fournit pas d'identifiant exploitable,
  la vidéo disparaîtra comme auparavant.
- Les fichiers renommés en une autre extension que MKV/MP4 ne sont pas repris.
- Une vidéo déplacée dans un autre dossier n'est pas recherchée automatiquement.
- La synchronisation reste suspendue pendant une conversion.
- Les dossiers surveillés continuent de détecter les nouvelles vidéos.

Tests recommandés :
1. Déposer une vidéo seule, la renommer dans le même dossier ; vérifier le nom.
2. Glisser une vidéo d'un sous-dossier, puis la renommer ; elle reste visible.
3. Supprimer une vidéo importée : elle disparaît (pas de remplacement aléatoire).
4. Importer un dossier, puis renommer l'une de ses vidéos : elle reste importée.
5. Vérifier les chemins Destination et la conversion après renommage.
6. Vérifier que les conversions parallèles, les presets et les statistiques restent OK.

Tests automatisés : python -m unittest test_rename_tracking -v

Aucune modification directe de GitHub.
