"""Tests de `tools/commentaire_youtube.py` et `tools/youtube_autoriser.py`.

Rien ne part sur le reseau : une fausse session HTTP joue le site et l'API
YouTube, et enregistre ce qu'on lui demande.
"""
from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

import commentaire_youtube as cy
import common
import youtube_autoriser as ya

ENV = {"RECO_YT_COMMENTAIRES": "1", "RECO_YT_CLIENT_ID": "id",
       "RECO_YT_CLIENT_SECRET": "secret", "RECO_YT_REFRESH_TOKEN": "jeton"}
EPISODE = {"guid": "yt-abc", "title": "S6-E06", "date": "2026-10-23"}


class Reponse:
    def __init__(self, statut=200, texte="", donnees=None):
        self.status_code, self.text, self._donnees = statut, texte, donnees or {}

    def json(self):
        return self._donnees

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class Session:
    """Le site rend `page` ; Google rend un jeton puis un identifiant."""

    def __init__(self, page="", statut_page=200, statut_jeton=200):
        self.page, self.statut_page, self.statut_jeton = page, statut_page, statut_jeton
        self.postes: list[dict] = []

    def get(self, url, timeout):
        return Reponse(self.statut_page, self.page)

    def post(self, url, timeout, data=None, json=None, headers=None):
        if url == cy.JETON_URL:
            return Reponse(self.statut_jeton, donnees={"access_token": "acces"})
        self.postes.append({"json": json, "headers": headers})
        return Reponse(donnees={"id": "UgzCommentaire"})


@pytest.fixture
def recos(tmp_path: Path, monkeypatch) -> Path:
    dossier = tmp_path / "recos" / "ubm"
    dossier.mkdir(parents=True)
    monkeypatch.setattr(common, "RECOS_DIR", tmp_path / "recos")
    return dossier


def poser(dossier: Path, nom: str, **champs) -> None:
    doc = {"episodeGuid": "yt-abc", "status": "validated", "transcriptSource": "youtube",
           **champs}
    (dossier / f"{nom}.json").write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")


def appels():
    vus: dict[str, list] = {"notify": [], "rapporter": [], "oublier": []}
    return vus, {
        "rapporter": lambda st, cle, msg, notify: vus["rapporter"].append(msg),
        "oublier": lambda st, cle: vus["oublier"].append(cle),
    }


# ===== Le texte ============================================================
def test_minutage_a_la_forme_que_youtube_rend_cliquable():
    assert cy.minutage("00:01:10") == "1:10"
    assert cy.minutage("01:23:58") == "1:23:58"
    assert cy.minutage(None) is None
    assert cy.minutage("bientot") is None


def test_texte_separe_recos_et_evocations():
    message = cy.texte([
        {"title": "Renversée", "creator": "Amandine Lourdel", "timestamp": "00:01:10",
         "transcriptSource": "youtube", "kind": "reco"},
        {"title": "Bo Burnham", "creator": "Bo Burnham", "timestamp": "01:19:51",
         "transcriptSource": "youtube", "kind": "citation"},
    ], "https://site/ep/")
    recos, evocations = message.split("Aussi évoqués")
    # Un createur identique au titre ne se repete pas, et le type donne l'emoji.
    assert "1:10 ✨ Renversée (Amandine Lourdel)" in recos
    assert evocations.startswith(" : Bo Burnham (1:19:51)\n")
    assert "https://site/ep/" in message and "non officiel" in message


def test_l_emoji_suit_le_type():
    message = cy.texte([{"title": "Noor", "types": ["artiste"], "timestamp": "01:09:06",
                         "transcriptSource": "youtube"}], "https://site/")
    assert "1:09:06 🎤 Noor" in message


def test_les_evocations_d_un_meme_moment_tiennent_en_une_ligne():
    message = cy.texte([
        {"title": "Nardwuar", "timestamp": "00:29:34", "transcriptSource": "youtube", "kind": "citation"},
        {"title": "Bigflo & Oli", "timestamp": "00:29:34", "transcriptSource": "youtube", "kind": "citation"},
        {"title": "Linky", "timestamp": "01:00:00", "transcriptSource": "youtube", "kind": "citation"},
    ], "https://site/")
    assert "💬 Aussi évoqués : Nardwuar et Bigflo & Oli (29:34), Linky (1:00:00)\n" in message


def test_un_minutage_acast_n_est_pas_donne_pour_la_video():
    message = cy.texte([{"title": "X", "timestamp": "00:10:00",
                         "transcriptSource": "acast"}], "https://site/")
    assert "✨ X" in message and "10:00" not in message


def test_recos_publiees_dans_l_ordre_sans_les_ecartees(recos: Path):
    poser(recos, "2", title="Deux", timestamp="00:20:00")
    poser(recos, "1", title="Une", timestamp="00:10:00")
    poser(recos, "3", title="Ecartee", status="discarded")
    poser(recos, "4", title="Autre episode", episodeGuid="yt-zzz")
    assert [r["title"] for r in cy.recos_publiees("ubm", "yt-abc")] == ["Une", "Deux"]


