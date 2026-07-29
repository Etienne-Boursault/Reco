"""Tests du module tools/review_handler_base.py.

Ces tests ciblent la plomberie HTTP partagée : regex de validation, headers
sécu, parse POST, gestion du cache reco_id → Path. Aucun handler métier ici
(cf. test_review_server.py pour ces tests).
"""
from __future__ import annotations

import json
import pytest

import review_handler_base as rhb


# ===== Regex de validation ==================================================
@pytest.mark.parametrize(
    "rid,expected",
    [
        ("ubm-001", True),
        ("ds-0042", True),
        ("abc_123", True),
        ("UBM-001", False),     # majuscules refusées
        ("ubm 001", False),     # espace refusé
        ("ubm-001!", False),    # symbole refusé
        ("", False),
        ("../../etc/passwd", False),  # traversal refusé
    ],
)
def test_RE_RECO_ID_validates(rid, expected):
    assert bool(rhb._RE_RECO_ID.match(rid)) is expected


@pytest.mark.parametrize(
    "guid,expected",
    [
        ("ep-001", True),
        ("8df3c12c-9ab7-4d4e-9c2a-71c8f8c9d2e1", True),
        ("https://example.com/path", True),    # URL-style guid
        ("guid@host", True),
        ("", False),
        ("a" * 257, False),                    # trop long
        ("guid avec espace", False),           # espaces interdits
        ("guid;rm -rf", False),                # injection-y refusée
    ],
)
def test_RE_GUID_validates(guid, expected):
    assert bool(rhb._RE_GUID.match(guid)) is expected


# ===== Security headers =====================================================
def test_security_headers_basic():
    """Headers minimaux toujours présents."""
    h = rhb._SECURITY_HEADERS
    assert h["X-Content-Type-Options"] == "nosniff"
    assert h["X-Frame-Options"] == "DENY"
    assert h["Referrer-Policy"] == "strict-origin-when-cross-origin"
    csp = h["Content-Security-Policy"]
    assert "frame-src" in csp
    assert "youtube.com" in csp


def test_csp_allows_youtube_thumbnails():
    csp = rhb._SECURITY_HEADERS["Content-Security-Policy"]
    assert "i.ytimg.com" in csp


def test_csp_allows_podcast_audio():
    """media-src doit autoriser l'audio https (MP3 Acast) — sinon le lecteur
    audio des épisodes audio-only est bloqué par le CSP (retour user 07-24)."""
    csp = rhb._SECURITY_HEADERS["Content-Security-Policy"]
    assert "media-src https:" in csp


def test_csp_allows_youtube_player_api_script():
    """L'IFrame Player API YouTube (pilotage clavier) doit pouvoir se charger."""
    csp = rhb._SECURITY_HEADERS["Content-Security-Policy"]
    assert "script-src" in csp and "https://www.youtube.com" in csp


# ===== Parse POST ============================================================
def test_parse_post_data_simple():
    body = b"id=ubm-001&action=validate"
    out = rhb._parse_post_data(body)
    assert out["id"] == ["ubm-001"]
    assert out["action"] == ["validate"]


def test_parse_post_data_multivalue():
    """Plusieurs valeurs pour une même clé (checkbox group)."""
    body = b"who=alice&who=bob&other=carol"
    out = rhb._parse_post_data(body)
    assert out["who"] == ["alice", "bob"]
    assert out["other"] == ["carol"]


def test_parse_post_data_blank_values_kept():
    """keep_blank_values=True : un input vide ne disparaît pas."""
    body = b"id=ubm-001&title="
    out = rhb._parse_post_data(body)
    assert out["title"] == [""]


# ===== Cache reco_id → Path =================================================
def test_invalidate_reco_path_cache_clears_only_target_source():
    """L'invalidation ne touche que la source ciblée (cache cross-source)."""
    from pathlib import Path
    rhb._RECO_PATH_CACHE.clear()
    rhb._RECO_PATH_CACHE["src-a"] = {"id-1": Path("/tmp/a.json")}
    rhb._RECO_PATH_CACHE["src-b"] = {"id-1": Path("/tmp/b.json")}
    rhb._invalidate_reco_path_cache("src-a")
    assert "src-a" not in rhb._RECO_PATH_CACHE
    assert "src-b" in rhb._RECO_PATH_CACHE
    rhb._RECO_PATH_CACHE.clear()


def test_rebuild_and_lookup_reco_path(tmp_path, monkeypatch):
    """rebuild lit le disque ; reco_path retourne via le cache."""
    import common
    rhb._RECO_PATH_CACHE.clear()
    src_id = "demo-rhb"
    recos_dir = tmp_path / "recos" / src_id
    recos_dir.mkdir(parents=True)
    (recos_dir / "ubm-001.json").write_text(
        json.dumps({"id": "ubm-001", "title": "X"}), encoding="utf-8",
    )
    monkeypatch.setattr(common, "RECOS_DIR", tmp_path / "recos")
    rhb._rebuild_reco_path_cache(src_id)
    p = rhb._reco_path(src_id, "ubm-001")
    assert p is not None and p.exists()
    assert rhb._reco_path(src_id, "missing") is None
    rhb._RECO_PATH_CACHE.clear()


