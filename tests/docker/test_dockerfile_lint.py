"""Lint statique des fichiers Docker (P3.18, ADR 0037).

Tests autonomes — ne lancent pas `docker build`. Validations :
 - Dockerfile multistage (>=3 FROM, healthcheck, expose, entrypoint).
 - .dockerignore exclut secrets et caches.
 - docker-compose.yml structure (services, healthcheck, profile pipeline).
 - entrypoint.sh routes attendues.
 - .env.example couvre les variables Phase 2.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _read(name: str) -> str:
    p = ROOT / name
    if not p.exists():
        pytest.fail(f"Fichier manquant : {name}")
    return p.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Dockerfile
# ---------------------------------------------------------------------------
def test_dockerfile_multistage():
    """3 stages nommés : node-builder, python-builder, runtime."""
    dockerfile = _read("Dockerfile")
    stages = re.findall(r"^FROM\s+\S+\s+AS\s+(\S+)", dockerfile, re.MULTILINE)
    assert "node-builder" in stages, f"stage node-builder manquant ; trouvé : {stages}"
    assert "python-builder" in stages, f"stage python-builder manquant ; trouvé : {stages}"
    assert "runtime" in stages, f"stage runtime manquant ; trouvé : {stages}"
    assert len(stages) >= 3, f"attendu >=3 stages, trouvé {len(stages)}"


def test_dockerfile_runtime_is_slim():
    """L'image runtime utilise python:3.12-slim (pas full)."""
    dockerfile = _read("Dockerfile")
    # Cherche le FROM ... AS runtime
    m = re.search(r"^FROM\s+(\S+)\s+AS\s+runtime", dockerfile, re.MULTILINE)
    assert m, "stage runtime introuvable"
    assert "slim" in m.group(1), f"runtime devrait être slim ; trouvé : {m.group(1)}"


def test_dockerfile_healthcheck_present():
    dockerfile = _read("Dockerfile")
    assert "HEALTHCHECK" in dockerfile, "HEALTHCHECK requis pour orchestration"


def test_dockerfile_expose_review_port():
    dockerfile = _read("Dockerfile")
    assert re.search(r"^EXPOSE\b.*\b8000\b", dockerfile, re.MULTILINE), \
        "EXPOSE 8000 requis (review_server)"


def test_dockerfile_entrypoint_and_cmd():
    dockerfile = _read("Dockerfile")
    assert "ENTRYPOINT" in dockerfile
    assert "CMD" in dockerfile


def test_dockerfile_no_secret_copy():
    """Aucun COPY ne doit embarquer .env / tools/.env."""
    dockerfile = _read("Dockerfile")
    for line in dockerfile.splitlines():
        stripped = line.strip()
        if stripped.startswith("COPY"):
            assert ".env" not in stripped or "example" in stripped.lower(), \
                f"COPY suspect (secret ?) : {stripped}"


def test_dockerfile_copies_venv_from_builder():
    dockerfile = _read("Dockerfile")
    assert "--from=python-builder" in dockerfile
    assert "--from=node-builder" in dockerfile


# ---------------------------------------------------------------------------
# .dockerignore
# ---------------------------------------------------------------------------
def test_dockerignore_excludes_secrets_and_caches():
    content = _read(".dockerignore")
    must_exclude = [
        ".env",
        "tools/.env",
        "node_modules",
        "dist",
        ".git",
        ".venv",
        "tools/.venv",
        "__pycache__",
    ]
    for needle in must_exclude:
        assert needle in content, f".dockerignore devrait exclure : {needle}"


def test_dockerignore_keeps_env_example():
    content = _read(".dockerignore")
    assert "!.env.example" in content, "garder .env.example (template public)"


# ---------------------------------------------------------------------------
# docker-compose.yml
# ---------------------------------------------------------------------------
def test_compose_services():
    content = _read("docker-compose.yml")
    for svc in ("reco-review:", "reco-site:", "reco-pipeline:"):
        assert svc in content, f"service manquant : {svc}"


