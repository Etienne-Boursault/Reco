"""
extract_recos.py — Étape 3 du pipeline « Reco ».

Lit la transcription d'un épisode et en extrait les recommandations d'œuvres
via l'API Anthropic (SDK `anthropic`, modèle « claude-opus-4-7 »). Produit *un
fichier JSON par reco* dans `src/content/recos/<sourceId>/`, conforme au schéma.

RÈGLES MÉTIER (cf. DATA_SCHEMA.md) :
  - Ne RIEN inventer : un champ incertain est omis plutôt qu'halluciné.
  - `status` toujours « draft » (relecture humaine obligatoire ensuite).
  - `links` toujours vide ([]) : le site génère les liens éthiques.
  - `episodeGuid` = exactement le guid de l'épisode.
  - `type` ∈ enum {film, serie, livre, bd, musique, album, podcast, jeu,
    spectacle, lieu, autre}.

La transcription longue est découpée en *chunks* (par lignes/timestamps) pour
respecter les limites de contexte et de coût ; les recos de chaque chunk sont
agrégées puis dédupliquées.

La clé API est lue depuis la variable d'environnement ANTHROPIC_API_KEY
(via python-dotenv si un fichier .env est présent dans tools/).

Usage :
    python extract_recos.py --source un-bon-moment --guid <GUID>
    python extract_recos.py --source un-bon-moment --all [--limit N]
    python extract_recos.py --source un-bon-moment --guid <GUID> --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

Provider = Literal["anthropic", "openai"]

from dotenv import load_dotenv

from review_lock import ServerLockBusy, acquire_pipeline_lock

from extraction_history import (
    ASSUMED,
    ExtractionEntry,
    derive_extractors,
    from_dict as _entry_from_dict,
    merge_history,
    pick_display_state,
    to_dict as _entry_to_dict,
)
from common import (
    TOOLS_DIR,
    find_episode_by_guid,
    list_episode_files,
    load_source,
    log,
    make_anthropic_client,
    make_openai_client,
    normalize_text,
    read_json,
    reco_prefix,
    recos_dir_for,
    transcript_path_for,
    write_json_if_changed,
)

# Modèle d'extraction par défaut : Haiku 4.5 (basculé depuis Sonnet 4.6 le
# 2026-06-04 après étude comparative 4-LLM sur 11 ép). Trouve ~60% des recos
# de Sonnet pour 1/4 du coût, et catch en plus 40% que Sonnet rate (recall
# supérieur sur les recos subtiles). Surchargé par --model.
MODEL = "claude-haiku-4-5"
MAX_TOKENS = 8000
# Nombre approximatif de caractères par chunk (~ contexte raisonnable + marge coût).
CHUNK_CHARS = 24_000
# Recouvrement entre chunks pour ne pas couper une reco en deux à la jonction.
CHUNK_OVERLAP_CHARS = 500
# Intervalle de scrutation du statut d'un batch (Message Batches API).
BATCH_POLL_SECONDS = 20
# Sécurité : on n'attend pas plus de 4 h qu'un batch se termine.
BATCH_TIMEOUT_SECONDS = 4 * 3600
# Statuts terminaux possibles pour un batch (cf. doc API Message Batches).
TERMINAL_STATUSES = {"ended", "errored", "canceled", "expired"}

# Regex pré-compilées (chemins chauds des chunks/json).
_RE_NON_ALNUM = re.compile(r"[^a-z0-9 ]+")
_RE_SPACES = re.compile(r"\s+")
_RE_FENCE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL)
_RE_JSON_OBJ = re.compile(r"\{.*\}", re.DOTALL)
# L6 (revue 2026-07-19) : ANCRÉE en tête (^) — les fichiers recos sont nommés
# « {index:04d}.json », le numéro est donc TOUJOURS un préfixe. Sans ancre, un
# stem non numérique (« manual-note ») ou à chiffres internes (« take-2 »)
# fausserait le compteur d'index en captant un nombre qui n'est pas l'ID.
_RE_STEM_DIGITS = re.compile(r"^(\d+)")

VALID_TYPES = {
    "film", "serie", "livre", "bd", "musique", "album",
    "podcast", "jeu", "spectacle", "lieu", "artiste", "video", "autre",
}

SYSTEM_PROMPT = (
    "Tu es un assistant d'édition pour un site qui recense les œuvres "
    "recommandées dans des podcasts. Tu extrais UNIQUEMENT les recommandations "
    "réelles présentes dans la transcription fournie. Tu ne dois JAMAIS inventer "
    "d'information : si un champ est incertain ou absent, OMETS-le. Tu réponds "
    "exclusivement en JSON valide, sans texte autour."
)

# Instruction de tâche : appliquée à chaque chunk.
USER_TEMPLATE = """\
Voici un extrait de transcription d'un épisode du podcast « {podcast_title} ».
Les intervenants sont : {hosts}. Des invités peuvent aussi recommander des œuvres.

