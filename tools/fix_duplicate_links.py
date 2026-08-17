"""
fix_duplicate_links.py — retire les liens qui font doublon dans une même reco.

DEUX RÈGLES, INDÉPENDANTES, chacune activable seule (`--rule`). Elles ne
partagent que le socle : ce qui les sépare, c'est ce qui rend deux liens
redondants, et ça n'a rien d'universel.

CE QUI N'EST PAS UN DOUBLON
---------------------------
L'audit du 2026-08-15 a passé les 1209 recos actives au crible. La plupart des
paires sur un même hôte sont COMPLÉMENTAIRES, et les supprimer appauvrirait la
carte :

    page artiste + album (Deezer, Qobuz)   morceau + album (Spotify)
    série + tome 1 (Glénat)                deux spectacles distincts (Netflix)
    recherche par auteur + un livre précis (Place des Libraires)

Ce module ne touche donc QUE les deux familles ci-dessous, identifiées une par
une. Aucune heuristique « même hôte donc doublon » : elle se tromperait sur la
majorité des cas.

RÈGLE `allocine` — la fiche et ses onglets
-------------------------------------------
AlloCiné sert la même œuvre sous deux URL portant le MÊME identifiant :

    https://www.allocine.fr/film/fichefilm_gen_cfilm=6608.html   ← la fiche
    https://www.allocine.fr/film/fichefilm-6608/telecharger-vod/ ← un onglet

L'onglet n'est qu'une section de la fiche. On garde la fiche : le visiteur y
accède à tout le reste, l'inverse n'est pas vrai. Le rapprochement se fait sur
l'IDENTIFIANT, jamais sur le titre.

RÈGLE `editions` — deux éditions du même livre
-----------------------------------------------
Un même ouvrage listé deux fois chez Place des Libraires, en grand format et en
poche. La règle est une TABLE CURÉE À LA MAIN (`EDITIONS`), pas une heuristique
de prix : le moins cher est presque toujours le poche, mais « presque » ne
suffit pas quand deux ISBN peuvent désigner deux TRADUCTIONS différentes.

C'est le cas du Tao Te King (`ubm-1145`), volontairement ABSENT de la table :
Folio Sagesses et Quadrige sont deux traductions, et n'en garder qu'une revient
à choisir un traducteur — un acte éditorial, pas un nettoyage de doublon.

Usage :
    python fix_duplicate_links.py                       # dry-run, les 2 règles
    python fix_duplicate_links.py --rule allocine --apply
"""
from __future__ import annotations

import argparse
import re
from collections.abc import Sequence
from typing import Any
from urllib.parse import parse_qs, urlparse

import dataset_fixes
from dataset_fixes import Change, add_common_args, run

__all__ = ["EDITIONS", "RULES", "allocine_key", "transform_factory"]

#: Fiche canonique : `…_gen_cfilm=<id>.html`. C'est elle qu'on garde.
_RE_FICHE = re.compile(
    r"allocine\.fr/(?:film|series)/fiche(?:film|serie)_gen_c(?:film|serie)=(\d+)",
    re.IGNORECASE)
#: Onglet d'une fiche : `…/fichefilm-<id>/<section>/`. Redondant avec la fiche.
_RE_ONGLET = re.compile(
    r"allocine\.fr/(?:film|series)/fiche(?:film|serie)-(\d+)/[a-z-]+/?$",
    re.IGNORECASE)

