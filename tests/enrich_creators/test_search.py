"""Tests de la stratégie `tmdb-search` (recherche par titre, opt-in).

Contexte : 91 recos film/série actives n'ont AUCUN identifiant externe, donc
aucune ancre pour les stratégies par id. La recherche par titre les rattrape —
mais elle est structurellement plus risquée : sans id, rien ne prouve a priori
que le résultat désigne la bonne œuvre.

D'où un contrat volontairement plus sévère que celui des stratégies par id :

  1. **Titre STRICTEMENT égal** après normalisation (`titles_match_strict`).
     `titles_match` (inclusion de mots, similarité 0,x) est trop permissif ici :
     il ferait passer « Mortal » pour « Mortal Kombat ».
  2. **Un seul candidat survivant.** Deux œuvres au titre identique ⇒ on ne
     devine pas, on laisse vide (`search-ambiguous`).
  3. Les garde-fous des stratégies par id s'appliquent **en plus**, sur la
     fiche complète re-téléchargée (année, anachronisme, créateur == titre).
  4. La stratégie est **opt-in** (`--search`) : le comportement par défaut
     reste « identifiants externes uniquement ».
"""
from __future__ import annotations

import pytest
import requests
import responses

import enrich_creators as ec

TMDB = "https://api.themoviedb.org/3"


@pytest.fixture()
def session():
    return requests.Session()


# ===== titles_match_strict (pur) ===========================================
@pytest.mark.parametrize(("a", "b"), [
    ("Rick et Morty", "RICK ET MORTY"),          # casse
    ("Le Bureau des Légendes", "Le Bureau des Legendes"),  # accents
    ("L'Île de la Tentation", "L Ile de la Tentation"),    # ponctuation
])
def test_strict_match_accepte_les_variantes_typographiques(a, b):
    assert ec.titles_match_strict(a, b) is True


@pytest.mark.parametrize(("a", "b"), [
    ("Mortal", "Mortal Kombat"),        # inclusion : refusée ici
    ("White Lotus", "The White Lotus"),  # inclusion : refusée ici
    ("Colombo", "Columbo"),              # similarité : refusée ici
    ("Vice", "Vice-versa"),
])
def test_strict_match_refuse_ce_que_titles_match_accepterait(a, b):
    assert ec.titles_match_strict(a, b) is False


@pytest.mark.parametrize(("a", "b"), [(None, "x"), ("x", None), ("", "x"), ("  ", "x")])
def test_strict_match_refuse_les_titres_vides(a, b):
    assert ec.titles_match_strict(a, b) is False


# ===== search_kind (pur) ====================================================
def test_search_kind_film_vers_movie():
    assert ec.search_kind({"types": ["film"]}) == "movie"


def test_search_kind_serie_vers_tv():
    assert ec.search_kind({"types": ["serie"]}) == "tv"


def test_search_kind_suit_l_ordre_des_types():
    assert ec.search_kind({"types": ["autre", "serie", "film"]}) == "tv"


def test_search_kind_none_hors_video():
    assert ec.search_kind({"types": ["musique"]}) is None
    assert ec.search_kind({}) is None


# ===== exact_title_candidates (pur) ========================================
def test_candidats_filtre_sur_le_titre_exact():
    results = [
        {"id": 1, "title": "Jurassic Park"},
        {"id": 2, "title": "Jurassic Park III"},
        {"id": 3, "original_title": "Jurassic Park"},
    ]
    ids = [c["id"] for c in ec.exact_title_candidates("Jurassic Park", results)]
    assert ids == [1, 3]


def test_candidats_vide_si_aucun_titre_exact():
    assert ec.exact_title_candidates("Groom", [{"id": 9, "title": "Grooming"}]) == []


def test_candidats_ignore_les_entrees_sans_id():
    assert ec.exact_title_candidates("X", [{"title": "X"}]) == []


