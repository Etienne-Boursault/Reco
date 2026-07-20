"""reco_dedup.py — Détection (clustering) de recos quasi-doublons.

Une même œuvre peut être extraite plusieurs fois pour un même épisode :
  - multi-transcripts (Acast vs YouTube),
  - multi-LLMs (Anthropic, OpenAI),
  - coquilles phonétiques.

Ce module fournit :
  - `cluster_recos()` : regroupe les recos similaires en clusters,
    par titre normalisé (SequenceMatcher) + proximité temporelle.
  - `pick_canonical()` : choisit la version par défaut à conserver.
  - `is_cluster_compatible()` : validation cross-épisode/cross-kind.

Pour la fusion (merge_cluster, restore_last_backup, helpers _merge_*)
voir `reco_dedup_merge.py` (#G — séparation pour rester sous 500 LOC).

Single-threaded by design : pas de lock — voir docs/yagni.md.
"""
from __future__ import annotations

import os  # noqa: F401  — réexporté pour les tests qui patchent reco_dedup.os.replace
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from common import normalize_text

# Réexports publics : helpers de fusion vivent dans reco_dedup_merge (#G).
# Les ré-exports préservent la rétro-compat des callers (review_server, tests).
from reco_dedup_merge import (  # noqa: F401
    BACKUP_DIR,
    _apply_merged_fields,
    _atomic_write_json,
    _collect_aliases,
    _collect_losers_to_delete,
    _longest_quote,
    _merge_custom_links,
    _merge_external_ids,
    _merge_link_overrides,
    _merge_watch_providers,
    _merged_history,
    _now_iso,
    _path_for_reco,
    _union_list_of_dicts_by_key,
    _write_backup,
    merge_cluster,
    restore_last_backup,
)

# Seuils par défaut (ajustables en argument de cluster_recos).
DEFAULT_TITLE_THRESHOLD = 0.80
DEFAULT_TIME_WINDOW_SEC = 120
LOW_SIMILARITY_FLOOR = 0.70  # En dessous, on n'autorise rien.


def is_cluster_compatible(
    reco: dict,
    *,
    expected_guid: str,
    expected_kind: str = "reco",
    exclude_discarded: bool = True,
) -> bool:
    """#14 — Helper centralisé : True si `reco` peut rejoindre le cluster.

    Critères :
      - `episodeGuid` doit matcher `expected_guid` (jamais cross-épisode).
      - `kind` (défaut "reco") doit égaler `expected_kind`.
      - Si `exclude_discarded`, `status` ne doit pas être "discarded".
    """
    if reco.get("episodeGuid") != expected_guid:
        return False
    if exclude_discarded and reco.get("status") == "discarded":
        return False
    if (reco.get("kind") or "reco") != expected_kind:
        return False
    return True


@dataclass
class Cluster:
    """Un groupe de recos quasi-doublons.

    `canonical_id`        : id de la version pré-sélectionnée (cf. `pick_canonical`).
    `members`             : recos appartenant au cluster (>= 2 — invariant #13).
    `similarity`          : score minimum observé entre titres du cluster.
    `avg_timecode_delta`  : moyenne des écarts (en sec.) au temps minimum.
    """
    canonical_id: str
    members: list[dict] = field(default_factory=list)
    similarity: float = 1.0
    avg_timecode_delta: int = 0

    def __post_init__(self) -> None:
        """#13 — Invariant : >=2 members ET canonical_id présent parmi eux.

        Empêche des Cluster mal formés (1 membre, canonical_id absent) de
        glisser jusqu'à merge_cluster qui aurait un comportement subtil
        difficile à débuguer.
        """
        if len(self.members) < 2:
            raise ValueError("Cluster requiert au moins 2 membres")
        ids = {m.get("id") for m in self.members}
        if self.canonical_id not in ids:
            raise ValueError(
                f"canonical_id={self.canonical_id!r} absent des members"
            )


# --- Helpers internes -----------------------------------------------------
def _title_similarity(a: str, b: str) -> float:
    """Ratio SequenceMatcher sur les titres normalisés (0..1)."""
    na, nb = normalize_text(a), normalize_text(b)
    if not na or not nb:
        return 0.0
    return SequenceMatcher(None, na, nb).ratio()


