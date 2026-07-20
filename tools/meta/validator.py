"""tools.meta.validator — Validation du schema `reco-registry.json` (v1).

Pas de dépendance externe : on reste sur des checks structuraux explicites
pour rester aligné avec le schema Zod côté Astro (`src/lib/registry/types.ts`).

H24-2 / parité Zod `.strict()` : tout champ inconnu fait échouer le document.
L24-21 : regex ISO 8601 stricte (heures/minutes/secondes bornées).
M24-5 / M24-6 / M24-7 : bornes (titre, hosts, endpoints).
R-P1-05 : champ `podcasts` (array) accepté comme optionnel pour forward-compat.

Toute évolution incompatible DOIT bumper `REGISTRY_SCHEMA_VERSION` ici ET
côté TS — et être tracée dans ADR 0045.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Iterable

REGISTRY_SCHEMA_VERSION: int = 1

# L24-21 — ISO 8601 strict (HH 00-23, MM/SS 00-59).
_RE_ISO_DT = re.compile(
    r"^\d{4}-\d{2}-\d{2}T(?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d"
    r"(?:\.\d+)?(?:Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)$"
)
_RE_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_RE_LANG = re.compile(r"^[a-z]{2}$")
# M24-7 — chemin absolu /... ou URL https://...
_RE_ENDPOINT = re.compile(
    r"^/[\w./\-?=&%~+:#]*$|^https://[\w./\-?=&%~+:#@!]+$"
)

# M24-5 / M24-6 / B-HIGH-5 — bornes raisonnables (parité TS).
LIMITS = {
    "title_max": 200,
    "tagline_max": 500,
    "host_max": 200,
    "hosts_max": 64,
    "generator_max": 100,
    "url_max": 2048,  # B-HIGH-5 — RFC 7230 §3.1.1 limite recommandée.
}

# Schéma `.strict()` — clés autorisées par objet.
_ALLOWED_KEYS_ROOT = {
    "schemaVersion",
    "siteUrl",
    "podcast",
    "podcasts",  # R-P1-05 — réservé multi-source (Phase 4.5)
    "stats",
    "meta",
    "endpoints",
}
_ALLOWED_KEYS_PODCAST = {
    "title",
    "tagline",
    "rssUrl",
    "hosts",
    "since",
    "language",
}
_ALLOWED_KEYS_STATS = {
    "itemsCount",
    "mentionsCount",
    "episodesCount",
    "guestsCount",
    "lastUpdatedAt",
}
_ALLOWED_KEYS_META = {"generator", "generatedAt", "manifesto"}
_ALLOWED_KEYS_ENDPOINTS = {"ogImage", "sitemap", "search"}


class RegistryValidationError(ValueError):
    """Erreur de validation — agrège toutes les raisons."""

    def __init__(self, errors: Iterable[str]) -> None:
        self.errors: list[str] = list(errors)
        super().__init__("; ".join(self.errors) or "registry invalide")


def _require(cond: bool, msg: str, bag: list[str]) -> None:
    """B-NIT-1 — helper trivial conservé pour la lisibilité (un seul site
    d'appel, mais ce sucre garde la pile de checks plate et symétrique
    avec `_check_*`). Inliner casserait la cohérence du style."""
    if not cond:
        bag.append(msg)


def _check_str(
    value: Any,
    path: str,
    bag: list[str],
    *,
    allow_empty: bool = False,
    max_len: int | None = None,
) -> None:
    if not isinstance(value, str):
        bag.append(f"{path}: chaîne attendue, reçu {type(value).__name__}")
        return
    if not allow_empty and not value.strip():
        bag.append(f"{path}: ne peut pas être vide")
    if max_len is not None and len(value) > max_len:
        bag.append(f"{path}: longueur > {max_len}")


def _check_int_ge0(value: Any, path: str, bag: list[str]) -> None:
    if not isinstance(value, int) or isinstance(value, bool):
        bag.append(f"{path}: entier attendu")
        return
    if value < 0:
        bag.append(f"{path}: entier ≥ 0 attendu")


def _check_url_https(
    value: Any, path: str, bag: list[str], *, max_len: int = LIMITS["url_max"]
) -> None:
    """B-HIGH-5 — borne par défaut 2048 caractères pour les URLs."""
    _check_str(value, path, bag, max_len=max_len)
    if isinstance(value, str) and not value.startswith("https://"):
        bag.append(f"{path}: URL HTTPS attendue")


def _check_url(
    value: Any, path: str, bag: list[str], *, max_len: int = LIMITS["url_max"]
) -> None:
    _check_str(value, path, bag, max_len=max_len)
    if isinstance(value, str) and not (
        value.startswith("http://") or value.startswith("https://")
    ):
        bag.append(f"{path}: URL attendue")


def _check_iso_dt(value: Any, path: str, bag: list[str]) -> None:
    """B-MED-8 — validation stricte : la regex valide la *forme*, puis on
    parse réellement la date avec `datetime.fromisoformat` pour rejeter
    les dates calendaires impossibles (``2026-02-31``, ``2026-13-01``).
    """
    if not isinstance(value, str) or not _RE_ISO_DT.match(value):
        bag.append(f"{path}: ISO 8601 date-time attendu")
        return
    try:
        # fromisoformat accepte un `Z` final depuis Python 3.11.
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        bag.append(f"{path}: ISO 8601 date-time attendu (date invalide)")


def _check_endpoint(value: Any, path: str, bag: list[str]) -> None:
    if not isinstance(value, str):
        bag.append(f"{path}: chaîne attendue")
        return
    if not _RE_ENDPOINT.match(value):
        bag.append(f"{path}: chemin /... ou URL https:// attendu")


def _check_unknown_keys(
    obj: dict, allowed: set[str], path: str, bag: list[str]
) -> None:
    extras = set(obj.keys()) - allowed
    for k in sorted(extras):
        bag.append(f"{path}.{k}: clé inconnue (strict)")


def _check_podcast(podcast: dict, path: str, bag: list[str]) -> None:
    _check_unknown_keys(podcast, _ALLOWED_KEYS_PODCAST, path, bag)
    _check_str(
        podcast.get("title"), f"{path}.title", bag, max_len=LIMITS["title_max"]
    )
    if "tagline" in podcast and podcast["tagline"] is not None:
        _check_str(
            podcast["tagline"],
            f"{path}.tagline",
            bag,
            allow_empty=True,
            max_len=LIMITS["tagline_max"],
        )
    lang = podcast.get("language")
    if not isinstance(lang, str) or not _RE_LANG.match(lang):
        bag.append(f"{path}.language: code ISO 639-1 attendu (2 lettres minuscules)")
    # B-MED-9 — rssUrl doit être HTTPS (protection MITM côté client).
    if "rssUrl" in podcast and podcast["rssUrl"] is not None:
        _check_url_https(podcast["rssUrl"], f"{path}.rssUrl", bag)
    if "since" in podcast and podcast["since"] is not None:
        since = podcast["since"]
        if not isinstance(since, str) or not _RE_DATE.match(since):
            bag.append(f"{path}.since: format AAAA-MM-JJ attendu")
        else:
            # B-MED-8 — strptime stricte pour rejeter les dates impossibles.
            try:
                datetime.strptime(since, "%Y-%m-%d")
            except ValueError:
                bag.append(
                    f"{path}.since: date invalide (calendrier impossible)"
                )
    hosts = podcast.get("hosts", [])
    if not isinstance(hosts, list) or not all(isinstance(h, str) for h in hosts):
        # B-NIT-2 — message 100 % français.
        bag.append(f"{path}.hosts: liste de chaînes attendue")
    else:
        if len(hosts) > LIMITS["hosts_max"]:
            bag.append(f"{path}.hosts: max {LIMITS['hosts_max']} entrées")
        for i, h in enumerate(hosts):
            if len(h) > LIMITS["host_max"]:
                bag.append(f"{path}.hosts[{i}]: longueur > {LIMITS['host_max']}")


def validate_registry(raw: Any) -> dict[str, Any]:
    """Valide un document brut. Lève `RegistryValidationError` ou retourne
    le document tel quel (defaults appliqués)."""
    bag: list[str] = []

    if not isinstance(raw, dict):
        raise RegistryValidationError(["document: objet attendu"])

    _check_unknown_keys(raw, _ALLOWED_KEYS_ROOT, "document", bag)

    version = raw.get("schemaVersion")
    _require(
        version == REGISTRY_SCHEMA_VERSION,
        f"schemaVersion: doit être {REGISTRY_SCHEMA_VERSION} (reçu {version!r})",
        bag,
    )

    _check_url_https(raw.get("siteUrl"), "siteUrl", bag)

    podcast = raw.get("podcast")
    if not isinstance(podcast, dict):
        bag.append("podcast: objet attendu")
    else:
        _check_podcast(podcast, "podcast", bag)

    # R-P1-05 — `podcasts` réservé (Phase 4.5). On valide la forme si présent
    # mais on ne consomme pas (le consumer reste single-podcast en v1).
    if "podcasts" in raw and raw["podcasts"] is not None:
        if not isinstance(raw["podcasts"], list):
            bag.append("podcasts: list attendu")
        else:
            for i, p in enumerate(raw["podcasts"]):
                if not isinstance(p, dict):
                    bag.append(f"podcasts[{i}]: objet attendu")
                else:
                    _check_podcast(p, f"podcasts[{i}]", bag)

    stats = raw.get("stats")
    if not isinstance(stats, dict):
        bag.append("stats: objet attendu")
    else:
        _check_unknown_keys(stats, _ALLOWED_KEYS_STATS, "stats", bag)
        for k in ("itemsCount", "mentionsCount", "episodesCount", "guestsCount"):
            _check_int_ge0(stats.get(k), f"stats.{k}", bag)
        _check_iso_dt(stats.get("lastUpdatedAt"), "stats.lastUpdatedAt", bag)

    meta = raw.get("meta")
    if not isinstance(meta, dict):
        bag.append("meta: objet attendu")
    else:
        _check_unknown_keys(meta, _ALLOWED_KEYS_META, "meta", bag)
        _check_str(
            meta.get("generator"),
            "meta.generator",
            bag,
            max_len=LIMITS["generator_max"],
        )
        _check_iso_dt(meta.get("generatedAt"), "meta.generatedAt", bag)
        if "manifesto" in meta and meta["manifesto"] is not None:
            _check_url(meta["manifesto"], "meta.manifesto", bag)

    # endpoints : objet optionnel, valeurs string-ish acceptées
    endpoints = raw.get("endpoints", {})
    if endpoints is None:
        endpoints = {}
    if not isinstance(endpoints, dict):
        bag.append("endpoints: objet attendu")
    else:
        _check_unknown_keys(endpoints, _ALLOWED_KEYS_ENDPOINTS, "endpoints", bag)
        for k in ("ogImage", "sitemap", "search"):
            if k in endpoints and endpoints[k] is not None:
                _check_endpoint(endpoints[k], f"endpoints.{k}", bag)

    if bag:
        raise RegistryValidationError(bag)

    # Document valide → on renvoie une copie avec endpoints par défaut posé.
    out = dict(raw)
    if out.get("endpoints") is None:
        out["endpoints"] = {}
    return out
