"""apply_links.py — Écrit les liens trouvés par les agents dans le champ `links`.

Sépare la RECHERCHE (agents + WebSearch) de l'ÉCRITURE (déterministe, validée),
comme apply_verdicts.py sépare décision et mutation. Les agents ne touchent
JAMAIS les JSON de recos à la main : ils produisent un fichier de liens, ce
script l'applique.

Usage :
    python tools/apply_links.py --links liens.json --guid <episodeGuid>
    python tools/apply_links.py --links liens.json --guid <guid> --dry-run
    python tools/apply_links.py --links liens.json --guid <guid> --source autre

Format d'entrée :
    { "ubm-3198": [ {"label": "Arte.tv", "url": "https://...",
                     "kind": "streaming", "ethics": "indie"}, ... ], ... }

Garde-fous :
- N'écrit que sur les recos `status=validated` de l'épisode --guid.
- URL : https:// obligatoire. Un host AVOID_DOMAINS (Amazon / Bolloré /
  Editis-Hachette) est ACCEPTÉ mais forcé en `ethics: "avoid"` → affiché avec
  le badge d'avertissement. Supprimer laisserait la reco sans lien utile, ce
  qui est pire pour le lecteur (arbitrage produit du 2026-07-19).
- `kind` et `ethics` validés contre l'enum du schéma Zod (content.config.ts).
- Refuse d'écraser des `links` déjà non vides sauf --force.
- Vérification HTTP de chaque URL (cf. link_check). Une URL bien formée mais
  fabriquée est indiscernable d'une vraie à la lecture : seule la requête
  tranche. --no-verify la désactive (dépannage hors ligne uniquement).
- Jamais de suppression de fichier.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import urlparse

# Permettre l'exécution directe `python tools/apply_links.py`.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import read_json, recos_dir_for, write_json_if_changed  # noqa: E402
from link_check import ProbeResult, verify_url  # noqa: E402

DEFAULT_SOURCE = "un-bon-moment"

VALID_KINDS = frozenset({"buy", "borrow", "streaming", "info", "official", "social"})
VALID_ETHICS = frozenset({"indie", "neutral", "avoid"})

# Miroir de src/data/merchants.ts::AVOID_DOMAINS (politique éditoriale).
AVOID_DOMAINS = frozenset({
    "amazon.fr", "amazon.com",
    "canalplus.com", "cnews.fr", "europe1.fr", "parismatch.com", "lejdd.fr",
    "editis.com", "hachette.fr",
})


def host_avoided(host: str) -> bool:
    """True si le host est un domaine évité (match exact ou sous-domaine)."""
    host = host.lower().lstrip(".")
    return any(host == d or host.endswith("." + d) for d in AVOID_DOMAINS)


def validate_link(entry: object) -> tuple[dict | None, str]:
    """Renvoie (lien normalisé, "") ou (None, raison du rejet)."""
    if not isinstance(entry, dict):
        return None, "entrée non-objet"
    label = str(entry.get("label") or "").strip()
    url = str(entry.get("url") or "").strip()
    if not label:
        return None, "label vide"
    if not url.lower().startswith("https://"):
        return None, f"URL non-https ({url[:60]})"
    try:
        host = urlparse(url).hostname or ""
    except ValueError:
        return None, f"URL illisible ({url[:60]})"
    if not host:
        return None, f"host vide ({url[:60]})"
    kind = entry.get("kind") or "info"
    ethics = entry.get("ethics") or "neutral"
    # Un lien Amazon/Bolloré est ACCEPTÉ (utile en dernier recours quand
    # l'œuvre n'est disponible que là) mais forcé en `avoid`.
    if host_avoided(host):
        ethics = "avoid"
    if kind not in VALID_KINDS:
        return None, f"kind invalide : {kind}"
    if ethics not in VALID_ETHICS:
        return None, f"ethics invalide : {ethics}"
    return {"label": label, "url": url, "kind": kind, "ethics": ethics}, ""


def index_recos_by_id(source_id: str, guid: str) -> dict[str, Path]:
    """Les recos de l'épisode `guid`, indexées par identifiant."""
    by_id: dict[str, Path] = {}
    for path in sorted(recos_dir_for(source_id).glob("*.json")):
        reco = read_json(path)
        if reco.get("episodeGuid") == guid:
            by_id[str(reco.get("id", ""))] = path
    return by_id


