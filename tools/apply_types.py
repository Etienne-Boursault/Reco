"""apply_types.py — Applique la reclassification des types « autre » des recos.

Sépare l'ANALYSE (agents + lecture des liens → `tools/output/types_proposes.json`)
de l'ÉCRITURE (déterministe, validée, rejouable), comme `apply_links.py` et
`apply_verdicts.py`. Aucun agent ne touche les JSON de recos à la main.

Usage :
    python tools/apply_types.py                          # dry-run (défaut)
    python tools/apply_types.py --apply
    python tools/apply_types.py --apply --json rapport.json
    python tools/apply_types.py --only certain --apply

Ce qui est appliqué :
  1. les ARBITRAGES rendus par l'utilisateur (constante `ARBITRAGES` ci-dessous),
     qui PRIMENT sur `typesProposes` du fichier de propositions ;
  2. les propositions `confiance: "certain"` qui ne relèvent d'aucune famille
     d'arbitrage gelée.

Ce qui ne l'est PAS :
  - les propositions `confiance: "inference"` sans arbitrage (soumises à
    l'utilisateur, listées dans le rapport) ;
  - les familles encore ouvertes (`FAMILLES_GELEES`), y compris leurs
    propositions `certain` : l'utilisateur a demandé qu'elles restent en l'état ;
  - toute reco dont le `status` n'est pas `validated`.

Garde-fous :
- SEUL le champ `types` est réécrit ; le reste du document est ré-sérialisé à
  l'identique (mêmes clés triées, même indentation, même encodage).
- Refus d'écrire si les `types` du fichier ne correspondent plus aux
  `typesActuels` de la proposition (fichier modifié depuis la génération).
- `types` cible non vide, et chaque valeur validée contre l'enum `recoType`
  de `src/content.config.ts`.
- Jamais de suppression de fichier, jamais d'écriture hors `src/content/recos/`.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

# Permettre l'exécution directe `python tools/apply_types.py`.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import RECOS_DIR, read_json, write_json_if_changed

DEFAULT_PROPOSALS: Path = Path(__file__).resolve().parent / "output" / "types_proposes.json"

# Miroir de l'enum `recoType` de `src/content.config.ts` (15 valeurs depuis
# l'ajout d'`application` le 2026-07-31). Une valeur absente d'ici est refusée
# à l'écriture : le contenu doit rester validable par `astro check`.
VALID_TYPES: frozenset[str] = frozenset({
    "film", "serie", "livre", "bd",
    "musique", "album", "podcast", "jeu",
    "spectacle", "lieu", "artiste", "video", "chaine",
    "application", "autre",
})

# --- Arbitrages rendus par l'utilisateur le 2026-07-31 ----------------------
# Ils PRIMENT sur `typesProposes`. Chaque famille porte son motif : sans lui,
# la règle se relit comme une liste d'exceptions arbitraires.
ARBITRAGES: dict[str, dict] = {
    "court_metrage_en_ligne": {
        "types": ("film",),
        "motif": (
            "Le critère est la NATURE de l'œuvre, pas le canal de diffusion. "
            "`video` reste réservé à ce qui n'existe QUE comme vidéo en ligne "
            "(vlog, sketch, essai vidéo)."
        ),
        "ids": ("ubm-0633", "ubm-0777", "ubm-1228", "ubm-0815"),
    },
    "compte_social": {
        "types": ("artiste",),
        "motif": "Un compte TikTok/Instagram récurrent reste un créateur de contenu, "
                 "donc un artiste.",
        "ids": ("ubm-0489", "ubm-0642", "ubm-0811", "ubm-1014",
                "ubm-1685", "ubm-2184", "ubm-3032"),
    },
    "emission_tv": {
        "types": ("video",),
        "motif": "Une émission TV récurrente sans fiction ne va pas dans `serie`, "
                 "réservé à la fiction.",
        "ids": ("ubm-0208", "ubm-0527", "ubm-0656", "ubm-2100", "ubm-2267"),
    },
    "application": {
        "types": ("application",),
        "motif": "Applications et outils : le type `application` a été créé pour eux "
                 "le 2026-07-31.",
        "ids": ("ubm-0708", "ubm-0826", "ubm-1094", "ubm-1454",
                "ubm-1456", "ubm-2389", "ubm-2633", "ubm-2692"),
    },
}

ARBITRAGE_BY_ID: dict[str, str] = {
    reco_id: famille
    for famille, rule in ARBITRAGES.items()
    for reco_id in rule["ids"]
}

# Familles d'arbitrage encore OUVERTES : l'utilisateur a demandé qu'elles
# restent en l'état, y compris leurs propositions `certain`.
FAMILLES_GELEES: frozenset[str] = frozenset({
    "categorie_absente", "musique_vs_album", "oeuvre_non_identifiee",
})


@dataclass(frozen=True)
class Decision:
    """Ce que le script fait — ou refuse de faire — d'une proposition."""

    reco_id: str
    title: str
    current: tuple[str, ...]
    target: tuple[str, ...]
    origin: str          # "arbitrage:<famille>" | "certain" | "inference" | "—"
    applied: bool
    reason: str
    justification: str = ""
    # Ce que la proposition demandait, même quand on ne l'applique pas : c'est
    # cette colonne que l'utilisateur arbitre pour les `inference` laissées.
    proposed: tuple[str, ...] = ()

    def as_dict(self) -> dict:
        return {
            "id": self.reco_id,
            "titre": self.title,
            "typesActuels": list(self.current),
            "typesProposes": list(self.proposed),
            "typesCibles": list(self.target),
            "origine": self.origin,
            "applique": self.applied,
            "motif": self.reason,
            "justification": self.justification,
        }