# ===== fetch_tmdb_search (réseau mocké) ====================================
@responses.activate
def test_fetch_search_movie_passe_l_annee(session):
    responses.add(responses.GET, f"{TMDB}/search/movie",
                  json={"results": []}, status=200)
    ec.fetch_tmdb_search(session, "movie", "Titanic", api_key="k", year=1997)
    url = responses.calls[0].request.url
    assert "query=Titanic" in url
    assert "year=1997" in url
    assert "language=fr-FR" in url
    assert "api_key=k" in url


@responses.activate
def test_fetch_search_tv_utilise_first_air_date_year(session):
    responses.add(responses.GET, f"{TMDB}/search/tv",
                  json={"results": []}, status=200)
    ec.fetch_tmdb_search(session, "tv", "Groom", api_key="k", year=2020)
    url = responses.calls[0].request.url
    assert "first_air_date_year=2020" in url
    assert "year=2020" not in url.replace("first_air_date_year=2020", "")


@responses.activate
def test_fetch_search_sans_annee_n_envoie_pas_le_parametre(session):
    responses.add(responses.GET, f"{TMDB}/search/movie",
                  json={"results": []}, status=200)
    ec.fetch_tmdb_search(session, "movie", "Titanic", api_key="k")
    assert "year=" not in responses.calls[0].request.url


# ===== plan() : la recherche est opt-in ====================================
def test_plan_sans_search_refuse_faute_d_identifiant():
    reco = {"types": ["film"], "title": "Jurassic Park"}
    assert ec.plan(reco).reason == ec.REASON_NO_EXTERNAL_ID


def test_plan_avec_search_choisit_la_recherche():
    reco = {"types": ["film"], "title": "Jurassic Park"}
    assert ec.plan(reco, allow_search=True).strategy == ec.STRATEGY_TMDB_SEARCH


def test_plan_avec_search_prefere_toujours_l_identifiant_externe():
    reco = {"types": ["film"], "title": "Titanic",
            "externalIds": {"tmdb": "597", "tmdbType": "movie"}}
    assert ec.plan(reco, allow_search=True).strategy == ec.STRATEGY_TMDB_MOVIE


def test_plan_avec_search_ne_devine_pas_le_type_tmdb():
    """Un id TMDB sans `tmdbType` reste ambigu : la recherche ne le sauve pas."""
    reco = {"types": ["film"], "title": "X", "externalIds": {"tmdb": "1396"}}
    assert ec.plan(reco, allow_search=True).reason == ec.REASON_NO_TMDB_TYPE


def test_plan_avec_search_n_affecte_pas_musique_et_livres():
    assert ec.plan({"types": ["album"], "title": "X"},
                   allow_search=True).reason == ec.REASON_NO_EXTERNAL_ID
    assert ec.plan({"types": ["livre"], "title": "X"},
                   allow_search=True).reason == ec.REASON_NO_EXTERNAL_ID


def test_plan_avec_search_respecte_creator_deja_pose():
    reco = {"types": ["film"], "title": "X", "creator": "Déjà là"}
    assert ec.plan(reco, allow_search=True).reason == ec.REASON_ALREADY_SET


# ===== resolve_creator via recherche (bout en bout, réseau mocké) ==========
def _search_body(results):
    """Corps de réponse `/search`.

    Une `popularity` par défaut est injectée : sans elle, le garde-fou
    d'obscurité refuserait tout (`popularity` absente ⇒ 0). Les tests qui
    portent SUR ce garde-fou fixent leurs propres valeurs, qui priment.
    """
    return {"page": 1,
            "results": [{"popularity": 10.0, **r} for r in results],
            "total_results": len(results)}


@responses.activate
def test_recherche_film_trouve_le_realisateur(session):
    responses.add(responses.GET, f"{TMDB}/search/movie",
                  json=_search_body([{"id": 329, "title": "Jurassic Park",
                                      "release_date": "1993-06-11"}]), status=200)
    responses.add(responses.GET, f"{TMDB}/movie/329",
                  json={"title": "Jurassic Park", "release_date": "1993-06-11",
                        "credits": {"crew": [{"job": "Director",
                                              "name": "Steven Spielberg"}]}},
                  status=200)
    reco = {"types": ["film"], "title": "Jurassic Park"}
    res = ec.resolve_creator(reco, session=session, api_key="k", allow_search=True)
    assert res.creator == "Steven Spielberg"
    assert res.reason == ec.REASON_FILLED
    assert res.source == "tmdb:movie/329"


