"""
normalize_youtube_channels.py — une seule forme d'URL par chaîne YouTube.

YouTube désigne la même chaîne de quatre façons, et le corpus les mélange :

    https://www.youtube.com/@Fouloscopie                      ← la forme voulue
    https://www.youtube.com/channel/UCLXDNUOO3EQ80VmD9nQBHPg
    https://www.youtube.com/c/verinaze                        (hérité)
    https://www.youtube.com/user/PewDiePie                    (hérité)

Conséquence visible : une même reco porte parfois DEUX liens qui mènent au même
endroit (31 recos au 2026-08-15), et deux recos de la même chaîne ne se
ressemblent pas. Ce correctif ramène tout au format `@pseudo`.

CE QUE LE PSEUDO COÛTE, ET COMMENT ON LE PAIE
---------------------------------------------
`@pseudo` est lisible mais RENOMMABLE : un créateur qui change de pseudo casse
le lien. `UC…` ne bouge jamais mais n'apprend rien à personne. On garde donc
les deux : le lien VISIBLE passe en `@pseudo`, et l'identifiant part dans
`externalIds.youtubeChannelId`, d'où le lien peut être reconstruit.

RÉSOLUTION — CE QU'ON INTERROGE, ET POURQUOI CELUI-LÀ
-----------------------------------------------------
Le pseudo ne se déduit pas de l'identifiant : il faut demander à YouTube. Trois
champs de la page ont été essayés (2026-08-15) :

  - `<link rel="canonical">`  → renvoie `/channel/UC…`, jamais le pseudo. Inutile.
  - `"vanityChannelUrl"`      → absent des pages servies à ce client.
  - `"canonicalBaseUrl":"/@…"` → présent et exact sur les QUATRE formes d'URL.

C'est donc `canonicalBaseUrl` qui fait autorité ici.

**Un 200 ne prouve rien.** YouTube répond 200 à une chaîne inexistante, avec un
corps de page vide de tout marqueur. La preuve d'existence est donc la présence
CONJOINTE du pseudo et du titre (`og:title`), pas le code HTTP — c'est le piège
documenté du dépôt sur la vérification des liens.

CE QUE CE CORRECTIF NE FAIT JAMAIS
-----------------------------------
Il ne fusionne DEUX liens que si les deux résolvent vers le MÊME identifiant de
chaîne. Une reco peut légitimement pointer une chaîne principale et une chaîne
secondaire : les confondre supprimerait un vrai lien. En cas de désaccord, les
deux liens sont conservés et la reco est signalée dans le rapport.

Il n'invente aucune URL : une chaîne qu'on n'arrive pas à résoudre (réseau,
chaîne supprimée, pas de pseudo) garde son lien d'origine, avec la raison dans
le rapport.

Usage :
    python normalize_youtube_channels.py                       # dry-run (défaut)
    python normalize_youtube_channels.py --json rapport.json
    python normalize_youtube_channels.py --apply
"""
from __future__ import annotations

import argparse
import json
import re
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import dataset_fixes
from common import OUTPUT_DIR, log
from dataset_fixes import Change, add_common_args, run

__all__ = [
    "CACHE_PATH",
    "Resolution",
    "channel_key",
    "handle_url",
    "parse_channel_page",
    "resolve",
    "transform_factory",
]

#: Sous-domaines acceptés : `www.`, `m.` (version mobile du MÊME site) ou
#: aucun. `music.youtube.com` en est VOLONTAIREMENT exclu — l'alternative
#: `m\.` ne peut pas le capturer par accident (« m » y est suivi de « u »).
#: YouTube Music est un service distinct : ses liens sont des liens d'ÉCOUTE,
#: pas des liens de chaîne vidéo, et deux cas réels du corpus le montrent —
#: pour « Dissiz » l'identifiant est le même que celui de la chaîne vidéo, pour
#: « Willylancien » il diffère (chaîne générée par YouTube Music). Les
#: convertir changerait la destination du lien ; ils restent donc intacts.
_HOTE = r"^https?://(?:www\.|m\.)?youtube\.com"

#: Formes d'URL de chaîne reconnues. L'ordre ne compte pas : elles s'excluent.
_RE_HANDLE = re.compile(_HOTE + r"/(@[^/?#]+)/?", re.IGNORECASE)
_RE_CHANNEL = re.compile(_HOTE + r"/channel/(UC[\w-]+)/?", re.IGNORECASE)
_RE_LEGACY = re.compile(_HOTE + r"/(?:c|user)/([^/?#]+)/?", re.IGNORECASE)

