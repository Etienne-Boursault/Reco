"""Tests garde SSRF (B-CRIT-2)."""
from __future__ import annotations

import pytest

from meta.url_safety import is_safe_external_url


def test_https_public_host_ok() -> None:
    # Resolver injecté avec une IP publique → safe.
    assert is_safe_external_url(
        "https://example.com/path", resolver=lambda h: ["93.184.216.34"],
    )


def test_http_rejected() -> None:
    assert is_safe_external_url("http://example.com") is False


def test_scheme_file_rejected() -> None:
    assert is_safe_external_url("file:///etc/passwd") is False


def test_loopback_ip_rejected() -> None:
    assert is_safe_external_url("https://127.0.0.1/x") is False
    assert is_safe_external_url("https://[::1]/x") is False


def test_private_rfc1918_rejected() -> None:
    for ip in ("10.0.0.1", "172.16.0.1", "192.168.1.1"):
        assert is_safe_external_url(f"https://{ip}/x") is False, ip


def test_link_local_rejected() -> None:
    assert is_safe_external_url("https://169.254.169.254/latest") is False


def test_ipv6_unique_local_rejected() -> None:
    assert is_safe_external_url("https://[fc00::1]/x") is False
    assert is_safe_external_url("https://[fe80::1]/x") is False


def test_host_resolves_private_rejected() -> None:
    """DNS rebind simple : un host qui résout en IP RFC1918 est bloqué."""
    assert is_safe_external_url(
        "https://attacker.example/", resolver=lambda h: ["10.0.0.5"],
    ) is False


def test_resolver_failure_blocks() -> None:
    def fail(_h: str) -> list[str]:
        raise OSError("dns")

    assert is_safe_external_url("https://x.example/", resolver=fail) is False


def test_resolver_empty_blocks() -> None:
    assert is_safe_external_url("https://x.example/", resolver=lambda h: []) is False


def test_empty_string_rejected() -> None:
    assert is_safe_external_url("") is False
    assert is_safe_external_url("   ") is False


def test_non_string_rejected() -> None:
    assert is_safe_external_url(None) is False  # type: ignore[arg-type]
    assert is_safe_external_url(42) is False  # type: ignore[arg-type]


def test_no_hostname_rejected() -> None:
    assert is_safe_external_url("https:///path") is False


def test_default_resolver_invoked_for_ip_path() -> None:
    """Hostname est une IP → on n'invoque pas le resolver."""
    calls: list[str] = []

    def spy(h: str) -> list[str]:
        calls.append(h)
        return ["1.1.1.1"]

    assert is_safe_external_url("https://8.8.8.8/x", resolver=spy) is True
    assert calls == []


def test_default_resolver_used_when_none() -> None:
    """Smoke : le resolver par défaut est `socket.getaddrinfo`. On le
    monkey-patche via le module pour ne pas dépendre du DNS réel."""
    import socket

    orig = socket.getaddrinfo
    try:
        socket.getaddrinfo = lambda *a, **k: [  # type: ignore[assignment]
            (None, None, None, None, ("93.184.216.34", 0))
        ]
        assert is_safe_external_url("https://example.com/") is True
    finally:
        socket.getaddrinfo = orig  # type: ignore[assignment]


def test_invalid_url_with_value_error() -> None:
    """URL malformée (`urlparse` lève) → False."""
    # urlparse est tolérant ; on construit une chaîne qui passe puis
    # échoue côté ipaddress.
    assert is_safe_external_url("https://[bad::ip") is False


def test_addr_unparseable_treated_as_private() -> None:
    """Un resolver qui retourne une chaîne non-IP → bloqué."""
    assert is_safe_external_url(
        "https://x.example/", resolver=lambda h: ["not-an-ip"],
    ) is False
