"""Tests du client Qobuz — le seul qui lise du HTML plutôt qu'une API.

Aucun appel réel : `responses` sert toutes les pages. Les extraits HTML
reproduisent la structure observée le 2026-09-25 sur qobuz.com, y compris ses
pièges : le titre de piste affiché porte un suffixe (« (Bulerías) ») que le
`item_name` d'analytique n'a pas, et une recherche sans résultat pertinent rend
les chemins d'AUTRES artistes.

Le fil rouge : un lien n'est rendu que si la PAGE CIBLE nomme l'œuvre et
l'artiste. Tout le reste est un refus.
"""
from __future__ import annotations

import pytest
import requests
import responses

import music_links_qobuz as q

#: Qobuz déclare son encodage (vérifié : `Content-Type: text/html; charset=UTF-8`).
#: Sans lui, `requests` décoderait en ISO-8859-1 et « Camarón » serait illisible.
HTML = "text/html; charset=utf-8"
RECHERCHE = "https://www.qobuz.com/fr-fr/search"
ALBUM_URL = "https://www.qobuz.com/fr-fr/album/como-el-agua-camaron-de-la-isla/0060249871616"
ARTISTE_URL = "https://www.qobuz.com/fr-fr/interpreter/camaron-de-la-isla/39051"


@pytest.fixture()
def session():
    return requests.Session()


def _recherche_html(*chemins: str) -> str:
    liens = "".join(f'<a href="{c}">x</a>' for c in chemins)
    return f"<html><body><div class='results'>{liens}</div></body></html>"


def _album_html(titre="Como El Agua", artiste="Camarón de la Isla",
                pistes=("Como El Agua (Tangos)", "Gitana Te Quiero (Bulerías)"),
                item_names=("Como El Agua", "Gitana Te Quiero")) -> str:
    """Page album : JSON-LD Product + lignes de pistes, comme la vraie page."""
    lignes = "".join(
        '<div class="track__item track__item--name" itemprop="name">'
        f"<span>{p}</span></div>" for p in pistes)
    analytique = "".join(
        f'<a data-track-v2="{{&quot;item_name&quot;:&quot;{n}&quot;,'
        '&quot;item_id&quot;:1}">x</a>' for n in item_names)
    return f"""<html><head><title>{titre}, {artiste} - Qobuz</title>
<script type="application/ld+json">
{{"@context":"https://schema.org","@type":"Product","name":"{titre}",
  "brand":{{"@type":"Brand","name":"{artiste}"}}}}
</script>
<script type="application/ld+json">
{{"@type":"MusicAlbum","name":"{titre}"}}
</script></head><body>{lignes}{analytique}</body></html>"""


def _artiste_html(nom="Camarón de la Isla") -> str:
    return (f"<html><head><title>Discographie de {nom} - Téléchargez des albums"
            " en Hi-Res - Qobuz</title></head><body></body></html>")


# ===== extraction des chemins de recherche ==================================
@responses.activate
def test_search_paths_keeps_album_paths_in_order_without_duplicates(session):
    responses.add(responses.GET, RECHERCHE, status=200, content_type=HTML,
                  body=_recherche_html("/fr-fr/album/aa/111", "/fr-fr/album/aa/111",
                                       "/fr-fr/album/bb/222"))

    assert q.search_paths(session, "album", "x") == [
        "https://www.qobuz.com/fr-fr/album/aa/111",
        "https://www.qobuz.com/fr-fr/album/bb/222"]


@responses.activate
def test_search_paths_for_artist_ignores_album_paths(session):
    """Une reco d'artiste veut la page interprète, jamais un album."""
    responses.add(responses.GET, RECHERCHE, status=200, content_type=HTML,
                  body=_recherche_html("/fr-fr/album/aa/111",
                                       "/fr-fr/interpreter/camaron/39051"))

    assert q.search_paths(session, "artist", "x") == [
        "https://www.qobuz.com/fr-fr/interpreter/camaron/39051"]


@responses.activate
def test_search_paths_caps_the_number_of_pages_opened(session):
    """Une page Qobuz pèse ~300 Ko : le nombre d'ouvertures est borné."""
    responses.add(responses.GET, RECHERCHE, status=200, content_type=HTML,
                  body=_recherche_html(*[f"/fr-fr/album/a{i}/{i}" for i in range(9)]))

    assert len(q.search_paths(session, "album", "x")) == q.MAX_PAGES