@dataclass
class Plan:
    """Le plan complet : décisions + index des documents chargés."""

    decisions: list[Decision] = field(default_factory=list)
    docs: dict[str, tuple[Path, dict]] = field(default_factory=dict)

    @property
    def applied(self) -> list[Decision]:
        return [d for d in self.decisions if d.applied]

    @property
    def skipped(self) -> list[Decision]:
        return [d for d in self.decisions if not d.applied]


def index_recos(root: Path) -> dict[str, tuple[Path, dict]]:
    """Indexe les recos par identifiant : {id: (chemin, document)}."""
    by_id: dict[str, tuple[Path, dict]] = {}
    for path in sorted(root.rglob("*.json")):
        doc = read_json(path)
        reco_id = doc.get("id")
        if reco_id:
            by_id[reco_id] = (path, doc)
    return by_id


def frozen_families(proposals: dict) -> dict[str, str]:
    """{id de reco: nom de famille} pour les familles encore ouvertes."""
    familles = proposals.get("famillesDArbitrage") or {}
    return {
        reco_id: nom
        for nom, bloc in familles.items() if nom in FAMILLES_GELEES
        for reco_id in bloc.get("ids", ())
    }


def decide(prop: dict, doc: dict, frozen: dict[str, str], only: str,
           validated: frozenset[str] = frozenset()) -> Decision:
    """Décide du sort d'une proposition. Pure : ne lit ni n'écrit aucun fichier.

    `validated` contient les ids que l'utilisateur a validés un par un. Ils
    échappent au SEUL refus « inference non arbitrée » — pas aux autres : une
    reco `discarded`, désynchronisée, appartenant à une famille d'arbitrage
    encore ouverte ou dont les types cibles sortent du schéma reste refusée
    même validée. Une validation humaine ne rend pas une donnée cohérente.
    """
    reco_id = prop["id"]
    current = tuple(doc.get("types") or ())
    base = dict(
        reco_id=reco_id,
        title=prop.get("title") or doc.get("title") or "",
        current=current,
        justification=prop.get("justification", ""),
        proposed=tuple(prop["typesProposes"]),
    )

    def refus(origin: str, reason: str) -> Decision:
        return Decision(**base, target=current, origin=origin, applied=False, reason=reason)

    status = doc.get("status")
    if status != "validated":
        return refus("—", f"status « {status} » — hors périmètre")
    if sorted(current) != sorted(prop["typesActuels"]):
        return refus("—", "désynchronisé : `types` a changé depuis la génération "
                          f"(proposition : {list(prop['typesActuels'])})")

    famille = ARBITRAGE_BY_ID.get(reco_id)
    if famille is not None:
        origin = f"arbitrage:{famille}"
        target = tuple(ARBITRAGES[famille]["types"])
    elif reco_id in frozen:
        return refus("famille ouverte", f"famille « {frozen[reco_id]} » — reste en l'état")
    elif prop["confiance"] == "certain":
        origin, target = "certain", tuple(prop["typesProposes"])
    elif reco_id in validated:
        # L'utilisateur a validé CETTE reco nommément (case à cocher du tableau
        # de curation, ou relecture manuelle de la liste `inference`). Sa
        # décision explicite prime sur le refus automatique — c'est le seul
        # chemin par lequel une `inference` s'applique.
        origin, target = "validé-main", tuple(prop["typesProposes"])
    else:
        return refus("inference", "inference non arbitrée — soumise à l'utilisateur")

    if only != "all" and not origin.startswith(only):
        return refus(origin, f"hors périmètre --only {only}")

    invalides = [t for t in target if t not in VALID_TYPES]
    if invalides:
        return refus(origin, f"types cibles hors schéma : {invalides}")
    if not target:
        return refus(origin, "types cibles vides — un tableau non vide est requis")
    if sorted(target) == sorted(current):
        return refus(origin, "déjà conforme")

    return Decision(**base, target=target, origin=origin, applied=True, reason="")


