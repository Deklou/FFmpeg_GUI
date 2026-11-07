# FFmpeg GUI — V0.7 : synchronisation dynamique

Cette version se base sur le dépôt `Deklou/FFmpeg_GUI`, V0.6.1 validée.
Elle n'apporte **aucune modification au dépôt GitHub**.

## Installation

1. Fermer FFmpeg GUI.
2. Copier **`main.py`** et le nouveau **`interface_v07.py`** à la racine du projet `FFmpeg_GUI`.
3. Remplacer le `main.py` existant. **Conserver tous les autres fichiers**, notamment `interface.py`, `converter.py`, `output_planning.py`, etc.
4. Lancer `python main.py`.

L'interface V0.7 étend l'interface existante : c'est volontaire, afin de limiter les risques de régression.

## Comportement

- **Ajouter un dossier** : mémorise le dossier sélectionné pour cette session. Son contenu est rescanné toutes les **3 secondes** lorsque le logiciel ne convertit pas.
- **Inclure les sous-dossiers** : synchronise immédiatement la liste des vidéos des dossiers importés en fonction de la case.
- **Conserver l'arborescence en sortie** : actualise immédiatement la colonne **Destination** sans réimporter les vidéos.
- **Changer le format MKV/MP4** ou **changer le dossier de sortie** actualise également les destinations.
- **Actualiser** : force un scan immédiatement.
- Les vidéos importées avec **Ajouter des vidéos** restent présentes même si les sous-dossiers sont décochés.
- Les vidéos **retirées manuellement** restent écartées tant que leur fichier est présent. Pour les réintégrer, réimporter le dossier ou sélectionner la vidéo manuellement.
- **Tout vider** supprime aussi les dossiers surveillés pour la session ; l'application ne garde pas les dossiers importés après redémarrage.
- Pendant une conversion, la file et les options restent figées. Une synchronisation reprend lorsque la conversion s'achève.
- Les sorties produites pendant cette session sont ignorées par la synchronisation automatique pour éviter qu'elles deviennent de nouvelles sources.

La synchronisation est basée sur des vérifications périodiques : sur un dossier gigantesque ou un partage lent, la recherche récursive peut prendre un peu de temps. La V0.7 ne surveille pas les changements survenus pendant la fermeture de l'application ; les dossiers sont réimportés manuellement au démarrage suivant.

## Scénarios de validation Windows

1. Importer `Desktop/test` sans récursivité : seulement les vidéos directement dans `test`.
2. Cocher **Inclure les sous-dossiers** : les vidéos de `test/sub` arrivent sans réimport.
3. Décocher : les vidéos propres aux sous-dossiers disparaissent, sauf celles choisies à la main.
4. Ajouter un `.mp4` dans `test` avec l'Explorateur : il apparaît sous quelques secondes.
5. Renommer puis supprimer ce `.mp4` : l'ancien nom disparaît et le nouveau apparaît, puis disparaît.
6. Cocher/décocher **Conserver l'arborescence** : la colonne Destination change immédiatement, sans modifier la liste des sources.
7. Changer la sortie et le conteneur MKV/MP4 : les chemins Destination s'actualisent.
8. Importer deux vidéos de même nom dans deux sous-dossiers, désactiver la conservation d'arborescence : les destinations sont différentes.
9. Lancer une conversion : les changements du dossier source ne doivent pas altérer la file en cours, le suivi de progression et les statistiques doivent rester fonctionnels.
10. Terminer ou annuler puis vérifier la reprise de l'actualisation et l'absence de réimportation des propres sorties.

## Remarque technique

Le nouveau `main.py` importe `FFmpegGUI` depuis `interface_v07` plutôt que `interface`. Cela laisse `interface.py` de la version précédente intact.
