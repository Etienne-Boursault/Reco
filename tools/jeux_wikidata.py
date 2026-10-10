"""Site officiel et page Steam des jeux vidéo SANS studio, par Wikidata.

`liens_boutique` s'abstient sur ces jeux (« no-creator-to-verify ») : sans
studio, rien ne corrobore un titre sur Steam. Wikidata offre une autre ancre —
une entité dont le libellé est EXACTEMENT le titre et dont la nature est « jeu
vidéo » (P31 = Q7889) — et porte elle-même le site officiel (P856) et
l'identifiant Steam (P1733). Mesuré le 2026-10-10 sur Dofus (S6-E04) : Q1139866,
`http://www.dofus.com/`, Steam 254300.

GARDE-FOUS
----------
1. **Une seule entité** au libellé exact (fr ou en) parmi les jeux vidéo :
   « Catan » en rend trois (Q5051418, Q16266534, Q127929075) → `ambiguous`.
2. **Pas de jeu de société homonyme.** Le type `jeu` du corpus couvre aussi les
   jeux de société : une reco « Catan » vise sans doute le plateau, pas son
   adaptation. Un jeu de société, de cartes ou de rôle (Q131436, Q142714,
   Q1643932) portant ce nom en libellé OU en alias suffit à refuser. Les alias
   comptent ici, car le refus est la direction prudente : le plateau Q17271
   s'appelle « Les Colons de Catane » et n'a « Catan » qu'en alias.
3. **Un article Wikipédia (fr ou en).** Un jeu qu'on recommande dans un
   podcast en a un ; un homonyme obscur, non. Mesuré sur le corpus : la seule
   entité « Golden Axe » au libellé exact (Q123938492) n'a aucun article — ce
   n'est pas le jeu de 1989 que la reco désigne — et le plateau « Root » voisine
   avec une entité « Roots » sans article non plus.
4. **Steam doit vendre le jeu en France** : `appdetails?cc=fr` doit répondre
   `success: true` avec ce même `steam_appid`, de type `game`. Dofus n'y est
   plus (254300 → `success: false`) : son site est posé, pas de lien Steam.

La recherche de Wikidata ne fait que PROPOSER des entités : la décision tient
à l'égalité exacte du libellé, à la nature, et à l'unicité. Le site officiel
est pris tel que Wikidata le donne (cf. `wikidata_matching._url_site`).
"""
from __future__ import annotations

import argparse
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

import requests

import common
from boutique_links import BoutiqueInjoignable, steam_fiche
from boutique_matching import SOURCE_STEAM, TYPE_STEAM_JEU, url_steam
from common import log, normalize_text, parse_ids_option
from passe_liens import derouler
from wikidata_links import (
    RapportWikidata,
    WikidataInjoignable,
    _get,
    format_rapport,
)
from wikidata_matching import (
    RAISON_AMBIGUOUS,
    RAISON_HTTP_ERROR,
    RAISON_NO_ENTITY,
    RAISON_NO_NEW_LINK,
    RAISON_OK,
    RAISON_TYPE_INCOMPATIBLE,
    SOURCE_SITE,
    Lien,
    Resolution,
    _url_site,
    hote,
)

TYPE_JEU = "jeu"
NATURE_JEU_VIDEO = "Q7889"
#: Jeu de société, jeu de cartes, jeu de rôle sur table (libellés vérifiés).
NATURES_HOMONYMES = ("Q131436", "Q142714", "Q1643932")
PREUVE = "libelle+nature"
RAISON_HOMONYME = "tabletop-homonym"
RAISON_SANS_ARTICLE = "no-wikipedia-article"
WIKIS_NOTOIRES = ("frwiki", "enwiki")
PAUSE = 0.4


def servie(reco: dict[str, Any]) -> bool:
    """Les jeux SANS studio : ceux qui ont un studio relèvent de `liens_boutique`."""
    return TYPE_JEU in (reco.get("types") or []) and not str(reco.get("creator") or "").strip()


def noms(brut: dict[str, Any], *, alias: bool) -> set[str]:
    """Libellés fr/en normalisés d'une entité brute, plus ses alias si demandé."""
    trouves = {normalize_text(v.get("value"))
               for v in (brut.get("labels") or {}).values()}
    if alias:
        trouves |= {normalize_text(a.get("value"))
                    for valeurs in (brut.get("aliases") or {}).values() for a in valeurs}
    return trouves - {""}


def valeurs(brut: dict[str, Any], prop: str) -> list[str]:
    """Valeurs d'une propriété d'une entité brute (identifiant d'item ou chaîne)."""
    sortie = []
    for enonce in (brut.get("claims") or {}).get(prop, []):
        donnee = (enonce.get("mainsnak") or {}).get("datavalue", {}).get("value")
        if isinstance(donnee, dict):
            donnee = donnee.get("id")
        if isinstance(donnee, str) and donnee:
            sortie.append(donnee)
    return sortie


