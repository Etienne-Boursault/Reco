"""Tests de `tools/sorties_annoncees.py` : la relance quotidienne des sorties annoncées.

R4 B, 27/11/2026 (PR « sorties annoncées », tranche D2). Le git est RÉEL (un dépôt
temporaire et son `origin` nu) ; les passes de liens, la publication, Matrix et l'horloge
sont remplacés. Aucun test ne touche au dépôt Reco ni au réseau.
"""
from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfoNotFoundError

import pytest

import branche_de_contenu as bdc
import common
import date_sortie
import sorties_annoncees as sa
import sorties_plan as sp
from publication import ErreurGit

ENV = {"RECO_SORTIES_ANNONCEES": "1"}
CLE = "un-bon-moment/ubm-1"
CHEMIN = "src/content/recos/un-bon-moment/ubm-1.json"
URL_A = "https://www.deezer.com/album/1"
URL_B = "https://music.apple.com/fr/album/2"


def _git(racine: Path, *args: str) -> str:
    fini = subprocess.run(["git", *args], cwd=racine, capture_output=True, text=True,
                          encoding="utf-8", check=True)
    return (fini.stdout or "").strip()


def _ecrire_reco(racine: Path, chemin: str, **champs) -> None:
    doc = {"id": Path(chemin).stem, "sourceId": Path(chemin).parent.name, "status": "validated",
           "types": ["album"], "title": "(Re)belle", "releaseDate": "2026-11-20", "links": []}
    doc.update(champs)
    fichier = racine / chemin
    fichier.parent.mkdir(parents=True, exist_ok=True)
    fichier.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


@pytest.fixture
def depot(tmp_path):
    """Un clone sur `main` (ubm-1 avec date, ubm-2 sans, une autre source) et son `origin` nu."""
    origine = tmp_path / "origine.git"
    racine = tmp_path / "clone"
    _git(tmp_path, "init", "--bare", "-b", "main", str(origine))
    racine.mkdir()
    _git(racine, "init", "-b", "main")
    _git(racine, "remote", "add", "origin", str(origine))
    _git(racine, "config", "user.name", "Reco (essai)")
    _git(racine, "config", "user.email", "essai@example.test")
    _ecrire_reco(racine, CHEMIN)
    _ecrire_reco(racine, "src/content/recos/un-bon-moment/ubm-2.json", releaseDate=None, title="Sans date")
    _ecrire_reco(racine, "src/content/recos/autre/x-1.json", title="Autre source")
    _git(racine, "add", ".")
    _git(racine, "commit", "-m", "depart")
    _git(racine, "push", "-u", "origin", "main")
    return racine


@pytest.fixture(autouse=True)
def paris(monkeypatch):
    """Paris = UTC+1 : l'essai ne dépend pas de `tzdata` (absent sous Windows)."""
    faux = lambda _nom: timezone(timedelta(hours=1))
    monkeypatch.setattr(sa, "ZoneInfo", faux)
    monkeypatch.setattr(date_sortie, "ZoneInfo", faux)


class Passe:
    """Une passe de liens factice : ajoute des liens à chaque reco de la copie, ou échoue."""

    def __init__(self, *urls: str, panne: Exception | None = None) -> None:
        self.urls, self.panne, self.appels = urls, panne, 0

    def __call__(self, source: str, ids: set[str]) -> None:
        self.appels += 1
        if self.panne:
            raise self.panne
        for rid in ids:
            chemin = common.RECOS_DIR / source / f"{rid}.json"
            doc = json.loads(chemin.read_text(encoding="utf-8"))
            doc["links"] += [{"kind": "streaming", "label": "Deezer", "url": u, "ethics": "neutral"}
                             for u in self.urls]
            chemin.write_text(json.dumps(doc), encoding="utf-8")


class Publieur:
    """Remplace `publier_branche` : écrit dans un dossier d'essai et rend un résultat fixe."""

    def __init__(self, tmp_path: Path, resultat="ok", erreur: Exception | None = None) -> None:
        self.dossier, self.erreur, self.appels = tmp_path / "arbre", erreur, []
        self.resultat = (bdc.BrancheDeContenu("contenu/sorties-2026-11-27", "abc", "https://github.com/o/r/pull/1",
                                              True) if resultat == "ok" else resultat)

    def __call__(self, racine, base, ecrire, message, *, titre, corps, jeton="", poster=None):
        self.appels.append({"base": base, "message": message, "titre": titre, "corps": corps,
                            "jeton": jeton})
        if self.erreur:
            raise self.erreur
        self.dossier.mkdir(exist_ok=True)
        ecrire(self.dossier)
        return self.resultat


