"""`deploy/venus/tick.sh` note chaque passage dans `passages.jsonl` (tableau de
bord, R2 B du 27/11/2026 et TB-1 C du 28/11/2026 ; relecture du plan R6, R22).

Le vrai script tourne, sur une copie dont seuls le dossier de travail et le
verrou sont déplacés vers un dossier temporaire. `docker`, `git` et `curl` sont
de faux programmes placés en tête du `PATH` : ils notent leurs arguments et
répondent selon `FAUX_OUI` (sondes qui disent oui) et `FAUX_ECHEC` (étapes qui
échouent). Il faut `sh` et `flock` : sous Windows, l'essai se saute (il tourne
sur le PC LLM).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest

TICK = Path(__file__).resolve().parent.parent / "deploy" / "venus" / "tick.sh"
DOSSIER_PROD = "/home/etienne/docker/reco"
VERROU_PROD = "/tmp/reco-tick.lock"

_SANS_SH = shutil.which("sh") is None
_SANS_ESSAI = sys.platform == "win32" or _SANS_SH or shutil.which("flock") is None

_FAUX_DOCKER = """#!/bin/sh
printf '%s\\n' "$*" >>"$FAUX_JOURNAL"
# Ce que voit la page pendant le passage (tour 1, F8 repris).
if [ -f "${RECO_BORD_DIR:-/nulle-part}/en-cours" ]; then
  cp "${RECO_BORD_DIR}/en-cours" "$FAUX_JOURNAL.en-cours"
fi
for dernier in "$@"; do :; done
case " ${FAUX_OUI:-} " in *" $dernier "*) exit 0 ;; esac
case " ${FAUX_ECHEC:-} " in *" $dernier "*) exit 1 ;; esac
case "$dernier" in a-*) exit 1 ;; esac
exit 0
"""
# `date` : seuls le jour (`+%u`) et l'heure (`+%H`) se fixent (FAUX_JOUR, FAUX_HEURE ; par
# défaut un lundi à midi) ; le reste va au vrai `date`, dont le chemin est posé à l'écriture.
_FAUX_DATE = """#!/bin/sh
case "$*" in
  "+%u") printf '%s\\n' "${FAUX_JOUR:-1}" ;;
  "+%H") printf '%s\\n' "${FAUX_HEURE:-12}" ;;
  *) exec @VRAI_DATE@ "$@" ;;
esac
"""
_FAUX_OUTIL = """#!/bin/sh
printf '%s %s\\n' "$(basename "$0")" "$*" >>"$FAUX_JOURNAL"
exit 0
"""


@pytest.mark.skipif(_SANS_SH, reason="sh absent")
def test_tick_sh_se_lit_sans_erreur_de_syntaxe():
    res = subprocess.run(["sh", "-n", str(TICK)], capture_output=True, text=True, check=False)
    assert res.returncode == 0, res.stderr


@pytest.mark.skipif(shutil.which("shellcheck") is None, reason="shellcheck absent")
def test_tick_sh_passe_shellcheck():
    res = subprocess.run(["shellcheck", "-s", "sh", str(TICK)], capture_output=True, text=True, check=False)
    assert res.returncode == 0, res.stdout + res.stderr


def _preparer(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    """Copie de tick.sh qui travaille dans `tmp_path`, et l'environnement des faux."""
    travail = tmp_path / "reco"
    travail.mkdir()
    (travail / ".env").write_text("RECO_KUMA_PUSH_URL=https://kuma.invalid/push\n", encoding="utf-8")
    texte = TICK.read_text(encoding="utf-8")
    assert DOSSIER_PROD in texte and VERROU_PROD in texte, "tick.sh a changé : revoir l'essai"
    texte = texte.replace(DOSSIER_PROD, str(travail)).replace(VERROU_PROD, str(tmp_path / "tick.lock"))
    script = tmp_path / "tick.sh"
    script.write_text(texte, encoding="utf-8")
    faux = tmp_path / "bin"
    faux.mkdir()
    faux_date = _FAUX_DATE.replace("@VRAI_DATE@", shutil.which("date") or "/bin/date")
    for nom, corps in (("docker", _FAUX_DOCKER), ("git", _FAUX_OUTIL), ("curl", _FAUX_OUTIL),
                       ("date", faux_date)):
        (faux / nom).write_text(corps, encoding="utf-8")
        (faux / nom).chmod(0o755)
    env = {k: v for k, v in os.environ.items() if k != "RECO_BORD_DIR"}
    env.update(PATH=f"{faux}{os.pathsep}{env.get('PATH', '')}",
               FAUX_JOURNAL=str(tmp_path / "appels.txt"), FAUX_OUI="", FAUX_ECHEC="")
    return script, env


