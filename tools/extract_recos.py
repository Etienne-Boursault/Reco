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
import unicodedata
from pathlib import Path
from typing import Any


def _norm(s: str | None) -> str:
    """Normalisation robuste pour l'appariement (sans accent, casse, ponct.)."""
    if not s:
        return ""
    s = s.lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()

from dotenv import load_dotenv

from common import (
    TOOLS_DIR,
    list_episode_files,
    load_source,
    log,
    read_json,
    reco_prefix,
    recos_dir_for,
    transcript_path_for,
    write_json_if_changed,
)

# Modèle d'extraction par défaut : Sonnet (bon rapport qualité/coût pour cette
# tâche d'extraction structurée ; Opus serait surdimensionné). Surchargé par --model.
MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 8000
# Nombre approximatif de caractères par chunk (~ contexte raisonnable + marge coût).
CHUNK_CHARS = 24_000
# Intervalle de scrutation du statut d'un batch (Message Batches API).
BATCH_POLL_SECONDS = 20

VALID_TYPES = {
    "film", "serie", "livre", "bd", "musique", "album",
    "podcast", "jeu", "spectacle", "lieu", "autre",
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
albums, podcasts, jeux, spectacles, lieux…). Une « reco » est une œuvre qu'un
intervenant conseille, vante, ou invite à découvrir.

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


def _chunk_transcript(text: str, max_chars: int = CHUNK_CHARS) -> list[str]:
    """
    Découpe la transcription en morceaux d'au plus `max_chars`, en coupant sur
    des frontières de lignes (donc de segments horodatés) pour ne pas tronquer
    une phrase au milieu.
    """
    lines = text.splitlines(keepends=True)
    chunks: list[str] = []
    current: list[str] = []
    size = 0
    for line in lines:
        if size + len(line) > max_chars and current:
            chunks.append("".join(current))
            current = [line]
            size = len(line)
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
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", raw, re.DOTALL)
    if fence:
        raw = fence.group(1).strip()
    # Si du texte entoure le JSON, isole le premier objet { … }.
    if not raw.startswith("{"):
        m = re.search(r"\{.*\}", raw, re.DOTALL)
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

    reco: dict[str, Any] = {"title": title, "type": rtype}

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
        k = _norm(reco["title"])
        if k not in out_by_key:
            out_by_key[k] = reco
            continue
        # Fusionne : complète les champs manquants.
        existing = out_by_key[k]
        for fld in ("creator", "year", "recommendedBy", "quote", "timestamp"):
            if fld in reco and not existing.get(fld):
                existing[fld] = reco[fld]
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


def _call_anthropic(client: Any, model: str, podcast_title: str, hosts: str,
                    chunk: str) -> list[dict[str, Any]]:
    """Appel synchrone sur un chunk ; renvoie la liste de recos brutes."""
    params = _request_params(model, podcast_title, hosts, chunk)
    message = client.messages.create(**params)
    return _parse_recos_from_content(message.content)


