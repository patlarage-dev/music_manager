# Architecture connectée

React/TypeScript (Vite), Nginx en lecture seule, backend FastAPI/Mutagen/Pillow, SQLite dans le volume privé `state/`. Le navigateur passe par `/api` sur la même origine. Aucun endpoint de commande shell ou d’accès Docker.

## Indexation

Un seul travailleur effectue une analyse progressive, sans suivre de liens symboliques. Les empreintes SHA-256 sont recalculées uniquement si taille ou mtime changent. L’ancien index reste disponible pendant la lecture ; le remplacement SQLite est transactionnel. Les pochettes intégrées ou fichiers cover/folder sont réduits à 600 px et mis en cache. Formats pris en charge selon Mutagen. Les dossiers cachés, dont la corbeille applicative, sont exclus.

Albums groupés par espace, dossier, artiste d’album et titre. Les identifiants sont dérivés de ces valeurs ; une modification du chemin peut changer l’identifiant. Les éditions MusicBrainz associées à l’ancien chemin peuvent alors devoir être choisies à nouveau. Les éditions de tags effectuées dans l’application conservent une identité stable par piste pour préserver la référence choisie.

## Fichiers réels

Racines vérifiées : `/mnt/media/music`, `/mnt/media/incoming`, `/mnt/media/quarantine`. L’UID 1000 correspond au propriétaire patrick sur ce serveur. Le montage commun évite les copies/suppressions non atomiques entre bind mounts. Le backend n’expose que ces racines, refuse traversées, liens symboliques, dossiers partagés ou contenant d’autres albums, collisions et plans expirés.

Une opération doit être prévisualisée ; la liste des fichiers, tailles et mtime est revérifiée avant exécution. Sous Linux, renameat2 avec RENAME_NOREPLACE garantit de ne pas remplacer une destination apparue entre deux contrôles. Chaque transfert est journalisé avant renommage ; la reprise vérifie les chemins présents. Les lots tentent de revenir sur les éléments déjà déplacés en cas d’échec. Un problème de disque pendant cette compensation peut nécessiter un contrôle dans l’historique.

La corbeille est `/mnt/media/quarantine/.music-manager-trash`. Aucun nettoyage automatique. Les restaurations refusent les collisions et nouveaux liens symboliques.

Les éditions de tags préparent les nouveaux fichiers dans des copies, conservent les originaux et les empreintes avant/après, puis remplacent chaque fichier atomiquement. Une interruption détectée au démarrage restaure les versions connues depuis les sauvegardes. Si un tiers a modifié les fichiers, la restauration automatique est refusée, l’opération reste signalée « contrôle requis » et les copies sont conservées. Un ensemble d’albums n’est pas une transaction de système de fichiers globale : le journal sert à terminer ou reprendre proprement chaque cas.

## Authentification et réseau

Lecture limitée par le tailnet Tailscale. Les requêtes de mutation nécessitent un en-tête applicatif et une origine cohérente (aucun CORS ouvert). Les écritures musicales exigent une session issue d’un compte administrateur Navidrome. Cookie HttpOnly, SameSite Strict, expiration de sept jours. Le rôle est celui obtenu à la connexion ; reconnecter le navigateur après un changement de permissions Navidrome. Le service stocke des identifiants Subsonic équivalents à un secret dans SQLite, jamais le mot de passe en clair. `state/` doit rester mode 700, la base mode 600, et hors Git et des archives de release.

Le backend rejoint le réseau Docker `music_backend` déjà utilisé par Navidrome et l’interroge à `http://navidrome:4533`. Le port hôte expose seulement Nginx sur l’IP Tailscale. Pas de modification de la configuration Navidrome/Deemix, ni d’écriture directe dans leur base.

## API musicales

OpenSubsonic pour ping, getUser, recherche d’artistes, artistes similaires, catalogue et playlists. Navidrome peut exposer un chemin virtuel différent du nom physique. Les métadonnées réduisent les candidats et les empreintes SHA-256 des fichiers originaux téléchargés via son API valident le rapprochement avant envoi. Ces correspondances sont mises en cache sept jours. Une piste absente ou différente fait échouer l’opération, sans substitution par un titre similaire. Le premier envoi peut donc lire les fichiers côté serveur et demander le droit de téléchargement au compte.

MusicBrainz est interrogé à la demande, avec User-Agent, limite d’un appel par 1,1 seconde et cache sept jours. L’utilisateur choisit explicitement l’édition. Les numéros de disque et de piste déterminent les manquants. Les tags seuls restent une indication, pas une preuve d’édition.

Sources : [API MusicBrainz](https://musicbrainz.org/doc/MusicBrainz_API), [limites](https://musicbrainz.org/doc/MusicBrainz_API/Rate_Limiting), [création de playlists OpenSubsonic](https://opensubsonic.netlify.app/docs/endpoints/createplaylist/).

## Validation

Tests backend sur fichiers temporaires : indexation WAV, Range audio, chemins, liens symboliques, authentification, CSRF, collisions, source changée, transferts/restaurations, rejeu de plans, exclusions de corbeille, doublons, radio locale, identifiants par session, tags FLAC aller-retour, récupération d’interruption et protection des modifications externes. Construction TypeScript/Vite et contrôles de configuration Nginx/Compose. Inspection visuelle ordinateur et viewport mobile ; les gestes Safari sur un iPhone physique nécessitent une vérification sur l’appareil.
