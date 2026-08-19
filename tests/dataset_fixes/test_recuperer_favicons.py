"""Tests de `tools/recuperer_favicons.py`.

CE QUE LA RELECTURE A VU
------------------------
« L'icone de Molotov TV n'est pas la bonne, utilise la FAVicon » (2026-08-19).
Elle affichait un « m » en Arial. Trente-huit icones sur soixante-cinq etaient
dans ce cas : une lettre dans une police systeme, posee faute de logo.

CE QUE CES TESTS PROTEGENT
--------------------------
Le RESEAU n'est pas teste ici — il est injecte. Ce qui est verifie, c'est ce
qui decide : reconnaitre un placeholder, refuser une image qui n'en est pas
une, et ne jamais produire un SVG qui appellerait un serveur tiers.

Ce dernier point est le plus important. Une favicon distante fuiterait
l'adresse IP et le referent de chaque visiteur vers la plateforme, ce que le
depot s'interdit depuis l'ADR 0034. L'image doit etre integree, toujours.
"""
from __future__ import annotations

import base64
import io
import re
from pathlib import Path

import pytest
from PIL import Image

import recuperer_favicons as rf


def png(taille: int = 32, couleurs: int = 2) -> bytes:
    """Un PNG carre, avec assez de couleurs pour ne pas passer pour vide."""
    img = Image.new("RGBA", (taille, taille), (200, 30, 40, 255))
    if couleurs > 1:
        for x in range(taille // 2):
            for y in range(taille // 2):
                img.putpixel((x, y), (10, 20, 200, 255))
    tampon = io.BytesIO()
    img.save(tampon, format="PNG")
    return tampon.getvalue()


PLACEHOLDER = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
               '<rect width="24" height="24" fill="#000"/>'
               '<text x="12" y="17">A</text></svg>')
VRAI_LOGO = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
             '<path d="M2 2h20v20H2z"/></svg>')


# ===== Reconnaitre un placeholder ==========================================
def test_une_lettre_est_un_placeholder():
    assert rf.est_placeholder(PLACEHOLDER)


def test_un_trace_n_en_est_pas_un():
    assert not rf.est_placeholder(VRAI_LOGO)


def test_une_favicon_deja_integree_n_en_est_pas_un():
    """Sinon la passe se relancerait indefiniment sur son propre resultat."""
    svg = rf.svg_de_png(png(), "exemple.fr", "https://exemple.fr/favicon.ico")
    assert not rf.est_placeholder(svg)


# ===== Ce qui est refuse ===================================================
def test_un_fichier_qui_n_est_pas_une_image_est_refuse():
    """Certains hotes servent du HTML sur `/favicon.ico`."""
    assert rf.en_png(b"<!doctype html><html>404</html>") is None


def test_un_contenu_vide_est_refuse():
    assert rf.en_png(b"") is None


def test_une_image_TROP_PETITE_est_refusee():
    assert rf.en_png(png(taille=8)) is None


def test_une_image_D_UNE_SEULE_COULEUR_est_refusee():
    """C'est le carre vide que renvoient les serveurs sans icone."""
    assert rf.en_png(png(couleurs=1)) is None


def test_une_image_RICHE_est_acceptee():
    """Le test ci-dessus passait meme quand tout etait refuse : mes images
    d'essai n'avaient que deux couleurs. Une vraie favicon en compte des
    centaines, et `getcolors(maxcolors=N)` rend `None` au-dela de N — donc
    `None` veut dire « riche », pas « vide ». La premiere version lisait
    l'inverse et rejetait les trente-huit favicons a remplacer."""
    riche = Image.new("RGBA", (64, 64))
    for x in range(64):
        for y in range(64):
            riche.putpixel((x, y), (x * 4 % 256, y * 4 % 256, (x + y) % 256, 255))
    tampon = io.BytesIO()
    riche.save(tampon, format="PNG")
    resultat = rf.en_png(tampon.getvalue())
    assert resultat is not None


