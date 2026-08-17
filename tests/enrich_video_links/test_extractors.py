"""Tests de la couche PURE d'`enrich_video_links` : extraction et garde-fous.

Aucun réseau, aucun disque. C'est ici que se joue la règle « zéro invention » :
un lien ne doit exister que si un IDENTIFIANT renvoyé par l'API le fonde.
"""
from __future__ import annotations

import pytest

import enrich_video_links as evl

# Importée de son module d'origine : cette exception appartient à la couche
# d'audit trail, pas à l'API de cet outil.
from enrichment.field_refresher import EnrichedAtCorruptedError

# --- Payloads TMDB de référence (forme réelle de l'API) ---------------------
MOVIE_PAYLOAD = {
    "id": 597,
    "title": "Titanic",
    "original_title": "Titanic",
    "release_date": "1997-12-19",
    "external_ids": {"imdb_id": "tt0120338", "wikidata_id": "Q44578"},
    "watch/providers": {
        "results": {"FR": {"link": "https://www.justwatch.com/fr/film/titanic"}},
    },
}


# ===== link_host ============================================================
def test_link_host_strips_www():
    assert evl.link_host("https://www.imdb.com/title/tt0120338/") == "imdb.com"


def test_link_host_keeps_bare_host():
    assert evl.link_host("https://themoviedb.org/movie/597") == "themoviedb.org"


def test_link_host_lowercases():
    assert evl.link_host("https://WWW.IMDb.COM/x") == "imdb.com"


def test_link_host_empty_url():
    assert evl.link_host("") == ""


def test_link_host_unparsable_url():
    assert evl.link_host("https://[") == ""


# ===== covered_hosts ========================================================
def test_covered_hosts_empty_reco():
    assert evl.covered_hosts({}) == set()


def test_covered_hosts_reads_links_and_custom_links():
    reco = {
        "links": [{"label": "AlloCiné", "url": "https://www.allocine.fr/film/1.html"}],
        "customLinks": [{"label": "IMDb", "url": "https://www.imdb.com/title/tt1/"}],
    }
    assert evl.covered_hosts(reco) == {"allocine.fr", "imdb.com"}


def test_covered_hosts_ignores_entries_without_url():
    assert evl.covered_hosts({"links": [{"label": "vide"}]}) == set()


# ===== imdb_id_from =========================================================
def test_imdb_id_from_payload():
    assert evl.imdb_id_from(MOVIE_PAYLOAD) == "tt0120338"


def test_imdb_id_from_missing_block():
    assert evl.imdb_id_from({"id": 1}) is None


def test_imdb_id_from_non_dict_block():
    assert evl.imdb_id_from({"external_ids": "nope"}) is None


def test_imdb_id_from_empty_string():
    assert evl.imdb_id_from({"external_ids": {"imdb_id": ""}}) is None


def test_imdb_id_from_null():
    assert evl.imdb_id_from({"external_ids": {"imdb_id": None}}) is None


def test_imdb_id_from_rejects_person_id():
    """`nm…` est un identifiant de PERSONNE : sur /title/ il donne un 404."""
    assert evl.imdb_id_from({"external_ids": {"imdb_id": "nm0000123"}}) is None


def test_imdb_id_from_rejects_malformed():
    assert evl.imdb_id_from({"external_ids": {"imdb_id": "tt"}}) is None


def test_imdb_id_from_strips_whitespace():
    assert evl.imdb_id_from({"external_ids": {"imdb_id": " tt0120338 "}}) == "tt0120338"


# ===== justwatch_url_from ===================================================
def test_justwatch_url_from_payload():
    assert evl.justwatch_url_from(MOVIE_PAYLOAD) == "https://www.justwatch.com/fr/film/titanic"


def test_justwatch_url_from_missing_block():
    assert evl.justwatch_url_from({"id": 1}) is None


def test_justwatch_url_from_non_dict_block():
    assert evl.justwatch_url_from({"watch/providers": []}) is None


def test_justwatch_url_from_non_dict_results():
    assert evl.justwatch_url_from({"watch/providers": {"results": 3}}) is None


