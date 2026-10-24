# ADR 0059 — Approbation humaine des publications

- **Statut** : Proposée
- **Date** : 2026-10-25
- **Décideurs** : équipe Reco (éditeur)
- **Liens** : ADR 0058 (publication par révisions) ; ADR 0052 (données de
  visiteurs) ; ADR 0054 (métriques, inchangé)

## Contexte

La publication par révisions (ADR 0058) supprime l'étape de la PR fusionnée à
la main, qui servait aussi de contrôle humain. Aucune révision ne doit passer
en ligne sans qu'un humain l'ait vue et approuvée.

## Décision

- **Pas d'activation sans approbation explicite.** L'écran « Publier », sur
  venus, montre la différence entre la révision proposée et la révision
  active : pages ajoutées, modifiées, retirées. L'éditeur approuve ou refuse.
  Une approbation ne sert qu'une fois et expire. Une commande en ligne de
  commande sert de secours.
- **Le cron construit et envoie, il n'active jamais.**
- **L'écran est authentifié**, distinct de la relecture. La méthode reste à
  choisir (Q5). Recommandation : un mot de passe haché par `scrypt`, et un
  cookie de session `HttpOnly`, `SameSite=Strict`, valable 8 h.
- **Registre des approbations et activations** : schéma fermé, sans
  identifiant de session, adresse IP, navigateur ni cookie. Les durées de
  conservation restent à confirmer (DV-06).
- **Risque accepté et écrit** (D-07, différé) : le site ne peut vérifier que la
  signature de la machine. Sans signature propre à l'éditeur, sur son appareil,
  une compromission complète de venus permet de publier. À réévaluer s'il y a
  un second opérateur, une offre Cloud, ou un incident sur venus.

## Conséquences

- Positives : chaque mise en ligne reste une décision humaine, tracée, sans
  donnée personnelle.
- Négatives : une étape de plus pour l'éditeur à chaque publication.
- Notes : l'écran doit être en service avant la première activation publique.
