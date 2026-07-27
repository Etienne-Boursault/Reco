"""Conftest racine — chargé par pytest avant de descendre dans ``tests/``.

Garantit que ``tools/`` est en tête de ``sys.path`` AVANT l'import des
conftest sous ``tests/``. Sans cela, ``tests/cache/`` (qui n'a pas
d'``__init__.py``) est résolu comme *namespace package* ``cache`` et masque le
vrai paquet ``tools/cache/`` : l'import ``from cache.builder import …`` échoue
alors en CI avec ``ModuleNotFoundError: No module named 'cache.builder'``.

Le `pythonpath = ["tools", "tests"]` du ``pyproject.toml`` ne suffit pas :
selon l'OS et la version de pytest, l'insertion de ``tests`` (via le conftest
de sous-dossier) peut précéder celle de ``tools``. On force donc l'ordre ici,
au point d'entrée le plus précoce. Un paquet régulier (``tools/cache``) gagne
toujours sur un namespace package (``tests/cache``) dès que son dossier parent
est sur le path.
"""
import sys
from pathlib import Path

_TOOLS = str(Path(__file__).resolve().parent / "tools")
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)
