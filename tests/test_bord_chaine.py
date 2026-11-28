"""Bloc « Chaîne » du tableau de bord (R2 B du 27/11/2026 et TB-1 C du 28/11/2026 ;
relecture du plan R7 : « Détecté » sans heure, « Publié » par `published`, sinon
« inconnu » — jamais « tout va bien » faute de donnée)."""
from __future__ import annotations

import json
import sqlite3

import pytest

import bord_chaine

SOURCE = "un-bon-moment"


@pytest.fixture
def corpus(tmp_path, monkeypatch):
    """Dossiers temporaires pour les épisodes, l'état, la télémétrie et le bord."""
    import common
    episodes = tmp_path / "episodes"
    monkeypatch.setattr(common, "EPISODES_DIR", episodes)
    monkeypatch.setattr(common, "OUTPUT_DIR", tmp_path / "output")
    monkeypatch.delenv("RECO_BORD_DIR", raising=False)
    monkeypatch.delenv("RECO_METRICS_DB", raising=False)
    (episodes / SOURCE).mkdir(parents=True)
    return tmp_path


def _episode(tmp, guid, date, statut="auto", titre=None):
    data = {"guid": guid, "date": date, "transcriptStatus": statut, "title": titre or guid}
    chemin = tmp / "episodes" / SOURCE / f"{guid.lower()}.json"
    chemin.write_text(json.dumps(data), encoding="utf-8")


def _etat(tmp, **champs):
    chemin = tmp / "output" / "pipeline" / f"{SOURCE}.json"
    chemin.parent.mkdir(parents=True, exist_ok=True)
    base = {"extracted": [], "finalized": [], "published": [], "lastErrors": {}}
    chemin.write_text(json.dumps({**base, **champs}), encoding="utf-8")


def _base(tmp, lignes):
    chemin = tmp / "output" / "telemetry" / "reco_metrics.sqlite"
    chemin.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(chemin)
    conn.execute("CREATE TABLE stage_attempts (id TEXT, source_id TEXT, episode_guid TEXT,"
                 " stage TEXT, status TEXT, started_at TEXT, ended_at TEXT)")
    conn.executemany("INSERT INTO stage_attempts VALUES (?,?,?,?,?,?,?)", lignes)
    conn.commit()
    conn.close()


def _par_cle(etat):
    return {e["cle"]: e for e in etat["etapes"]}


def test_l_episode_en_cours_est_le_plus_recent_non_publie(corpus):
    _episode(corpus, "yt-Ancien", "2026-11-01")
    _episode(corpus, "yt-Recent", "2026-11-26")
    _episode(corpus, "yt-Publie", "2026-11-25")
    _episode(corpus, "S6-E01", "2026-11-30")  # Acast : hors de la chaîne
    _etat(corpus, published=["yt-Publie"])
    etat = bord_chaine.etat_chaine(SOURCE)
    assert etat["episode"]["guid"] == "yt-Recent"


def test_un_vieil_episode_hors_de_published_n_est_pas_en_cours(corpus):
    # Tour 1, M2 : seul un épisode plus récent que le dernier publié est « en cours ».
    _episode(corpus, "yt-Vieux", "2026-10-01")
    _episode(corpus, "yt-Publie", "2026-11-25")
    _etat(corpus, published=["yt-Publie"])
    assert bord_chaine.etat_chaine(SOURCE)["episode"]["guid"] == "yt-Publie"


def test_le_dernier_publie_se_choisit_par_date_et_non_par_position(corpus):
    _episode(corpus, "yt-Neuf", "2026-11-25")
    _episode(corpus, "yt-Vieux", "2026-10-01")
    _etat(corpus, published=["yt-Neuf", "yt-Vieux"])  # dans le désordre
    assert bord_chaine.etat_chaine(SOURCE)["episode"]["guid"] == "yt-Neuf"


def test_detecte_sans_heure_et_publie_a_venir(corpus):
    _episode(corpus, "yt-A", "2026-11-20")
    _etat(corpus, extracted=["yt-A"])
    etapes = _par_cle(bord_chaine.etat_chaine(SOURCE))
    assert [e for e in etapes] == ["detecte", "transcrit", "extrait", "finalise", "publie"]
    assert etapes["detecte"] == {"cle": "detecte", "libelle": "Détecté", "etat": "fait",
                                 "heure": None, "source": "fiche de l'épisode"}
    assert etapes["transcrit"]["etat"] == "fait"
    assert etapes["extrait"]["etat"] == "fait"
    assert etapes["finalise"]["etat"] == "a_venir"
    assert etapes["publie"]["etat"] == "a_venir"
    assert etapes["publie"]["heure"] is None
    assert etapes["publie"]["source"] == "état de la chaîne"


