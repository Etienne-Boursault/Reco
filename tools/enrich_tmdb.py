"""
enrich_tmdb.py — Enrichit les recos film/série avec leurs « watch providers »
FR (plateformes de streaming) en interrogeant l'API TMDB.

Pour chaque reco de type `film` ou `serie` sans `externalIds.tmdb` :
  1. Recherche TMDB par titre (+ créateur si dispo), langue FR.
  2. Si non trouvé en `movie`, essai en `tv` (et inversement) — robustesse face
     au mauvais typage par le LLM (un docu peut être tagué film alors qu'il
     est en TV, etc.).
  3. Récupère les watch providers FR (`/<kind>/{id}/watch/providers`).
  4. Mappe chaque provider à une URL de recherche dédiée + marqueur éthique :
     - Amazon Prime Video → `ethics='avoid'` (politique anti-Amazon).
     - Canal+ / myCANAL    → `ethics='avoid'` (groupe Bolloré).
     - Arte / Mubi / Universcine / Tenk → `ethics='indie'`.
     - Tout le reste → `ethics='neutral'`.
  5. Sauvegarde `externalIds.tmdb`, `externalIds.tmdbType`, `watchProviders`
     dans le JSON de la reco (idempotent : write_json_if_changed).

Usage :
    python enrich_tmdb.py --source un-bon-moment
    python enrich_tmdb.py --source un-bon-moment --limit 10
    python enrich_tmdb.py --source un-bon-moment --force   # re-traiter même
                                                            # celles déjà enrichies
    python enrich_tmdb.py --source un-bon-moment --ids ubm-1,ubm-2 --dry-run

`--ids` restreint la passe à quelques recos : la chaîne de venus l'appelle sur
le seul épisode qu'elle vient de finaliser, et lister les 3 000 autres recos en
exclusion n'était pas tenable. `--dry-run` n'écrit rien — cet outil écrivait
sans filet, là où l'enrichisseur musical simule par défaut.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from collections.abc import Iterable
from dataclasses import dataclass, field

import requests
from dotenv import load_dotenv

from common import (
    TOOLS_DIR,
    log,
    parse_ids_option,
    read_json,
    recos_dir_for,
    write_json_if_changed,
)
from review_lock import ServerLockBusy, acquire_pipeline_lock
from tmdb_providers import _provider_link

TMDB_BASE = "https://api.themoviedb.org/3"
RATE_LIMIT_SLEEP = 0.1  # 10 req/sec, bien sous la limite TMDB (50 req/sec).

class TMDBAPIError(RuntimeError):
    """Erreur HTTP ou réseau TMDB — distincte d'un « non trouvé » légitime.

    Levée uniquement quand `_tmdb_get(..., strict=True)` est utilisé (appels
    UI ré-enrichissement) ; le mode batch CLI continue à retourner `None`
    pour skipper la reco sans casser la passe.

    `status_code` : code HTTP renvoyé par TMDB (utile pour distinguer 401 =
    clé invalide / 429 = rate-limit / 5xx = panne TMDB). `None` si l'erreur
    est réseau (timeout, DNS) avant qu'on ait pu recevoir un statut.
    """

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


def _tmdb_get(
    session: requests.Session,
    path: str,
    params: dict | None = None,
    api_key: str | None = None,
    strict: bool = False,
) -> dict | None:
    """GET TMDB avec auth, journalise les erreurs.

    La clé API est passée à `session.get` via `params=` (jamais via header
    custom) pour rester compatible avec l'API v3 de TMDB.

    `api_key` est explicite quand fourni par `main()` ; sinon on retombe sur
    `os.environ` pour rester compatible avec les appels directs (tests).

    `strict=True` : en cas d'erreur HTTP (401, 500…) ou réseau, lève
    `TMDBAPIError` au lieu de retourner `None`. Permet à l'UI de distinguer
    « API indisponible » d'un vrai « titre introuvable ».
    """
    if api_key is None:
        api_key = os.environ.get("TMDB_API_KEY", "")
    full = {"api_key": api_key, **(params or {})}
    try:
        r = session.get(f"{TMDB_BASE}{path}", params=full, timeout=15)
    except requests.RequestException as e:
        log.error("  HTTP : %s", e)
        if strict:
            raise TMDBAPIError(f"TMDB {path} : {e}") from e
        return None
    if r.status_code != 200:
        # On n'inclut pas `params` dans le log d'erreur : il contient la clé API.
        log.error("  TMDB %s → %s : %s", path, r.status_code, r.text[:200])
        if strict:
            raise TMDBAPIError(
                f"TMDB {path} → HTTP {r.status_code}",
                status_code=r.status_code,
            )
        return None
    return r.json()


def tmdb_search(
    session: requests.Session, reco_type: str, title: str,
    creator: str | None = None, api_key: str | None = None,
    strict: bool = False,
) -> tuple[str, str] | None:
    """Cherche le titre sur TMDB. Retourne (tmdb_id, kind in {'movie','tv'}) ou None.

    Stratégie de recherche (premier hit gagne) :
      1. titre + creator (si fourni), langue FR, type primaire (film→movie / serie→tv).
      2. titre seul, langue FR, type primaire.
      3. titre seul, sans contrainte de langue (include_adult=false), type primaire.
      4. mêmes étapes mais sur le type secondaire (cas de mauvais typage par le LLM).
    """
    primary = "movie" if reco_type == "film" else "tv"
    secondary = "tv" if primary == "movie" else "movie"

    queries: list[tuple[str, dict]] = []
    if creator:
        queries.append((f"{title} {creator}", {"language": "fr-FR"}))
    queries.append((title, {"language": "fr-FR"}))
    queries.append((title, {}))  # toutes langues

    for kind in (primary, secondary):
        for q, extra in queries:
            data = _tmdb_get(session, f"/search/{kind}",
                             {"query": q, **extra}, api_key=api_key,
                             strict=strict)
            results = (data or {}).get("results") or []
            if results:
                return str(results[0]["id"]), kind
    return None


def tmdb_watch_providers(
    session: requests.Session, tmdb_id: str, kind: str, title: str,
    api_key: str | None = None, strict: bool = False,
) -> tuple[str | None, list[dict]]:
    """Récupère la page « où regarder » du film + les watch providers FR.

    Retourne (watch_page_url, providers). ATTENTION : `results.FR.link` ne
    renvoie PLUS une URL JustWatch mais une URL themoviedb.org (l'API TMDB a
    changé) — d'où le nom `watchPage`, qui décrit la fonction et non le
    fournisseur. C'est notre lien streaming principal.
    Les providers sont conservés à titre informatif (debug / évolutions futures).
    """
    data = _tmdb_get(session, f"/{kind}/{tmdb_id}/watch/providers",
                     api_key=api_key, strict=strict)
    fr = ((data or {}).get("results") or {}).get("FR") or {}
    watch_page_url = fr.get("link") or None
    seen: set[str] = set()
    providers: list[dict] = []
    for slot in ("flatrate", "free", "ads", "rent", "buy"):
        for prov in fr.get(slot, []) or []:
            name = (prov.get("provider_name") or "").strip()
            if not name or name in seen:
                continue
            seen.add(name)
            providers.append(_provider_link(name, title))
    return watch_page_url, providers


def is_targetable(reco: dict) -> bool:
    """True si la reco a au moins un type que cet enricher traite (film/serie)."""
    return any(t in ("film", "serie") for t in (reco.get("types") or []))


@dataclass(frozen=True)
class CasTmdb:
    """Sort d'une reco dans une passe : `raison` vaut `ok` ou `not_found`."""

    reco_id: str
    titre: str
    raison: str
    providers: int