# ===== Quand commenter =====================================================
def test_inerte_sans_interrupteur_ni_secrets():
    etat = {"published": ["yt-abc"]}
    assert cy.a_commenter("ubm", etat, [(None, EPISODE)], env={}) == []
    sans_jeton = {**ENV, "RECO_YT_REFRESH_TOKEN": ""}
    assert cy.a_commenter("ubm", etat, [(None, EPISODE)], env=sans_jeton) == []


def test_seuls_les_episodes_publies_recents_et_non_commentes():
    ancien = {**EPISODE, "guid": "yt-old", "date": "2026-10-16"}
    non_publie = {**EPISODE, "guid": "yt-new"}
    deja = {**EPISODE, "guid": "yt-done"}
    etat = {"published": ["yt-abc", "yt-old", "yt-done"], "commented": ["yt-done"]}
    retenus = cy.a_commenter("ubm", etat, [(None, e) for e in (EPISODE, ancien, non_publie, deja)],
                             env=ENV)
    assert [e["guid"] for _, e in retenus] == ["yt-abc"]


# ===== Poster ==============================================================
def test_poste_quand_la_page_est_en_ligne(recos: Path):
    poser(recos, "1", title="Widow's Bay", timestamp="01:15:58", kind="reco")
    session = Session(page="<h3>Widow&#39;s Bay</h3>")
    etat = {"published": ["yt-abc"], "lastErrors": {}}
    vus, aides = appels()

    cy.commenter("ubm", vus["notify"].append, etat, [(None, EPISODE)], session=session,
                 env=ENV, **aides)

    assert etat["commented"] == ["yt-abc"]
    envoi = session.postes[0]
    assert envoi["headers"] == {"Authorization": "Bearer acces"}
    assert envoi["json"]["snippet"]["videoId"] == "abc"
    assert "1:15:58 ✨ Widow's Bay" in envoi["json"]["snippet"]["topLevelComment"]["snippet"]["textOriginal"]
    assert "lc=UgzCommentaire" in vus["notify"][0]


def test_attend_que_la_page_porte_les_recos(recos: Path):
    poser(recos, "1", title="Widow's Bay", timestamp="01:15:58")
    for session in (Session(statut_page=404), Session(page="<h1>autre chose</h1>")):
        etat = {"published": ["yt-abc"], "lastErrors": {}}
        vus, aides = appels()
        cy.commenter("ubm", vus["notify"].append, etat, [(None, EPISODE)], session=session,
                     env=ENV, **aides)
        assert etat["commented"] == [] and session.postes == []


def test_une_panne_se_signale_et_l_episode_reste_a_commenter(recos: Path):
    poser(recos, "1", title="Titre", timestamp="00:01:00")
    etat = {"published": ["yt-abc"], "lastErrors": {}}
    vus, aides = appels()
    cy.commenter("ubm", vus["notify"].append, etat, [(None, EPISODE)],
                 session=Session(page="Titre", statut_jeton=401), env=ENV, **aides)
    assert etat["commented"] == []
    assert "HTTP 401" in vus["rapporter"][0]


def test_un_episode_sans_reco_ne_recoit_pas_de_commentaire_vide(recos: Path):
    etat = {"published": ["yt-abc"], "lastErrors": {}}
    session = Session()
    vus, aides = appels()
    cy.commenter("ubm", vus["notify"].append, etat, [(None, EPISODE)], session=session,
                 env=ENV, **aides)
    assert etat["commented"] == ["yt-abc"] and session.postes == []


def test_l_apercu_affiche_le_texte(recos: Path, capsys):
    poser(recos, "1", title="Titre", timestamp="00:01:00")
    assert cy.main(["--source", "ubm", "--apercu", "yt-abc"]) == 0
    assert "1:00 ✨ Titre" in capsys.readouterr().out


# ===== L'autorisation ======================================================
def test_le_consentement_demande_un_acces_durable_et_pkce():
    verificateur, defi = ya.defi_pkce()
    attendu = base64.urlsafe_b64encode(
        hashlib.sha256(verificateur.encode()).digest()).rstrip(b"=").decode()
    assert defi == attendu
    q = parse_qs(urlsplit(ya.adresse_consentement("id", "http://127.0.0.1:1", "e", defi)).query)
    assert q["access_type"] == ["offline"] and q["prompt"] == ["consent"]
    assert q["scope"] == [ya.PORTEE] and q["code_challenge_method"] == ["S256"]


def test_lire_client_refuse_un_fichier_inattendu(tmp_path: Path):
    bon = tmp_path / "bon.json"
    bon.write_text(json.dumps({"installed": {"client_id": "i", "client_secret": "s"}}))
    assert ya.lire_client(bon) == ("i", "s")
    mauvais = tmp_path / "mauvais.json"
    mauvais.write_text("{}")
    with pytest.raises(SystemExit):
        ya.lire_client(mauvais)


def test_les_lignes_env_portent_les_trois_secrets():
    assert ya.lignes_env("i", "s", "j").splitlines() == [
        "RECO_YT_CLIENT_ID=i", "RECO_YT_CLIENT_SECRET=s", "RECO_YT_REFRESH_TOKEN=j"]
