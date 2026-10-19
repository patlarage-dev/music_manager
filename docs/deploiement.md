# Mise en ligne Debian

Cible fournie : patrick@100.120.247.35 via Tailscale. Branche souhaitée : music_manager.

## Contrôles préalables

Connexion SSH autorisée et Docker Compose disponibles ; inspecter `docker ps` et `ss -ltn` pour vérifier que le port 8095 est libre. Ne pas modifier les services Deemix/Navidrome, les montages ou les permissions de la bibliothèque.

Copier le code dans un répertoire dédié, par exemple `~/apps/music-manager`, puis :

```sh
BIND_ADDRESS=100.120.247.35 APP_PORT=8095 APP_VERSION=0.1.0 docker compose up -d --build
curl --fail http://100.120.247.35:8095/health
docker compose ps
```

Adresse attendue après vérification : http://100.120.247.35:8095, accessible aux appareils autorisés du tailnet. Aucune publication Internet. Le conteneur ne monte aucun fichier musical.

Pour HTTPS, inspecter d’abord `tailscale serve status`, puis configurer un chemin ou port disponible sans remplacer une route existante. Ne pas activer Funnel.

## Retour arrière

Avant mise à jour, conserver le code et l’image actuellement déployés et noter la version. Pour revenir à une image existante :

```sh
APP_VERSION=VERSION_PRECEDENTE BIND_ADDRESS=100.120.247.35 docker compose up -d --no-build
```

Pour arrêter uniquement cette application : `docker compose down` dans son répertoire. Aucun volume musical n’est impliqué. La suppression de conteneur n’efface pas la corbeille simulée du navigateur.

## État

La procédure n’est pas une preuve de déploiement. Vérifier le point de santé et l’interface sur le serveur après exécution. Déployé le 19 octobre 2026 dans `/home/patrick/apps/music-manager`, image `music-manager:0.1.0`. Point de santé et interface vérifiés depuis le navigateur sur http://100.120.247.35:8095. Le déverrouillage de la clé dans l’agent SSH du Mac a permis l’accès. HTTPS Tailscale sur un nouveau port nécessitera une commande sudo ; aucune configuration Tailscale existante n’a été remplacée.
