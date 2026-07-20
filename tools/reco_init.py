"""tools.reco_init — wizard CLI ``reco init`` (cf. ADR 0038, roadmap #19).

Usage interactif :

    python -m tools.reco_init

Usage non-interactif (CI / scripts) :

    python -m tools.reco_init --ci \\
        --slug=mon-podcast --name="Mon Podcast" \\
        --rss-url=https://example.com/rss.xml \\
        --output-dir=/tmp/wizard-demo

Produit ``<output_dir>/<slug>.json`` conforme au schéma Zod de
``src/content.config.ts``.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence, TextIO

from tools.init import WIZARD_VERSION
from tools.init.prompts import (
    ask_list,
    ask_text,
    ask_yes_no,
    email_validator,
    hex_validator,
    reco_prefix_validator,
    slug_validator,
    suggest_slug,
    url_validator,
)
from tools.init.writer import (
    DEFAULT_THEME_COLORS,
    ValidationError,
    WizardAnswers,
    answers_summary,
    validate_answers,
    write_source,
)

DEFAULT_OUTPUT_DIR = Path("src") / "content" / "sources"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="reco init",
        description="Wizard de création d'une source Reco (podcast).",
    )
    p.add_argument(
        "--ci", "--non-interactive",
        dest="ci", action="store_true",
        help="Mode non-interactif (utilise les flags + defaults).",
    )
    p.add_argument("--slug", help="Identifiant de la source (^[a-z0-9-]+$).")
    p.add_argument("--name", "--title", dest="name", help="Nom affiché du podcast.")
    p.add_argument("--rss-url", help="URL du flux RSS.")
    p.add_argument("--site-url", default="", help="Site officiel (optionnel).")
    p.add_argument(
        "--hosts", default="",
        help='Animateurs (CSV — ex. "Kyan,Navo").',
    )
    p.add_argument("--reco-prefix", default="", help="Préfixe ID recos (2-8 chars).")
    p.add_argument(
        "--accent", default=DEFAULT_THEME_COLORS["accent"],
        help=f"Couleur d'accent (hex, défaut {DEFAULT_THEME_COLORS['accent']}).",
    )
    p.add_argument(
        "--bg", default=DEFAULT_THEME_COLORS["bg"],
        help=f"Couleur de fond (hex, défaut {DEFAULT_THEME_COLORS['bg']}).",
    )
    p.add_argument(
        "--public-site-url", default="http://localhost:4321",
        help="SITE_URL publique (à reporter dans .env / hébergeur).",
    )
    p.add_argument("--contact-email", default="", help="Email contact (mailto fallback).")
    p.add_argument(
        "--output-dir", default=str(DEFAULT_OUTPUT_DIR),
        help="Dossier de sortie (défaut src/content/sources).",
    )
    p.add_argument("--force", action="store_true", help="Écrase un fichier existant.")
    p.add_argument(
        "--dry-run", action="store_true",
        help="Affiche le JSON sans rien écrire.",
    )
    p.add_argument(
        "--yes", "-y", action="store_true",
        help="Skip la confirmation finale (mode interactif).",
    )
    p.add_argument("--version", action="version", version=f"reco init {WIZARD_VERSION}")
    return p


def _ci_answers(args: argparse.Namespace) -> WizardAnswers:
    """Construit ``WizardAnswers`` à partir des flags (mode --ci)."""
    missing = [k for k in ("slug", "name", "rss_url") if not getattr(args, k)]
    if missing:
        raise SystemExit(
            f"--ci requiert au minimum --slug, --name, --rss-url (manquent: "
            f"{', '.join(missing)}).",
        )
    hosts = [h.strip() for h in (args.hosts or "").split(",") if h.strip()]
    return WizardAnswers(
        slug=args.slug,
        title=args.name,
        rss_url=args.rss_url,
        site_url=args.site_url or "",
        hosts=hosts,
        reco_prefix=args.reco_prefix or "",
        accent=args.accent,
        bg=args.bg,
        public_site_url=args.public_site_url,
        contact_email=args.contact_email or "",
    )


def _interactive_answers(
    args: argparse.Namespace,
    *,
    stdin: TextIO,
    stdout: TextIO,
) -> WizardAnswers:
    """Pose les questions et renvoie les réponses normalisées."""
    stdout.write(
        f"\n=== Reco — wizard d'initialisation (v{WIZARD_VERSION}) ===\n\n"
        f"Trois questions clés, le reste a des defaults raisonnables.\n\n"
    )
    title = args.name or ask_text(
        "Nom du podcast", required=True,
        stdin=stdin, stdout=stdout,
    )
    slug_default = args.slug or suggest_slug(title)
    slug = ask_text(
        "Slug (id unique, [a-z0-9-])",
        default=slug_default,
        required=True,
        validator=slug_validator,
        error_msg="slug invalide (regex ^[a-z0-9]+(?:-[a-z0-9]+)*$, max 32 chars).",
        stdin=stdin, stdout=stdout,
    )
    rss_url = args.rss_url or ask_text(
        "URL du flux RSS",
        required=True,
        validator=url_validator,
        error_msg="URL invalide (attendu http(s)://…).",
        stdin=stdin, stdout=stdout,
    )
    site_url = args.site_url or ask_text(
        "Site officiel (optionnel)",
        required=False,
        validator=lambda v: v == "" or url_validator(v),
        error_msg="URL invalide.",
        stdin=stdin, stdout=stdout,
    )
    hosts_from_arg = [h.strip() for h in (args.hosts or "").split(",") if h.strip()]
    hosts = hosts_from_arg or ask_list("Animateurs (hosts)", stdin=stdin, stdout=stdout)
    reco_prefix = args.reco_prefix or ask_text(
        "Préfixe ID recos (2-8 chars, optionnel)",
        required=False,
        validator=lambda v: v == "" or reco_prefix_validator(v),
        error_msg="préfixe invalide (^[a-z0-9]{2,8}$).",
        stdin=stdin, stdout=stdout,
    )
    accent = ask_text(
        "Couleur d'accent (hex)",
        default=args.accent,
        required=True,
        validator=hex_validator,
        error_msg="hex invalide (attendu #RRGGBB).",
        stdin=stdin, stdout=stdout,
    )
    bg = ask_text(
        "Couleur de fond (hex)",
        default=args.bg,
        required=True,
        validator=hex_validator,
        error_msg="hex invalide (attendu #RRGGBB).",
        stdin=stdin, stdout=stdout,
    )
    public_site_url = ask_text(
        "SITE_URL public (env)",
        default=args.public_site_url,
        required=True,
        validator=url_validator,
        error_msg="URL invalide.",
        stdin=stdin, stdout=stdout,
    )
    contact_email = ask_text(
        "Email contact (optionnel)",
        required=False,
        validator=lambda v: v == "" or email_validator(v),
        error_msg="email invalide.",
        stdin=stdin, stdout=stdout,
    )
    return WizardAnswers(
        slug=slug,
        title=title,
        rss_url=rss_url,
        site_url=site_url,
        hosts=hosts,
        reco_prefix=reco_prefix,
        accent=accent,
        bg=bg,
        public_site_url=public_site_url,
        contact_email=contact_email,
    )


def _next_steps_msg(path: Path, ans: WizardAnswers) -> str:
    return (
        "\nProchaines étapes :\n"
        f"  1. Vérifie / complète {path}\n"
        f"     (champs optionnels : tagline, description, youtubeChannel, "
        f"avoidBrands, extractionAnchorPatterns…)\n"
        f"  2. Définis SITE_URL={ans.public_site_url} (ou exporte en env).\n"
        "  3. npm install && npm run build\n"
        "  4. (pipeline) python -m tools.fetch_episodes "
        f"--source {ans.slug}\n"
        "  5. npm run test:contrast  # WCAG AA sur ta palette\n"
    )


def run(
    argv: Sequence[str] | None = None,
    *,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
) -> int:
    """Point d'entrée testable (renvoie un code de sortie)."""
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.ci:
            ans = _ci_answers(args)
        else:
            ans = _interactive_answers(args, stdin=stdin, stdout=stdout)
    except EOFError as exc:
        stdout.write(f"\nErreur entrée : {exc}\n")
        return 2

    try:
        validate_answers(ans)
    except ValidationError as exc:
        stdout.write(f"Validation : {exc}\n")
        return 2

    stdout.write("\n" + answers_summary(ans))

    if not args.ci and not args.yes and not args.dry_run:
        if not ask_yes_no(
            "Écrire le fichier ?",
            default=True,
            stdin=stdin, stdout=stdout,
        ):
            stdout.write("Annulé.\n")
            return 1

    output_dir = Path(args.output_dir)
    try:
        path, text = write_source(
            ans, output_dir,
            force=args.force,
            dry_run=args.dry_run,
        )
    except FileExistsError as exc:
        stdout.write(f"Erreur : {exc}\n")
        return 2
    except ValidationError as exc:
        stdout.write(f"Validation : {exc}\n")
        return 2

    if args.dry_run:
        stdout.write(f"\n[DRY-RUN] Fichier qui serait écrit : {path}\n")
        stdout.write(text)
    else:
        stdout.write(f"\n✓ Source écrite : {path}\n")
        stdout.write(_next_steps_msg(path, ans))
    return 0


def main() -> int:  # pragma: no cover — wrapper trivial
    return run()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
