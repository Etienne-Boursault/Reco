# ADR 0060 — Autorité éditoriale et sauvegardes

- **Statut** : Proposée (la sauvegarde est décidée ; l'écrivain unique reste à
  confirmer)
- **Date** : 2026-10-25
- **Décideurs** : équipe Reco (éditeur)
- **Liens** : ADR 0058 (publication par révisions) ; ADR 0056 (registre des
  identifiants) ; ADR 0055 (modèle canonique)

## Contexte

Le corpus est écrit aujourd'hui à plusieurs endroits : la chaîne de venus
commite et pousse, et des PR de contenu partent du poste de l'éditeur. Git
sert à la fois de stockage, de canal de publication et de sauvegarde.

## Décision

- **Décidé le 24/10.** Les données éditoriales sont sauvegardées depuis venus,
  chaque nuit, vers un stockage chiffré hors site (Proton Drive). Une perte de
  24 h au plus est acceptée. Git ne sert plus d'archive des données.
- **Proposé, à confirmer avant la bascule (Q1, D-13, DV-10, DV-11) :**
  - venus devient le seul écrivain du corpus, dans un répertoire hors du clone
    Git ; les maintenances se font sur venus ;
  - les PR de contenu sont gelées au lancement de la bascule, après
    vérification des branches ouvertes ;
  - avant chaque sauvegarde, un instantané cohérent est pris sous les verrous de
    la chaîne, ce qui arrête la relecture quelques secondes ; un manifeste
    d'empreintes accompagne la copie ;
  - des PR `donnees-sync`, manuelles et exceptionnelles, rafraîchissent le
    catalogue embarqué de `main` après un jalon stable.
- **Restauration exercée** avant la bascule : une copie récupérée depuis le
  stockage hors site est vérifiée par son manifeste d'empreintes et par
  l'identifiant de révision qu'elle contient.

## Conséquences

- Positives : une seule autorité sur les données ; Git redevient un dépôt de
  code ; la sauvegarde est vérifiable.
- Négatives : tout dépend de venus ; une panne de venus suspend les
  publications, pas le site, qui continue de servir la dernière révision.
- Notes : la durée réelle de l'arrêt de la relecture n'est pas mesurée ; elle
  sera relevée à la répétition.