#: Marqueurs lus dans la page de chaîne (cf. docstring).
_RE_BASE_URL = re.compile(r'"canonicalBaseUrl":"/(@[^"]+)"')
_RE_CANONICAL_ID = re.compile(
    r'<link rel="canonical" href="https://www\.youtube\.com/channel/(UC[\w-]+)"')
_RE_OG_TITLE = re.compile(r'<meta property="og:title" content="([^"]*)"')

#: Identifiant de chaîne valide : `UC` + 22 caractères. Le même motif garde le
#: schéma Zod — les deux doivent rester d'accord.
_RE_UC = re.compile(r"^UC[\w-]{22}$")

#: Réponses réseau mises en cache : une chaîne recommandée dans 5 épisodes ne
#: doit être interrogée qu'UNE fois, et une relance après interruption ne doit
#: pas tout refaire. Sous `tools/output/`, donc hors du build.
CACHE_PATH: Path = OUTPUT_DIR / "youtube_channels_cache.json"

#: Raisons stables (agrégats du rapport).
REASON_OK = "resolu"
REASON_NO_HANDLE = "chaine-sans-pseudo"
REASON_UNKNOWN = "chaine-introuvable"
REASON_HTTP = "erreur-reseau"
REASON_CONFLICT = "deux-chaines-differentes"
REASON_ALREADY = "deja-au-format-pseudo"

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/120 Safari/537.36")


class Resolution(dict):
    """Résultat de résolution d'une URL : `{handle, channelId, title, reason}`.

    Un `dict` et non une dataclass : il est sérialisé tel quel dans le cache et
    dans le rapport JSON, sans conversion.
    """


def channel_key(url: str) -> tuple[str, str] | None:
    """`(genre, valeur)` de l'URL de chaîne, ou None si ce n'en est pas une.

    Genres : `handle` (@pseudo), `channel` (UC…), `legacy` (/c/ ou /user/).
    Une URL de VIDÉO (`/watch?v=`) ou de playlist n'est pas une chaîne et
    renvoie None — ce correctif n'y touche pas.
    """
    for genre, rx in (("handle", _RE_HANDLE), ("channel", _RE_CHANNEL),
                      ("legacy", _RE_LEGACY)):
        m = rx.match(url.strip())
        if m:
            return genre, m.group(1)
    return None


def handle_url(handle: str) -> str:
    """URL canonique d'une chaîne à partir de son pseudo (`@` compris)."""
    return f"https://www.youtube.com/{handle}"


def parse_channel_page(html: str) -> Resolution:
    """Extrait pseudo, identifiant et titre d'une page de chaîne.

    L'existence de la chaîne se prouve par le TITRE, pas par le code HTTP :
    YouTube sert un 200 pour un identifiant inexistant.
    """
    handle = m.group(1) if (m := _RE_BASE_URL.search(html)) else None
    chan = m.group(1) if (m := _RE_CANONICAL_ID.search(html)) else None
    titre = m.group(1) if (m := _RE_OG_TITLE.search(html)) else None
    if not titre:
        return Resolution(handle=None, channelId=None, title=None,
                          reason=REASON_UNKNOWN)
    if not handle:
        # Chaîne réelle mais sans pseudo public : rare, et parfaitement légitime.
        return Resolution(handle=None, channelId=chan, title=titre,
                          reason=REASON_NO_HANDLE)
    return Resolution(handle=handle, channelId=chan, title=titre,
                      reason=REASON_OK)


def _load_cache() -> dict[str, Any]:
    try:
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save_cache(cache: dict[str, Any]) -> None:
    try:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=2,
                                         sort_keys=True) + "\n", encoding="utf-8")
    except OSError as exc:                       # pragma: no cover - disque plein
        log.warning("Cache non écrit (%s)", exc)


def resolve(url: str, cache: dict[str, Any], session: Any,
            pause: float = 0.3) -> Resolution:
    """Résout une URL de chaîne vers `{handle, channelId, title, reason}`.

    Le cache est consulté AVANT le réseau et alimenté après : une chaîne citée
    dans plusieurs épisodes n'est interrogée qu'une fois.
    """
    if url in cache:
        return Resolution(cache[url])
    try:
        r = session.get(url, timeout=30)
        res = parse_channel_page(r.text)
    except Exception as exc:                     # noqa: BLE001 - réseau hostile
        # PAS mis en cache : une panne réseau est transitoire, la relance doit
        # pouvoir réessayer. Seul un verdict s'écrit dans le cache.
        log.warning("  %s → %s", url, exc)
        return Resolution(handle=None, channelId=None, title=None,
                          reason=REASON_HTTP)
    cache[url] = dict(res)
    time.sleep(pause)
    return res


