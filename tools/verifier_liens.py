"""verifier_liens.py — vérifie les liens du site construit, internes et externes.

La source est le site CONSTRUIT (`dist/`), pas les données : 215 des liens
publiés au 2026-11-02 sont fabriqués à la construction (vidéo YouTube de
l'épisode, fiche TMDB tirée de l'identifiant, réseaux d'un créateur) et
n'apparaissent dans aucun fichier JSON. On vérifie ce que le visiteur voit.

Deux modes :

- `internes DIST` : chaque lien vers une page du site doit mener à un fichier
  de `dist/`. Sans réseau, quelques secondes : tourne dans la CI après le build.
- `externes DIST` : sonde chaque adresse externe une fois, avec la politique de
  `link_check` (vivant / mort / inconnu, jamais deux verdicts). Une requête à
  la fois par site, plusieurs sites en parallèle : un 429 provoqué par nos
  propres requêtes ne prouve rien. Tourne chaque semaine sur venus.

Rien n'est jamais retiré du corpus : le rapport nomme la reco, la plateforme et
la réponse obtenue, et l'éditeur décide (décision LV-3 du 2026-11-02).
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import threading
import time
from collections import defaultdict
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import unquote, urlparse

from link_check import ProbeResult, fetch_via_urllib, verify_url

# Le site lui-même : celui du build (la CI construit avec https://example.com).
SITE = (urlparse(os.environ.get("SITE_URL") or "https://unebonnere.co").hostname
        or "unebonnere.co").removeprefix("www.")
# Routes servies à la demande par le serveur Node : absentes de `dist/` par
# construction (cf. `ssrOnDemandRoutes` dans astro.config.mjs).
ROUTES_SERVEUR = ("/api/", "/audience")
# Un même site n'est jamais sondé deux fois en moins de PAUSE_HOTE secondes.
PAUSE_HOTE = 1.0
SITES_EN_PARALLELE = 8
# Un message Matrix lisible : au-delà, le rapport complet fait foi.
MESSAGE_MAX = 15

_HREF = re.compile(r'<a\b[^>]*?\bhref="([^"]+)"', re.IGNORECASE)


def pages(dist: Path) -> Iterable[tuple[str, str]]:
    """(chemin de la page, contenu) de chaque page HTML construite."""
    for fichier in sorted(dist.rglob("*.html")):
        chemin = "/" + fichier.relative_to(dist).as_posix()
        yield chemin.removesuffix("index.html"), fichier.read_text(encoding="utf-8",
                                                                     errors="replace")


def liens(dist: Path) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    """(internes, externes) : chaque cible et les pages qui y renvoient."""
    internes: dict[str, set[str]] = defaultdict(set)
    externes: dict[str, set[str]] = defaultdict(set)
    for page, contenu in pages(dist):
        for brut in _HREF.findall(contenu):
            cible = html.unescape(brut).strip()
            parties = urlparse(cible)
            if parties.scheme in ("http", "https"):
                hote = (parties.hostname or "").removeprefix("www.")
                if hote == SITE:
                    internes[parties.path or "/"].add(page)
                else:
                    externes[cible].add(page)
            elif not parties.scheme and not parties.netloc and cible.startswith("/"):
                internes[parties.path].add(page)
    return internes, externes


def existe(dist: Path, chemin: str) -> bool:
    """Le fichier que le serveur rendrait pour `chemin` existe-t-il ?"""
    if chemin.startswith(ROUTES_SERVEUR):
        return True
    relatif = unquote(chemin).lstrip("/")
    candidats = [dist / relatif / "index.html"] if chemin.endswith("/") else [
        dist / relatif, dist / relatif / "index.html", dist / f"{relatif}.html"]
    return any(c.is_file() for c in candidats)


def internes_casses(dist: Path) -> dict[str, set[str]]:
    internes, _externes = liens(dist)
    return {c: p for c, p in sorted(internes.items()) if not existe(dist, c)}


# ===== liens externes ==========================================================
Sonde = Callable[[str], ProbeResult]


def _sonde_reelle(url: str) -> ProbeResult:
    return verify_url(url, fetcher=fetch_via_urllib)


def sonder(urls: Iterable[str], sonde: Sonde = _sonde_reelle,
           pause: float = PAUSE_HOTE) -> dict[str, ProbeResult]:
    """Sonde chaque URL ; un fil par site, `pause` entre deux requêtes d'un site."""
    par_hote: dict[str, list[str]] = defaultdict(list)
    for url in sorted(set(urls)):
        par_hote[(urlparse(url).hostname or "").lower()].append(url)
    resultats: dict[str, ProbeResult] = {}
    verrou = threading.Lock()

    def un_site(adresses: list[str]) -> None:
        for k, url in enumerate(adresses):
            if k:
                time.sleep(pause)
            try:
                verdict = sonde(url)
            except Exception as exc:  # noqa: BLE001 — une adresse ne bloque pas les autres.
                verdict = ProbeResult("unknown", f"sonde en échec ({type(exc).__name__})")
            with verrou:
                resultats[url] = verdict

    with ThreadPoolExecutor(SITES_EN_PARALLELE) as pool:
        list(pool.map(un_site, par_hote.values()))
    return resultats


