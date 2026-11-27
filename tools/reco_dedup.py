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
    from review_render_common import _ts_seconds as _impl
    return _impl(ts)


def _is_active(r: dict) -> bool:
    """Une reco active = non discarded (on ne déduplique pas les rejets)."""
    return (r.get("status") or "draft") != "discarded"


def _kind_of(r: dict) -> str:
    """`kind` effectif (défaut: 'reco')."""
    return r.get("kind") or "reco"


# Types entre lesquels une passe d'extraction hésite pour une même œuvre.
# « autre » (aucun type choisi) n'est jamais une preuve : il est retiré.
_FAMILLES_DE_TYPES = (
    {"musique", "album", "artiste", "spectacle"},
    {"film", "serie", "video", "chaine", "spectacle", "podcast"},
    {"livre", "bd", "article"},
    {"jeu", "application"},
)
_MOTS_DE_LIAISON = {"et", "and", "feat", "ft", "featuring", "x", "avec"}
_SEUIL_CREATEUR = 0.80


def _types_proches(types_a: set[str], types_b: set[str]) -> bool:
    """Vrai si un type de chaque côté est le même, ou de la même famille."""
    return any(ta == tb or any({ta, tb} <= f for f in _FAMILLES_DE_TYPES)
               for ta in types_a for tb in types_b)


def _mots_du_createur(createur: str | None) -> list[str]:
    return [m for m in normalize_text(createur).split() if m not in _MOTS_DE_LIAISON]


def _createurs_differents(a: str | None, b: str | None) -> bool:
    """Vrai si deux créateurs renseignés ne sont pas deux graphies du même.

    Sont tenus pour le même : « Bigflo & Oli » et « Bigflo et Oli », un nom
    contenu dans l'autre (« Orelsan » et « Orelsan feat. Stromae »), et un nom
    mal entendu (« Canet », « Canné », à partir de 80 % de ressemblance).
    """
    mots_a, mots_b = _mots_du_createur(a), _mots_du_createur(b)
    if not mots_a or not mots_b:
        return False
    if set(mots_a) <= set(mots_b) or set(mots_b) <= set(mots_a):
        return False
    return SequenceMatcher(None, " ".join(mots_a), " ".join(mots_b)).ratio() < _SEUIL_CREATEUR


def _oeuvres_distinctes(a: dict, b: dict) -> bool:
    """Vrai quand deux recos désignent à coup sûr deux œuvres différentes.

    Il faut deux preuves à la fois : des types sans rien de proche, et deux
    créateurs renseignés qui ne sont pas deux graphies du même. Une seule ne
    suffit pas : une passe d'extraction peut mal choisir le type, ou mal
    entendre le créateur, d'une même œuvre.

    Demandé par Étienne le 2026-11-27 sur S6-E11 : l'album « Karma » de
    Bigflo & Oli et le film « Karma » de Guillaume Canet, cités à 11 s
    d'écart, s'affichaient comme « doublons probables ».
    """
    types_a = set(a.get("types") or []) - {"autre"}
    types_b = set(b.get("types") or []) - {"autre"}
    if not types_a or not types_b or _types_proches(types_a, types_b):
        return False
    return _createurs_differents(a.get("creator"), b.get("creator"))


def _can_match(a: dict, b: dict, sim: float, time_window_sec: int) -> bool:
    """Décide si deux recos forment un appariement valide.

    - Toujours séparées par `episodeGuid` (jamais inter-épisode).
    - Toujours séparées par `kind` (reco vs citation pas mélangés).
    - Séparées quand ce sont deux œuvres distinctes (`_oeuvres_distinctes`).
    - Similarité >= 0.80 obligatoire.
    - Tolérance [0.70 ; 0.80) : OK seulement si Δt ≤ time_window_sec.
    """
    if a.get("episodeGuid") != b.get("episodeGuid"):
        return False
    if _kind_of(a) != _kind_of(b):
        return False
    if _oeuvres_distinctes(a, b):
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

    def union(i: int, j: int) -> bool:
        """Joint les groupes de i et j, sauf s'ils réuniraient deux œuvres
        distinctes : une troisième reco qui ressemble aux deux rejoint l'une,
        jamais les deux à la fois (revue de la PR #218)."""
        ri, rj = find(i), find(j)
        if ri == rj:
            return True
        groupe_i = [k for k in range(n) if find(k) == ri]
        groupe_j = [k for k in range(n) if find(k) == rj]
        if any(_oeuvres_distinctes(actives[x], actives[y])
               for x in groupe_i for y in groupe_j):
            return False
        parent[rj] = ri
        return True

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
            if union(i, j):
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
