# La chaîne automatique sur venus

Un épisode d'*Un bon moment* sort sur YouTube le dimanche à 10 h. Sans que le Mac ni
aucun portable ne soit allumé, venus :

1. **détecte** la vidéo sur la chaîne et crée l'épisode (`yt-<id>`) ;
2. **transcrit** l'audio sur son processeur — `large-v3-turbo`, ~17 min pour 82 min ;
3. **extrait** les recos candidates, en brouillon ;
4. **réécoute** les quelques secondes d'où vient chaque citation, en soufflant à Whisper
   les noms que l'extraction a reconnus (`preciser_citations.py`) : la citation publiée
   vient telle quelle de la transcription, qui écorche les noms propres ;
5. **cale** chaque citation sur la transcription (`caler_citations.py`) : le minutage
   prend celui de la ligne où la phrase est dite — le modèle d'extraction le recopiait,
   parfois avec une minute de trop —, et un nom mal transcrit (« Camelot ») prend la
   graphie du titre ou du créateur (Kaamelott) ;
6. **prévient sur Matrix**, avec le lien de la page de validation et chaque nom rétabli
   (ancien → nouveau) : la relecture tranche, en particulier quand c'est la fiche qui
   se trompe ou quand l'invité a dit le titre français.

**Le registre des graphies** (décision R6 A du 2026-11-27, `tools/graphies.py`) : en fin de
traitement d'un épisode, après la réécoute et le calage des citations (sinon leurs corrections
automatiques passeraient pour des corrections de relecture), la chaîne garde le brouillon de chaque
reco encore à relire ; un nouveau passage l'écrase tant que la reco n'est pas relue. La publication
d'un épisode relu compare ce brouillon à la version validée : chaque nom propre corrigé
(« Hilleret » → « Hillairet ») entre au registre, `tools/output/graphies/registre.json`, hors de
Git. Les petits mots courants (« Le » → « Les ») n'y entrent pas, et un brouillon d'un autre épisode
(identifiant de reco réutilisé) est ignoré. Aux épisodes suivants, la page de validation affiche
« Graphie déjà corrigée » dans l'encadré « À vérifier » quand la forme fautive revient, tant que la
reco n'est pas validée et que la bonne graphie n'est dans aucun de ses champs. Elle ne fait que
proposer : la correction reste à faire dans « Corriger ». Seuls les épisodes traités après la mise
en service y entrent, et une reco écartée n'y entre pas.

La relecture reste humaine : la page de validation est le serveur de relecture
habituel, sur <http://192.168.1.59:8000> depuis le réseau local, ou
<http://10.8.0.1:8000> par le VPN.

⚠️ **Elle n'a aucune authentification.** Jusqu'au 2026-10-02 elle n'écoutait que sur
l'adresse du VPN ; elle écoute désormais sur toutes les interfaces, et seul ufw la
protège — port 8000 autorisé depuis `192.168.1.0/24` et `10.8.0.0/24`, Internet exclu
par le refus par défaut. Tout appareil du Wi-Fi peut donc modifier le corpus. Pour
refermer sans perdre l'accès local : exiger une clé dans l'URL et répondre 404 sans
elle, comme le fait déjà `/audience` (`src/lib/audience/`).

**La garde des hôtes** (tableau de bord, 28/11/2026, `tools/review_handler_base.py`) ferme
le « DNS rebinding » : une page piégée qui parle au serveur sous son propre nom de domaine
reçoit un 403, en lecture comme en écriture. Sont admis une adresse IP littérale, un nom en
`.local`, `localhost`, l'hôte de `RECO_REVIEW_URL` et les noms de `RECO_REVIEW_HOTES`.
`RECO_REVIEW_URL` et `RECO_REVIEW_HOTES` ne comptent qu'en mode réseau local (`ALLOW_LAN`) :
en mode local strict, seuls `localhost` et le bouclage passent, quoi que disent ces deux
variables. Un signet sous un autre nom recevrait « Forbidden » : ajouter ce nom à `RECO_REVIEW_HOTES`, puis
`docker compose up -d --force-recreate review` sous le verrou du tick. Chaque refus est
journalisé avec le `Host` reçu. Un moniteur HTTP qui appellerait la page par un nom de
conteneur serait refusé de même.

Juste après l'extraction, le même passage **cherche les liens** des brouillons
(`chercher-liens`, cf. `tools/liens_avant_relecture.py`) avec les passes de la
finalisation, sans arrêter la page de validation : chaque carte montre ensuite ses
liens, et un lien faux se retire d'un clic (son URL est notée dans `linksRejected`
et ne revient plus). Un message Matrix dit combien de liens ont été trouvés.

