"""title_variants.py — les autres noms sous lesquels une œuvre se cherche.

Le corpus écrit souvent un titre ENRICHI : « Acharnés (Beef) » (titre français
puis original), « Sauf si c'est toi (reprise française de Until I Found You) »
(précision éditoriale). Les plateformes, elles, écrivent « Acharnés », « BEEF »,
ou « Sauf si c'est toi - Adaptation de Until i found you ». Comparer les
chaînes entières refusait ces œuvres pourtant bien trouvées : sur S6-E04, ces
deux recos ont fini sans aucun lien (« title-mismatch » et « no-match »), et
neuf liens ont dû être posés à la main.

Ce module ne décide de rien : il découpe. C'est à chaque appelant d'exiger, en
plus du titre, une seconde preuve (identifiant TMDB déjà posé, artiste
identique) — sans elle, un noyau de titre comme « Love » ne prouverait rien.
"""
from __future__ import annotations

import re

from common import normalize_text

# Un seul suffixe final : parenthèse ou crochet, ou « - suite » à la Spotify.
_PAREN = re.compile(r"^(?P<core>.+?)\s*[(\[](?P<inner>[^()\[\]]+)[)\]]\s*$")
_DASH = re.compile(r"^(?P<core>.+?)\s+[-–—]\s+(?P<inner>.+)$")

#: Mots qui, dans un suffixe, désignent une AUTRE version du même titre. Les
#: retrouver côté plateforme mais pas côté reco, c'est risquer de lier un live
#: ou un remix à la place du morceau recommandé : on s'abstient alors.
VERSION_MARKERS = frozenset({
    "live", "remix", "mix", "acoustic", "acoustique", "instrumental", "karaoke",
    "edit", "version", "piano", "demo", "session", "sessions", "extended", "radio",
    "remastered", "remaster", "orchestral", "symphonique", "unplugged",
})

#: Mots qui, dans un suffixe, désignent une PARTIE de l'œuvre : « Bref (saison
#: 2) » n'est pas « Bref » (la série de 2011 et Bref.2 sont deux fiches), « Vol.
#: 2 » n'est pas l'album « Vol. 1 ». Un tel suffixe interdit tout découpage.
PART_MARKERS = frozenset({
    "saison", "season", "tome", "volume", "vol", "partie", "part", "chapitre",
    "chapter", "episode", "livre",
})

#: En deçà, un noyau de titre se répète par coïncidence.
MIN_CORE = 4


def split_suffix(title: str | None) -> tuple[str, str]:
    """`(noyau, suffixe)` : le titre sans son dernier suffixe, et ce suffixe.

    `("", "")` : découpe impossible (pas de suffixe, noyau trop court, ou
    suffixe qui désigne une partie de l'œuvre).
    """
    text = (title or "").strip()
    for rx in (_PAREN, _DASH):
        m = rx.match(text)
        if not m or len(normalize_text(m["core"])) < MIN_CORE:
            continue
        if set(normalize_text(m["inner"]).split()) & PART_MARKERS:
            return "", ""
        return m["core"].strip(), m["inner"].strip()
    return "", ""


def variants(title: str | None) -> list[str]:
    """Titre entier, puis noyau, puis contenu du suffixe — normalisés, uniques."""
    core, inner = split_suffix(title)
    out: list[str] = []
    for v in (title, core, inner):
        n = normalize_text(v)
        if len(n) >= MIN_CORE and n not in out:
            out.append(n)
    return out


def is_other_version(reco_title: str | None, remote_title: str | None) -> bool:
    """True si le suffixe distant désigne une version que la reco ne nomme pas.

    « Ils s'aimaient toujours (Version piano) » n'est pas « Ils s'aimaient
    toujours » ; mais si la reco dit elle-même « (live) », le live est voulu.
    """
    _, inner = split_suffix(remote_title)
    distant = set(normalize_text(inner).split()) & VERSION_MARKERS
    if not distant:
        return False
    return not distant <= set(normalize_text(reco_title).split())


def cores_match(reco_title: str | None, remote_title: str | None) -> bool:
    """Même noyau de titre, sans glisser vers une autre version.

    Compare le noyau de chaque côté (le titre entier s'il n'a pas de suffixe).
    """
    if is_other_version(reco_title, remote_title):
        return False
    a = normalize_text(split_suffix(reco_title)[0] or reco_title)
    b = normalize_text(split_suffix(remote_title)[0] or remote_title)
    return len(a) >= MIN_CORE and a == b