@responses.activate
def test_search_paths_empty_on_http_error(session):
    responses.add(responses.GET, RECHERCHE, status=403, body="nope")
    assert q.search_paths(session, "album", "x") == []


def test_search_paths_empty_on_network_failure(session):
    """Aucune exception ne doit remonter : la passe continue sans Qobuz."""
    with responses.RequestsMock():  # toute requête non déclarée échoue
        assert q.search_paths(session, "album", "x") == []


# ===== lecture d'une page ===================================================
def test_album_identity_reads_title_and_artist_from_json_ld():
    assert q.album_identity(_album_html()) == ("Como El Agua", "Camarón de la Isla")


def test_album_identity_empty_without_json_ld():
    assert q.album_identity("<html><title>Como El Agua</title></html>") == ("", "")


def test_album_identity_empty_when_json_ld_is_unreadable():
    """Un bloc JSON-LD tronqué ne doit pas faire tomber la passe."""
    page = ('<script type="application/ld+json">{"@type":"Product",</script>')
    assert q.album_identity(page) == ("", "")


def test_album_identity_ignores_product_without_brand():
    page = ('<script type="application/ld+json">'
            '{"@type":"Product","name":"Sans marque"}</script>')
    assert q.album_identity(page) == ("", "")


def test_artist_identity_reads_the_discography_title():
    assert q.artist_identity(_artiste_html()) == "Camarón de la Isla"


def test_artist_identity_prefers_json_ld_when_present():
    page = ('<script type="application/ld+json">'
            '{"@type":"MusicGroup","name":"Solann"}</script>'
            "<title>Discographie de Autre Chose - Qobuz</title>")
    assert q.artist_identity(page) == "Solann"


def test_artist_identity_empty_on_unexpected_title():
    assert q.artist_identity("<html><title>Qobuz</title></html>") == ""


def test_track_names_reads_both_markups():
    """Le titre affiché porte le suffixe, l'`item_name` ne l'a pas : on veut les deux."""
    noms = q.track_names(_album_html())

    assert "Gitana Te Quiero (Bulerías)" in noms
    assert "Gitana Te Quiero" in noms


# ===== candidats corroborés =================================================
@responses.activate
def test_candidates_album_is_corroborated_by_its_page(session):
    responses.add(responses.GET, RECHERCHE, status=200, content_type=HTML,
                  body=_recherche_html("/fr-fr/album/como-el-agua/0060249871616"))
    responses.add(responses.GET,
                  "https://www.qobuz.com/fr-fr/album/como-el-agua/0060249871616",
                  status=200, content_type=HTML, body=_album_html())

    trouves = q.candidates(session, "album", "Como el agua Camarón de la Isla")

    assert [(c.title, c.artist, c.ident) for c in trouves] == [
        ("Como El Agua", "Camarón de la Isla", "0060249871616")]


@responses.activate
def test_candidates_track_keeps_the_album_that_lists_it(session):
    """Pour un morceau, la cible est l'album — s'il porte vraiment la piste."""
    responses.add(responses.GET, RECHERCHE, status=200, content_type=HTML,
                  body=_recherche_html("/fr-fr/album/aa/111"))
    responses.add(responses.GET, "https://www.qobuz.com/fr-fr/album/aa/111",
                  status=200, content_type=HTML, body=_album_html())

    trouves = q.candidates(session, "track", "Gitana Te Quiero Camarón",
                           wanted_title="Gitana te quiero")

    assert [(c.title, c.artist) for c in trouves] == [
        ("Gitana Te Quiero", "Camarón de la Isla")]


@responses.activate
def test_candidates_track_refused_when_the_album_does_not_list_it(session):
    responses.add(responses.GET, RECHERCHE, status=200, content_type=HTML,
                  body=_recherche_html("/fr-fr/album/aa/111"))
    responses.add(responses.GET, "https://www.qobuz.com/fr-fr/album/aa/111",
                  status=200, content_type=HTML, body=_album_html())

    assert q.candidates(session, "track", "x", wanted_title="Une autre piste") == []


@responses.activate
def test_candidates_track_without_wanted_title_is_refused(session):
    responses.add(responses.GET, RECHERCHE, status=200, content_type=HTML,
                  body=_recherche_html("/fr-fr/album/aa/111"))
    responses.add(responses.GET, "https://www.qobuz.com/fr-fr/album/aa/111",
                  status=200, content_type=HTML, body=_album_html())

    assert q.candidates(session, "track", "x", wanted_title=None) == []


