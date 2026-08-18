"""Invariant : deux liens TMDB sur une reco, c'est la fiche ET la page « où regarder ».

POURQUOI CE FICHIER EXISTE
--------------------------
Le 2026-08-18, un rapport a classe « 269 recos avec deux liens themoviedb.org »
parmi les defauts a corriger. La mesure a montre que la premisse etait fausse :
les 269 sont la configuration VOULUE. TMDB sert ici a deux choses distinctes,
et `link_families.cle_couverture` les traite deliberement comme telles :

    fiche          https://www.themoviedb.org/tv/94801
    ou regarder    https://www.themoviedb.org/tv/94801-mortel/watch?locale=FR

Le danger n'est donc pas le doublon, c'est le NETTOYAGE du doublon. Un
correcteur qui verrait deux liens partageant un hote supprimerait la page de
visionnage — exactement la regression que ce projet a deja connue quand la
couverture etait calculee par hote et non par fonction.

Ce fichier n'est pas un correcteur : c'est une GARDE. Il fige l'invariant dans
les deux sens, pour que la prochaine derive se signale d'elle-meme au lieu
d'etre prise pour un menage a faire.
"""
from __future__ import annotations

import json
import re

import pytest

from common import CONTENT_DIR

#: `/movie/123` ou `/tv/456` — l'identifiant, seul element signifiant de l'URL.
#: Le slug (`-mortel`) est decoratif, TMDB l'ignore.
_ID = re.compile(r"/(movie|tv)/(\d+)")


def _recos() -> list[dict]:
    out = []
    for chemin in (CONTENT_DIR / "recos").rglob("*.json"):
        try:
            out.append(json.loads(chemin.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            continue
    return out


def _liens_tmdb(doc: dict) -> list[str]:
    return [lien.get("url") or "" for lien in (doc.get("links") or [])
            if isinstance(lien, dict) and "themoviedb.org" in (lien.get("url") or "")]


@pytest.fixture(scope="module")
def corpus() -> list[dict]:
    docs = _recos()
    # Sans cette garde, tous les tests ci-dessous passeraient sur zero reco et
    # annonceraient un corpus sain qu'ils n'ont jamais regarde.
    assert len(docs) > 500, "corpus introuvable ou vide"
    return docs


def test_jamais_plus_de_deux_liens_tmdb(corpus):
    trop = [d.get("id") for d in corpus if len(_liens_tmdb(d)) > 2]
    assert not trop, f"trois liens TMDB ou plus : {trop[:10]}"


def test_une_paire_tmdb_designe_TOUJOURS_la_meme_oeuvre(corpus):
    """Deux identifiants differents sur une meme reco : l'un des deux pointe
    une autre œuvre. C'est le seul cas vraiment grave, et il n'existe pas."""
    fautifs = []
    for d in corpus:
        liens = _liens_tmdb(d)
        if len(liens) != 2:
            continue
        ids = {m.groups() for m in (_ID.search(u) for u in liens) if m}
        if len(ids) != 1:
            fautifs.append((d.get("id"), liens))
    assert not fautifs, f"identifiants TMDB divergents : {fautifs[:5]}"


def test_une_paire_tmdb_est_une_fiche_ET_une_page_de_visionnage(corpus):
    """Ni deux fiches (vrai doublon), ni deux pages de visionnage."""
    fautifs = []
    for d in corpus:
        liens = _liens_tmdb(d)
        if len(liens) != 2:
            continue
        watch = sum(1 for u in liens if "/watch" in u)
        if watch != 1:
            fautifs.append((d.get("id"), watch, liens))
    assert not fautifs, f"paire TMDB mal formee : {fautifs[:5]}"


def test_aucune_page_de_visionnage_orpheline(corpus):
    """L'invariant dans l'autre sens : une page « où regarder » sans sa fiche
    signalerait que la fiche a ete supprimee par erreur."""
    orphelins = []
    for d in corpus:
        liens = _liens_tmdb(d)
        if len(liens) == 1 and "/watch" in liens[0]:
            orphelins.append((d.get("id"), liens[0]))
    assert not orphelins, f"page de visionnage sans fiche : {orphelins[:5]}"


def test_les_tests_ci_dessus_portent_bien_sur_quelque_chose(corpus):
    """Garde anti-test-vide.

    Les trois tests de paire filtrent sur `len(liens) == 2`. Si ce filtre ne
    retenait plus rien — renommage d'hote, changement de structure des liens —
    ils passeraient tous SANS RIEN VERIFIER, et leur vert annoncerait un
    corpus sain qu'ils n'auraient jamais regarde. Ce projet s'est deja fait
    prendre par un test infalsifiable ; celui-ci rend les autres refutables.
    """
    paires = sum(1 for d in corpus if len(_liens_tmdb(d)) == 2)
    assert paires >= 200, (
        f"seulement {paires} paires TMDB trouvees (269 au 2026-08-18) : le "
        f"filtre des tests de paire ne mord plus, ils passent a vide.")


# ===== watchPage derive de l'identifiant (2026-08-18) ======================
def _docs() -> list[dict]:
    """Recos ET items : le champ `watchPage` vit dans les deux collections."""
    out = []
    for collection in ("recos", "items"):
        for chemin in (CONTENT_DIR / collection).rglob("*.json"):
            try:
                out.append(json.loads(chemin.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError):
                continue
    return out


@pytest.fixture(scope="module")
def avec_watchpage() -> list[dict]:
    docs = [d for d in _docs()
            if isinstance((d.get("externalIds") or {}).get("watchPage"), str)]
    # Garde anti-test-vide : si le champ disparaissait du corpus, les deux
    # tests ci-dessous passeraient sans rien verifier.
    assert len(docs) > 100, f"seulement {len(docs)} documents portent watchPage"
    return docs


def test_watchPage_designe_la_MEME_oeuvre_que_l_identifiant(avec_watchpage):
    """`watchPage` se DEDUIT de `externalIds.tmdb` : c'est un derive, pas une
    donnee independante.

    Cinq recos violaient cet invariant le 2026-08-18, et chacune envoyait le
    visiteur ailleurs : « Vice » d'Adam McKay menait a « Vice-versa » de Pixar
    (le slug disait `150540-inside-out`), « Fantomas » de 1964 au muet de
    1913, « Looking » a « Looking up to Magical Girls ». Le bouton disait
    « Où regarder » et tenait une autre promesse.
    """
    fautifs = []
    for d in avec_watchpage:
        ext = d["externalIds"]
        m = _ID.search(ext["watchPage"])
        if m is None:
            continue  # adresse hors TMDB, hors juridiction
        if (m.group(1), m.group(2)) != (str(ext.get("tmdbType")),
                                        str(ext.get("tmdb"))):
            fautifs.append((d.get("id"), d.get("title"), ext["watchPage"][:60]))
    assert not fautifs, f"watchPage designe une autre oeuvre : {fautifs[:5]}"


def test_aucun_watchPage_ne_survit_a_son_identifiant(avec_watchpage):
    """Sans `tmdb`, l'adresse ne derive plus de rien — elle fige un identifiant
    qu'on a justement juge faux. La reco « Bagarre » en portait un vers
    « Picture Snatcher » (1933) apres le retrait de son identifiant."""
    orphelins = [(d.get("id"), d.get("title"))
                 for d in avec_watchpage
                 if _ID.search(d["externalIds"]["watchPage"])
                 and d["externalIds"].get("tmdb") is None]
    assert not orphelins, f"watchPage sans identifiant : {orphelins[:5]}"
