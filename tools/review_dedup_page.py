"""review_dedup_page.py — Page /doublons : consolidation MANUELLE des doublons.

L'auto-dedup est peu fiable (faux positifs : œuvres proches mais distinctes, ex.
album vs film-concert ; notes « Doublon de » imparfaites). Ici l'HUMAIN décide :
par cluster, il coche la/les reco(s) à GARDER (type + titre corrigeables inline),
et les autres passent automatiquement en `discarded`. Retour utilisateur 07-23.

Détection intra-épisode uniquement (règle Etienne : même artiste sur des épisodes
DIFFÉRENTS = à garder, pas un doublon). Signaux : note « Doublon de ubm-XXXX »
(même épisode) ; titre normalisé identique ; même épisode + timestamps ≤ 15 s +
≥ 1 mot de titre commun (attrape les variantes garblées type « Valérie Le
Marseille »). Les clusters à ≥ 2 membres actifs sont présentés.
"""
from __future__ import annotations

import html
import re
import unicodedata
import urllib.parse

from review_render import _PLAYER_WRAP_HTML, _load_groups
from review_render_common import (
    _shell,
    _strip_french_quotes,
    _ts_seconds,
    _yt_timecode_link_parts,
)

_DOUBLON = re.compile(r"[Dd]oublon de (ubm-\d+)")
_TYPES = (("validate", "⭐ Reco"), ("citation", "📝 Citation"),
          ("guest-work", "🎭 Leur œuvre"))
_TS_WINDOW = 15  # secondes : deux recos si proches = même moment probable


def _norm(s: str | None) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "", s)


def _tokens(s: str | None) -> set[str]:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return {w for w in re.split(r"[^a-z0-9]+", s) if len(w) >= 4}


def collect_dup_clusters(source_id: str):
    """(source, episodes, clusters) — clusters = liste de listes de recos ACTIVES
    (≥2), triées meilleure d'abord (plus de liens/extractors)."""
    source, episodes, groups = _load_groups(source_id)
    byid = {r["id"]: r for recos in groups.values() for r in recos}
    ep_of = {i: r.get("episodeGuid") for i, r in byid.items()}

    parent: dict[str, str] = {}

    def find(x: str) -> str:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        parent[find(a)] = find(b)

    # Deux signaux HAUTE PRÉCISION (même épisode) — on ne relie PAS via les notes
    # « Doublon de » (imparfaites : lient album vs film-concert) ni via la seule
    # proximité de timestamp (mots communs génériques « spectacle », « Matrix »…).
    def _link_by(key_fn, min_len=1):
        buckets: dict[tuple, list[str]] = {}
        for i in byid:
            k = key_fn(byid[i])
            if k and len(k) >= min_len:
                buckets.setdefault((ep_of.get(i), k), []).append(i)
        for ids in buckets.values():
            for j in ids[1:]:
                union(ids[0], j)

    # signal 1 — titre normalisé identique
    _link_by(lambda r: _norm(r.get("title")))
    # signal 2 — quote normalisée identique (= même extraction). Longueur mini
    # pour éviter de grouper des quotes triviales/vides.
    _link_by(lambda r: _norm(r.get("quote"))[:80], min_len=15)

    groups_by_root: dict[str, list[str]] = {}
    for i in parent:
        groups_by_root.setdefault(find(i), []).append(i)
    clusters = []
    for members in groups_by_root.values():
        # « À trancher » = pas encore décidé par un humain (reviewedByHuman).
        # Critère volontairement basé là-dessus (et NON sur le statut) : (1) les
        # jumelles écartées par l'AGENT — pas par l'humain — restent à revoir (ex.
        # cluster Valérie Lemercier tout discardé par l'agent, l'humain veut en
        # garder une en citation) ; (2) après « Consolider », tout devient
        # reviewedByHuman → le cluster disparaît (même si on garde plusieurs recos
        # actives au même titre). Retour utilisateur 2026-07-23.
        # Membres ACTIFS non encore tranchés par un humain. Critère reviewedByHuman
        # (et non le simple statut) → APRÈS « Consolider », tout devient
        # reviewedByHuman et le cluster DISPARAÎT, même si on a gardé plusieurs
        # recos actives au même titre (bug signalé 2026-07-23). On ne montre QUE
        # les clusters à ≥2 actives : les cas « tout écarté par l'agent » (ex.
        # Valérie Lemercier) se restaurent dans /doutes (section « Confiance
        # faible ») — les inclure ici noierait la page (~69 clusters d'agent-discard).
        active_p = [byid[i] for i in members
                    if byid[i].get("status") != "discarded"
                    and not (byid[i].get("agentReview") or {}).get("reviewedByHuman")]
        if len(active_p) >= 2:
            active_p.sort(key=lambda r: (-len(r.get("links") or []),
                                         -len(r.get("extractors") or []), r["id"]))
            clusters.append(active_p)
    clusters.sort(key=lambda c: (c[0].get("episodeGuid", ""),
                                 _ts_seconds(c[0].get("timestamp")) or 0))
    return source, episodes, clusters


