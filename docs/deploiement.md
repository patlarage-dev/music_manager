# Déploiement Debian

Cible : `patrick@100.120.247.35`, application dans `/home/patrick/apps/music-manager`, accès [Tailscale privé](http://100.120.247.35:8095/). Branche GitHub : `music_manager`.

## Installation

Docker et Compose doivent être disponibles, le réseau externe `music_backend` présent et le port 8095 libre. Les racines /mnt/media/music, incoming et quarantine doivent appartenir à l’UID 1000 avec des permissions appropriées. Ne pas effectuer de chown récursif sur les fichiers existants.

```sh
mkdir -p state
chmod 700 state
APP_VERSION=0.2.0 docker compose build
APP_VERSION=0.2.0 docker compose up -d
curl --fail http://100.120.247.35:8095/api/health
```

Le fichier `.env` de ce serveur contient `BIND_ADDRESS=100.120.247.35`, `APP_PORT=8095`, `APP_VERSION=0.2.0`. `state/` contient les index, sessions, secrets Subsonic, sauvegardes et journaux : ne jamais publier ce dossier dans Git ou une archive de release. Le sauvegarder séparément en privé. L’application n’est pas conçue pour être exposée publiquement sans authentification réseau et HTTPS.

La première connexion Navidrome s’effectue dans Paramètres avec le compte actuel. Aucune écriture dans les fichiers musicaux ne peut être faite sans session administrateur et confirmation d’un plan. Deemix alimente incoming ; Navidrome continue de lire music.

## Mise à jour

Construire et tester avant de remplacer les conteneurs. Conserver les anciennes images et les fichiers Compose. Ne pas inclure `state/` dans la release. Tester le backend isolément : `docker build --target test -t music-manager-api:test backend`.

Après mise à jour : vérifier `/api/status`, les compteurs réels, une pochette et une préécoute ; vérifier `docker compose ps`. Ne jamais tester la corbeille sur les albums personnels pour valider un déploiement : utiliser les tests isolés. Les empreintes de tous les fichiers de la bibliothèque ont été relevées avant intégration pour comparaison après démarrage.

## Retour arrière

L’interface v0.1 et sa configuration sont conservées dans `rollback-v01/`, l’image `music-manager:0.1.0` reste disponible. Pour revenir au prototype antérieur : arrêter uniquement le service backend de ce projet, rétablir les fichiers Compose/Nginx/Dockerfile de ce dossier de sauvegarde et lancer l’image 0.1.0 avec `--no-build`. Conserver `state/` et le journal de la v0.2 pour les éventuelles restaurations ; revenir à une version frontend seule ne restaure pas des fichiers déplacés ultérieurement.

## HTTPS

Les services Tailscale existants sur 443 et 8443 sont conservés. Un nouveau port HTTPS exige actuellement un mot de passe sudo. Ne pas remplacer ces routes et ne pas activer Funnel. L’accès actuel HTTP reste transporté dans le réseau Tailscale chiffré.

## Intégration Mini

Le service web conserve les labels `mini.name`, `mini.url`, `mini.icon` définis dans Compose, conformément à AGENTS.md. L’icône existante est `/icons/music-manager.svg`. Le backend ne reçoit aucun lien Mini. Vérifier ces labels avec docker inspect après un déploiement.
