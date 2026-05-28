"""Tests d'intégration pour `enrich_tmdb.main()` + fonctions HTTP.

Couvre :
  - `_tmdb_get` : succès, erreur HTTP, RequestException.
  - `tmdb_search` : hit primaire, hit secondaire (fallback de type), pas trouvé.
  - `tmdb_watch_providers` : providers FR (dédup, multi-slots), pas de FR.
  - `main()` : --limit, --force, absence de TMDB_API_KEY, reco déjà enrichie,
    réutilisation de l'id, pas trouvé.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
import requests
import responses

import enrich_tmdb


# ===== _tmdb_get ============================================================
@responses.activate
def test_tmdb_get_success(monkeypatch):
    monkeypatch.setenv("TMDB_API_KEY", "fake")
    responses.add(
        responses.GET,
        "https://api.themoviedb.org/3/foo",
        json={"ok": True},
        status=200,
    )
    s = requests.Session()
    assert enrich_tmdb._tmdb_get(s, "/foo", {"x": "1"}) == {"ok": True}


@responses.activate
def test_tmdb_get_http_error_returns_none(monkeypatch):
    monkeypatch.setenv("TMDB_API_KEY", "fake")
    responses.add(
        responses.GET,
        "https://api.themoviedb.org/3/bar",
        json={"status_message": "nope"},
        status=404,
    )
    s = requests.Session()
    assert enrich_tmdb._tmdb_get(s, "/bar") is None


def test_tmdb_get_request_exception_returns_none(monkeypatch):
    monkeypatch.setenv("TMDB_API_KEY", "fake")
    s = requests.Session()
    # On force l'exception au niveau de la session.
    def boom(*a, **kw):
        raise requests.ConnectionError("boom")
    monkeypatch.setattr(s, "get", boom)
    assert enrich_tmdb._tmdb_get(s, "/bar") is None


# ===== tmdb_search ==========================================================
@responses.activate
def test_tmdb_search_primary_hit(monkeypatch):
    monkeypatch.setenv("TMDB_API_KEY", "fake")
    # Première URL appelée : /search/movie (primary, query=title creator FR).
    responses.add(
        responses.GET,
        "https://api.themoviedb.org/3/search/movie",
        json={"results": [{"id": 42, "title": "Mortel"}]},
        status=200,
    )
    out = enrich_tmdb.tmdb_search(requests.Session(), "film", "Mortel", "Réalisateur X")
    assert out == ("42", "movie")


@responses.activate
def test_tmdb_search_falls_back_to_secondary_kind(monkeypatch):
    """Aucun résultat film → essai sur tv (cas mauvais typage)."""
    monkeypatch.setenv("TMDB_API_KEY", "fake")
    responses.add(
        responses.GET,
        "https://api.themoviedb.org/3/search/movie",
        json={"results": []},
        status=200,
    )
    responses.add(
        responses.GET,
        "https://api.themoviedb.org/3/search/tv",
        json={"results": [{"id": 7}]},
        status=200,
    )
    out = enrich_tmdb.tmdb_search(requests.Session(), "film", "Mortel", None)
    assert out == ("7", "tv")


@responses.activate
def test_tmdb_search_not_found(monkeypatch):
    monkeypatch.setenv("TMDB_API_KEY", "fake")
    responses.add(
        responses.GET,
        "https://api.themoviedb.org/3/search/movie",
        json={"results": []},
        status=200,
    )
    responses.add(
        responses.GET,
        "https://api.themoviedb.org/3/search/tv",
        json={"results": []},
        status=200,
    )
    assert enrich_tmdb.tmdb_search(requests.Session(), "film", "Inconnu", None) is None


@responses.activate
def test_tmdb_search_serie_starts_with_tv(monkeypatch):
    """type=serie → premier essai sur /tv."""
    monkeypatch.setenv("TMDB_API_KEY", "fake")
    responses.add(
        responses.GET,
        "https://api.themoviedb.org/3/search/tv",
        json={"results": [{"id": 99}]},
        status=200,
    )
    out = enrich_tmdb.tmdb_search(requests.Session(), "serie", "Engrenages")
    assert out == ("99", "tv")


# ===== tmdb_watch_providers ================================================
@responses.activate
def test_watch_providers_returns_link_and_unique_providers(monkeypatch):
    monkeypatch.setenv("TMDB_API_KEY", "fake")
    responses.add(
        responses.GET,
        "https://api.themoviedb.org/3/movie/42/watch/providers",
        json={"results": {"FR": {
            "link": "https://www.justwatch.com/fr/film/mortel",
            "flatrate": [{"provider_name": "Netflix"}],
            "rent": [{"provider_name": "Apple TV"}, {"provider_name": "Netflix"}],  # doublon
            "buy": [{"provider_name": ""}],  # nom vide → ignoré
        }}},
        status=200,
    )
    link, providers = enrich_tmdb.tmdb_watch_providers(
        requests.Session(), "42", "movie", "Mortel"
    )
    assert link == "https://www.justwatch.com/fr/film/mortel"
    names = [p["label"] for p in providers]
    assert names == ["Netflix", "Apple TV"]


@responses.activate
def test_watch_providers_no_fr_market(monkeypatch):
    monkeypatch.setenv("TMDB_API_KEY", "fake")
    responses.add(
        responses.GET,
        "https://api.themoviedb.org/3/movie/42/watch/providers",
        json={"results": {"US": {"link": "x"}}},
        status=200,
    )
    link, providers = enrich_tmdb.tmdb_watch_providers(
        requests.Session(), "42", "movie", "Mortel"
    )
    assert link is None
    assert providers == []


# ===== main() ===============================================================
@pytest.fixture
def reco_env(tmp_path, monkeypatch):
    """Configure un dossier de recos factice + redirection de recos_dir_for."""
    recos_dir = tmp_path / "recos" / "src"
    recos_dir.mkdir(parents=True)
    monkeypatch.setattr(enrich_tmdb, "recos_dir_for", lambda s: recos_dir)
    # Désactive le sleep pour des tests rapides.
    monkeypatch.setattr(enrich_tmdb.time, "sleep", lambda *_: None)
    # Désactive load_dotenv (sinon peut écraser TMDB_API_KEY).
    monkeypatch.setattr(enrich_tmdb, "load_dotenv", lambda *a, **k: None)
    return recos_dir


def _write_reco(d, name, data):
    p = d / name
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return p


def test_main_missing_api_key_exits(reco_env, monkeypatch):
    monkeypatch.delenv("TMDB_API_KEY", raising=False)
    monkeypatch.setattr(sys, "argv", ["enrich_tmdb.py", "--source", "src"])
    with pytest.raises(SystemExit):
        enrich_tmdb.main()


@responses.activate
def test_main_enriches_one_reco(reco_env, monkeypatch):
    monkeypatch.setenv("TMDB_API_KEY", "fake")
    _write_reco(reco_env, "a.json", {"id": "a", "types": ["film"], "title": "Mortel"})
    # Ignorée car type=livre.
    _write_reco(reco_env, "b.json", {"id": "b", "types": ["livre"], "title": "X"})

    responses.add(
        responses.GET,
        "https://api.themoviedb.org/3/search/movie",
        json={"results": [{"id": 42}]},
        status=200,
    )
    responses.add(
        responses.GET,
        "https://api.themoviedb.org/3/movie/42/watch/providers",
        json={"results": {"FR": {
            "link": "https://www.justwatch.com/fr/film/mortel",
            "flatrate": [{"provider_name": "Netflix"}],
        }}},
        status=200,
    )

    monkeypatch.setattr(sys, "argv", ["enrich_tmdb.py", "--source", "src"])
    enrich_tmdb.main()

    out = json.loads((reco_env / "a.json").read_text(encoding="utf-8"))
    assert out["externalIds"]["tmdb"] == "42"
    assert out["externalIds"]["tmdbType"] == "movie"
    assert out["externalIds"]["justwatch"].endswith("/film/mortel")
    assert out["watchProviders"][0]["label"] == "Netflix"


@responses.activate
def test_main_limit_caps_targets(reco_env, monkeypatch):
    monkeypatch.setenv("TMDB_API_KEY", "fake")
    for i in range(3):
        _write_reco(reco_env, f"{i}.json", {"id": str(i), "types": ["film"], "title": f"T{i}"})

    # Une seule recherche/provider, car --limit 1.
    responses.add(
        responses.GET,
        "https://api.themoviedb.org/3/search/movie",
        json={"results": [{"id": 1}]},
        status=200,
    )
    responses.add(
        responses.GET,
        "https://api.themoviedb.org/3/movie/1/watch/providers",
        json={"results": {}},
        status=200,
    )
    monkeypatch.setattr(sys, "argv", ["enrich_tmdb.py", "--source", "src", "--limit", "1"])
    enrich_tmdb.main()
    # Seule la 1ʳᵉ a été enrichie.
    enriched = [json.loads((reco_env / f"{i}.json").read_text("utf-8")).get("externalIds")
                for i in range(3)]
    assert enriched[0] and enriched[1] is None and enriched[2] is None


@responses.activate
def test_main_skips_already_enriched_without_force(reco_env, monkeypatch):
    monkeypatch.setenv("TMDB_API_KEY", "fake")
    _write_reco(reco_env, "a.json", {
        "id": "a", "types": ["film"], "title": "M",
        "externalIds": {"tmdb": "1", "tmdbType": "movie", "justwatch": "u"},
    })
    monkeypatch.setattr(sys, "argv", ["enrich_tmdb.py", "--source", "src"])
    # Aucune route enregistrée : si on appelle l'API, responses lèvera.
    enrich_tmdb.main()


@responses.activate
def test_main_force_reuses_known_id(reco_env, monkeypatch):
    """--force + tmdb_id déjà connu : pas de /search, juste /watch/providers."""
    monkeypatch.setenv("TMDB_API_KEY", "fake")
    _write_reco(reco_env, "a.json", {
        "id": "a", "types": ["serie"], "title": "Engrenages",
        "externalIds": {"tmdb": "10", "tmdbType": "tv"},
    })
    responses.add(
        responses.GET,
        "https://api.themoviedb.org/3/tv/10/watch/providers",
        json={"results": {"FR": {"link": None, "flatrate": []}}},
        status=200,
    )
    monkeypatch.setattr(sys, "argv", ["enrich_tmdb.py", "--source", "src", "--force"])
    enrich_tmdb.main()
    out = json.loads((reco_env / "a.json").read_text("utf-8"))
    # Pas de providers et pas de justwatch → on n'écrit rien de plus.
    assert "justwatch" not in out["externalIds"]
    assert "watchProviders" not in out


@responses.activate
def test_main_not_found_keeps_reco_untouched(reco_env, monkeypatch):
    monkeypatch.setenv("TMDB_API_KEY", "fake")
    _write_reco(reco_env, "a.json", {"id": "a", "types": ["film"], "title": "Introuvable"})
    responses.add(
        responses.GET,
        "https://api.themoviedb.org/3/search/movie",
        json={"results": []},
        status=200,
    )
    responses.add(
        responses.GET,
        "https://api.themoviedb.org/3/search/tv",
        json={"results": []},
        status=200,
    )
    monkeypatch.setattr(sys, "argv", ["enrich_tmdb.py", "--source", "src"])
    enrich_tmdb.main()
    out = json.loads((reco_env / "a.json").read_text("utf-8"))
    assert "externalIds" not in out


def test_main_no_targets_returns_early(reco_env, monkeypatch):
    """Aucun fichier film/série → main retourne sans appeler l'API."""
    monkeypatch.setenv("TMDB_API_KEY", "fake")
    _write_reco(reco_env, "a.json", {"id": "a", "types": ["livre"], "title": "X"})
    monkeypatch.setattr(sys, "argv", ["enrich_tmdb.py", "--source", "src"])
    enrich_tmdb.main()


