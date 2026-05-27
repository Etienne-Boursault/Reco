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