def _call_openai(client: Any, model: str, podcast_title: str, hosts: str,
                 chunk: str) -> list[dict[str, Any]]:
    """Idem _call_anthropic, mais via l'API OpenAI Chat Completions."""
    prompt = USER_TEMPLATE.format(
        podcast_title=podcast_title, hosts=hosts,
        types=", ".join(sorted(VALID_TYPES)), chunk=chunk,
    )
    resp = client.chat.completions.create(
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


def _call_llm(client: Any, model: str, podcast_title: str, hosts: str,
              chunk: str) -> list[dict[str, Any]]:
    """Dispatche vers Anthropic ou OpenAI selon le type du client."""
    if hasattr(client, "chat"):  # OpenAI client a .chat.completions
        return _call_openai(client, model, podcast_title, hosts, chunk)
    return _call_anthropic(client, model, podcast_title, hosts, chunk)


def _next_reco_index(source_id: str) -> int:
    """Calcule le prochain index de reco (numérotation continue par source)."""
    d = recos_dir_for(source_id)
    if not d.exists():
        return 1
    max_idx = 0
    for path in d.glob("*.json"):
        m = re.search(r"(\d+)", path.stem)
        if m:
            max_idx = max(max_idx, int(m.group(1)))
    return max_idx + 1


def _existing_reco_keys(source_id: str) -> set[tuple[str, str, str]]:
    """
    Indexe les recos déjà écrites par (episodeGuid, titre, créateur) pour ne pas
    recréer de doublons lors d'une ré-exécution (idempotence inter-runs).
    """
    keys: set[tuple[str, str, str]] = set()
    d = recos_dir_for(source_id)
    if not d.exists():
        return keys
    for path in d.glob("*.json"):
        try:
            r = read_json(path)
        except Exception:  # noqa: BLE001
            continue
        keys.add((
            r.get("episodeGuid", ""),
            (r.get("title") or "").lower(),
            (r.get("creator") or "").lower(),
        ))
    return keys


def _persist_recos(source_id: str, guid: str,
                   raw_recos: list[dict[str, Any]],
                   provider: str = "anthropic") -> int:
    """
    Normalise, déduplique et persiste les recos brutes d'un épisode en mode
    UPSERT (préserve le travail humain) :

      - Si une reco existe déjà (mêmes guid+titre+créateur) :
          * `timestamp` est TOUJOURS mis à jour (recalage YT).
          * `quote` n'est mis à jour QUE si la reco n'est pas `validated`
            (on ne réécrit pas du contenu déjà curé par un humain).
          * `creator` et `year` sont complétés s'ils étaient vides.
          * `status`, `recommendedBy`, `links`, `id`, `note` sont PRÉSERVÉS.
      - Sinon, on écrit une nouvelle reco en `draft`.

    Renvoie le nombre de fichiers créés ou modifiés.
    """
    normalized = [r for r in (_normalize_reco(x) for x in raw_recos) if r]
    normalized = _dedupe(normalized)
    log.info("Épisode %s : %d reco(s) candidate(s) après normalisation.",
             guid, len(normalized))
    if not normalized:
        return 0

    # Map (guid, titre_normalisé) -> chemin du fichier existant.
    # Match par titre uniquement (le créateur varie souvent d'un run à l'autre).
    target_dir = recos_dir_for(source_id)
    existing_map: dict[tuple[str, str], Path] = {}
    if target_dir.exists():
        for path in target_dir.glob("*.json"):
            try:
                r = read_json(path)
            except Exception:  # noqa: BLE001
                continue
            key = (r.get("episodeGuid", ""), _norm(r.get("title")))
            existing_map[key] = path

    prefix = reco_prefix(source_id)
    index = _next_reco_index(source_id)
    new_count = 0
    upd_count = 0

    for reco in normalized:
        key = (guid, _norm(reco["title"]))

        if key in existing_map:
            path = existing_map[key]
            existing = read_json(path)
            merged = dict(existing)
            # Timestamp : on met à jour systématiquement (recalage YT).
            if reco.get("timestamp"):
                merged["timestamp"] = reco["timestamp"]
            # Quote : préservée pour les recos déjà validées.
            if existing.get("status") != "validated" and reco.get("quote"):
                merged["quote"] = reco["quote"]
            # creator / year : complète s'ils étaient vides.
            for k in ("creator", "year"):
                if k in reco and not existing.get(k):
                    merged[k] = reco[k]
            # extractors : on ajoute le provider courant à la liste.
            merged["extractors"] = sorted(
                set((existing.get("extractors") or []) + [provider])
            )
            if write_json_if_changed(path, merged):
                upd_count += 1
                log.info("  ↻ MAJ %s — « %s » (extractors=%s)",
                         path.name, reco["title"], merged["extractors"])
            continue

        # Nouvelle reco.
        full: dict[str, Any] = {
            "id": f"{prefix}-{index:04d}",
            "sourceId": source_id,
            "episodeGuid": guid,
            "title": reco["title"],
            "type": reco["type"],
        }
        for key_name in ("creator", "year", "recommendedBy", "quote", "timestamp"):
            if key_name in reco:
                full[key_name] = reco[key_name]
        full["links"] = []
        full["status"] = "draft"
        full["extractors"] = [provider]

        path = target_dir / f"{index:04d}.json"
        if write_json_if_changed(path, full):
            new_count += 1
            log.info("  + NEW %s — « %s » (extractor=%s)", path.name, reco["title"], provider)
        existing_map[key] = path
        index += 1

    log.info("Épisode %s : %d nouvelle(s), %d mise(s) à jour.", guid, new_count, upd_count)
    return new_count + upd_count


def extract_for_episode(source_id: str, episode_path: Path, client: Any | None,
                        dry_run: bool, model: str = MODEL,
                        provider: str = "anthropic") -> int:
    """
    Extraction SYNCHRONE d'un épisode (1 appel API par chunk, à la suite).
    Si `dry_run`, n'appelle pas l'API et n'écrit rien (affiche seulement le plan).
    """
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
        raw_recos.extend(_call_llm(client, model, podcast_title, hosts, chunk))

    return _persist_recos(source_id, guid, raw_recos, provider)


def extract_all_batch(source_id: str, episode_paths: list[Path], client: Any,
                      model: str = MODEL,
                      poll_seconds: int = BATCH_POLL_SECONDS,
                      provider: str = "anthropic") -> int:
    """
    Extraction par LOT via la Message Batches API (−50 % de coût, asynchrone).

    Toutes les requêtes (1 par chunk, tous épisodes confondus) sont soumises en
    un seul batch, puis on attend la fin du traitement et on écrit les recos par
    épisode. Idéal pour traiter beaucoup d'épisodes d'un coup.
    """
    source = load_source(source_id)
    podcast_title = source.get("title", source_id)
    hosts = ", ".join(source.get("hosts", [])) or "inconnus"

    # 1. Construire les requêtes en mémorisant custom_id -> guid.
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

    if not requests:
        log.warning("Aucun chunk à traiter (transcriptions manquantes ?).")
        return 0

    log.info("Batch : %d requête(s) sur %d épisode(s), modèle %s.",
             len(requests), len(guids), model)

    # 2. Soumettre le batch.
    batch = client.messages.batches.create(requests=requests)
    batch_id = batch.id
    log.info("Batch créé : %s. Traitement en cours…", batch_id)

    # 3. Scruter jusqu'à la fin.
    while True:
        batch = client.messages.batches.retrieve(batch_id)
        if batch.processing_status == "ended":
            break
        log.info("  … statut=%s", batch.processing_status)
        time.sleep(poll_seconds)

    # 4. Récupérer et regrouper les résultats par épisode.
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
            log.warning("  Requête %s en échec : %s", entry.custom_id, entry.result.type)
    if errors:
        log.warning("%d requête(s) en échec dans le batch.", errors)

    # 5. Écrire les recos par épisode.
    total = 0
    for guid in guids:
        total += _persist_recos(source_id, guid, raw_by_guid[guid], provider)
    log.info("Batch terminé : %d nouvelle(s) reco(s) écrite(s) au total.", total)
    return total


def _make_client() -> Any:
    """Initialise le client Anthropic (clé via ANTHROPIC_API_KEY)."""
    try:
        import anthropic  # noqa: PLC0415 — import paresseux.
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "Le SDK anthropic n'est pas installé (pip install -r requirements.txt)."
        ) from exc
    load_dotenv(TOOLS_DIR / ".env")
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "Variable d'environnement ANTHROPIC_API_KEY manquante. "
            "Copie tools/.env.example en tools/.env et renseigne la clé, "
            "ou exporte-la dans ton shell."
        )
    return anthropic.Anthropic(api_key=api_key)


