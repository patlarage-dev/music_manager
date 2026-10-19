---
name: Music Manager
description: Une discothèque personnelle lisible et calme
colors:
  background: "#141c26"
  surface: "#19232f"
  raised: "#263645"
  text: "#f4f5f7"
  muted: "#b1bdcb"
  accent: "#ffc49e"
typography:
  body:
    fontFamily: "Manrope, Trebuchet MS, sans-serif"
    fontSize: "14px"
    fontWeight: 400
  heading:
    fontFamily: "Manrope, Trebuchet MS, sans-serif"
    fontSize: "34px"
    fontWeight: 800
    lineHeight: 1.2
    letterSpacing: "-1px"
rounded:
  control: "8px"
  panel: "14px"
spacing:
  sm: "8px"
  md: "16px"
  lg: "24px"
  xl: "32px"
components:
  button-primary:
    backgroundColor: "{colors.accent}"
    textColor: "#30251f"
    rounded: "{rounded.control}"
    padding: "11px 16px"
---
# Design System: Music Manager

## Overview
Une discothèque personnelle calme. Les pochettes graphiques illustratives donnent son identité à la collection ; les opérations restent lisibles en listes compactes. Mode Operate, interface française sombre pour consultation sur Mac et téléphone.

## Colors
La pêche porte les actions principales ; l’ardoise distingue les espaces de travail. Le texte secondaire reste clair sur les surfaces sombres.

## Typography
Manrope est la famille réalisée, avec Trebuchet MS en repli. Titres de section à 20 px ; titre principal à 34 px sur grand écran et 29 px sur téléphone. La revue future doit surveiller les petits textes de statut (9 à 11 px), qui ne constituent pas une norme de confort à étendre.

## Layout
Navigation fixe à gauche, contenu limité à 1510 px. La grille passe de cinq à trois, puis deux albums. À 650 px, navigation dans un volet, accessible par le bouton du bandeau fixe. Les tableaux peuvent défiler horizontalement. Aucun résultat filtré ne doit être caché par le responsive.

## Elevation & Depth
Les différences de ton séparent les espaces ; les ombres servent les pochettes superposées, la notification et le volet mobile.

## Shapes
Commandes arrondies, pochettes carrées, panneaux modérément arrondis. Géométrie abstraite pour les visuels de démonstration.

## Components
Icônes Lucide cohérentes. Commande pêche pour l’action principale, commandes neutres pour les choix secondaires. Focus visible pêche avec décalage de 4 px. Fiche album avec confinement du focus et fermeture par Échap ; notification annoncée par role status. Mouvement supprimé si l’utilisateur préfère réduire les animations.

## Do's and Don'ts
- Préserver le signalement des données de démonstration.
- Présenter les opérations de gestion en lignes lisibles.
- Ne pas faire passer les illustrations pour des pochettes officielles.
- Ne pas masquer un résultat pour équilibrer la grille.

## Adaptation téléphone, version 0.2
La navigation latérale est remplacée sous 768 px par quatre accès persistants en bas : Accueil, Albums, Explorateur, Plus. Plus ouvre une feuille native modale contenant toutes les sections, avec fermeture visible, confinement natif du focus et Échap. Le choix courant reste signalé. Safe areas iOS prises en compte ; le contenu conserve une marge sous la barre. Les champs ont une taille de texte de 16 px et les actions tactiles une hauteur minimale de 44 px. Le menu desktop garde son identité.
Les pochettes viennent des fichiers réels ; une absence se montre par un disque neutre et le titre, sans inventer une illustration officielle. Les états vides, connexion indisponible et édition inconnue sont explicites.