@responses.activate
def test_candidates_artist_page(session):
    responses.add(responses.GET, RECHERCHE, status=200, content_type=HTML,
                  body=_recherche_html("/fr-fr/interpreter/camaron/39051"))
    responses.add(responses.GET, ARTISTE_URL.replace("camaron-de-la-isla", "camaron"),
                  status=200, content_type=HTML, body=_artiste_html())

    trouves = q.candidates(session, "artist", "Camarón de la Isla")

    assert [(c.artist, c.title, c.ident) for c in trouves] == [
        ("Camarón de la Isla", "", "39051")]


@responses.activate
def test_candidates_returns_what_the_page_says_not_what_was_searched(session):
    """La recherche « Mona Guba » renvoie un autre artiste : le candidat porte CE nom.

    C'est ainsi que `verdict()` peut le refuser — s'il portait le nom cherché,
    la corroboration serait circulaire.
    """
    responses.add(responses.GET, RECHERCHE, status=200, content_type=HTML,
                  body=_recherche_html("/fr-fr/interpreter/amparo-sanchez/290605"))
    responses.add(responses.GET,
                  "https://www.qobuz.com/fr-fr/interpreter/amparo-sanchez/290605",
                  status=200, content_type=HTML,
                  body=_artiste_html("Amparo Sánchez"))

    trouves = q.candidates(session, "artist", "Mona Guba")

    assert [c.artist for c in trouves] == ["Amparo Sánchez"]


@responses.activate
def test_candidates_skips_a_page_that_fails(session):
    """Une page en erreur n'arrête pas l'examen des suivantes."""
    responses.add(responses.GET, RECHERCHE, status=200, content_type=HTML,
                  body=_recherche_html("/fr-fr/album/aa/111", "/fr-fr/album/bb/222"))
    responses.add(responses.GET, "https://www.qobuz.com/fr-fr/album/aa/111",
                  status=429, body="trop de requêtes")
    responses.add(responses.GET, "https://www.qobuz.com/fr-fr/album/bb/222",
                  status=200, content_type=HTML, body=_album_html())

    assert [c.ident for c in q.candidates(session, "album", "x")] == ["222"]


@responses.activate
def test_candidates_skips_a_page_that_is_not_an_album(session):
    """La recherche peut mener à une page sans JSON-LD d'album : on passe."""
    responses.add(responses.GET, RECHERCHE, status=200, content_type=HTML,
                  body=_recherche_html("/fr-fr/album/aa/111"))
    responses.add(responses.GET, "https://www.qobuz.com/fr-fr/album/aa/111",
                  status=200, content_type=HTML,
                  body="<html><body>page sans données structurées</body></html>")

    assert q.candidates(session, "album", "x") == []


# ===== formes inattendues du JSON-LD ========================================
def test_album_identity_walks_past_a_non_product_object():
    """L'ordre des blocs n'est pas garanti : le Product peut venir en second."""
    page = ('<script type="application/ld+json">{"@type":"MusicAlbum",'
            '"name":"Como El Agua"}</script>'
            '<script type="application/ld+json">{"@type":"Product",'
            '"name":"Como El Agua","brand":{"name":"Camarón de la Isla"}}</script>')

    assert q.album_identity(page) == ("Como El Agua", "Camarón de la Isla")


def test_json_ld_array_with_a_stray_string_is_tolerated():
    page = ('<script type="application/ld+json">["du texte",'
            '{"@type":"Product","name":"X","brand":{"name":"Y"}}]</script>')

    assert q.album_identity(page) == ("X", "Y")


def test_artist_identity_empty_when_the_page_has_no_title():
    """Page tronquée : aucun nom à corroborer, donc aucun candidat."""
    assert q.artist_identity("<html><body>rien</body></html>") == ""


@responses.activate
def test_candidates_skips_an_artist_page_without_a_name(session):
    """Si la page ne nomme personne, il n'y a rien à corroborer : pas de candidat."""
    responses.add(responses.GET, RECHERCHE, status=200, content_type=HTML,
                  body=_recherche_html("/fr-fr/interpreter/inconnu/1"))
    responses.add(responses.GET, "https://www.qobuz.com/fr-fr/interpreter/inconnu/1",
                  status=200, content_type=HTML, body="<html><body>?</body></html>")

    assert q.candidates(session, "artist", "Solann") == []


def test_artist_identity_falls_back_when_json_ld_has_no_name():
    page = ('<script type="application/ld+json">{"@type":"MusicGroup"}</script>'
            "<title>Discographie de Solann - Qobuz</title>")

    assert q.artist_identity(page) == "Solann"
