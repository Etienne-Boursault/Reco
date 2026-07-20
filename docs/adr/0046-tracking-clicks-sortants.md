# ADR 0046 — Tracking clics sortants (validation effet réseau)

- Statut : Accepté
- Date : 2026-06-12
- Phase : 4 — item #25 (validation « les gens cliquent »)
- Voir aussi : ADR 0034 (signalements visiteurs, pattern IP hashée+saltée),
  ADR 0040 (manifeste éthique — pas de tracker tiers, RGPD),
  ADR 0042 (cron RSS + notifications).

## Contexte

Reco est un kit duplicable qui agrège des recommandations vers des plateformes
externes (TMDB, Spotify, IMDB, YouTube, librairies indépendantes…). On sait
qu'on **publie** des liens. On ne sait pas si les visiteurs **cliquent** dessus.
Sans ce signal :

- impossible d'évaluer si une recommandation a une valeur ajoutée réelle,
- impossible d'arbitrer entre catégories (films / livres / musique / podcasts)
  sur ce qui « marche »,
- aucun moyen de prouver à des fork-maintainers que leur travail trouve son
  public,
- aucun moyen d'identifier des liens cassés implicitement (zéro clic anormal).

Le projet refuse explicitement (ADR 0040) :

- les **cookies** de traçage,
- les **trackers tiers** (GA, Hotjar, Facebook Pixel, etc.),
- le **fingerprinting**,
- l'IP en clair.

Il faut donc un mécanisme **privacy-first, self-hostable, RGPD-friendly** qui
mesure le nombre de clics par catégorie / par reco / par URL — sans jamais
identifier un visiteur.

## Décision

On ajoute un endpoint `POST /api/click` (+ fallback pixel `GET`) servi par
Astro en mode hybrid SSR, alimenté par un composant `OutboundLink.astro` qui
remplace les `<a target="_blank">` dans `RecoCard` et `MentionsTimeline`.

### Architecture

```
src/lib/tracking/
  types.ts        — ClickEvent, ClickCategory, CLICK_LIMITS
  validator.ts    — Zod schema (url http(s), max 2 KiB, category enum, sourceId/recoId slugs)
  storage.ts      — append JSONL atomique (open 'a' + writeSync + fsync)
  rateLimit.ts    — 60 clics/min/IP, hash SHA-256 salt + IP, GC opportuniste
  handler.ts      — orchestration (Sec-GPC → Origin → honeypot → Zod → RL → write)
src/pages/api/click.ts  — endpoint POST JSON + GET pixel 1×1
src/components/OutboundLink.astro  — wrapper anchor avec data-track="click"
src/layouts/Layout.astro  — script global délégant `click` → sendBeacon
tools/aggregate_clicks.py  — CLI agrégation (--source --by --from-date --to-date)
tools/output/clicks/<sourceId>/<YYYY-MM-DD>.jsonl  — storage (gitignored)
```

### Format JSONL persisté

Un fichier par (sourceId, jour UTC), append-only, une ligne par clic :

```json
{"ts":"2026-06-12T10:42:00.000Z","url":"https://themoviedb.org/movie/42","category":"tmdb","sourceId":"un-bon-moment","recoId":"ubm-0001","ref":"/un-bon-moment/episode/abc"}
```

Aucune IP, aucun cookie, aucun User-Agent. Le champ `ref` est **réduit au
path** côté serveur (`sanitizeRef`) — pas de query string, pas de hash.

### Garde-fous (defense in depth)

1. **`Sec-GPC: 1`** (Global Privacy Control) → 204 silencieux, aucune écriture.
   Le script client court-circuite aussi sur `navigator.globalPrivacyControl`.
2. **Origin/Referer same-origin** → 403 sinon (CSRF protection).
3. **Honeypot `bot_trap`** → 204 silencieux (bot croit avoir réussi).
4. **Validation Zod stricte** (`.strict()`) → rejette tout champ inconnu,
   URL non-http(s), category hors enum, sourceId non-slug.
5. **Rate-limit IP hashée** : 60 clics/min, fenêtre glissante in-memory.
   Salt via `TRACKING_IP_SALT` (≥ 16 chars) sinon random au boot — cohérent
   avec `reports/rateLimit.ts` (ADR 0034).