def build_plan(proposals: dict, recos: dict[str, tuple[Path, dict]], only: str,
               validated: frozenset[str] = frozenset()) -> Plan:
    """Construit le plan complet à partir des propositions et du contenu."""
    plan = Plan(docs=recos)
    frozen = frozen_families(proposals)
    for prop in proposals["propositions"]:
        entry = recos.get(prop["id"])
        if entry is None:
            plan.decisions.append(Decision(
                reco_id=prop["id"], title=prop.get("title", ""), current=(), target=(),
                origin="—", applied=False, reason="reco absente du contenu",
                justification=prop.get("justification", ""),
                proposed=tuple(prop["typesProposes"]),
            ))
            continue
        plan.decisions.append(decide(prop, entry[1], frozen, only, validated))
    return plan


def parse_ids(raw: str | None) -> frozenset[str]:
    """« a,b,c » ou « @fichier » → ensemble d'ids. Même convention que les
    `--exclude-ids` des scripts d'enrichissement, pour ne pas obliger à
    retenir deux syntaxes."""
    if not raw:
        return frozenset()
    if raw.startswith("@"):
        raw = Path(raw[1:]).read_text(encoding="utf-8")
    return frozenset(p.strip() for p in raw.replace("\n", ",").split(",") if p.strip())


def type_distribution(recos: dict[str, tuple[Path, dict]]) -> dict[str, int]:
    """Répartition des types sur les recos actives (`status == validated`)."""
    counter: Counter[str] = Counter()
    for _path, doc in recos.values():
        if doc.get("status") == "validated":
            counter.update(doc.get("types") or ())
    return dict(sorted(counter.items(), key=lambda kv: (-kv[1], kv[0])))


def execute(plan: Plan, *, dry_run: bool) -> int:
    """Écrit les `types` retenus. En dry-run, ne touche à rien. Renvoie le nb de fichiers.

    Le document en mémoire est muté dans les deux modes : la répartition
    « après » du rapport se calcule dessus, y compris en simulation.
    """
    written = 0
    for decision in plan.applied:
        path, doc = plan.docs[decision.reco_id]
        doc["types"] = list(decision.target)
        if not dry_run:
            write_json_if_changed(path, doc)
        written += 1
    return written