@responses.activate
def test_recherche_serie_trouve_les_createurs(session):
    responses.add(responses.GET, f"{TMDB}/search/tv",
                  json=_search_body([{"id": 60625, "name": "Rick et Morty",
                                      "first_air_date": "2013-12-02"}]), status=200)
    responses.add(responses.GET, f"{TMDB}/tv/60625",
                  json={"name": "Rick et Morty", "first_air_date": "2013-12-02",
                        "created_by": [{"name": "Dan Harmon"},
                                       {"name": "Justin Roiland"}]},
                  status=200)
    reco = {"types": ["serie"], "title": "Rick et Morty"}
    res = ec.resolve_creator(reco, session=session, api_key="k", allow_search=True)
    assert res.creator == "Dan Harmon, Justin Roiland"
    assert res.source == "tmdb:tv/60625"


@responses.activate
def test_recherche_refuse_deux_oeuvres_au_meme_titre(session):
    responses.add(responses.GET, f"{TMDB}/search/movie",
                  json=_search_body([{"id": 1, "title": "Titanic",
                                      "release_date": "1997-11-18"},
                                     {"id": 2, "title": "Titanic",
                                      "release_date": "1997-01-01"}]), status=200)
    reco = {"types": ["film"], "title": "Titanic"}
    res = ec.resolve_creator(reco, session=session, api_key="k", allow_search=True)
    assert res.creator is None
    assert res.reason == ec.REASON_SEARCH_AMBIGUOUS
    assert "1" in res.detail and "2" in res.detail
    # Aucune fiche complète n'est téléchargée quand c'est ambigu.
    assert len(responses.calls) == 1


@responses.activate
def test_recherche_refuse_un_titre_seulement_ressemblant(session):
    responses.add(responses.GET, f"{TMDB}/search/movie",
                  json=_search_body([{"id": 9, "title": "Mortal Kombat",
                                      "release_date": "2021-04-07"}]), status=200)
    reco = {"types": ["film"], "title": "Mortal"}
    res = ec.resolve_creator(reco, session=session, api_key="k", allow_search=True)
    assert res.creator is None
    assert res.reason == ec.REASON_SEARCH_NO_MATCH


@responses.activate
def test_recherche_ecarte_les_candidats_a_l_annee_incompatible(session):
    """Deux « Dune » : seul celui dont l'année colle est retenu."""
    responses.add(responses.GET, f"{TMDB}/search/movie",
                  json=_search_body([{"id": 41, "title": "Dune",
                                      "release_date": "1984-12-14"},
                                     {"id": 42, "title": "Dune",
                                      "release_date": "2021-09-15"}]), status=200)
    responses.add(responses.GET, f"{TMDB}/movie/42",
                  json={"title": "Dune", "release_date": "2021-09-15",
                        "credits": {"crew": [{"job": "Director",
                                              "name": "Denis Villeneuve"}]}},
                  status=200)
    reco = {"types": ["film"], "title": "Dune", "year": 2021}
    res = ec.resolve_creator(reco, session=session, api_key="k", allow_search=True)
    assert res.creator == "Denis Villeneuve"


@responses.activate
def test_recherche_ecarte_une_oeuvre_sortie_apres_l_episode(session):
    responses.add(responses.GET, f"{TMDB}/search/movie",
                  json=_search_body([{"id": 7, "title": "Mourir seul",
                                      "release_date": "2025-03-01"}]), status=200)
    reco = {"types": ["film"], "title": "Mourir seul"}
    res = ec.resolve_creator(reco, session=session, api_key="k",
                             episode_year=2021, allow_search=True)
    assert res.creator is None
    assert res.reason == ec.REASON_SEARCH_NO_MATCH