# ===== enrich_one / is_targetable ==========================================
def test_is_targetable_true_for_film():
    assert enrich_tmdb.is_targetable({"types": ["film"]}) is True
    assert enrich_tmdb.is_targetable({"types": ["serie", "podcast"]}) is True


def test_is_targetable_false_for_other_types():
    assert enrich_tmdb.is_targetable({"types": ["livre"]}) is False
    assert enrich_tmdb.is_targetable({}) is False
    assert enrich_tmdb.is_targetable({"types": []}) is False


@responses.activate
def test_enrich_one_found(monkeypatch):
    monkeypatch.setenv("TMDB_API_KEY", "fake")
    responses.add(
        responses.GET,
        "https://api.themoviedb.org/3/search/movie",
        json={"results": [{"id": 42}]},
        status=200,
    )
    responses.add(
        responses.GET,
        "https://api.themoviedb.org/3/movie/42/watch/providers",
        json={"results": {"FR": {
            "link": "https://www.justwatch.com/fr/film/x",
            "flatrate": [{"provider_name": "Netflix"}],
        }}},
        status=200,
    )
    reco = {"id": "a", "types": ["film"], "title": "X"}
    out = enrich_tmdb.enrich_one(reco, session=requests.Session(), api_key="fake")
    assert out is reco
    assert out["externalIds"]["tmdb"] == "42"
    assert out["externalIds"]["tmdbType"] == "movie"
    assert out["externalIds"]["justwatch"].endswith("/film/x")
    assert out["watchProviders"][0]["label"] == "Netflix"
    assert out["_enrich_status"] == "ok"


