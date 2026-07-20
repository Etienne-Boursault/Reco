"""link_check.py — Vérifie qu'une URL de lien de reco est vivante.

Sépare le TRANSPORT (urllib, réseau) de la POLITIQUE (classification du
résultat). `classify()` est une fonction pure : toute la connaissance durement
acquise sur le comportement des plateformes y est testable sans réseau.

LIMITE STRUCTURELLE — à garder en tête à chaque usage : ce module établit
qu'une URL est VIVANTE, jamais qu'elle pointe vers la BONNE œuvre. Une
playlist proposée pour « Serge le Mytho » répondait 200 avec un titre
plausible ; c'était une vraie playlist, mais d'une autre émission. D'où
`ProbeResult.title`, affiché à l'appelant pour relecture humaine : c'est le
seul filet contre ce mode de défaillance.
"""
from __future__ import annotations

import html
import re
import ssl
import urllib.error
import urllib.request
from typing import Callable, NamedTuple
from urllib.parse import urlparse

__all__ = [
    "ProbeResult", "FetchOutcome", "verify_url", "classify",
    "page_title", "fetch_via_urllib", "host_in",
]

# Codes qui prouvent l'ABSENCE de la ressource. Eux seuls font rejeter.
DEAD_CODES = frozenset({404, 410})

# Codes qui ne prouvent RIEN : anti-bot, quota, panne passagère, géo-blocage.
# Les traiter comme des échecs rejetterait des liens parfaitement valides —
# constaté le 2026-07-20 sur Fnac Spectacles (403), Paramount+ (406),
# Qobuz (503) et chiensdenavarre.com (429, déclenché par nos propres threads
# lors d'un audit trop parallèle : sonder un host en série).
INCONCLUSIVE_CODES = frozenset({401, 403, 405, 406, 429, 500, 502, 503, 504})

# Hosts dont même le 404 ne prouve RIEN. Établi le 2026-07-20 en comparant un
# ID valide et un ID bidon sur chaque plateforme : Netflix et Deezer répondent
# 404 dans les DEUX cas, leur 404 ne porte donc aucune information.
# Disney+ en est volontairement ABSENT : il discrimine (vrai UUID → 200 avec
# titre, UUID bidon → 404), son 404 est exploitable — c'est ce qui a démasqué
# une URL Black Swan restée à l'ancien schéma `/movies/<slug>/<id>`.
# LIMITE ASSUMÉE : un lien fabriqué vers un host de cette liste passera le
# filtre. Seule une relecture humaine les couvre.
OPAQUE_404_HOSTS = frozenset({
    "netflix.com", "deezer.com",
    "hbomax.com", "paramountplus.com", "primevideo.com",
})

# YouTube place son <title> à ~700 Ko, derrière son bundle JS. Un plafond plus
# bas ferait passer une page valide pour une coquille vide.
MAX_BODY_BYTES = 2_500_000
_CHUNK_BYTES = 65_536

BROWSER_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
    # SOCS=CAI saute le mur de consentement européen. Sans lui on ne reçoit que
    # l'interstitiel — sur YouTube ET sur Canal+, qui passe alors de 403 à 200.
    "Cookie": "SOCS=CAI",
}

_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.S | re.I)
_BRAND_SUFFIX_RE = re.compile(
    r"\s*[-|–]\s*(YouTube|AlloCiné|Canal\+|Netflix|Disney\+)\s*$", re.I)


def _make_ssl_context() -> ssl.SSLContext:
    """Contexte TLS adossé à certifi quand il est disponible.

    Le magasin de certificats système de certains postes est périmé : il
    faisait échouer fr.wikipedia.org en « certificate has expired », un faux
    négatif qui aurait fait rejeter un lien parfaitement valide.
    """
    try:
        import certifi
    except ImportError:  # pragma: no cover - certifi est une dépendance présente
        return ssl.create_default_context()
    return ssl.create_default_context(cafile=certifi.where())


def host_in(url: str, domains: frozenset[str]) -> bool:
    """True si le host de `url` est dans `domains` (exact ou sous-domaine)."""
    try:
        host = (urlparse(url).hostname or "").lower().lstrip(".")
    except ValueError:
        return False
    return any(host == d or host.endswith("." + d) for d in domains)


