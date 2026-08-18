"""Tests pour tools/review_search_links.py — recherches pré-remplies /tableau.

Module neuf : exigence 100 % statements ET branches.

Trois familles d'invariants, dans l'ordre de ce qui casserait le plus :

1. La LIGNE ROUGE — ces URL sont un outil de curation interne. Le test qui
   compte vraiment est celui qui vérifie qu'aucune n'a de forme de « fiche » :
   toutes doivent être des recherches, pour qu'on ne puisse pas en recopier
   une dans `src/content/recos/**.json` en croyant tenir une fiche.
2. Le CIBLAGE — on ne propose que ce qui MANQUE. Une reco qui a déjà son lien
   Deezer n'a pas besoin qu'on lui propose de chercher sur Deezer.
3. L'ENCODAGE — `quote_plus` en query string, `quote` en segment de chemin.
   Un `+` dans un chemin reste un `+` littéral : la confusion des deux
   fabriquerait des recherches qui ne cherchent pas ce qu'on croit.
"""
from __future__ import annotations

from pathlib import Path

import pytest

import review_search_links as rsl
from review_edit import RECO_TYPES

_REPO = Path(__file__).resolve().parents[1]


def _urls(*args, **kwargs) -> dict[str, str]:
    """{label: url} — la forme dans laquelle la plupart des tests raisonnent."""
    return {s["label"]: s["url"] for s in rsl.search_links(*args, **kwargs)}


# ===== Cohérence de la table ===============================================
def test_every_type_key_points_to_a_known_platform():
    """Un type qui référence une clé inconnue lèverait KeyError EN PRODUCTION.

    `search_links` indexe `SEARCH_PLATFORMS[key]` sans `.get` — à dessein :
    une clé manquante est un bug de table, pas une donnée à tolérer. Ce test
    est ce qui rend ce choix sûr.
    """
    for reco_type, keys in rsl.SEARCH_PLATFORMS_BY_TYPE.items():
        for key in keys:
            assert key in rsl.SEARCH_PLATFORMS, f"{reco_type} → {key}"


def test_every_reco_type_has_search_platforms():
    """Aucun type du vocabulaire ne doit tomber dans le repli par hasard."""
    for reco_type in RECO_TYPES:
        assert reco_type in rsl.SEARCH_PLATFORMS_BY_TYPE, reco_type


def test_default_key_is_a_known_platform():
    for key in rsl._DEFAULT_KEYS:
        assert key in rsl.SEARCH_PLATFORMS


def test_all_platforms_are_reachable_from_some_type():
    """Une plateforme que plus aucun type n'atteint est du code mort."""
    used = {k for keys in rsl.SEARCH_PLATFORMS_BY_TYPE.values() for k in keys}
    used.update(rsl._DEFAULT_KEYS)
    assert used == set(rsl.SEARCH_PLATFORMS)


@pytest.mark.parametrize("key", sorted(rsl.SEARCH_PLATFORMS))
def test_templates_are_https_search_urls(key):
    platform = rsl.SEARCH_PLATFORMS[key]
    assert platform.template.startswith("https://")
    assert "{q}" in platform.template or "{p}" in platform.template
    assert platform.label and platform.hosts


@pytest.mark.parametrize("key", sorted(rsl.SEARCH_PLATFORMS))
def test_no_template_looks_like_an_item_page(key):
    """LA LIGNE ROUGE : que des recherches, jamais une forme de fiche.

    Si un jour quelqu'un ajoute ici `https://www.deezer.com/fr/album/{p}`, la
    puce cesserait d'être une recherche et deviendrait une URL qu'on pourrait
    recopier dans le corpus en croyant tenir la fiche — exactement ce que
    l'en-tête du module interdit.
    """
    template = rsl.SEARCH_PLATFORMS[key].template
    # `?q=` couvre le moteur généraliste, dont la route de recherche EST la
    # racine du site ; une URL de fiche n'a, elle, jamais de paramètre `q`.
    marker = ("search", "recherche", "find", "listeliv", "results", "?q=")
    assert any(m in template.lower() for m in marker), template


def test_hosts_are_written_without_www():
    """Le `www.` est retiré à la comparaison : le garder ici ne matcherait
    jamais."""
    for platform in rsl.SEARCH_PLATFORMS.values():
        for host in platform.hosts:
            assert not host.startswith("www."), platform


