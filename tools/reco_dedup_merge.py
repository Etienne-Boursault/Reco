"""reco_dedup_merge.py — Fusion (merge_cluster) + helpers purs (#G).

Extrait de `reco_dedup.py` pour rester sous 500 LOC. Ce module contient :
  - les helpers purs (sans I/O) de fusion : `_merge_custom_links`,
    `_merge_watch_providers`, `_merge_link_overrides`, `_merge_external_ids`,
    `_longest_quote`, `_collect_aliases`, `_apply_merged_fields` ;
  - les helpers d'I/O : `_atomic_write_json` (Windows-safe), `_write_backup`,
    `_collect_losers_to_delete` ;
  - l'orchestration : `merge_cluster`, `restore_last_backup`.

Single-threaded by design : on n'utilise PAS de lock — voir docs/yagni.md.
"""
from __future__ import annotations

import json
import os
import shutil
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from common import TOOLS_DIR, log, normalize_text, read_json, reco_prefix
from extraction_history import (
    derive_extractors, from_dict as _entry_from_dict, merge_history,
    pick_display_state, to_dict as _entry_to_dict,
)

BACKUP_DIR: Path = TOOLS_DIR / "output" / "dedup-backup"


# --- Helpers I/O ----------------------------------------------------------
def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _path_for_reco(source_id: str, reco_id: str,
                   recos_root: Path | None = None) -> Path | None:
    """Localise le fichier JSON d'une reco (scan dossier — non cached)."""
    from common import recos_dir_for  # noqa: PLC0415
    d = recos_root or recos_dir_for(source_id)
    if not d.exists():
        return None
    for p in d.glob("*.json"):
        try:
            r = read_json(p)
        except (OSError, ValueError):
            continue
        if r.get("id") == reco_id:
            return p
    return None


def _union_list_of_dicts_by_key(
    a: list[dict], b: list[dict], key: str,
) -> list[dict]:
    """Union ordonnée de listes de dicts, déduplication par `key`."""
    seen: set[str] = set()
    out: list[dict] = []
    for src in (a, b):
        for item in src:
            k = item.get(key)
            if k is None or k in seen:
                continue
            seen.add(k)
            out.append(item)
    return out


def _merged_history(members: list[dict]) -> list[dict]:
    """Union dédupliquée de toutes les entrées d'extractionHistory."""
    merged: list = []
    for r in members:
        for e in (r.get("extractionHistory") or []):
            merged = merge_history(merged, _entry_from_dict(e))
    return [_entry_to_dict(e) for e in merged]


# --- Helpers purs de fusion (#18) -----------------------------------------
def _merge_custom_links(kept: dict, members: list[dict],
                       keep_id: str) -> list[dict]:
    """Union dédup par url des `customLinks` du kept + losers."""
    out = list(kept.get("customLinks") or [])
    for m in members:
        if m.get("id") == keep_id:
            continue
        out = _union_list_of_dicts_by_key(out, m.get("customLinks") or [], "url")
    return out


def _merge_watch_providers(kept: dict, members: list[dict],
                           keep_id: str) -> list[dict]:
    """Union dédup par url des `watchProviders` du kept + losers."""
    out = list(kept.get("watchProviders") or [])
    for m in members:
        if m.get("id") == keep_id:
            continue
        out = _union_list_of_dicts_by_key(out, m.get("watchProviders") or [], "url")
    return out


def _merge_dict_field(kept: dict, members: list[dict],
                      keep_id: str, field: str) -> dict:
    """#7 review — helper générique : merge dict field, kept gagne au conflit."""
    out = dict(kept.get(field) or {})
    for m in members:
        if m.get("id") == keep_id:
            continue
        for k, v in (m.get(field) or {}).items():
            out.setdefault(k, v)
    return out


def _merge_link_overrides(kept: dict, members: list[dict],
                          keep_id: str) -> dict:
    """Merge dict — kept gagne en cas de conflit clé."""
    return _merge_dict_field(kept, members, keep_id, "linkOverrides")


def _merge_external_ids(kept: dict, members: list[dict],
                        keep_id: str) -> dict:
    """Merge dict — kept gagne en cas de conflit clé."""
    return _merge_dict_field(kept, members, keep_id, "externalIds")


def _longest_quote(kept: dict, members: list[dict]) -> str:
    """Renvoie la quote la plus longue parmi kept + tous les members."""
    longest = kept.get("quote") or ""
    for m in members:
        q = m.get("quote") or ""
        if len(q) > len(longest):
            longest = q
    return longest