@responses.activate
def test_enrich_one_not_found_does_not_touch_existing_fields(monkeypatch):
    monkeypatch.setenv("TMDB_API_KEY", "fake")
    responses.add(
        responses.GET, "https://api.themoviedb.org/3/search/movie",
        json={"results": []}, status=200,
    )
    responses.add(
        responses.GET, "https://api.themoviedb.org/3/search/tv",
        json={"results": []}, status=200,
    )
    reco = {"id": "a", "types": ["film"], "title": "Introuvable",
            "externalIds": {"isbn": "999"}}
    out = enrich_tmdb.enrich_one(reco, session=requests.Session(), api_key="fake")
    assert out["_enrich_status"] == "not_found"
    # Champs préexistants intacts, pas de tmdb ajouté.
    assert out["externalIds"] == {"isbn": "999"}
    assert "watchProviders" not in out


@responses.activate
def test_enrich_one_handles_api_error_as_not_found(monkeypatch):
    """Si toutes les requêtes /search renvoient 500 (HTTP error), enrich_one
    retombe gracieusement sur 'not_found' (cf. _tmdb_get qui retourne None)."""
    monkeypatch.setenv("TMDB_API_KEY", "fake")
    responses.add(
        responses.GET, "https://api.themoviedb.org/3/search/movie",
        json={"err": "boom"}, status=500,
    )
    responses.add(
        responses.GET, "https://api.themoviedb.org/3/search/tv",
        json={"err": "boom"}, status=500,
    )
    reco = {"id": "a", "types": ["film"], "title": "X"}
    out = enrich_tmdb.enrich_one(reco, session=requests.Session(), api_key="fake")
    assert out["_enrich_status"] == "not_found"
    assert "externalIds" not in out