class Banc:
    """Le passage du jour, avec horloge, notifications et état d'essai."""

    def __init__(self, racine: Path, tmp_path: Path) -> None:
        self.racine, self.chemin_etat, self.tmp = racine, tmp_path / "etat" / "sorties.json", tmp_path
        self.messages: list[str] = []
        self.sorties: list[str] = []
        self.maintenant = datetime(2026, 11, 27, 8, 0, tzinfo=UTC)
        self.publieur = Publieur(tmp_path)

    def lancer(self, passes=None, **kw) -> int:
        reglages = {"env": ENV, "publier": self.publieur, "maintenant": lambda: self.maintenant,
                    "passes": [("musique", Passe(URL_A))] if passes is None else passes,
                    "notify": self.messages.append, "afficher": self.sorties.append}
        reglages.update(kw)
        return sa.relancer(self.racine, chemin_etat=self.chemin_etat, **reglages)

    def etat(self) -> dict:
        return json.loads(self.chemin_etat.read_text(encoding="utf-8"))


@pytest.fixture
def banc(depot, tmp_path):
    return Banc(depot, tmp_path)


# --- l'étape est éteinte, ou ce n'est pas l'heure ---------------------------------------

def test_sans_la_variable_l_etape_ne_fait_rien(banc):
    passe = Passe(URL_A)
    assert banc.lancer([("musique", passe)], env={}) == 0
    assert passe.appels == 0 and not banc.chemin_etat.exists() and not banc.messages


def test_avant_six_heures_a_paris_rien_ne_part(banc):
    passe = Passe(URL_A)
    banc.maintenant = datetime(2026, 11, 27, 4, 59, tzinfo=UTC)  # 5 h 59 à Paris
    assert banc.lancer([("musique", passe)]) == 0
    assert passe.appels == 0 and not banc.chemin_etat.exists()
    banc.maintenant = datetime(2026, 11, 27, 5, 0, tzinfo=UTC)  # 6 h à Paris
    banc.lancer([("musique", passe)])
    assert passe.appels == 1


def test_sans_tzdata_le_repli_utc_ouvre_a_cinq_heures(banc, monkeypatch):
    def absent(_nom):
        raise ZoneInfoNotFoundError
    monkeypatch.setattr(sa, "ZoneInfo", absent)
    monkeypatch.setattr(date_sortie, "ZoneInfo", absent)
    passe = Passe(URL_A)
    banc.maintenant = datetime(2026, 11, 27, 4, 59, tzinfo=UTC)
    banc.lancer([("musique", passe)])
    assert passe.appels == 0
    banc.maintenant = datetime(2026, 11, 27, 5, 0, tzinfo=UTC)
    banc.lancer([("musique", passe)])
    assert passe.appels == 1


def test_une_seule_fois_par_jour_puis_le_lendemain(banc):
    passe = Passe(URL_A)
    banc.lancer([("musique", passe)])
    banc.lancer([("musique", passe)])
    assert passe.appels == 1
    banc.maintenant += timedelta(days=1)
    banc.lancer([("musique", passe)])
    assert passe.appels == 2


# --- la trouvaille, la PR et le message --------------------------------------------------

def test_un_lien_trouve_donne_une_pr_une_proposition_et_un_message(banc):
    assert banc.lancer() == 0
    [appel] = banc.publieur.appels
    assert appel["base"] == "contenu/sorties-2026-11-27" and appel["jeton"] == ""
    assert "(Re)belle" in appel["titre"] and URL_A in appel["corps"]
    ecrit = json.loads((banc.publieur.dossier / CHEMIN).read_text(encoding="utf-8"))
    assert [lien["url"] for lien in ecrit["links"]] == [URL_A]
    assert not (banc.publieur.dossier / "src/content/recos/un-bon-moment/ubm-2.json").exists()
    [message] = banc.messages
    assert "🗓️" in message and "(Deezer)" in message and "pull/1" in message
    etat = banc.etat()
    assert etat["propositions"][CLE] == {"branche": "contenu/sorties-2026-11-27", "sha": "abc",
                                         "adresses": [URL_A], "derniere": [URL_A], "externalIds": {}}
    assert etat["relancees"] == [CLE] and etat["dernier_jour"] == "2026-11-27"


