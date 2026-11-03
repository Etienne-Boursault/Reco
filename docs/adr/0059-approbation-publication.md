# ADR 0059 — Approbation humaine des publications

- **Statut** : Acceptée (2026-11-01), à la validation de la documentation ; acceptée sur le principe le 2026-10-25
- **Date** : 2026-10-25
- **Décideurs** : équipe Reco (éditeur)
- **Liens** : ADR 0058 (publication sans rebuild) ; ADR 0052 (données de visiteurs) ; ADR 0054 (métriques, inchangé)

## Contexte

La publication sans rebuild (ADR 0058) supprime la PR fusionnée à la main, qui servait aussi de contrôle humain. Rien ne doit passer en ligne sans qu'un humain l'ait vu et approuvé. L'éditeur veut aussi pouvoir publier depuis plusieurs appareils, pour ne pas dépendre d'une seule machine.

## Décision

- **Pas de publication sans approbation explicite.**
  - L'écran « Publier », sur venus, montre ce qui change par rapport à la publication en ligne : les entités et les pages ajoutées, modifiées ou retirées.
  - L'écran est protégé par un mot de passe, haché par `scrypt`. La session est un cookie `HttpOnly`, `SameSite=Strict`, valable 8 h. L'écran n'est joignable que depuis le réseau privé de l'atelier, jamais directement depuis Internet. La connexion y est chiffrée (HTTPS), réseau privé compris : le mot de passe et la session ne circulent jamais en clair, et le cookie est marqué `Secure`.
  - Une approbation vaut pour un point de départ, un lot et une empreinte d'arrivée. Elle ne sert qu'une fois et expire : le site refuse d'appliquer pour la première fois une publication approuvée depuis plus de 24 heures. Un envoi déjà appliqué, renvoyé après une coupure, reste reconnu comme tel. Si la publication en ligne a changé entre-temps, elle est périmée. Le site vérifie le départ, puis que le catalogue obtenu a exactement l'empreinte approuvée : un autre lot ne peut rien publier d'autre que ce qui a été approuvé. L'approbation engage le lot entier, y compris ses événements (un épisode retiré, une fiche fusionnée ou supprimée), que l'éditeur voit avant d'approuver ; le site vérifie qu'aucun de ces événements ne contredit l'état d'arrivée. Une œuvre qui quitte le public, faute de citation publique, n'est pas pour autant supprimée.
  - Un appareil dont la publication est refusée, parce qu'une autre est passée avant, ne republie jamais tel quel : il compare, il bloque sur une modification concurrente du même champ, et il demande une nouvelle approbation.
  - Une commande de secours, qui exige un terminal, remplace l'écran au besoin.
- **La tâche planifiée prépare, elle ne publie jamais seule.** La seule exception est la remise automatique de la dernière publication confirmée, quand le site l'a perdue ou altérée (ADR 0058). Seule la clé de l'atelier peut la sceller : le site tient la liste des clés autorisées à remettre, et refuse une remise venue d'une autre clé. Il vérifie aussi que le motif annoncé par l'enveloppe scellée est celui du contenu.
- **Plusieurs appareils, chaque clé suffit.**
  - Le site accepte une publication scellée par l'une des clés de sa liste : venus, le poste de l'éditeur, puis ses futurs appareils.
  - Chaque clé est protégée par une phrase secrète sur son appareil. La clé de venus doit pouvoir sceller sans l'éditeur, pour la remise automatique : sa protection est celle de venus.
  - Ajouter ou retirer un appareil se fait par une ligne dans la configuration du site.
  - Un outil du poste lit la publication en ligne, applique une correction ou revient en arrière, puis scelle et envoie. Il ne publie pas d'épisode, et il ne crée ni ne retire aucune œuvre : l'identité des œuvres reste à l'atelier (ADR 0056). Avant de sceller, il vérifie les règles bloquantes du catalogue (ADR 0061).
  - Le site refuse toute publication qui ne part pas de celle en ligne. Avant de reprendre, venus récupère les publications faites ailleurs.
- **Risque accepté et écrit.** Voler un appareil avec sa phrase secrète suffit pour publier ; prendre le contrôle de venus aussi. Le site vérifie un sceau, pas un humain : la garantie humaine est appliquée par l'appareil qui envoie. Les parades :
  - une alerte à l'éditeur à chaque publication, avec l'appareil qui l'a scellée ;
  - le retour arrière, possible depuis le poste sans venus ;
  - le retrait de la clé.
- **Journaux** : schémas fermés, sans identifiant de session, adresse IP, navigateur ni cookie.
  - L'historique des publications et des approbations est gardé sans limite.
  - Les envois reçus ou refusés sont gardés 30 jours, ceux mis de côté pour anomalie 7 jours.
  - Aucune donnée de visiteur n'y entre.

## Conséquences

- **Positives** : chaque mise en ligne reste une décision humaine, tracée, sans donnée personnelle ; une machine en panne n'empêche pas de corriger le site.
- **Négatives** : une étape de plus pour l'éditeur à chaque publication. Plus il y a de clés, plus il y a de portes d'entrée.
- **Notes** :
  - l'écran doit être en service avant la première publication publique ;
  - un sceau exigé de l'éditeur, en plus de celui de la machine, n'aurait de sens qu'avec une branche principale protégée : c'est à réévaluer s'il y a un second éditeur, une offre Cloud ou un incident.
