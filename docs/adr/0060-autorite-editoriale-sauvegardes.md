# ADR 0060 — Autorité éditoriale et sauvegardes

- **Statut** : Acceptée (2026-11-01), à la validation de la documentation ; acceptée sur le principe le 2026-10-25
- **Date** : 2026-10-25
- **Décideurs** : équipe Reco (éditeur)
- **Liens** : ADR 0058 (publication sans rebuild) ; ADR 0059 (approbation) ; ADR 0056 (registre des identifiants) ; ADR 0055 (modèle canonique)

## Contexte

Le corpus est écrit aujourd'hui à plusieurs endroits : la chaîne de venus commite et pousse, et des PR de contenu partent du poste de l'éditeur. Git sert à la fois de stockage, de canal de publication et de sauvegarde. Plusieurs podcasts pourraient suivre, chacun avec son propre site : garder leurs données dans un dépôt de code ne tiendrait pas.

## Décision

- **Un seul écrivain des données de travail** : venus, dans un répertoire hors du clone Git. Cela vaut pour les brouillons, la relecture et les notes. Les maintenances se font sur venus.
- **Les publications** peuvent venir de venus ou d'un appareil de l'éditeur (ADR 0059). Le site refuse une publication qui ne part pas de celle en ligne, et venus récupère toute publication faite ailleurs avant de reprendre.
- **Le passage** à cet écrivain unique vient après la bascule de la publication. Les PR de contenu s'arrêtent alors, après la vérification des branches ouvertes. Les PR de code continuent.
- **Aucune donnée de podcast dans un dépôt de code** :
  - après le passage, la copie gardée dans le dépôt n'est plus rafraîchie ;
  - après le mois de double publication, le dépôt repart d'un historique neuf, avec le code seul. L'ancien est archivé en deux copies avant sa suppression ;
  - les tests utilisent des données d'exemple.
- **Sauvegarde** : chaque jour, depuis venus, une copie chiffrée part hors site. Une perte de 24 h au plus est acceptée. Git ne sert plus d'archive des données.
  - Avant chaque sauvegarde, une copie cohérente est prise sous les verrous de la chaîne : la relecture s'arrête quelques secondes, à une heure creuse. Un manifeste d'empreintes accompagne la copie. Elle n'est mise en place qu'une fois vérifiée : en cas d'échec, la précédente reste, la relecture repart, et l'éditeur est prévenu.
  - La clé qui scelle les publications de venus reste hors des sauvegardes : après une restauration, une clé neuve la remplace.
  - La copie contient aussi l'export complet de chaque publication. La base de l'hébergeur n'est donc qu'une copie, que venus peut remplir à nouveau (ADR 0058).
- **Restauration exercée** avant le passage, puis chaque trimestre. Une copie récupérée est vérifiée par son manifeste et par l'empreinte de la dernière publication qu'elle contient. Après une restauration de venus, toute action automatique reste bloquée jusqu'à la décision de l'éditeur. venus récupère d'abord les publications faites depuis la sauvegarde, avec leurs événements (retraits d'épisodes, identifiants émis ou supprimés) : un épisode retiré ne revient pas, et un identifiant n'est jamais redonné. Une récupération interrompue reprend sans rien appliquer deux fois. Si ses données ne redonnent pas l'empreinte du site, le blocage reste.
- **Secours** : si venus est en panne, le poste de l'éditeur publie des corrections. Les nouveaux épisodes attendent son retour.

## Conséquences

- **Positives** : une seule autorité sur les données ; Git redevient un dépôt de code, le même pour tous les podcasts ; la sauvegarde est vérifiable.
- **Négatives** :
  - les épisodes dépendent de venus : une panne suspend leur publication, pas le site, qui continue de servir la dernière publication ;
  - l'historique du code d'avant le dépôt neuf n'est plus en ligne : il reste dans l'archive.
- **Notes** : la durée réelle de l'arrêt de la relecture n'est pas mesurée ; elle sera relevée à la répétition du passage.
