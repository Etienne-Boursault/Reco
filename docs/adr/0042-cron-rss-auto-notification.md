# ADR 0042 — Cron RSS hebdomadaire + notification nouvel épisode

- **Statut** : Accepté (Phase 3 Vague 2, item roadmap #23, juin 2026)
- **Décideurs** : Etienne (lead), agent backend-dev P3.23
- **Tags** : automation, rss, notifications, ci, autonomie, self-hosting

## Contexte

Le kit Reco est conçu pour vivre **sans serveur permanent** : Astro statique,
pipeline Python on-demand, hébergement Pages/Netlify/Vercel. Or les podcasts
publient un épisode par semaine (en moyenne) et il faut **détecter** ces
nouveaux épisodes pour déclencher l'enrichissement (transcription, extraction
recos, audits).

Aujourd'hui :
- Un humain doit lancer `tools/run_pipeline.py` manuellement.
- Aucune notification quand une source publie.
- Risque : un fork laissé sans entretien stagne pendant des mois sans
  qu'on s'en rende compte.

Le but de l'item #23 : **rendre le poll RSS et la notif autonomes**,
gratuitement, sans dépendance à un service tiers, et sans réintroduire
de serveur 24/7.

## Alternatives envisagées

1. **Polling minute / heure (pipeline complet)** — overkill : les podcasts
   publient hebdomadairement. Gaspillerait des minutes GHA et générerait
   du bruit dans les notifications.
2. **Serveur PHP/Node maintenu** — réintroduit un coût d'hébergement et
   une surface d'attaque. Contraire à l'esprit kit self-hostable
   (ADR 0028 fork-personalization-boundary).
3. **Service RSS→Email tiers** (Zapier, IFTTT, Feedly Pro) — perte
   d'autonomie + données qui transitent par un tiers (RGPD pour un kit
   open-source destiné à être forké en UE = compliqué). Coût mensuel.
4. **Webhook push depuis l'hébergeur RSS** (PodcastIndex, Acast, etc.) —
   pas standardisé, dépendance forte à un fournisseur précis.
5. **Pas de notif — l'humain check manuellement** — incompatible avec
   l'objectif « kit duplicable que d'autres podcasts peuvent reprendre
   sans connaissance technique du backend ».

## Décision

Adopter une chaîne **GitHub Actions cron + Python + webhook Discord** :

### 1. CLI `tools/poll_rss.py`

- Lit `src/content/sources/<id>.json` pour récupérer `rssUrl`.
- Fetcher injectable (`rss.ports.FeedFetcher`). Production :
  `RequestsFeedFetcher` avec support `If-None-Match` / `If-Modified-Since`
  → 304 → skip parse.
- Parser feedparser → `ParsedFeed`/`ParsedEpisode` (dataclasses frozen).
- État JSON sidecar `tools/output/rss/<source>/state.json` (gitignored),
  contenant `schemaVersion=1`, `lastCheckedAt`, `lastEtag`,
  `lastModified`, `seenGuids` (borné LRU à 10 000) et `metadata`.
- Diff `seenGuids` vs flux → liste des nouveaux épisodes, plafonnée par
  `--limit-new` (défaut 5) pour éviter de noyer le canal au premier run.
- Notification : payload différencié par canal
  (`build_discord_embed`/`build_slack_blocks`/`build_plain_text`),
  troncature 256/4096 caractères Discord, échappement markdown du titre.
- Dispatch event GitHub (`repository_dispatch` `reco-new-episode`) si
  `--dispatch-event` — déclenche le futur pipeline complet.
- Lockfile pipeline (cf. `tools/review_lock.py`) acquis avant write
  d'état, sauf en `--dry-run`.

### 2. GitHub Action `.github/workflows/cron-rss.yml`

- Cron `0 6 * * 1` (lundi 06:00 UTC).
- `workflow_dispatch` manuel avec choix de la source et du canal.
- `actions/cache@v4` sur `tools/output/rss/` pour préserver l'état
  entre runs (sinon on re-notifierait tout à chaque exécution).
- Secret `RECO_DISCORD_WEBHOOK` pour l'URL du webhook.
- Permission `actions: write` strictement nécessaire au `repository_dispatch`.

### 3. Architecture modulaire

```
tools/rss/        ports / parser / state / detector
tools/notify/     ports / discord / slack / email / formatter
tools/poll_rss.py CLI runner orchestrant le tout
```

Tous les composants externes (HTTP, SMTP, dispatch GitHub) sont injectables
via constructeur → **aucun appel réseau réel en CI** : les tests utilisent
des fakes (`_FakeFetcher`, `_RecordingSender`, `_FakeSmtp`).

## Conséquences

### Positives
- **Autonomie complète** : aucune dépendance à un service tiers payant.
- **Gratuit** : ~2 minutes GHA / semaine / source — très loin du quota
  gratuit (2000 min/mois).
- **Discord first** : ubiquitaire chez les communautés podcast FR, riche
  rendu embed avec titre/lien/timestamp/footer.
- **Slack + email en option** : symétrie de design, prêts à l'emploi.
- **Idempotence** : re-run sans nouveauté = pas de double notification
  (testé `test_idempotent_second_run_emits_no_notification`).
- **Pas de secret en log** : URL webhook réduite à son host en cas
  d'erreur ; pas de log de payload.
- **Pas de couplage Astro/Python** : tout vit côté `tools/`, le SSG ne
  bouge pas.

### Négatives
- L'état hebdo est stocké en **cache GitHub Actions** (TTL ~7 jours
  d'inactivité) — si le repo dort 8+ jours, on perd l'état et le premier
  re-run risque de re-notifier (mitigation : `--limit-new=5`).
- Le dispatch event nécessite `permissions: actions: write` — élève
  légèrement le risque côté workflow ; mitigation : workflow distinct
  (ne touche pas au code).
- Pas de retry/backoff sur les webhooks (best-effort) — acceptable pour
  une notification info, on log le statut.

## Critères de bascule

- Si **> 100 sources** → état hebdo trop volumineux pour le cache GHA →
  bascule vers un store léger (Redis sur Upstash gratuit, ou commit auto
  dans une branche `state/`).
- Si le délai de notification hebdo devient critique (« je veux savoir
  dans l'heure ») → on baisse la cadence à `0 */6 * * *` ; mêmes
  contraintes, pas de changement de design.

## Liens

- Item roadmap : #23 (Cron RSS auto + notification nouvel épisode)
- ADR 0009 (JSON canonique, écriture atomique)
- ADR 0010 (schemaVersion idempotence)
- ADR 0019 (audit_core, pattern Settings/RunOptions)
- ADR 0023 (re-enrich proactif, philosophie dataset vivant)
- ADR 0024 (CI quality gates — `.github/workflows/ci.yml` pattern)
- ADR 0025 (locales i18n — message FR par défaut)
- ADR 0028 (fork personalization boundary — autonomie du kit)