Extrais la liste des ŒUVRES RECOMMANDÉES (films, séries, livres, BD, musiques,
albums, podcasts, jeux, spectacles, lieux, artistes/personnes, vidéos YouTube…).
Une « reco » est une œuvre ou une personne qu'un intervenant conseille, vante,
ou invite à découvrir/suivre.

Types possibles dans le champ "type" :
  film, serie, livre, bd, musique, album, podcast, jeu, spectacle, lieu,
  artiste (humoriste, musicien, créateur — la personne elle-même est la reco),
  video (vidéo YouTube précise ou chaîne YT), autre.

IMPORTANT — la transcription est AUTOMATIQUE et imparfaite : les noms propres et
titres d'œuvres contiennent souvent des coquilles phonétiques (ex. « Mortal »
entendu pour la série « Mortel »). Quand tu reconnais une œuvre réelle malgré la
coquille, donne sa FORME OFFICIELLE correcte dans "title"/"creator".

FORMAT du podcast « Un Bon Moment » :
  - L'hôte demande RÉGULIÈREMENT aux invités leur(s) recommandation(s),
    typiquement avec une formule comme « est-ce que tu as une reco ? »,
    « ta reco ? », « qu'est-ce que tu nous recommandes ? », souvent vers la
    FIN de l'épisode. C'est LE moment-clé : capture TOUTES les œuvres citées
    juste après cette question — par l'invité ET par les hôtes en réaction
    (recos « croisées »).
  - 1 ou 2 recos supplémentaires peuvent apparaître AILLEURS dans l'épisode
    (œuvre citée en passant qu'un intervenant invite à découvrir / dont il
    fait l'éloge marqué).
  - Sois donc particulièrement VIGILANT à ce passage-tradition, ET balaye
    attentivement le reste pour ces recos plus discrètes.

Pour CHAQUE reco, renvoie un objet JSON avec ces clés (omets toute clé dont la
valeur est incertaine ou absente — NE DEVINE PAS) :
  - "title"        (obligatoire) : titre OFFICIEL de l'œuvre (orthographe corrigée).
  - "creator"      : auteur·rice / réalisateur·rice / artiste (nom correct).
  - "type"         (obligatoire) : un parmi {types}.
  - "year"         : année (entier).
  - "recommendedBy": qui recommande (nom de l'intervenant).
  - "quote"        : courte citation tirée de la transcription, VERBATIM (telle
                     quelle, SANS correction — c'est le texte d'origine).
  - "timestamp"    : horodatage « HH:MM:SS » du début de la reco (depuis les [..]).

Règles strictes :
  - N'INVENTE AUCUNE œuvre : seules celles réellement mentionnées comptent.
    Corriger l'orthographe d'une œuvre bien citée n'est PAS inventer ; mais
    n'ajoute jamais une œuvre absente du texte.
  - Si tu n'es pas certain qu'une œuvre existe, garde le titre tel qu'entendu.
  - Si aucune reco dans cet extrait, renvoie une liste vide.
  - "type" DOIT appartenir à l'ensemble autorisé, sinon utilise "autre".

Réponds avec un objet JSON de la forme : {{"recos": [ ... ]}} et RIEN d'autre.

--- TRANSCRIPTION (extrait) ---
{chunk}
--- FIN DE L'EXTRAIT ---
"""


# Alias historique : préserve la rétro-compat des tests qui importent _norm.
def _norm(s: str | None) -> str:
    """Alias compatibilité — utilise désormais `common.normalize_text`."""
    return normalize_text(s)


def _chunk_transcript(text: str, max_chars: int = CHUNK_CHARS,
                      overlap_chars: int = CHUNK_OVERLAP_CHARS) -> list[str]:
    """
    Découpe la transcription en morceaux d'au plus `max_chars`, en coupant sur
    des frontières de lignes (donc de segments horodatés) pour ne pas tronquer
    une phrase au milieu.

    Ajoute un recouvrement (`overlap_chars`) entre chunks consécutifs pour ne
    pas perdre une reco qui tomberait pile à la jonction. Le recouvrement
    n'est appliqué que si > 0 et que les chunks sont suffisamment grands pour
    le supporter.
    """
    lines = text.splitlines(keepends=True)
    chunks: list[str] = []
    current: list[str] = []
    size = 0
    for line in lines:
        if size + len(line) > max_chars and current:
            chunks.append("".join(current))
            # Démarre le chunk suivant avec un overlap : les dernières lignes
            # du chunk précédent dont la longueur cumulée approche overlap_chars.
            overlap_lines: list[str] = []
            ov_size = 0
            if overlap_chars > 0:
                for prev_line in reversed(current):
                    if ov_size + len(prev_line) > overlap_chars:
                        break
                    overlap_lines.insert(0, prev_line)
                    ov_size += len(prev_line)
            current = overlap_lines + [line]
            size = ov_size + len(line)
        else:
            current.append(line)
            size += len(line)
    if current:
        chunks.append("".join(current))
    return chunks or [""]


def _extract_json_block(raw: str) -> dict[str, Any]:
    """
    Extrait l'objet JSON de la réponse du modèle, tolérant à un éventuel
    encadrement (```json … ```), et le parse.
    """
    raw = raw.strip()
    # Retire un éventuel bloc de code Markdown.
    fence = _RE_FENCE.match(raw)
    if fence:
        raw = fence.group(1).strip()
    # Si du texte entoure le JSON, isole le premier objet { … }.
    if not raw.startswith("{"):
        m = _RE_JSON_OBJ.search(raw)
        if m:
            raw = m.group(0)
    return json.loads(raw)


def _normalize_reco(item: dict[str, Any]) -> dict[str, Any] | None:
    """
    Valide et normalise une reco brute renvoyée par le LLM. Renvoie None si
    inexploitable (pas de titre). Force les règles métier (status, links, type).
    """
    title = (item.get("title") or "").strip()
    if not title:
        return None

    rtype = (item.get("type") or "").strip().lower()
    if rtype not in VALID_TYPES:
        rtype = "autre"

    reco: dict[str, Any] = {"title": title, "types": [rtype]}

    # Champs optionnels : seulement s'ils sont présents et non vides.
    for key in ("creator", "recommendedBy", "quote", "timestamp"):
        val = item.get(key)
        if isinstance(val, str) and val.strip():
            reco[key] = val.strip()

    year = item.get("year")
    if isinstance(year, int):
        reco["year"] = year
    elif isinstance(year, str) and year.strip().isdigit():
        reco["year"] = int(year.strip())

    return reco


def _dedupe(recos: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Déduplique sur le titre normalisé (par épisode, même œuvre = une reco).

    On garde la version la plus 'riche' (avec créateur si possible) pour fusionner
    les variantes que le LLM peut produire dans deux chunks différents.
    """
    out_by_key: dict[str, dict[str, Any]] = {}
    for reco in recos:
        k = normalize_text(reco["title"])
        if k not in out_by_key:
            out_by_key[k] = reco
            continue
        # Fusionne : complète les champs manquants.
        existing = out_by_key[k]
        for fld in ("creator", "year", "recommendedBy", "quote", "timestamp"):
            if fld in reco and not existing.get(fld):
                existing[fld] = reco[fld]
        # Fusion des types : union dédupliquée, ordre stable.
        seen_t: set[str] = set()
        merged_types: list[str] = []
        for t in (existing.get("types") or []) + (reco.get("types") or []):
            if t and t not in seen_t:
                seen_t.add(t)
                merged_types.append(t)
        if merged_types:
            existing["types"] = merged_types
    return list(out_by_key.values())


def _request_params(model: str, podcast_title: str, hosts: str, chunk: str) -> dict[str, Any]:
    """Construit les paramètres d'un appel `messages` (réutilisé en sync et batch)."""
    prompt = USER_TEMPLATE.format(
        podcast_title=podcast_title,
        hosts=hosts,
        types=", ".join(sorted(VALID_TYPES)),
        chunk=chunk,
    )
    return {
        "model": model,
        "max_tokens": MAX_TOKENS,
        "system": SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": prompt}],
    }


def _parse_recos_from_content(content: Any) -> list[dict[str, Any]]:
    """Extrait la liste de recos brutes depuis les blocs de contenu d'un message."""
    raw = "".join(
        block.text for block in content if getattr(block, "type", "") == "text"
    )
    try:
        data = _extract_json_block(raw)
    except json.JSONDecodeError:
        log.warning("Réponse non-JSON ignorée pour un chunk.")
        return []
    return data.get("recos", []) if isinstance(data, dict) else []


# --- Adaptateurs LLM (dispatch sans duck-typing implicite) -----------------
class _AnthropicExtractor:
    """Petit adaptateur autour du SDK anthropic pour appels synchrones."""

    def __init__(self, client: Any) -> None:
        self.client = client

    def extract(self, model: str, podcast_title: str, hosts: str,
                chunk: str) -> list[dict[str, Any]]:
        params = _request_params(model, podcast_title, hosts, chunk)
        message = self.client.messages.create(**params)
        return _parse_recos_from_content(message.content)


class _OpenAIExtractor:
    """Adaptateur OpenAI Chat Completions (JSON object response_format)."""

    def __init__(self, client: Any) -> None:
        self.client = client

    def extract(self, model: str, podcast_title: str, hosts: str,
                chunk: str) -> list[dict[str, Any]]:
        prompt = USER_TEMPLATE.format(
            podcast_title=podcast_title, hosts=hosts,
            types=", ".join(sorted(VALID_TYPES)), chunk=chunk,
        )
        resp = self.client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
            max_tokens=MAX_TOKENS,
        )
        raw = resp.choices[0].message.content or ""
        try:
            data = _extract_json_block(raw)
        except json.JSONDecodeError:
            log.warning("Réponse non-JSON ignorée pour un chunk (OpenAI).")
            return []
        return data.get("recos", []) if isinstance(data, dict) else []


_EXTRACTOR_REGISTRY: dict[str, type] = {
    "anthropic": _AnthropicExtractor,
    "openai": _OpenAIExtractor,
}


def _make_extractor(client: Any, provider: Provider | None = None) -> Any:
    """Choisit l'adaptateur LLM, typé par `provider` (préféré) ou par classe client.

    Si `provider` est fourni, dispatch direct via le registre. Sinon, fallback
    rétro-compatible : on inspecte le module/classe du client pour décider.
    """
    if provider is not None:
        cls = _EXTRACTOR_REGISTRY.get(provider)
        if cls is None:
            raise ValueError(f"Provider LLM inconnu : {provider!r}")
        return cls(client)
    # Fallback : inspection du module pour identifier le SDK.
    module = type(client).__module__ or ""
    if module.startswith("openai") or hasattr(client, "chat"):
        return _OpenAIExtractor(client)
    return _AnthropicExtractor(client)


def _call_llm(client: Any, model: str, podcast_title: str, hosts: str,
              chunk: str, provider: Provider | None = None) -> list[dict[str, Any]]:
    """Dispatche vers l'adaptateur Anthropic ou OpenAI."""
    return _make_extractor(client, provider).extract(model, podcast_title, hosts, chunk)


# Conservés en alias pour la rétro-compat des tests historiques.
def _call_anthropic(client: Any, model: str, podcast_title: str, hosts: str,
                    chunk: str) -> list[dict[str, Any]]:
    return _AnthropicExtractor(client).extract(model, podcast_title, hosts, chunk)


def _call_openai(client: Any, model: str, podcast_title: str, hosts: str,
                 chunk: str) -> list[dict[str, Any]]:
    return _OpenAIExtractor(client).extract(model, podcast_title, hosts, chunk)


def _next_reco_index(source_id: str) -> int:
    """Calcule le prochain index de reco (numérotation continue par source)."""
    d = recos_dir_for(source_id)
    if not d.exists():
        return 1
    max_idx = 0
    for path in d.glob("*.json"):
        m = _RE_STEM_DIGITS.match(path.stem)
        if m:
            max_idx = max(max_idx, int(m.group(1)))
    return max_idx + 1


def _build_existing_index(source_id: str) -> dict[tuple[str, str], Path]:
    """Indexe les recos déjà écrites par (episodeGuid, titre_normalisé)."""
    target_dir = recos_dir_for(source_id)
    existing_map: dict[tuple[str, str], Path] = {}
    if not target_dir.exists():
        return existing_map
    for path in target_dir.glob("*.json"):
        try:
            r = read_json(path)
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        key = (r.get("episodeGuid", ""), normalize_text(r.get("title")))
        existing_map[key] = path
    return existing_map


class _RunIndex:
    """Index partagé pour un run multi-épisodes (M4, revue 2026-07-19).

    `_build_existing_index` et `_next_reco_index` relisent TOUS les fichiers
    recos de la source. Les appeler à chaque épisode d'un run ``--all``/``--batch``
    donne un coût en O(épisodes × recos) (≈ 3000 recos relues par épisode). On
    construit donc l'index existant et le compteur d'index UNE seule fois par
    run, puis on met l'état à jour au fil des écritures (`existing_map` reçoit
    les nouvelles recos, `next_index` avance).
    """

    __slots__ = ("existing_map", "next_index")

    def __init__(self, existing_map: dict[tuple[str, str], Path],
                 next_index: int) -> None:
        self.existing_map = existing_map
        self.next_index = next_index

    @classmethod
    def build(cls, source_id: str) -> "_RunIndex":
        return cls(_build_existing_index(source_id), _next_reco_index(source_id))


def new_run_index(source_id: str) -> _RunIndex:
    """Fabrique un index de run partagé (cf. `_RunIndex`).

    Exposé pour les orchestrateurs (run_pipeline) qui bouclent sur les épisodes
    et veulent éviter de relire tous les fichiers recos à chaque itération.
    """
    return _RunIndex.build(source_id)


def _now_iso() -> str:
    """ISO datetime UTC sans microsecondes (stable pour comparaisons)."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _build_entry(reco: dict[str, Any], provider: str,
                 transcript_source: str, transcript_model: str | None,
                 llm_model: str | None, worker: str | None,
                 at: str | None = None) -> ExtractionEntry:
    """Construit une `ExtractionEntry` à partir des paramètres d'extraction."""
    return ExtractionEntry(
        at=at or _now_iso(),
        transcriptModel=transcript_model or ASSUMED,
        transcriptSource=transcript_source if transcript_source in ("acast", "youtube") else "acast",  # type: ignore[arg-type]
        llmProvider=provider if provider in ("anthropic", "openai") else "anthropic",  # type: ignore[arg-type]
        llmModel=llm_model or ASSUMED,
        worker=worker or ASSUMED,
        timestamp_at_extraction=(reco.get("timestamp") or "00:00:00"),
    )


def _legacy_entry_for(existing: dict[str, Any], file_mtime_iso: str) -> ExtractionEntry:
    """Forge une entrée d'historique pour une reco antérieure au schéma history."""
    existing_extractors = existing.get("extractors") or ["anthropic"]
    legacy_provider = existing_extractors[0] if existing_extractors else "anthropic"
    return ExtractionEntry(
        at=file_mtime_iso,
        transcriptModel=ASSUMED,
        transcriptSource=existing.get("transcriptSource") or "acast",  # type: ignore[arg-type]
        llmProvider=legacy_provider,  # type: ignore[arg-type]
        llmModel=ASSUMED,
        worker=ASSUMED,
        timestamp_at_extraction=existing.get("timestamp") or "00:00:00",
    )


def _merge_reco(existing: dict[str, Any], new: dict[str, Any],
                provider: str,
                transcript_source: str = "acast",
                transcript_model: str | None = None,
                llm_model: str | None = None,
                worker: str | None = None,
                file_mtime_iso: str | None = None) -> dict[str, Any]:
    """Fusionne une nouvelle extraction dans une reco existante.

    Règles :
      - `extractionHistory` est mis à jour (dédup par signature, ordre par `at`).
      - `timestamp` / `transcriptSource` au top-level = derniers de l'entrée YT
        (ou de la plus récente si aucune YT).
      - `quote` n'est mis à jour QUE si la reco n'est pas `validated`.
      - `creator`, `year` complétés s'ils étaient vides.
      - `extractors` = dérivé de l'historique.
    """
    merged = dict(existing)
    existing_history_raw = existing.get("extractionHistory") or []
    history = [_entry_from_dict(e) for e in existing_history_raw]
    # Si pas d'historique, on backfille une entrée legacy AVANT le merge,
    # pour préserver la trace de l'extraction d'origine.
    if not history:
        history = [_legacy_entry_for(existing, file_mtime_iso or _now_iso())]

    new_entry = _build_entry(new, provider, transcript_source,
                             transcript_model, llm_model, worker)
    history = merge_history(history, new_entry)
    display = pick_display_state(history)

    merged["extractionHistory"] = [_entry_to_dict(e) for e in history]
    merged["extractors"] = derive_extractors(history)
    merged["timestamp"] = display["timestamp"]
    merged["transcriptSource"] = display["transcriptSource"]

    # On préserve la quote humaine si :
    #   - l'item a été validé (`status=validated`), OU
    #   - l'item a été qualifié de citation (`kind=citation`) — la quote a
    #     alors été choisie par l'humain comme représentative de la mention.
    is_human_locked = (
        existing.get("status") == "validated"
        or existing.get("kind") == "citation"
    )
    if not is_human_locked and new.get("quote"):
        merged["quote"] = new["quote"]
    for k in ("creator", "year"):
        if k in new and not existing.get(k):
            merged[k] = new[k]
    # Fusion des types : union dédupliquée, ordre stable (existants en tête).
    existing_types = existing.get("types") or []
    new_types = new.get("types") or []
    seen: set[str] = set()
    merged_types: list[str] = []
    for t in list(existing_types) + list(new_types):
        if t and t not in seen:
            seen.add(t)
            merged_types.append(t)
    if merged_types:
        merged["types"] = merged_types
    return merged


def _create_reco(source_id: str, guid: str, reco: dict[str, Any],
                 prefix: str, index: int, provider: str,
                 transcript_source: str = "acast",
                 transcript_model: str | None = None,
                 llm_model: str | None = None,
                 worker: str | None = None) -> dict[str, Any]:
    """Construit le dict d'une NOUVELLE reco (draft) avec historique initial.

    `transcript_source` indique d'où vient le timestamp (acast/youtube) pour
    permettre au review_server d'appliquer le bon offset YT au moment du clic.
    """
    full: dict[str, Any] = {
        "id": f"{prefix}-{index:04d}",
        "sourceId": source_id,
        "episodeGuid": guid,
        "title": reco["title"],
        "types": list(reco["types"]),
    }
    for key_name in ("creator", "year", "recommendedBy", "quote"):
        if key_name in reco:
            full[key_name] = reco[key_name]
    full["links"] = []
    full["status"] = "draft"

    entry = _build_entry(reco, provider, transcript_source,
                         transcript_model, llm_model, worker)
    history = [entry]
    full["extractionHistory"] = [_entry_to_dict(e) for e in history]
    full["extractors"] = derive_extractors(history)
    display = pick_display_state(history)
    full["timestamp"] = display["timestamp"]
    full["transcriptSource"] = display["transcriptSource"]
    return full


def _persist_recos(source_id: str, guid: str,
                   raw_recos: list[dict[str, Any]],
                   provider: str = "anthropic",
                   transcript_source: str = "acast",
                   transcript_model: str | None = None,
                   llm_model: str | None = None,
                   worker: str | None = None,
                   run_index: _RunIndex | None = None) -> int:
    """
    Normalise, déduplique et persiste les recos brutes d'un épisode en mode
    UPSERT (préserve le travail humain).

    `run_index` (M4) : index de run partagé. S'il est fourni, on NE relit PAS
    tous les fichiers recos (l'appelant l'a construit une fois pour tout le run)
    et on met son état à jour au fil des écritures. S'il est None, on le
    construit ici (chemin standalone — appel isolé sur un seul épisode).

    Renvoie le nombre de fichiers créés ou modifiés.
    """
    normalized = [r for r in (_normalize_reco(x) for x in raw_recos) if r]
    normalized = _dedupe(normalized)
    log.info("Épisode %s : %d reco(s) candidate(s) après normalisation.",
             guid, len(normalized))
    if not normalized:
        return 0

    if run_index is None:
        run_index = _RunIndex.build(source_id)
    existing_map = run_index.existing_map
    target_dir = recos_dir_for(source_id)
    prefix = reco_prefix(source_id)
    index = run_index.next_index
    new_count = 0
    upd_count = 0

    for reco in normalized:
        key = (guid, normalize_text(reco["title"]))

        # Le timestamp et donc la source côté YT/Acast viennent du transcript
        # courant — on l'injecte dans `reco` pour que merge/create soient
        # cohérents.
        reco["transcriptSource"] = transcript_source

        if key in existing_map:
            path = existing_map[key]
            existing = read_json(path)
            try:
                file_mtime_iso = datetime.fromtimestamp(
                    path.stat().st_mtime, tz=timezone.utc
                ).replace(microsecond=0).isoformat()
            except OSError:
                file_mtime_iso = _now_iso()
            merged = _merge_reco(existing, reco, provider,
                                 transcript_source=transcript_source,
                                 transcript_model=transcript_model,
                                 llm_model=llm_model,
                                 worker=worker,
                                 file_mtime_iso=file_mtime_iso)
            if write_json_if_changed(path, merged):
                upd_count += 1
                log.info("  ↻ MAJ %s — « %s » (extractors=%s)",
                         path.name, reco["title"], merged["extractors"])
            continue

        full = _create_reco(source_id, guid, reco, prefix, index, provider,
                            transcript_source=transcript_source,
                            transcript_model=transcript_model,
                            llm_model=llm_model,
                            worker=worker)
        path = target_dir / f"{index:04d}.json"
        if write_json_if_changed(path, full):
            new_count += 1
            log.info("  + NEW %s — « %s » (extractor=%s)",
                     path.name, reco["title"], provider)
        existing_map[key] = path
        index += 1

    # Propage le compteur avancé pour le prochain épisode du run (M4).
    run_index.next_index = index
    log.info("Épisode %s : %d nouvelle(s), %d mise(s) à jour.",
             guid, new_count, upd_count)
    return new_count + upd_count


def extract_for_episode(source_id: str, episode_path: Path, client: Any | None,
                        dry_run: bool, model: str = MODEL,
                        provider: str = "anthropic",
                        source: dict[str, Any] | None = None,
                        worker: str | None = None,
                        run_index: _RunIndex | None = None) -> int:
    """
    Extraction SYNCHRONE d'un épisode (1 appel API par chunk, à la suite).
    Si `dry_run`, n'appelle pas l'API et n'écrit rien (affiche seulement le plan).

    `source` peut être fourni par l'appelant pour éviter un rechargement à
    chaque épisode lorsqu'on traite une liste (boucle main).

    `run_index` (M4) : index de run partagé, à construire une fois par run
    multi-épisodes pour éviter de relire tous les fichiers recos à chaque
    épisode. Transmis tel quel à `_persist_recos`.
    """
    if source is None:
        source = load_source(source_id)
    episode = read_json(episode_path)
    guid = episode["guid"]
    transcript_path = transcript_path_for(source_id, guid)

    if not transcript_path.exists():
        log.warning("Pas de transcription pour %s (%s). Lance transcribe.py d'abord.",
                    guid, transcript_path.name)
        return 0

    text = transcript_path.read_text(encoding="utf-8")
    chunks = _chunk_transcript(text)
    podcast_title = source.get("title", source_id)
    hosts = ", ".join(source.get("hosts", [])) or "inconnus"

    log.info("Épisode %s : transcription de %d caractères -> %d chunk(s).",
             guid, len(text), len(chunks))

    if dry_run:
        log.info("[DRY-RUN] %d appel(s) API seraient effectués (modèle %s). "
                 "Aucune écriture.", len(chunks), model)
        return 0

    if client is None:
        raise RuntimeError("Client Anthropic non initialisé (clé API manquante ?).")

    raw_recos: list[dict[str, Any]] = []
    for i, chunk in enumerate(chunks, 1):
        log.info("  Chunk %d/%d…", i, len(chunks))
        raw_recos.extend(_call_llm(client, model, podcast_title, hosts, chunk,
                                   provider))  # type: ignore[arg-type]

    return _persist_recos(
        source_id, guid, raw_recos, provider,
        transcript_source=episode.get("transcriptSource") or "acast",
        transcript_model=episode.get("transcriptModel"),
        llm_model=model,
        worker=worker or os.environ.get("RECO_WORKER") or "main-cpu",
        run_index=run_index,
    )


# --- Batch helpers ---------------------------------------------------------
def _build_batch_requests(source_id: str, episode_paths: list[Path],
                          podcast_title: str, hosts: str,
                          model: str) -> tuple[list[dict[str, Any]],
                                               dict[str, str],
                                               list[str]]:
    """Prépare les requêtes batch.

    Renvoie (requests, custom_id → guid, liste des guids traitables).
    """
    requests: list[dict[str, Any]] = []
    cid_to_guid: dict[str, str] = {}
    guids: list[str] = []
    n = 0
    for path in episode_paths:
        guid = read_json(path)["guid"]
        transcript_path = transcript_path_for(source_id, guid)
        if not transcript_path.exists():
            log.warning("Pas de transcription pour %s — ignoré.", guid)
            continue
        chunks = _chunk_transcript(transcript_path.read_text(encoding="utf-8"))
        guids.append(guid)
        for chunk in chunks:
            cid = f"req-{n}"
            requests.append({
                "custom_id": cid,
                "params": _request_params(model, podcast_title, hosts, chunk),
            })
            cid_to_guid[cid] = guid
            n += 1
    return requests, cid_to_guid, guids


def _submit_batch(client: Any, requests: list[dict[str, Any]]) -> str:
    """Soumet le batch et renvoie son identifiant."""
    batch = client.messages.batches.create(requests=requests)
    log.info("Batch créé : %s. Traitement en cours…", batch.id)
    return batch.id


def _poll_batch_until_done(client: Any, batch_id: str,
                           poll_seconds: int,
                           timeout_seconds: int = BATCH_TIMEOUT_SECONDS) -> None:
    """Scrute le statut d'un batch jusqu'à un état terminal.

    Lève `TimeoutError` si le batch dépasse `timeout_seconds`.
    """
    deadline = time.time() + timeout_seconds
    while True:
        batch = client.messages.batches.retrieve(batch_id)
        status = batch.processing_status
        if status in TERMINAL_STATUSES:
            if status != "ended":
                log.warning("Batch %s terminé avec statut=%s", batch_id, status)
            return
        log.info("  … statut=%s", status)
        if time.time() > deadline:
            raise TimeoutError(
                f"Batch {batch_id} pas terminé après {timeout_seconds}s "
                f"(dernier statut: {status})."
            )
        time.sleep(poll_seconds)


def _collect_results(client: Any, batch_id: str,
                     cid_to_guid: dict[str, str],
                     guids: list[str]) -> dict[str, list[dict[str, Any]]]:
    """Récupère les résultats batch et regroupe les recos brutes par guid."""
    raw_by_guid: dict[str, list[dict[str, Any]]] = {g: [] for g in guids}
    errors = 0
    for entry in client.messages.batches.results(batch_id):
        guid = cid_to_guid.get(entry.custom_id)
        if guid is None:
            continue
        if entry.result.type == "succeeded":
            raw_by_guid[guid].extend(
                _parse_recos_from_content(entry.result.message.content)
            )
        else:
            errors += 1
            log.warning("  Requête %s en échec : %s",
                        entry.custom_id, entry.result.type)
    if errors:
        log.warning("%d requête(s) en échec dans le batch.", errors)
    return raw_by_guid


def extract_all_batch(source_id: str, episode_paths: list[Path], client: Any,
                      model: str = MODEL,
                      poll_seconds: int = BATCH_POLL_SECONDS,
                      provider: str = "anthropic",
                      worker: str | None = None) -> int:
    """
    Extraction par LOT via la Message Batches API (−50 % de coût, asynchrone).

    Toutes les requêtes (1 par chunk, tous épisodes confondus) sont soumises en
    un seul batch, puis on attend la fin du traitement et on écrit les recos par
    épisode.
    """
    source = load_source(source_id)
    podcast_title = source.get("title", source_id)
    hosts = ", ".join(source.get("hosts", [])) or "inconnus"

    requests, cid_to_guid, guids = _build_batch_requests(
        source_id, episode_paths, podcast_title, hosts, model
    )
    if not requests:
        log.warning("Aucun chunk à traiter (transcriptions manquantes ?).")
        return 0
    log.info("Batch : %d requête(s) sur %d épisode(s), modèle %s.",
             len(requests), len(guids), model)

    batch_id = _submit_batch(client, requests)
    _poll_batch_until_done(client, batch_id, poll_seconds)
    raw_by_guid = _collect_results(client, batch_id, cid_to_guid, guids)

    total = 0
    worker_resolved = worker or os.environ.get("RECO_WORKER") or "main-cpu"
    # M2 (revue 2026-07-19) : relire les épisodes par guid pour propager le VRAI
    # transcriptSource / transcriptModel (comme extract_for_episode). Hardcoder
    # "acast" corrompait les timecodes des épisodes transcrits depuis YouTube :
    # le review_server applique alors un yt_offset à un timestamp déjà calé sur
    # la vidéo → le lecteur saute au mauvais endroit.
    ep_by_guid: dict[str, dict] = {}
    for path in episode_paths:
        try:
            ep = read_json(path)
        except (OSError, ValueError):
            continue
        g = ep.get("guid")
        if g:
            ep_by_guid[g] = ep
    # M4 : index de run construit UNE fois (sinon relecture de tous les fichiers
    # recos par épisode).
    run_index = _RunIndex.build(source_id)
    for guid in guids:
        ep = ep_by_guid.get(guid, {})
        total += _persist_recos(
            source_id, guid, raw_by_guid[guid], provider,
            transcript_source=ep.get("transcriptSource") or "acast",
            transcript_model=ep.get("transcriptModel"),
            llm_model=model, worker=worker_resolved,
            run_index=run_index,
        )
    log.info("Batch terminé : %d nouvelle(s) reco(s) écrite(s) au total.", total)
    return total


def main() -> None:
    # Charge tools/.env si présent (clé API).
    load_dotenv(TOOLS_DIR / ".env")

    parser = argparse.ArgumentParser(
        description="Extrait les recommandations d'une transcription via l'API Anthropic."
    )
    parser.add_argument("--source", required=True, help="Identifiant de la source.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--guid", help="Guid de l'épisode à traiter.")
    group.add_argument("--all", action="store_true",
                       help="Traite tous les épisodes (transcrits) de la source.")
    parser.add_argument("--limit", type=int, default=None,
                        help="Avec --all : limite le nombre d'épisodes.")
    parser.add_argument("--model", default=MODEL,
                        help="Modèle LLM d'extraction (défaut: %(default)s).")
    parser.add_argument("--provider", choices=["anthropic", "openai"], default="anthropic",
                        help="Fournisseur LLM. OpenAI utile en repli si Anthropic est en panne.")
    parser.add_argument("--batch", action="store_true",
                        help="Utilise la Message Batches API (Anthropic uniquement).")
    parser.add_argument("--poll-interval", type=int, default=BATCH_POLL_SECONDS,
                        help="Batch : intervalle de scrutation en secondes (défaut: %(default)s).")
    parser.add_argument("--dry-run", action="store_true",
                        help="N'appelle pas l'API et n'écrit rien (plan seulement).")
    parser.add_argument("--worker", default=None,
                        help="Étiquette du worker (ex. main-cpu, portable-gpu). "
                             "Défaut: $RECO_WORKER ou main-cpu.")
    parser.add_argument("--force", action="store_true",
                        help="Ignore le verrou serveur (à tes risques : "
                             "écritures concurrentes possibles avec review_server).")
    args = parser.parse_args()

    # Coordination avec review_server : refuse de démarrer si le serveur
    # tourne (sauf --force). Cf. tools/review_lock.py.
    try:
        lock_ctx = acquire_pipeline_lock(force=args.force)
        lock_ctx.__enter__()
    except ServerLockBusy as exc:
        log.error("%s", exc)
        import sys as _sys  # noqa: PLC0415
        _sys.exit(1)

    try:
        if args.dry_run:
            client = None
        elif args.provider == "openai":
            client = make_openai_client()
            if args.model == MODEL:  # encore le défaut Anthropic -> on switche
                args.model = "gpt-4o-mini"
            if args.batch:
                log.warning("--batch ignoré avec --provider openai (mode synchrone).")
                args.batch = False
        else:
            client = make_anthropic_client()

        # Liste des épisodes ciblés.
        if args.guid:
            paths = [find_episode_by_guid(args.source, args.guid)]
        else:
            paths = list_episode_files(args.source)
            if args.limit is not None:
                paths = paths[: args.limit]

        # Mode batch (asynchrone) : un seul lot pour tous les épisodes.
        if args.batch and not args.dry_run:
            # L1 (revue 2026-07-19) : parité avec la boucle sync — une erreur
            # batch est journalisée, pas propagée en traceback brut.
            try:
                extract_all_batch(args.source, paths, client, args.model,
                                  args.poll_interval, args.provider,
                                  worker=args.worker)
            except Exception as exc:  # noqa: BLE001
                log.error("Échec de l'extraction par batch : %s", exc)
            return

        # Mode synchrone (ou dry-run) : charge la source UNE fois.
        source = load_source(args.source) if paths else None
        # M4 : index de run partagé (une seule relecture des recos par run).
        # Inutile en dry-run (aucune écriture).
        run_index = new_run_index(args.source) if (paths and not args.dry_run) else None
        log.info("%d épisode(s) à traiter pour extraction.", len(paths))
        for path in paths:
            try:
                extract_for_episode(args.source, path, client, args.dry_run,
                                    args.model, args.provider, source=source,
                                    worker=args.worker, run_index=run_index)
            except Exception as exc:  # noqa: BLE001 — continue sur l'épisode suivant
                log.error("Échec extraction sur %s : %s", path.name, exc)
    finally:
        try:
            lock_ctx.__exit__(None, None, None)
        except Exception:  # noqa: BLE001 — best-effort release
            pass


if __name__ == "__main__":
    main()
