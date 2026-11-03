# ADR 0062 — Orientation Community + Cloud

- **Statut** : Acceptée (2026-11-01), à la validation de la documentation ; acceptée sur le principe le 2026-10-25. L'orientation est décidée ; l'offre Cloud est conditionnelle
- **Date** : 2026-10-25
- **Décideurs** : équipe Reco (éditeur)
- **Liens** : [`vision-2026.md`](../vision-2026.md), décision 4 ; [`roadmap-2026.md`](../roadmap-2026.md) ; ADR 0039 (licence MIT) ; ADR 0045 (registre des sites) ; ADR 0058 (publication sans rebuild)

## Contexte

La vision fixait trois décisions structurelles, sans trancher la forme durable du projet au-delà du kit open-source. La conception de la V2 devait savoir si une offre hébergée était envisagée, pour ne rien bâtir qui l'empêche.

## Décision

- **L'orientation Community + Cloud est décidée** : le kit open-source pour les podcasts qui l'installent eux-mêmes, puis peut-être une offre hébergée.
- **Un podcast, un site.** Chaque podcast a son domaine, sa base, ses publications et ses clés. Les adresses existantes gardent leur préfixe de source (`/un-bon-moment/`), et aucun lien ne casse.
- **Le kit Community** installe l'atelier et le site, avec une base MySQL ou MariaDB (ADR 0058). Il fonctionne seul, sans compte ni service extérieur obligatoire.
- **L'offre Cloud est conditionnelle.** Avant tout engagement, une étude dira si un particulier peut la proposer ou s'il faut une structure : statut, obligations d'un hébergeur, coûts, temps. Rien n'est arbitré sur sa spécification, le multi-tenant ni le financement.
- **Aucune fondation de la V2 ne dépend du Cloud.** Le registre des sites (ADR 0045) reste en v1, sans champ nouveau.

## Conséquences

- **Positives** : la direction est écrite, et les choix de la V2 ne la ferment pas.
- **Négatives** : un hébergeur sans base MySQL ou MariaDB ne peut pas accueillir le kit en mode dynamique ; le mode statique reste possible.
- **Notes** :
  - les refus de `roadmap-2026.md` (comptes utilisateurs, multi-rôles) restent valables tant que l'offre Cloud n'est pas arbitrée ;
  - l'étude devra vérifier ce que les mentions légales exigent d'une offre professionnelle.