# ===== Ciblage par type ====================================================
def test_film_gets_the_platforms_the_apis_cannot_reach():
    """JustWatch et AlloCiné sont le SEUL chemin : TMDB ne renvoie plus de lien
    JustWatch et AlloCiné n'a pas d'API publique."""
    urls = _urls("Mulholland Drive", "David Lynch", ["film"], [])
    assert "JustWatch" in urls and "AlloCiné" in urls
    assert set(urls) == {"JustWatch", "AlloCiné", "SensCritique", "TMDB", "IMDb"}


def test_serie_gets_the_same_platforms_as_film():
    assert (set(_urls("Mortel", "", ["serie"], []))
            == set(_urls("Mortel", "", ["film"], [])))


def test_music_gets_listening_platforms():
    urls = _urls("Discovery", "Daft Punk", ["album"], [])
    assert set(urls) == {"Deezer", "Spotify", "Bandcamp", "Qobuz", "Apple Music"}


def test_book_prefers_independent_booksellers():
    """Politique éditoriale : on ne pousse pas vers Amazon (marqué `avoid`)."""
    urls = _urls("L’Étranger", "Camus", ["livre"], [])
    assert set(urls) == {"Place des Libraires", "Librairies indép.",
                         "OpenLibrary"}
    assert not any("amazon" in u for u in urls.values())


def test_comic_is_searched_like_a_book():
    assert set(_urls("Persepolis", "", ["bd"], [])) == set(
        _urls("Persepolis", "", ["livre"], []))


def test_podcast_deezer_url_targets_the_podcast_section():
    """Le drift TS↔Py sur Deezer a déjà été payé une fois : `/podcast`."""
    urls = _urls("Transfert", "", ["podcast"], [])
    assert set(urls) == {"Deezer", "Apple Podcasts"}
    assert urls["Deezer"].endswith("/podcast")


def test_game_falls_back_to_senscritique_and_steam():
    """IGDB répond 403 (Cloudflare) : écarté, ces deux-là le remplacent."""
    assert set(_urls("Celeste", "", ["jeu"], [])) == {"SensCritique", "Steam"}


@pytest.mark.parametrize("reco_type,expected", [
    # Fnac Spectacles réintégré le 2026-08-16 après vérification en navigateur.
    ("spectacle", {"BilletReduc", "Fnac Spectacles", "Web"}),
    ("lieu", {"Google Maps", "Web"}),
    ("chaine", {"YouTube", "Web"}),
    ("video", {"YouTube", "Web"}),
    ("application", {"Web"}),
    ("autre", {"Web"}),
])
def test_residual_types_always_get_a_generic_web_search(reco_type, expected):
    """« Au minimum une recherche web » : aucune ligne sans porte de sortie."""
    assert set(_urls("Titre", "", [reco_type], [])) == expected


def test_artist_gets_a_web_search_on_top_of_listening_platforms():
    """Dans ce corpus, un « artiste » est souvent un·e humoriste : Deezer seul
    laisserait la ligne sans issue."""
    assert "Web" in _urls("Blanche Gardin", "", ["artiste"], [])


def test_unknown_type_falls_back_to_a_web_search():
    assert set(_urls("Truc", "", ["type-inconnu"], [])) == {"Web"}


def test_reco_without_types_falls_back_to_a_web_search():
    assert set(_urls("Truc", "", [], [])) == {"Web"}


def test_reco_with_types_none_falls_back_to_a_web_search():
    assert set(_urls("Truc", "", None, [])) == {"Web"}


def test_multiple_types_union_their_platforms_in_order():
    labels = [s["label"] for s in rsl.search_links("X", "", ["film", "jeu"], [])]
    assert labels[:2] == ["JustWatch", "AlloCiné"]
    assert "Steam" in labels
    assert labels.count("SensCritique") == 1   # présent des deux côtés


def test_deezer_appears_once_for_a_music_podcast():
    """Deezer a deux gabarits (musique / podcast) mais UN seul libellé : deux
    puces « Deezer » sur la même ligne seraient illisibles."""
    found = rsl.search_links("X", "", ["musique", "podcast"], [])
    assert [s["label"] for s in found].count("Deezer") == 1
    deezer = next(s for s in found if s["label"] == "Deezer")
    assert deezer["url"].endswith("/X")   # gabarit musique, pas /podcast