def page_title(body: str) -> str:
    """Titre de la page, vidé de son suffixe de marque. "" si absent."""
    match = _TITLE_RE.search(body)
    if not match:
        return ""
    title = html.unescape(re.sub(r"\s+", " ", match.group(1))).strip()
    return _BRAND_SUFFIX_RE.sub("", title).strip()


class FetchOutcome(NamedTuple):
    """Résultat brut du transport, avant toute interprétation.

    `status` vaut None quand aucune réponse HTTP n'a été obtenue (DNS, TLS,
    timeout) — cas où `error` est renseigné.
    """
    status: int | None
    body: str = ""
    error: str = ""


class ProbeResult(NamedTuple):
    """Verdict interprété.

    `accepted` est délibérément True pour "unknown" : on laisse passer plutôt
    que de rejeter un lien valide qu'on n'a pas su vérifier. L'incertitude
    remonte par `verdict`, à l'appelant d'en tenir le compte.
    """
    verdict: str          # "alive" | "dead" | "unknown"
    detail: str
    title: str = ""

    @property
    def accepted(self) -> bool:
        return self.verdict != "dead"


Fetcher = Callable[[str, float], FetchOutcome]


def fetch_via_urllib(url: str, timeout: float) -> FetchOutcome:
    """Transport réel. GET et non HEAD : le corps est nécessaire au titre."""
    req = urllib.request.Request(url, method="GET", headers=dict(BROWSER_HEADERS))
    try:
        with urllib.request.urlopen(req, timeout=timeout,
                                    context=_make_ssl_context()) as resp:
            charset = resp.headers.get_content_charset() or "utf-8"
            # Lecture incrémentale : on s'arrête dès </title> pour ne pas
            # rapatrier le mégaoctet de JS que servent YouTube ou Netflix.
            chunks: list[bytes] = []
            size = 0
            while size < MAX_BODY_BYTES:
                chunk = resp.read(_CHUNK_BYTES)
                if not chunk:
                    break
                chunks.append(chunk)
                size += len(chunk)
                # Deux chunks : le marqueur peut chevaucher une frontière.
                if b"</title>" in b"".join(chunks[-2:]):
                    break
            return FetchOutcome(resp.status, b"".join(chunks).decode(charset, "replace"))
    except urllib.error.HTTPError as exc:
        return FetchOutcome(exc.code)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        # Réseau, DNS, TLS : jamais une preuve d'absence de la ressource.
        return FetchOutcome(None, error=str(exc)[:70])


def classify(url: str, outcome: FetchOutcome) -> ProbeResult:
    """Interprète un FetchOutcome. Fonction pure — tout le savoir est ici."""
    if outcome.status is None:
        return ProbeResult("unknown", f"injoignable ({outcome.error})")
    if outcome.status in DEAD_CODES:
        if host_in(url, OPAQUE_404_HOSTS):
            return ProbeResult("unknown", f"HTTP {outcome.status} (host au 404 opaque)")
        return ProbeResult("dead", f"HTTP {outcome.status}")
    if outcome.status in INCONCLUSIVE_CODES:
        return ProbeResult("unknown", f"HTTP {outcome.status} (non concluant)")
    if outcome.status >= 400:
        return ProbeResult("unknown", f"HTTP {outcome.status}")
    title = page_title(outcome.body)
    if not title:
        # Page servie mais sans titre : coquille vide (playlist supprimée,
        # fiche inexistante). C'est LA signature des identifiants inventés —
        # YouTube répond 200 à n'importe quel ID de playlist bien formé, y
        # compris du garbage pur, et seul le titre absent les distingue.
        return ProbeResult("dead", f"HTTP {outcome.status} mais page sans titre")
    return ProbeResult("alive", f"HTTP {outcome.status}", title)


def verify_url(url: str, timeout: float = 15.0,
               cache: dict[str, ProbeResult] | None = None,
               fetcher: Fetcher = fetch_via_urllib) -> ProbeResult:
    """Sonde `url` et classe le résultat. `cache` évite les doublons."""
    if cache is not None and url in cache:
        return cache[url]
    result = classify(url, fetcher(url, timeout))
    if cache is not None:
        cache[url] = result
    return result