def recos_par_url(recos: Path) -> dict[str, list[str]]:
    """Identifiants des recos affichées qui portent chaque URL."""
    trouvees: dict[str, list[str]] = defaultdict(list)
    for fichier in sorted(recos.rglob("*.json")):
        reco = json.loads(fichier.read_text(encoding="utf-8"))
        if reco.get("status") == "discarded":
            continue
        for cle in ("links", "customLinks", "watchProviders"):
            for lien in reco.get(cle) or []:
                if isinstance(lien, dict) and lien.get("url"):
                    trouvees[lien["url"]].append(reco.get("id", fichier.stem))
    return trouvees


@dataclass
class Rapport:
    date: str
    morts: dict[str, dict] = field(default_factory=dict)
    inconnus_par_site: dict[str, int] = field(default_factory=dict)
    vivants: int = 0
    nouveaux: list[str] = field(default_factory=list)


def rapporter(resultats: dict[str, ProbeResult], externes: dict[str, set[str]],
              recos: dict[str, list[str]], deja_morts: set[str]) -> Rapport:
    rapport = Rapport(datetime.now(UTC).strftime("%Y-%m-%d"))
    inconnus: dict[str, int] = defaultdict(int)
    for url, verdict in sorted(resultats.items()):
        if verdict.verdict == "alive":
            rapport.vivants += 1
        elif verdict.verdict == "unknown":
            inconnus[(urlparse(url).hostname or "?").removeprefix("www.")] += 1
        else:
            rapport.morts[url] = {"reponse": verdict.detail,
                                  "recos": sorted(set(recos.get(url, []))),
                                  "pages": sorted(externes.get(url, ()))[:5]}
            if url not in deja_morts:
                rapport.nouveaux.append(url)
    rapport.inconnus_par_site = dict(sorted(inconnus.items(), key=lambda x: -x[1]))
    return rapport


def en_markdown(rapport: Rapport) -> str:
    total = rapport.vivants + len(rapport.morts) + sum(rapport.inconnus_par_site.values())
    bilan = (f"{total} adresses : {rapport.vivants} vivantes, {len(rapport.morts)} mortes "
             f"(dont {len(rapport.nouveaux)} nouvelles), "
             f"{sum(rapport.inconnus_par_site.values())} invérifiables.")
    lignes = [f"# Liens externes du site — {rapport.date}", "", bilan, ""]
    if rapport.morts:
        lignes += ["## Mortes", "", "| Adresse | Réponse | Recos | Page |", "|---|---|---|---|"]
        for url, m in rapport.morts.items():
            neuf = " 🆕" if url in rapport.nouveaux else ""
            lignes.append(f"| {url}{neuf} | {m['reponse']} | {', '.join(m['recos']) or '—'} "
                          f"| {m['pages'][0] if m['pages'] else '—'} |")
        lignes.append("")
    if rapport.inconnus_par_site:
        lignes += ["## Invérifiables, par site", "",
                   ("Le site a refusé de répondre à un robot, ou sa réponse ne prouve "
                    "rien (Netflix et Deezer répondent 404 même pour une vraie page)."), ""]
        lignes += [f"- {site} : {n}" for site, n in rapport.inconnus_par_site.items()]
    return "\n".join(lignes) + "\n"


