"""Tests interactifs (stdin scripté) pour ``tools.reco_init``."""
from __future__ import annotations

import io
import json
from pathlib import Path

from tools.reco_init import run


def test_interactive_full_session(tmp_path: Path) -> None:
    # Réponses dans l'ordre des questions du wizard :
    # 1. Nom, 2. Slug (default), 3. RSS, 4. site (vide),
    # 5. hosts (CSV), 6. recoPrefix (vide), 7. accent (default),
    # 8. bg (default), 9. SITE_URL (default), 10. email (vide),
    # 11. confirmation o
    answers = "\n".join([
        "Mon Podcast",                    # nom
        "",                               # slug → default suggéré (mon-podcast)
        "https://example.com/rss",        # rss
        "",                               # site optionnel
        "Alice, Bob",                     # hosts CSV
        "",                               # recoPrefix optionnel
        "",                               # accent default
        "",                               # bg default
        "",                               # SITE_URL default
        "",                               # email optionnel
        "o",                              # confirmation
        "",                               # newline final
    ])
    stdin = io.StringIO(answers)
    stdout = io.StringIO()
    code = run([f"--output-dir={tmp_path}"], stdin=stdin, stdout=stdout)
    assert code == 0, stdout.getvalue()
    path = tmp_path / "mon-podcast.json"
    assert path.exists()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["id"] == "mon-podcast"
    assert data["title"] == "Mon Podcast"
    assert data["hosts"] == ["Alice", "Bob"]
    assert "Prochaines étapes" in stdout.getvalue()


def test_interactive_user_cancels(tmp_path: Path) -> None:
    answers = "\n".join([
        "Mon Podcast",
        "",                               # slug default
        "https://example.com/rss",
        "",
        "",                               # hosts vide
        "",
        "",
        "",
        "",
        "",
        "n",                              # refuse l'écriture
        "",
    ])
    stdin = io.StringIO(answers)
    stdout = io.StringIO()
    code = run([f"--output-dir={tmp_path}"], stdin=stdin, stdout=stdout)
    assert code == 1
    assert not (tmp_path / "mon-podcast.json").exists()
    assert "Annulé" in stdout.getvalue()
