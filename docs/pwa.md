# Installer Music Manager

Adresse HTTPS privée prévue : https://macmini-server.tail9ed71f.ts.net:9444/ (Tailscale actif).

## iPhone et iPad

Ouvrir cette adresse dans Safari, utiliser le partage puis « Sur l’écran d’accueil ». Choisir « Ouvrir comme app » si Safari le propose. Le nom et l’icône disque sont fournis par le manifeste et l’icône Apple de 180 px.

## Android et ordinateur

Ouvrir l’adresse HTTPS dans un navigateur compatible, puis choisir « Installer l’application » dans son menu. Une commande est également affichée dans Paramètres lorsque le navigateur fournit sa proposition d’installation.

L’origine HTTPS est distincte de l’ancienne adresse HTTP : reconnecter le compte Navidrome dans Paramètres sur cette nouvelle origine pour les opérations authentifiées.

## Mode hors ligne et mises à jour

Le service worker met uniquement les ressources statiques de l’interface, le manifeste et les icônes en cache. Les réponses API, sessions, pochettes provenant de l’API et fichiers audio ne sont jamais mis en cache par ce worker. Une ouverture hors ligne affiche une page de reconnexion : activer Tailscale et vérifier la connexion avant de réessayer.

Le cache est versionné par les fichiers produits au build et les anciennes versions sont supprimées lors de l’activation. Une mise à jour en attente peut être appliquée dans Paramètres ou lors de la prochaine ouverture après fermeture des anciennes fenêtres. Le manifeste et le script du worker sont servis sans cache HTTP durable.

## HTTPS serveur

Sur Debian, commande administrateur à exécuter une fois :

```sh
sudo tailscale serve --bg --https=9444 http://100.120.247.35:8095
```

Cette route privée s’ajoute aux services sur 443 et 8443 sans les remplacer ; ne pas utiliser Funnel. La disponibilité se vérifie avec `tailscale serve status`, puis `/api/health` sur la nouvelle adresse HTTPS.

Le disque est le même symbole Lucide Disc3 que celui du titre, en pêche sur fond ardoise. Les PNG 192/512 px, variante maskable et icône Apple 180 px sont générés à partir du SVG. La licence du dessin est conservée dans public/icons/NOTICE.txt.
