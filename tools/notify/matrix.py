"""notify.matrix — sender vers un salon Matrix (API Client-Server).

Poste un événement `m.room.message` dans un salon via
`PUT /_matrix/client/v3/rooms/{roomId}/send/m.room.message/{txnId}`.

Config (secrète) passée au constructeur — en pratique lue depuis l'env côté
CLI :
  - `homeserver` : URL de base du homeserver (ex. https://matrix.exemple.fr).
  - `token`      : access token d'un utilisateur « bot » (RECO_MATRIX_TOKEN).
  - `room_id`    : identifiant du salon (`!xxx:serveur` ou alias `#reco:serveur`).

On ne logue JAMAIS le token — seulement le host du homeserver en cas d'erreur.
Best-effort : on logue et on renvoie False, sans jamais lever (parité avec les
autres senders — un canal en panne ne doit pas casser le poll).
"""
from __future__ import annotations

import uuid
from urllib.parse import quote, urlparse

from common import log


class MatrixSender:
    """PUT un `m.room.message` dans le salon configuré.

    Attribut `name="matrix"` pour le routing depuis le CLI.
    """

    name = "matrix"

    def __init__(
        self,
        homeserver: str,
        token: str,
        room_id: str,
        *,
        timeout: float = 10.0,
        session=None,
    ) -> None:
        if not homeserver or not token or not room_id:
            raise ValueError(
                "MatrixSender : homeserver/token/room_id requis — vérifie "
                "RECO_MATRIX_HOMESERVER / RECO_MATRIX_TOKEN / RECO_MATRIX_ROOM.",
            )
        self._hs = homeserver.rstrip("/")
        self._token = token
        self._room = room_id
        self._timeout = timeout
        self._session = session  # injecté en test ; sinon `requests` global.

    def _endpoint(self) -> str:
        txn = uuid.uuid4().hex
        room = quote(self._room, safe="")
        return f"{self._hs}/_matrix/client/v3/rooms/{room}/send/m.room.message/{txn}"

    def _put(self, content: dict):
        url = self._endpoint()
        headers = {"Authorization": f"Bearer {self._token}"}
        if self._session is not None:
            return self._session.put(url, json=content, headers=headers, timeout=self._timeout)
        import requests

        return requests.put(url, json=content, headers=headers, timeout=self._timeout)

    def send(self, payload: dict) -> bool:
        try:
            resp = self._put(payload)
        except Exception as exc:  # noqa: BLE001 — best-effort, ne casse pas le poll
            host = urlparse(self._hs).hostname or "matrix"
            log.warning("Matrix (%s) a échoué : %s", host, exc)
            return False
        ok = bool(getattr(resp, "ok", False)) or getattr(resp, "status_code", 0) == 200
        if not ok:
            log.warning("Matrix a renvoyé status=%s", getattr(resp, "status_code", "?"))
        return ok
