"""Tests des routes du tableau de bord : `GET /bord`, `POST /bord/reseau`,
`GET /polices/…` (tableau de bord, R2 B du 27/11/2026 ; TB-1 C du 28/11/2026 ;
plan `pr-tableau-de-bord.md`, tranche 1e).

La requête brute passe par le vrai `handle_one_request` du `Handler` de la
relecture (sans socket), comme dans `test_review_hotes.py` : la garde des
hôtes, l'anti-CSRF et le routage sont ceux du serveur. Le corpus, l'état de la
chaîne et le dossier du bord vivent dans un dossier temporaire : aucun test
n'écrit dans `tools/output/`.
"""
from __future__ import annotations

import io
import json
import re
import urllib.parse
from pathlib import Path

import pytest

import bord_reseaux
import review_handler_base
import review_render
import review_routes_bord
from review_routes import Handler

SOURCE = "demo"
_CSS = Path(review_routes_bord.__file__).parent / "review_bord.css"


class _Server:
    server_address = ("127.0.0.1", 8000)


@pytest.fixture(autouse=True)
def corpus(tmp_path, monkeypatch):
    """Une source, deux épisodes publiés et fusionnés, une reco à relire."""
    import common
    from telemetry import recorder

    for nom in ("SOURCES_DIR", "RECOS_DIR", "TRANSCRIPTS_DIR", "OUTPUT_DIR"):
        monkeypatch.setattr(common, nom, tmp_path / nom.lower())
    monkeypatch.setattr(common, "EPISODES_DIR", tmp_path / "episodes")
    monkeypatch.setattr(review_handler_base, "ALLOW_LAN", False)
    monkeypatch.delenv(recorder.ENV_DB, raising=False)
    monkeypatch.setenv("RECO_BORD_DIR", str(tmp_path / "bord"))
    for env in ("RECO_REVIEW_URL", "RECO_REVIEW_HOTES"):
        monkeypatch.delenv(env, raising=False)

    def ecrire(chemin: Path, donnees: dict) -> None:
        chemin.parent.mkdir(parents=True, exist_ok=True)
        chemin.write_text(json.dumps(donnees), encoding="utf-8")

    ecrire(common.SOURCES_DIR / f"{SOURCE}.json", {"title": "Démo Podcast", "hosts": []})
    for guid, num in (("ep-001", 1), ("ep-002", 2)):
        ecrire(common.EPISODES_DIR / SOURCE / f"{guid}.json",
               {"guid": guid, "title": f"Épisode {num}", "season": 6, "number": num})
    ecrire(common.RECOS_DIR / SOURCE / "demo-001.json",
           {"id": "demo-001", "episodeGuid": "ep-002", "types": ["film"],
            "title": "Mortel", "status": "draft"})
    ecrire(common.OUTPUT_DIR / "pipeline" / f"{SOURCE}.json",
           {"published": ["ep-001", "ep-002"]})
    review_render._clear_groups_cache()
    yield tmp_path
    review_render._clear_groups_cache()


def _requete(methode: str, chemin: str, *, corps: dict | None = None,
             entetes: dict[str, str] | None = None) -> tuple[int, dict[str, str], bytes]:
    donnees = urllib.parse.urlencode(corps or {}).encode()
    lignes = [f"{methode} {chemin} HTTP/1.1", "Host: localhost:8000"]
    lignes += [f"{k}: {v}" for k, v in (entetes or {}).items()]
    if methode == "POST":
        lignes += ["Content-Type: application/x-www-form-urlencoded",
                   f"Content-Length: {len(donnees)}"]
    brut = ("\r\n".join(lignes) + "\r\n\r\n").encode("latin-1") + donnees

    h = Handler.__new__(Handler)  # sans socket : pas de __init__
    h.source_id = SOURCE
    h.rfile = io.BytesIO(brut)
    h.wfile = io.BytesIO()
    h.client_address = ("127.0.0.1", 12345)
    h.server = _Server()
    h.handle_one_request()
    tete, _, reste = h.wfile.getvalue().partition(b"\r\n\r\n")
    ligne, *champs = tete.decode("latin-1").split("\r\n")
    en = {k.lower(): v for k, v in (c.split(": ", 1) for c in champs)}
    return int(ligne.split(" ", 2)[1]), en, reste