# ===== On ne propose que ce qui manque =====================================
def test_platform_already_linked_is_not_proposed():
    urls = _urls("Discovery", "Daft Punk", ["album"],
                 [{"url": "https://www.deezer.com/fr/album/302127"}])
    assert "Deezer" not in urls
    assert "Spotify" in urls


def test_subdomain_counts_as_the_same_platform():
    """Une page d'artiste `xxx.bandcamp.com` vaut bien un lien Bandcamp."""
    urls = _urls("Home", "Resonance", ["musique"],
                 [{"url": "https://homeretro.bandcamp.com/album/odyssey"}])
    assert "Bandcamp" not in urls


def test_www_prefix_does_not_defeat_the_match():
    assert "AlloCiné" not in _urls(
        "Mortel", "", ["film"],
        [{"url": "https://www.allocine.fr/film/fichefilm_gen_cfilm=1.html"}])


def test_port_and_userinfo_do_not_defeat_the_match():
    """Une URL exotique ne doit pas rouvrir une puce déjà résolue."""
    assert "AlloCiné" not in _urls(
        "Mortel", "", ["film"],
        [{"url": "https://user@www.allocine.fr:443/film/1.html"}])


def test_a_platform_covered_once_stays_hidden_for_every_type():
    """Deezer couvert côté musique ne doit pas réapparaître côté podcast."""
    urls = _urls("X", "", ["musique", "podcast"],
                 [{"url": "https://www.deezer.com/fr/album/1"}])
    assert "Deezer" not in urls and "Apple Podcasts" in urls


def test_unrelated_link_hides_nothing():
    urls = _urls("Mortel", "", ["film"],
                 [{"url": "https://www.netflix.com/title/80990668"}])
    assert set(urls) == {"JustWatch", "AlloCiné", "SensCritique", "TMDB", "IMDb"}


def test_a_host_that_merely_ends_with_the_name_is_not_a_match():
    """`notdeezer.com` n'est pas Deezer — la comparaison est par étiquette de
    domaine, pas par sous-chaîne."""
    assert "Deezer" in _urls("X", "", ["musique"],
                             [{"url": "https://notdeezer.com/x"}])


def test_malformed_links_are_ignored_without_raising():
    urls = _urls("Mortel", "", ["film"], [
        "pas un objet",
        {"label": "sans url"},
        {"url": ""},
        {"url": "https:///chemin-sans-hote"},
    ])
    assert "AlloCiné" in urls


def test_links_none_is_tolerated():
    assert "AlloCiné" in _urls("Mortel", "", ["film"], None)


# ===== Requête et encodage =================================================
def test_query_joins_title_and_creator():
    assert "Discovery+Daft+Punk" in _urls(
        "Discovery", "Daft Punk", ["musique"], [])["Bandcamp"]


def test_query_uses_the_title_alone_when_there_is_no_creator():
    assert _urls("Discovery", "", ["musique"], [])["Bandcamp"].endswith(
        "q=Discovery")


def test_query_uses_the_creator_alone_when_there_is_no_title():
    """Un titre vide n'annule pas la recherche s'il reste un nom à chercher."""
    assert _urls("", "Daft Punk", ["musique"], [])["Bandcamp"].endswith(
        "q=Daft+Punk")


def test_untitled_and_uncredited_reco_gets_no_search_at_all():
    """Une puce qui ouvrirait un formulaire vide ne rend service à personne."""
    assert rsl.search_links("", "", ["film"], []) == []
    assert rsl.search_links("   ", None, ["film"], []) == []


def test_none_title_and_creator_are_tolerated():
    assert rsl.search_links(None, None, ["film"], []) == []


def test_query_string_uses_quote_plus():
    """En query string, `+` EST l'espace : `quote_plus` est la bonne règle."""
    assert _urls("L’Étranger", "Camus", ["livre"], [])["OpenLibrary"] == (
        "https://openlibrary.org/search?q=L%E2%80%99%C3%89tranger+Camus")