Une fois l'épisode relu de bout en bout (plus aucune reco en brouillon), le passage
suivant le **finalise** : liens d'écoute posés par `enrich_music_links` — qui n'écrit
une URL que si Deezer, Apple Music, Spotify ou Qobuz corrobore titre ET artiste, et
dont la passe Qobuz se coupe par `RECO_QOBUZ=0` (voir plus bas) —, fiches « où regarder »
des films et séries par `enrich_tmdb` (clé `TMDB_API_KEY` dans `.env` ; si elle manque
ou si TMDB répond mal, l'épisode est finalisé quand même et le message le signale ;
une plateforme sans recherche publique ou disparue — Orange VOD et SFR Play depuis le
2026-11-13 — ne reçoit aucun bouton, et deux offres qui mènent à la même recherche
n'en reçoivent qu'un, cf. `tools/tmdb_providers.py`),
puis conversion en œuvres et mentions par `publier_episode.py`, et un message Matrix
qui liste **ce qui reste à faire à la main**, reco par reco. Ce qui demande un jugement
(homonymes, livres, jeux, associations, vidéos, sites officiels) n'est jamais deviné.

Le passage suivant **publie** : il commite les fichiers de l'épisode, les pousse sur une
branche `contenu/<guid>` et ouvre la PR (voir plus bas). Il ne reste donc qu'un clic :
fusionner. `migrate_reco_to_item_mention.py`, lui, ne doit jamais être lancé — il
réécrit tout le corpus.

## Publication : ce que venus pousse, et comment

Une **clé de dépôt** ed25519 (`~/.ssh/reco_deploy`, droits 600) est déclarée en écriture
sur ce dépôt seul. Le clone s'en sert par son `core.sshCommand`, et le compose la monte
dans le conteneur **en lecture seule, au même chemin absolu** — c'est ce qui rend la
configuration valable des deux côtés. Son homologue publique est déposée sur GitHub ;
la partie privée n'a jamais quitté venus.

La séquence évite un piège : le clone est sur `main`, et `tick.sh` fait `git pull
--ff-only` à chaque passage. Un commit laissé sur `main` en local ferait échouer ce pull
dès la fusion de la PR.

1. `git add` des seuls fichiers de l'épisode — épisode, recos, mentions, œuvres, et ses
   vignettes (`public/vignettes/`), téléchargées juste avant par
   `tools/vignettes_episodes.py`. Une vignette introuvable ne bloque pas la publication :
   la carte s'affiche alors sans image (ADR 0052) ;
2. commit, puis poussée sur `contenu/<guid>` ;
3. **vérification** que la branche distante porte bien ce commit ;
4. alors seulement, `main` revient sur `origin/main` (`reset --mixed`, jamais `--hard`,
   qui emporterait une validation en cours) et les copies locales des fichiers poussés
   sont retirées : la fusion de la PR les ramènera, suivies par git.

Rien n'est retiré si la poussée échoue. L'étape refuse par ailleurs de travailler si une
reco est encore en brouillon, ou si le clone porte la moindre modification étrangère à
l'épisode — jamais emporter le travail de quelqu'un d'autre dans un commit.

**Conséquence à connaître** : entre la poussée et la fusion, l'épisode n'apparaît plus
sur la page de validation. Sa relecture est terminée à ce stade, et le message Matrix le
rappelle.

### Ouvrir la PR automatiquement : `RECO_GITHUB_TOKEN`

Une clé de dépôt permet de pousser, pas d'ouvrir une PR : cela passe par l'API. Sans
jeton, tout fonctionne et le message Matrix porte le **lien de comparaison**, qui ouvre
le formulaire prérempli — un clic de plus. Avec un jeton, la PR est ouverte et le message
porte son adresse.

Le créer sur GitHub → *Settings* → *Developer settings* → *Personal access tokens* →
*Fine-grained tokens*, en le restreignant au seul dépôt `Reco` et à la seule permission
**Pull requests : Read and write**. Puis l'ajouter au `.env` : `RECO_GITHUB_TOKEN=…`.
Aucune autre permission n'est nécessaire : la poussée passe par la clé, pas par le jeton.

## Relancer la recherche de liens à la sortie d'une œuvre : `RECO_SORTIES_ANNONCEES=1`

Décision « R4 B », 27/11/2026. Quand l'éditeur note une **date de sortie annoncée**
(`releaseDate`) sur une reco, par exemple un album pas encore publié, les liens d'écoute
n'existent pas encore au moment de la publication. L'étape `tools/sorties_annoncees.py`
les cherche donc après coup, sans que personne y pense.

- **Quand** : une fois par jour, au premier passage de `tick.sh` après 6 h à Paris, du jour
  de la sortie à J+30. Inerte sans `RECO_SORTIES_ANNONCEES=1` dans le `.env` : la
  retirer la coupe au passage suivant, sans commit. L'état (jours traités, relances,
  propositions) est dans `tools/output/pipeline/sorties-annoncees.json`.
- **Comment** : les passes de recherche tournent sur une **copie d'`origin/main`**, dans un
  dossier à part (`tools/branche_de_contenu.py`). Le clone vivant n'est jamais écrit, ni son
  `HEAD`, ni son index : la page de validation peut rester ouverte, et un fichier que
  l'éditeur vient de sauvegarder ne risque rien. C'est la seconde façon de pousser, à côté
  de `publication.py` (qui, lui, commite dans le clone). Même clé de dépôt, même jeton
  `RECO_GITHUB_TOKEN` (sans lui, le message porte le lien de comparaison).
