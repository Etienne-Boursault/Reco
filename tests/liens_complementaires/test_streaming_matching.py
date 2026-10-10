"""Tests de la couche pure des plateformes vidéo — aucun réseau.

Les entités reprennent ce que Wikidata a réellement rendu le 2026-10-10 :
Acharnés (Q112168983) porte Netflix 81447461 ; Fleabag (Q16868648) porte Apple
TV et un ASIN Prime américain, mais TMDB ne liste en France que Prime Video.
"""
from __future__ import annotations

import pytest

import streaming_matching as sm
from wikidata_matching import Entite, Lien

ACHARNES = Entite("Q112168983", claims={
    "P4983": ("154385",), "P345": ("tt14403178",), "P1874": ("81447461",),
    "P1267": ("28766",)})
FLEABAG = Entite("Q16868648", claims={
    "P4983": ("67070",), "P345": ("tt5687612",), "P1267": ("20611",),
    "P9751": ("umc.cmc.3q807jzamz6a79sq9c1nco48o",), "P8055": ("B0875MH9J8",)})


def _reco(tmdb="154385", genre="tv", fournisseurs=(), **champs):
    return {"id": "r", "title": "Acharnés (Beef)", "types": ["serie"],
            "externalIds": {"tmdb": tmdb, "tmdbType": genre},
            "watchProviders": [{"label": f} for f in fournisseurs], **champs}


# ===== identité ==============================================================
@pytest.mark.parametrize("ext,attendu", [
    ({"tmdb": "154385", "tmdbType": "tv"}, ("P4983", "154385", "tv")),
    ({"tmdb": 603, "tmdbType": "movie"}, ("P4947", "603", "movie")),
    ({"tmdb": "154385"}, None),
    ({"tmdb": "abc", "tmdbType": "tv"}, None),
    ({}, None),
])
def test_type_tmdb(ext, attendu):
    assert sm.type_tmdb({"externalIds": ext}) == attendu


def test_servie_ne_prend_que_les_films_et_series():
    assert sm.servie({"types": ["film"]}) and sm.servie({"types": ["autre", "serie"]})
    assert not sm.servie({"types": ["livre"]}) and not sm.servie({})


# ===== disponibilité en France ==============================================
@pytest.mark.parametrize("fournisseurs,plateforme,attendu", [
    (["Netflix Standard with Ads"], sm.NETFLIX, "streaming"),
    (["Apple TV Store"], sm.APPLE, "buy"),
    (["Apple TV", "Apple TV Store"], sm.APPLE, "streaming"),
    (["Apple TV Amazon Channel"], sm.APPLE, None),
    (["Amazon Video"], sm.PRIME, "buy"),
    (["Disney Plus"], sm.DISNEY, "streaming"),
    ([], sm.NETFLIX, None),
])
def test_genre_offert(fournisseurs, plateforme, attendu):
    reco = {"watchProviders": [{"label": f} for f in fournisseurs]}
    assert sm.genre_offert(plateforme, reco) == attendu


# ===== formats d'URL ========================================================
def test_netflix_et_formats_refuses():
    assert sm.url_plateforme(sm.NETFLIX, ACHARNES, "tv") == \
        "https://www.netflix.com/title/81447461"
    assert sm.url_plateforme(sm.NETFLIX, Entite("Q", claims={"P1874": ("x1",)}), "tv") is None
    assert sm.url_plateforme(sm.ARTE, ACHARNES, "tv") is None


def test_prime_ne_lit_jamais_lasin_americain():
    """P8055 répond 404 sur la boutique FR (mesuré sur Fleabag) : ignoré."""
    assert sm.url_plateforme(sm.PRIME, FLEABAG, "tv") is None
    gti = "amzn1.dv.gti.a391bb9d-4315-4b8a-a835-2a3159eeac73"
    assert sm.url_plateforme(sm.PRIME, Entite("Q", claims={"P14462": (gti,)}), "movie") == \
        sm.A_RESOUDRE + f"https://www.primevideo.com/-/fr/detail/{gti}"
    ident = "0LT1TJXTAD3TVX4QBV0QDG1BCB"
    assert sm.url_plateforme(sm.PRIME, Entite("Q", claims={"P14440": (ident,)}), "tv") == \
        sm.A_RESOUDRE + f"https://www.primevideo.com/-/fr/detail/{ident}"


