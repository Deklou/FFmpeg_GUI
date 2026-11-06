FFmpeg GUI V0.5 — Suivi temporel et pourcentages sans +
=====================================================

Installation dans ton dossier FFmpeg_GUI existant :
- Remplacer interface.py et converter.py
- Ajouter conversion_time.py
- Optionnel : ajouter test_conversion_time.py
- Conserver main.py, conversion_settings.py, compression_stats.py,
  presets.py, requirements.txt et tes presets existants.

Démarrer avec : python main.py

Nouveautés :
- Pourcentage de réduction sans signe + devant les valeurs positives.
- Trois colonnes : Temps écoulé, Restant estimé, Vitesse (x).
- Sous la progression globale : temps écoulé du lot et ETA du lot.
- Le temps écoulé reste disponible même si FFprobe ne peut pas lire la durée.
- L'ETA reste « — » si la durée ou la vitesse est indisponible.
- Le temps restant du lot est une estimation basée sur la vitesse du
  fichier actuel extrapolée aux durées des fichiers suivants. Elle peut
  varier fortement d'une vidéo à l'autre.
- Analyse préliminaire des durées en arrière-plan (FFprobe) avant
  l'encodage ; pour un grand lot, le démarrage peut prendre quelques instants.

Tests conseillés :
1. Sur une vidéo, constater le temps écoulé, la vitesse et l'ETA.
2. Avec plusieurs vidéos, constater le temps total du lot et son ETA.
3. Vérifier un fichier déjà converti : il doit rester ignoré.
4. Vérifier qu'une réduction positive affiche « 42,5 % » et non « +42,5 % ».
5. Vérifier l'annulation et les presets habituels.

Test automatisé facultatif : python -m unittest -v test_conversion_time.py

Ce correctif ne modifie pas les commandes FFmpeg ni les presets.
Le dépôt GitHub n'a pas été modifié.
