"""tools.meta.fetcher — Fetch HTTP des registries déclarés.

Lit un fichier YAML ou JSON listant les URLs des registries (chacune
pointant vers un `/.well-known/reco-registry.json`), les fetche en GET
(cache requests-cache TTL 1h), valide chaque document, et retourne la
liste des entrées valides + un compteur d'erreurs.

R-P1-02 : `RegistryHttpGet` est formellement un `typing.Protocol`.
H24-4   : cap `--max-bytes` (défaut 256 KiB) — abandon dès dépassement.
M24-18  : distinction `Timeout` / `ConnectionError` dans le tag d'erreur.
"""
from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from .url_safety import HostResolver, is_safe_external_url
from .validator import RegistryValidationError, validate_registry

#: Cap par défaut du payload fetché (H24-4). 256 KiB suffit largement
# pour un registry réaliste (~5 KB).
DEFAULT_MAX_BYTES: int = 256 * 1024


class RegistryFetchError(RuntimeError):
    """Erreur de fetch (réseau, statut HTTP, JSON invalide)."""


class PayloadTooLargeError(RegistryFetchError):
    """Le payload distant dépasse le cap autorisé (H24-4)."""


@runtime_checkable
class RegistryHttpGet(Protocol):
    """R-P1-02 — Protocol formel pour les callables HTTP injectés.

    Implémentation minimale : `(url: str) -> (status_code: int, text: str)`.
    Lever une exception standard (`TimeoutError`, `ConnectionError`, ...)
    pour signaler une erreur réseau ; le fetcher distingue les variétés.
    """

    def __call__(self, url: str) -> tuple[int, str]: ...  # pragma: no cover


@dataclass
class FetchResult:
    """Résultat d'un fetch unitaire."""

    source_url: str
    registry: dict[str, Any] | None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.registry is not None and self.error is None


#: B-LOW-4 — heuristique de noms : on n'attrape QUE les classes dont le
#: nom commence/finit par les tokens connus (`Timeout`, `Connection`,
#: `DnsError`, …) — pas une simple recherche par substring qui ramènerait
#: des faux positifs type `MyTimeoutLogger`.
_TIMEOUT_NAMES: frozenset[str] = frozenset(
    {"timeout", "readtimeout", "connecttimeout", "writetimeout"}
)
_CONNECTION_NAMES: frozenset[str] = frozenset(
    {"connectionerror", "connectionrefusederror", "dnserror", "dnsfailure"}
)


def _classify_network_error(exc: BaseException) -> str:
    """M24-18 — choisit un tag d'erreur lisible selon le type d'exception.

    B-LOW-4 — match exact (lower-cased) sur les noms de classe pour ne pas
    confondre une `MyTimeoutLogger` avec un vrai `Timeout`.
    """
    if isinstance(exc, TimeoutError):
        return f"timeout: {exc}"
    if isinstance(exc, ConnectionError):
        return f"connection: {exc}"
    name = type(exc).__name__.lower()
    if name in _TIMEOUT_NAMES:
        return f"timeout: {exc}"
    if name in _CONNECTION_NAMES:
        return f"connection: {exc}"
    return f"network: {exc}"