def test_disney_entite_directe_ancien_a_resoudre_collection_refusee():
    entite = "entity-05eb6a8e-90ed-4947-8c0b-e6536cbddd5f"
    assert sm.url_plateforme(sm.DISNEY, Entite("Q", claims={"P13902": (entite,)}), "tv") == \
        f"https://www.disneyplus.com/fr-fr/browse/{entite}"
    collection = Entite("Q", claims={"P13902": ("page-e68fa3ee-0f68-402d-9cb8-56883ae4c9dd",)})
    assert sm.url_plateforme(sm.DISNEY, collection, "tv") is None
    assert sm.url_plateforme(sm.DISNEY, Entite("Q", claims={"P7596": ("52m6nx7HoP5F",)}),
                             "tv") == sm.A_RESOUDRE + \
        "https://www.disneyplus.com/series/wp/52m6nx7HoP5F"
    assert sm.url_plateforme(sm.DISNEY, Entite("Q", claims={"P7595": ("1vXLGiOUqEP9",)}),
                             "movie") == sm.A_RESOUDRE + \
        "https://www.disneyplus.com/movies/wd/1vXLGiOUqEP9"


def test_apple_toujours_a_resoudre_et_selon_le_genre():
    assert sm.url_plateforme(sm.APPLE, FLEABAG, "tv") == \
        sm.A_RESOUDRE + "https://tv.apple.com/fr/show/umc.cmc.3q807jzamz6a79sq9c1nco48o"
    assert sm.url_plateforme(sm.APPLE, FLEABAG, "movie") is None


def test_allocine_film_et_serie():
    assert sm.url_allocine(FLEABAG, "tv") == \
        "https://www.allocine.fr/series/ficheserie_gen_cserie=20611.html"
    assert sm.url_allocine(Entite("Q", claims={"P1265": ("9113",)}), "movie") == \
        "https://www.allocine.fr/film/fichefilm_gen_cfilm=9113.html"
    assert sm.url_allocine(Entite("Q"), "movie") is None


# ===== verdict ==============================================================
def test_acharnes_recoit_netflix_et_allocine():
    verdict = sm.verdict_wikidata(_reco(fournisseurs=["Netflix"]), [ACHARNES])

    assert verdict.raison == "ok" and verdict.qid == "Q112168983"
    assert [(lien.label, lien.kind, lien.ethics, lien.url) for lien in verdict.liens] == [
        ("Netflix", "streaming", "neutral", "https://www.netflix.com/title/81447461"),
        ("AlloCiné", "info", "neutral",
         "https://www.allocine.fr/series/ficheserie_gen_cserie=28766.html")]


def test_fleabag_napple_tv_que_si_tmdb_la_liste_en_france():
    """Apple TV a un identifiant, mais TMDB ne la liste pas en France : on s'abstient."""
    verdict = sm.verdict_wikidata(
        _reco("67070", fournisseurs=["Amazon Prime Video"]), [FLEABAG])

    assert [lien.label for lien in verdict.liens] == ["AlloCiné"]
    assert "Apple TV" in verdict.detail


def test_rien_que_des_plateformes_absentes_de_france():
    reco = _reco(fournisseurs=[], links=[
        {"url": "https://www.allocine.fr/series/ficheserie_gen_cserie=28766.html"}])
    verdict = sm.verdict_wikidata(reco, [ACHARNES])
    assert (verdict.raison, verdict.liens) == (sm.RAISON_PAS_EN_FRANCE, ())


def test_rien_de_neuf_quand_tout_est_deja_pose():
    reco = _reco(fournisseurs=["Netflix"], links=[
        {"url": "https://www.netflix.com/title/81447461"},
        {"url": "https://www.allocine.fr/series/ficheserie_gen_cserie=28766.html"}])
    assert sm.verdict_wikidata(reco, [ACHARNES]).raison == "no-new-link"


@pytest.mark.parametrize("reco,entites,raison", [
    ({"externalIds": {}}, [ACHARNES], "no-tmdb-id"),
    (_reco(), [], "no-entity"),
    (_reco(), [ACHARNES, FLEABAG], "ambiguous"),
    (_reco("999"), [ACHARNES], "id-mismatch"),
    (_reco(links=[{"url": "https://www.imdb.com/title/tt0000001/"}]), [ACHARNES],
     "id-mismatch"),
])
def test_refus(reco, entites, raison):
    assert sm.verdict_wikidata(reco, entites).raison == raison


def test_une_meme_entite_trouvee_deux_fois_nest_pas_ambigue():
    assert sm.verdict_wikidata(_reco(fournisseurs=["Netflix"]),
                               [ACHARNES, ACHARNES]).raison == "ok"


def test_imdb_coherent_accepte():
    reco = _reco(fournisseurs=["Netflix"],
                 links=[{"url": "https://www.imdb.com/title/tt14403178/"}])
    assert sm.verdict_wikidata(reco, [ACHARNES]).raison == "ok"