def _case(guid: str = "ep-002", reseau: str = "deezer", fait: str = "1", *,
          json_: bool = False, origine: str = "http://localhost:8000"):
    entetes = {"Origin": origine}
    if json_:
        entetes["Accept"] = "application/json"
    return _requete("POST", "/bord/reseau", corps={"guid": guid, "reseau": reseau, "fait": fait},
                    entetes=entetes)


def _cases(corpus: Path) -> dict | None:
    chemin = corpus / "bord" / "reseaux.json"
    return json.loads(chemin.read_text(encoding="utf-8")) if chemin.exists() else None


# ---- GET /bord --------------------------------------------------------------
def test_get_bord_rend_la_page():
    code, en, corps = _requete("GET", "/bord")
    page = corps.decode("utf-8")
    assert code == 200
    assert en["content-type"].startswith("text/html")
    assert "Tableau de bord — Démo Podcast" in page
    assert 'action="/bord/reseau"' in page
    assert "Mortel" not in page  # rien du contenu des recos, seulement leur compte
    assert "relire" in page


def test_get_bord_affiche_le_message_de_la_redirection():
    msg = urllib.parse.quote("Deezer : fait.")
    _, _, corps = _requete("GET", f"/bord?flash={msg}&kind=success")
    page = corps.decode("utf-8")
    assert "Deezer : fait." in page and "flash-success" in page


def test_get_bord_un_genre_de_message_inconnu_devient_info():
    _, _, corps = _requete("GET", "/bord?flash=x&kind=%22%3E%3Cscript%3E")
    page = corps.decode("utf-8")
    assert "flash-info" in page and "<script>\"" not in page


def test_get_bord_fichier_des_cases_illisible(corpus):
    (corpus / "bord").mkdir()
    (corpus / "bord" / "reseaux.json").write_text("{abîmé", encoding="utf-8")
    code, _, corps = _requete("GET", "/bord")
    assert code == 200
    assert "Le fichier des cases est illisible" in corps.decode("utf-8")


def test_get_bord_sans_etat_de_chaine(corpus):
    (corpus / "output_dir" / "pipeline" / f"{SOURCE}.json").unlink()
    code, _, _ = _requete("GET", "/bord")
    assert code == 200


@pytest.mark.parametrize("contenu", ["[]", '["published"]', '"texte"', "3"])
def test_get_bord_etat_de_chaine_qui_n_est_pas_un_objet(corpus, contenu):
    # Tour 1, F1 : un JSON valide mais pas un objet ne fait pas tomber la connexion.
    (corpus / "output_dir" / "pipeline" / f"{SOURCE}.json").write_text(contenu, encoding="utf-8")
    code, _, corps = _requete("GET", "/bord")
    assert code == 200
    assert "inconnu" in corps.decode("utf-8")


def test_l_accueil_de_la_relecture_mene_au_tableau_de_bord():
    _, _, corps = _requete("GET", "/")
    assert 'href="/bord"' in corps.decode("utf-8")


# ---- POST /bord/reseau ------------------------------------------------------
def test_post_case_sans_script_redirige_en_303(corpus):
    code, en, _ = _case()
    assert code == 303
    lieu = urllib.parse.urlsplit(en["location"])
    assert lieu.path == "/bord" and lieu.fragment == "bord-reseaux"
    qs = urllib.parse.parse_qs(lieu.query)
    assert qs["kind"] == ["success"] and "Deezer" in qs["flash"][0]
    assert list(_cases(corpus)["ep-002"]) == ["deezer"]


