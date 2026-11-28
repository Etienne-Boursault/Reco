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

import bord_chaine
import bord_contenu
import bord_distant
import bord_github
import bord_reseaux
import bord_systeme
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
    # Aucun rafraîchissement détaché pendant les tests (GitHub serait appelé pour de bon).
    monkeypatch.setattr(bord_distant, "_lancer", lambda *a, **k: False)
    for env in ("RECO_REVIEW_URL", "RECO_REVIEW_HOTES", "RECO_AUDIENCE_KEY"):
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


def test_get_bord_lit_l_audience_et_compte_les_signalements(corpus, monkeypatch):
    """L'audience vient du cache de `bord_distant` (frais : rien n'est relancé)."""
    from datetime import UTC, datetime

    monkeypatch.setenv("RECO_AUDIENCE_KEY", "fausse-cle-audience-123")
    quand = datetime.now(UTC).isoformat(timespec="seconds")
    donnees = {"genere": quand, "perimetre": "tout le site", "sept": None, "trente": None,
               "jours": [], "erreur": None,
               "signalements": {"etat": "lu", "enAttente": [
                   {"id": "rep-1", "recoId": "ubm-1", "categorie": "error",
                    "date": "2026-11-27T10:00:00.000Z"}]}}
    (corpus / "bord").mkdir(parents=True, exist_ok=True)
    (corpus / "bord" / "distant.json").write_text(json.dumps({"audience": {
        "etat": "ok", "detail": None, "essai": quand, "lu": quand, "donnees": donnees}}),
        encoding="utf-8")
    code, _, corps = _requete("GET", "/bord")
    page = corps.decode("utf-8")
    assert code == 200
    assert 'data-etat="ok"' in page and "ubm-1" in page
    assert "1 signalement en attente" in page
    assert "fausse-cle-audience-123" not in page


@pytest.mark.parametrize("signalements", [
    {"etat": "lu", "enAttente": "pas une liste"},
    {"etat": "lu", "enAttente": {"id": "x"}},
    {"etat": "lu", "enAttente": ["texte", 3, None]},
    ["pas", "un", "objet"],
    "texte",
])
def test_get_bord_une_forme_inattendue_de_signalements_reste_inconnue(corpus, monkeypatch,
                                                                       signalements):
    """Tour 1, M3 : un site qui répond de travers ne fait pas tomber `/bord` en 500."""
    from datetime import UTC, datetime

    monkeypatch.setenv("RECO_AUDIENCE_KEY", "fausse-cle-audience-123")
    quand = datetime.now(UTC).isoformat(timespec="seconds")
    donnees = {"genere": quand, "perimetre": "tout le site", "sept": None, "trente": None,
               "jours": [], "erreur": None, "signalements": signalements}
    (corpus / "bord").mkdir(parents=True, exist_ok=True)
    (corpus / "bord" / "distant.json").write_text(json.dumps({"audience": {
        "etat": "ok", "detail": None, "essai": quand, "lu": quand, "donnees": donnees}}),
        encoding="utf-8")
    code, _, corps = _requete("GET", "/bord")
    page = corps.decode("utf-8")
    assert code == 200
    assert "Signalements : inconnu" in page and "signalements : inconnu" in page


def test_get_bord_lit_github_et_le_systeme_une_seule_fois_chacun(monkeypatch):
    appels = []
    github = {"etat": "ok", "donnees": {"ci": {"conclusion": "failure", "date": None,
                                                "adresse": "https://github.com/a/b/actions/runs/1"},
                                        "deploiement": None}, "age": 5}
    systeme = {"couts": None, "modeles": None, "image": "reco-atelier:essai-1"}
    monkeypatch.setattr(bord_github, "lire", lambda **kw: appels.append("github") or github)
    monkeypatch.setattr(bord_systeme, "lire",
                        lambda source_id, **kw: appels.append(("systeme", source_id)) or systeme)
    page = _requete("GET", "/bord")[2].decode("utf-8")
    assert sorted(map(str, appels)) == sorted(["github", str(("systeme", SOURCE))])
    assert 'data-conclusion="echec"' in page and "reco-atelier:essai-1" in page


def test_get_bord_lit_le_contenu_une_seule_fois_et_remplit_les_lignes_d_a_faire(monkeypatch):
    appels = []
    contenu = {"sorties": {"liste": [{"id": "r", "titre": "Un film à venir", "date": "2026-12-01",
                                      "jours": 3, "relancee": False}], "total": 1,
                           "illisibles": 0},
               "graphies": {"total": 1, "ecartees": 0,
                            "plus_vues": [{"fausse": "Kaffka", "juste": "Kafka", "vu": 2}]},
               "liens": {"date": "2026-11-25", "age": 3, "ancien": False, "morts": 2,
                         "nouveaux": 0, "inconnus": 0, "vivants": 5,
                         "liste": [{"url": "https://exemple.test/mort", "reponse": "404",
                                    "recos": ["r"]}]}}
    pr = {"numero": 7, "titre": "Sorties", "branche": "contenu/sorties-x", "groupe": "sorties",
          "date": "2026-11-28T08:00:00Z", "adresse": "https://github.com/a/b/pull/7"}
    github = {"etat": "ok", "donnees": {"ouvertes": {"episodes": [], "sorties": [pr],
                                                     "coupee": False},
                                        "ci": None, "deploiement": None}, "age": 5}
    monkeypatch.setattr(bord_contenu, "lire",
                        lambda source_id, **kw: appels.append(source_id) or contenu)
    monkeypatch.setattr(bord_github, "lire", lambda **kw: github)
    page = _requete("GET", "/bord")[2].decode("utf-8")
    assert appels == [SOURCE]
    assert "Un film à venir" in page and "Kaffka" in page
    assert 'href="https://exemple.test/mort"' in page
    assert "2 liens morts" in page and "fusionner la PR des sorties : Sorties (#7)" in page
    assert 'href="https://github.com/a/b/pull/7"' in page
    assert "data-attente" not in page


