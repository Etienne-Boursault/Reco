# ADR 0058 — Publication sans rebuild : une base chez l'hébergeur, alimentée ligne par ligne

- **Statut** : Acceptée (2026-11-01), à la validation de la documentation ; acceptée sur le principe le 2026-10-25
- **Date** : 2026-10-25
- **Décideurs** : équipe Reco (éditeur)
- **Liens** : ADR 0055 (modèle canonique) ; ADR 0059 (approbation) ; ADR 0060 (autorité éditoriale) ; ADR 0052 (vignettes servies localement) ; amende ADR 0021 (sitemap, cartes de partage), ADR 0035 (index de recherche), ADR 0050 (cartes à la demande) et ADR 0053 (redirections)
- **Note** : le numéro 0057 est réservé par un brouillon tenu hors du dépôt.

## Contexte

Aujourd'hui, publier une correction passe par une PR, la CI, puis une construction complète du site. Corriger une faute de frappe coûte un rebuild, et un build raté laisse le site hors ligne.

L'atelier (venus) fait déjà tout le calcul : extraction, relecture, liens. Le site a déjà un serveur Node, qui sert les pages. Il lui manque de quoi recevoir les données et les garder.

## Décision

- **venus calcule, le site range et sert.** Le site garde le catalogue public dans une base MySQL ou MariaDB, chez l'hébergeur. Les tables (œuvres, citations, épisodes, liens, sources, redirections) sont lisibles par l'éditeur. Chaque ligne porte aussi sa forme canonique complète, en JSON : tout ce qui change une page, y compris ce qui la rattache et l'ordonne, comme l'œuvre et le rang d'un lien. L'empreinte couvre donc aussi l'ordre des liens.
- **Une publication, c'est un lot** : les lignes ajoutées, modifiées ou retirées, envoyées en un seul bloc par une requête HTTPS POST. Le lot est scellé par Ed25519 (ADR 0059). Il déclare son point de départ (le numéro et l'empreinte de la publication en ligne) et l'empreinte attendue à l'arrivée.
- **Le site vérifie avant de lire** : le sceau, la fenêtre de temps, l'empreinte du corps (avant toute décompression), des plafonds absolus de taille, de profondeur et de nombre de lignes, et le point de départ.
- **Le site applique tout en une seule transaction.** Il recalcule l'empreinte du catalogue entier et ne valide que si elle égale l'empreinte attendue ; sinon, il annule. Deux publications parties du même état ne peuvent pas réussir toutes les deux : la seconde reçoit 409. Un envoi coupé peut être renvoyé : il est reconnu, et jamais appliqué deux fois.
- **Deux garde-fous :**
  - l'**empreinte** du catalogue est comparée à chaque publication, et lors d'une vérification régulière de l'atelier ;
  - un **renvoi complet** remplace tout le catalogue en cas d'écart, pour revenir en arrière, ou après un changement du modèle.
  Une ligne modifiée à la main dans la base est donc remise en ordre à la vérification suivante. Seule la forme canonique de chaque ligne fait foi.
