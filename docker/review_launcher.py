"""Launcher conteneur pour `tools/review_server.py`.

`review_server.main()` instancie un `HTTPServer(("127.0.0.1", port), …)` en dur
(cf. tools/review_server.py:100). Dans un conteneur, ce bind n'est pas joignable
depuis l'extérieur — on ne peut pas exposer le port avec `-p 8000:8000`.

On évite de patcher review_server.py (zone sensible Phase 2 close) et on
monkeypatche `HTTPServer.__init__` avant l'import pour forcer le bind sur
``0.0.0.0``. Single point of change, pas de fork du code métier.

Usage :
    python docker/review_launcher.py --source un-bon-moment --port 8000
"""

from __future__ import annotations

import http.server
import sys

_original_init = http.server.HTTPServer.__init__


def _bind_all(self, server_address, RequestHandlerClass, bind_and_activate=True):
    # On garde le port d'origine, on remplace l'adresse par 0.0.0.0.
    host, port = server_address
    if host in ("127.0.0.1", "localhost", ""):
        host = "0.0.0.0"  # noqa: S104 — voulu : conteneur, exposition contrôlée par compose
    _original_init(self, (host, port), RequestHandlerClass, bind_and_activate)


http.server.HTTPServer.__init__ = _bind_all  # type: ignore[method-assign]

# review_server vit dans /app/tools (PYTHONPATH=/app/tools). On l'importe
# *après* le monkeypatch pour que son `HTTPServer(...)` hérite du nouveau init.
sys.argv[0] = "review_server"
import review_server  # type: ignore  # noqa: E402

if __name__ == "__main__":
    review_server.main()