def test_les_heures_viennent_de_la_telemetrie(corpus):
    _episode(corpus, "yt-A", "2026-11-20")
    _etat(corpus, extracted=["yt-A"])
    _base(corpus, [
        ("1", SOURCE, "yt-A", "transcribe", "failed", "t0", "2026-11-20T09:00:00+00:00"),
        ("2", SOURCE, "yt-A", "transcribe", "succeeded", "t1", "2026-11-20T10:00:00+00:00"),
        ("3", SOURCE, "yt-A", "transcribe", "succeeded", "t2", "2026-11-20T11:00:00+00:00"),
        ("4", SOURCE, "yt-A", "extract", "succeeded", "t3", "2026-11-20T12:00:00+00:00"),
        ("5", SOURCE, "yt-B", "finalize", "succeeded", "t4", "2026-11-20T13:00:00+00:00"),
        ("6", "autre", "yt-A", "finalize", "succeeded", "t4", "2026-11-20T13:00:00+00:00"),
    ])
    etapes = _par_cle(bord_chaine.etat_chaine(SOURCE))
    assert etapes["transcrit"]["heure"] == "2026-11-20T11:00:00+00:00"
    assert etapes["extrait"]["heure"] == "2026-11-20T12:00:00+00:00"
    assert etapes["finalise"]["heure"] is None
    assert etapes["detecte"]["heure"] is None


def test_une_base_illisible_donne_des_heures_absentes(corpus):
    _episode(corpus, "yt-A", "2026-11-20")
    _etat(corpus)
    chemin = corpus / "output" / "telemetry" / "reco_metrics.sqlite"
    chemin.parent.mkdir(parents=True)
    chemin.write_bytes(b"pas une base sqlite" * 100)
    etapes = _par_cle(bord_chaine.etat_chaine(SOURCE))
    assert etapes["transcrit"]["heure"] is None


def test_sans_etat_de_la_chaine_les_etapes_sont_inconnues(corpus):
    _episode(corpus, "yt-A", "2026-11-20", statut="none")
    etapes = _par_cle(bord_chaine.etat_chaine(SOURCE))
    assert etapes["detecte"]["etat"] == "fait"
    assert etapes["transcrit"]["etat"] == "a_venir"
    for cle in ("extrait", "finalise", "publie"):
        assert etapes[cle]["etat"] == "inconnu"
        assert etapes[cle]["source"] == "inconnu"


def test_sans_etat_une_etape_mesuree_est_faite_selon_la_telemetrie(corpus):
    _episode(corpus, "yt-A", "2026-11-20")
    _base(corpus, [("1", SOURCE, "yt-A", "extract", "succeeded", "t", "2026-11-20T12:00:00")])
    etapes = _par_cle(bord_chaine.etat_chaine(SOURCE))
    assert etapes["extrait"]["etat"] == "fait"
    assert etapes["extrait"]["source"] == "télémétrie"


def test_un_etat_illisible_compte_comme_absent(corpus):
    _episode(corpus, "yt-A", "2026-11-20")
    chemin = corpus / "output" / "pipeline" / f"{SOURCE}.json"
    chemin.parent.mkdir(parents=True)
    chemin.write_text("{pas du json", encoding="utf-8")
    etat = bord_chaine.etat_chaine(SOURCE)
    assert _par_cle(etat)["publie"]["etat"] == "inconnu"
    assert etat["erreurs"] == []


def test_tout_publie_montre_le_dernier_publie_meme_sans_sa_fiche(corpus):
    # La publication retire les fichiers de l'épisode du clone jusqu'à la fusion.
    _episode(corpus, "yt-Vieux", "2026-10-01")
    _etat(corpus, extracted=["yt-Vieux", "yt-Neuf"], finalized=["yt-Vieux", "yt-Neuf"],
          published=["yt-Vieux", "yt-Neuf"])
    etat = bord_chaine.etat_chaine(SOURCE)
    assert etat["episode"] == {"guid": "yt-Neuf", "titre": None, "date": None}
    etapes = _par_cle(etat)
    assert all(e["etat"] == "fait" for e in etapes.values())
    assert etapes["detecte"]["source"] == "état de la chaîne"
    assert etapes["publie"]["source"] == "état de la chaîne"


MERGE = "2026-11-27T10:00:00Z"