def _ts_to_seconds(ts: str | None) -> int | None:
    """« HH:MM:SS » → secondes (None si invalide / absent).

    #22 — Réexport pour rétro-compat ; implémentation unique dans
    `review_render_common._ts_seconds`.
    """
    from review_render_common import _ts_seconds as _impl  # noqa: PLC0415
    return _impl(ts)


def _is_active(r: dict) -> bool:
    """Une reco active = non discarded (on ne déduplique pas les rejets)."""
    return (r.get("status") or "draft") != "discarded"


def _kind_of(r: dict) -> str:
    """`kind` effectif (défaut: 'reco')."""
    return r.get("kind") or "reco"


def _can_match(a: dict, b: dict, sim: float, time_window_sec: int) -> bool:
    """Décide si deux recos forment un appariement valide.

    - Toujours séparées par `episodeGuid` (jamais inter-épisode).
    - Toujours séparées par `kind` (reco vs citation pas mélangés).
    - Similarité >= 0.80 obligatoire.
    - Tolérance [0.70 ; 0.80) : OK seulement si Δt ≤ time_window_sec.
    """
    if a.get("episodeGuid") != b.get("episodeGuid"):
        return False
    if _kind_of(a) != _kind_of(b):
        return False
    if sim >= DEFAULT_TITLE_THRESHOLD:
        return True
    if sim < LOW_SIMILARITY_FLOOR:
        return False
    sa, sb = _ts_to_seconds(a.get("timestamp")), _ts_to_seconds(b.get("timestamp"))
    if sa is None or sb is None:
        return False
    return abs(sa - sb) <= time_window_sec


# --- Clustering -----------------------------------------------------------
def cluster_recos(
    recos: list[dict],
    similarity_threshold: float = DEFAULT_TITLE_THRESHOLD,
    time_window_sec: int = DEFAULT_TIME_WINDOW_SEC,
) -> list[Cluster]:
    """Groupe les recos par similarité titre + proximité timecode.

    Algorithme : union-find naïf sur les paires actives. O(n²) mais n est
    le nombre de recos par épisode (typ. < 30), c'est négligeable.

    Retourne SEULEMENT les clusters de >= 2 membres (1 reco isolée n'est
    pas un cluster, le caller la traite séparément).
    """
    actives = [r for r in recos if _is_active(r)]
    n = len(actives)
    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[rj] = ri

    matched: list[tuple[int, int, float]] = []
    for i in range(n):
        for j in range(i + 1, n):
            sim = _title_similarity(
                actives[i].get("title", ""), actives[j].get("title", "")
            )
            if sim < similarity_threshold:
                continue
            if not _can_match(actives[i], actives[j], sim, time_window_sec):
                continue
            union(i, j)
            matched.append((i, j, sim))

    groups: dict[int, list[int]] = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)

    clusters: list[Cluster] = []
    for indices in groups.values():
        if len(indices) < 2:
            continue
        members = [actives[i] for i in indices]
        canonical = pick_canonical(members)
        secs = [_ts_to_seconds(m.get("timestamp")) or 0 for m in members]
        base = min(secs)
        avg_delta = int(sum(abs(s - base) for s in secs) / len(secs))
        idx_set = set(indices)
        score = min(
            (s for (i, j, s) in matched if i in idx_set and j in idx_set),
            default=1.0,
        )
        clusters.append(Cluster(
            canonical_id=canonical,
            members=members,
            similarity=score,
            avg_timecode_delta=avg_delta,
        ))
    clusters.sort(key=lambda c: c.canonical_id)
    return clusters


def pick_canonical(cluster_members: list[dict]) -> str:
    """Choisit l'ID par défaut. Ordre de tri (du PIRE au MEILLEUR) :

    1. status == "validated" (validé > non validé)
    2. transcriptSource == "youtube" (YT > Acast)
    3. nb d'extracteurs distincts
    4. longueur de la quote
    5. id (tri lexicographique stable comme tie-break déterministe)
    """
    def score(r: dict) -> tuple:
        is_validated = 1 if r.get("status") == "validated" else 0
        is_yt = 1 if r.get("transcriptSource") == "youtube" else 0
        n_ext = len(r.get("extractors") or [])
        ql = len(r.get("quote") or "")
        return (is_validated, is_yt, n_ext, ql)

    ordered = sorted(
        cluster_members,
        key=lambda r: (
            -score(r)[0], -score(r)[1], -score(r)[2], -score(r)[3],
            r.get("id", "")
        ),
    )
    return ordered[0].get("id", "")