def _links_of(doc: dict[str, Any]) -> list[dict[str, Any]]:
    return [link for link in (doc.get("links") or []) if isinstance(link, dict)]


def transform_factory(resolver, report: dict[str, Any]):
    """Construit la transformation. `resolver(url)` renvoie une `Resolution`.

    Injecté plutôt que codé en dur : les tests fournissent un résolveur en
    mémoire, et aucune suite de tests ne part sur le réseau.
    """
    def transform(doc: dict[str, Any]) -> list[Change]:
        liens = _links_of(doc)
        cibles = [(i, link) for i, link in enumerate(liens)
                  if channel_key(link.get("url") or "")]
        if not cibles:
            return []

        # 1. Résoudre chaque lien de chaîne vers son identifiant permanent.
        resolus: dict[int, Resolution] = {}
        for i, link in cibles:
            genre, _ = channel_key(link["url"])
            res = resolver(link["url"])
            resolus[i] = res
            if genre == "handle" and res.get("reason") == REASON_OK:
                res["reason"] = REASON_ALREADY

        ids = {r.get("channelId") for r in resolus.values() if r.get("channelId")}
        if len(ids) > 1:
            # Chaîne principale + chaîne secondaire : ce ne sont PAS des
            # doublons. On ne touche à rien et on signale.
            report.setdefault("conflits", []).append({
                "id": doc.get("id"), "title": doc.get("title"),
                "urls": [link["url"] for _, link in cibles],
                "channelIds": sorted(ids),
            })
            return []

        changes: list[Change] = []

        # 2. Réécrire chaque lien vers la forme `@pseudo`.
        vus: set[str] = set()
        garder: list[dict[str, Any]] = []
        # `enumerate` et non `liens.index(link)` : deux liens au contenu
        # identique sont égaux au sens de `==`, et `index` renverrait alors
        # deux fois le même rang — donc la résolution du premier pour le second.
        for i, link in enumerate(liens):
            cle = channel_key(link.get("url") or "")
            if cle is None:
                garder.append(link)
                continue
            res = resolus.get(i) or {}
            handle = res.get("handle")
            if not handle:
                garder.append(link)              # non résolu : on n'invente rien
                continue
            cible = handle_url(handle)
            if cible in vus:
                # Doublon franc : la même chaîne était déjà listée.
                changes.append(Change(field="links[].url",
                                      before=link["url"], after=None))
                continue
            vus.add(cible)
            if link["url"] != cible:
                changes.append(Change(field="links[].url",
                                      before=link["url"], after=cible))
                link["url"] = cible
            garder.append(link)

        if len(garder) != len(liens):
            doc["links"] = garder

        # 3. Conserver l'identifiant permanent, que le pseudo peut trahir.
        chan = next(iter(ids), None)
        if chan and _RE_UC.match(chan):
            ext = doc.setdefault("externalIds", {})
            if ext.get("youtubeChannelId") != chan:
                changes.append(Change(field="externalIds.youtubeChannelId",
                                      before=ext.get("youtubeChannelId"),
                                      after=chan))
                ext["youtubeChannelId"] = chan
        return changes

    return transform


def _build_session():                            # pragma: no cover - réseau réel
    import requests
    s = requests.Session()
    s.headers.update({"User-Agent": _UA, "Accept-Language": "fr-FR,fr;q=0.9"})
    # Sans ce cookie, YouTube sert le mur de consentement à la place de la page.
    s.cookies.set("SOCS", "CAI", domain=".youtube.com")
    return s


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Normalise les URL de chaînes YouTube au format @pseudo.")
    add_common_args(parser)
    parser.add_argument("--pause", type=float, default=0.3,
                        help="Délai entre deux appels YouTube (défaut : 0.3 s).")
    return parser


def main(argv: Sequence[str] | None = None) -> int:  # pragma: no cover - E/S
    args = build_parser().parse_args(argv)
    cache = _load_cache()
    session = _build_session()
    rapport: dict[str, Any] = {}

    def resolver(url: str):
        return resolve(url, cache, session, args.pause)

    try:
        run(transform_factory(resolver, rapport), args,
            roots=(dataset_fixes.RECOS_DIR, dataset_fixes.ITEMS_DIR),
            extra_report=rapport)
    finally:
        _save_cache(cache)                       # même si l'on interrompt
    for c in rapport.get("conflits", []):
        log.warning("  CONFLIT %s « %s » → %s", c["id"], c["title"], c["channelIds"])
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