def _make_openai_client() -> Any:
    """Initialise un client OpenAI (clé via OPENAI_API_KEY)."""
    try:
        import openai  # noqa: PLC0415 — import paresseux.
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("Le SDK openai n'est pas installé (pip install openai).") from exc
    load_dotenv(TOOLS_DIR / ".env")
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("Variable d'environnement OPENAI_API_KEY manquante.")
    return openai.OpenAI(api_key=api_key)


def _find_episode_by_guid(source_id: str, guid: str) -> Path:
    for path in list_episode_files(source_id):
        if read_json(path).get("guid") == guid:
            return path
    raise FileNotFoundError(
        f"Aucun épisode avec guid « {guid} » dans « {source_id} »."
    )


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
    args = parser.parse_args()

    if args.dry_run:
        client = None
    elif args.provider == "openai":
        client = _make_openai_client()
        if args.model == MODEL:  # encore le défaut Anthropic -> on switche
            args.model = "gpt-4o-mini"
        if args.batch:
            log.warning("--batch ignoré avec --provider openai (mode synchrone).")
            args.batch = False
    else:
        client = _make_client()

    # Liste des épisodes ciblés.
    if args.guid:
        paths = [_find_episode_by_guid(args.source, args.guid)]
    else:
        paths = list_episode_files(args.source)
        if args.limit is not None:
            paths = paths[: args.limit]

    # Mode batch (asynchrone) : un seul lot pour tous les épisodes.
    if args.batch and not args.dry_run:
        extract_all_batch(args.source, paths, client, args.model,
                          args.poll_interval, args.provider)
        return

    # Mode synchrone (ou dry-run).
    log.info("%d épisode(s) à traiter pour extraction.", len(paths))
    for path in paths:
        try:
            extract_for_episode(args.source, path, client, args.dry_run,
                                args.model, args.provider)
        except Exception as exc:  # noqa: BLE001 — on continue sur l'épisode suivant.
            log.error("Échec extraction sur %s : %s", path.name, exc)


if __name__ == "__main__":
    main()
