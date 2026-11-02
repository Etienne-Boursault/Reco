"""Tests de verifier_liens : site construit factice, sonde factice, aucun réseau."""
from __future__ import annotations

import json
import threading
import time

import pytest

import verifier_liens as vl
from link_check import ProbeResult


def _page(dist, chemin, *hrefs):
    fichier = dist / chemin
    fichier.parent.mkdir(parents=True, exist_ok=True)
    fichier.write_text("".join(f'<a class="x" href="{h}">lien</a>' for h in hrefs),
                       encoding="utf-8")


@pytest.fixture
def dist(tmp_path, monkeypatch):
    # Le site se lit dans SITE_URL : la CI le fixe à https://example.com.
    monkeypatch.setattr(vl, "SITE", "unebonnere.co")
    d = tmp_path / "dist"
    _page(d, "index.html", "/un-bon-moment/", "/a-propos", "https://www.deezer.com/track/1",
          "https://unebonnere.co/manifeste/", "mailto:contact@example.org", "#haut",
          "/api/report", "https://www.youtube.com/watch?v=a&amp;t=3")
    _page(d, "un-bon-moment/index.html", "/un-bon-moment/oeuvre/abc/", "/disparue/")
    _page(d, "a-propos.html")
    _page(d, "manifeste/index.html")
    _page(d, "un-bon-moment/oeuvre/abc/index.html", "https://www.deezer.com/track/1")
    return d


def test_internal_and_external_links_are_told_apart(dist):
    internes, externes = vl.liens(dist)
    assert set(internes) == {"/un-bon-moment/", "/a-propos", "/manifeste/", "/api/report",
                             "/un-bon-moment/oeuvre/abc/", "/disparue/"}
    assert set(externes) == {"https://www.deezer.com/track/1",
                             "https://www.youtube.com/watch?v=a&t=3"}
    assert externes["https://www.deezer.com/track/1"] == {"/", "/un-bon-moment/oeuvre/abc/"}


def test_only_the_missing_page_is_a_broken_internal_link(dist):
    assert vl.internes_casses(dist) == {"/disparue/": {"/un-bon-moment/"}}


@pytest.mark.parametrize(("chemin", "attendu"), [
    ("/a-propos", True),          # a-propos.html
    ("/manifeste/", True),        # manifeste/index.html
    ("/manifeste", True),         # sans barre finale, comme le serveur
    ("/api/click", True),         # route servie à la demande
    ("/audience", True),
    ("/a-propos/", False),        # la barre finale exige un dossier
])
def test_a_path_exists_like_the_server_would_serve_it(dist, chemin, attendu):
    assert vl.existe(dist, chemin) is attendu


def test_internes_command_fails_on_a_broken_link(dist, capsys):
    assert vl.main(["internes", str(dist)]) == 1
    assert "/disparue/" in capsys.readouterr().out


@pytest.mark.parametrize("mode", ["internes", "externes"])
def test_a_missing_build_is_an_error_not_a_clean_site(tmp_path, mode):
    vide = tmp_path / "dist"
    vide.mkdir()
    extra = [] if mode == "internes" else ["--etat", str(tmp_path / "e"), "--sortie",
                                           str(tmp_path / "s")]
    assert vl.main([mode, str(vide), *extra]) == 2


def test_one_site_is_never_probed_twice_at_once():
    en_cours, chevauchements, verrou = {}, [], threading.Lock()

    def sonde(url):
        hote = url.split("/")[2]
        with verrou:
            if en_cours.get(hote):
                chevauchements.append(url)
            en_cours[hote] = True
        time.sleep(0.01)
        with verrou:
            en_cours[hote] = False
        return ProbeResult("alive", "HTTP 200", "titre")

    urls = [f"https://{h}.example/{k}" for h in "abc" for k in range(4)]
    resultats = vl.sonder(urls, sonde, pause=0)
    assert len(resultats) == 12 and chevauchements == []


def test_a_crashing_probe_is_unknown_not_dead():
    def sonde(url):
        raise ValueError("boum")
    assert vl.sonder(["https://a.example/"], sonde, pause=0)["https://a.example/"].verdict \
        == "unknown"


def _recos(tmp_path):
    d = tmp_path / "recos" / "src"
    d.mkdir(parents=True)
    (d / "1.json").write_text(json.dumps({"id": "ubm-0001", "status": "validated",
                                          "links": [{"url": "https://mort.example/"}]}))
    (d / "2.json").write_text(json.dumps({"id": "ubm-0002", "status": "discarded",
                                          "links": [{"url": "https://mort.example/"}]}))
    return tmp_path / "recos"


def test_a_dead_link_names_its_displayed_recos_only(tmp_path):
    recos = vl.recos_par_url(_recos(tmp_path))
    rapport = vl.rapporter({"https://mort.example/": ProbeResult("dead", "HTTP 404"),
                            "https://vivant.example/": ProbeResult("alive", "HTTP 200", "t"),
                            "https://www.netflix.com/title/1": ProbeResult("unknown", "x")},
                           {"https://mort.example/": {"/ep/"}}, recos, set())
    assert rapport.morts["https://mort.example/"]["recos"] == ["ubm-0001"]
    assert rapport.vivants == 1 and rapport.inconnus_par_site == {"netflix.com": 1}
    assert rapport.nouveaux == ["https://mort.example/"]


def test_a_link_already_dead_last_time_is_not_announced_again():
    rapport = vl.rapporter({"https://mort.example/": ProbeResult("dead", "HTTP 404")},
                           {}, {}, {"https://mort.example/"})
    assert rapport.nouveaux == [] and vl.message(rapport, "r.md") is None


def test_the_message_is_cut_but_says_how_many_remain():
    resultats = {f"https://m.example/{k}": ProbeResult("dead", "HTTP 404") for k in range(20)}
    texte = vl.message(vl.rapporter(resultats, {}, {}, set()), "r.md")
    assert texte.count("\n- ") == vl.MESSAGE_MAX and "… et 5 autre(s)." in texte
    assert "Rien n'a été retiré" in texte


def test_externes_command_keeps_the_dead_for_next_time(dist, tmp_path, monkeypatch):
    monkeypatch.setattr(vl, "sonder", lambda urls: {
        u: ProbeResult("dead" if "deezer" in u else "alive", "HTTP 404", "t") for u in urls})
    etat, sortie = tmp_path / "etat.json", tmp_path / "rapports"
    args = ["externes", str(dist), "--recos", str(_recos(tmp_path)),
            "--etat", str(etat), "--sortie", str(sortie)]

    assert vl.main(args) == 0
    assert json.loads(etat.read_text())["morts"] == ["https://www.deezer.com/track/1"]
    rapport = next(sortie.glob("liens-*.md")).read_text(encoding="utf-8")
    assert "https://www.deezer.com/track/1 🆕" in rapport

    assert vl.main(args) == 0
    assert "🆕" not in next(sortie.glob("liens-*.md")).read_text(encoding="utf-8")
