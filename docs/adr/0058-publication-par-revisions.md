# ADR 0058 — Publication par révisions du catalogue

- **Statut** : Proposée
- **Date** : 2026-10-25
- **Décideurs** : équipe Reco (éditeur)
- **Liens** : ADR 0055 (modèle canonique) ; ADR 0059 (approbation) ; ADR 0060
  (autorité éditoriale) ; amendera ADR 0021 (sitemap, cartes OG), ADR 0035
  (index de recherche), ADR 0050 (cartes à la demande) et ADR 0053
  (redirections) ; [`docs/v2/README.md`](../v2/README.md)
- **Note** : le numéro 0057 est réservé par un brouillon tenu hors du dépôt.

## Contexte

Publier une correction passe aujourd'hui par une PR, la CI, puis une
construction complète chez l'hébergeur. Corriger une faute de frappe coûte un
rebuild, et un build raté laisse le site hors ligne.

## Décision

- **Une révision immuable.** venus construit le catalogue public sous forme de
  segments adressés par leur empreinte (SHA-256), décrits par un manifeste. Le
  JSON est canonique (RFC 8785) : la même entrée donne toujours le même
  identifiant de révision. Venus signe la révision (Ed25519).
- **L'envoi** est vérifié par le site avant toute écriture : signature,
  empreinte du corps contrôlée avant décompression, plafonds absolus de taille
  et de profondeur. Un segment existant est re-haché ; un écart part en
  quarantaine.
- **L'activation** n'a lieu qu'après une approbation humaine (ADR 0059). Elle
  porte l'état attendu (époque, numéro de transition, révision active) : une
  enveloppe rejouée est refusée. Deux activations concurrentes ne peuvent pas
  réussir toutes les deux : chaque transition est créée de façon exclusive, la
  seconde reçoit 409. Une panne au milieu se rattrape en avant.
- **Lecture.** Chaque requête lit un seul instantané du catalogue : jamais de
  réponse mélangeant deux révisions. Les ressources dérivées (recherche,
  cartes) portent l'identifiant de la révision et du build ; l'ETag aussi.
- **Repli.** Sans révision active, le site sert le catalogue embarqué au build.
  Une commande de restauration, distincte de l'activation, ne s'applique qu'à
  un magasin vide ou corrompu, et seulement vers la dernière révision
  approuvée et confirmée. Après une restauration de venus, elle reste bloquée
  jusqu'à une décision humaine.
- **Mise en service par étapes** : quelques publications en mode révision
  (phase 8a), puis le mode révision par défaut (8b), après une liste de
  contrôle entièrement verte.
- **Preuves préalables.** Avant toute activation en production, des sondes
  mesurent chez l'hébergeur ce que le protocole suppose : création exclusive
  atomique, lecture complète d'un gros envoi, persistance des données hors du
  dossier du site, modèle de processus. Un résultat négatif impose le repli
  prévu, documenté avant PR-07.

## Conséquences

- Positives : une correction approuvée passe en ligne sans rebuild ; revenir
  en arrière revient à activer une révision précédente ; un build raté ne peut
  plus couper le site pour une correction de données.
- Négatives : un composant de plus sur le site (ingestion, magasin, lecteur),
  et un protocole à tester sous concurrence et en cas de panne.
- Notes : les plafonds, les durées de conservation des journaux et la
  restauration automatique restent à confirmer (DV-05 à DV-07). La perte
  maximale de 24 h des données de venus est acceptée (ADR 0060).
