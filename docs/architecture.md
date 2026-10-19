# Architecture et progression

## Première itération

React + TypeScript, assemblage Vite, un conteneur Nginx sans privilèges. Les données sont dans src/data.ts, les écrans et interactions dans src/main.tsx, les tokens et adaptations dans src/style.css. Le navigateur n’accède pas au système de fichiers. Cette version permet de valider l’ergonomie sans ajouter de charge d’indexation au Mac mini 2012.

## Connexion aux données, phase suivante

Ajouter FastAPI, Mutagen et SQLite dans un service séparé, avec analyse progressive et file de tâches limitée à un travailleur. Tables envisagées : artistes, albums, éditions, pistes, fichiers, analyses, opérations et éléments de corbeille. Pagination et cache serveur des réponses publiques. Les clés Last.fm et Navidrome restent côté backend.

Commencer par des volumes en lecture seule pour incoming, music et quarantine. Vérifier les montages et UID/GID réels avant toute connexion. Autoriser ensuite les écritures dans un service dédié avec liste de racines autorisées, refus des liens symboliques, vérification des collisions, journal durable et reprise après interruption. Prévisualiser les opérations avant application ; tester la restauration avant d’activer une purge à 30 jours.

## Contraintes à résoudre

- Une extension FLAC ou un débit élevé ne prouve pas une meilleure source. Ne pas supprimer automatiquement une version sur ces seuls critères.
- MusicBrainz compare une édition précise, avec disques et bonus ; pas seulement le nom d’album. Une identification incertaine doit rester explicite.
- Recommandations, droits d’accès et limites API doivent être vérifiés lors de chaque intégration. Aucun fournisseur connecté dans ce prototype.
- La radio exige des identifiants de pistes réellement présentes ; la création de playlists Navidrome dépend d’un compte et de son API.
- Tailscale limite l’accès réseau mais ne remplace pas l’authentification applicative pour les futures opérations d’écriture.
- HTTPS est requis pour une installation PWA complète et les services workers. Préférer Tailscale Serve après inspection de la configuration existante.

## Validation manuelle

Sur ordinateur et téléphone : ouvrir les neuf sections, rechercher un artiste, filtrer un genre, ouvrir et fermer une fiche, sélectionner un album dans l’explorateur, le mettre à la corbeille puis le restaurer, suivre un artiste, générer et exporter une sélection. Vérifier clavier, focus, absence de débordement et message de démonstration. Aucun audio ne doit être présenté comme réellement écoutable.
