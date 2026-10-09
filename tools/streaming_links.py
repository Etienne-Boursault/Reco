"""Liens directs des plateformes vidéo : interroge, résout une reco, écrit.

Les garde-fous et la doctrine sont dans `streaming_matching` ; ce module fait
les appels. Trois chemins réseau :
  Wikidata   l'entité qui déclare l'identifiant TMDB de la reco (`haswbstatement`,
             le client de `wikidata_links`, donc son agent et ses pannes typées) ;
  pages      Apple TV, Disney+ (anciens identifiants) et Prime Video, ouvertes
             pour lire l'URL que le site DÉCLARE plutôt que la fabriquer ;
  ARTE       la recherche rendue côté serveur, puis la page candidate.

    python streaming_links.py --source un-bon-moment --ids ubm-3260,ubm-3262
    python streaming_links.py --source un-bon-moment --ids ubm-3260 --apply
"""
from __future__ import annotations

import argparse
import re
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

import requests

import common
from common import log, parse_ids_option
from passe_liens import derouler
from streaming_matching import (
    A_RESOUDRE,
    RAISON_ARTE_INTROUVABLE,
    RAISON_ARTE_NON_CORROBORE,
    hotes_presents,
    lien_arte,
    liens_arte_de_recherche,
    page_arte_corrobore,
    placer,
    servie,
    titres_candidats,
    type_tmdb,
    verdict_wikidata,
)
from wikidata_links import (
    RapportWikidata,
    WikidataInjoignable,
    entites_par_identifiant,
    format_rapport,
)
from wikidata_matching import (
    RAISON_AMBIGUOUS,
    RAISON_HTTP_ERROR,
    RAISON_OK,
    Lien,
    Resolution,
)

USER_AGENT = "reco-liens-plateformes/1.0 (+https://github.com/Etienne-Boursault/Reco)"
HTTP_TIMEOUT = 25
HTTP_TOO_MANY_REQUESTS = 429
HTTP_NOT_FOUND = 404
PAUSE = 0.4
ARTE_RECHERCHE = "https://www.arte.tv/fr/search/"
PREUVE_TMDB = "identifiant-tmdb"
PREUVE_ARTE = "page-arte"

_RE_APPLE_CANONIQUE = re.compile(
    r"^https://tv\.apple\.com/fr/(?:show|movie)/[^/?#]+/umc\.cmc\.[a-z0-9]+$")
_RE_DISNEY_ENTITE = re.compile(r"/browse/(entity-[0-9a-f-]{36})$")


class PageInjoignable(RuntimeError):
    """Un site n'a pas répondu (429, 5xx, panne réseau).

    Distincte d'un 404, qui EST une réponse : la page n'existe pas (une vidéo
    ARTE expirée, mesuré sur « Los años nuevos »), et c'est un fait.
    """


def _page(session: requests.Session, url: str,
          params: dict[str, str] | None = None) -> requests.Response:
    """Un appel HTTP (redirections suivies). Lève `PageInjoignable` s'il se dérobe."""
    try:
        reponse = session.get(url, params=params or {}, timeout=HTTP_TIMEOUT,
                              headers={"User-Agent": USER_AGENT,
                                       "Accept-Language": "fr-FR,fr;q=0.9"})
    except requests.RequestException as exc:
        raise PageInjoignable(f"injoignable ({exc})") from exc
    if reponse.status_code == HTTP_TOO_MANY_REQUESTS:
        raise PageInjoignable("limite d'appels atteinte (429)")
    if reponse.status_code not in (200, HTTP_NOT_FOUND):
        raise PageInjoignable(f"HTTP {reponse.status_code}")
    return reponse


def resoudre_url(session: requests.Session, lien: Lien) -> str | None:
    """L'URL que le site déclare pour un lien `A_RESOUDRE`, ou None.

    Apple TV : la page sans segment de titre redirige vers sa forme canonique —
    c'est elle que le corpus porte. Disney+ : l'ancien identifiant redirige vers
    la page `entity-…`, réécrite en `fr-fr` comme les 47 liens du corpus. Prime
    Video : la page FR doit exister ; on garde l'URL demandée, car la
    canonique désigne la saison 1 sous un AUTRE identifiant.
    """
    demande = lien.url.removeprefix(A_RESOUDRE)
    reponse = _page(session, demande)
    if reponse.status_code != 200:
        return None
    finale = str(reponse.url)
    if lien.source == "apple":
        return finale if _RE_APPLE_CANONIQUE.match(finale) else None
    if lien.source == "disney":
        m = _RE_DISNEY_ENTITE.search(finale)
        return f"https://www.disneyplus.com/fr-fr/browse/{m.group(1)}" if m else None
    return demande