def _lancer(script: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["sh", str(script)], env=env, capture_output=True, text=True,
                          timeout=60, check=False)


def _lignes(chemin: Path) -> list[dict]:
    return [json.loads(x) for x in chemin.read_text(encoding="utf-8").splitlines()]


@pytest.mark.skipif(_SANS_ESSAI, reason="sh ou flock absent, ou Windows")
def test_un_passage_note_les_etapes_lancees_et_en_echec(tmp_path):
    script, env = _preparer(tmp_path)
    bord = tmp_path / "bord"
    env.update(RECO_BORD_DIR=str(bord), FAUX_OUI="a-extraire a-publier",
               FAUX_ECHEC="transcrire extraire")
    res = _lancer(script, env)
    assert res.returncode == 0, res.stderr
    [ligne] = _lignes(bord / "passages.jsonl")
    assert ligne["lancees"] == ["extraire", "publier"]
    assert ligne["echecs"] == ["transcrire", "extraire"]
    debut, fin = datetime.fromisoformat(ligne["debut"]), datetime.fromisoformat(ligne["fin"])
    assert debut <= fin


@pytest.mark.skipif(_SANS_ESSAI, reason="sh ou flock absent, ou Windows")
def test_un_passage_sans_travail_note_des_listes_vides(tmp_path):
    script, env = _preparer(tmp_path)
    bord = tmp_path / "bord"
    env["RECO_BORD_DIR"] = str(bord)
    assert _lancer(script, env).returncode == 0
    [ligne] = _lignes(bord / "passages.jsonl")
    assert ligne["lancees"] == [] and ligne["echecs"] == []


@pytest.mark.skipif(_SANS_ESSAI, reason="sh ou flock absent, ou Windows")
def test_le_journal_garde_les_200_derniers_passages(tmp_path):
    script, env = _preparer(tmp_path)
    bord = tmp_path / "bord"
    bord.mkdir()
    anciens = "".join(json.dumps({"debut": f"ancien-{i}"}) + "\n" for i in range(205))
    (bord / "passages.jsonl").write_text(anciens, encoding="utf-8")
    env["RECO_BORD_DIR"] = str(bord)
    assert _lancer(script, env).returncode == 0
    lignes = _lignes(bord / "passages.jsonl")
    assert len(lignes) == 200
    assert lignes[0]["debut"] == "ancien-6"
    assert "lancees" in lignes[-1]


@pytest.mark.skipif(_SANS_ESSAI, reason="sh ou flock absent, ou Windows")
def test_le_dossier_par_defaut_est_celui_du_clone(tmp_path):
    script, env = _preparer(tmp_path)
    assert _lancer(script, env).returncode == 0
    attendu = tmp_path / "reco" / "depot" / "tools" / "output" / "bord" / "passages.jsonl"
    assert len(_lignes(attendu)) == 1


@pytest.mark.skipif(_SANS_ESSAI, reason="sh ou flock absent, ou Windows")
def test_un_suivi_impossible_n_arrete_pas_la_chaine(tmp_path):
    script, env = _preparer(tmp_path)
    obstacle = tmp_path / "fichier"
    obstacle.write_text("pas un dossier", encoding="utf-8")
    env["RECO_BORD_DIR"] = str(obstacle / "bord")
    res = _lancer(script, env)
    assert res.returncode == 0, res.stderr
    appels = (tmp_path / "appels.txt").read_text(encoding="utf-8")
    assert "curl " in appels, "le ping Kuma, après le suivi, n'a pas eu lieu"
    journal = next((tmp_path / "reco" / "logs").glob("tick-*.log")).read_text(encoding="utf-8")
    assert "suivi des passages impossible" in journal