def test_justwatch_url_from_no_fr_region():
    payload = {"watch/providers": {"results": {"US": {"link": "https://www.justwatch.com/us/x"}}}}
    assert evl.justwatch_url_from(payload) is None


def test_justwatch_url_from_non_dict_fr():
    assert evl.justwatch_url_from({"watch/providers": {"results": {"FR": "x"}}}) is None


def test_justwatch_url_from_empty_link():
    assert evl.justwatch_url_from({"watch/providers": {"results": {"FR": {"link": ""}}}}) is None


def test_justwatch_url_from_rejects_hostless_link():
    payload = {"watch/providers": {"results": {"FR": {"link": "/fr/film/titanic"}}}}
    assert evl.justwatch_url_from(payload) is None


def test_justwatch_url_from_rejects_foreign_host():
    """Garde-fou : on n'accepte comme « lien JustWatch » que du justwatch.com."""
    payload = {"watch/providers": {"results": {"FR": {"link": "https://evil.test/fr/x"}}}}
    assert evl.justwatch_url_from(payload) is None


def test_justwatch_url_from_accepts_subdomain():
    payload = {"watch/providers": {"results": {"FR": {"link": "https://www.justwatch.com/fr/x"}}}}
    assert evl.justwatch_url_from(payload) == "https://www.justwatch.com/fr/x"


# ===== build_link ===========================================================
def test_build_link_imdb():
    link = evl.build_link(evl.SITE_IMDB, "https://www.imdb.com/title/tt0120338/")
    assert link == {"label": "IMDb", "url": "https://www.imdb.com/title/tt0120338/",
                    "kind": "info", "ethics": "neutral"}


def test_build_link_justwatch_is_streaming():
    link = evl.build_link(evl.SITE_JUSTWATCH, "https://www.justwatch.com/fr/film/titanic")
    assert link["kind"] == "streaming"
    assert link["label"] == "Où regarder"


def test_build_link_rejects_non_https():
    assert evl.build_link(evl.SITE_TMDB, "http://www.themoviedb.org/movie/597") is None


# ===== imdb_url / tmdb_url ==================================================
def test_imdb_url_uses_canonical_pattern():
    assert evl.imdb_url("tt0120338") == "https://www.imdb.com/title/tt0120338/"


def test_tmdb_url_movie():
    assert evl.tmdb_url("movie", "597") == "https://www.themoviedb.org/movie/597"


def test_tmdb_url_tv():
    assert evl.tmdb_url("tv", "1396") == "https://www.themoviedb.org/tv/1396"


# ===== candidate_links ======================================================
def test_candidate_links_all_three_in_order():
    links = evl.candidate_links(MOVIE_PAYLOAD, kind="movie", tmdb_id="597",
                                sites=evl.ALL_SITES)
    assert [link["label"] for link in links] == ["IMDb", "TMDB", "Où regarder"]


def test_candidate_links_honours_site_selection():
    links = evl.candidate_links(MOVIE_PAYLOAD, kind="movie", tmdb_id="597",
                                sites=(evl.SITE_IMDB,))
    assert [link["label"] for link in links] == ["IMDb"]


def test_candidate_links_without_imdb_id():
    payload = {**MOVIE_PAYLOAD, "external_ids": {}}
    links = evl.candidate_links(payload, kind="movie", tmdb_id="597", sites=evl.ALL_SITES)
    assert [link["label"] for link in links] == ["TMDB", "Où regarder"]


def test_candidate_links_without_justwatch():
    payload = {k: v for k, v in MOVIE_PAYLOAD.items() if k != "watch/providers"}
    links = evl.candidate_links(payload, kind="movie", tmdb_id="597", sites=evl.ALL_SITES)
    assert [link["label"] for link in links] == ["IMDb", "TMDB"]


def test_candidate_links_drops_a_non_https_justwatch_url():
    """TMDB renvoyant du http : `build_link` refuse, aucun lien n'est posé."""
    payload = {**MOVIE_PAYLOAD, "watch/providers": {
        "results": {"FR": {"link": "http://www.justwatch.com/fr/film/titanic"}}}}
    links = evl.candidate_links(payload, kind="movie", tmdb_id="597", sites=evl.ALL_SITES)
    assert [link["label"] for link in links] == ["IMDb", "TMDB"]