def _ep_label(ep: dict) -> str:
    s, n = ep.get("season"), ep.get("number")
    badge = f"S{s}·E{n} — " if s and n else ""
    return f'{badge}{ep.get("title", ep.get("guid", "?"))}'


def _member_row(r: dict, ep: dict, is_survivor: bool) -> str:
    rid = html.escape(r["id"])
    tcl = _yt_timecode_link_parts(r, ep)
    quote = _strip_french_quotes(r.get("quote") or "")[:140]
    cur = "guest-work" if r.get("guestWork") else r.get("kind", "reco")
    default = cur if cur in ("citation", "guest-work") else "validate"
    types = "".join(
        f'<label class="sig-radio sig-radio-{v}"><input type="radio" '
        f'name="type_{rid}" value="{v}"{" checked" if v == default else ""}> '
        f'{lbl}</label>' for v, lbl in _TYPES)
    quote_html = f'<p class="q">« {html.escape(quote)} »</p>' if quote else ""
    badge = ' <span class="dup-suggest">★ suggérée</span>' if is_survivor else ""
    is_disc = r.get("status") == "discarded"
    # Case cochée par défaut si la reco est ACTIVE (on la garde). Une reco déjà
    # écartée (par l'agent) est décochée → la cocher la RESTAURE. Sécurité : rien
    # ne se perd/change sans (dé)cochage explicite puis Consolider.
    checked = "" if is_disc else " checked"
    keep_label = "Restaurer" if is_disc else "Garder"
    return (
        f'<li class="dup-member{" dup-survivor" if is_survivor else ""}">'
        f'<label class="dup-keep"><input type="checkbox" name="keep" value="{rid}"'
        f'{checked}> {keep_label}</label>'
        f'<div class="dup-body">'
        f'<input class="dup-title" type="text" name="title_{rid}" '
        f'value="{html.escape(r.get("title") or "")}" aria-label="titre">{badge}'
        f'<span class="dup-meta">{tcl.html} · {html.escape(r.get("status", "?"))} '
        f'· {len(r.get("links") or [])} lien(s) · <code>{rid}</code></span>'
        f'{quote_html}<div class="sig-type dup-type">{types}</div>'
        f'</div></li>'
    )


def _render_cluster(members: list[dict], ep: dict) -> str:
    rows = "".join(_member_row(r, ep, i == 0) for i, r in enumerate(members))
    hidden = "".join(
        f'<input type="hidden" name="member" value="{html.escape(r["id"])}">'
        for r in members)
    return (
        f'<form class="dup-cluster" method="post" action="/consolidate">'
        f'{hidden}<input type="hidden" name="ep" value="{html.escape(ep.get("guid", ""))}">'
        f'<h3 class="dup-h">{html.escape(_ep_label(ep))} '
        f'<span class="cnt">{len(members)}</span></h3>'
        f'<p class="dup-hint">Tout est <b>gardé</b> par défaut. <b>Décoche</b> les '
        f'vrais doublons à écarter (corrige titre/type des gardées si besoin), puis '
        f'Consolider. Si ce ne sont pas des doublons (œuvres différentes citées '
        f'ensemble) : laisse tout coché ou ignore ce bloc.</p>'
        f'<ul class="dup-members">{rows}</ul>'
        f'<button type="submit" class="sig-ok">✓ Consolider</button>'
        f'</form>'
    )


def render_dedup_page(source_id: str, flash: str | None = None,
                      flash_kind: str = "info") -> str:
    from review_render_common import _flash_banner  # noqa: PLC0415
    source, episodes, clusters = collect_dup_clusters(source_id)
    banner = _flash_banner(flash, flash_kind)
    back = '<a class="back" href="/doutes">← doutes</a>'
    if not clusters:
        inner = (f"{banner}{back}<p>Aucun doublon intra-épisode à consolider. 🎉</p>")
        return _shell(source.get("title", source_id), "Doublons à consolider.", inner)
    body = [banner, back,
            f'<h1 class="doubt-ep-title">Doublons à consolider '
            f'<span class="cnt">{len(clusters)}</span></h1>',
            _PLAYER_WRAP_HTML]
    for members in clusters:
        ep = episodes.get(members[0].get("episodeGuid", ""),
                          {"guid": members[0].get("episodeGuid", "")})
        body.append(_render_cluster(members, ep))
    return _shell(source.get("title", source_id),
                  f"{len(clusters)} cluster(s) de doublons.", "".join(body))
