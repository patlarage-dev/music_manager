# Music Manager

Interface française de gestion d’une collection personnelle. Première itération du cahier des charges : neuf écrans navigables, données de démonstration clairement indiquées. Aucun accès aux fichiers musicaux et aucune connexion aux services existants.

## Lancer localement

Node.js 22 recommandé.

```sh
npm ci
npm run dev
```

Ouvrir http://127.0.0.1:5173. Pour compiler : `npm run build`. Pour vérifier les invariants : `npm test`.

## Fonctionnalités disponibles

Tableau de bord, explorateur filtrable avec sélection, bibliothèque et fiches album, albums incomplets, comparaison de doublons, artistes suivis, génération d’une sélection illustrée, export M3U de démonstration, corbeille et restauration, historique de session, préférences simulées. La corbeille de démonstration est conservée dans le navigateur. Les autres choix restent en mémoire pour la session.

Les visuels sont des compositions graphiques originales illustratives, pas des pochettes officielles. Les nombres, formats et pistes sont fictifs. L’export M3U ne contient aucun chemin audio et ne permet pas la lecture.

## Déployer sur Debian

Voir [la procédure](docs/deploiement.md). Docker Compose expose uniquement une adresse choisie explicitement, sans volume musical, sans socket Docker et sans privilèges. Ne pas exposer ce prototype directement sur Internet.

## Suite du projet

Voir [l’architecture](docs/architecture.md). Les fonctions d’analyse réelle, écriture de tags, déplacement, doublons automatiques, API musicales, lecture et synchronisation Navidrome ne sont pas encore implémentées. Le manifeste prépare l’installation ; une PWA complète et son cache hors ligne restent à valider sur HTTPS et sur iOS.