def test_get_bord_passe_les_prs_fusionnees_a_la_chaine_et_a_la_publication(monkeypatch):
    """Tour 1, M2 : une seule lecture de GitHub, partagée par la chaîne et « À faire d'abord »."""
    vus = []
    original = bord_chaine.etat_chaine
    monkeypatch.setattr(bord_chaine, "etat_chaine",
                        lambda source_id, **kw: vus.append(kw) or original(source_id, **kw))
    pr = {"numero": 3, "titre": "T", "branche": "contenu/ep-001", "groupe": "episodes",
          "date": "2026-11-27T10:00:00Z", "adresse": "https://github.com/a/b/pull/3"}
    github = {"etat": "ok", "donnees": {"depot": "a/b", "ouvertes": {"episodes": [], "sorties": [],
                                                                      "coupee": False},
                                        "fusionnees": [pr], "ci": None, "deploiement": None},
              "age": 5}
    monkeypatch.setattr(bord_github, "lire", lambda **kw: github)
    # Clone en retard : ni l'un ni l'autre n'y est revenu.
    monkeypatch.setattr(bord_reseaux, "episodes_recents", lambda *a: [
        {"guid": "ep-001", "fusionne": False, "episode": {"season": 6, "number": 1}},
        {"guid": "ep-002", "fusionne": False, "episode": {"season": 6, "number": 2}}])
    page = _requete("GET", "/bord")[2].decode("utf-8")
    assert vus == [{"fusionnees": {"contenu/ep-001": "2026-11-27T10:00:00Z"}}]
    # ep-001 : PR fusionnée, rien à faire ; ep-002 : poussé sans PR, à ouvrir (lien de comparaison).
    assert "ouvrir puis fusionner la PR de S6·E2" in page
    assert 'href="https://github.com/a/b/compare/main...contenu/ep-002?expand=1"' in page
    assert "fusionner la PR de S6·E1" not in page


def test_get_bord_verifie_la_publication_sur_dix_episodes_et_les_cases_sur_trois(
        corpus, monkeypatch):
    """Revue globale, E1 : la chaîne ne crée pas de PR ; un épisode non fusionné au-delà des 3
    derniers reste signalé, et les publiés plus anciens que la fenêtre sont comptés."""
    chemin = corpus / "output_dir" / "pipeline" / f"{SOURCE}.json"
    chemin.write_text(json.dumps({"published": ["old-1", "old-2", *[f"x{i}" for i in range(10)]]}),
                      encoding="utf-8")
    entrees = [{"guid": f"x{i}", "fusionne": False, "episode": {"season": 6, "number": i + 1}}
               for i in range(9, -1, -1)]
    appels = []

    def faux(source_id, state, episodes, n=3):
        appels.append(n)
        return entrees[:n]

    monkeypatch.setattr(bord_reseaux, "episodes_recents", faux)
    monkeypatch.setattr(bord_github, "lire", lambda **kw: {
        "etat": "ok", "age": 5, "donnees": {
            "depot": "a/b", "fusionnees": [], "ci": None, "deploiement": None,
            "ouvertes": {"episodes": [], "sorties": [], "coupee": False}}})
    page = _requete("GET", "/bord")[2].decode("utf-8")
    assert appels == [bord_reseaux.N_PUBLICATION]
    assert "ouvrir puis fusionner la PR de S6·E1" in page          # le plus ancien de la fenêtre
    assert "2 épisodes plus anciens non vérifiés" in page           # old-1 et old-2
    assert "réseaux de S6·E10 :" in page and "réseaux de S6·E7 :" not in page


def test_get_bord_sans_contenu_lisible_dit_inconnu(monkeypatch):
    monkeypatch.setattr(bord_contenu, "lire",
                        lambda source_id, **kw: {"sorties": None, "graphies": None, "liens": None})
    page = _requete("GET", "/bord")[2].decode("utf-8")
    assert "liens morts : inconnu" in page and "sorties : inconnu" in page
    assert "Liens morts : inconnu" in page and "Sorties à venir : inconnu" in page


def test_get_bord_sans_cache_github_dit_inconnu():
    page = _requete("GET", "/bord")[2].decode("utf-8")
    assert "GitHub : pas encore lu" in page


def test_get_bord_sans_cle_d_audience_le_dit(corpus):
    page = _requete("GET", "/bord")[2].decode("utf-8")
    assert 'data-etat="cle-absente"' in page and "signalements : inconnu" in page


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