@responses.activate
def test_enrich_one_reuses_known_id_skips_search(monkeypatch):
    """tmdb + tmdbType déjà connus → pas d'appel /search, juste /watch/providers."""
    monkeypatch.setenv("TMDB_API_KEY", "fake")
    responses.add(
        responses.GET,
        "https://api.themoviedb.org/3/tv/10/watch/providers",
        json={"results": {"FR": {"link": "https://jw/x", "flatrate": []}}},
        status=200,
    )
    reco = {"id": "a", "types": ["serie"], "title": "E",
            "externalIds": {"tmdb": "10", "tmdbType": "tv"}}
    out = enrich_tmdb.enrich_one(reco, session=requests.Session(), api_key="fake")
    assert out["externalIds"]["tmdb"] == "10"
    assert out["externalIds"]["justwatch"] == "https://jw/x"
    assert out["_enrich_status"] == "ok"
    # Une seule requête HTTP enregistrée par responses → pas de /search appelé.
    assert len(responses.calls) == 1


@responses.activate
def test_enrich_one_force_raises_on_http_error(monkeypatch):
    """force=True : un HTTP 401 doit lever TMDBAPIError (pas être avalé en
    'not_found'). C'est ce qui permet à l'UI de différencier 'titre inconnu'
    de 'clé invalide / API down'."""
    monkeypatch.setenv("TMDB_API_KEY", "fake")
    responses.add(
        responses.GET, "https://api.themoviedb.org/3/search/tv",
        json={"status_message": "Invalid API key"}, status=401,
    )
    reco = {"id": "a", "types": ["serie"], "title": "X"}
    with pytest.raises(enrich_tmdb.TMDBAPIError):
        enrich_tmdb.enrich_one(
            reco, session=requests.Session(), api_key="fake", force=True,
        )