def test_post_case_en_json_puis_decochee(corpus):
    code, en, corps = _case(json_=True)
    assert code == 200 and en["content-type"].startswith("application/json")
    assert json.loads(corps)["kind"] == "success"
    code, _, corps = _case(fait="0", json_=True)
    assert code == 200 and json.loads(corps)["kind"] == "success"
    assert _cases(corpus) == {}


def test_post_case_d_une_autre_origine_refusee(corpus):
    code, _, _ = _case(origine="http://exemple.local:8000")
    assert code == 403
    assert _cases(corpus) is None


@pytest.mark.parametrize("guid,reseau", [("ep-999", "deezer"), ("ep-002", "myspace")])
def test_post_case_guid_ou_reseau_inconnus(corpus, guid, reseau):
    code, _, corps = _case(guid, reseau, json_=True)
    assert code == 400
    assert json.loads(corps)["kind"] == "error"
    code, en, _ = _case(guid, reseau)
    assert code == 303 and "kind=error" in en["location"]
    assert _cases(corpus) is None


def test_post_case_champs_absents(corpus):
    code, _, corps = _requete("POST", "/bord/reseau", corps={},
                              entetes={"Origin": "http://localhost:8000",
                                       "Accept": "application/json"})
    assert code == 400 and json.loads(corps)["kind"] == "error"


def test_post_case_fichier_illisible_jamais_reecrit(corpus):
    (corpus / "bord").mkdir()
    chemin = corpus / "bord" / "reseaux.json"
    chemin.write_text("{abîmé", encoding="utf-8")
    code, _, corps = _case(json_=True)
    assert code == 500
    rep = json.loads(corps)
    assert rep["kind"] == "error" and "illisible" in rep["message"]
    assert chemin.read_text(encoding="utf-8") == "{abîmé"


def test_post_case_ecriture_impossible(corpus, monkeypatch):
    def refuse(*_a, **_k):
        raise PermissionError("lecture seule")
    monkeypatch.setattr(bord_reseaux, "cocher", refuse)
    code, _, corps = _case(json_=True)
    assert code == 500 and json.loads(corps)["kind"] == "error"


# ---- GET /polices/… ---------------------------------------------------------
def test_police_servie_en_woff2():
    code, en, corps = _requete("GET", "/polices/inter-latin-400-normal.woff2")
    assert code == 200
    assert en["content-type"] == "font/woff2"
    assert en["x-content-type-options"] == "nosniff"
    assert int(en["content-length"]) == len(corps)
    assert corps[:4] == b"wOF2"


@pytest.mark.parametrize("chemin", [
    "/polices/../review_routes.py",
    "/polices/%2e%2e/review_routes.py",
    "/polices/..%2Freview_routes.py",
    "/polices/OFL-inter.txt",
    "/polices/inconnue.woff2",
    "/polices/",
])
def test_police_hors_de_la_liste_refusee(chemin):
    code, _, corps = _requete("GET", chemin)
    assert code == 404
    assert b"import" not in corps


def test_police_de_la_liste_absente_du_disque(monkeypatch, tmp_path):
    monkeypatch.setattr(review_routes_bord, "_POLICES_DIR", tmp_path)
    code, _, _ = _requete("GET", "/polices/inter-latin-400-normal.woff2")
    assert code == 404


def test_chaque_police_du_style_est_servie():
    urls = re.findall(r"url\(\"?(/polices/[^\")]+)\"?\)", _CSS.read_text(encoding="utf-8"))
    assert len(urls) == 4
    for url in urls:
        code, en, _ = _requete("GET", url)
        assert (code, en["content-type"]) == (200, "font/woff2"), url


def test_chaque_police_a_sa_licence():
    for nom in ("OFL-bebas-neue.txt", "OFL-inter.txt"):
        texte = (review_routes_bord._POLICES_DIR / nom).read_text(encoding="utf-8")
        assert "SIL Open Font License" in texte