@dataclass
class RegistryFetcher:
    """Fetcher injectable — le `get` est un callable, ce qui permet d'éviter
    `requests` dans les tests.

    Signature `get(url) -> (status_code, text)`.
    """

    get: RegistryHttpGet
    max_bytes: int = DEFAULT_MAX_BYTES
    results: list[FetchResult] = field(default_factory=list)
    #: B-CRIT-2 — resolver SSRF injectable (tests). ``None`` = ``socket``.
    url_resolver: HostResolver | None = None
    #: B-CRIT-2 — désactive la garde SSRF (tests uniquement, JAMAIS en prod).
    allow_unsafe_urls: bool = False

    def fetch_one(self, source_url: str) -> FetchResult:
        # B-CRIT-2 — garde SSRF avant tout fetch réseau.
        if not self.allow_unsafe_urls and not is_safe_external_url(
            source_url, resolver=self.url_resolver
        ):
            res = FetchResult(
                source_url=source_url,
                registry=None,
                error="ssrf: URL non autorisée (https public uniquement)",
            )
            self.results.append(res)
            return res
        try:
            status, text = self.get(source_url)
        # B-LOW-5 — `Exception` (pas `BaseException`) : on laisse passer
        # `KeyboardInterrupt`/`SystemExit` qui héritent de `BaseException`
        # et doivent rester non rattrapées pour permettre l'arrêt propre.
        except Exception as exc:  # noqa: BLE001 — on capture pour reporter
            res = FetchResult(
                source_url=source_url,
                registry=None,
                error=_classify_network_error(exc),
            )
            self.results.append(res)
            return res
        # H24-4 — cap byte-size : on rejette dès le dépassement, avant tout
        # parse JSON, pour éviter un DoS via réponse géante.
        encoded_size = len(text.encode("utf-8", errors="ignore"))
        if encoded_size > self.max_bytes:
            res = FetchResult(
                source_url=source_url,
                registry=None,
                error=f"payload too large: {encoded_size} > {self.max_bytes}",
            )
            self.results.append(res)
            return res
        if status != 200:
            res = FetchResult(
                source_url=source_url,
                registry=None,
                error=f"http {status}",
            )
            self.results.append(res)
            return res
        try:
            raw = json.loads(text)
        except json.JSONDecodeError as exc:
            res = FetchResult(source_url=source_url, registry=None, error=f"json: {exc.msg}")
            self.results.append(res)
            return res
        try:
            doc = validate_registry(raw)
        except RegistryValidationError as exc:
            res = FetchResult(source_url=source_url, registry=None, error=str(exc))
            self.results.append(res)
            return res
        res = FetchResult(source_url=source_url, registry=doc)
        self.results.append(res)
        return res

    def fetch_many(self, urls: Iterable[str]) -> list[FetchResult]:
        return [self.fetch_one(u) for u in urls]


def load_registries_file(path: Path) -> list[str]:
    """Charge un fichier listant les URLs des registries (YAML ou JSON).

    Formats acceptés :
      - JSON : `["https://a/.well-known/reco-registry.json", ...]`
      - JSON : `{"registries": ["..."]}`
      - YAML : équivalent (si PyYAML dispo, sinon le YAML doit être trivial)

    Lève FileNotFoundError ou RegistryFetchError.
    """
    if not path.exists():
        raise FileNotFoundError(f"Fichier des registries introuvable : {path}")

    text = path.read_text(encoding="utf-8")
    raw: Any
    if path.suffix.lower() in (".yaml", ".yml"):
        try:
            import yaml  # noqa: PLC0415

            raw = yaml.safe_load(text)
        except ImportError as exc:  # pragma: no cover
            raise RegistryFetchError(
                "PyYAML requis pour les fichiers .yaml/.yml. "
                "Installe-le ou utilise un fichier .json."
            ) from exc
    else:
        try:
            raw = json.loads(text)
        except json.JSONDecodeError as exc:
            raise RegistryFetchError(f"JSON invalide ({path}): {exc.msg}") from exc

    if isinstance(raw, dict):
        raw = raw.get("registries", [])
    if not isinstance(raw, list):
        raise RegistryFetchError(
            f"Format inattendu : list[str] ou {{registries: [...]}} attendu ({path})"
        )
    urls: list[str] = []
    for item in raw:
        # B-LOW-6 — message d'erreur explicite : on distingue
        # "type incorrect" et "string vide" pour faciliter le debug.
        if not isinstance(item, str):
            raise RegistryFetchError(
                f"Entrée non-string dans {path}: {item!r} "
                f"(type {type(item).__name__})"
            )
        if not item.strip():
            raise RegistryFetchError(
                f"Entrée vide dans {path}: une URL non-blanche est attendue"
            )
        urls.append(item.strip())
    return urls