@responses.activate
def test_recherche_sans_resultat(session):
    responses.add(responses.GET, f"{TMDB}/search/movie",
                  json=_search_body([]), status=200)
    reco = {"types": ["film"], "title": "Film qui n'existe pas"}
    res = ec.resolve_creator(reco, session=session, api_key="k", allow_search=True)
    assert res.reason == ec.REASON_SEARCH_NO_MATCH


@responses.activate
def test_recherche_erreur_http(session):
    responses.add(responses.GET, f"{TMDB}/search/movie", json={}, status=500)
    reco = {"types": ["film"], "title": "X"}
    res = ec.resolve_creator(reco, session=session, api_key="k", allow_search=True)
    assert res.reason == ec.REASON_HTTP_ERROR


@responses.activate
def test_recherche_fiche_complete_en_erreur(session):
    """La recherche aboutit mais la fiche complète échoue → pas d'invention."""
    responses.add(responses.GET, f"{TMDB}/search/movie",
                  json=_search_body([{"id": 5, "title": "X",
                                      "release_date": "2000-01-01"}]), status=200)
    responses.add(responses.GET, f"{TMDB}/movie/5", json={}, status=503)
    res = ec.resolve_creator({"types": ["film"], "title": "X"},
                             session=session, api_key="k", allow_search=True)
    assert res.reason == ec.REASON_HTTP_ERROR


@responses.activate
def test_recherche_sans_realisateur_dans_les_credits(session):
    responses.add(responses.GET, f"{TMDB}/search/movie",
                  json=_search_body([{"id": 5, "title": "X",
                                      "release_date": "2000-01-01"}]), status=200)
    responses.add(responses.GET, f"{TMDB}/movie/5",
                  json={"title": "X", "release_date": "2000-01-01",
                        "credits": {"crew": [{"job": "Producer", "name": "P"}]}},
                  status=200)
    res = ec.resolve_creator({"types": ["film"], "title": "X"},
                             session=session, api_key="k", allow_search=True)
    assert res.reason == ec.REASON_NO_DIRECTOR


def test_recherche_exige_une_cle_api(session):
    res = ec.resolve_creator({"types": ["film"], "title": "X"},
                             session=session, api_key=None, allow_search=True)
    assert res.reason == ec.REASON_NO_API_KEY


@responses.activate
def test_recherche_refuse_un_createur_egal_au_titre(session):
    """Garde-fou partagé : « Truc » réalisé par « Truc » ⇒ mauvais match."""
    responses.add(responses.GET, f"{TMDB}/search/movie",
                  json=_search_body([{"id": 8, "title": "Jean Dupont",
                                      "release_date": "2010-01-01"}]), status=200)
    responses.add(responses.GET, f"{TMDB}/movie/8",
                  json={"title": "Jean Dupont", "release_date": "2010-01-01",
                        "credits": {"crew": [{"job": "Director",
                                              "name": "Jean Dupont"}]}},
                  status=200)
    res = ec.resolve_creator({"types": ["film"], "title": "Jean Dupont"},
                             session=session, api_key="k", allow_search=True)
    assert res.creator is None
    assert res.reason == ec.REASON_CREATOR_EQUALS_TITLE


# ===== garde-fous d'obscurité et d'éclipse ==================================
# Mesures réelles TMDB du 2026-07-29 (cf. docstring de `obscurity_verdict`) :
#   « Amélie » retenu pop. 0,14 — éclipsé ×96,9 par « Le Fabuleux Destin
#   d'Amélie Poulain » ; « Le Moulin Rouge » 0,71 ; « White fire » 0,44 ;
#   à l'opposé « Star Wars » 40,5 et « South Park » 83,5.
def test_candidat_trop_obscur_est_refuse():
    cand = {"id": 891850, "title": "Amélie", "popularity": 0.14}
    assert ec.obscurity_verdict(cand, [cand]) == ec.REASON_SEARCH_TOO_OBSCURE


