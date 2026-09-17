# La chaîne automatique sur venus

Un épisode d'*Un bon moment* sort sur YouTube le dimanche à 10 h. Sans que le Mac ni
aucun portable ne soit allumé, venus :

1. **détecte** la vidéo sur la chaîne et crée l'épisode (`yt-<id>`) ;
2. **transcrit** l'audio sur son processeur — `large-v3-turbo` en `float32`, ~37 min pour 82 min ;
3. **extrait** les recos candidates, en brouillon ;
4. **prévient sur Matrix**, avec le lien de la page de validation.

La relecture reste humaine : la page de validation est le serveur de relecture
habituel, joignable **par le VPN seulement**, sur <http://10.8.0.1:8000>.

La publication — conversion des recos validées en œuvres et mentions, puis poussée
sur `main` — n'est pas encore automatisée : l'outil existant
(`migrate_reco_to_item_mention.py`) réécrit tout le corpus et ne doit pas être lancé.

## Où sont les choses

| Chemin sur venus | Rôle | Sauvegardé |
|---|---|---|
| `~/docker/reco/compose.yml` | lien vers `depot/deploy/venus/compose.yml` | oui |
| `~/docker/reco/.env` | clés (droits 600) | oui |
| `~/docker/reco/depot/` | clone du dépôt ; `tools/output/` y garde transcriptions et états | oui |
| `~/docker/reco/logs/tick-AAAA-MM.log` | journal des passages | oui |
| `~/.cache/reco/` | modèle Whisper (1,6 Go), caches yt-dlp — se retéléchargent | **non**, volontairement |

## Le `.env`

```
ANTHROPIC_API_KEY=…            # extraction ; sans elle, la chaîne s'arrête après la transcription et le signale
RECO_MATRIX_HOMESERVER=…       # les trois mêmes valeurs que les secrets GitHub de la veille RSS
RECO_MATRIX_TOKEN=…
RECO_MATRIX_ROOM=…
RECO_REVIEW_URL=http://10.8.0.1:8000
```

## Quand ça tourne

```
*/10 9-18 * * 0  /home/etienne/docker/reco/depot/deploy/venus/tick.sh
5    */2  * * *  /home/etienne/docker/reco/depot/deploy/venus/tick.sh
```

Le dimanche de 9 h à 18 h toutes les 10 minutes, sinon toutes les deux heures. Un
verrou (`flock`) empêche deux passages de se chevaucher. Interroger la chaîne plus
souvent n'apporterait rien, et exposerait venus au blocage « Sign in to confirm
you're not a bot » de YouTube.

## Opérations courantes

```sh
cd ~/docker/reco
tail -f logs/tick-$(date +%Y-%m).log                     # suivre un passage
docker compose ps                                        # la page de validation tourne-t-elle ?
depot/deploy/venus/tick.sh                               # forcer un passage
docker compose run --rm pipeline python traiter_nouveaux_episodes.py --source un-bon-moment a-extraire
docker compose build && docker compose up -d review      # après un changement de requirements.txt
```

## Premier passage

Au tout premier passage, la détection marque comme vues toutes les vidéos en ligne sans
rien signaler — sinon toute la chaîne serait rapportée comme nouvelle. Un épisode
reconnu mais absent du corpus est créé quand même.

## Retirer le service

Dans l'ordre de `_shared/docs/process-installation-app.md` : `docker compose down`
(sans `-v`), retirer les deux lignes de la crontab, la carte de Homepage, le moniteur
d'Uptime Kuma, puis marquer le service retiré dans `hosts.md`.