- **Ce que voit l'éditeur** :
  - une PR `contenu/sorties-AAAA-MM-JJ` (`-2`, `-3`… si le nom est pris), une seule par jour
    pour toutes les recos, qu'il n'a qu'à fusionner ;
  - un message Matrix 🗓️ « liens trouvés après sa sortie du … » par reco ;
  - un message ⏳ « sortie annoncée, aucun lien trouvé en … » quand la recherche a déjà été
    faite, sans résultat (une seule fois par reco) ;
  - un message ⚠️ quand une reco est sautée parce que l'éditeur l'a modifiée dans le clone
    (sa PR de liens ferait échouer le `pull`), quand une passe tombe en panne, ou quand la
    publication échoue. Chaque panne n'est signalée qu'une fois.
- **Ce qu'elle ne refait jamais** : un lien retiré à la relecture (`linksRejected`) ne revient
  pas, et une adresse ou un identifiant (`externalIds`) déjà proposés par une PR, même
  refermée, ne sont pas reproposés. Tant qu'une PR de liens attend, la reco est sautée.
  Une PR **n'attend plus** (tour 1 de revue, PR #227) dès que ses adresses figurent dans la
  reco d'`origin/main` (fusion de toute sorte, squash et rebase compris) ; sinon, avec
  `RECO_GITHUB_TOKEN`, dès que GitHub la dit fermée ou fusionnée ; sans jeton, quand sa
  branche a disparu ou que son commit est dans `origin/main`. Une PR refermée sans fusion
  laisse donc la reco relançable, avec les seules adresses nouvelles. Seules les recos encore
  dans leur fenêtre sont testées, ce qui borne le nombre d'appels à GitHub.
- **Le ⏳ ne part pas** si l'éditeur a posé un lien à la main depuis la première relance (un
  lien que la reco n'avait pas ce jour-là).
- **Limites de la V1** :
  - seuls les types `album`, `musique`, `livre` et `jeu` sont servis ; les **films et les
    séries attendent** (leurs passes passent par TMDB, écartées exprès) ;
  - la relance ne va pas plus loin que la reco : **l'œuvre** (`year`, alias) et **les recos
    sœurs** de la même œuvre ne suivent pas, ni les playlists de l'épisode.
- **Essai sans rien écrire** : `docker compose run --rm -T pipeline python
  sorties_annoncees.py --apercu` affiche ce que l'étape ferait. Aucun état écrit, aucune
  branche, rien d'envoyé, et **aucun `git fetch`** (tour 1 de revue, PR #227) : il lit
  l'`origin/main` de la dernière récupération, celle du dernier passage de `tick.sh` ; il
  ignore la variable et l'heure.
- **Code de sortie** : 0, ou 1 si l'état est illisible, si une commande git échoue (`fetch`,
  lecture d'`origin/main`, `ls-remote` ; réessayé au passage suivant, le jour n'est pas
  noté) ou si la publication échoue ; `tick.sh` le journalise sans arrêter le passage.
  Une reco dont le JSON est illisible sur `origin/main` est sautée et signalée une fois (⚠️),
  elle ne fait pas échouer l'étape. Un message ⚠️ qui n'a pas pu partir sur Matrix est
  renvoyé au passage suivant.

## Le tableau de bord : `/bord`

Décision R2 B du 27/11/2026, puis TB-1 C du 28/11/2026. La page `/bord`, liée depuis
l'accueil de la relecture (« 🧭 Tableau de bord »), dit en un coup d'œil ce qu'il reste à
faire. `/` reste la relecture. Cinq colonnes sur l'écran de 39 pouces : **À faire
d'abord**, **Chaîne**, **Audience** au centre, **Réseaux**, **Système**. Sous 2 200 px, le
menu des sections passe à gauche et la chaîne à droite ; sous 900 px, une colonne avec des
onglets. Le choix « Vue : auto · 39" · 13" · téléphone » reste gardé dans le navigateur. La
page se recharge toute seule toutes les 5 minutes.

- **À faire d'abord** : les épisodes à relire, les PR de publication à fusionner (lues sur
  GitHub ; sans lecture de GitHub, l'état de la chaîne), les réseaux pas encore faits des 3
  derniers épisodes publiés, le nombre de signalements en attente, le nombre de liens morts
  du dernier rapport, les PR de sorties à fusionner. Une PR porte un bouton « Ouvrir la PR »
  vers `github.com` seulement.
  Les signalements disent « inconnu » tant que l'audience n'est pas « à jour » (une lecture
  ratée garde les anciens chiffres, pas la ligne) ; les sorties disent « inconnu » tant que
  GitHub n'est pas lu, les liens morts tant qu'aucun contrôle du lundi n'a écrit son résumé.