#: ISBN à CONSERVER, par reco. Vérifié un par un chez Place des Libraires le
#: 2026-08-15 (collection + prix) : dans chaque cas, l'ISBN retenu est l'édition
#: de poche. Une reco absente de cette table n'est pas touchée.
EDITIONS: dict[str, str] = {
    "ubm-0392": "9791041425723",   # L'homme-dé — Points, 10,80 € (vs 20 €)
    "ubm-0760": "9782070360284",   # Voyage au bout de la nuit — Folio, 11,20 €
    "ubm-1158": "9782253907824",   # La Prochaine fois… — Livre de Poche, 8,40 €
    "ubm-1169": "9782253907824",   # idem, seconde reco du même livre
    "ubm-2741": "9782811218393",   # Blood Song — Bragelonne poche, 7,90 €
    "ubm-2850": "9782253162889",   # Mouchette — Livre de Poche, 9,70 €
    "ubm-2948": "9782290028599",   # Les Particules élémentaires — J'ai lu, 8,70 €
    # ABSENT À DESSEIN — ubm-1145 « Tao Te King » : Folio Sagesses et Quadrige
    # sont deux TRADUCTIONS, pas deux formats. Choisir relève de l'éditorial.
}

_RE_PDL_ISBN = re.compile(r"placedeslibraires\.fr/livre/(\d{13})", re.IGNORECASE)

RULES = ("allocine", "editions", "variantes", "racine")


def allocine_key(url: str) -> tuple[str, str] | None:
    """`("fiche"|"onglet", identifiant)` si l'URL est une page d'œuvre AlloCiné.

    Une URL AlloCiné qui n'est ni l'une ni l'autre (page d'accueil, dossier,
    actualité) renvoie None et n'est jamais touchée.
    """
    if m := _RE_FICHE.search(url):
        return "fiche", m.group(1)
    if m := _RE_ONGLET.search(url):
        return "onglet", m.group(1)
    return None


def _rule_allocine(doc: dict[str, Any], liens: list[dict]) -> tuple[list[dict], list[Change]]:
    """Retire un onglet quand la FICHE du même identifiant est présente."""
    fiches = {k[1] for link in liens
              if (k := allocine_key(link.get("url") or "")) and k[0] == "fiche"}
    garder, changes = [], []
    for link in liens:
        cle = allocine_key(link.get("url") or "")
        if cle and cle[0] == "onglet" and cle[1] in fiches:
            changes.append(Change(field="links[].url", before=link["url"], after=None))
            continue
        garder.append(link)
    return garder, changes


def _rule_editions(doc: dict[str, Any], liens: list[dict]) -> tuple[list[dict], list[Change]]:
    """Ne garde que l'ISBN retenu, pour les recos listées dans `EDITIONS`."""
    isbn_garde = EDITIONS.get(doc.get("id") or "")
    if not isbn_garde:
        return liens, []
    # Ne rien supprimer si l'ISBN attendu n'est PAS là : la donnée a changé
    # depuis la vérification, et la table doit être revue avant d'agir.
    presents = {m.group(1) for link in liens
                if (m := _RE_PDL_ISBN.search(link.get("url") or ""))}
    if isbn_garde not in presents or len(presents) < 2:
        return liens, []
    garder, changes = [], []
    for link in liens:
        m = _RE_PDL_ISBN.search(link.get("url") or "")
        if m and m.group(1) != isbn_garde:
            changes.append(Change(field="links[].url", before=link["url"], after=None))
            continue
        garder.append(link)
    return garder, changes




# ---------------------------------------------------------------------------
# RÈGLE `variantes` — la même page sous deux adresses
#
# Trois formes relevées sur le corpus, toutes menant au MÊME contenu :
#
#     segment de langue   netflix.com/title/70143836
#                         netflix.com/fr-en/title/70143836
#                         open.spotify.com/album/X · /intl-fr/album/X
#                         hbomax.com/fr/en/shows/…/ID · /fr/fr/shows/…/ID
#     libellé facultatif  primevideo.com/-/fr/detail/ID
#                         primevideo.com/-/fr/detail/Fleabag/ID
#     paramètre de suivi  music.apple.com/…/1588117066?uo=4
#
# On garde la forme la PLUS COURTE : elle est stable, tandis qu'un segment de
# langue fige la langue du visiteur et qu'un libellé bouge avec le titre
# commercial. Le rapprochement se fait sur l'EMPREINTE — hôte plus identifiant
# —, jamais sur le titre du lien.
# ---------------------------------------------------------------------------

