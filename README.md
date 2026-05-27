# Reco — site duplicable de recommandations de podcasts

> Pipeline et site statique qui catalogue les œuvres recommandées dans des
> podcasts. **Première source** : *Un Bon Moment* (Kyan Khojandi & Navo).
> **Duplicable** : un podcast = une « source » → ajouter une source, c'est
> ajouter un JSON et relancer le pipeline.

## Sommaire

1. [Aperçu](#aperçu)
2. [Architecture (Clean / SOLID)](#architecture-clean--solid)
3. [Démarrage rapide](#démarrage-rapide)
4. [Workflow de bout en bout](#workflow-de-bout-en-bout)
5. [Ajouter un nouveau podcast](#ajouter-un-nouveau-podcast)
6. [Pipeline détaillé](#pipeline-détaillé)
7. [Outils de relecture](#outils-de-relecture)
8. [Configuration & secrets](#configuration--secrets)
9. [Conventions éditoriales](#conventions-éditoriales)
10. [Carte des fichiers](#carte-des-fichiers)
11. [Améliorations futures](#améliorations-futures)

---

## Aperçu

```
Flux RSS Acast ─┐
                │
                ├─► Transcription (Whisper, CPU ou GPU/CUDA) ─► Texte + timecodes
Chaîne YouTube ─┤      (audio = vidéo YT si elle existe, sinon Acast)
                │
                └─► Matching épisode RSS ↔ vidéo YT (similarité titre + OCR
                       miniature pour les anciens épisodes sans S/E)
                                │
                                ▼
                     Extraction LLM (Anthropic Sonnet + OpenAI gpt-4o-mini)
                          → ⭐ recos confirmées par 2 LLMs en tête de
                             liste pour la relecture humaine
                                │
                                ▼
                     Relecture humaine (review_server.py)
                          → status: draft → validated
                                │
                                ▼
                     Site Astro statique
                          /<source-id>/                catalogue public
                          /<source-id>/verifier        outil de relecture
```

**Pile technique** : Astro 5 (site statique) · TypeScript + Zod (schéma de
données) · Python 3.12 (pipeline) · faster-whisper / whisper.cpp · Anthropic
+ OpenAI SDKs · yt-dlp · feedparser.

---

## Architecture (Clean / SOLID)

Le code suit une **architecture en couches** : domaine métier au centre,
use cases qui orchestrent, adaptateurs aux frontières. Les abstractions
vivent dans [`tools/domain.py`](tools/domain.py).

```
┌───────────────────── Entry points (CLI scripts) ─────────────────────┐
│  fetch_episodes.py · transcribe.py · match_youtube.py ·              │
│  extract_recos.py · ocr_thumbnails.py · rematch_with_ocr.py          │
│  review_server.py (UI) · run_pipeline.py (orchestrateur)             │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────────┐
│                       Use cases (logique métier)                    │
│   Chaque script CLI au-dessus implémente UN use case clair.         │
│   Dépend uniquement des Protocols définis dans domain.py.           │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────────┐
│                Ports (Protocols) — tools/domain.py                  │
│  EpisodeRepository · RecoRepository · TranscriptStore               │
│  RSSClient · YouTubeClient · TranscriberEngine · LLMExtractor       │
│  VisionOCR                                                          │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────────┐
│                Adaptateurs (implémentations concrètes)              │
│  JSON filesystem (common.py) · feedparser (fetch_episodes)          │
│  yt-dlp (match_youtube/transcribe) · whisper.cpp + faster-whisper   │
│  (transcribe) · Anthropic & OpenAI SDKs (extract_recos,             │
│  ocr_thumbnails) · requests (HTTP)                                  │
└─────────────────────────────────────────────────────────────────────┘
```

### Comment chaque principe SOLID est appliqué

| Principe | Application |
|---|---|
| **S**ingle Responsibility | Un fichier de `tools/` = un use case unique. `common.py` ne fait QUE la persistence JSON + chemins. `domain.py` ne fait QUE déclarer les contrats. |
| **O**pen/Closed | Ajouter une nouvelle source = créer un fichier `src/content/sources/<id>.json`. Aucune modification du code requise. Ajouter un nouveau LLM = nouvelle implémentation de `LLMExtractor` + flag `--provider`. |
| **L**iskov Substitution | Les ports (`Protocol`) garantissent qu'on peut remplacer une implémentation (ex. `whisper.cpp` ou `faster-whisper` derrière `TranscriberEngine`) sans toucher au reste. |
| **I**nterface Segregation | Pas d'interface fourre-tout : `EpisodeRepository` ne sait rien des recos, `TranscriptStore` ne sait rien de YouTube, etc. |
| **D**ependency Inversion | Les use cases reçoivent leurs dépendances en paramètres ; aucun n'instancie directement Anthropic ou yt-dlp. La composition se fait dans le `main()` de chaque script. |

---

## Démarrage rapide

### Site (statique)

```bash
npm install
npm run dev      # http://localhost:4321
npm run build    # → dist/
```

### Pipeline Python

```bash
cd tools
python -m venv .venv
.venv/Scripts/activate            # Windows (Linux/Mac : source .venv/bin/activate)
pip install -r requirements.txt
```

Variables d'environnement (créer `.env` à la racine) :

```dotenv
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
```

---

## Workflow de bout en bout

```bash
# 1) Ingestion : récupérer les épisodes du flux RSS Acast
python tools/fetch_episodes.py --source un-bon-moment

# 2) Matching YouTube : associer chaque épisode RSS à sa vidéo YT complète
#    (filtre <30 min activé → ignore les extraits, jeux, blindtests)
python tools/match_youtube.py --source un-bon-moment

# 3) OCR de validation : lit le numéro affiché sur la miniature des anciens
#    épisodes (sans pattern S/E dans le titre) via Anthropic Vision Haiku
python tools/ocr_thumbnails.py --source un-bon-moment
# Ou re-match forcé + validation OCR (extraits → vidéos complètes) :
python tools/rematch_with_ocr.py --source un-bon-moment

# 4) Transcription (préférer l'audio YouTube pour aligner les timecodes)
python tools/transcribe.py --source un-bon-moment --all --youtube

# 5) Extraction LLM cross-validée (Anthropic puis OpenAI sur le même
#    transcript → champ `extractors` rempli avec les noms de modèles)
python tools/extract_recos.py --source un-bon-moment --all --provider anthropic
python tools/extract_recos.py --source un-bon-moment --all --provider openai

# 6) Relecture humaine
python tools/review_server.py --source un-bon-moment
# → http://localhost:8000 : galerie de miniatures, clic = page de relecture
#   avec lecteur YT embarqué top-right + contexte ±3-4 phrases du transcript

# 7) Build du site public
npm run build
```

L'orchestrateur `run_pipeline.py` enchaîne fetch → transcribe → extract en
un seul appel quand on veut tout faire d'un coup.

---

## Ajouter un nouveau podcast

### Étape 1 — fichier source

Créer `src/content/sources/mon-podcast.json` :

```json
{
  "id": "mon-podcast",
  "title": "Mon Podcast",
  "description": "Ce que recommandent les invités",
  "rssUrl": "https://feeds.example.com/mon-podcast",
  "youtubeChannel": "https://www.youtube.com/@MaChaine",
  "website": "https://monpodcast.fr",
  "hosts": ["Hôte 1", "Hôte 2"],
  "theme": {
    "accent": "#ff6b35",
    "bg": "#1a1a1f",
    "text": "#e8e8e8"
  }
}
```

### Étape 2 — pipeline

```bash
python tools/fetch_episodes.py --source mon-podcast
python tools/match_youtube.py  --source mon-podcast
python tools/transcribe.py     --source mon-podcast --all --youtube
python tools/extract_recos.py  --source mon-podcast --all --provider anthropic
python tools/extract_recos.py  --source mon-podcast --all --provider openai
python tools/review_server.py  --source mon-podcast
```

C'est tout. Le site Astro consomme la collection multi-source — la route
`/<source-id>/` est générée automatiquement par `getStaticPaths`.

---

## Pipeline détaillé

### 1. Fetch épisodes RSS — `fetch_episodes.py`

- `feedparser` (pas d'authentification, juste un User-Agent).
- Pour chaque entrée RSS : `guid`, `title`, `audioUrl`, `audioDuration`,
  `publishedAt`. Détection de saison/numéro depuis le titre quand présent
  (regex `S\d+-E\d+`).
- Écriture **idempotente** dans `src/content/episodes/<source-id>/<file>.json`
  via `write_json_if_changed`.

### 2. Match YouTube — `match_youtube.py`

- `yt-dlp` en mode `extract_flat` liste les vidéos de la chaîne (titre +
  durée + ID).
- **Filtre `<30 min`** activé : un épisode du podcast fait toujours ≥ 30 min ;
  les vidéos plus courtes sont des extraits/jeux/blindtests et sont écartées
  du matching. *(Ajouté après que des extraits aient pollué les premiers
  matches.)*
- Matching par **similarité de titre** (`SequenceMatcher` après
  normalisation Unicode + suppression accents/ponct/casse).
- Extraction de saison/numéro depuis le titre YT si pattern `Sx-Ex`.

### 3. OCR de validation — `ocr_thumbnails.py` / `rematch_with_ocr.py`

Pour les épisodes anciens (titres « avec X » sans `Sx-Ex`), la chaîne
affiche souvent « ÉPISODE NN » sur la miniature. On utilise **Anthropic
Haiku Vision** (modèle peu coûteux) pour lire ce numéro et :

- soit le compléter dans le JSON (`ocr_thumbnails.py`),
- soit **valider** un match candidat en comparant l'OCR au numéro attendu
  (`rematch_with_ocr.py`). N'écrit le lien que si l'OCR confirme.

### 4. Transcription — `transcribe.py`

Deux moteurs interchangeables (port `TranscriberEngine`) :

- **`faster-whisper`** (CPU ou CUDA). Choix par défaut pour les machines
  sans GPU. Modèle `small` = meilleur ratio qualité/coût.
- **`whisper.cpp`** (CUDA) — pour les vieux GPU Nvidia incompatibles avec
  les wheels de `ctranslate2` (ex. Maxwell GTX 950M). Compilé avec
  `-DCMAKE_CUDA_ARCHITECTURES=50`.

**Source audio** : préférer la **vidéo YouTube** (`--youtube`) — les
timecodes s'alignent alors parfaitement avec le lien de relecture
`?t=NNNs`. Repli : audio Acast (avec User-Agent) quand aucune vidéo YT
longue n'existe.

Distribution multi-machine possible : `make_dispatch.py` + un worker
portable lancé en SSH (`rebalance_watcher.py`, `retranscribe_acast_gpu.sh`).

### 5. Extraction LLM cross-validée — `extract_recos.py`

- **Cross-LLM** : on fait tourner Anthropic Sonnet **puis** OpenAI
  gpt-4o-mini sur le même transcript, en upsert (clé = `episodeGuid` +
  titre normalisé).
- Champ `extractors` sur chaque reco : `["anthropic"]`, `["openai"]`, ou
  `["anthropic","openai"]` (= ⭐ confirmée par 2 LLMs).
- Pour des transcripts longs : découpage en chunks avec overlap.
- Anthropic Batch API supporté (`--batch`, −50 % coût).

### 6. Relecture humaine — `review_server.py`

Serveur HTTP local (stdlib uniquement, pas de dépendance UI).

- Galerie de miniatures, **un épisode = une vignette à sa position
  chronologique** (par saison + numéro).
- États visuels :
  - 🟢 normal (recos en attente de validation)
  - ⏳ filigrane « transcription en cours… » (pas encore de transcript)
  - 🟠 « 0 reco » (transcript présent mais extraction vide)
  - opaque/grisé (toutes les recos validated)
- Page d'épisode :
  - **Lecteur YT embarqué en haut-droite** (sticky, `target="ytplayer"`).
  - Pour chaque reco : timecode cliquable, contexte ±3-4 phrases du
    transcript (ligne cible en jaune), candidats `recommendedBy` (hôtes +
    invité déduit du titre + champ libre).
  - Tri : drafts d'abord, ⭐ confirmées par 2 LLMs en tête de la tranche
    draft.

---

## Outils de relecture

### `review_server.py` — relecture interactive (port 8000)

Recommandé pour la phase de validation. Écrit directement dans les JSON.

### `verifier.astro` — page statique publique-friendly

Route Astro `/<source-id>/verifier` — générée au build, utilisable sans
serveur Python. Plus dépouillée que `review_server.py`.

### `inventory_md.py` — tableau de bord

Génère `docs/inventaire-<source>.md` : numéro, titre, durées, lien YT,
nb recos, état transcription/extraction/miniature. Utile pour voir d'un
coup d'œil ce qui manque.

---

## Configuration & secrets

Dans `.env` à la racine (NE PAS committer) :

```dotenv
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
```

Les SDK lisent ces variables au démarrage.

Pour la distribution multi-machine :
- Clé SSH dédiée : `~/.ssh/reco_laptop` (pubkey installée dans
  `~/.ssh/authorized_keys` du portable).
- File server du main : `python -m http.server 8001 --bind <IP-LAN>`.
- mDNS : le portable est résolu via `llm.local` (fallback IP en dur si
  l'agent SSH ne route pas).

---

## Conventions éditoriales

- **Liens éthiques** : pour les recos, on **évite Amazon et le groupe
  Bolloré** ; on privilégie librairies indépendantes, Bandcamp, Qobuz,
  JustWatch (voir `tools/extract_recos.py` — prompt + post-processing).
- **Recommandé par** : pas de diarisation auto (trop lourd CPU sans GPU
  performant). Validation manuelle dans `review_server.py` (hôtes + invité
  déduit du titre + champ libre).
- **Recos confirmées** (`extractors ≥ 2`) : signal de qualité fort,
  remontées en tête de la file de relecture.

---

## Carte des fichiers

### Pipeline (`tools/`)

| Fichier | Responsabilité (Single Responsibility) |
|---|---|
| `domain.py` | Entités (`Episode`, `Reco`, `Source`, `TranscriptSegment`) + ports (Protocols). Centre de l'architecture. |
| `common.py` | Adaptateur de persistence JSON (chemins, lecture/écriture idempotente), logger. |
| `fetch_episodes.py` | RSS → `Episode` + écriture. |
| `match_youtube.py` | Chaîne YT → assignation de `youtubeUrl/Title/Duration` aux épisodes. Filtre extraits <30 min. |
| `ocr_thumbnails.py` | Miniature YT → numéro d'épisode (Anthropic Vision Haiku). |
| `rematch_with_ocr.py` | Re-matching forcé + validation OCR du numéro attendu. |
| `transcribe.py` | Audio (YT via yt-dlp ou Acast) → transcription Whisper. |
| `extract_recos.py` | Transcript → recommandations (Anthropic et/ou OpenAI), upsert avec `extractors`. |
| `review_server.py` | Serveur HTTP local pour la relecture humaine. |
| `inventory_md.py` | Export `docs/inventaire-<source>.md` (tableau de bord). |
| `run_pipeline.py` | Orchestrateur séquentiel (fetch → match → transcribe → extract). |
| `compare_models.py` | Banc d'essai Whisper (tiny vs small vs medium). |
| `make_dispatch.py`, `rebalance_watcher.py` | Distribution multi-machine (main CPU + portable GPU via SSH/HTTP). |

### Site (`src/`)

| Chemin | Rôle |
|---|---|
| `content.config.ts` | Schéma Zod des collections (`sources`, `episodes`, `recos`). |
| `content/sources/<id>.json` | Une source = un podcast. |
| `content/episodes/<id>/*.json` | Un fichier = un épisode. |
| `content/recos/<id>/*.json` | Un fichier = une recommandation. |
| `pages/[source]/index.astro` | Catalogue public d'une source. |
| `pages/[source]/episode/[guid].astro` | Page d'un épisode. |
| `pages/[source]/verifier.astro` | Page statique de relecture (non publique). |

---

## Améliorations futures

- [ ] **Tests automatisés** : pour l'instant le pipeline est testé
      manuellement à chaque source. Ajouter des fixtures (1 mini-RSS + 1
      transcript factice) et tester chaque use case en isolation grâce aux
      ports.
- [ ] **CI** : `npm run build` + lint Python (ruff) sur les PR.
- [ ] **Use cases en classes** : actuellement la composition est faite dans
      les `main()` des scripts CLI. Une couche `usecases/<X>UseCase` pourrait
      isoler la logique pour la tester sans passer par argparse.
- [ ] **Diarisation** quand un GPU performant sera disponible (pour
      détecter automatiquement qui recommande quoi). Cf. WhisperX +
      pyannote.
- [ ] **Page publique** stylisée : pour l'instant `/<source>/verifier` est
      la route active de relecture. La page d'accueil publique
      (`pages/[source]/index.astro`) reste à styliser pour le grand public
      une fois la relecture avancée.
- [ ] **Site multi-sources index** : `/` qui liste les podcasts couverts.
- [ ] **Liens marchands** : `src/data/merchants.ts` — terminer la table
      des plateformes alternatives (Bandcamp, libraires, Qobuz, JustWatch)
      et le post-processing des liens proposés par les LLMs.

---

## Licence & crédits

Projet personnel. Données sources : flux RSS publics des podcasts.
Architecture pensée pour être dupliquée — fork bienvenu.