- **Chaîne** : l'épisode en cours et ses étapes (détecté, transcrit, extrait, finalisé,
  publié), les erreurs en cours et les 5 derniers passages de `tick.sh`. Chaque passage note
  dans `tools/output/bord/passages.jsonl` les étapes lancées et celles en échec (200 lignes
  gardées). Une écriture ratée est journalisée et n'arrête pas la chaîne. L'en-tête dit « en
  retard » au-delà de 2 h 30 sans passage terminé, le seuil de Kuma. Comme `tick.sh` ne note un
  passage qu'à sa fin, il écrit le début du passage dans `tools/output/bord/en-cours` dès qu'il
  tient le verrou, et l'efface en notant la fin : tant que le fichier est plus récent que le
  dernier passage noté, l'en-tête dit « passage en cours depuis … » au lieu de « en retard »
  (tour 1, F8, 28/11/2026). Au-delà de 2 h 30, le passage est dit « bloqué » ; un fichier resté
  après une note ratée finit de même par le dire. Les échecs du dernier passage terminé
  passent avant.
- **Réseaux** : une case par réseau (Instagram, Threads, Spotify, Deezer, SensCritique,
  YouTube) et par épisode, pour les 3 derniers publiés. Un clic la coche ou la décoche, sans
  recharger la page ; sans script, le formulaire part et la page revient avec un message. Les
  cases vivent dans `tools/output/bord/reseaux.json`. Un fichier abîmé n'est jamais réécrit :
  la page le signale, et aucune case ne s'enregistre tant qu'il n'est pas réparé ou retiré.