def entites(session: requests.Session, titre: str, natures: Sequence[str]
            ) -> dict[str, dict[str, Any]]:
    """Entités brutes proposées par la recherche, restreinte à ces natures."""
    filtre = "|".join(f"P31={q}" for q in natures)
    donnees = _get(session, {"action": "query", "list": "search", "srnamespace": "0",
                             "srlimit": "10",
                             "srsearch": f"{titre} haswbstatement:{filtre}"})
    qids = [r["title"] for r in (donnees.get("query") or {}).get("search", [])
            if str(r.get("title", "")).startswith("Q")]
    if not qids:
        return {}
    detail = _get(session, {"action": "wbgetentities", "ids": "|".join(qids),
                            "props": "labels|aliases|claims|sitelinks",
                            "languages": "fr|en"})
    return {qid: brut for qid, brut in (detail.get("entities") or {}).items()
            if "missing" not in brut}


def verdict(titre: str, jeux: dict[str, dict[str, Any]],
            homonymes: dict[str, dict[str, Any]]) -> tuple[str, str | None, str]:
    """(raison, qid retenu, détail). Aucun réseau."""
    voulu = normalize_text(titre)
    exacts = [qid for qid, brut in jeux.items() if voulu in noms(brut, alias=False)]
    if not exacts:
        return RAISON_NO_ENTITY, None, ""
    if len(exacts) > 1:
        return RAISON_AMBIGUOUS, None, " ".join(sorted(exacts))
    qid = exacts[0]
    if NATURE_JEU_VIDEO not in valeurs(jeux[qid], "P31"):
        return RAISON_TYPE_INCOMPATIBLE, qid, ",".join(valeurs(jeux[qid], "P31"))
    if not set(jeux[qid].get("sitelinks") or {}) & set(WIKIS_NOTOIRES):
        return RAISON_SANS_ARTICLE, qid, ""
    plateaux = sorted(q for q, brut in homonymes.items() if voulu in noms(brut, alias=True))
    if plateaux:
        return RAISON_HOMONYME, qid, " ".join(plateaux)
    return RAISON_OK, qid, ""


def resoudre(reco: dict[str, Any], *, session: requests.Session) -> Resolution:
    titre = str(reco.get("title") or "")
    try:
        jeux = entites(session, titre, (NATURE_JEU_VIDEO,))
        homonymes = entites(session, titre, NATURES_HOMONYMES) if jeux else {}
    except WikidataInjoignable as exc:
        return Resolution((), RAISON_HTTP_ERROR, detail=str(exc))
    raison, qid, detail = verdict(titre, jeux, homonymes)
    if raison != RAISON_OK:
        return Resolution((), raison, None, qid, detail)

    deja = {hote(str(e.get("url") or "")) for e in reco.get("links") or []}
    liens: list[Lien] = []
    site = next(iter(valeurs(jeux[qid], "P856")), "")
    url = _url_site(site) if site else None
    if url and hote(url) not in deja:
        liens.append(Lien(SOURCE_SITE.nom, SOURCE_SITE.kind, SOURCE_SITE.ethics,
                          SOURCE_SITE.label, url))
    appid = next(iter(valeurs(jeux[qid], "P1733")), "")
    if appid.isdigit() and hote(url_steam(int(appid))) not in deja:
        try:
            fiche = steam_fiche(session, int(appid))
        except BoutiqueInjoignable as exc:
            fiche, detail = None, f"steam : {exc}"
        if fiche and fiche.get("type") == TYPE_STEAM_JEU:
            liens.append(Lien(SOURCE_STEAM.nom, SOURCE_STEAM.kind, SOURCE_STEAM.ethics,
                              SOURCE_STEAM.label, url_steam(int(appid))))
        elif not detail:
            detail = f"steam {appid} hors vente en France"
    if not liens:
        return Resolution((), RAISON_NO_NEW_LINK, PREUVE, qid, detail)
    return Resolution(tuple(liens), RAISON_OK, PREUVE, qid, detail)


def run(*, root: Path, session: requests.Session | None = None,
        source: str | None = None, ids: Iterable[str] = (),
        apply: bool = False, sleep: float = PAUSE) -> RapportWikidata:
    session = session or requests.Session()
    return derouler(root=root, source=source, ids=ids, servie=servie,
                    resoudre=lambda reco: resoudre(reco, session=session),
                    apply=apply, sleep=sleep)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Site officiel et Steam des jeux vidéo sans studio, par Wikidata.")
    parser.add_argument("--source")
    parser.add_argument("--root", type=Path, help="dossier des recos (défaut : le corpus)")
    parser.add_argument("--ids", help="ids de recos séparés par des virgules")
    parser.add_argument("--apply", action="store_true", help="écrire (défaut : simulation)")
    args = parser.parse_args(argv)
    rapport = run(root=args.root or common.RECOS_DIR, source=args.source,
                  ids=parse_ids_option(args.ids), apply=args.apply)
    log.info("%s", format_rapport(rapport))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