@dataclass
class RapportTmdb:
    """Agrégats d'une passe, pour la chaîne de venus et les rapports."""

    vues: int = 0
    ecrites: int = 0
    cas: list[CasTmdb] = field(default_factory=list)

    @property
    def servies(self) -> set[str]:
        """Ids des recos pour lesquelles TMDB a rendu une fiche."""
        return {c.reco_id for c in self.cas if c.raison == "ok"}

    @property
    def introuvables(self) -> list[CasTmdb]:
        return [c for c in self.cas if c.raison == "not_found"]


def cle_api() -> str:
    """Clé TMDB, depuis l'environnement ou `tools/.env`. Lève si elle manque.

    Sur venus, la clé arrive par `env_file` (cf. deploy/venus/compose.yml) :
    elle est déjà dans l'environnement, et `load_dotenv` ne fait rien.
    """
    load_dotenv(TOOLS_DIR / ".env")
    cle = os.getenv("TMDB_API_KEY")
    if not cle:
        raise RuntimeError(
            "TMDB_API_KEY absent (tools/.env en local, ~/docker/reco/.env sur venus). "
            "Clé v3 sur https://www.themoviedb.org/settings/api.")
    return cle


def enrich_one(
    reco: dict,
    *,
    session: requests.Session,
    api_key: str | None = None,
    force: bool = False,
) -> dict:
    """Enrichit une reco film/série avec TMDB.

    - Lit `reco['title']`, `reco['creator']` (réalisateur si présent), `reco['types']`.
    - Choisit le type pertinent (film/serie) pour orienter la recherche.
    - Si `externalIds.tmdb` + `externalIds.tmdbType` déjà présents et `force=False` :
      réutilise l'id sans re-chercher (économise 1 appel API).
    - Si `force=True` : ignore les ids existants et relance `tmdb_search` (cas
      du bouton « Ré-enrichir » de l'UI quand le titre a été corrigé).
      Dans ce mode, propage les erreurs HTTP/réseau comme `TMDBAPIError` —
      l'UI distingue ainsi « titre vraiment introuvable » de « API down ».
    - Récupère `watch_providers` et met à jour la reco IN-PLACE :
      `externalIds.tmdb`, `externalIds.tmdbType`, `externalIds.watchPage`,
      `watchProviders` (les deux derniers sont supprimés si l'API ne renvoie rien).
    - Si TMDB ne trouve rien, ne touche pas aux champs existants et ajoute un
      champ NON PERSISTÉ `_enrich_status='not_found'` au dict retourné — utile
      pour les logs / l'UI. Le CLI prend soin de le retirer avant write.
    - Retourne la reco modifiée (même référence).
    """
    title = reco["title"]
    creator = reco.get("creator")
    types_list = reco.get("types") or []
    reco_type = next(
        (t for t in types_list if t in ("film", "serie")),
        types_list[0] if types_list else "film",
    )

    # En mode `force=True` (bouton UI Ré-enrichir), on remonte les vraies
    # erreurs HTTP (401/500/timeout) sous forme d'exception, pour qu'elles
    # soient distinguées d'un « titre vraiment introuvable ». En mode batch
    # CLI (`force=False`), on garde l'ancien comportement « skip silencieux ».
    ext = dict(reco.get("externalIds") or {})
    if not force and ext.get("tmdb") and ext.get("tmdbType"):
        tmdb_id, kind = ext["tmdb"], ext["tmdbType"]
    else:
        found = tmdb_search(session, reco_type, title, creator,
                            api_key=api_key, strict=force)
        if not found:
            reco["_enrich_status"] = "not_found"
            return reco
        tmdb_id, kind = found

    watch_page_url, providers = tmdb_watch_providers(
        session, tmdb_id, kind, title, api_key=api_key, strict=force,
    )
    ext["tmdb"] = tmdb_id
    ext["tmdbType"] = kind
    if watch_page_url:
        ext["watchPage"] = watch_page_url
    elif "watchPage" in ext:
        del ext["watchPage"]
    reco["externalIds"] = ext
    if providers:
        reco["watchProviders"] = providers
    elif "watchProviders" in reco:
        del reco["watchProviders"]
    reco["_enrich_status"] = "ok"
    return reco