def _check(link: dict, timeout: float, cache: dict[str, ProbeResult],
           stats: dict[str, int]) -> bool:
    """Sonde le lien et journalise. False si l'URL est morte."""
    result = verify_url(link["url"], timeout, cache)
    if result.verdict == "dead":
        print(f"  MORT {link['url'][:70]} — {result.detail}")
        stats["dead"] += 1
        return False
    if result.verdict == "unknown":
        print(f"  ~ NON VÉRIFIÉ {link['url'][:60]} — {result.detail}")
        stats["unverified"] += 1
        return True
    # Titre affiché pour relecture humaine : un lien vivant peut pointer vers
    # la mauvaise œuvre, et seul l'œil le voit.
    print(f"     cible « {result.title[:60]} »  (label : {link['label'][:40]})")
    return True


def apply_links(payload: dict, source_id: str, guid: str, *,
                dry_run: bool = False, force: bool = False,
                verify: bool = True, timeout: float = 15.0) -> dict[str, int]:
    """Applique `payload` et renvoie les compteurs."""
    by_id = index_recos_by_id(source_id, guid)
    stats = {"written": 0, "links": 0, "rejected": 0, "dead": 0,
             "unverified": 0, "missing": 0, "not_validated": 0,
             "skipped_existing": 0}
    cache: dict[str, ProbeResult] = {}

    for rid, entries in sorted(payload.items()):
        path = by_id.get(rid)
        if path is None:
            print(f"  MANQUANT {rid} (pas dans l'épisode {guid})")
            stats["missing"] += 1
            continue
        reco = read_json(path)
        if reco.get("status") != "validated":
            print(f"  SKIP {rid}: status={reco.get('status')} (non validée)")
            stats["not_validated"] += 1
            continue
        if (reco.get("links") or []) and not force:
            print(f"  SKIP {rid}: links déjà présents (--force pour écraser)")
            stats["skipped_existing"] += 1
            continue

        clean: list[dict] = []
        for entry in entries or []:
            link, why = validate_link(entry)
            if link is None:
                print(f"  REJET {rid}: {why}")
                stats["rejected"] += 1
                continue
            if verify and not _check(link, timeout, cache, stats):
                continue
            clean.append(link)

        if not clean:
            print(f"  VIDE {rid}: aucun lien valide → inchangé")
            continue
        reco["links"] = clean
        stats["links"] += len(clean)
        stats["written"] += 1
        if dry_run:
            print(f"  DRY {rid}: {len(clean)} lien(s)")
        else:
            write_json_if_changed(path, reco)
            print(f"  OK  {rid}: {len(clean)} lien(s)")
    return stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--links", required=True)
    parser.add_argument("--guid", required=True)
    parser.add_argument("--source", default=DEFAULT_SOURCE)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true",
                        help="Écrase des links déjà présents.")
    parser.add_argument("--no-verify", action="store_true",
                        help="Saute la vérification HTTP (dépannage hors "
                             "ligne). Une URL fabriquée passera.")
    parser.add_argument("--timeout", type=float, default=15.0)
    args = parser.parse_args(argv)

    if args.no_verify:
        print("!! Vérification HTTP DÉSACTIVÉE — les URL ne sont pas contrôlées.\n")

    payload = json.loads(Path(args.links).read_text(encoding="utf-8"))
    stats = apply_links(payload, args.source, args.guid,
                        dry_run=args.dry_run, force=args.force,
                        verify=not args.no_verify, timeout=args.timeout)
    print(f"\nRésumé {args.guid}: {stats}")
    return 1 if (stats["missing"] or stats["rejected"] or stats["dead"]) else 0


if __name__ == "__main__":  # pragma: no cover - point d'entrée CLI
    sys.exit(main())