def test_candidat_eclipse_par_un_homonyme_populaire_est_refuse():
    cand = {"id": 123, "title": "Le Seigneur des Anneaux", "popularity": 4.44}
    autre = {"id": 122, "title": "Le Seigneur des anneaux : Le Retour du roi",
             "popularity": 51.82}
    assert ec.obscurity_verdict(cand, [cand, autre]) == ec.REASON_SEARCH_ECLIPSED


def test_candidat_populaire_et_dominant_est_accepte():
    cand = {"id": 2190, "title": "South Park", "popularity": 83.52}
    assert ec.obscurity_verdict(cand, [cand]) is None


def test_un_ecart_modere_ne_disqualifie_pas():
    """« Star Wars » (40,5) est devancé ×4,3 par un spin-off : ça reste le bon."""
    cand = {"id": 11, "title": "Star Wars", "popularity": 40.50}
    autre = {"id": 99, "title": "Star Wars : The Mandalorian and Grogu",
             "popularity": 175.81}
    assert ec.obscurity_verdict(cand, [cand, autre]) is None


def test_popularite_absente_vaut_zero_donc_refus():
    assert ec.obscurity_verdict({"id": 1, "title": "X"}, []) == \
        ec.REASON_SEARCH_TOO_OBSCURE


@pytest.mark.parametrize("brut", ["beaucoup", None, {}, []])
def test_popularite_non_numerique_vaut_zero(brut):
    """TMDB a déjà renvoyé des champs mal typés : on dégrade, on ne plante pas."""
    assert ec.popularity({"popularity": brut}) == 0.0


@responses.activate
def test_recherche_refuse_le_candidat_obscur_de_bout_en_bout(session):
    """Cas réel : la reco « Amélie » désigne Amélie Poulain, pas l'homonyme."""
    responses.add(responses.GET, f"{TMDB}/search/movie",
                  json=_search_body([
                      {"id": 891850, "title": "Amélie",
                       "release_date": "2021-01-01", "popularity": 0.14},
                      {"id": 194, "title": "Le Fabuleux Destin d'Amélie Poulain",
                       "release_date": "2001-04-25", "popularity": 14.02}]),
                  status=200)
    res = ec.resolve_creator({"types": ["film"], "title": "Amélie"},
                             session=session, api_key="k", allow_search=True)
    assert res.creator is None
    assert res.reason == ec.REASON_SEARCH_TOO_OBSCURE
    # Aucune fiche complète n'est téléchargée : le refus est décidé avant.
    assert len(responses.calls) == 1


def test_les_deux_refus_meritent_un_oeil_humain():
    assert ec.REASON_SEARCH_TOO_OBSCURE in ec.AMBIGUOUS_REASONS
    assert ec.REASON_SEARCH_ECLIPSED in ec.AMBIGUOUS_REASONS


# ===== câblage CLI ==========================================================
def test_cli_search_absent_par_defaut():
    assert ec.build_parser().parse_args([]).search is False


def test_cli_search_est_transmis_a_run(monkeypatch, tmp_path):
    """`--search` doit atteindre `run()` : sans ce câblage l'option ne fait rien."""
    seen: dict[str, object] = {}

    def _fake_run(**kwargs):
        seen.update(kwargs)
        return ec.Report()

    monkeypatch.setattr(ec, "run", _fake_run)
    monkeypatch.setattr(ec, "load_episode_years", lambda *a, **kw: {})
    monkeypatch.setenv("TMDB_API_KEY", "k")

    assert ec.main(["--search"]) == 0
    assert seen["allow_search"] is True

    seen.clear()
    assert ec.main([]) == 0
    assert seen["allow_search"] is False


# ===== ambiguïté remontée dans le rapport ==================================
def test_search_ambiguous_est_une_raison_a_revoir():
    assert ec.REASON_SEARCH_AMBIGUOUS in ec.AMBIGUOUS_REASONS


def test_search_no_match_n_est_pas_une_raison_a_revoir():
    """Une absence de résultat n'est pas un doute : rien à arbitrer à la main."""
    assert ec.REASON_SEARCH_NO_MATCH not in ec.AMBIGUOUS_REASONS