def test_une_pr_fusionnee_suffit_a_dire_publie_meme_si_le_clone_n_est_pas_a_jour(corpus):
    """Tour 1, M2 : `published` ne dit pas la fusion ; `merged_at` de la PR la dit, avec son heure."""
    _episode(corpus, "yt-DNoUz4FJ_Z8", "2026-11-20")
    _etat(corpus, extracted=["yt-DNoUz4FJ_Z8"])
    sans = bord_chaine.etat_chaine(SOURCE)
    assert _par_cle(sans)["publie"]["etat"] == "a_venir"
    avec = bord_chaine.etat_chaine(SOURCE, fusionnees={"contenu/yt-dnouz4fj-z8": MERGE})
    assert avec["episode"]["guid"] == "yt-DNoUz4FJ_Z8"
    assert _par_cle(avec)["publie"] == {"cle": "publie", "libelle": "Publié", "etat": "fait",
                                        "heure": MERGE, "source": "PR fusionnée"}


def test_une_pr_fusionnee_sort_l_episode_de_ceux_en_cours(corpus):
    _episode(corpus, "yt-Vieux", "2026-11-01")
    _episode(corpus, "yt-Fusionne", "2026-11-20")
    _etat(corpus)
    etat = bord_chaine.etat_chaine(SOURCE, fusionnees={"contenu/yt-fusionne": MERGE})
    assert etat["episode"]["guid"] == "yt-Fusionne"
    assert _par_cle(etat)["publie"]["etat"] == "fait"


def test_une_pr_fusionnee_dit_publie_meme_sans_etat_de_la_chaine(corpus):
    _episode(corpus, "yt-A", "2026-11-20")
    etat = bord_chaine.etat_chaine(SOURCE, fusionnees={"contenu/yt-a": MERGE})
    assert _par_cle(etat)["publie"]["source"] == "PR fusionnée"
    assert _par_cle(etat)["extrait"]["etat"] == "inconnu"


def test_un_episode_deja_publie_garde_la_source_de_l_etat_de_la_chaine(corpus):
    _episode(corpus, "yt-A", "2026-11-20")
    _etat(corpus, published=["yt-A"])
    etat = bord_chaine.etat_chaine(SOURCE, fusionnees={"contenu/yt-a": MERGE})
    assert _par_cle(etat)["publie"]["source"] == "état de la chaîne"


def test_sans_aucun_episode(corpus):
    etat = bord_chaine.etat_chaine(SOURCE)
    assert etat["episode"] is None and etat["etapes"] == []


def test_les_erreurs_de_la_chaine_sont_rendues(corpus):
    _episode(corpus, "yt-A", "2026-11-20")
    _etat(corpus, lastErrors={"a": "⚠️ un", "b": "⚠️ deux", "c": "trois",
                              "transcription:yt-A": "⚠️ la transcription a échoué"})
    # Tour 1, M1 : l'état est écrit trié par clé, un plafond cacherait la dernière.
    assert bord_chaine.etat_chaine(SOURCE)["erreurs"] == [
        "⚠️ un", "⚠️ deux", "trois", "⚠️ la transcription a échoué"]


def test_une_fiche_illisible_est_comptee_et_pas_seulement_sautee(corpus):
    """Revue globale, D9 (F22) : sans ce compte, un épisode plus ancien passe pour « l'épisode de la semaine »."""
    _episode(corpus, "yt-Vieux", "2026-11-01")
    (corpus / "episodes" / SOURCE / "yt-abime.json").write_text("{", encoding="utf-8")
    (corpus / "episodes" / SOURCE / "yt-autre.json").write_bytes(bytes([0xFF, 0xFE]))
    etat = bord_chaine.etat_chaine(SOURCE)
    assert etat["fiches_illisibles"] == 2 and etat["episode"]["guid"] == "yt-Vieux"
    assert bord_chaine.etat_chaine(SOURCE, db_path=corpus / "x")["fiches_illisibles"] == 2


def test_sans_fiche_abimee_le_compte_est_zero(corpus):
    _episode(corpus, "yt-A", "2026-11-20")
    assert bord_chaine.etat_chaine(SOURCE)["fiches_illisibles"] == 0


def test_etat_lu_se_dit_sans_dependre_d_un_episode(corpus):
    # Tour 1, F3 : sans épisode, un état lu reste lu.
    assert bord_chaine.etat_chaine(SOURCE)["etat_lu"] is False
    _etat(corpus)
    etat = bord_chaine.etat_chaine(SOURCE)
    assert etat["episode"] is None and etat["etat_lu"] is True