@pytest.mark.skipif(_SANS_ESSAI, reason="sh ou flock absent, ou Windows")
def test_un_passage_se_signale_en_cours_puis_efface_son_fichier(tmp_path):
    # Tour 1, F8 repris : le tableau de bord sait qu'un passage tourne, donc ne crie pas
    # au retard pendant une longue transcription.
    script, env = _preparer(tmp_path)
    bord = tmp_path / "bord"
    env["RECO_BORD_DIR"] = str(bord)
    assert _lancer(script, env).returncode == 0
    [ligne] = _lignes(bord / "passages.jsonl")
    pendant = (tmp_path / "appels.txt.en-cours").read_text(encoding="utf-8").strip()
    assert pendant == ligne["debut"]
    assert not (bord / "en-cours").exists()


RAPPEL = "rappel_dimanche.py --notifier matrix"


@pytest.mark.skipif(_SANS_ESSAI, reason="sh ou flock absent, ou Windows")
@pytest.mark.parametrize(("jour", "heure"), [("7", "20"), ("7", "21"), ("7", "23")])
def test_le_rappel_part_le_dimanche_a_partir_de_20h(tmp_path, jour, heure):
    script, env = _preparer(tmp_path)
    env.update(RECO_BORD_DIR=str(tmp_path / "bord"), FAUX_JOUR=jour, FAUX_HEURE=heure)
    assert _lancer(script, env).returncode == 0
    appels = (tmp_path / "appels.txt").read_text(encoding="utf-8").splitlines()
    assert sum(RAPPEL in a for a in appels) == 1
    # Revue de la PR 4, F3 : le suivi des passages note l'étape lancée.
    [ligne] = _lignes(tmp_path / "bord" / "passages.jsonl")
    assert "rappel-dimanche" in ligne["lancees"]


@pytest.mark.skipif(_SANS_ESSAI, reason="sh ou flock absent, ou Windows")
@pytest.mark.parametrize(("jour", "heure"), [("7", "19"), ("7", "08"), ("7", "09"), ("7", "00"),
                                              ("6", "23"), ("1", "20")])
def test_le_rappel_ne_part_ni_un_autre_jour_ni_avant_20h(tmp_path, jour, heure):
    # « 08 » et « 09 » : lus en décimal par `[ -ge ]`, sans erreur d'octal.
    script, env = _preparer(tmp_path)
    env.update(RECO_BORD_DIR=str(tmp_path / "bord"), FAUX_JOUR=jour, FAUX_HEURE=heure)
    res = _lancer(script, env)
    assert res.returncode == 0, res.stderr
    assert RAPPEL not in (tmp_path / "appels.txt").read_text(encoding="utf-8")
    journal = next((tmp_path / "reco" / "logs").glob("tick-*.log")).read_text(encoding="utf-8")
    assert "rappel-dimanche" not in journal and "bad number" not in journal.lower()
    [ligne] = _lignes(tmp_path / "bord" / "passages.jsonl")
    assert "rappel-dimanche" not in ligne["lancees"]


@pytest.mark.skipif(_SANS_ESSAI, reason="sh ou flock absent, ou Windows")
def test_l_echec_du_rappel_est_note_et_n_arrete_pas_la_chaine(tmp_path):
    script, env = _preparer(tmp_path)
    bord = tmp_path / "bord"
    env.update(RECO_BORD_DIR=str(bord), FAUX_JOUR="7", FAUX_HEURE="20", FAUX_ECHEC="matrix")
    res = _lancer(script, env)
    assert res.returncode == 0, res.stderr
    [ligne] = _lignes(bord / "passages.jsonl")
    # `sorties_annoncees.py --notifier matrix` finit aussi par « matrix » : il échoue avec lui.
    assert ligne["echecs"][-1] == "rappel-dimanche"
    assert "curl " in (tmp_path / "appels.txt").read_text(encoding="utf-8")
    journal = next((tmp_path / "reco" / "logs").glob("tick-*.log")).read_text(encoding="utf-8")
    assert "message du dimanche soir en échec" in journal