#: Segments à ignorer dans un chemin : langues (`fr`, `fr-en`, `intl-fr`) et
#: séparateurs de Prime Video.
_RE_LANGUE = re.compile(r"^(?:intl-)?[a-z]{2}(?:-[a-z]{2})?$", re.IGNORECASE)

#: Paramètres qui ne changent pas la cible. `list` en est ABSENT : sur
#: `/playlist?list=…` il EST l'identifiant, et l'ignorer confondrait deux
#: playlists distinctes.
_PARAMS_SUIVI = frozenset({
    "uo", "at", "app", "ls", "i", "si", "index", "t", "pp", "feature",
    "utm_source", "utm_medium", "utm_campaign", "utm_content",
})

#: Identifiant reconnaissable en fin d'URL, par site. Sert à rapprocher deux
#: adresses dont seuls les segments décoratifs diffèrent.
_RE_ID_FINAL = re.compile(r"[A-Za-z0-9]{8,}$")


def empreinte_variante(url: str) -> str | None:
    """Empreinte d'une URL, débarrassée de ce qui ne change pas sa cible.

    Renvoie None si l'URL n'expose aucun identifiant exploitable : sans lui,
    deux adresses ne peuvent pas être déclarées équivalentes, et on préfère
    garder les deux liens plutôt que d'en supprimer un au jugé.
    """
    try:
        p = urlparse(url)
    except ValueError:
        return None
    hote = (p.hostname or "").lower().removeprefix("www.")
    if not hote:
        return None
    segments = [s for s in p.path.split("/") if s and s != "-"]
    # Les segments de langue disparaissent, où qu'ils soient dans le chemin.
    segments = [s for s in segments if not _RE_LANGUE.match(s)]
    if not segments:
        return None
    # L'identifiant est le dernier segment qui en a l'allure ; ce qui le
    # précède (libellé, titre commercial) est décoratif.
    identifiant = next((s for s in reversed(segments) if _RE_ID_FINAL.match(s)), None)
    if identifiant is None:
        return None
    params = sorted(f"{k}={v[0]}" for k, v in parse_qs(p.query).items()
                    if k not in _PARAMS_SUIVI)
    # Le type de page (`title`, `album`, `shows`…) reste dans l'empreinte :
    # un album et un morceau de même identifiant ne sont pas la même page.
    genre = next((s for s in segments if s != identifiant), "")
    return "|".join([hote, genre, identifiant, *params])


#: Segment désignant explicitement le français. « fr-en » n'en est PAS un :
#: c'est la convention pays-langue de Netflix, « France, en anglais ».
_LANGUE_FR = re.compile(r"^(?:intl-)?fr(?:-fr)?$", re.IGNORECASE)


def _preference(link: dict) -> tuple[int, int, int]:
    """Ordre de préférence entre deux adresses équivalentes.

    L'ABSENCE de segment de langue l'emporte, et ce n'est pas un détail : sans
    lui, la plateforme redirige selon le visiteur. C'est la décision déjà prise
    pour les URL Deezer (cf. `fix_deezer_locale`), et pour la même raison — ce
    site est DUPLICABLE, un fork peut être anglophone, et câbler le français en
    dur lui imposerait un choix franco-centré.

    Entre deux adresses qui portent toutes deux une langue, on préfère le
    français au reste (« /fr/ » plutôt que « /gf/ »), puis la plus courte.
    """
    url = link.get("url") or ""
    try:
        segments = [s for s in urlparse(url).path.split("/") if s]
    except ValueError:
        segments = []
    langues = [s for s in segments if _RE_LANGUE.match(s)]
    return (1 if langues else 0,
            0 if any(_LANGUE_FR.match(s) for s in langues) else 1,
            len(url))