def message(rapport: Rapport, chemin_rapport: str) -> str | None:
    """Message Matrix, ou None quand aucun lien n'est mort depuis la dernière fois."""
    if not rapport.nouveaux:
        return None
    lignes = [f"🔗 {len(rapport.nouveaux)} lien(s) mort(s) depuis la dernière vérification :"]
    for url in rapport.nouveaux[:MESSAGE_MAX]:
        m = rapport.morts[url]
        qui = ", ".join(m["recos"]) or (m["pages"][0] if m["pages"] else "?")
        lignes.append(f"- {qui} : {url} ({m['reponse']})")
    if len(rapport.nouveaux) > MESSAGE_MAX:
        lignes.append(f"… et {len(rapport.nouveaux) - MESSAGE_MAX} autre(s).")
    lignes.append(f"Rapport complet : {chemin_rapport}. Rien n'a été retiré du site.")
    return "\n".join(lignes)


# ===== CLI =====================================================================
def _sans_pages(dist: Path) -> bool:
    """Un build absent ou raté ne doit pas passer pour un site sans lien cassé."""
    if next(dist.rglob("*.html"), None) is None:
        print(f"Aucune page HTML dans {dist} : le site n'est pas construit.")
        return True
    return False


def _cmd_internes(args: argparse.Namespace) -> int:
    if _sans_pages(Path(args.dist)):
        return 2
    casses = internes_casses(Path(args.dist))
    for cible, origines in casses.items():
        print(f"Lien interne cassé : {cible} (depuis {', '.join(sorted(origines)[:3])})")
    print(f"{len(casses)} lien(s) interne(s) cassé(s).")
    return 1 if casses else 0


def _cmd_externes(args: argparse.Namespace) -> int:
    if _sans_pages(Path(args.dist)):
        return 2
    _internes, externes = liens(Path(args.dist))
    etat_p, sortie = Path(args.etat), Path(args.sortie)
    deja = set(json.loads(etat_p.read_text(encoding="utf-8")).get("morts", [])) \
        if etat_p.exists() else set()
    resultats = sonder(externes)
    rapport = rapporter(resultats, externes, recos_par_url(Path(args.recos)), deja)
    sortie.mkdir(parents=True, exist_ok=True)
    md = sortie / f"liens-{rapport.date}.md"
    md.write_text(en_markdown(rapport), encoding="utf-8")
    (sortie / f"liens-{rapport.date}.json").write_text(
        json.dumps(rapport.__dict__, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp = etat_p.with_suffix(".tmp")
    tmp.write_text(json.dumps({"date": rapport.date, "morts": sorted(rapport.morts)}),
                   encoding="utf-8")
    tmp.replace(etat_p)
    print(en_markdown(rapport).split("\n\n")[1])
    texte = message(rapport, str(md))
    if texte and args.notifier == "matrix":
        from traiter_nouveaux_episodes import build_notify
        build_notify("matrix")(texte)
    elif texte:
        print(texte)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sous = parser.add_subparsers(dest="mode", required=True)
    p_int = sous.add_parser("internes", help="liens vers les pages du site (sans réseau)")
    p_int.add_argument("dist")
    p_int.set_defaults(func=_cmd_internes)
    p_ext = sous.add_parser("externes", help="liens vers d'autres sites (réseau)")
    p_ext.add_argument("dist")
    p_ext.add_argument("--recos", default="src/content/recos")
    p_ext.add_argument("--etat", required=True, help="morts de la vérification précédente")
    p_ext.add_argument("--sortie", required=True, help="dossier des rapports")
    p_ext.add_argument("--notifier", choices=("matrix", "none"), default="none")
    p_ext.set_defaults(func=_cmd_externes)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