# ===== La conversion =======================================================
def test_une_image_valide_donne_un_png_carre():
    resultat = rf.en_png(png(taille=64))
    assert resultat is not None
    brut, taille = resultat
    assert brut[:8] == b"\x89PNG\r\n\x1a\n"
    img = Image.open(io.BytesIO(brut))
    assert img.size[0] == img.size[1]
    assert f"{img.size[0]}x{img.size[1]}" == taille


def test_une_grande_image_est_ramenee_a_la_taille_cible():
    """Elle est affichee entre 16 et 24 px : au-dela, elle pese pour rien."""
    brut, _ = rf.en_png(png(taille=256))
    assert Image.open(io.BytesIO(brut)).size == (rf.TAILLE_CIBLE, rf.TAILLE_CIBLE)


def test_une_petite_image_n_est_pas_agrandie_a_l_exces():
    """Agrandir un 16 px en 64 ne produit que du flou."""
    brut, _ = rf.en_png(png(taille=16))
    assert Image.open(io.BytesIO(brut)).size[0] <= 32


# ===== Le SVG produit ======================================================
def test_le_svg_n_appelle_AUCUN_serveur_tiers():
    """Le point le plus important : une favicon distante fuiterait l'adresse
    IP et le referent de chaque visiteur vers la plateforme."""
    svg = rf.svg_de_png(png(), "exemple.fr", "https://exemple.fr/favicon.ico")
    # Seule l'URL SOURCE apparait, en commentaire — jamais dans un attribut.
    sans_commentaires = re.sub(r"<!--.*?-->", "", svg, flags=re.DOTALL)
    assert not re.search(r'(?:href|src)="https?://', sans_commentaires)


def test_le_svg_porte_l_image_en_data_uri():
    svg = rf.svg_de_png(png(), "exemple.fr", "https://exemple.fr/favicon.ico")
    m = re.search(r'href="data:image/png;base64,([^"]+)"', svg)
    assert m
    assert base64.b64decode(m.group(1))[:8] == b"\x89PNG\r\n\x1a\n"


def test_le_svg_garde_la_trace_de_sa_source():
    """Sans elle, impossible de savoir d'ou vient l'image ni de la refaire."""
    svg = rf.svg_de_png(png(), "exemple.fr", "https://exemple.fr/icone.png")
    assert "https://exemple.fr/icone.png" in svg
    assert "exemple.fr" in svg


def test_le_svg_a_les_dimensions_des_autres_icones():
    svg = rf.svg_de_png(png(), "exemple.fr", "https://exemple.fr/f.ico")
    assert 'viewBox="0 0 24 24"' in svg
    assert 'width="24"' in svg


# ===== La passe ============================================================
@pytest.fixture
def dossier(tmp_path: Path, monkeypatch) -> Path:
    (tmp_path / "avec-logo.fr.svg").write_text(VRAI_LOGO, encoding="utf-8")
    (tmp_path / "avec-lettre.fr.svg").write_text(PLACEHOLDER, encoding="utf-8")
    monkeypatch.setattr(rf, "telecharger", lambda url, **kw: png(64))
    return tmp_path


def test_seuls_les_placeholders_sont_remplaces(dossier: Path):
    avant = (dossier / "avec-logo.fr.svg").read_text(encoding="utf-8")
    rapport = rf.executer(dossier, apply=True)
    assert (dossier / "avec-logo.fr.svg").read_text(encoding="utf-8") == avant
    assert "<text" not in (dossier / "avec-lettre.fr.svg").read_text(encoding="utf-8")
    assert rapport["remplaces"] == 1


def test_la_simulation_n_ecrit_rien(dossier: Path):
    avant = (dossier / "avec-lettre.fr.svg").read_text(encoding="utf-8")
    rapport = rf.executer(dossier, apply=False)
    assert (dossier / "avec-lettre.fr.svg").read_text(encoding="utf-8") == avant
    assert rapport["remplaces"] == 1


def test_un_hote_SANS_favicon_garde_sa_lettre(dossier: Path, monkeypatch):
    """Une lettre vaut mieux qu'une image cassee."""
    monkeypatch.setattr(rf, "telecharger", lambda url, **kw: None)
    avant = (dossier / "avec-lettre.fr.svg").read_text(encoding="utf-8")
    rapport = rf.executer(dossier, apply=True)
    assert (dossier / "avec-lettre.fr.svg").read_text(encoding="utf-8") == avant
    assert rapport["echecs"] == ["avec-lettre.fr"]


