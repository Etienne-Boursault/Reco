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

La relecture reste humaine : la page de validation est le serveur de relecture
habituel, sur <http://192.168.1.59:8000> depuis le réseau local, ou
<http://10.8.0.1:8000> par le VPN.

⚠️ **Elle n'a aucune authentification.** Jusqu'au 2026-10-02 elle n'écoutait que sur
l'adresse du VPN ; elle écoute désormais sur toutes les interfaces, et seul ufw la
protège — port 8000 autorisé depuis `192.168.1.0/24` et `10.8.0.0/24`, Internet exclu
par le refus par défaut. Tout appareil du Wi-Fi peut donc modifier le corpus. Pour
refermer sans perdre l'accès local : exiger une clé dans l'URL et répondre 404 sans
elle, comme le fait déjà `/audience` (`src/lib/audience/`).

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
ou si TMDB répond mal, l'épisode est finalisé quand même et le message le signale),
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

1. `git add` des seuls fichiers de l'épisode — épisode, recos, mentions, œuvres ;
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

## Où sont les choses

| Chemin sur venus | Rôle | Sauvegardé |
|---|---|---|
| `~/docker/reco/compose.yml` | lien vers `depot/deploy/venus/compose.yml` | oui |
| `~/docker/reco/.env` | clés (droits 600) | oui |
| `~/docker/reco/depot/` | clone du dépôt ; `tools/output/` y garde transcriptions et états | oui |
| `~/docker/reco/logs/tick-AAAA-MM.log` | journal des passages | oui |
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
RECO_GITHUB_TOKEN=…            # ouvre la PR de publication ; absent, le message porte le lien de comparaison
RECO_KUMA_PUSH_URL=…           # moniteur « push » Uptime Kuma ; absent, aucun ping n'est envoyé
```

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

## Savoir que la chaîne tourne encore : le moniteur « push » de Kuma

Quand tout va bien, la chaîne est **silencieuse**. Si le cron meurt, si un conteneur
casse, si le verrou reste coincé, rien ne le dit : cela se verrait au prochain épisode
manqué. Kuma tourne sur venus et ne peut pas interroger la page de validation, ouverte
au seul VPN (l'adresse d'un conteneur n'est pas dans la plage autorisée par ufw). C'est
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

## Premier passage

Au tout premier passage, la détection marque comme vues toutes les vidéos en ligne sans
rien signaler — sinon toute la chaîne serait rapportée comme nouvelle. Un épisode
reconnu mais absent du corpus est créé quand même.

## Retirer le service

Dans l'ordre de `_shared/docs/process-installation-app.md` : `docker compose down`
(sans `-v`), retirer les trois lignes de la crontab, la carte de Homepage, le moniteur
d'Uptime Kuma, la clé de dépôt côté GitHub (*Settings* → *Deploy keys*) et le jeton s'il
existe, puis marquer le service retiré dans `hosts.md`.