- **Audience** (tranche 2c, 28/11/2026), la colonne la plus large : confirmés, incertains et
  robots en visiteurs-jours sur 7 jours en grand, ceux de 30 jours en dessous ; 7 barres
  empilées (un jour sans fichier de mesure est « pas de mesure », jamais zéro), doublées d'un
  tableau pour le lecteur d'écran ; les 5 premières pages et provenances, en texte seul ; les
  clics pour 100 visiteurs ; les jours où le signal semble en panne ; le lien vers `/audience`,
  sans la clé (il s'ouvre depuis le signet). Avant la bascule du tri, « ancien tri » : humains
  et passages de robots seulement. Les chiffres viennent de `GET /api/bord` du site, avec
  `RECO_AUDIENCE_KEY` (ci-dessous) : la page ne lit que le cache
  `tools/output/bord/distant.json`, et le relit sur le site en arrière-plan quand il a plus de
  10 minutes. En tête, l'état et l'âge : « À jour · lu il y a 12 min », ou clé absente, clé
  refusée (le site répond « introuvable » : clé différente, clé absente du site, ou route pas encore là), site injoignable, réponse illisible, cache
  illisible (à effacer à la main). Après une panne, les derniers chiffres restent, avec leur
  âge.
- **Signalements**, dans la colonne des réseaux : les 5 derniers en attente, avec leur reco,
  leur catégorie et leur date, jamais le nom, l'adresse ni le texte ; « + N autres » au-delà.
- **Sorties à venir**, dans la colonne des réseaux (tranche 3d-2, 28/11/2026) : titre, date et
  jours restants des recos validées qui sortent dans les 30 jours ; « déjà sortie, en relance »
  jusqu'à 30 jours après la date.
- **Système** : **Santé et versions** (la CI de `main`, le dernier déploiement, l'image de la
  chaîne selon `compose.yml`), **Coûts et modèles** (7 jours et 7 jours d'avant, modèles
  d'extraction et de secours), **Liens morts** (nombre, date du rapport et son âge, « ancien »
  au-delà de 8 jours, 10 adresses au plus) et **Graphies apprises** (les 5 plus vues). Un bloc
  qui n'a pas pu être lu dit « inconnu », jamais « aucun » ni « 0 $ ». GitHub se lit par son
  API publique : `RECO_GITHUB_TOKEN` est **facultatif** ; sans lui, les appels sont anonymes,
  environ 24 par heure sous la limite de 60 (le dernier essai en échec s'affiche : « limite de
  débit atteinte »). Le résumé des liens morts, `tools/output/bord/liens.json`, est écrit par
  le contrôle du lundi (`verifier_liens.sh`, vu par `review` dans le même dépôt monté) : avant le
  premier lundi suivant la mise en service, le bloc dit « inconnu ». Mise en service :
  `docker compose restart review` sous le verrou du tick, une fois le `git pull` passé.

Les polices de la page (Bebas Neue, Inter, licence OFL) sont servies par le serveur lui-même
(`/polices/…`, `tools/review_polices/`), sans appel extérieur. `RECO_BORD_DIR` déplace
le dossier du tableau de bord pour les essais : ne pas la poser dans le `.env`. `tick.sh` ne l'y
lit pas, et le serveur et `tick.sh` écriraient alors dans deux dossiers différents. La page
n'écrit que dans ce dossier, jamais dans le corpus, et ne prend aucun verrou de la chaîne : comme la relecture,
elle s'arrête une à deux minutes pendant l'extraction et la finalisation. Après une PR qui la
change : `docker compose restart review` sous le verrou du tick, une fois le `git pull` passé.

## Où sont les choses

| Chemin sur venus | Rôle | Sauvegardé |
|---|---|---|
| `~/docker/reco/compose.yml` | lien vers `depot/deploy/venus/compose.yml` | oui |
| `~/docker/reco/.env` | clés (droits 600) | oui |
| `~/docker/reco/depot/` | clone du dépôt ; `tools/output/` y garde transcriptions et états | oui |
| `~/docker/reco/logs/tick-AAAA-MM.log` | journal des passages | oui |
| `~/docker/reco/depot/tools/output/bord/` | tableau de bord : `passages.jsonl` (200 derniers passages) et `en-cours` (début du passage qui tourne), écrits par `tick.sh`, `reseaux.json` (cases cochées), `distant.json` (dernières lectures de l'audience et de GitHub), `distant.log` (sortie du rafraîchissement), `liens.json` (résumé du contrôle des liens du lundi) | oui |
| `~/.cache/reco/` | modèle Whisper (1,6 Go), caches yt-dlp — se retéléchargent | **non**, volontairement |
| `~/.ssh/reco_deploy` | clé de dépôt (écriture sur ce dépôt seul), droits 600 | **non** : la sauvegarde ne couvre que `~/docker`. Une clé perdue se régénère et se redéclare sur GitHub |

## Le `.env`

```
ANTHROPIC_API_KEY=…            # extraction ; sans elle, la chaîne s'arrête après la transcription et le signale
RECO_MATRIX_HOMESERVER=…       # les trois mêmes valeurs que les secrets GitHub de la veille RSS
RECO_MATRIX_TOKEN=…
RECO_MATRIX_ROOM=…
RECO_REVIEW_URL=http://192.168.1.59:8000   # adresse mise dans les liens Matrix ; l'adresse du VPN (10.8.0.1) marche aussi
TMDB_API_KEY=…                 # « où regarder » des films et séries ; absente, l'épisode est finalisé quand même
SPOTIFY_CLIENT_ID=…            # liens Spotify ; absents, le rapport dit « no-credentials » et non « aucun lien »
SPOTIFY_CLIENT_SECRET=…
RECO_SPOTIFY=0                 # sans Premium, l'API répond 403 : liens posés à la publication (docs/reseaux-episode.md)
RECO_GITHUB_TOKEN=…            # ouvre la PR de publication ; absent, le message porte le lien de comparaison ; /bord lit GitHub sans lui (appels anonymes, 60 par heure)
RECO_SORTIES_ANNONCEES=1       # relance quotidienne des liens à la sortie annoncée ; absent, l'étape ne fait rien
RECO_KUMA_PUSH_URL=…           # moniteur « push » Uptime Kuma ; absent, aucun ping n'est envoyé
RECO_AUDIENCE_KEY=…            # la même clé que chez l'hébergeur : /bord lit l'audience par GET /api/bord ; absente, la page dit « clé absente »
RECO_REVIEW_HOTES=…            # facultatif : autres noms admis par la garde des hôtes (virgules ou espaces) ; lu seulement en mode réseau local (ALLOW_LAN)
```

### Changer de modèle d'extraction : `RECO_MODELE_EXTRACTION`

Les fournisseurs retirent leurs modèles tous les quelques mois. Le modèle se choisit
dans le `.env`, **sans commit ni redéploiement** — mais jamais à l'aveugle : un autre
modèle change ce que la chaîne trouve (mesuré le 2026-09-17, cf. `tools/extract_recos.py`).

```
RECO_MODELE_EXTRACTION=claude-opus-5   # défaut s'il est absent
RECO_MODELE_SECOURS=claude-opus-5-5    # défaut ; « aucun » coupe le secours
```

- **Veille** : l'étape `veiller-modeles`, une fois par semaine, interroge la liste des
  modèles d'Anthropic. Message Matrix si le modèle configuré (ou le secours) a disparu,
  si son retrait est annoncé (`retires_at` ou `deprecated_at` de l'API), ou si un modèle
  plus récent de la même famille est sorti — chacun signalé une fois.
- **Banc d'essai**, avant tout changement — il rejoue l'extraction sur les épisodes
  relus les plus récents et compare à la relecture (recos retrouvées, déjà écartées,
  autres, coût par épisode). Rien n'est écrit dans le corpus ; compter ~0,56 $ par
  épisode et par modèle avec Opus 5 :

  ```sh
  docker compose run --rm pipeline python banc_modeles.py --source un-bon-moment --plan
  docker compose run --rm pipeline python banc_modeles.py --source un-bon-moment \
    --modeles claude-opus-5 claude-opus-5-5
  ```

- **Secours** : si le fournisseur répond « modèle inconnu » (404), l'épisode est
  extrait avec `RECO_MODELE_SECOURS` et un message le signale. Toute autre erreur
  reste une erreur.
- L'effort de raisonnement n'est envoyé qu'aux modèles qui l'acceptent, d'après l'API
  des modèles : un nouveau modèle n'exige pas de modifier le code.

**Choix en service : Opus 5.5 depuis le 2026-10-22**, Opus 5 en secours
(`.env` de venus ; l'ancien fichier est gardé en `.env.avant-opus-5-5`). Banc du
même jour, sur S6-E03 à E05 (35 recos relues) :

| Modèle | $/épisode | Retrouvées | Déjà écartées reproposées | Autres | Durée |
|---|---|---|---|---|---|
| Opus 5 | 0,42 | 25 / 35 | 4 | 8 | 78 s |
| Opus 5.5 | 0,39 | 26 / 35 | 3 | 5 | 145 s |

Écart dans le bruit sur trois épisodes, mais Opus 5.5 ne fait moins bien sur
aucune colonne. Manquées par les deux : Bref. 2 le livre, Renversée, Les Groos,
Rose et Massimo, Impionçable, la vidéo IA de Kemar — le modèle n'y peut rien.
Pour revenir en arrière : remettre `.env.avant-opus-5-5` en place.

### Couper Qobuz sans redéployer : `RECO_QOBUZ=0`

Qobuz n'a pas d'API : la passe lit ses pages web, et c'est la seule source du dépôt
qui dépende de la structure d'une page. Elle ne produit jamais de faux lien — chaque
candidat est corroboré par la page cible — mais elle n'est pas reproductible : la
recherche de Qobuz ne classe pas ses résultats de façon stable, si bien qu'un même
artiste donne un lien à un essai et une ambiguïté au suivant (mesuré sur « Solann »,
que 0,923 de similarité rend indistinguable de « Solanna »).

Ajouter `RECO_QOBUZ=0` au `.env` la coupe au passage suivant, **sans commit ni
redéploiement** : la variable est relue à chaque appel. Les autres plateformes
continuent, et le rapport porte alors la mention « Qobuz COUPÉ » plutôt qu'un
silence qui ferait croire que Qobuz ignore ces œuvres. Valeurs acceptées pour
couper : `0`, `off`, `false`, `no`, `non` ; tout le reste — y compris l'absence de
la variable — laisse Qobuz actif.

### Poster les recos sous la vidéo YouTube : `RECO_YT_COMMENTAIRES=1`

Une fois l'épisode en ligne sur le site, l'étape `commenter` poste sous sa vidéo un
commentaire de la chaîne « Une Bonne Reco » : les recos avec leur minutage
cliquable, les évocations à part, et rien d'autre : YouTube efface en silence les
commentaires qui portent l'adresse du site, et depuis le 2026-11-02 au soir ceux qui
finissent par un renvoi vers la chaîne ou la signature « site de fan » (décision YT-3 A,
détail dans `tools/commentaire_youtube.py`). Le salon Matrix reçoit le lien du
commentaire posté, à ouvrir en navigation privée. Elle attend que la page porte les recos (PR fusionnée ET déploiement terminé), et ne
commente que les épisodes sortis depuis `RECO_YT_COMMENTAIRES_DEPUIS` (défaut :
2026-10-22). Aperçu sans rien poster : `python commentaire_youtube.py --apercu <guid>`.

Mise en place, une seule fois :

1. Google Cloud : un projet, l'API « YouTube Data API v3 » activée, un écran de
   consentement **publié** (en mode « Test », le jeton expire au bout de 7 jours),
   et des identifiants OAuth de type « Application de bureau ». Télécharger leur
   `client_secret.json`.
2. Sur un poste avec navigateur : `python tools/youtube_autoriser.py client_secret.json`,
   choisir la chaîne « Une Bonne Reco » au consentement. Le script écrit trois
   lignes dans `~/reco-youtube.env`.
3. Les recopier dans le `.env` de venus avec `RECO_YT_COMMENTAIRES=1`, puis
   supprimer `~/reco-youtube.env`.

```
RECO_YT_COMMENTAIRES=1
RECO_YT_CLIENT_ID=…
RECO_YT_CLIENT_SECRET=…
RECO_YT_REFRESH_TOKEN=…
```

Retirer `RECO_YT_COMMENTAIRES=1` coupe l'étape au passage suivant. Chaque
commentaire coûte 50 unités de quota sur 10 000 par jour.

**Les anciennes vidéos** (avant `RECO_YT_COMMENTAIRES_DEPUIS`) reçoivent le même
commentaire au compte-gouttes, de la plus récente à la plus ancienne. Décision du
2026-11-03 (YT-4 C) : deux ou trois par jour, à une heure tirée au hasard dans trois
créneaux (12 h–14 h, 16 h 30–18 h 30, 21 h–23 h), un tirage propre au jour choisissant les
créneaux qui postent ; les autres ne font que relire. Le rattrapage est **suspendu**
depuis le 2026-11-03 (`suspendu` dans l'état) : la reprise attend que le commentaire de
S6-E08 ait tenu 24 h. Elle se fait en remplaçant les deux lignes du 2026-11-02
(`23 9,13,17` et `23 21`) par :

```
0 12 * * * cd /home/etienne/docker/reco && [ -f depot/tools/rattrapage_commentaires_youtube.py ] && flock -n /tmp/reco-rattrapage-yt.lock docker compose run --rm -T pipeline python rattrapage_commentaires_youtube.py --creneau 1 --attente-max 120 --notifier matrix >> logs/rattrapage-youtube.log 2>&1
30 16 * * * cd /home/etienne/docker/reco && [ -f depot/tools/rattrapage_commentaires_youtube.py ] && flock -n /tmp/reco-rattrapage-yt.lock docker compose run --rm -T pipeline python rattrapage_commentaires_youtube.py --creneau 2 --attente-max 120 --notifier matrix >> logs/rattrapage-youtube.log 2>&1
0 21 * * * cd /home/etienne/docker/reco && [ -f depot/tools/rattrapage_commentaires_youtube.py ] && flock -n /tmp/reco-rattrapage-yt.lock docker compose run --rm -T pipeline python rattrapage_commentaires_youtube.py --creneau 3 --attente-max 120 --recap --notifier matrix >> logs/rattrapage-youtube.log 2>&1
```

puis en retirant `suspendu` du fichier d'état. Un appel attend dans son créneau
seulement s'il va poster : suspendu, inactif ou non retenu ce jour-là, il relit et
s'arrête aussitôt.

État dans `depot/tools/output/pipeline/rattrapage-commentaires-youtube.json` : les vidéos
commentées (`postes`) et celles mises de côté sur un échec qui leur est propre
(`de_cote`, avec la raison) ; retirer une entrée de `de_cote` la fait retenter.
Le salon Matrix reçoit un récapitulatif par jour (dernier créneau, `--recap`) avec le
lien de chaque commentaire du jour, à ouvrir en navigation privée — la relecture sans
compte ne prouve qu'une absence —, les échecs et la fin du rattrapage. Aperçu :
`python rattrapage_commentaires_youtube.py --apercu --nombre 3`.

## Quand ça tourne

```
*/10 9-18 * * 0  /home/etienne/docker/reco/depot/deploy/venus/tick.sh
*/10 11-16 * * 5 /home/etienne/docker/reco/depot/deploy/venus/tick.sh
5    */2  * * *  /home/etienne/docker/reco/depot/deploy/venus/tick.sh
```

Toutes les 10 minutes dans les deux fenêtres de publication — dimanche 9 h-19 h et
vendredi 11 h-17 h, la saison 6 ayant démarré un vendredi à midi —, sinon toutes les
deux heures. Un verrou (`flock`) empêche deux passages de se chevaucher. Interroger la
chaîne plus souvent n'apporterait rien, et exposerait venus au blocage « Sign in to
confirm you're not a bot » de YouTube.

### Les liens externes du site, chaque lundi à 3 h 17

```
17 3 * * 1  /home/etienne/docker/reco/depot/deploy/venus/verifier_liens.sh
```

`verifier_liens.sh` construit le site dans `~/reco-liens/site` (un clone tiré de
celui de la chaîne, dans l'image `node:24.22.2-bookworm-slim` : venus a Node 20 et
Astro en demande 22.22), puis sonde chaque adresse externe une fois, une requête à la
fois par site. Rapports dans `~/reco-liens/liens-AAAA-MM-JJ.{md,json}`, journal dans
`~/reco-liens/journal-AAAA-MM.log`. Le salon Matrix ne reçoit un message que si des
liens sont morts depuis la vérification précédente (`~/reco-liens/etat.json`), et
rien n'est jamais retiré du site. Les liens internes, eux, se vérifient dans la CI
après chaque build (`tools/verifier_liens.py internes dist`).

## Savoir que la chaîne tourne encore : le moniteur « push » de Kuma

Quand tout va bien, la chaîne est **silencieuse**. Si le cron meurt, si un conteneur
casse, si le verrou reste coincé, rien ne le dit : cela se verrait au prochain épisode
manqué. Kuma tourne sur venus et ne peut pas interroger la page de validation, ouverte
au seul réseau local et au VPN (l'adresse d'un conteneur n'est pas dans la plage
autorisée par ufw, et la garde des hôtes refuse un nom de conteneur). C'est
donc au passage de se signaler.

À la **fin** de chaque passage, `tick.sh` appelle l'URL de `RECO_KUMA_PUSH_URL` si elle
est définie. Un ping raté n'est jamais fatal : il est seulement journalisé.

Côté Kuma : *Add New Monitor* → **Monitor Type : Push** → nommer (« Reco — chaîne
venus ») → **Heartbeat Interval : 9000 s** (2 h 30) → *Save*. Kuma affiche alors une
*Push URL* : la coller dans le `.env` sous `RECO_KUMA_PUSH_URL`.

Pourquoi 2 h 30 : le passage le plus espacé tombe toutes les 2 heures, et un passage
peut durer une demi-heure (transcription puis extraction). En dessous, Kuma alerterait
pendant un passage normal ; beaucoup au-dessus, une panne du vendredi soir ne se
verrait que le lendemain. Les fenêtres à 10 minutes envoient simplement plus de pings
que nécessaire, ce qui ne gêne pas.

**Limite à connaître** : Kuma est sur venus. Il signale une chaîne morte alors que la
machine tourne — le cas courant — mais si venus s'arrête, Kuma s'arrête avec. Couvrir ça
demanderait une surveillance hors de la maison.

## Opérations courantes

```sh
cd ~/docker/reco
tail -f logs/tick-$(date +%Y-%m).log                     # suivre un passage
docker compose ps                                        # la page de validation tourne-t-elle ?
depot/deploy/venus/tick.sh                               # forcer un passage
docker compose run --rm pipeline python traiter_nouveaux_episodes.py --source un-bon-moment a-extraire
docker compose build && docker compose up -d review      # après un changement de requirements.txt,
                                                         # du Dockerfile ou de l'étiquette de l'image
git -C depot ls-remote origin main                       # la clé de dépôt répond-elle ?
docker compose run --rm pipeline git ls-remote origin main   # ... et depuis le conteneur
```

⚠️ **Après une reconstruction, vérifier que la transcription part encore.** Un build vert
ne prouve rien : le 2026-10-02, l'image reconstruite a installé PyAV 19, que
faster-whisper 1.2.1 ne sait pas appeler, et toute transcription mourait sur
`TypeError: open() got an unexpected keyword argument 'metadata_errors'`. Rien ne l'aurait
signalé avant le lundi suivant, épisode non transcrit à la clé. D'où la borne `av<19` dans
`tools/requirements.txt` et ce contrôle, qui tient en une ligne :

```sh
docker compose run --rm pipeline python -c \
  "import av, faster_whisper as w; print('av', av.__version__, 'fw', w.__version__)"
```

Ce contrôle ne suffit pas toujours. Une reconstruction monte tout ce que ses bornes permettent :
les paquets sans borne haute (`yt-dlp`, `anthropic`), et les autres jusqu'à leur borne. L'image du
2026-11-14 a changé ceux-ci :

| Paquet    | Avant (`2026-10-02-av18`) | Après (`2026-11-14-pillow13`) |
|-----------|---------------------------|-------------------------------|
| Pillow    | 12.3.0 (tiré par fastembed) | 13.0.0                      |
| fastembed | 0.8.1                     | 0.9.1                         |
| anthropic | 1.11.0                    | 2.8.0                         |
| yt-dlp    | 2026.08.19                | 2026.10.26                    |

Depuis sa version 2026.10, yt-dlp ne résout plus seul le défi JavaScript de YouTube. Il avertit
alors `n challenge solving failed: Some formats may be missing`. D'où `yt-dlp[default]`, qui
installe le solveur `yt-dlp-ejs`.

Après une reconstruction, vérifier aussi, **dans le conteneur** :

```sh
# yt-dlp : aucune ligne ne doit sortir
docker compose run --rm pipeline yt-dlp --encoding utf-8 -F \
  "https://www.youtube.com/watch?v=rwlXWp7Lrhg" 2>&1 | grep -i "challenge solving failed"
# l'extraction : un vrai appel du modèle configuré, qui doit lister ses recos
docker compose run --rm pipeline python -c "
import extract_recos as er; from common import make_anthropic_client; from modeles_llm import modele_extraction
p = er._request_params(modele_extraction(), 'Un Bon Moment', 'Kyan, Navo', 'Allez voir le film Eternal Sunshine.')
print([r.get('title') for r in er._parse_recos_from_content(make_anthropic_client().messages.create(**p).content)])"
```

**Revenir à l'image précédente** : remettre son étiquette dans `compose.yml`, puis
`docker compose up -d review` **sans** `build`. Le service déclare `image:` et `build:` : un
`docker compose build` reconstruirait les dépendances du jour sous l'ancienne étiquette et
effacerait le repli. Ne pas supprimer l'ancienne image (`docker image prune -a`) tant que la
nouvelle n'a pas traité un vrai épisode.

### Métriques du pipeline

Chaque étape de la chaîne écrit ses mesures dans
`depot/tools/output/telemetry/reco_metrics.sqlite` (durées, origine du média,
jetons et coût des appels, actions et temps actif de la page de validation).
Rien à commiter, rien à configurer : la configuration de chaque passe est
reconnue par son empreinte, et le payeur des appels se déduit de la clé.

```sh
docker compose run --rm pipeline python metrics_report.py coverage --source un-bon-moment
docker compose run --rm pipeline python metrics_report.py cohort --source un-bon-moment --season 6
docker compose run --rm pipeline python metrics_report.py recover   # tick.sh le fait chaque semaine
```

Contrat et limites : `docs/workflow-metrics.md`. Après la mise à jour, redémarrer
la page de validation (`docker compose restart review`) pour qu'elle serve le
script du temps actif.

## Premier passage

Au tout premier passage, la détection marque comme vues toutes les vidéos en ligne sans
rien signaler — sinon toute la chaîne serait rapportée comme nouvelle. Un épisode
reconnu mais absent du corpus est créé quand même.

## Retirer le service

Dans l'ordre de `_shared/docs/process-installation-app.md` : `docker compose down`
(sans `-v`), retirer les trois lignes de la crontab, la carte de Homepage, le moniteur
d'Uptime Kuma, la clé de dépôt côté GitHub (*Settings* → *Deploy keys*) et le jeton s'il
existe, puis marquer le service retiré dans `hosts.md`.