def test_path_segment_uses_percent_encoding_not_plus():
    """En segment de CHEMIN, un `+` resterait un `+` littéral : `%20`."""
    url = _urls("Discovery", "Daft Punk", ["musique"], [])["Deezer"]
    assert url == "https://www.deezer.com/fr/search/Discovery%20Daft%20Punk"
    assert "+" not in url


def test_url_special_characters_are_escaped():
    """Un titre avec `&`, `?` ou `#` ne doit pas fabriquer un autre paramètre."""
    url = _urls("Rock & Roll ?#1", "", ["musique"], [])["Bandcamp"]
    assert url == "https://bandcamp.com/search?q=Rock+%26+Roll+%3F%231"


# ===== Forme du résultat ===================================================
def test_each_entry_carries_a_label_a_url_and_a_hint():
    for entry in rsl.search_links("Mortel", "F. Garcia", ["film"], []):
        assert set(entry) == {"label", "url", "hint"}
        assert entry["url"].startswith("https://")
        assert "Mortel F. Garcia" in entry["hint"]
        assert entry["label"] in entry["hint"]


def test_hint_says_it_is_a_search_and_not_the_item_page():
    """L'info-bulle doit lever l'ambiguïté : c'est le seul texte que l'on lit
    avant de cliquer."""
    hint = rsl.search_links("Mortel", "", ["film"], [])[0]["hint"]
    assert "Recherche" in hint and "pas la fiche" in hint


# ===== Duplication surveillée avec review_links ============================
#
# `review_links` fabrique lui aussi des URL de recherche : 12 gabarits sont
# communs. On ne fusionne pas les deux modules (contrats opposés — cf. l'en-tête
# de `review_search_links`), donc on surveille l'écart. Le test interroge le
# COMPORTEMENT (`auto_url`) et non les littéraux, pour survivre à un refactor
# interne de `review_links`.

#: {label chez review_links: (clé ici, type à passer)}. Un label absent de
#: cette table n'existe que d'un seul côté — rien à comparer.
_SHARED = {
    "Bandcamp":            ("bandcamp", "musique"),
    "Deezer":              ("deezer", "musique"),
    "Spotify":             ("spotify", "musique"),
    "Qobuz":               ("qobuz", "musique"),
    "Apple Music":         ("apple_music", "musique"),
    "Apple Podcasts":      ("apple_podcasts", "podcast"),
    "Steam":               ("steam", "jeu"),
    "Place des Libraires": ("place_libraires", "livre"),
    "Où regarder":         ("justwatch", "film"),
    "YouTube":             ("youtube", "video"),
    "Google Maps":         ("google_maps", "lieu"),
    "Recherche":           ("web", "autre"),
}

#: Divergences VOULUES, avec leur raison. Toute autre divergence casse le test.
#:
#: VIDE depuis le 2026-07-31. BilletReduc y figurait : `review_links` recopiait
#: le soft-404 de `merchants.ts` (`/recherche/index.htm?txt=`, qui rend la même
#: page pour n'importe quelle requête). Plutôt que de vivre avec la divergence,
#: le site public a été corrigé — `merchants.ts` ET son miroir pointent
#: désormais `/search.htm?se=`, la forme qui cherche vraiment. Une divergence
#: déclarée doit rester un dernier recours : ici, la bonne réponse était de
#: réparer la source, pas de documenter le défaut.
_EXPECTED_DRIFT: dict[str, str] = {}

_SENTINEL = "SENTINELLE"


def _shape_from_review_links(label: str, in_type: str) -> str | None:
    """Gabarit tel que `review_links` le produit, requête remplacée par `{}`.

    On passe une reco SANS `externalIds` : c'est le chemin « repli recherche »
    de `auto_url`, le seul qui soit comparable au nôtre (l'autre renvoie une
    URL d'identifiant, ce qui est justement la différence de contrat).
    """
    from review_links import auto_url
    url = auto_url(label, {"title": _SENTINEL, "creator": "", "types": []},
                   in_type=in_type)
    return url if url is None else url.replace(_SENTINEL, "{}")