def test_le_jeton_et_les_avertissements_passent(banc):
    banc.publieur.resultat.avertissements.append("PR non ouverte (URLError)")
    banc.lancer(env={**ENV, "RECO_GITHUB_TOKEN": "jeton-d-essai"})
    assert banc.publieur.appels[0]["jeton"] == "jeton-d-essai"
    assert banc.messages[0].endswith("PR non ouverte (URLError)")


def test_rien_a_commiter_ne_laisse_aucune_proposition(banc):
    banc.publieur.resultat = None
    assert banc.lancer() == 0
    assert not banc.messages and banc.etat()["propositions"] == {}


def test_un_jour_sans_trouvaille_n_envoie_rien(banc):
    assert banc.lancer([("musique", Passe())]) == 0
    assert not banc.publieur.appels and not banc.messages
    assert banc.etat()["relancees"] == [CLE]


def test_les_autres_sources_et_les_recos_sans_date_sont_ignorees(banc):
    passe = Passe(URL_A)
    banc.lancer([("musique", passe)])
    assert [r for r in json.loads((banc.publieur.dossier / CHEMIN).read_text(encoding="utf-8"))["links"]]
    assert banc.etat()["relancees"] == [CLE]  # ni ubm-2 (sans date) ni autre/x-1


# --- ce qui ne revient jamais ------------------------------------------------------------

def test_un_lien_rejete_n_est_jamais_repose(banc, depot):
    _ecrire_reco(depot, CHEMIN, linksRejected=[URL_A])
    _git(depot, "commit", "-am", "rejet")
    _git(depot, "push", "origin", "main")
    assert banc.lancer([("musique", Passe(URL_A))]) == 0
    assert not banc.publieur.appels and not banc.messages


def test_une_adresse_deja_proposee_n_est_pas_reproposee(banc):
    etat = sp.noter_proposition(sp.etat_vide(), CLE, "contenu/sorties-2026-11-26", "abc", [URL_A])
    sp.ecrire_etat(banc.chemin_etat, etat)  # PR refermée sans fusion : la branche a disparu
    banc.lancer([("musique", Passe(URL_A, URL_B))])
    ecrit = json.loads((banc.publieur.dossier / CHEMIN).read_text(encoding="utf-8"))
    assert [lien["url"] for lien in ecrit["links"]] == [URL_B]
    assert banc.etat()["propositions"][CLE]["adresses"] == [URL_A, URL_B]
    banc.maintenant += timedelta(days=1)
    banc.publieur.appels.clear()
    banc.lancer([("musique", Passe(URL_A, URL_B))])
    assert not banc.publieur.appels


def test_une_proposition_en_attente_saute_la_reco(banc, depot):
    _git(depot, "checkout", "-q", "-b", "contenu/sorties-2026-11-26")
    _ecrire_reco(depot, CHEMIN, links=[{"url": URL_A, "label": "Deezer", "kind": "streaming"}])
    _git(depot, "commit", "-am", "liens")
    sha = _git(depot, "rev-parse", "HEAD")
    _git(depot, "push", "origin", "contenu/sorties-2026-11-26")
    _git(depot, "checkout", "-q", "main")
    sp.ecrire_etat(banc.chemin_etat,
                   sp.noter_proposition(sp.etat_vide(), CLE, "contenu/sorties-2026-11-26", sha, [URL_A]))
    passe = Passe(URL_B)
    banc.lancer([("musique", passe)])
    assert passe.appels == 0
    # la PR est fusionnée : le commit devient ancêtre de origin/main, la reco repart
    _git(depot, "merge", "-q", "--ff-only", "contenu/sorties-2026-11-26")
    _git(depot, "push", "origin", "main")
    banc.maintenant += timedelta(days=1)
    banc.lancer([("musique", passe)])
    assert passe.appels == 1


# --- le clone vivant ---------------------------------------------------------------------

