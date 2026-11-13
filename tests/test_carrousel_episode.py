"""Tests pour `tools/carrousel_episode.py` — pages, images et légendes, sans rendu ni réseau."""
from __future__ import annotations

import json

from PIL import Image

import carrousel_episode as ce

EP = {"numero": "S6 · E06", "titre": "Un titre", "invites": ["A", "B"], "lien": "https://unebonnere.co/x/",
      "recos": [{"type": "Film", "titre": "Court", "createur": "X", "citation": "« <b> »", "qui": "Navo",
                 "moment": "1:10"},
                {"type": "Série", "titre": "Un titre vraiment beaucoup trop long", "createur": "",
                 "citation": "c", "qui": "Kyan Khojandi", "moment": "2:00"}]}


def faux_telechargement(tailles):
    """Écrit une image de la taille voulue pour chaque adresse ; None pour les autres."""
    demandes = []

    def telecharger(url, chemin):
        demandes.append(url)
        if url not in tailles:
            return None
        chemin = chemin.with_suffix(".png")
        Image.new("RGB", tailles[url]).save(chemin)
        return chemin
    telecharger.demandes = demandes
    return telecharger


def test_pages_couverture_recos_fin_sans_image(tmp_path):
    pages = ce.pages(EP, tmp_path, telecharger=faux_telechargement({}))
    assert [p.name for p in pages] == ["01-couverture.html", "02-reco.html", "03-reco.html", "04-fin.html"]
    reco = pages[1].read_text(encoding="utf-8")
    assert "&lt;b&gt;" in reco and "Navo" in reco and "<img" not in reco
    assert "font-size: 116px" in pages[2].read_text(encoding="utf-8")
    assert "Images :" not in pages[3].read_text(encoding="utf-8")


def test_pages_telechargent_les_images_et_choisissent_la_mise_en_scene(tmp_path):
    ep = {**EP, "couverture": "https://yt/v.jpg",
          "recos": [{**EP["recos"][0], "image": "https://image.tmdb.org/t/p/w780/a.jpg"},
                    {**EP["recos"][1], "image": ["https://cdn-images.dzcdn.net/1.jpg", "https://absente/2.jpg"],
                     "mise": "double"}]}
    tel = faux_telechargement({"https://yt/v.jpg": (1280, 720), "https://image.tmdb.org/t/p/w780/a.jpg": (780, 1170),
                               "https://cdn-images.dzcdn.net/1.jpg": (1000, 1000)})
    pages = ce.pages(ep, tmp_path, telecharger=tel)
    textes = [p.read_text(encoding="utf-8") for p in pages]
    assert (tmp_path / "images" / "00-couverture.png").exists() and "00-couverture.png" in textes[0]
    assert "height: 460px" in textes[1] and "blur(46px)" in textes[1]
    # « double » demandé, mais une seule image téléchargée : la page reprend la mise calculée.
    assert "02-0.png" in textes[2] and "width: 440px; height: 440px" in textes[2] and "width: 400px" not in textes[2]
    # Seules les images réellement téléchargées sont créditées.
    assert "Images : affiches TMDB, pochettes Deezer, sites des œuvres" in textes[3]
    assert len(tel.demandes) == 4


def test_telecharger_ecrit_l_image_et_rate_proprement(tmp_path):
    class Reponse:
        def __init__(self, ok):
            self.ok, self.content = ok, b"\x89PNG"
            self.headers = {"content-type": "image/png"}

        def raise_for_status(self):
            if not self.ok:
                raise OSError("404")

    class Session:
        def __init__(self, ok):
            self.ok = ok

        def get(self, url, **kw):
            return Reponse(self.ok)

    chemin = ce.telecharger("https://x/a.jpg?w=1", tmp_path / "01-0", session=Session(True))
    assert chemin == tmp_path / "01-0.png" and chemin.read_bytes() == b"\x89PNG"
    assert ce.telecharger("https://x/b.jpg", tmp_path / "02-0", session=Session(False)) is None


def test_textes_groupent_par_type_et_suivent_les_images(tmp_path):
    t = ce.textes(EP)
    assert t["instagram"].startswith("Les 2 recos d’Un Bon Moment S6·E06, avec A et B 🎙️\n\n🎬 Court\n📺 Un titre")
    assert "lien en bio" in t["instagram"] and "https://unebonnere.co/x/" in t["threads"]
    assert t["instagram"].endswith("Site de fan, non officiel.")
    assert len(t["alts"]) == len(ce.pages(EP, tmp_path, telecharger=faux_telechargement({}))) == 4
    assert t["alts"][1] == "Reco 1 sur 2. Film : Court — X. « « <b> » » Reco de Navo, à 1:10."
    assert t["alts"][2].startswith("Reco 2 sur 2. Série : Un titre vraiment beaucoup trop long. «")


def test_main_ecrit_pages_legendes_et_textes_alternatifs(tmp_path, monkeypatch, capsys):
    (tmp_path / "episode.json").write_text(json.dumps(EP, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(ce, "rendre", lambda page: page.with_suffix(".png"))
    monkeypatch.setattr(ce, "telecharger", faux_telechargement({}))
    monkeypatch.setattr(ce, "LIMITE_THREADS", 10)
    assert ce.main(["carrousel", str(tmp_path)]) == 0
    assert (tmp_path / "legende-threads.txt").read_text(encoding="utf-8").startswith("Les 2 recos")
    assert len(json.loads((tmp_path / "alts.json").read_text(encoding="utf-8"))) == 4
    assert "ATTENTION" in capsys.readouterr().out
    assert ce.main(["carrousel"]) == 2


def test_rendre_demande_a_edge_une_capture_de_la_page(tmp_path, monkeypatch):
    appels = []
    monkeypatch.setattr(ce.subprocess, "run", lambda cmd, **kw: appels.append(cmd))
    page = tmp_path / "02-reco.html"
    assert ce.rendre(page) == tmp_path / "02-reco.png"
    assert "--window-size=1080,1350" in appels[0] and f"--screenshot={tmp_path / '02-reco.png'}" in appels[0]


def test_main_sans_alerte_quand_la_legende_threads_tient(tmp_path, monkeypatch, capsys):
    (tmp_path / "episode.json").write_text(json.dumps(EP, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(ce, "rendre", lambda page: page.with_suffix(".png"))
    monkeypatch.setattr(ce, "telecharger", faux_telechargement({}))
    assert ce.main(["carrousel", str(tmp_path)]) == 0
    assert "ATTENTION" not in capsys.readouterr().out
