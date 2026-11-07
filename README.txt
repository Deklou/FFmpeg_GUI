FFmpeg GUI V0.8.1 - Correctif redimensionnement

INSTALLATION
1. Fermer l'application.
2. Copier interface_v08.py dans le dossier FFmpeg_GUI et remplacer l'ancien.
3. Ne toucher à aucun autre fichier.
4. Relancer : python main.py

MODIFICATIONS
- Hauteur minimale du tableau passée de 240 à 80 pixels.
- Fenêtre redimensionnable jusqu'à 620 x 340 pixels ; une barre de défilement
  verticale permet d'accéder aux contrôles quand l'espace est insuffisant.
- La hauteur de la fenêtre est mémorisée à l'ouverture des paramètres avancés
  et rétablie lorsqu'on les referme.

TESTS CONSEILLES
1. Réduire la hauteur de la fenêtre : le tableau doit pouvoir se contracter.
2. Réduire davantage : les contrôles doivent rester accessibles en défilant.
3. Ouvrir les réglages avancés, puis les refermer : retrouver la hauteur initiale.
4. Réessayer après avoir agrandi/réduit manuellement la fenêtre.
5. Importer et convertir une petite vidéo : vérifier que le flux fonctionne encore.

Ce correctif ne modifie ni le moteur FFmpeg ni le dépôt GitHub.