def main():
    parser = argparse.ArgumentParser(
        description="Enrichit les recos film/série avec leurs watch providers FR via TMDB."
    )
    parser.add_argument("--source", required=True)
    parser.add_argument("--limit", type=int, default=None,
                        help="Limiter le nombre de recos traitées (utile pour tester).")
    parser.add_argument("--force", action="store_true",
                        help="Re-traiter même les recos qui ont déjà un externalIds.tmdb.")
    parser.add_argument("--ids", default=None,
                        help="N'enrichir QUE ces recos : « a,b,c » ou « @fichier » "
                             "(un id par ligne).")
    parser.add_argument("--dry-run", action="store_true",
                        help="N'écrit rien : dit ce qui serait enrichi.")
    parser.add_argument("--ignore-server-lock", action="store_true",
                        help="Ignore le verrou review_server (à tes risques : "
                             "écritures concurrentes possibles).")
    args = parser.parse_args()

    # Coordination avec review_server (cf. tools/review_lock.py).
    try:
        lock_ctx = acquire_pipeline_lock(force=args.ignore_server_lock)
        lock_ctx.__enter__()
    except ServerLockBusy as exc:
        log.error("%s", exc)
        sys.exit(1)

    try:
        try:
            api_key = cle_api()
        except RuntimeError as exc:
            log.error("%s", exc)
            sys.exit(1)

        _run_enrichment(args, api_key)
    finally:
        try:
            lock_ctx.__exit__(None, None, None)
        except Exception:  # noqa: BLE001, S110 — release best-effort
            pass