def test_un_hote_qui_sert_du_html_garde_sa_lettre(dossier: Path, monkeypatch):
    monkeypatch.setattr(rf, "telecharger", lambda url, **kw: b"<html>oups</html>")
    rapport = rf.executer(dossier, apply=True)
    assert "<text" in (dossier / "avec-lettre.fr.svg").read_text(encoding="utf-8")
    assert rapport["echecs"] == ["avec-lettre.fr"]


def test_l_option_host_limite_la_passe(dossier: Path):
    (dossier / "autre.fr.svg").write_text(PLACEHOLDER, encoding="utf-8")
    rf.executer(dossier, apply=True, seulement=["autre.fr"])
    assert "<text" in (dossier / "avec-lettre.fr.svg").read_text(encoding="utf-8")
    assert "<text" not in (dossier / "autre.fr.svg").read_text(encoding="utf-8")


# ===== Ajouter un hote qui n'avait aucune icone ============================
def test_un_hote_SANS_fichier_est_cree_quand_on_le_demande(dossier: Path):
    """`www.imdb.com` apparait dans 353 liens du corpus et n'avait aucune
    icone : l'outil ne savait que remplacer une lettre par un logo, donc les
    plateformes jamais dessinees restaient invisibles."""
    rapport = rf.executer(dossier, apply=True, seulement=["neuf.fr"])
    cree = dossier / "neuf.fr.svg"
    assert cree.exists()
    assert not rf.est_placeholder(cree.read_text(encoding="utf-8"))
    assert rapport["ajoutes"] == 1


def test_un_ajout_n_est_pas_compte_comme_un_remplacement(dossier: Path):
    """Les deux gestes n'ont pas le meme sens : l'un corrige une lettre,
    l'autre etend la couverture. Les confondre rendrait le rapport muet."""
    rapport = rf.executer(dossier, apply=True,
                          seulement=["neuf.fr", "avec-lettre.fr"])
    assert (rapport["ajoutes"], rapport["remplaces"]) == (1, 1)


def test_un_hote_inconnu_n_est_PAS_cree_sans_demande_explicite(dossier: Path):
    """La creation est un geste editorial : on n'invente pas des icones pour
    des hotes que personne n'a demandes."""
    rf.executer(dossier, apply=True)
    assert sorted(p.name for p in dossier.glob("*.svg")) == [
        "avec-lettre.fr.svg", "avec-logo.fr.svg"]


def test_un_ajout_SANS_favicon_ne_laisse_pas_de_fichier_vide(dossier: Path,
                                                             monkeypatch):
    """Un SVG vide serait pire que pas d'icone : le site afficherait un carre
    blanc au lieu de retomber sur son symbole generique."""
    monkeypatch.setattr(rf, "telecharger", lambda url, **kw: None)
    rapport = rf.executer(dossier, apply=True, seulement=["neuf.fr"])
    assert not (dossier / "neuf.fr.svg").exists()
    assert "neuf.fr" in rapport["echecs"]


def test_la_simulation_ne_CREE_aucun_fichier(dossier: Path):
    rapport = rf.executer(dossier, apply=False, seulement=["neuf.fr"])
    assert not (dossier / "neuf.fr.svg").exists()
    assert rapport["ajoutes"] == 1


def test_un_hote_deja_dote_d_un_VRAI_logo_n_est_pas_recree(dossier: Path):
    """Redemander un hote qui a deja son logo ne doit pas l'ecraser par une
    favicon fraiche : le trace pose a la main est souvent meilleur."""
    avant = (dossier / "avec-logo.fr.svg").read_text(encoding="utf-8")
    rapport = rf.executer(dossier, apply=True, seulement=["avec-logo.fr"])
    assert (dossier / "avec-logo.fr.svg").read_text(encoding="utf-8") == avant
    assert (rapport["ajoutes"], rapport["remplaces"]) == (0, 0)


