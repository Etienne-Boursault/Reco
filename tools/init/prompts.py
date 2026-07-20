"""tools.init.prompts — helpers ``input()`` typés pour le wizard.

Sans dépendance externe (cf. ADR 0038, garde-fou « pas de framework
prompt lourd »). Chaque helper accepte un flux d'entrée/sortie pour
faciliter les tests (mock stdin/stdout via ``io.StringIO``).
"""
from __future__ import annotations

import sys
from typing import Callable, TextIO

from . import validators
from .slugify import is_valid_slug, slugify


def _read_line(stdin: TextIO) -> str:
    line = stdin.readline()
    if line == "":  # EOF — évite la boucle infinie en mode piped sans input.
        raise EOFError("Plus d'entrée disponible (stdin clos).")
    return line.rstrip("\n").rstrip("\r")


def _write(stdout: TextIO, text: str) -> None:
    stdout.write(text)
    stdout.flush()


def ask_text(
    label: str,
    *,
    default: str | None = None,
    required: bool = True,
    validator: Callable[[str], bool] | None = None,
    error_msg: str = "Valeur invalide.",
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
    max_attempts: int = 5,
) -> str:
    """Pose une question texte, retente jusqu'à ``max_attempts``."""
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    prompt = f"{label}"
    if default is not None:
        prompt += f" [{default}]"
    prompt += " : "
    for _ in range(max_attempts):
        _write(stdout, prompt)
        raw = _read_line(stdin).strip()
        if not raw and default is not None:
            raw = default
        if not raw:
            if not required:
                return ""
            _write(stdout, "  → champ requis.\n")
            continue
        if validator is not None and not validator(raw):
            _write(stdout, f"  → {error_msg}\n")
            continue
        return raw
    raise ValueError(f"Trop de tentatives invalides pour « {label} ».")


def ask_yes_no(
    label: str,
    *,
    default: bool = True,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
    max_attempts: int = 5,
) -> bool:
    """Question oui/non (FR + EN — ``o``/``y``/``n``)."""
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    hint = "O/n" if default else "o/N"
    for _ in range(max_attempts):
        _write(stdout, f"{label} [{hint}] : ")
        raw = _read_line(stdin).strip().lower()
        if not raw:
            return default
        if raw in {"o", "oui", "y", "yes"}:
            return True
        if raw in {"n", "non", "no"}:
            return False
        _write(stdout, "  → réponds par o/oui ou n/non.\n")
    raise ValueError(f"Trop de tentatives invalides pour « {label} ».")


def ask_list(
    label: str,
    *,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
    max_items: int = 20,
) -> list[str]:
    """Saisie CSV ou prompt-loop simple (vide = stop).

    L'utilisateur peut taper « Kyan, Navo » d'un coup OU saisir un nom
    par ligne (vide pour arrêter).
    """
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    _write(stdout, f"{label}\n")
    _write(stdout, "  (CSV séparé par virgules, OU un par ligne — vide pour finir)\n")
    items: list[str] = []
    for i in range(max_items):
        _write(stdout, f"  #{i + 1} : ")
        raw = _read_line(stdin).strip()
        if not raw:
            break
        if "," in raw:
            for part in raw.split(","):
                p = part.strip()
                if p:
                    items.append(p)
            break  # CSV en un coup → on s'arrête
        items.append(raw)
    return items


def suggest_slug(name: str) -> str:
    """Slug suggéré depuis le nom (passé en defaut du prompt slug)."""
    return slugify(name)


# Validators exposés pour ``ask_text``.
def slug_validator(value: str) -> bool:
    return is_valid_slug(value)


def url_validator(value: str) -> bool:
    return validators.is_valid_url(value)


def hex_validator(value: str) -> bool:
    return validators.is_valid_hex_color(value)


def email_validator(value: str) -> bool:
    return validators.is_valid_email(value)


def reco_prefix_validator(value: str) -> bool:
    return validators.is_valid_reco_prefix(value)


__all__ = [
    "ask_list",
    "ask_text",
    "ask_yes_no",
    "email_validator",
    "hex_validator",
    "reco_prefix_validator",
    "slug_validator",
    "suggest_slug",
    "url_validator",
]
