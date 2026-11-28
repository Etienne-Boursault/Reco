# Pipeline de collecte — Reco

Pipeline **semi-automatique** qui alimente le site « Reco » (recensement des
œuvres recommandées dans des podcasts). Il produit des fichiers JSON conformes
au contrat de données (voir `../DATA_SCHEMA.md` et `../src/content.config.ts`),
écrits dans `src/content/episodes/<sourceId>/` et `src/content/recos/<sourceId>/`.

Le pipeline se compose de **4 étapes indépendantes et ré-exécutables** :

| # | Script | Rôle | Sortie |
|---|--------|------|--------|
| 1 | `fetch_episodes.py` | Lit le flux RSS Acast de la source | `src/content/episodes/<sourceId>/*.json` |
| 2 | `transcribe.py` | Télécharge l'audio + transcrit (Whisper local) | `tools/output/transcripts/<sourceId>/<guid>.txt` + maj `transcriptStatus` |
| 3 | `extract_recos.py` | Extrait les recos via l'API Anthropic | `src/content/recos/<sourceId>/*.json` |
| 4 | `run_pipeline.py` | Orchestrateur CLI des 3 étapes | — |

---

## Prérequis système

- **Python 3.12**
- **ffmpeg** dans le `PATH` (requis par faster-whisper et yt-dlp).
  Vérifier : `ffmpeg -version`

## Installation (venv + pip)

Depuis le dossier `tools/`, sous **PowerShell (Windows)** :

```powershell
cd tools
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

> macOS / Linux : `source .venv/bin/activate` au lieu du script `.ps1`.

> Première transcription : faster-whisper télécharge le modèle Whisper choisi
> (quelques centaines de Mo pour `small`/`medium`).

## Configuration

L'étape 3 (extraction des recos) appelle l'API Anthropic et nécessite une clé :

```powershell
Copy-Item .env.example .env
# puis éditer .env et renseigner ANTHROPIC_API_KEY
```

La clé peut aussi être fournie via la variable d'environnement
`ANTHROPIC_API_KEY` directement dans le shell.

---

## Utilisation

### Lanceur autonome (recommandé)

```powershell
.\run_all.ps1                    # tout, tous les épisodes (reprend où il s'arrête)
.\run_all.ps1 -Limit 3           # validation rapide sur 3 épisodes
.\run_all.ps1 -Batch             # extraction via Batch API (-50 % de coût)
.\run_all.ps1 -Steps "fetch,transcribe"   # sans clé API
```

Le lanceur crée le venv, installe les dépendances, et saute proprement
l'extraction si `ANTHROPIC_API_KEY` est absente de `.env`.

### Tout le pipeline (orchestrateur)

```powershell
python run_pipeline.py --source un-bon-moment
```

Options utiles :

```powershell
# Limiter aux 5 épisodes les plus récents
python run_pipeline.py --source un-bon-moment --limit 5

# N'exécuter que certaines étapes
python run_pipeline.py --source un-bon-moment --steps fetch,transcribe

# Extraction « à blanc » (aucun appel API, aucune écriture)
python run_pipeline.py --source un-bon-moment --steps extract --dry-run

# Modèle de transcription Whisper plus précis (plus lent)
python run_pipeline.py --source un-bon-moment --whisper-model medium

# Modèle d'extraction LLM (défaut: claude-sonnet-4-6) + Batch API (-50 %)
python run_pipeline.py --source un-bon-moment --extract-model claude-haiku-4-5 --batch
```

### Étape par étape

```powershell
# 1) Récupérer les épisodes
python fetch_episodes.py --source un-bon-moment [--limit N]

# 2) Transcrire (un épisode, ou tous)
python transcribe.py --source un-bon-moment --guid <GUID>
python transcribe.py --source un-bon-moment --all --limit 3 --model small
python transcribe.py --source un-bon-moment --guid <GUID> --force   # ignore le cache

