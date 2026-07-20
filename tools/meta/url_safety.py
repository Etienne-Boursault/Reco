"""tools.meta.url_safety — Garde SSRF pour les fetches externes.

B-CRIT-2 — Avant tout `requests.get(url)` sur une URL fournie par un
fichier de configuration (registries.yaml/json), on doit s'assurer que
l'URL :

  - utilise le schéma ``https://`` (pas de ``http://``, ``file://``,
    ``ftp://``, ``gopher://``, …) ;
  - cible un host externe **public** — pas une IP RFC1918 (10/8,
    172.16/12, 192.168/16), pas du lien-local IPv4 (169.254/16), pas
    du loopback (127/8, ``::1``), pas une adresse IPv6 unique-local
    (``fc00::/7``) ni link-local (``fe80::/10``).

Le helper résout les hostnames en best-effort (``socket.getaddrinfo``)
pour bloquer les noms qui pointent vers un réseau interne (« DNS
rebinding » dans sa variante simple). Si la résolution échoue (offline,
DNS lent…), on rejette aussi : l'appelant remonte ``error="ssrf: …"`` et
le pipeline continue sur le registry suivant.

API publique :

    >>> from tools.meta.url_safety import is_safe_external_url
    >>> is_safe_external_url("https://example.com/.well-known/x.json")
    True
    >>> is_safe_external_url("http://example.com")
    False
    >>> is_safe_external_url("https://127.0.0.1/x")
    False

Le helper est volontairement strict : false-positives possibles sur
hosts non-résolvables. Pour les tests / fixtures, injecter un
``resolver`` qui renvoie une liste d'adresses contrôlées.
"""
from __future__ import annotations

import ipaddress
import socket
from typing import Callable, Iterable
from urllib.parse import urlparse

#: Schémas autorisés. ``https`` uniquement — `http` est explicitement
#: rejeté pour éviter qu'un MITM réécrive la réponse.
_ALLOWED_SCHEMES: frozenset[str] = frozenset({"https"})

#: Type d'un resolver injectable (testable). Retourne une liste d'IPs
#: (str) pour un host donné, ou lève ``OSError`` si la résolution échoue.
HostResolver = Callable[[str], Iterable[str]]


def _default_resolver(host: str) -> list[str]:
    """Résout `host` via ``socket.getaddrinfo`` (A + AAAA)."""
    infos = socket.getaddrinfo(host, None)
    return [info[4][0] for info in infos]


def _is_private_ip(addr: str) -> bool:
    """True si `addr` n'est pas une adresse publique globale.

    Couvre : loopback, link-local, private (RFC1918), unique-local IPv6
    (``fc00::/7``), multicast, réservé, non-spécifié.
    """
    try:
        ip = ipaddress.ip_address(addr)
    except ValueError:
        # Si l'input n'est pas une IP, on est conservateur → bloque.
        return True
    return not ip.is_global or ip.is_loopback or ip.is_link_local or ip.is_private


def is_safe_external_url(
    url: str, *, resolver: HostResolver | None = None
) -> bool:
    """Renvoie True si `url` peut être fetchée sans risque SSRF évident.

    Args:
        url: URL à valider.
        resolver: callable injectable ``host -> list[str]`` (tests).
            Par défaut, ``socket.getaddrinfo``.
    """
    if not isinstance(url, str) or not url.strip():
        return False
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    if parsed.scheme not in _ALLOWED_SCHEMES:
        return False
    host = parsed.hostname
    if not host:
        return False
    # Si le hostname est déjà une IP, on check direct.
    try:
        ipaddress.ip_address(host)
        return not _is_private_ip(host)
    except ValueError:
        pass
    # Sinon, on résout — on rejette si toute IP retournée est privée
    # OU si la résolution échoue.
    resolve = resolver or _default_resolver
    try:
        addrs = list(resolve(host))
    except OSError:
        return False
    if not addrs:
        return False
    for addr in addrs:
        if _is_private_ip(addr):
            return False
    return True


__all__ = ["HostResolver", "is_safe_external_url"]