- **Revenir en arrière** crée une publication nouvelle, qui reprend l'état d'une publication ancienne. L'historique avance toujours.
- **La base n'est qu'une copie.** Si elle se perd ou s'altère, l'atelier la remplit à nouveau, automatiquement, avec la dernière publication confirmée, et prévient l'éditeur. Rien n'est automatique juste après une restauration de l'atelier, ni quand une publication plus récente, faite depuis un autre appareil, risquerait d'être perdue. C'est aussi le cas quand l'atelier n'a pas observé le site assez récemment pour savoir qu'aucune publication plus récente n'existe : il bloque alors, et prévient l'éditeur.
- **La lecture** : chaque requête est servie depuis un instantané en mémoire, une seule publication par requête. Un instantané ne recule jamais : une base vidée ou restaurée à un état ancien n'est pas servie, tant que le site garde un témoin plus récent hors de la base (son instantané en mémoire, sa copie, ou le numéro qu'il a noté avant de valider). Sans ce témoin, au démarrage, il ne peut pas savoir qu'une base est en retard : c'est la vérification régulière de l'atelier qui le voit et la remet en ordre. Les ressources dérivées (recherche, fragments) portent le numéro et le début de l'empreinte de la publication, ainsi que l'identifiant du build ; l'ETag aussi. Une adresse qui nomme une publication ne sert jamais une autre publication : si celle-ci n'est plus disponible, la réponse le dit, sans cache, et la page se recharge. Les pages du catalogue sont rendues à la demande, sans qu'aucun fichier d'un build précédent puisse les masquer.
- **Le repli** : si la base est illisible, le site sert la dernière copie dont il dispose. C'est la copie de la dernière publication, qu'il écrit lui-même, hors de la base ; sinon, une page de maintenance. Avant de valider une publication, le site note aussi hors de la base le numéro qu'il valide, ou il l'annule : une copie plus ancienne que ce témoin n'est pas servie, puisqu'elle ferait revenir ce que la publication manquante a retiré. Au démarrage, une base plus ancienne que ce numéro n'est pas servie non plus. Deux contenus ne portent jamais le même numéro : seul le renvoi de l'envoi noté, ou un renvoi complet de numéro plus grand, referme l'écart. Ce numéro n'est jamais abaissé : une validation dont l'issue est inconnue le laisse en avance, et le site préfère alors la page de maintenance, jusqu'à ce que l'atelier referme l'écart. Jamais un catalogue vide, ni des données d'exemple, ni l'ancien catalogue embarqué au build, où reviendrait ce qui a été retiré depuis : y revenir est une décision de l'éditeur.
- **Les identifiants** sont comparés octet pour octet, dans un format fermé, vérifié à l'entrée dans l'atelier, par le site et par la base.
- **Les vignettes** restent des fichiers, envoyés à part et vérifiés un par un : taille, type, empreinte (ADR 0052). Une publication qui désigne une vignette absente est refusée. Leurs adresses publiques ne changent pas : la publication associe chaque nom à l'empreinte d'un fichier, et un nom n'en désigne qu'un.
- **Le modèle évolue par ajouts** : des migrations additives, appliquées par le site à son démarrage. Le site refuse un lot d'une autre version du modèle.
- **La mise en service** :
  1. un mois de double publication. Les visiteurs gardent le contenu publié par le chemin actuel, et les pages fabriquées comme aujourd'hui. Le rendu à la demande tourne à côté, et il est comparé page par page : d'abord aux pages d'aujourd'hui, sur les mêmes données ; puis sur les données du nouveau chemin ;
  2. la bascule, en deux temps : la fabrication des pages, puis la source des données ;
  3. l'atelier devient le seul écrivain (ADR 0060) ;
  4. un dépôt de code sans données.

## Conséquences

- **Positives** :
  - une correction approuvée passe en ligne sans rebuild ;
  - un build raté ne peut plus couper le site pour une donnée ;
  - la base garantit l'atomicité et la concurrence ;
  - des tables lisibles, et des envois de quelques Kio.
- **Négatives** :
  - une base, une bibliothèque de connexion et des identifiants de plus chez l'hébergeur ;
  - deux façons d'envoyer (le lot et le renvoi complet) ;
  - des tables qui évoluent avec le modèle ;
  - une correction faite à la main dans la base est écrasée ;
  - une écriture de plus sur le disque du site à chaque publication : si elle échoue, la publication est annulée.
- **Notes** :
  - l'empreinte prouve que la base contient l'état attendu, pas qui l'a écrit. Une personne qui a l'accès à la base peut la modifier avec son empreinte : la vérification régulière de l'atelier le voit, puis remet la dernière publication confirmée et prévient l'éditeur ;
  - trois vérifications chez l'hébergeur précèdent toute mise en service : un envoi d'un mégaoctet lu en entier, la connexion du site à sa base, la survie du dossier des vignettes à un build ;
  - le kit Community demande une base MySQL ou MariaDB (ADR 0062).
