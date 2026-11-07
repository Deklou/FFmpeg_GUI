# FFmpeg GUI V0.9 — conversions simultanées

Cette version ajoute un sélecteur **Conversions simultanées : 1 à 4**, dans la barre d'actions de conversion.

## Installation sur la V0.8.1

1. Fermer l'application.
2. **Remplacer** `main.py`.
3. **Ajouter** `interface_v09.py` et `parallel_converter.py` à la racine du projet.
4. Conserver `interface.py`, `interface_v07.py`, `interface_v08.py`, `converter.py` et tous les modules existants.
5. Lancer `python main.py`.

Aucune modification de ton dépôt GitHub n'est effectuée automatiquement.

## Comportement

- **1 conversion (défaut)** : worker FFmpeg historique, ETA par fichier et pour le lot conservés.
- **2 à 4 conversions** : plusieurs processus FFmpeg indépendants, chacun avec sa progression, son temps écoulé, son ETA et sa vitesse.
- **ETA globale parallèle** : affichée comme indisponible ; additionner les ETA des encodages parallèles serait trompeur. L'ETA par vidéo reste disponible.
- **Annuler** : demande l'arrêt de tous les encodages actifs, ne lance plus les fichiers en attente. Les fichiers déjà terminés sont conservés ; les `.part` incomplets sont supprimés par le moteur historique.
- **Fichiers existants** : ignorés comme auparavant.
- **Paramètre mémorisé** : le nombre de conversions simultanées est sauvegardé via QSettings.

Attention : encodage CPU H.265 très coûteux. Deux travaux en parallèle ne seront pas forcément plus rapides qu'un seul.

## Tests Windows conseillés

1. Lancer trois petites vidéos avec `1` : mêmes résultats qu'en V0.8.1.
2. Régler `2` et lancer trois vidéos : deux démarrent avant la troisième.
3. Vérifier que chaque ligne a sa propre progression, vitesse, temps et taille de sortie.
4. Vérifier que la troisième démarre quand une des deux premières se termine.
5. Tester `3`, puis `4`, avec plusieurs courtes vidéos.
6. Tester **Annuler** pendant deux conversions : plus aucun encodage ne reste actif ; sorties terminées intactes.
7. Relancer le lot : déjà converti ignoré ; fichiers annulés retraités.
8. Fermer et rouvrir l'application : le choix du parallélisme doit être conservé.
9. Vérifier les sous-dossiers, la synchronisation, les presets et le panneau avancé.

Test de logique du répartiteur sans Qt : `python -m unittest -v test_parallel_controller.py`.

## Modifications

- `main.py` (remplacé)
- `interface_v09.py` (nouveau)
- `parallel_converter.py` (nouveau)
- `test_parallel_controller.py` (test facultatif)
- `README_V0_9.md` (ce guide)

Aucun changement aux paramètres d'encodage, à la structure des fichiers de sortie ou au code du moteur historique `converter.py`.
