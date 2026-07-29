r"""Hygiène du dépôt : aucun fichier vide ne doit être suivi par git.

POURQUOI — incident du 2026-07-29.

Les commandes shell mal échappées (un `>` non protégé dans une chaîne, un
heredoc non quoté) créent des fichiers de 0 octet aux noms absurdes à la racine
du dépôt : `0)`, `2\``, `branches`, `r.data)`, `{,+`… Pris isolément c'est
anodin. Le problème est qu'un `git add -A` les fait entrer dans un commit sans
que personne ne les voie — c'est arrivé **sept fois**, sur quatre commits
différents, dont un datant de plusieurs mois.

Ce test les attrape à la première exécution de la suite, avec leur nom exact.

Les seuls fichiers vides légitimes sont les `__init__.py` qui marquent un
paquet Python.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]

#: Fichiers vides admis : marqueurs de paquet Python.
NOMS_AUTORISES = {"__init__.py", ".gitkeep", ".keep"}


def _fichiers_suivis() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=RACINE, capture_output=True, text=True, check=True,
    )
    return [p for p in out.stdout.split("\0") if p]


def test_aucun_fichier_vide_suivi_par_git():
    vides = []
    for rel in _fichiers_suivis():
        chemin = RACINE / rel
        if Path(rel).name in NOMS_AUTORISES:
            continue
        try:
            if chemin.is_file() and chemin.stat().st_size == 0:
                vides.append(rel)
        except OSError:
            # Fichier listé par git mais absent du disque (checkout partiel) :
            # ce n'est pas l'objet de ce test.
            continue

    assert not vides, (
        "Fichiers de 0 octet suivis par git — presque toujours des résidus de "
        "commandes shell mal échappées, entrés via un `git add -A` :\n  "
        + "\n  ".join(repr(v) for v in vides)
        + "\n\nSupprimez-les : git rm --cached <fichier> && rm <fichier>"
    )