6. **Localhost exempté** pour dev/test (cohérent ADR 0034).
7. **Atomicité ligne JSONL** : open(`a`) + write < PIPE_BUF + fsync. Garde-fou
   `throw` si une ligne dépasse 4 KiB (jamais en pratique : URL ≤ 2 KiB +
   metadata bornée).
8. **Path traversal** : `assertSlug` sur `sourceId`/`recoId` avant tout
   `join()` — pattern identique à `reports/storage.ts`.
9. **CSP-friendly** : le script de tracking vit dans un `<script>` Astro
   bundlé (pas d'inline handler `onclick`).
10. **Pas d'IP en clair** : SHA-256(salt || ip) tronqué 12 bytes,
    uniquement pour le rate-limit in-memory — jamais persisté.

### Composant `OutboundLink.astro`

```astro
<OutboundLink
  href="https://themoviedb.org/movie/42"
  category="tmdb"
  sourceId="un-bon-moment"
  recoId="ubm-0001"
>
  ...
</OutboundLink>
```

Rend un `<a target="_blank" rel="noopener noreferrer external"
data-track="click" data-category="..." data-source-id="..." data-reco-id="...">`.
Le script global dans `Layout.astro` délègue `click` sur tout
`[data-track="click"]` et envoie un beacon JSON à `/api/click`.

### Catégorisation auto dans RecoCard

`categorizeUrl(url)` mappe :

- `themoviedb.org` / `tmdb.*` → `tmdb`
- `spotify.com` → `spotify`
- `imdb.com` → `imdb`
- `youtube.com` / `youtu.be` → `youtube`
- `placedeslibraires`, `lalibrairie`, `leslibraires`, `bookshop`, `librairie`
  → `library`
- tout le reste → `other`

Choix : la catégorisation côté composant évite de la dupliquer côté serveur ou
côté JS. Si elle évolue, c'est une seule ligne à modifier.

## Modes de déploiement

| Mode             | Endpoint POST | Pixel GET | Tracking effectif      |
| ---------------- | ------------- | --------- | ---------------------- |
| `output: 'static'` (default kit) | absent  | absent | **désactivé** — beacon échoue silencieusement, le clic suit son cours |
| `output: 'hybrid'` + adapter     | actif   | actif  | actif — JSONL append par jour |

C'est intentionnellement **opt-in** : un fork qui ne veut pas de tracking
n'a rien à faire (mode static par défaut). Pour activer :

1. installer `@astrojs/node` (ou Vercel/Netlify),
2. basculer `output: 'hybrid'` dans `astro.config.mjs`,
3. ajouter `export const prerender = false;` en tête de `src/pages/api/click.ts`,
4. (optionnel) définir `TRACKING_IP_SALT` (≥ 16 chars) pour persister le salt
   entre redéploiements,
5. (optionnel) définir `TRUSTED_PROXIES` (CSV) si derrière un proxy.

## Alternatives évaluées

| Option                | Pour                              | Contre                                                       |
| --------------------- | --------------------------------- | ------------------------------------------------------------ |
| **Plausible self-host** | Mature, dashboard prêt         | Conteneur + DB à opérer, overhead pour un kit duplicable     |
| **Matomo self-host**    | Riche                           | Lourd, cookies par défaut (RGPD), antithèse du kit            |
| **GA / Plausible cloud**| Gratuit                         | Tracker tiers, conflit direct avec ADR 0040 manifeste éthique |
| **Pas de tracking**     | Zéro complexité                 | Perte du signal de validation (item #25 non livré)            |
| **JSONL maison (retenu)** | Privacy by design, self-hostable, kit-friendly, agrégation Python triviale | Pas de dashboard built-in (rendu via `/stats` item #26 ou CLI) |

## Conséquences

### Positives

- Signal de validation enfin disponible (item #25 livré).
- Aucun cookie, aucun tracker tiers, aucune IP en clair → RGPD-friendly.
- `Sec-GPC` respecté → conforme aux signaux d'opt-out moderne.
- Dégradation gracieuse (mode static → tracking off, le site reste fonctionnel).
- Storage trivial à inspecter (`cat tools/output/clicks/.../2026-06-12.jsonl`).
- Format JSONL portable vers ClickHouse / DuckDB plus tard si besoin.

### Négatives

- Seuls les clics sont mesurés, pas les vues — donc pas de taux de conversion
  granulaire (acceptable : le signal qualitatif suffit pour l'item #25).
- Mode static = pas de tracking (par design, mais à documenter clairement
  pour les fork-maintainers).
- Rate-limit in-memory perdu au redéploiement (déjà acceptable cf. ADR 0034).
- Pas de dashboard built-in — il faut lancer `tools/aggregate_clicks.py` ou
  attendre l'item #26 (`/stats` SSR).

## Critères de bascule

- Si > **10 k clics/jour** sur une source → migrer vers ClickHouse ou
  Plausible self-host (le JSONL append reste tenable jusqu'à ~100 k/jour mais
  l'agrégation devient lente).
- Si demande de dashboard temps réel → soit Plausible self-host, soit un
  endpoint SSR qui lit le JSONL du jour courant (compatible item #26).
- Si plusieurs forks veulent un schema commun → publier `types.ts` comme
  package npm interne.

## Notes d'implémentation (Pass B — fixes senior + archi)

### Settings par source (R-P1-13)

`src/lib/tracking/settings.ts` expose `TrackingSettings.fromSourceExtra(extra)`
qui lit `extra.tracking` du registry (pattern Phase 3.5 `audit_core`) :

```ts
extra: {
  tracking: {
    windowMs: 30_000,        // override rate-limit window
    maxHits: 30,             // override rate-limit max
    categoryOverrides: {     // mapping hostname → ClickCategory
      "partner.example": "tmdb",
    },
  },
}
```

Si absent ou invalide → `DEFAULT_TRACKING_SETTINGS` (60 s / 60 hits, pas
d'override). L'API ne throw jamais sur input mal formé.

### `categorizeUrl` centralisé (R-P1-16, L25-27)

Le helper `categorizeUrl(href, overrides?)` est désormais exposé par
`lib/tracking/settings.ts`. Il est appelé automatiquement par
`OutboundLink.astro` quand la prop `category` n'est pas fournie. Si on doit
modifier le mapping (nouveau partenaire, nouvelle librairie indépendante),
une seule ligne à toucher (`DEFAULT_HOST_MAP`).

### Injection de stockage (R-P1-14)

`handleClick({ storage })` accepte n'importe quel `ClickStorage`
(`{ append(event): void }`). Le default est `JsonlClickStorage` (FS local
JSONL). Cette indirection permet :

- d'écrire un mock en test sans tâter du FS,
- de plugger un backend DuckDB / ClickHouse plus tard sans modifier le
  handler ni l'endpoint,
- de désactiver tout le storage en mode dry-run.

### CSRF strict POST + Referer toléré GET pixel (H25-3 / H25-6)

- `POST /api/click` : seul `Origin` est accepté pour le check same-origin.
  Referer n'est **PAS** un fallback CSRF (`allowReferer: false`).
- `GET /api/click` (pixel) : `Referer` toléré (`allowReferer: true`) car
  certains UAs ne joignent pas `Origin` sur des navigations `<img>`. Si la
  vérification échoue, l'endpoint **retourne quand même le GIF** mais
  **n'écrit pas** la ligne JSONL (UX consistante, pas de tracking).

### Garde-fou ts (H25-7)

Le handler rejette en 400 si `new Date(now).getUTCFullYear()` est `NaN`
(input `Number.NaN` / `Infinity`). Évite d'écrire un `ts: "Invalid Date"`
dans le JSONL.

### Compteurs in-memory (R-P3-22)

`src/lib/tracking/metrics.ts` expose :

```ts
recordClickStatus(status: number): void
getClickMetrics(): { total: number, byStatus: Record<string, number> }
resetClickMetrics(): void
```

Dump prévu via futur endpoint admin Phase 4.5 (`/api/_admin/metrics`).
Pas de persistance — RAZ au cold-start (cohérent rate-limit in-memory).

### Critères bascule RedisRateLimiter (R-P1-15)

Le rate-limit in-memory est suffisant tant qu'on est :
- mono-replica (1 instance Node),
- avec une durée de vie process ≥ window (60 s).

Bascule vers un store partagé (Redis, Upstash) RECOMMANDÉE si :
- multi-replica (load balancer + ≥ 2 instances) → un client peut taper
  N × maxHits avant qu'une instance ne déclenche le blocage,
- serverless avec cold-start fréquent (Vercel free / Netlify functions) :
  chaque instance fraîche redémarre à zéro, le rate-limit est de facto
  désactivé (cf. M25-14 ci-dessous),
- > 10 k clics/jour sur une source.

Interface `RateLimiter` (`{ check, reset, size }`) garde l'API existante
— le swap consiste à fournir une implémentation `RedisRateLimiter` qui
respecte ce contrat (pattern strategy).

### Cold-start serverless = rate-limit ↘ (M25-14)

Sur un déploiement Vercel free / Netlify functions, le process Node est
recyclé fréquemment (~quelques minutes d'idle). Chaque nouveau process
recharge un store rate-limit vide → le rate-limit n'est effectif que
dans la fenêtre d'une instance « tiède ». C'est ACCEPTABLE pour le seuil
60/min (un bot sérieux dégrade quand même), mais à documenter aux
forkers : pour un rate-limit strict en serverless, passer en Redis
(cf. R-P1-15).

### Atomicité JSONL sous Windows (R-P2-18)

POSIX garantit qu'un `write(fd, buf, n)` avec `O_APPEND` est atomique si
`n < PIPE_BUF` (4 KiB Linux). Windows NTFS n'offre PAS cette garantie
formelle. En pratique, `WriteFile` sur un handle ouvert en `FILE_APPEND_DATA`
est atomique pour un buffer petit, mais le contrat est implementation-defined.
Garde-fous appliqués :

1. `Buffer.byteLength(line, 'utf8')` ≤ 4000 (H25-5) — pas de calcul approximatif
   `line.length` qui sous-estime les non-ASCII.
2. `fsyncSync(fd)` après chaque write — durabilité confirmée même si le
   process crash juste après.

Si on observe une corruption sur déploiement Windows : envelopper l'append
dans un mutex applicatif (single-writer per file).

### IP determination & TRUSTED_PROXIES (M25-17 / M25-18)

`TRUSTED_PROXIES` (CSV) est parsé une fois au load du module. Stratégie :

- si `clientAddress ∈ TRUSTED_PROXIES` et XFF présent → first XFF token,
- si `clientAddress ∈ TRUSTED_PROXIES` mais XFF absent → fallback
  `clientAddress` (health-check interne, tests…),
- sinon → `clientAddress` directement (proxy non-trusted, on ignore XFF).
- si `clientAddress` est `null` (Astro prerendered, env mal configurée)
  → POST renvoie 204 silencieux (cf. C25-2 Pass A).

### Cohort réservé (R-P2-19)

Le type `ClickEvent` réserve un champ optionnel `cohort?: string | null`
(max 32, slug). Pas encore exposé côté API publique mais accepté par le
schéma JSONL → forward-compatible si on ajoute un découpage A/B simple
plus tard. Privacy : un cohort est un slug opaque, **pas** un identifiant
réversible vers un visiteur.

### Dépendances inter-Fixer

- **MX-1 (Fixer Cross / Layout)** : `tracking-script` ne doit PAS être
  injecté sur les pages `noindex` (cohérent ADR 0021 SEO). Cible :
  `src/layouts/Layout.astro` — hors zone de ce fixer (M25-19).
- **TRACKING_IP_SALT doc** : à ajouter dans `docs/fork-guide.md` (zone
  Fixer Cross / R-P2-20).

## Tests

- `tests/tracking/test_validator.test.ts` — Zod schema (8 cas)
- `tests/tracking/test_storage.test.ts` — append, rotation daily, path traversal,
  read corrompu (10 cas)
- `tests/tracking/test_rate_limit.test.ts` — fenêtre glissante, localhost
  exempt, reset, IPs distinctes (6 cas)
- `tests/tracking/test_handler.test.ts` — Sec-GPC truthy, origin strict POST,
  Referer toléré GET pixel, honeypot, validation, rate-limit, happy path,
  sanitize ref, ts NaN, storage injecté (24 cas)
- `tests/tracking/test_settings.test.ts` — fromSourceExtra, categorizeUrl,
  overrides (10 cas)
- `tests/tracking/test_metrics.test.ts` — compteurs par status, reset (3 cas)
- `tests/test_aggregate_clicks.py` — iter, aggregate par axe, CLI smoke, CSV,
  `--csv-include-dimension`, skip URL absente (18 cas pytest)

Couverture cible : 100 % sur les nouveaux fichiers `src/lib/tracking/*` et
`tools/aggregate_clicks.py`.