def test_enrich_one_force_raises_on_network_error(monkeypatch):
    """force=True : si requests lève (timeout, DNS), TMDBAPIError remonte."""
    import requests as _rq
    class _Sess:
        def get(self, *a, **kw):
            raise _rq.ConnectionError("DNS fail")
    reco = {"id": "a", "types": ["film"], "title": "X"}
    with pytest.raises(enrich_tmdb.TMDBAPIError):
        enrich_tmdb.enrich_one(reco, session=_Sess(), api_key="k", force=True)


@responses.activate
def test_enrich_one_no_force_keeps_silent_skip_on_http_error(monkeypatch):
    """force=False (mode CLI batch) : un HTTP 401 reste silencieux pour
    permettre au batch de continuer sur les autres recos."""
    monkeypatch.setenv("TMDB_API_KEY", "fake")
    for path in ("/3/search/movie", "/3/search/tv"):
        responses.add(
            responses.GET, f"https://api.themoviedb.org{path}",
            json={"err": "x"}, status=401,
        )
    reco = {"id": "a", "types": ["film"], "title": "X"}
    out = enrich_tmdb.enrich_one(
        reco, session=requests.Session(), api_key="fake", force=False,
    )
    assert out["_enrich_status"] == "not_found"


@responses.activate
def test_enrich_one_force_ignores_known_id_and_re_searches(monkeypatch):
    """force=True : on relance /search même si tmdb_id déjà connu (cas UI bouton
    Ré-enrichir après correction de titre — l'ancien id peut être obsolète)."""
    monkeypatch.setenv("TMDB_API_KEY", "fake")
    # /search retourne un NOUVEL id 99 (différent du 10 stocké).
    responses.add(
        responses.GET, "https://api.themoviedb.org/3/search/tv",
        json={"results": [{"id": 99}]}, status=200,
    )
    responses.add(
        responses.GET, "https://api.themoviedb.org/3/tv/99/watch/providers",
        json={"results": {"FR": {"link": "https://jw/99", "flatrate": []}}},
        status=200,
    )
    reco = {"id": "a", "types": ["serie"], "title": "Nouveau Titre",
            "externalIds": {"tmdb": "10", "tmdbType": "tv"}}
    out = enrich_tmdb.enrich_one(
        reco, session=requests.Session(), api_key="fake", force=True,
    )
    assert out["externalIds"]["tmdb"] == "99"      # remplacé
    assert out["externalIds"]["justwatch"] == "https://jw/99"
    assert out["_enrich_status"] == "ok"


@responses.activate
def test_main_force_re_searches_and_removes_stale_justwatch(reco_env, monkeypatch):
    """--force : reco déjà enrichie, mais on re-cherche et le justwatch disparaît."""
    monkeypatch.setenv("TMDB_API_KEY", "fake")
    _write_reco(reco_env, "a.json", {
        "id": "a", "types": ["film"], "title": "M",
        "externalIds": {"tmdb": "1", "tmdbType": "movie", "justwatch": "stale"},
        "watchProviders": [{"label": "old"}],
    })
    responses.add(
        responses.GET,
        "https://api.themoviedb.org/3/movie/1/watch/providers",
        json={"results": {"FR": {"link": None, "flatrate": []}}},
        status=200,
    )
    monkeypatch.setattr(sys, "argv", ["enrich_tmdb.py", "--source", "src", "--force"])
    enrich_tmdb.main()
    out = json.loads((reco_env / "a.json").read_text("utf-8"))
    assert "justwatch" not in out["externalIds"]
    assert "watchProviders" not in out