def test_candidate_links_tmdb_always_available_when_asked():
    links = evl.candidate_links({}, kind="tv", tmdb_id="1396", sites=evl.ALL_SITES)
    assert [link["url"] for link in links] == ["https://www.themoviedb.org/tv/1396"]


# ===== missing_links ========================================================
def test_missing_links_keeps_all_when_reco_has_none():
    candidates = evl.candidate_links(MOVIE_PAYLOAD, kind="movie", tmdb_id="597",
                                     sites=evl.ALL_SITES)
    assert len(evl.missing_links({}, candidates)) == 3


def test_missing_links_drops_already_covered_host():
    candidates = evl.candidate_links(MOVIE_PAYLOAD, kind="movie", tmdb_id="597",
                                     sites=evl.ALL_SITES)
    reco = {"links": [{"label": "IMDb", "url": "https://www.imdb.com/title/tt9/"}]}
    assert [link["label"] for link in evl.missing_links(reco, candidates)] == ["TMDB", "Où regarder"]


def test_missing_links_host_comparison_ignores_www():
    candidates = [evl.build_link(evl.SITE_JUSTWATCH, "https://www.justwatch.com/fr/a")]
    reco = {"links": [{"label": "JW", "url": "https://justwatch.com/fr/b"}]}
    assert evl.missing_links(reco, candidates) == []


# ===== merge_links ==========================================================
def test_merge_links_appends_after_existing():
    reco = {"links": [{"label": "AlloCiné", "url": "https://www.allocine.fr/f/1.html",
                       "kind": "info", "ethics": "neutral"}]}
    added = [evl.build_link(evl.SITE_IMDB, "https://www.imdb.com/title/tt1/")]
    merged = evl.merge_links(reco, added)
    assert [link["label"] for link in merged] == ["AlloCiné", "IMDb"]


def test_merge_links_on_empty_reco():
    added = [evl.build_link(evl.SITE_IMDB, "https://www.imdb.com/title/tt1/")]
    assert evl.merge_links({}, added) == added


def test_merge_links_never_duplicates_an_existing_host():
    """L'idempotence ne doit pas dépendre du bon vouloir de l'appelant."""
    reco = {"links": [{"label": "IMDb", "url": "https://www.imdb.com/title/tt1/"}]}
    added = [evl.build_link(evl.SITE_IMDB, "https://www.imdb.com/title/tt2/")]
    assert evl.merge_links(reco, added) == reco["links"]


def test_merge_links_deduplicates_within_the_additions():
    added = [evl.build_link(evl.SITE_IMDB, "https://www.imdb.com/title/tt1/"),
             evl.build_link(evl.SITE_IMDB, "https://www.imdb.com/title/tt2/")]
    assert len(evl.merge_links({}, added)) == 1


# ===== apply_video_links ====================================================
def test_apply_video_links_writes_field_and_audit_trail():
    reco = {"id": "x"}
    added = [evl.build_link(evl.SITE_IMDB, "https://www.imdb.com/title/tt1/")]
    evl.apply_video_links(reco, added, timestamp="2026-07-31T00:00:00Z")
    assert reco["links"] == added
    assert reco["enrichedAt"] == {"links": "2026-07-31T00:00:00Z"}


def test_apply_video_links_preserves_other_audit_entries():
    reco = {"id": "x", "enrichedAt": {"creator": "2026-01-01T00:00:00Z"}}
    evl.apply_video_links(reco, [evl.build_link(evl.SITE_IMDB,
                                                "https://www.imdb.com/title/tt1/")],
                          timestamp="2026-07-31T00:00:00Z")
    assert reco["enrichedAt"]["creator"] == "2026-01-01T00:00:00Z"
    assert reco["enrichedAt"]["links"] == "2026-07-31T00:00:00Z"


def test_apply_video_links_uses_now_by_default():
    reco = {"id": "x"}
    evl.apply_video_links(reco, [evl.build_link(evl.SITE_IMDB,
                                                "https://www.imdb.com/title/tt1/")])
    assert reco["enrichedAt"]["links"].endswith("Z")


