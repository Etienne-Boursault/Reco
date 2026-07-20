"""poll_rss.py — CLI : poll RSS hebdomadaire + notification nouvel épisode.

Item roadmap #23 (ADR 0042). Fonctionnement :

1. Pour chaque source (--source <id>|all), lit le `rssUrl` configuré
   dans `src/content/sources/<id>.json`.
2. Récupère le flux via un `FeedFetcher` injectable (production :
   `RequestsFeedFetcher`). Utilise `If-None-Match`/`If-Modified-Since`
   si on a déjà un état pour éviter de re-télécharger.
3. Diff `seenGuids` (état persistant `tools/output/rss/<src>/state.json`)
   contre les épisodes du flux → liste des nouveaux épisodes.
4. Si nouveau(x) épisode(s) : notifie via le sender choisi
   (--notify discord|slack|email|none) et, si --dispatch-event, poste un
   `repository_dispatch` GitHub pour déclencher le pipeline en CI.
5. Met à jour l'état (atomic). Lockfile pipeline pour ne pas concurrencer
   les autres scripts d'écriture.

Garanties :
- Idempotent : re-run sans nouveauté = pas de notif, pas de write inutile.
- Pas d'appel HTTP en test : `FeedFetcher`/`NotificationSender` injectés
  via le constructeur de `PollRunner`.
- Pas de secret en log : webhook URL réduite à son host.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence
from urllib.parse import urlparse

from common import OUTPUT_DIR, load_source, log
from notify.discord import DiscordWebhookSender
from notify.formatter import NewEpisodeMessage, build_discord_embed, build_slack_blocks
from notify.ports import NotificationSender
from notify.slack import SlackWebhookSender
from review_lock import acquire_pipeline_lock
from rss.detector import detect_new_episodes
from rss.parser import ParsedEpisode, ParsedFeed, parse_feed_bytes
from rss.ports import FeedFetcher, FetchResult
from rss.state import load_state, save_state
from audit_core.cli_runner import utcnow_iso

DEFAULT_STATE_DIR: Path = OUTPUT_DIR / "rss"
DEFAULT_LIMIT_NEW = 5

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_BAD_ARGS = 2


# ---------------------------------------------------------------------------
# Fetcher production (requests). Isolé pour qu'un test puisse injecter un mock.
# ---------------------------------------------------------------------------
class RequestsFeedFetcher:
    """Implémentation `FeedFetcher` réelle basée sur `requests`.

    Honore `If-None-Match` / `If-Modified-Since` pour économiser la bande
    et signaler 304 → `not_modified=True` côté détecteur (skip diff).
    """

    def __init__(self, *, timeout: float = 15.0, session=None) -> None:
        self._timeout = timeout
        self._session = session

    def fetch(
        self,
        url: str,
        *,
        etag: str | None = None,
        last_modified: str | None = None,
    ) -> FetchResult:
        import requests  # noqa: PLC0415

        headers: dict[str, str] = {"User-Agent": "reco-poll-rss/1.0"}
        if etag:
            headers["If-None-Match"] = etag
        if last_modified:
            headers["If-Modified-Since"] = last_modified
        s = self._session or requests
        resp = s.get(url, headers=headers, timeout=self._timeout)
        if getattr(resp, "status_code", 0) == 304:
            return FetchResult(body=b"", not_modified=True)
        resp.raise_for_status()
        return FetchResult(
            body=resp.content,
            etag=resp.headers.get("ETag") if hasattr(resp, "headers") else None,
            last_modified=(
                resp.headers.get("Last-Modified") if hasattr(resp, "headers") else None
            ),
        )


# ---------------------------------------------------------------------------
# Dispatch event GitHub.
# ---------------------------------------------------------------------------
class GitHubDispatcher:
    """Poste un `repository_dispatch` event pour déclencher le pipeline.

    Conf via env GITHUB_TOKEN + GITHUB_REPOSITORY (`owner/repo`). Injecter
    `session` en test.
    """

    def __init__(
        self,
        *,
        token: str,
        repository: str,
        event_type: str = "reco-new-episode",
        timeout: float = 10.0,
        session=None,
    ) -> None:
        if not token:
            raise ValueError("GITHUB_TOKEN manquant pour dispatch event.")
        if "/" not in repository:
            raise ValueError(
                "GITHUB_REPOSITORY doit avoir la forme owner/repo.",
            )
        self._token = token
        self._repository = repository
        self._event_type = event_type
        self._timeout = timeout
        self._session = session

    def dispatch(self, payload: dict) -> bool:
        url = f"https://api.github.com/repos/{self._repository}/dispatches"
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self._token}",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        body = {"event_type": self._event_type, "client_payload": payload}
        try:
            if self._session is not None:
                resp = self._session.post(
                    url, headers=headers, json=body, timeout=self._timeout,
                )
            else:
                import requests  # noqa: PLC0415

                resp = requests.post(
                    url, headers=headers, json=body, timeout=self._timeout,
                )
        except Exception as exc:  # noqa: BLE001
            log.warning("Dispatch GitHub a échoué : %s", exc)
            return False
        ok = bool(getattr(resp, "ok", False))
        if not ok:
            log.warning(
                "Dispatch GitHub status=%s", getattr(resp, "status_code", "?"),
            )
        return ok


# ---------------------------------------------------------------------------
# Runner.
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class PollOptions:
    sources: tuple[str, ...]
    state_dir: Path
    dry_run: bool = False
    force_notify: bool = False
    limit_new: int = DEFAULT_LIMIT_NEW
    notify_channel: str = "none"  # discord|slack|email|none


@dataclass(frozen=True, slots=True)
class SourcePollResult:
    source_id: str
    feed_episode_count: int
    new_episodes: tuple[ParsedEpisode, ...]
    notified: int
    dispatched: bool
    not_modified: bool = False


def _resolve_sources(arg: str) -> list[str]:
    """Renvoie la liste des source ids à poller. `all` → liste depuis SOURCES_DIR."""
    from common import SOURCES_DIR  # noqa: PLC0415

    if arg == "all":
        if not SOURCES_DIR.exists():
            return []
        return sorted(p.stem for p in SOURCES_DIR.glob("*.json"))
    return [arg]


def _notify_one(
    sender: NotificationSender,
    feed: ParsedFeed,
    ep: ParsedEpisode,
    source_id: str,
) -> bool:
    """Construit le payload selon le canal et délègue au sender."""
    msg = NewEpisodeMessage(
        feed_title=feed.title or source_id,
        episode_title=ep.title,
        episode_url=ep.link,
        published_at=ep.published,
        source_id=source_id,
    )
    if sender.name == "discord":
        return sender.send(build_discord_embed(msg))
    if sender.name == "slack":
        return sender.send(build_slack_blocks(msg))
    if sender.name == "email":
        from notify.formatter import build_plain_text  # noqa: PLC0415

        return sender.send(
            {
                "subject": f"[Reco] Nouvel épisode — {feed.title or source_id}",
                "body": build_plain_text(msg),
            },
        )
    # Canal inconnu : on log mais on ne crashe pas.
    log.warning("Canal de notification inconnu : %s", sender.name)
    return False


def _poll_one_source(
    source_id: str,
    *,
    fetcher: FeedFetcher,
    sender: NotificationSender | None,
    dispatcher: GitHubDispatcher | None,
    options: PollOptions,
) -> SourcePollResult:
    """Poll une source : fetch → parse → diff → notify → save."""
    cfg = load_source(source_id)
    feed_url = cfg.get("rssUrl")
    if not feed_url:
        log.warning("Source %s : pas de rssUrl, skip.", source_id)
        return SourcePollResult(source_id, 0, (), 0, False)

    state = load_state(source_id, state_dir=options.state_dir)
    try:
        result = fetcher.fetch(
            feed_url,
            etag=state.last_etag,
            last_modified=state.last_modified,
        )
    except Exception as exc:  # noqa: BLE001
        host = urlparse(feed_url).hostname or "?"
        log.error("Source %s : fetch RSS (%s) a échoué : %s", source_id, host, exc)
        return SourcePollResult(source_id, 0, (), 0, False)

    if result.not_modified:
        log.info("Source %s : 304 Not Modified, rien à faire.", source_id)
        # On rafraîchit `lastCheckedAt` même en 304 pour traçabilité.
        if not options.dry_run:
            new_state = state.with_observed(
                guids=[], checked_at=utcnow_iso(),
            )
            save_state(new_state, state_dir=options.state_dir)
        return SourcePollResult(source_id, 0, (), 0, False, not_modified=True)

    feed = parse_feed_bytes(result.body, fallback_url=feed_url)
    new_eps = detect_new_episodes(feed, state, limit=options.limit_new)

    # Premier run sur état vierge : tout est « nouveau » mais on ne veut
    # PAS noyer Discord — on cap à `limit_new` (déjà fait dans le
    # détecteur) et on log explicitement.
    if not state.seen_guids and new_eps:
        log.info(
            "Source %s : premier run, %d/%d épisodes seront marqués vus "
            "(plafond notif --limit-new=%d).",
            source_id, len(new_eps), len(feed.episodes), options.limit_new,
        )

    notified = 0
    if options.force_notify and not new_eps and feed.episodes:
        # --force-notify : envoie le tout dernier épisode pour valider la
        # chaîne d'envoi sans dépendre d'un vrai nouveau.
        new_eps = [feed.episodes[0]]

    if new_eps and sender is not None and not options.dry_run:
        for ep in new_eps:
            ok = _notify_one(sender, feed, ep, source_id)
            if ok:
                notified += 1

    dispatched = False
    if new_eps and dispatcher is not None and not options.dry_run:
        dispatched = dispatcher.dispatch(
            {
                "source_id": source_id,
                "episode_count": len(new_eps),
                "episode_titles": [e.title for e in new_eps],
            },
        )

    # Mise à jour de l'état (sauf dry-run).
    if not options.dry_run:
        all_guids = [e.guid for e in feed.episodes]
        new_state = state.with_observed(
            guids=all_guids,
            checked_at=utcnow_iso(),
            etag=result.etag,
            last_modified=result.last_modified,
            metadata={"feedTitle": feed.title, "feedUrl": feed_url},
        )
        save_state(new_state, state_dir=options.state_dir)

    return SourcePollResult(
        source_id=source_id,
        feed_episode_count=len(feed.episodes),
        new_episodes=tuple(new_eps),
        notified=notified,
        dispatched=dispatched,
    )


def run_poll(
    options: PollOptions,
    *,
    fetcher: FeedFetcher | None = None,
    sender: NotificationSender | None = None,
    dispatcher: GitHubDispatcher | None = None,
    use_lock: bool = True,
) -> list[SourcePollResult]:
    """Boucle sur les sources. Lockfile pipeline acquis si `use_lock`.

    `fetcher`/`sender`/`dispatcher` injectables (tests). En prod, le CLI
    construit les valeurs par défaut depuis l'environnement.
    """
    fetcher = fetcher or RequestsFeedFetcher()
    results: list[SourcePollResult] = []

    def _loop() -> None:
        for sid in options.sources:
            try:
                r = _poll_one_source(
                    sid,
                    fetcher=fetcher,
                    sender=sender,
                    dispatcher=dispatcher,
                    options=options,
                )
            except FileNotFoundError as exc:
                log.error("Source inconnue %s : %s", sid, exc)
                continue
            results.append(r)
            log.info(
                "Source %s : feed=%d, nouveaux=%d, notifiés=%d, dispatched=%s",
                r.source_id, r.feed_episode_count, len(r.new_episodes),
                r.notified, r.dispatched,
            )

    if use_lock and not options.dry_run:
        with acquire_pipeline_lock():
            _loop()
    else:
        _loop()
    return results


# ---------------------------------------------------------------------------
# CLI.
# ---------------------------------------------------------------------------
def _build_sender(channel: str) -> NotificationSender | None:
    """Instancie le sender en fonction du canal demandé."""
    if channel == "none":
        return None
    if channel == "discord":
        url = os.environ.get("RECO_DISCORD_WEBHOOK", "")
        return DiscordWebhookSender(url)
    if channel == "slack":
        url = os.environ.get("RECO_SLACK_WEBHOOK", "")
        return SlackWebhookSender(url)
    if channel == "email":
        from notify.email import SmtpConfig, SmtpSender  # noqa: PLC0415

        config = SmtpConfig(
            host=os.environ.get("SMTP_HOST", ""),
            port=int(os.environ.get("SMTP_PORT", "587")),
            user=os.environ.get("SMTP_USER", ""),
            password=os.environ.get("SMTP_PASS", ""),
            sender=os.environ.get("SMTP_FROM", ""),
            recipient=os.environ.get("SMTP_TO", ""),
            use_ssl=os.environ.get("SMTP_SSL", "").lower() in {"1", "true", "yes"},
        )
        if not config.host:
            raise ValueError("SMTP_HOST manquant pour le canal email.")
        return SmtpSender(config)
    raise ValueError(f"Canal de notification inconnu : {channel}")


def _build_dispatcher() -> GitHubDispatcher | None:
    token = os.environ.get("GITHUB_TOKEN", "")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if not token or not repo:
        log.warning(
            "--dispatch-event demandé mais GITHUB_TOKEN/GITHUB_REPOSITORY "
            "manquant ; dispatch désactivé.",
        )
        return None
    return GitHubDispatcher(token=token, repository=repo)


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="poll_rss",
        description=(
            "Poll les flux RSS configurés, détecte les nouveaux épisodes, "
            "notifie un canal et (optionnel) déclenche le pipeline."
        ),
    )
    p.add_argument(
        "--source", default="all",
        help="Source id (`un-bon-moment`) ou `all`. Défaut: all.",
    )
    p.add_argument(
        "--state-dir", default=str(DEFAULT_STATE_DIR),
        help="Dossier des sidecars d'état. Défaut: tools/output/rss/.",
    )
    p.add_argument(
        "--notify", choices=["discord", "slack", "email", "none"],
        default="none",
        help="Canal de notification. Défaut: none (parse + diff seulement).",
    )
    p.add_argument(
        "--dispatch-event", action="store_true",
        help="Poste un repository_dispatch GitHub pour déclencher le pipeline.",
    )
    p.add_argument(
        "--dry-run", action="store_true",
        help="Parse + diff, mais ni notif ni write d'état.",
    )
    p.add_argument(
        "--force-notify", action="store_true",
        help="Notifier même sans nouveauté (smoke-test webhook).",
    )
    p.add_argument(
        "--limit-new", type=int, default=DEFAULT_LIMIT_NEW,
        help=f"Cap notifications par run. Défaut: {DEFAULT_LIMIT_NEW}.",
    )
    p.add_argument(
        "--json", action="store_true",
        help="Sortie résumé JSON sur stdout (pour parsing CI).",
    )
    return p


def _validate_args(args: argparse.Namespace) -> str | None:
    if args.limit_new < 0:
        return "--limit-new doit être ≥ 0"
    return None


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    err = _validate_args(args)
    if err:
        log.error(err)
        return EXIT_BAD_ARGS

    sources = _resolve_sources(args.source)
    if not sources:
        log.error("Aucune source à poller (--source=%s).", args.source)
        return EXIT_BAD_ARGS

    try:
        sender = _build_sender(args.notify)
    except ValueError as exc:
        log.error("Configuration sender invalide : %s", exc)
        return EXIT_BAD_ARGS

    dispatcher = _build_dispatcher() if args.dispatch_event else None

    options = PollOptions(
        sources=tuple(sources),
        state_dir=Path(args.state_dir),
        dry_run=args.dry_run,
        force_notify=args.force_notify,
        limit_new=args.limit_new,
        notify_channel=args.notify,
    )

    try:
        results = run_poll(
            options,
            sender=sender,
            dispatcher=dispatcher,
        )
    except Exception as exc:  # noqa: BLE001
        log.error("Poll RSS a échoué : %s", exc)
        return EXIT_ERROR

    if args.json:
        summary = [
            {
                "sourceId": r.source_id,
                "feedEpisodes": r.feed_episode_count,
                "newEpisodes": [e.title for e in r.new_episodes],
                "notified": r.notified,
                "dispatched": r.dispatched,
                "notModified": r.not_modified,
            }
            for r in results
        ]
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    return EXIT_OK


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
