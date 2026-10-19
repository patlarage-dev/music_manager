# Music Manager

Application personnelle en français, connectée aux fichiers du serveur Debian et à l’API OpenSubsonic de Navidrome.

[Ouvrir l’application via Tailscale en HTTPS](https://macmini-server.tail9ed71f.ts.net:9444/).

## Version 0.2

Navigation mobile en bas de l’écran : Accueil, Albums, Explorateur et Plus. Navigation latérale conservée sur ordinateur. Les neuf sections affichent les données réelles ; aucun repli silencieux sur des données fictives.

- Indexation incrémentale en arrière-plan : tags, formats, durée, pochettes intégrées et fichiers cover/folder.
- Explorateur des dossiers music, incoming (Deemix) et quarantine ; préécoute audio avec prise en charge des requêtes Range.
- Recherche, filtres de genre/format/état et pagination des albums. Dans l’explorateur, les actions de sélection sont disponibles avant et après la liste, et restent visibles en bas lorsqu’une sélection existe. La sélection est conservée entre les filtres/pages (20 albums maximum par opération).
- Complétude d’après les totaux des tags et comparaison d’une édition MusicBrainz choisie explicitement.
- Doublons par SHA-256 et versions portant le même artiste/titre à comparer, sans suppression automatique.
- Radio locale à partir de l’artiste et des genres présents, export M3U et création de playlist Navidrome.
- Suggestions similaires via Navidrome et, à défaut, artistes locaux partageant un genre. Suivis persistants.
- Déplacement, renommage et corbeille d’albums après prévisualisation ; historique et restauration sans écrasement.
- Édition des tags d’album (artiste de l’album, nom, année, genre), copie complète avant écriture et restauration.

## Connecter son compte

Dans **Paramètres → Connexion Navidrome**, saisir son compte Navidrome actuel. Aucun mot de passe à transmettre au développeur. Le mot de passe sert à produire les identifiants Subsonic ; seuls le nom et le couple sel/empreinte sont conservés dans le volume privé `state/`. Ce couple reste un secret équivalent à des identifiants. Les opérations Navidrome utilisent les identifiants de la session concernée. Les éditions de fichiers exigent un rôle administrateur Navidrome et une confirmation à l’écran.

Amperfy utilise les playlists du même serveur Navidrome. Il faut rafraîchir sa bibliothèque/playlists après création.

## Développement local

```sh
npm ci
npm run dev
```

Le serveur Vite relaie `/api` vers `127.0.0.1:8000`. Dans un environnement Python 3.13 :

```sh
python -m venv .venv
.venv/bin/pip install -r backend/requirements.txt pytest
STATE_DIR=/tmp/music-manager-state MEDIA_ROOT=/chemin/vers/des/fichiers-de-test .venv/bin/uvicorn backend.app:app --host 127.0.0.1 --port 8000
```

Ne pas utiliser une bibliothèque de production comme fixture de test. `npm run build`, `npm test`, puis `python -m pytest backend/tests -q`. Les tests Python utilisent exclusivement des répertoires temporaires. Le Dockerfile backend comporte une cible `test` pour exécuter ces contrôles sous Linux.

## Déploiement et limites

[Procédure et retour arrière](docs/deploiement.md) · [Architecture](docs/architecture.md).

Accès privé Tailscale ; pas de publication Internet. Aucun socket Docker monté. Le backend tourne avec UID 1000 et ne publie aucun port hôte. Le montage parent `/mnt/media` permet des renommages atomiques ; les opérations applicatives sont strictement limitées aux trois racines configurées. Pas de purge définitive ni automatique. Les sauvegardes de tags occupent de l’espace jusqu’à une gestion de rétention ultérieure.

Pas d’empreinte acoustique ni de classement automatique de qualité. La radio utilise les tags, pas une analyse acoustique d’ambiance. Pas d’historique d’écoute transmis. Les intégrations Last.fm et ListenBrainz directes et le téléchargement automatique ne sont pas activés. Les pistes manquantes ne sont fiables que pour l’édition et les numéros de disque/piste identifiés. Les codecs de préécoute dépendent du navigateur ; Navidrome reste le lecteur principal. L’installation PWA est décrite dans [la procédure dédiée](docs/pwa.md). La musique n’est pas conservée pour une écoute hors ligne.

## Installer l’application

Le manifeste, les icônes disque pour iOS/Android et le service worker sont inclus. Utiliser l’adresse HTTPS Tailscale et suivre [la procédure PWA](docs/pwa.md). Une page de reconnexion est disponible hors ligne, sans cache des données privées ni de la musique.