def test_apply_video_links_refuses_corrupted_audit_trail():
    reco = {"id": "x", "enrichedAt": "pas-un-dict"}
    with pytest.raises(EnrichedAtCorruptedError):
        evl.apply_video_links(reco, [])


# ===== video_type ===========================================================
def test_video_type_film():
    assert evl.video_type({"types": ["film"]}) == "film"


def test_video_type_prefers_declared_order():
    assert evl.video_type({"types": ["serie", "film"]}) == "serie"


def test_video_type_skips_unrelated_types():
    assert evl.video_type({"types": ["autre", "film"]}) == "film"


def test_video_type_without_video_type():
    assert evl.video_type({"types": ["podcast"]}) == "?"


def test_video_type_without_types():
    assert evl.video_type({}) == "?"


# ===== plan =================================================================
def test_plan_movie_with_id():
    p = evl.plan({"types": ["film"], "externalIds": {"tmdb": "597", "tmdbType": "movie"}})
    assert p.strategy == evl.STRATEGY_TMDB_ID
    assert p.population == evl.POPULATION_ID


def test_plan_tv_with_id():
    p = evl.plan({"types": ["serie"], "externalIds": {"tmdb": "1396", "tmdbType": "tv"}})
    assert p.strategy == evl.STRATEGY_TMDB_ID


def test_plan_id_without_tmdb_type_is_refused():
    """Les espaces d'ids movie et tv sont disjoints : deviner produirait un faux."""
    p = evl.plan({"types": ["film"], "externalIds": {"tmdb": "1396"}})
    assert p.strategy is None
    assert p.reason == evl.REASON_NO_TMDB_TYPE


def test_plan_without_id_and_without_search():
    p = evl.plan({"types": ["film"]})
    assert p.strategy is None
    assert p.reason == evl.REASON_SEARCH_DISABLED


def test_plan_without_id_with_search():
    p = evl.plan({"types": ["film"]}, allow_search=True)
    assert p.strategy == evl.STRATEGY_TMDB_SEARCH
    assert p.population == evl.POPULATION_SEARCH


def test_plan_non_video_type():
    p = evl.plan({"types": ["livre"]}, allow_search=True)
    assert p.strategy is None
    assert p.reason == evl.REASON_TYPE_UNSUPPORTED


def test_plan_no_types_at_all():
    p = evl.plan({})
    assert p.reason == evl.REASON_TYPE_UNSUPPORTED


# ===== parse_sites ==========================================================
def test_parse_sites_default_is_all():
    assert evl.parse_sites(None) == evl.ALL_SITES


def test_parse_sites_subset_keeps_canonical_order():
    assert evl.parse_sites("justwatch,imdb") == (evl.SITE_IMDB, evl.SITE_JUSTWATCH)


def test_parse_sites_ignores_blanks():
    assert evl.parse_sites(" imdb , ") == (evl.SITE_IMDB,)


def test_parse_sites_rejects_unknown():
    with pytest.raises(ValueError, match="site inconnu"):
        evl.parse_sites("allocine")


# ===== La page « où regarder » a changé d'hôte ==============================
#
# TMDB servait autrefois une URL justwatch.com. Il renvoie désormais sa PROPRE
# page de visionnage. Le contrôle d'hôte n'avait pas suivi : il rejetait donc
# exactement ce que l'API donne, et la passe ne posait plus aucun lien de
# visionnage — en silence, puisqu'« aucun candidat » ressemble à « rien à
# faire ». Ces tests sont ceux qui manquaient pour que la panne se voie.
_WATCH_TMDB = "https://www.themoviedb.org/movie/424277-annette/watch?locale=FR"


def test_la_page_de_visionnage_TMDB_est_acceptee():
    payload = {"watch/providers": {"results": {"FR": {"link": _WATCH_TMDB}}}}
    assert evl.justwatch_url_from(payload) == _WATCH_TMDB


