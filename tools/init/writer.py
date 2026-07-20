"""tools.init.writer — construit et écrit le JSON source.

Produit un dictionnaire conforme au schéma Zod de
``src/content.config.ts`` (collection ``sources``) et l'écrit via
``tools.common.atomic_write_text`` pour éviter les fichiers tronqués.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import WIZARD_VERSION
from .slugify import is_valid_slug
from .validators import (
    is_valid_email,
    is_valid_hex_color,
    is_valid_reco_prefix,
    is_valid_url,
)

# Palette par défaut (cf. ``un-bon-moment.json``). L'utilisateur ne
# personnalise que ``accent`` + ``bg`` dans le wizard ; les autres
# valeurs sont des defaults vérifiés WCAG AA sur ``#0e0e10`` / ``#f6f4ee``.
DEFAULT_THEME_COLORS: dict[str, str] = {
    "bg": "#0e0e10",
    "surface": "#17171c",
    "text": "#f6f4ee",
    "muted": "#9a99a3",
    "accent": "#5eead4",
    "accentText": "#0e0e10",
}


@dataclass(slots=True)
class WizardAnswers:
    """Réponses normalisées du wizard.

    Champs optionnels = ``""`` ou ``None`` → omis du JSON final si vides
    (le schéma Zod marque ces champs ``.optional()``).
    """

    slug: str
    title: str
    rss_url: str
    site_url: str = ""              # ``website`` côté Zod
    hosts: list[str] = field(default_factory=list)
    reco_prefix: str = ""
    accent: str = DEFAULT_THEME_COLORS["accent"]
    bg: str = DEFAULT_THEME_COLORS["bg"]
    public_site_url: str = "http://localhost:4321"  # SITE_URL env (non écrit)
    contact_email: str = ""         # idem (non écrit dans le JSON source)


class ValidationError(ValueError):
    """Levée si une réponse ne passe pas la validation pré-écriture."""


def validate_answers(ans: WizardAnswers) -> None:
    """Garde-fou avant écriture. Lève ``ValidationError`` au premier souci."""
    if not is_valid_slug(ans.slug):
        raise ValidationError(
            f"slug invalide « {ans.slug} » — attendu ^[a-z0-9]+(?:-[a-z0-9]+)*$, "
            f"max 32 chars."
        )
    if not ans.title.strip():
        raise ValidationError("title vide.")
    if not is_valid_url(ans.rss_url):
        raise ValidationError(f"rssUrl invalide « {ans.rss_url} » — attendu http(s)://…")
    if ans.site_url and not is_valid_url(ans.site_url):
        raise ValidationError(f"website invalide « {ans.site_url} »")
    if not is_valid_hex_color(ans.accent):
        raise ValidationError(f"accent invalide « {ans.accent} » — attendu #RRGGBB.")
    if not is_valid_hex_color(ans.bg):
        raise ValidationError(f"bg invalide « {ans.bg} » — attendu #RRGGBB.")
    if ans.reco_prefix and not is_valid_reco_prefix(ans.reco_prefix):
        raise ValidationError(
            f"recoPrefix invalide « {ans.reco_prefix} » — attendu ^[a-z0-9]{{2,8}}$."
        )
    if ans.contact_email and not is_valid_email(ans.contact_email):
        raise ValidationError(f"email invalide « {ans.contact_email} »")


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z",
    )


def build_source_config(
    ans: WizardAnswers,
    *,
    created_at: str | None = None,
) -> dict[str, Any]:
    """Construit le dict prêt à être sérialisé en JSON source."""
    validate_answers(ans)

    theme_colors = dict(DEFAULT_THEME_COLORS)
    theme_colors["accent"] = ans.accent
    theme_colors["bg"] = ans.bg

    data: dict[str, Any] = {
        "id": ans.slug,
        "title": ans.title,
        "hosts": list(ans.hosts),
        "rssUrl": ans.rss_url,
        "theme": {
            "fontDisplay": "Reco Display",
            "fontBody": "Reco Body",
            "colors": theme_colors,
        },
        "schemaVersion": 1,
    }
    if ans.site_url:
        data["website"] = ans.site_url
    if ans.reco_prefix:
        data["recoPrefix"] = ans.reco_prefix
        # Cohérence : ``siteColorAccent`` (pipeline Python) doit suivre
        # ``theme.colors.accent`` quand un préfixe est défini.
        data["siteColorAccent"] = ans.accent

    # Métadonnées de provenance (forward-compat — Zod ignore les clés
    # inconnues seulement si on les place sous une clé valide ; on les
    # met dans un objet « __wizard__ » qui passerait le schéma ``passthrough``
    # mais Astro lit en mode strict. On évite donc les clés non-schématisées
    # et on enregistre la trace dans un sidecar.
    _ = (created_at or _utcnow_iso())  # réservé pour usage futur (sidecar)
    return data


def serialize(data: dict[str, Any]) -> str:
    """JSON UTF-8, indent 2, accents conservés, clés triées (idempotent)."""
    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def write_source(
    ans: WizardAnswers,
    output_dir: Path,
    *,
    force: bool = False,
    dry_run: bool = False,
    created_at: str | None = None,
) -> tuple[Path, str]:
    """Écrit ``<output_dir>/<slug>.json``.

    Renvoie ``(path, serialized_text)``. En ``dry_run``, ne crée pas le
    fichier. Lève ``FileExistsError`` si le fichier existe et ``force=False``.
    """
    data = build_source_config(ans, created_at=created_at)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{ans.slug}.json"
    text = serialize(data)
    if path.exists() and not force and not dry_run:
        raise FileExistsError(
            f"{path} existe déjà — utilise --force pour écraser."
        )
    if dry_run:
        return path, text
    # Import paresseux : ``tools.common`` charge logging/etc.
    from tools.common import atomic_write_text  # noqa: PLC0415

    atomic_write_text(path, text)
    return path, text


def answers_summary(ans: WizardAnswers) -> str:
    """Résumé human-readable pour la confirmation Y/n du wizard."""
    d = asdict(ans)
    lines = [
        "Résumé :",
        f"  slug           : {d['slug']}",
        f"  title          : {d['title']}",
        f"  rssUrl         : {d['rss_url']}",
        f"  website        : {d['site_url'] or '(vide)'}",
        f"  hosts          : {', '.join(d['hosts']) or '(vide)'}",
        f"  recoPrefix     : {d['reco_prefix'] or '(vide)'}",
        f"  theme.accent   : {d['accent']}",
        f"  theme.bg       : {d['bg']}",
        f"  SITE_URL (env) : {d['public_site_url']}",
        f"  contact email  : {d['contact_email'] or '(vide)'}",
    ]
    return "\n".join(lines) + "\n"


WIZARD_TAG = f"reco init wizard v{WIZARD_VERSION}"


__all__ = [
    "DEFAULT_THEME_COLORS",
    "ValidationError",
    "WIZARD_TAG",
    "WizardAnswers",
    "answers_summary",
    "build_source_config",
    "serialize",
    "validate_answers",
    "write_source",
]
