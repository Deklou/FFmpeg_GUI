# FFmpeg GUI — V0.8 : refonte de l'interface

Cette version se superpose à la **V0.7 validée**. Aucun changement du moteur FFmpeg, de la synchronisation, des statistiques, des presets ou de l'organisation des fichiers.

## Installation

1. Fermer FFmpeg GUI.
2. Extraire l'archive dans le dossier du projet.
3. **Remplacer** `main.py`.
4. **Ajouter** `interface_v08.py`.
5. **Garder** `interface_v07.py`, `interface.py` et tous les autres fichiers en place.
6. Lancer `python main.py`.

## Changements

- Fichiers et dossiers : importation, entrée et sortie sur une seule ligne ; cases à cocher en dessous.
- Le chemin d'entrée et le chemin de sortie sont sélectionnables à la souris, sans encombrer la fenêtre par deux grands encarts.
- Presets et chemin FFmpeg restent visibles.
- Panneaux Vidéo / Pistes et format repliés par défaut derrière un bouton.
- Tableau des vidéos prioritaire dans la hauteur ; colonnes redimensionnables à la souris, avec défilement horizontal si nécessaire.

## Tests manuels

1. Lancer l'application. Vérifier l'affichage compact et l'absence d'erreur.
2. Importer un dossier : vérifier que son chemin apparaît dans le champ Entrée.
3. Choisir la sortie : vérifier que son chemin apparaît dans le champ Sortie.
4. Cocher / décocher Inclure les sous-dossiers : la liste doit se mettre à jour.
5. Cocher / décocher Conserver l'arborescence : la colonne Destination doit changer.
6. Déplier les réglages : modifier le codec ou le CRF, puis replier. Le résumé doit refléter le réglage choisi.
7. Tester un preset : il doit restaurer les réglages correspondants, même si les panneaux sont cachés.
8. Importer plusieurs vidéos : le tableau doit occuper la zone centrale, avec des colonnes redimensionnables et une barre de défilement horizontal si nécessaire.
9. Ajouter, supprimer ou renommer une vidéo dans un dossier surveillé ; constater la synchronisation.
10. Réaliser une conversion courte : progression, statistiques et destination doivent toujours fonctionner ; l'annulation reste disponible.

## Notes

- La refonte est une modification de présentation, pas une version avec de nouvelles options FFmpeg.
- Les panneaux avancés sont fermés au démarrage, y compris si un preset personnalisé a été sélectionné auparavant (celui-ci n'est pas effacé).
- Cette version a été vérifiée par compilation Python ; elle doit encore être validée sur Windows avec PySide6.
- Aucun fichier GitHub n'a été modifié.