def _par_wikidata(reco: dict[str, Any], session: requests.Session
                  ) -> tuple[list[Lien], str, str | None, str]:
    """(liens, raison, qid, détail) du chemin Wikidata."""
    cle = type_tmdb(reco)
    entites = entites_par_identifiant(session, cle[0], cle[1]) if cle else []
    verdict = verdict_wikidata(reco, entites)
    liens: list[Lien] = []
    refuses: list[str] = []
    for lien in verdict.liens:
        if not lien.url.startswith(A_RESOUDRE):
            liens.append(lien)
            continue
        url = resoudre_url(session, lien)
        if url is None:
            refuses.append(lien.label)
        else:
            liens.append(Lien(lien.source, lien.kind, lien.ethics, lien.label, url))
    detail = verdict.detail
    if refuses:
        detail = "; ".join(filter(None, (detail, f"page absente : {', '.join(refuses)}")))
    return liens, verdict.raison, verdict.qid, detail


def _par_arte(reco: dict[str, Any], session: requests.Session) -> tuple[list[Lien], str, str]:
    """(liens, raison, détail) du chemin ARTE : recherche, puis page corroborée."""
    cle = type_tmdb(reco)
    genre = cle[2] if cle else ("tv" if "serie" in (reco.get("types") or []) else "movie")
    for titre in titres_candidats(reco):
        recherche = _page(session, ARTE_RECHERCHE, {"q": titre})
        chemins = liens_arte_de_recherche(recherche.text, titre, genre)
        if len(chemins) > 1:
            return [], RAISON_AMBIGUOUS, " ".join(chemins)
        if not chemins:
            continue
        page = _page(session, chemins[0])
        if page.status_code != 200:
            return [], RAISON_ARTE_INTROUVABLE, f"{chemins[0]} → {page.status_code}"
        ok, motif = page_arte_corrobore(page.text, reco, titre)
        if not ok:
            return [], RAISON_ARTE_NON_CORROBORE, motif
        return [lien_arte(str(page.url))], RAISON_OK, ""
    return [], RAISON_ARTE_INTROUVABLE, ""


def resoudre(reco: dict[str, Any], *, session: requests.Session) -> Resolution:
    """Les deux chemins, indépendants : une panne de l'un n'ôte rien à l'autre."""
    liens: list[Lien] = []
    raisons: list[str] = []
    details: list[str] = []
    qid = None
    try:
        trouves, raison, qid, detail = _par_wikidata(reco, session)
        liens += trouves
        raisons.append(raison)
        details.append(detail)
    except (WikidataInjoignable, PageInjoignable) as exc:
        raisons.append(RAISON_HTTP_ERROR)
        details.append(f"wikidata : {exc}")
    if "arte.tv" not in hotes_presents(reco):
        try:
            trouves, raison, detail = _par_arte(reco, session)
            liens = trouves + liens
            raisons.append(raison)
            details.append(f"arte : {detail}" if detail else "")
        except PageInjoignable as exc:
            raisons.append(RAISON_HTTP_ERROR)
            details.append(f"arte : {exc}")
    detail = "; ".join(d for d in details if d)
    if liens:
        preuve = PREUVE_ARTE if all(lien.source == "arte" for lien in liens) else PREUVE_TMDB
        return Resolution(tuple(liens), RAISON_OK, preuve, qid, detail)
    raison = RAISON_HTTP_ERROR if RAISON_HTTP_ERROR in raisons else raisons[0]
    return Resolution((), raison, None, qid, detail)


def run(*, root: Path, session: requests.Session | None = None,
        source: str | None = None, ids: Iterable[str] = (),
        apply: bool = False, sleep: float = PAUSE) -> RapportWikidata:
    """Passe complète sur les recos film/série (de l'épisode si `ids`)."""
    session = session or requests.Session()
    return derouler(root=root, source=source, ids=ids, servie=servie,
                    resoudre=lambda reco: resoudre(reco, session=session),
                    apply=apply, placer=placer, sleep=sleep)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Liens directs Netflix / Prime Video / Disney+ / Apple TV / "
                    "ARTE.tv (+ AlloCiné) des recos film et série.")
    parser.add_argument("--source")
    parser.add_argument("--root", type=Path, help="dossier des recos (défaut : le corpus)")
    parser.add_argument("--ids", help="ids de recos séparés par des virgules")
    parser.add_argument("--apply", action="store_true", help="écrire (défaut : simulation)")
    args = parser.parse_args(argv)
    rapport = run(root=args.root or common.RECOS_DIR, source=args.source, ids=parse_ids_option(args.ids),
                  apply=args.apply)
    log.info("%s", format_rapport(rapport))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