def _rule_variantes(doc: dict[str, Any], liens: list[dict]) -> tuple[list[dict], list[Change]]:
    """Ne garde qu'une adresse par empreinte : la plus courte."""
    par_empreinte: dict[str, list[dict]] = {}
    sans_empreinte = []
    for link in liens:
        emp = empreinte_variante(link.get("url") or "")
        if emp is None:
            sans_empreinte.append(link)
        else:
            par_empreinte.setdefault(emp, []).append(link)

    garder, changes = list(sans_empreinte), []
    for groupe in par_empreinte.values():
        if len(groupe) == 1:
            garder.append(groupe[0])
            continue
        gagnant = min(groupe, key=_preference)
        garder.append(gagnant)
        for link in groupe:
            if link is not gagnant:
                changes.append(Change(field="links[].url",
                                      before=link.get("url"), after=None))
    # L'ordre d'origine est préservé : la carte affiche les liens dans l'ordre
    # du fichier, et le bousculer changerait l'apparence sans raison.
    ordre = {id(link): i for i, link in enumerate(liens)}
    garder.sort(key=lambda link: ordre.get(id(link), 0))
    return garder, changes


# ---------------------------------------------------------------------------
# RÈGLE `racine` — l'accueil d'un site quand une page précise existe
#
#     bigfloetoli.com/                  ← n'apprend rien de plus
#     bigfloetoli.com/products/cd-karma ← l'œuvre recommandée
#
# La page d'accueil ne mène à l'œuvre qu'au prix d'une recherche ; l'inverse
# n'est pas vrai. On ne la retire QUE si une page profonde du même hôte est
# présente — seule, elle reste le meilleur lien disponible.
# ---------------------------------------------------------------------------
def _est_racine(url: str) -> bool:
    try:
        p = urlparse(url)
    except ValueError:
        return False
    return not [s for s in p.path.split("/") if s] and not p.query


def _rule_racine(doc: dict[str, Any], liens: list[dict]) -> tuple[list[dict], list[Change]]:
    def _hote(url: str) -> str:
        """`urlparse` LÈVE sur un IPv6 malformé (« https://[::1 ») : une seule
        URL saisie de travers ferait tomber la passe entière."""
        try:
            return (urlparse(url).hostname or "").lower()
        except ValueError:
            return ""

    profonds = {h for link in liens
                if link.get("url") and not _est_racine(link["url"])
                and (h := _hote(link["url"]))}
    garder, changes = [], []
    for link in liens:
        url = link.get("url") or ""
        hote = _hote(url)
        if url and _est_racine(url) and hote in profonds:
            changes.append(Change(field="links[].url", before=url, after=None))
            continue
        garder.append(link)
    return garder, changes


_IMPLS = {"allocine": _rule_allocine, "editions": _rule_editions,
          "variantes": _rule_variantes, "racine": _rule_racine}


def transform_factory(rules: Sequence[str]):
    """Construit la transformation pour les règles demandées."""
    impls = [_IMPLS[r] for r in rules]

    def transform(doc: dict[str, Any]) -> list[Change]:
        liens = [link for link in (doc.get("links") or []) if isinstance(link, dict)]
        autres = [link for link in (doc.get("links") or []) if not isinstance(link, dict)]
        changes: list[Change] = []
        for impl in impls:
            liens, ch = impl(doc, liens)
            changes.extend(ch)
        if changes:
            doc["links"] = autres + liens if autres else liens
        return changes

    return transform


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Retire les liens redondants d'une même reco.")
    add_common_args(parser)
    parser.add_argument("--rule", action="append", choices=RULES,
                        help="Règle à appliquer (répétable). Défaut : toutes.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:  # pragma: no cover - E/S
    args = build_parser().parse_args(argv)
    rules = args.rule or list(RULES)
    run(transform_factory(rules), args,
        roots=(dataset_fixes.RECOS_DIR,), extra_report={"rules": rules})
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