def _run_enrichment(args, api_key):
    """Corps métier de enrich_tmdb — extrait pour wrapper avec le lock context."""
    run(source=args.source, api_key=api_key, ids=parse_ids_option(args.ids),
        limit=args.limit, force=args.force, apply=not args.dry_run)


def run(*, source: str, api_key: str, ids: Iterable[str] = (),
        limit: int | None = None, force: bool = False, apply: bool = True,
        session: requests.Session | None = None) -> RapportTmdb:
    """Passe TMDB sur les recos film/série d'une source.

    `ids` non vide → SEULES ces recos sont examinées (périmètre d'un épisode).
    `apply=False` → rien n'est écrit, le rapport dit ce qui l'aurait été.
    """
    recos_dir = recos_dir_for(source)
    voulus = set(ids)
    rapport = RapportTmdb()
    targets = []
    for p in sorted(recos_dir.glob("*.json")):
        d = read_json(p)
        if not is_targetable(d):
            continue
        if voulus and d.get("id") not in voulus:
            continue
        ext = d.get("externalIds") or {}
        if not force and ext.get("tmdb") and ext.get("watchPage"):
            # Déjà enrichi complètement.
            continue
        targets.append((p, d))

    if limit:
        targets = targets[:limit]
    log.info("%d reco(s) film/série à enrichir TMDB%s.", len(targets),
             " (simulation)" if not apply else "")
    rapport.vues = len(targets)
    if not targets:
        return rapport

    session = session or requests.Session()
    enriched = 0
    not_found = 0
    for i, (p, d) in enumerate(targets, 1):
        title = d["title"]
        creator = d.get("creator")
        label = f"{title} ({creator})" if creator else title
        types_list = d.get("types") or []
        reco_type = next(
            (t for t in types_list if t in ("film", "serie")),
            types_list[0] if types_list else "film",
        )
        log.info("[%d/%d] %s [%s]", i, len(targets), label[:60], reco_type)
        # On log la réutilisation d'id avant l'appel (enrich_one ne re-loggue pas).
        ext_pre = d.get("externalIds") or {}
        had_id = bool(ext_pre.get("tmdb") and ext_pre.get("tmdbType"))
        if had_id:
            log.info("  ↻ TMDB id déjà connu : %s (%s)",
                     ext_pre["tmdb"], ext_pre["tmdbType"])

        # Pas de `force=` ici : il ferait remonter les erreurs HTTP en exception
        # (mode UI), alors que la passe batch doit sauter la reco et continuer.
        # `--force` agit sur la SÉLECTION, plus haut (recos déjà enrichies).
        enrich_one(d, session=session, api_key=api_key)
        status = d.pop("_enrich_status", None)
        reco_id = str(d.get("id") or p.stem)
        if status == "not_found":
            log.info("  → TMDB : pas trouvé")
            not_found += 1
            rapport.cas.append(CasTmdb(reco_id, title, "not_found", 0))
            time.sleep(RATE_LIMIT_SLEEP)
            continue
        tmdb_id = d["externalIds"]["tmdb"]
        kind = d["externalIds"]["tmdbType"]
        watch_page_url = d["externalIds"].get("watchPage")
        providers = d.get("watchProviders") or []
        if apply and write_json_if_changed(p, d):
            enriched += 1
        rapport.cas.append(CasTmdb(reco_id, title, "ok", len(providers)))
        log.info("  → tmdb_id=%s (%s) · page « où regarder »=%s · %d providers info%s",
                 tmdb_id, kind, "OK" if watch_page_url else "—", len(providers),
                 " (simulation)" if not apply else "")
        time.sleep(RATE_LIMIT_SLEEP)

    rapport.ecrites = enriched
    log.info("Terminé : %d enrichis · %d non trouvés · %d inchangés.",
             enriched, not_found, len(targets) - enriched - not_found)
    return rapport


if __name__ == "__main__":
    main()
