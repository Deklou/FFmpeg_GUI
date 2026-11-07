FFmpeg GUI V0.6 - Sous-dossiers et sécurité des destinations
==========================================================

INSTALLATION
Fermez l'application. Dans votre dossier FFmpeg_GUI, remplacez :
  - interface.py
  - converter.py
Ajoutez :
  - output_planning.py

Conservez tous vos autres fichiers (main.py, presets.py,
conversion_settings.py, conversion_time.py, compression_stats.py, etc.).

Puis lancez : python main.py

NOUVEAUTÉS
- « Inclure les sous-dossiers » : décoché par défaut, prend effet lors de
  l'import d'un dossier. Les vidéos déjà importées ne changent pas.
- « Conserver l'arborescence en sortie » : coché par défaut. Exemple :
    Entrée/Série A/épisode.mp4 -> Sortie/Série A/épisode.mkv
- Option décochée : toutes les vidéos sont placées à la racine du dossier
  de sortie. En cas de noms identiques, suffixe stable __<empreinte>.
- Fichiers ajoutés individuellement : dans la racine de sortie, sauf s'ils
  ont également été reconnus lors de l'import d'un dossier.
- Les dossiers de sortie situés dans le dossier importé ne sont pas réimportés.
- Les destinations sont calculées avant le lot et ne peuvent pas correspondre
  à l'un des fichiers sources du lot. Les fichiers existants sont ignorés,
  jamais écrasés volontairement.
- Passez la souris sur le nom de la vidéo pour connaître la destination
  prévue une fois que le lot a été lancé.

ATTENTION
Les sorties déjà présentes restent ignorées sans validation de leur codec.
Si les options « Conserver l'arborescence » et « Inclure les sous-dossiers »
sont indépendantes. Changer la conservation avant le prochain lot modifie
les destinations calculées ; ne supprime pas les fichiers déjà créés.

TESTS SUGGÉRÉS
1) Importer un dossier avec et sans recherche récursive.
2) Garder l'arborescence et lancer un encodage : vérifier les sous-dossiers.
3) Décocher la conservation de l'arborescence : tester 2 épisodes homonymes.
4) Relancer le lot : vérifier que les sorties existantes sont ignorées.
5) Vérifier qu'on ne peut pas convertir un fichier sur lui-même.
6) Vérifier progression, temps restant, réduction et presets.

TEST AUTOMATIQUE FACULTATIF
python -m unittest test_output_planning -v

Aucun changement n'a été envoyé à GitHub : seuls les fichiers de
cette archive sont fournis, à intégrer et committer par vos soins.