# ===== ARTE =================================================================
RECHERCHE = ('<a href="/fr/videos/RC-024878/samuel/">Samuel</a>'
             '<a href="/fr/videos/120032-000-A/samuel/">Samuel</a>'
             '<a href="/fr/videos/RC-027959/catastrophe/">Catastrophe</a>'
             '<a href="https://www.arte.tv/fr/videos/RC-024878/samuel/">bis</a>')


def test_la_recherche_ne_garde_que_le_segment_exact_du_bon_genre():
    assert sm.liens_arte_de_recherche(RECHERCHE, "Samuel", "tv") == [
        "https://www.arte.tv/fr/videos/RC-024878/samuel/"]
    assert sm.liens_arte_de_recherche(RECHERCHE, "Samuel", "movie") == [
        "https://www.arte.tv/fr/videos/120032-000-A/samuel/"]
    assert sm.liens_arte_de_recherche(RECHERCHE, "Les Groos", "tv") == []


def test_titres_candidats():
    assert sm.titres_candidats({"title": "Acharnés (Beef)"}) == ["Acharnés (Beef)", "Acharnés"]
    assert sm.titres_candidats({"title": "Samuel"}) == ["Samuel"]
    assert sm.titres_candidats({}) == []


def _page(titre, corps=""):
    return f"<html><head><title>{titre}</title></head><body>{corps}</body></html>"


SAMUEL = {"title": "Samuel", "creator": "Émilie Tronche", "types": ["serie"]}
GROOS = {"title": "Les Groos", "types": ["serie"],
         "quote": "J'ai aimé la mini-série Arte Bro."}


def test_samuel_corrobore_par_sa_creatrice():
    page = _page("Samuel - Séries et fictions | ARTE", "la série d&#39;Émilie Tronche")
    assert sm.page_arte_corrobore(page, SAMUEL, "Samuel") == (True, "")


def test_un_createur_absent_de_la_page_refuse():
    ok, motif = sm.page_arte_corrobore(_page("Samuel - Séries et fictions | ARTE"),
                                       {**SAMUEL, "creator": "Jean Dupont & Ana"}, "Samuel")
    assert not ok and "créateur" in motif


def test_un_autre_titre_de_page_refuse():
    ok, motif = sm.page_arte_corrobore(_page("Samuel et Julie - Films | ARTE"),
                                       SAMUEL, "Samuel")
    assert not ok and "titre de page" in motif
    assert not sm.page_arte_corrobore("<html></html>", SAMUEL, "Samuel")[0]


def test_sans_createur_la_mention_darte_dans_la_citation_suffit():
    page = _page("Les Groos - Séries et fictions | ARTE")
    assert sm.page_arte_corrobore(page, GROOS, "Les Groos") == (True, "")


def test_sans_createur_le_fournisseur_arte_suffit():
    reco = {"title": "Les Groos", "watchProviders": [{"label": "Arte"}]}
    assert sm.page_arte_corrobore(_page("Les Groos - Séries | ARTE"), reco, "Les Groos")[0]


def test_sans_createur_ni_fournisseur_ni_mention_on_sabstient():
    reco = {"title": "Les Groos", "quote": "une série géniale"}
    ok, motif = sm.page_arte_corrobore(_page("Les Groos - Séries | ARTE"), reco, "Les Groos")
    assert not ok and "ni créateur" in motif


def test_lien_arte():
    assert sm.lien_arte("https://www.arte.tv/fr/videos/RC-024878/samuel/").as_link() == {
        "kind": "streaming", "ethics": "indie", "label": "ARTE.tv",
        "url": "https://www.arte.tv/fr/videos/RC-024878/samuel/"}


# ===== placement ============================================================
def _l(label, url):
    return {"label": label, "url": url}


TMDB = _l("TMDB", "https://www.themoviedb.org/tv/67070")
OU = _l("Où regarder", "https://www.themoviedb.org/tv/67070-fleabag/watch?locale=FR")


def test_les_plateformes_vont_en_tete_dans_lordre_ethique():
    liens = [_l("Netflix", "https://www.netflix.com/title/1"), TMDB, OU]
    arte = Lien("arte", "streaming", "indie", "ARTE.tv", "https://www.arte.tv/x")
    prime = Lien("prime", "streaming", "avoid", "Prime Video", "https://www.primevideo.com/x")

    assert sm.placer(liens, arte) == 0
    assert sm.placer(liens, prime) == 1
    assert sm.placer(liens[:1], prime) == 1


def test_allocine_juste_avant_ou_regarder_sinon_a_la_fin():
    allocine = Lien("allocine", "info", "neutral", "AlloCiné", "https://www.allocine.fr/x")
    assert sm.placer([TMDB, OU], allocine) == 1
    assert sm.placer([TMDB], allocine) == 1