def test_la_passe_est_idempotente(dossier: Path):
    rf.executer(dossier, apply=True)
    assert rf.executer(dossier, apply=True)["remplaces"] == 0


# ===== Les pistes ==========================================================
def test_la_piste_conventionnelle_est_toujours_essayee(monkeypatch):
    monkeypatch.setattr(rf, "telecharger", lambda url, **kw: None)
    assert rf.pistes_favicon("exemple.fr") == ["https://exemple.fr/favicon.ico"]


def test_la_favicon_DECLAREE_passe_avant(monkeypatch):
    html = b'<html><link rel="icon" href="/assets/logo.png"></html>'
    monkeypatch.setattr(rf, "telecharger", lambda url, **kw: html)
    pistes = rf.pistes_favicon("exemple.fr")
    assert pistes[0] == "https://exemple.fr/assets/logo.png"
    assert pistes[-1] == "https://exemple.fr/favicon.ico"


def test_une_piste_absolue_est_gardee_telle_quelle(monkeypatch):
    html = b'<html><link rel="shortcut icon" href="https://cdn.ex.fr/i.png"></html>'
    monkeypatch.setattr(rf, "telecharger", lambda url, **kw: html)
    assert rf.pistes_favicon("exemple.fr")[0] == "https://cdn.ex.fr/i.png"


def test_les_pistes_ne_sont_jamais_repetees(monkeypatch):
    html = (b'<html><link rel="icon" href="/favicon.ico">'
            b'<link rel="shortcut icon" href="/favicon.ico"></html>')
    monkeypatch.setattr(rf, "telecharger", lambda url, **kw: html)
    assert len(rf.pistes_favicon("exemple.fr")) == 1


def test_telecharger_rend_None_sur_une_reponse_vide(monkeypatch):
    """Certains hotes repondent 200 avec un corps vide."""
    class Vide:
        stdout = b""
    monkeypatch.setattr(rf.subprocess, "run", lambda *a, **kw: Vide())
    assert rf.telecharger("https://exemple.fr/") is None


def test_telecharger_rend_le_corps_quand_curl_reussit(monkeypatch):
    class Reponse:
        stdout = b"des octets"
    monkeypatch.setattr(rf.subprocess, "run", lambda *a, **kw: Reponse())
    assert rf.telecharger("https://exemple.fr/") == b"des octets"


def test_une_balise_icon_SANS_href_est_ignoree(monkeypatch):
    """Elle existe dans la nature, et casserait la recherche du groupe."""
    html = b'<html><link rel="icon" type="image/png"><link rel="icon" href="/bon.png"></html>'
    monkeypatch.setattr(rf, "telecharger", lambda url, **kw: html)
    assert rf.pistes_favicon("exemple.fr")[0] == "https://exemple.fr/bon.png"


def test_telecharger_rend_None_quand_curl_echoue(monkeypatch):
    def echoue(*a, **kw):
        raise OSError("curl absent")
    monkeypatch.setattr(rf.subprocess, "run", echoue)
    assert rf.telecharger("https://exemple.fr/") is None


# ===== CLI =================================================================
def test_main_simulation(dossier: Path, monkeypatch):
    monkeypatch.setattr(rf, "DOSSIER", dossier)
    avant = (dossier / "avec-lettre.fr.svg").read_text(encoding="utf-8")
    assert rf.main([]) == 0
    assert (dossier / "avec-lettre.fr.svg").read_text(encoding="utf-8") == avant


def test_main_applique(dossier: Path, monkeypatch):
    monkeypatch.setattr(rf, "DOSSIER", dossier)
    assert rf.main(["--apply"]) == 0
    assert "<text" not in (dossier / "avec-lettre.fr.svg").read_text(encoding="utf-8")


def test_main_journalise_les_echecs(dossier: Path, monkeypatch, caplog):
    monkeypatch.setattr(rf, "DOSSIER", dossier)
    monkeypatch.setattr(rf, "telecharger", lambda url, **kw: None)
    with caplog.at_level("WARNING"):
        assert rf.main(["--apply"]) == 0
    assert "SANS FAVICON" in caplog.text