# 3) Extraire les recos (modèle par défaut : claude-sonnet-4-6)
python extract_recos.py --source un-bon-moment --guid <GUID>
python extract_recos.py --source un-bon-moment --all --limit 3
python extract_recos.py --source un-bon-moment --all --batch        # Batch API (-50 %)
python extract_recos.py --source un-bon-moment --all --model claude-haiku-4-5
python extract_recos.py --source un-bon-moment --guid <GUID> --dry-run
```

Le `<GUID>` d'un épisode est le champ `"guid"` de son fichier JSON dans
`src/content/episodes/<sourceId>/`.

### Sous le capot : commande Whisper / ffmpeg

La transcription utilise **faster-whisper** (implémentation CTranslate2 de
Whisper), pas la CLI `whisper`. Le modèle tourne sur **CPU en `int8`** par
défaut (rapide et léger). En interne, faster-whisper appelle **ffmpeg** pour
décoder l'audio — c'est pourquoi ffmpeg doit être dans le `PATH`.

Équivalent conceptuel en ligne de commande (pour information) :

```bash
# openai-whisper CLI (NON utilisé ici, juste à titre indicatif) :
whisper episode.mp3 --model small --language fr --output_format txt
```

Le téléchargement audio YouTube (quand l'épisode n'a qu'une `youtubeUrl`)
passe par **yt-dlp** + extraction mp3 via ffmpeg.

---

## Flux semi-automatique (extraction → relecture → validation)

1. **Collecte automatique** : `run_pipeline.py` produit des épisodes
   (`transcriptStatus: "auto"`) et des recos en **brouillon**
   (`status: "draft"`). L'IA n'invente rien : un champ incertain est omis.
2. **Relecture humaine** : un humain ouvre les fichiers
   `src/content/recos/<sourceId>/*.json`, corrige titre/créateur/type/année,
   ajuste la citation, supprime les faux positifs.
3. **Validation** : passer manuellement `"status": "draft"` →
   `"status": "validated"` (et, pour un épisode relu, `transcriptStatus`
   `"auto"` → `"validated"`). Seul le site décide d'afficher ou non les
   brouillons ; la validation est le signal « relu par un humain ».
4. **Liens** : le pipeline laisse toujours `links: []`. Le site génère des
   liens de recherche **éthiques** à partir de `type` + `title` + `creator`
   (jamais Amazon ni groupe Bolloré — cf. `DATA_SCHEMA.md`).

Les étapes sont **idempotentes** : relancer `fetch` ne réécrit pas un épisode
inchangé et ne régresse pas un `transcriptStatus`. `extract` déduplique les
recos déjà écrites (par épisode + titre + créateur), donc une ré-exécution
n'ajoute pas de doublons.

---

## Relance des sorties annoncées (R4 B, 27/11/2026)

Une reco peut porter `releaseDate` (voir `../DATA_SCHEMA.md`) : la chaîne relance chaque
jour, de la sortie à J+30, la recherche de liens. Modules :

- `date_sortie.py` : le validateur de la date, la fenêtre de relance et les types servis (pur).
- `review_edit_sortie.py` : la saisie de la date dans « Corriger », avec ses deux gardes.
  `year` suit la date quand il en venait et que la date change d'année, mais reste quand la date est retirée (PR #227) ; un type qui n'est plus servi fait retirer la date
  (« date de sortie retirée : type non servi »).
- `branche_de_contenu.py` : commit et poussée dans un dossier à part, sans toucher au clone vivant.
- `sorties_plan.py` : le choix des recos du jour et les messages 🗓️ ⏳ ⚠️ (pur).
- `sorties_propositions.py` : une PR de liens attend-elle encore ? (adresses sur `origin/main`, état de la PR
  par l'API GitHub, sinon la branche ; PR #227).
- `sorties_annoncees.py` : l'étape, appelée par `deploy/venus/tick.sh` ; `--apercu`
  n'écrit ni n'envoie rien et ne fait pas de `git fetch`. Variables et exploitation : `../deploy/venus/README.md`.

Limites de la V1 : seuls `album`, `musique`, `livre` et `jeu` sont servis (les films et
les séries attendent), et la relance ne suit ni l'œuvre (`year`, alias), ni les recos
sœurs de la même œuvre, ni les playlists de l'épisode.

---

## Tableau de bord `/bord` (R2 B du 27/11/2026, TB-1 C du 28/11/2026)

Une page du serveur de relecture, liée depuis son accueil. Ce qu'elle montre et son
exploitation : `../deploy/venus/README.md`. Modules :

- `review_routes_bord.py` : `GET /bord`, `POST /bord/reseau` (JSON `{kind, message}` pour le
  script de la page, sinon redirection 303 vers `/bord`) et `GET /polices/<nom>` (liste fixe).
- `bord_rendu.py`, `bord_rendu_blocs.py` : le rendu (pur) ; `review_bord.css` et
  `bord_client.js`, recopiés en ligne (la CSP n'admet que du style et du script en ligne).
- `bord_afaire.py` : la liste « À faire d'abord » (pure), que reprendra le rappel du dimanche (PR 4).
- `bord_chaine.py` : l'épisode en cours, ses étapes et les passages de `tick.sh`
  (`passages.jsonl`).
- `bord_reseaux.py` : les cases des réseaux (`reseaux.json`), pour les 3 derniers publiés.
- `bord_distant.py` : l'audience du site, lue par `GET /api/bord` avec `RECO_AUDIENCE_KEY` ;
  la page ne lit que le cache `distant.json`, `python tools/bord_distant.py rafraichir` le
  relit (lancé détaché par la page quand il a 10 min, sa sortie ajoutée à `distant.log`,
  remis à zéro au-delà de 200 Ko).
- `bord_rendu_audience.py` : la colonne Audience (pure) ; `bord_rendu_blocs.bloc_signalements`
  et `bord_afaire.lignes_signalements` lisent les signalements dans le même état.
- `bord_github.py` : les PR ouvertes et fusionnées, la CI de `main` et le dernier déploiement,
  lus par l'API publique de GitHub (jeton `RECO_GITHUB_TOKEN` facultatif) dans le même cache
  `distant.json` et sous le même verrou que l'audience.
- `bord_systeme.py` : coûts et modèles (télémétrie locale) et image de la chaîne (`compose.yml`).
- `bord_contenu.py` : sorties à venir, graphies apprises et liens morts, lus sur le disque.
- `bord_rendu_systeme.py` : les blocs « Santé et versions », « Coûts et modèles », « Sorties à
  venir », « Liens morts » et « Graphies apprises » (purs).
- `review_polices/` : Bebas Neue et Inter en WOFF2, copiées de `@fontsource`, licence OFL.

**Ce que dit « inconnu »** (tranches 3a à 3d-2, 28/11/2026) : la source n'a pas pu être lue
(pas encore lue, en panne, forme inattendue, rapport absent). Ce n'est jamais « aucun », « 0 $ »
ni « verte » : un « aucun » est une vraie mesure (la liste lue est vide). Sur la page,
une ligne « inconnu » de « À faire d'abord » est grisée et ne compte pas.

| Bloc | Source | Fraîcheur |
|---|---|---|
| Santé et versions | `bord_github` : CI de `main`, dernier déploiement ; image selon `compose.yml` | cache `distant.json`, relu en arrière-plan au-delà de 10 min ; l'âge est affiché, « Périmé » au-delà de 20 min ; pannes de la CI et du déploiement, jeton refusé dits |
| Coûts et modèles | `bord_systeme` : 7 derniers jours et 7 d'avant, par modèle ; modèles d'extraction et de secours | à chaque affichage (disque local) |
| Sorties à venir | `bord_contenu` : recos validées dont `releaseDate` tombe dans les 30 jours avant ou après aujourd'hui ; `jours <= 0` : « déjà sortie », puis « en relance », « pas de relance » ou « relance : inconnu » selon le registre | à chaque affichage ; les à venir d'abord (la plus proche en tête), puis les passées (la plus récente en tête), 10 au plus, puis « + N autres » |
| Graphies apprises | `bord_contenu` : registre `tools/output/graphies/registre.json`, les 5 plus vues | à chaque affichage |
| Liens morts | `bord_contenu` : résumé `tools/output/bord/liens.json`, écrit par `verifier_liens.py externes` (contrôle du lundi) | « ancien » au-delà de 8 jours ; « inconnu » avant le premier contrôle ; 10 liens au plus, puis « + N autres » |

Une adresse devient un lien seulement si elle commence par `http://` ou `https://` (liens morts)
ou si c'est du `https` vers `github.com` (PR, CI, déploiement) ; sinon elle reste du texte
échappé. Les lignes de « À faire d'abord » : `publication` (chaque épisode récent se rapproche de sa
branche `contenu/<slug>` : « fusionner la PR de S6·E12 » si elle est ouverte, rien si elle est fusionnée,
« ouvrir puis fusionner la PR de S6·E12 » avec le lien de comparaison si la branche est poussée sans PR,
comme sur venus sans jeton GitHub, et « publication de S6·E12 : inconnu » (grisée) si les PR
fusionnées n'ont pas été lues ; toute autre PR `contenu/*` ouverte, faite à la main ou d'un épisode plus
ancien, est une tâche, « fusionner la PR #N : titre », car une PR ouverte est à fusionner ou à fermer ;
sans GitHub lisible, l'état de la chaîne ; sans état de la chaîne, les PR ouvertes se listent et
« publication des épisodes : inconnu » est grisée), `sorties` (PR ouvertes de sorties `contenu/sorties-*` ; les
relances partent seules, rien à faire pour Étienne : décision du 28/11/2026) et `liens` (nombre
de liens morts du dernier rapport ; au-delà de 8 jours, une ligne grisée « rapport ancien » qui ne compte
pas). L'étape « Publié » de la chaîne se lit aussi sur la PR fusionnée (sa date de fusion).

Les PR fusionnées s'accumulent d'une lecture à l'autre (par branche, la date de fusion la plus
récente, 200 au plus) : la fenêtre de GitHub ne compte que les 30 PR fermées les plus récentes, et une
panne de cet appel garde la liste d'avant. Limite connue : une branche `contenu/<slug>` réutilisée pour
un nouvel épisode est masquée par sa PR fusionnée d'avant (même branche, donc « fusionné ») ; rien n'est
codé contre cela, la chaîne ne réutilise pas de branche.

Les états vivent sous `tools/output/bord/` (`RECO_BORD_DIR` pour les essais), hors de Git.

---

## Limites & risques connus

- **Coût API** : l'extraction appelle le modèle (défaut `claude-sonnet-4-6`) une
  fois par *chunk* de transcription (~24 000 caractères). Un épisode long =
  plusieurs appels. Leviers pour réduire le coût : `--batch` (Message Batches
  API, **−50 %**), un modèle moins cher via `--model`/`--extract-model` (ex.
  `claude-haiku-4-5`), et `--limit`/`--dry-run` pour valider avant. Les
  transcriptions longues sont découpées (chunking) pour rester dans le contexte.
- **Durée de transcription** : Whisper en CPU est lent (plusieurs minutes par
  épisode, davantage avec `medium`/`large`). Un GPU CUDA accélère fortement
  (adapter `device="cuda"` dans `transcribe.py`).
- **YouTube** : si un épisode n'a qu'une `youtubeUrl`, yt-dlp télécharge l'audio
  pour le transcrire. Les **sous-titres YouTube ne sont pas utilisés**
  (souvent absents/auto-générés peu fiables) — on transcrit l'audio. yt-dlp peut
  casser si YouTube change son site (mettre à jour `yt-dlp`).
- **Qualité d'extraction** : le LLM peut manquer des recos implicites ou en
  proposer de douteuses. D'où l'étape de **relecture humaine** obligatoire avant
  `validated`. Les `year`, `creator`, `timestamp` doivent être vérifiés.
- **Numérotation des recos** : l'`id` (`<prefixe>-NNNN`) est attribué de façon
  incrémentale par source. Supprimer manuellement des fichiers peut créer des
  trous (sans conséquence pour le site).
```