def test_une_reco_modifiee_dans_le_clone_est_sautee_et_signalee_une_fois(banc, depot):
    _ecrire_reco(depot, CHEMIN, title="Titre en cours de relecture")
    passe = Passe(URL_A)
    banc.lancer([("musique", passe)])
    assert passe.appels == 0 and len(banc.messages) == 1 and "modifiée" in banc.messages[0]
    banc.maintenant += timedelta(days=1)
    banc.lancer([("musique", passe)])
    assert len(banc.messages) == 1


def test_la_vraie_publication_ne_touche_ni_au_clone_ni_a_l_index(banc, depot):
    _ecrire_reco(depot, "src/content/recos/un-bon-moment/ubm-2.json", title="Édition en cours")
    avant = (_git(depot, "rev-parse", "HEAD"), _git(depot, "status", "--porcelain"),
             (depot / "src/content/recos/un-bon-moment/ubm-2.json").read_text(encoding="utf-8"))
    banc.lancer(publier=bdc.publier_branche)
    assert (_git(depot, "rev-parse", "HEAD"), _git(depot, "status", "--porcelain"),
            (depot / "src/content/recos/un-bon-moment/ubm-2.json").read_text(encoding="utf-8")) == avant
    branche = banc.etat()["propositions"][CLE]["branche"]
    assert branche == "contenu/sorties-2026-11-27"
    sur_origin = _git(depot, "ls-remote", "origin", f"refs/heads/{branche}")
    assert sur_origin.split()[0] == banc.etat()["propositions"][CLE]["sha"]
    assert (depot / CHEMIN).read_text(encoding="utf-8").count(URL_A) == 0  # le clone n'a rien reçu


# --- les pannes --------------------------------------------------------------------------

def test_une_passe_en_panne_n_arrete_pas_les_autres_et_se_signale_une_fois(banc):
    en_panne = Passe(panne=RuntimeError("API muette"))
    bonne = Passe(URL_A)
    assert banc.lancer([("musique", en_panne), ("boutique", bonne)]) == 0
    assert bonne.appels == 1 and en_panne.appels == 1
    assert len([m for m in banc.messages if m.startswith("⚠️")]) == 1
    assert "passe musique" in banc.messages[0] and "API muette" in banc.messages[0]
    banc.maintenant += timedelta(days=1)
    banc.lancer([("musique", en_panne), ("boutique", bonne)])
    assert len([m for m in banc.messages if m.startswith("⚠️")]) == 1
    banc.maintenant += timedelta(days=1)
    banc.lancer([("musique", Passe()), ("boutique", bonne)])
    assert "passe musique" not in banc.etat()["erreurs"]


def test_une_publication_ratee_se_signale_rend_1_et_ne_note_aucune_proposition(banc):
    banc.publieur.erreur = ErreurGit("push refusé")
    assert banc.lancer() == 1
    assert banc.messages == ["⚠️ Relance des sorties annoncées, publication : ErreurGit: push refusé"]
    etat = banc.etat()
    assert etat["propositions"] == {} and etat["dernier_jour"] == "2026-11-27"
    banc.maintenant += timedelta(days=1)
    banc.publieur.erreur = None
    assert banc.lancer() == 0 and "publication" not in banc.etat()["erreurs"]


def test_un_git_sans_origine_se_signale_une_fois_et_ne_note_pas_le_jour(tmp_path):
    vide = tmp_path / "vide"
    vide.mkdir()
    _git(vide, "init", "-b", "main")
    banc = Banc(vide, tmp_path)
    assert banc.lancer() == 1
    assert len(banc.messages) == 1 and banc.messages[0].startswith("⚠️ Relance des sorties annoncées, git")
    assert banc.etat()["dernier_jour"] is None
    assert banc.lancer() == 1 and len(banc.messages) == 1


def test_un_etat_illisible_arrete_l_etape_sans_rien_reecrire(banc):
    banc.chemin_etat.parent.mkdir(parents=True)
    banc.chemin_etat.write_text("{pas du json", encoding="utf-8")
    passe = Passe(URL_A)
    assert banc.lancer([("musique", passe)]) == 1
    assert passe.appels == 0 and not banc.messages
    assert banc.chemin_etat.read_text(encoding="utf-8") == "{pas du json"


def test_un_message_matrix_qui_echoue_n_empeche_pas_d_ecrire_l_etat(banc):
    def casse(_texte):
        raise OSError("Matrix coupé")
    assert banc.lancer(notify=casse) == 0
    assert CLE in banc.etat()["propositions"]


