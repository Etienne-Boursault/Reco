"""rss.ports — Protocols pour injection de dépendance.

Pourquoi : permet aux tests d'injecter un `FeedFetcher` qui renvoie des
octets de fixture, sans aucun appel HTTP réel. C'est la garantie « pas de
HTTP réel en CI » du roadmap item #23.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class FetchResult:
    """Résultat d'un fetch RSS : bytes + en-têtes utiles au cache HTTP.

    `etag`/`last_modified` sont remontés du serveur pour les requêtes
    conditionnelles `If-None-Match`/`If-Modified-Since` du prochain run.
    `not_modified` est True si le serveur a répondu 304 — alors `body`
    sera vide et il faut réutiliser l'état précédent.
    """

    body: bytes
    etag: str | None = None
    last_modified: str | None = None
    not_modified: bool = False


class FeedFetcher(Protocol):
    """Récupère un flux RSS. Injecté par DI pour les tests."""

    def fetch(
        self,
        url: str,
        *,
        etag: str | None = None,
        last_modified: str | None = None,
    ) -> FetchResult:
        """Renvoie les octets du flux + en-têtes HTTP utiles.

        Si `etag`/`last_modified` fournis, le fetcher SHOULD envoyer
        `If-None-Match`/`If-Modified-Since` et renvoyer `not_modified=True`
        en cas de 304 — économise bande et quota côté hébergeur RSS.
        """
        ...