def build_report(plan: Plan, *, only: str, dry_run: bool, recos_dir: Path,
                 avant: dict[str, int], apres: dict[str, int], written: int) -> dict:
    """Rapport machine, destiné à `--json` puis à la relecture humaine.

    `mode` et `recosDir` vont ENSEMBLE : un rapport « apply » produit sur une
    copie de travail ne décrit pas le dépôt. Sans le chemin, on relit
    « 124 fichiers écrits » sans pouvoir dire *où* — et on relance un --apply.
    """
    return {
        "mode": "dry-run" if dry_run else "apply",
        "recosDir": str(recos_dir),
        "only": only,
        "fichiersModifies": written,
        "statistiques": {
            "propositions": len(plan.decisions),
            "appliquees": len(plan.applied),
            "ignorees": len(plan.skipped),
            "parOrigine": dict(Counter(d.origin for d in plan.applied)),
            "parMotifIgnore": dict(Counter(d.reason for d in plan.skipped)),
        },
        "repartitionTypes": {"avant": avant, "apres": apres},
        "appliquees": [d.as_dict() for d in plan.applied],
        "ignorees": [d.as_dict() for d in plan.skipped],
    }


def _print_summary(report: dict, plan: Plan) -> None:
    """Résumé console — la sortie du script, pas du debug."""
    stats = report["statistiques"]
    mode = "DRY-RUN (aucune écriture)" if report["mode"] == "dry-run" else "APPLIQUÉ"
    print(f"=== apply_types — {mode} · --only {report['only']} ===")
    print(f"cible : {report['recosDir']}")
    print(f"{stats['propositions']} propositions · "
          f"{stats['appliquees']} appliquées · {stats['ignorees']} ignorées")
    print(f"{report['fichiersModifies']} fichier(s) réécrit(s)")
    for origin, n in sorted(stats["parOrigine"].items()):
        print(f"  · {origin}: {n}")
    for decision in plan.applied:
        print(f"  {decision.reco_id} {list(decision.current)} -> {list(decision.target)}"
              f"  [{decision.origin}]")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Applique la reclassification des types.")
    parser.add_argument("--proposals", type=Path, default=DEFAULT_PROPOSALS,
                        help="fichier de propositions (défaut : tools/output/types_proposes.json)")
    parser.add_argument("--recos-dir", type=Path, default=RECOS_DIR,
                        help="racine des recos (défaut : src/content/recos)")
    parser.add_argument("--json", type=Path, dest="report_path",
                        help="écrit le rapport machine dans ce fichier")
    parser.add_argument("--only", choices=("certain", "arbitrage", "all"), default="all",
                        help="restreint aux propositions certaines ou aux arbitrages")
    parser.add_argument("--validated-ids", dest="validated_ids",
                        help="ids validés à la main, qui échappent au refus "
                             "« inference » : « a,b,c » ou « @fichier »")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", dest="dry_run", action="store_true", default=True,
                      help="simulation, aucune écriture (défaut)")
    mode.add_argument("--apply", dest="dry_run", action="store_false",
                      help="écrit réellement les fichiers")
    args = parser.parse_args(argv)

    proposals = read_json(args.proposals)
    recos = index_recos(args.recos_dir)
    avant = type_distribution(recos)

    plan = build_plan(proposals, recos, args.only, parse_ids(args.validated_ids))
    written = execute(plan, dry_run=args.dry_run)
    apres = type_distribution(recos)  # `execute` a muté les documents en mémoire

    report = build_report(plan, only=args.only, dry_run=args.dry_run,
                          recos_dir=args.recos_dir, avant=avant, apres=apres, written=written)
    _print_summary(report, plan)

    if args.report_path is not None:
        args.report_path.parent.mkdir(parents=True, exist_ok=True)
        args.report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Rapport écrit : {args.report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