def test_un_signal_non_envoye_n_est_pas_marque(banc, depot):
    _ecrire_reco(depot, CHEMIN, title="Modifiée")

    def casse(_texte):
        raise OSError("Matrix coupé")
    banc.lancer(notify=casse)
    assert banc.etat()["signaux"] == []


# --- le sablier --------------------------------------------------------------------------

def test_le_sablier_part_une_fois_quand_la_fenetre_se_ferme(banc):
    sp.ecrire_etat(banc.chemin_etat, sp.noter_relance(sp.etat_vide(), [CLE]))
    passe = Passe(URL_A)
    banc.maintenant = datetime(2026, 12, 21, 8, 0, tzinfo=UTC)  # J+31
    banc.lancer([("musique", passe)])
    assert passe.appels == 0 and len(banc.messages) == 1 and banc.messages[0].startswith("⏳")
    banc.maintenant += timedelta(days=1)
    banc.lancer([("musique", passe)])
    assert len(banc.messages) == 1


# --- l'aperçu ----------------------------------------------------------------------------

def test_apercu_cherche_et_affiche_sans_rien_ecrire_ni_envoyer(banc, depot):
    banc.maintenant = datetime(2026, 11, 27, 1, 0, tzinfo=UTC)  # avant 6 h, variable absente
    avant = _git(depot, "rev-parse", "HEAD")
    assert banc.lancer(env={}, apercu=True) == 0
    assert banc.sorties == [f"{CLE} : {URL_A}", "1 reco(s) cherchée(s), 1 avec des liens nouveaux."]
    assert not banc.chemin_etat.exists() and not banc.messages and not banc.publieur.appels
    assert _git(depot, "rev-parse", "HEAD") == avant and "contenu/" not in _git(depot, "branch", "-a")


def test_apercu_ignore_le_jour_deja_traite_et_ne_signale_aucune_panne(banc):
    banc.lancer()
    etat_avant = banc.chemin_etat.read_text(encoding="utf-8")
    banc.messages.clear()
    banc.lancer([("musique", Passe(panne=RuntimeError("muette")))], apercu=True)
    assert not banc.messages and banc.chemin_etat.read_text(encoding="utf-8") == etat_avant


# --- la ligne de commande ----------------------------------------------------------------

def test_relancer_sans_passes_prend_celles_des_types_servis(depot, tmp_path, monkeypatch):
    appelees = []
    toutes = [(nom, (lambda source, ids, nom=nom: appelees.append(nom)))
              for nom in ("musique", "TMDB", "fiches", "Wikidata", "boutique", "plateformes",
                          "jeux", "YouTube Music")]
    monkeypatch.setattr(sa, "_passes_par_defaut", lambda: toutes)
    sa.relancer(depot, notify=lambda _t: None, chemin_etat=tmp_path / "e.json", env=ENV,
                maintenant=lambda: datetime(2026, 11, 27, 8, 0, tzinfo=UTC))
    assert appelees == ["musique", "boutique", "jeux", "YouTube Music"]


def test_main_passe_les_options_a_relancer(monkeypatch, tmp_path):
    recu = {}
    monkeypatch.setattr(sa, "relancer", lambda racine, **kw: recu.update(racine=racine, **kw) or 0)
    monkeypatch.setattr("traiter_nouveaux_episodes.build_notify", lambda canal: f"notifier:{canal}")
    monkeypatch.setattr(common, "OUTPUT_DIR", tmp_path)
    assert sa.main(["--apercu", "--notifier", "matrix", "--source", "autre"]) == 0
    assert recu["apercu"] is True and recu["source"] == "autre" and recu["notify"] == "notifier:matrix"
    assert recu["chemin_etat"] == tmp_path / "pipeline" / "sorties-annoncees.json"
    assert recu["racine"] == common.PROJECT_ROOT
    assert sa.main([]) == 0 and recu["apercu"] is False and recu["notify"] == "notifier:none"


def test_apercu_sans_origine_rend_1_sans_ecrire_ni_envoyer(tmp_path):
    vide = tmp_path / "vide"
    vide.mkdir()
    _git(vide, "init", "-b", "main")
    banc = Banc(vide, tmp_path)
    assert banc.lancer(apercu=True) == 1
    assert not banc.chemin_etat.exists() and not banc.messages

