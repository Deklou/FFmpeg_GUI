FFmpeg GUI — V0.4 : statistiques de compression

INSTALLATION
1. Fermer FFmpeg GUI.
2. Copier interface.py et converter.py dans le projet, en remplaçant les fichiers existants.
3. Ajouter compression_stats.py.
4. Optionnel : ajouter test_compression_stats.py.
5. Conserver tous les autres fichiers (main.py, conversion_settings.py, presets.py, etc.).
6. Relancer : python main.py

FONCTIONNEMENT
- Le poids total d'entrée est calculé dès l'importation des vidéos.
- Après une conversion réussie, la taille de sortie réelle et le pourcentage de réduction apparaissent pour la vidéo.
- Les fichiers "Déjà converti" affichent aussi leur taille réelle (fichier existant), même si leur encodage peut différer des paramètres actuels.
- Les autres vidéos affichent un tiret pour la taille de sortie et le pourcentage.
- La synthèse du lot affiche la taille totale d'entrée, la taille des sorties connues, l'espace gagné (ou supplémentaire) et la réduction globale calculée seulement sur les sorties connues.
- Une réduction négative indique une augmentation de la taille.
- Le bilan est remis à zéro à chaque nouvel export ; les fichiers sur disque ne sont pas supprimés.

TESTS RAPIDES
1. Importer trois vidéos : vérifier le poids d'entrée total et les tirets en sortie.
2. Convertir la première : vérifier taille sortie, réduction, et synthèse partielle.
3. Terminer le lot : vérifier le bilan global.
4. Relancer : les vidéos déjà présentes doivent être signalées et mesurées.
5. Vérifier les presets et l'annulation.

NOTE
Il n'existe pas d'estimation fiable du poids avant la fin d'un encodage CRF. Les chiffres affichés sont donc réels et non prédictifs.

Tests automatisés (sans PySide6 nécessaire pour les statistiques):
python -m unittest test_compression_stats -v
