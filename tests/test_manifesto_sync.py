"""Vérifie que `docs/manifeste-ethique.md` et `src/pages/manifeste.astro`
restent synchronisés (titres sections cohérents).

Test relaxé : si la page Astro utilise i18n (`{t('manifesto.x')}`), on se
contente de vérifier qu'on a au moins 4 sections dans le MD. Sinon on
compare strictement les titres H2 (ordre libre).
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _extract_h2_titles_md(md: str) -> list[str]:
    return re.findall(r"^## (.+)$", md, flags=re.MULTILINE)


def _extract_h2_titles_astro(astro: str) -> list[str]:
    return re.findall(r"<h2[^>]*>([^<]+)</h2>", astro)


def test_manifesto_sections_match() -> None:
    md_path = REPO_ROOT / "docs" / "manifeste-ethique.md"
    astro_path = REPO_ROOT / "src" / "pages" / "manifeste.astro"

    md = md_path.read_text(encoding="utf-8")
    astro = astro_path.read_text(encoding="utf-8")

    md_h2 = [t.strip() for t in _extract_h2_titles_md(md)]
    astro_h2 = [t.strip() for t in _extract_h2_titles_astro(astro)]

    # Si la page Astro utilise i18n, les h2 contiennent `{t(...)}` — on
    # bascule sur une vérif souple (nombre minimal de sections MD).
    if "{t(" in astro:
        assert len(md_h2) >= 4, (
            f"Manifesto MD doit avoir >=4 sections, trouve : {md_h2}"
        )
        return

    # Sinon comparaison stricte (ordre libre).
    assert set(md_h2) == set(astro_h2), (
        f"Mismatch sections manifeste: MD={md_h2}, Astro={astro_h2}"
    )