def test_justwatch_reste_accepte():
    """Les liens déjà posés dans le corpus restent valides, et rien n'oblige
    TMDB à ne pas y revenir."""
    assert evl.justwatch_url_from(MOVIE_PAYLOAD) is not None


def test_un_hote_tiers_reste_refuse():
    """Le champ vient d'une API tierce : accepter n'importe quel hôte
    reviendrait à laisser une API décider de ce qu'on publie."""
    payload = {"watch/providers": {"results": {"FR": {"link": "https://pub.example/x"}}}}
    assert evl.justwatch_url_from(payload) is None


# ===== Fiche et page de visionnage partagent un hôte ========================
def test_la_page_de_visionnage_ne_couvre_pas_la_fiche():
    """Le cœur du correctif. Les deux vivent sur themoviedb.org tout en étant
    deux ressources différentes ; dédoublonner sur l'hôte seul rendait la
    seconde impossible à poser dès que la première existait — c'est-à-dire
    toujours, puisque la fiche est ce que la passe pose en premier."""
    assert evl.cle_couverture(_WATCH_TMDB) == evl.CLE_VISIONNAGE
    assert evl.cle_couverture("https://www.themoviedb.org/movie/424277") == "themoviedb.org"


def test_cle_couverture_tolere_la_barre_finale():
    assert evl.cle_couverture("https://www.themoviedb.org/tv/1/watch/") == evl.CLE_VISIONNAGE


def test_cle_couverture_d_une_url_illisible_est_vide():
    assert evl.cle_couverture("pas une url") == ""


def test_une_reco_avec_SA_FICHE_TMDB_manque_encore_le_visionnage():
    reco = {"links": [{"url": "https://www.themoviedb.org/movie/424277"}]}
    manquants = evl.missing_links(reco, [{"url": _WATCH_TMDB, "label": "Où regarder"}])
    assert [l["url"] for l in manquants] == [_WATCH_TMDB]


def test_le_lien_de_visionnage_ne_se_pose_pas_deux_fois():
    """L'idempotence ne doit pas dépendre du bon vouloir de l'appelant."""
    reco = {"links": [{"url": _WATCH_TMDB, "label": "Où regarder"}]}
    assert evl.merge_links(reco, [{"url": _WATCH_TMDB, "label": "Où regarder"}]) == reco["links"]


def test_deux_ressources_du_meme_hote_s_ajoutent_toutes_les_deux():
    reco = {"links": [{"url": "https://www.themoviedb.org/movie/424277", "label": "TMDB"}]}
    fusion = evl.merge_links(reco, [{"url": _WATCH_TMDB, "label": "Où regarder"}])
    assert len(fusion) == 2


def test_le_libelle_ne_nomme_pas_une_marque_qui_peut_changer():
    """La destination est passée de JustWatch à TMDB. Un libellé de marque
    deviendrait faux au premier changement d'API ; l'usage, lui, reste vrai."""
    assert evl.SITE_LABELS[evl.SITE_JUSTWATCH] == "Où regarder"


def test_justwatch_et_la_page_TMDB_sont_LE_MEME_service():
    """Le piège symétrique du précédent. Une clé fondée sur le chemin les
    séparait — et posait deux liens « où regarder » sur la même reco. C'est
    exactement ce qui est arrivé à 8 recos (Fargo, The Office, The Rehearsal…)
    avant que ce test n'existe."""
    assert (evl.cle_couverture("https://www.justwatch.com/fr/serie/fargo")
            == evl.cle_couverture("https://www.themoviedb.org/tv/60622-fargo/watch?locale=FR"))


def test_une_reco_DEJA_sur_justwatch_ne_recoit_pas_la_page_TMDB():
    reco = {"links": [{"url": "https://www.justwatch.com/fr/serie/fargo", "label": "JustWatch"}]}
    assert evl.missing_links(reco, [{"url": _WATCH_TMDB, "label": "Où regarder"}]) == []
    assert evl.merge_links(reco, [{"url": _WATCH_TMDB, "label": "Où regarder"}]) == reco["links"]


def test_un_hote_hors_visionnage_garde_son_hote():
    assert evl.cle_couverture("https://www.netflix.com/fr/title/1") == "netflix.com"