def _collect_aliases(kept: dict, members: list[dict], keep_id: str) -> list[str]:
    """Aliases du kept + titres/aliases distincts (normalisés) des losers.

    #18 — Dédup global : on parcourt tous les losers et chaque titre/alias
    n'apparaît qu'une fois (normalisé). Le titre du kept et ses aliases
    existants sont préservés en tête.
    """
    aliases = list(kept.get("aliases") or [])
    seen = {normalize_text(a) for a in aliases}
    seen.add(normalize_text(kept.get("title", "")))
    for m in members:
        if m.get("id") == keep_id:
            continue
        loser_titles = [m.get("title", "")] + list(m.get("aliases") or [])
        for t in loser_titles:
            t = (t or "").strip()
            if not t:
                continue
            tn = normalize_text(t)
            if tn in seen:
                continue
            seen.add(tn)
            aliases.append(t)
    return aliases


def _atomic_write_json(path: Path, data: dict) -> None:
    """Écrit `data` JSON-encoded dans `path` de façon atomique (#E, #7, #34).

    Stratégie identique à `common.atomic_write_text` (DRY : tous les
    writers — pipeline + serveur + handler `_allocate_new_reco` — utilisent
    désormais ce pattern). On garde la copie LOCALE plutôt que de déléguer
    pour préserver les tests historiques qui patchent
    `reco_dedup_merge.os.replace` (cf. test_reco_dedup.py, test_review_server.py).

      - écrit dans un fichier .tmp dans le même dossier,
      - flush + fsync pour garantir bytes sur disque AVANT le rename,
      - os.replace (atomique POSIX ; Windows retry 4× pour les
        PermissionError dûs aux lecteurs concurrents).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(json.dumps(data, ensure_ascii=False, indent=2))
            f.flush()
            os.fsync(f.fileno())
        for i in range(4):
            try:
                os.replace(tmp, path)
                return
            except PermissionError:
                if i == 3:
                    raise
                time.sleep(0.1)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


def _collect_losers_to_delete(
    members: list[dict], keep_id: str, paths: dict[str, Path],
) -> list[tuple[str, Path]]:
    """Liste (id, path) des members non-kept dont le fichier existe encore.

    Idempotence : les fichiers déjà supprimés (cas d'un 2ᵉ appel) sont
    silencieusement ignorés (log.debug — #32).
    """
    out: list[tuple[str, Path]] = []
    for m in members:
        rid = m.get("id", "")
        if rid == keep_id:
            continue
        p = paths.get(rid)
        if p is None:
            log.debug("collect_losers : %s sans path connu, skip", rid)
            continue
        if not p.exists():
            log.debug("collect_losers : %s fichier absent, skip", rid)
            continue
        out.append((rid, p))
    return out


def _write_backup(
    keep_id: str, keep_path: Path,
    losers_to_delete: list[tuple[str, Path]],
    source_id: str, backup_root: Path | None,
) -> Path | None:
    """Crée le dossier daté du backup (kept + losers + manifest)."""
    if not (losers_to_delete or keep_path.exists()):
        return None
    timestamp = datetime.now(timezone.utc).isoformat(
        timespec="microseconds",
    ).replace(":", "-")
    merge_id = uuid.uuid4().hex[:8]
    root = backup_root or BACKUP_DIR
    backup_dir = root / f"{timestamp}_{merge_id}" / source_id
    merge_root = backup_dir.parent
    backup_dir.mkdir(parents=True, exist_ok=True)
    # IMPORTANT : on conserve le NOM DE FICHIER D'ORIGINE (keep_path.name)
    # plutôt que `{rid}.json`. Sinon le restore recopie sous un autre nom
    # (`ubm-XXXX.json` au lieu de `XXXX.json`) → doublon sur disque,
    # corruption silencieuse du dossier recos.
    shutil.copy2(keep_path, backup_dir / keep_path.name)
    loser_ids_backed: list[str] = []
    for rid, p in losers_to_delete:
        shutil.copy2(p, backup_dir / p.name)
        loser_ids_backed.append(rid)
    manifest = {
        "merge_id": merge_id,
        "source_id": source_id,
        "keep_id": keep_id,
        "loser_ids": loser_ids_backed,
        "at": _now_iso(),
    }
    # #19 review — manifest atomic : pas critique (le manifest reste lisible
    # si tronqué → skip dans restore), mais cohérent avec le reste du module.
    _atomic_write_json(merge_root / "manifest.json", manifest)
    return backup_dir


def _apply_merged_fields(kept: dict, members: list[dict], keep_id: str) -> None:
    """Mute `kept` in-place avec les champs fusionnés des `members` (#I).

    Invariant : ne JAMAIS diminuer un champ du kept — si tous les losers ont
    une liste vide pour `customLinks`, on ne touche pas au champ existant
    (le `if cl:` filtre les listes vides issues du merge, mais la branche
    n'est entrée que si au moins quelque chose s'ajoute).
    """
    # extractionHistory + extractors + display state (timestamp + transcriptSource)
    merged_hist_dicts = _merged_history(members)
    kept["extractionHistory"] = merged_hist_dicts
    if merged_hist_dicts:
        merged_entries = [_entry_from_dict(e) for e in merged_hist_dicts]
        kept["extractors"] = derive_extractors(merged_entries)
        disp = pick_display_state(merged_entries)
        kept["timestamp"] = disp["timestamp"]
        kept["transcriptSource"] = disp["transcriptSource"]

    cl = _merge_custom_links(kept, members, keep_id)
    if cl:
        kept["customLinks"] = cl
    wp = _merge_watch_providers(kept, members, keep_id)
    if wp:
        kept["watchProviders"] = wp
    lo = _merge_link_overrides(kept, members, keep_id)
    if lo:
        kept["linkOverrides"] = lo
    ext = _merge_external_ids(kept, members, keep_id)
    if ext:
        kept["externalIds"] = ext

    longest_quote = _longest_quote(kept, members)
    if longest_quote:
        kept["quote"] = longest_quote

    aliases = _collect_aliases(kept, members, keep_id)
    if aliases:
        kept["aliases"] = aliases


# --- Orchestration --------------------------------------------------------
def merge_cluster(
    cluster,
    keep_id: str,
    source_id: str,
    backup: bool = True,
    backup_root: Path | None = None,
) -> dict:
    """Fusionne `cluster.members` dans la reco `keep_id`.

    Single-threaded by design : pas de lock — voir docs/yagni.md.
    Idempotence : un second appel sur le même cluster ne fait rien si les
    autres fichiers n'existent déjà plus.
    """
    # Import tardif pour éviter le cycle reco_dedup ↔ reco_dedup_merge.
    from reco_dedup import is_cluster_compatible  # noqa: PLC0415

    members = list(cluster.members)
    keep = next((m for m in members if m.get("id") == keep_id), None)
    if keep is None:
        raise ValueError(f"keep_id={keep_id!r} absent du cluster")

    paths: dict[str, Path] = {}
    for m in members:
        rid = m.get("id", "")
        p = _path_for_reco(source_id, rid)
        if p is not None:
            paths[rid] = p

    keep_path = paths.get(keep_id)
    if keep_path is None:
        raise FileNotFoundError(f"Fichier introuvable pour keep_id={keep_id}")

    kept = read_json(keep_path)
    expected_guid = kept.get("episodeGuid")
    expected_kind = kept.get("kind", "reco")

    # #J + #K — re-read fresh + valide chaque loser :
    #   1) l'id du fichier disque doit matcher (sinon le slot a été réutilisé) ;
    #   2) la reco fraîche doit toujours être compatible avec le kept
    #      (kind/guid) — sinon un edit hostile entre la détection et le merge
    #      ferait dériver le cluster vers un loser muté.
    # En cas de mismatch, on retombe sur la version en mémoire (m).
    fresh_members: list[dict] = []
    for m in members:
        rid = m.get("id", "")
        p = paths.get(rid)
        if p is None or not p.exists():
            fresh_members.append(m)
            continue
        try:
            fresh = read_json(p)
        except (OSError, ValueError):
            fresh_members.append(m)
            continue
        if fresh.get("id") != rid:
            log.warning(
                "Fresh loser id mismatch %s≠%s, retombe en mémoire",
                fresh.get("id"), rid,
            )
            fresh_members.append(m)
            continue
        if rid != keep_id and not is_cluster_compatible(
            fresh, expected_guid=expected_guid, expected_kind=expected_kind,
        ):
            log.warning(
                "Fresh loser %s incompatible (kind/guid), retombe en mémoire", rid,
            )
            fresh_members.append(m)
            continue
        fresh_members.append(fresh)
    _apply_merged_fields(kept, fresh_members, keep_id)

    # --- Backup + delete des non-kept ---
    losers_to_delete = _collect_losers_to_delete(members, keep_id, paths)
    backup_dir = _write_backup(
        keep_id, keep_path, losers_to_delete, source_id, backup_root,
    ) if backup else None

    # Atomicité : on écrit le kept AVANT d'unlink les losers.
    _atomic_write_json(keep_path, kept)

    deleted_count = 0
    for _rid, p in losers_to_delete:
        try:
            p.unlink()
            deleted_count += 1
        except FileNotFoundError:
            pass
    log.info(
        "Cluster fusionné dans %s : %d membre(s) supprimé(s), backup=%s",
        keep_id, deleted_count,
        str(backup_dir) if backup and losers_to_delete else "non",
    )
    return kept


def _normalize_backup_filename(name: str, source_id: str) -> str:
    """Migration backups historiques : `ubm-1325.json` → `1325.json`.

    Avant le fix Bug B, `_write_backup` copiait sous `{prefix}-{NNNN}.json`
    (ex: `ubm-0569.json`). Restorer tel quel recréerait un doublon disque
    à côté du `0569.json` actuel. On normalise au copy. Identité pour les
    backups récents (déjà au bon nom).
    """
    prefix = reco_prefix(source_id)
    head = f"{prefix}-"
    if name.startswith(head):
        rest = name[len(head):]
        # On veut un id numérique court (4 chiffres typiques) suivi de .json.
        # Filet large : tant que ça commence par un chiffre et finit en .json.
        if rest.endswith(".json") and rest[:1].isdigit():
            return rest
    return name


def restore_last_backup(source_id: str, backup_root: Path | None = None) -> dict:
    """Restaure le dernier merge enregistré pour cette source.

    Stratégie sûre (#23, #33) :
      1. cherche le manifest le plus récent matching source_id ;
      2. valide que TOUS les JSON du dossier source sont parsables — un
         backup corrompu est skip et on essaie le précédent ;
      3. renomme le dossier en `.consumed` AVANT le copy : si le copy
         échoue à mi-parcours et qu'on rappelle restore, on n'a pas
         re-réappliqué le même backup deux fois ;
      4. copy + rmtree du `.consumed`.

    Retourne `{n_restored, timestamp_restored, merge_id}`.
    """
    from common import recos_dir_for  # noqa: PLC0415
    root = backup_root or BACKUP_DIR
    if not root.exists():
        return {
            "n_restored": 0, "n_failed": 0,
            "timestamp_restored": None, "merge_id": None,
        }
    dirs = sorted([d for d in root.iterdir() if d.is_dir()], reverse=True)
    for d in dirs:
        manifest_path = d / "manifest.json"
        if not manifest_path.exists():
            continue
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if manifest.get("source_id") != source_id:
            continue
        src_dir = d / source_id
        if not src_dir.exists():
            continue
        # #23 — valide tous les JSON avant de toucher au disque cible.
        json_files = list(src_dir.glob("*.json"))
        all_valid = True
        for p in json_files:
            try:
                json.loads(p.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                log.warning(
                    "Backup %s contient un JSON invalide (%s), skip",
                    d.name, exc,
                )
                all_valid = False
                break
        if not all_valid:
            continue

        # #33 — Idéalement on rename d'abord en `.consumed` (anti
        # double-application). Sur Windows (locks antivirus, handles),
        # le rename peut PermissionError ; dans ce cas on retombe sur
        # l'opération directe — le risque double-application existe
        # mais reste théorique pour un outil mono-utilisateur.
        consumed = d.with_name(d.name + ".consumed")
        try:
            d.rename(consumed)
            work_dir = consumed
        except OSError as exc:
            log.warning("Rename backup %s impossible (%s), copy in-place", d.name, exc)
            work_dir = d

        dst_dir = recos_dir_for(source_id)
        dst_dir.mkdir(parents=True, exist_ok=True)
        work_src = work_dir / source_id
        n = 0
        n_failed = 0
        for p in work_src.glob("*.json"):
            target_name = _normalize_backup_filename(p.name, source_id)
            try:
                shutil.copy2(p, dst_dir / target_name)
                n += 1
            except OSError as exc:
                log.warning("Restore copy %s échoué : %s", p.name, exc)
                n_failed += 1
        try:
            shutil.rmtree(work_dir)
        except OSError as exc:
            log.warning("Cleanup %s impossible : %s", work_dir.name, exc)
        log.info(
            "Restauré %d fichier(s) depuis %s (échec=%d)", n, d.name, n_failed,
        )
        return {
            "n_restored": n,
            "n_failed": n_failed,
            "timestamp_restored": d.name,
            "merge_id": manifest.get("merge_id"),
        }
    return {
        "n_restored": 0, "n_failed": 0,
        "timestamp_restored": None, "merge_id": None,
    }