def test_compose_pipeline_is_profile_opt_in():
    """reco-pipeline ne doit pas démarrer par défaut (profile)."""
    content = _read("docker-compose.yml")
    # Cherche le bloc reco-pipeline jusqu'au prochain service ou EOF
    m = re.search(r"^  reco-pipeline:\s*\n((?:  .+\n?|\s*\n)*)", content, re.MULTILINE)
    assert m, "bloc reco-pipeline introuvable"
    assert "profiles:" in m.group(1), "reco-pipeline doit avoir profiles: [pipeline]"


def test_compose_review_has_healthcheck():
    content = _read("docker-compose.yml")
    m = re.search(r"^  reco-review:\s*\n((?:  .+\n?|\s*\n)*?)(?=^  \S|\Z)",
                  content, re.MULTILINE)
    assert m, "bloc reco-review introuvable"
    assert "healthcheck:" in m.group(1)


def test_compose_ports_mapping():
    content = _read("docker-compose.yml")
    assert '"8000:8000"' in content, "port review_server 8000 doit être mappé"
    assert '"4321:4321"' in content, "port site statique 4321 doit être mappé"


def test_compose_volumes_persist_caches():
    content = _read("docker-compose.yml")
    assert "./tools/output:/app/tools/output" in content
    assert "./src/content:/app/src/content" in content


# ---------------------------------------------------------------------------
# entrypoint.sh
# ---------------------------------------------------------------------------
def test_entrypoint_routes():
    content = _read("docker/entrypoint.sh")
    for route in ("review)", "serve)", "pipeline)", "shell"):
        assert route in content, f"route entrypoint manquante : {route}"


def test_entrypoint_uses_review_launcher():
    """Le route 'review' doit passer par le launcher qui patche bind 0.0.0.0."""
    content = _read("docker/entrypoint.sh")
    assert "review_launcher.py" in content, \
        "review doit passer par docker/review_launcher.py (bind 0.0.0.0)"


def test_entrypoint_serve_binds_all():
    content = _read("docker/entrypoint.sh")
    # http.server doit écouter sur 0.0.0.0 sinon inaccessible hors conteneur.
    assert "--bind 0.0.0.0" in content or "--bind=0.0.0.0" in content


def test_entrypoint_has_shebang_and_strict():
    content = _read("docker/entrypoint.sh")
    assert content.startswith("#!/usr/bin/env sh"), "shebang sh requis"
    assert "set -eu" in content, "set -eu requis (strict mode)"


# ---------------------------------------------------------------------------
# review_launcher.py
# ---------------------------------------------------------------------------
def test_review_launcher_patches_httpserver():
    content = _read("docker/review_launcher.py")
    assert "HTTPServer.__init__" in content
    assert "0.0.0.0" in content
    # Import doit venir APRES le patch.
    patch_idx = content.find("HTTPServer.__init__ = ")
    import_idx = content.find("import review_server")
    assert patch_idx > 0 and import_idx > 0 and patch_idx < import_idx, \
        "le monkeypatch HTTPServer doit précéder `import review_server`"


# ---------------------------------------------------------------------------
# .env.example
# ---------------------------------------------------------------------------
def test_env_example_covers_phase2_vars():
    content = _read(".env.example")
    required = [
        "SITE_URL",
        "RECO_SOURCE",
        "REPORTS_SECRET",
        "REPORTS_IP_SALT",
        "TMDB_API_KEY",
        "SPOTIFY_CLIENT_ID",
        "SPOTIFY_CLIENT_SECRET",
    ]
    for var in required:
        assert re.search(rf"^{var}=", content, re.MULTILINE), \
            f"variable manquante dans .env.example : {var}"


def test_env_example_has_no_real_secrets():
    """Les valeurs après `=` doivent être vides ou des placeholders évidents."""
    content = _read(".env.example")
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        # Tolère uniquement vide ou URL/valeur de doc explicite.
        if value and not value.startswith("http://localhost") and value != "un-bon-moment":
            pytest.fail(f"valeur suspecte dans .env.example : {line}")


# ---------------------------------------------------------------------------
# Makefile
# ---------------------------------------------------------------------------
def test_makefile_targets():
    content = _read("Makefile")
    for target in ("build:", "up:", "down:", "pipeline:", "shell:", "test:"):
        assert target in content, f"cible Makefile manquante : {target}"