def _passages(dossier, lignes):
    dossier.mkdir(parents=True, exist_ok=True)
    (dossier / "passages.jsonl").write_text("".join(x + "\n" for x in lignes), encoding="utf-8")


def _p(i):
    return json.dumps({"debut": f"d{i}", "fin": f"f{i}", "lancees": [], "echecs": []})


def test_les_derniers_passages_du_plus_recent_au_plus_ancien(corpus):
    _passages(corpus / "output" / "bord", [_p(i) for i in range(8)])
    passages = bord_chaine.etat_chaine(SOURCE)["passages"]
    assert [p["debut"] for p in passages] == ["d7", "d6", "d5", "d4", "d3"]


def test_une_ligne_abimee_est_ignoree(corpus):
    _passages(corpus / "output" / "bord", [_p(1), "{coupée", "[1, 2]", _p(2)])
    passages = bord_chaine.lire_passages(corpus / "output" / "bord" / "passages.jsonl", 5)
    assert [p["debut"] for p in passages] == ["d2", "d1"]


def test_sans_journal_les_passages_sont_inconnus(corpus):
    assert bord_chaine.etat_chaine(SOURCE)["passages"] is None


def test_le_dossier_du_bord_se_regle_par_l_environnement(corpus, monkeypatch):
    ailleurs = corpus / "ailleurs"
    _passages(ailleurs, [_p(1)])
    monkeypatch.setenv("RECO_BORD_DIR", str(ailleurs))
    assert [p["debut"] for p in bord_chaine.etat_chaine(SOURCE)["passages"]] == ["d1"]


def test_une_fiche_ou_un_etat_mal_formes_sont_ecartes(corpus):
    _episode(corpus, "yt-A", "2026-11-20")
    (corpus / "episodes" / SOURCE / "yt-casse.json").write_text("{coupé", encoding="utf-8")
    (corpus / "episodes" / SOURCE / "yt-autre.json").write_text('{"guid": "S6-E01"}',
                                                                 encoding="utf-8")
    chemin = corpus / "output" / "pipeline" / f"{SOURCE}.json"
    chemin.parent.mkdir(parents=True)
    chemin.write_text('["pas", "un", "objet"]', encoding="utf-8")
    etat = bord_chaine.etat_chaine(SOURCE)
    assert etat["episode"]["guid"] == "yt-A"
    assert _par_cle(etat)["extrait"]["etat"] == "inconnu"


def test_des_erreurs_mal_formees_ne_cassent_rien(corpus):
    _episode(corpus, "yt-A", "2026-11-20")
    _etat(corpus, lastErrors=["pas", "un", "objet"])
    assert bord_chaine.etat_chaine(SOURCE)["erreurs"] == []


def test_un_journal_illisible_donne_des_passages_inconnus(corpus):
    dossier = corpus / "output" / "bord"
    dossier.mkdir(parents=True)
    (dossier / "passages.jsonl").write_bytes(b"\xff\xfe\xfa")
    assert bord_chaine.etat_chaine(SOURCE)["passages"] is None


def test_le_passage_en_cours_se_lit_dans_le_fichier_en_cours(corpus):
    dossier = corpus / "output" / "bord"
    dossier.mkdir(parents=True)
    (dossier / "en-cours").write_text("2026-11-29T10:11:00+01:00\n", encoding="utf-8")
    assert bord_chaine.etat_chaine(SOURCE)["en_cours"] == "2026-11-29T10:11:00+01:00"


def test_sans_fichier_en_cours_aucun_passage_n_est_en_cours(corpus):
    assert bord_chaine.etat_chaine(SOURCE)["en_cours"] is None


def test_un_fichier_en_cours_illisible_donne_aucun_passage_en_cours(corpus):
    dossier = corpus / "output" / "bord"
    dossier.mkdir(parents=True)
    (dossier / "en-cours").write_bytes(b"\xff\xfe\xfa")
    assert bord_chaine.etat_chaine(SOURCE)["en_cours"] is None


def test_la_base_se_choisit_a_l_appel(corpus):
    _episode(corpus, "yt-A", "2026-11-20")
    _etat(corpus)
    _base(corpus, [("1", SOURCE, "yt-A", "transcribe", "succeeded", "t", "2026-11-20T10:00:00")])
    ailleurs = corpus / "vide.sqlite"
    etapes = _par_cle(bord_chaine.etat_chaine(SOURCE, db_path=ailleurs))
    assert etapes["transcrit"]["heure"] is None