def test_rebuild_skips_unreadable_json(tmp_path, monkeypatch, caplog):
    """JSON corrompu → warning + skip, pas de crash (#5 sécu)."""
    import common
    rhb._RECO_PATH_CACHE.clear()
    src_id = "demo-rhb2"
    recos_dir = tmp_path / "recos" / src_id
    recos_dir.mkdir(parents=True)
    (recos_dir / "ok.json").write_text(
        json.dumps({"id": "ubm-ok"}), encoding="utf-8",
    )
    (recos_dir / "broken.json").write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(common, "RECOS_DIR", tmp_path / "recos")
    with caplog.at_level("WARNING"):
        rhb._rebuild_reco_path_cache(src_id)
    assert rhb._reco_path(src_id, "ubm-ok") is not None
    assert any("illisible" in r.message for r in caplog.records)
    rhb._RECO_PATH_CACHE.clear()


# ===== Décorateur _invalidates_reco_cache ===================================
def test_invalidates_reco_cache_decorator_clears_after_call():
    """Le décorateur invalide le cache même si la fonction lève."""
    from pathlib import Path

    class _Fake:
        source_id = "deco-src"

        @rhb._invalidates_reco_cache
        def mutate(self):
            return "ok"

        @rhb._invalidates_reco_cache
        def explode(self):
            raise RuntimeError("boom")

    rhb._RECO_PATH_CACHE["deco-src"] = {"x": Path("/tmp/x.json")}
    _Fake().mutate()
    assert "deco-src" not in rhb._RECO_PATH_CACHE

    rhb._RECO_PATH_CACHE["deco-src"] = {"y": Path("/tmp/y.json")}
    with pytest.raises(RuntimeError):
        _Fake().explode()
    assert "deco-src" not in rhb._RECO_PATH_CACHE


# ===== Constantes ============================================================
def test_max_post_bytes_is_reasonable():
    """Limite anti-DoS sur les POST : 1 MiB."""
    assert rhb._MAX_POST_BYTES == 1 << 20


# ===== Code mort supprimé (rev-server m1, revue 2026-07-19) =================
def test_dead_helpers_removed():
    """`_send_error` et `_csrf_check` étaient sans appelant → supprimés.

    Garde anti-régression : leur réintroduction (copier-coller) doit échouer
    ici plutôt que réaccumuler du code mort. On garde bien `_send`/`_send_404`
    (utilisés) et `_is_same_origin` (l'implémentation réelle du contrôle CSRF).
    """
    assert not hasattr(rhb.BaseHandler, "_send_error")
    assert not hasattr(rhb.BaseHandler, "_csrf_check")
    assert hasattr(rhb.BaseHandler, "_send")
    assert hasattr(rhb.BaseHandler, "_send_404")
    assert hasattr(rhb.BaseHandler, "_is_same_origin")


# ===== BaseHandler.__init__ garde source_id =================================
def test_base_handler_requires_source_id():
    """#3 sécu — instancier BaseHandler sans source_id lève ValueError (avant
    tout accès socket : la garde est en tête de __init__)."""
    with pytest.raises(ValueError, match="source_id"):
        rhb.BaseHandler(source_id="")


# ===== _is_private_ip =======================================================
@pytest.mark.parametrize("ip, expected", [
    ("192.168.1.10", True),
    ("10.0.0.1", True),
    ("172.16.5.4", True),
    ("127.0.0.1", True),
    ("::1", True),
    ("8.8.8.8", False),
    ("2001:4860:4860::8888", False),
])
def test_is_private_ip(ip, expected):
    assert rhb._is_private_ip(ip) is expected


@pytest.mark.parametrize("garbage", ["", "pas-une-ip", "999.999.999.999",
                                     "192.168.1", "<script>"])
def test_is_private_ip_rejects_garbage(garbage):
    """L'adresse vient de `client_address` / d'un header : une valeur illisible
    doit être traitée comme NON privée (refus), jamais lever."""
    assert rhb._is_private_ip(garbage) is False


# ===== _rebuild_reco_path_cache : entrées sans id ===========================
def test_rebuild_skips_reco_without_id(tmp_path, monkeypatch):
    """Un JSON valide mais sans `id` (brouillon, fichier annexe) n'entre pas au
    cache — sinon on indexerait `None`."""
    import common
    rhb._RECO_PATH_CACHE.clear()
    src_id = "demo-rhb-noid"
    recos_dir = tmp_path / "recos" / src_id
    recos_dir.mkdir(parents=True)
    (recos_dir / "sans-id.json").write_text(
        json.dumps({"title": "Sans identifiant"}), encoding="utf-8")
    (recos_dir / "ubm-001.json").write_text(
        json.dumps({"id": "ubm-001", "title": "X"}), encoding="utf-8")
    monkeypatch.setattr(common, "RECOS_DIR", tmp_path / "recos")

    rhb._rebuild_reco_path_cache(src_id)

    assert set(rhb._RECO_PATH_CACHE[src_id]) == {"ubm-001"}
    rhb._RECO_PATH_CACHE.clear()


# ===== _invalidate_reco_path_cache : repli bootstrap ========================
def test_invalidate_survives_missing_review_render(monkeypatch):
    """Pendant un bootstrap circulaire, `review_render` peut ne pas être
    importable : l'invalidation ne doit pas remonter d'ImportError."""
    import builtins

    rhb._RECO_PATH_CACHE["src-x"] = {}
    real_import = builtins.__import__

    def _no_review_render(name, *args, **kwargs):
        if name == "review_render":
            raise ImportError("cycle en cours de résolution")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _no_review_render)

    rhb._invalidate_reco_path_cache("src-x")

    assert "src-x" not in rhb._RECO_PATH_CACHE