def _shape_from_here(key: str) -> str:
    """Même gabarit vu d'ici. La sentinelle est un mot sans caractère spécial :
    `quote` et `quote_plus` la laissent identique, les deux formes de gabarit
    sont donc comparables."""
    template = rsl.SEARCH_PLATFORMS[key].template
    return template.format(q=_SENTINEL, p=_SENTINEL).replace(_SENTINEL, "{}")


@pytest.mark.parametrize("label", sorted(_SHARED))
def test_shared_search_templates_do_not_drift(label):
    """Un gabarit qui change d'un seul côté est un bug silencieux : les deux
    modules enverraient l'utilisateur à deux endroits différents pour la même
    plateforme, sans que rien ne le signale."""
    key, in_type = _SHARED[label]
    mirror = _shape_from_review_links(label, in_type)
    if mirror is None:
        pytest.skip(f"« {label} » n'existe plus dans review_links")
    assert mirror == _shape_from_here(key), (
        f"« {label} » diverge. Si c'est voulu, déclare-le dans "
        f"_EXPECTED_DRIFT avec sa raison.")


def test_declared_drift_is_still_real():
    """Une divergence déclarée qui a disparu doit sortir de la liste, sinon
    la liste devient un cimetière qu'on cesse de lire.

    CE TEST N'AVAIT AUCUN CORPS jusqu'au 2026-08-18 : rien qu'une docstring,
    donc vert par construction et incapable de rougir. Il gonflait le compte
    et laissait croire qu'une propriété était vérifiée. La charge était
    déléguée au test paramétré ci-dessous, lui-même sans aucun cas tant que
    `_EXPECTED_DRIFT` est vide — personne ne vérifiait donc rien.

    L'assertion porte désormais sur ce que la liste PRÉTEND : chaque
    divergence déclarée doit désigner un libellé qui existe encore. Elle
    échoue le jour où l'un disparaît, et c'est exactement l'oubli qu'on
    craint.
    """
    inconnus = sorted(set(_EXPECTED_DRIFT) - set(_SHARED))
    assert not inconnus, (
        f"Divergence(s) déclarée(s) pour un libellé qui n'existe plus : "
        f"{inconnus}. Retire-les de `_EXPECTED_DRIFT`.")


@pytest.mark.parametrize("label", sorted(_EXPECTED_DRIFT))
def test_each_declared_drift_is_still_observable(label):
    """Chaque divergence déclarée doit être RÉELLEMENT observable."""
    key, in_type = _SHARED[label]
    mirror = _shape_from_review_links(label, in_type)
    assert mirror is not None, f"« {label} » a disparu de review_links"
    assert mirror != _shape_from_here(key), (
        f"« {label} » ne diverge plus : retire-le de _EXPECTED_DRIFT.")


def test_this_module_never_returns_an_external_id_url():
    """LA différence de contrat, en un test.

    `review_links.auto_url` renvoie `externalIds.deezer` quand il existe. Ici,
    jamais : une puce « 🔍 Deezer » qui ouvrirait la fiche au lieu d'une
    recherche serait un mensonge — et c'est ce champ-là qui a déjà menti une
    fois (les 145 `externalIds.justwatch` du corpus sont des URL TMDB).
    """
    reco_ext = {"deezer": "https://www.deezer.com/fr/album/302127",
                "justwatch": "https://www.themoviedb.org/tv/94801/watch"}
    # Le module n'accepte même pas `externalIds` : il ne peut pas s'en servir.
    urls = _urls("Discovery", "Daft Punk", ["musique"], [])
    assert all(reco_ext["deezer"] != u for u in urls.values())
    assert all("themoviedb.org" not in u for u in urls.values())


# ===== La ligne rouge ======================================================
def test_the_public_site_never_imports_this_module():
    """Ces URL sont un outil de RELECTURE. Sur le site public, une puce
    « JustWatch » doit mener à la fiche ; y publier une URL de recherche
    tromperait le visiteur. Le dépôt a déjà publié par accident une page
    d'administration pré-rendue — ce test est le garde-fou.
    """
    src = _REPO / "src"
    offenders = [p.relative_to(_REPO).as_posix()
                 for p in src.rglob("*")
                 if p.is_file() and p.suffix in {".ts", ".astro", ".js", ".mjs"}
                 and "review_search_links" in p.read_text(encoding="utf-8",
                                                          errors="replace")]
    assert offenders == []
