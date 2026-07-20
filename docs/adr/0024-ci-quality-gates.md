# ADR 0024 — CI quality gates (a11y + contraste + pa11y)

- Statut : Acceptée
- Date : 2026-06-10
- Décideurs : équipe Reco
- Lié à : ADR 0022 (a11y AA), ADR 0030 (tokens)

## Contexte

Les checks a11y (`test:a11y`, `test:contrast`) existaient comme scripts
npm mais n'étaient pas exécutés en CI. Régression possible silencieuse :
un PR pouvait casser le skip-link ou le contraste sans qu'aucun garde-fou
ne lève la main.

Par ailleurs, les checks statiques ratent les violations dynamiques
(ARIA appliqué côté JS, état au focus, ordre Tab logique). Un audit
dynamique est nécessaire pour AA.

## Options étudiées

| Option | Pro | Contra |
|---|---|---|
| **Lighthouse CI** (lhci) | Score consolidé, perf + a11y + SEO | Install lourd (puppeteer), config verbeuse, score parfois bruité |
| **pa11y-ci** | Wrapper axe-core, install léger, configurable par page | Pas de score global, sortie moins « jolie » |
| **@axe-core/playwright** | Très précis | Nécessite Playwright (gros download CI) |

## Décision

**pa11y-ci** choisi pour l'audit dynamique. Justifications :

- Install ≈ 30 MB vs ≈ 250 MB pour Playwright.
- Axe-core sous le capot (même moteur que Lighthouse a11y) → couverture
  équivalente sur la partie a11y stricte.
- Configurable par page (3 pages clés : `/`, `/<source>/`,
  `/<source>/episode/<guid>/`).
- Mode `continue-on-error: true` au démarrage pour calibrer le baseline
  sans bloquer les PRs. Bascule en bloquant une fois 0 violation.

Workflow CI : `.github/workflows/a11y.yml`, déclenché sur `push main` et
`pull_request` ciblant `src/**` / `tests/a11y/**`.

Deux jobs :

1. **a11y** (bloquant) — `npm run test:a11y` + `npm run test:contrast`.
2. **pa11y** (informatif) — sert le `dist/` via `http-server`, lance
   pa11y-ci sur 2 pages.

Aucun secret n'est utilisé. Permissions GitHub Actions : `contents: read`
uniquement.

## Conséquences

### Positives

- Régression a11y rattrapée dès l'ouverture d'un PR (≤ 2 min de CI).
- Le job pa11y informatif accumulera un baseline visible → on saura
  quand le bascule en bloquant.
- Pas de secret ni de coût additionnel (GitHub Actions free tier).

### Négatives

- Le job pa11y ajoute ≈ 1 min de CI. Acceptable pour un kit qui mérge
  occasionnellement.
- Si pa11y change ses règles axe-core, le baseline peut bouger. À
  surveiller à chaque montée de version.

### Notes

- Lighthouse a11y reste mesuré **manuellement** au release-time (cible
  ≥ 95 sur 3 pages clés). Documenté dans `docs/fork-guide.md`.
- L'ajout futur de `lhci` reste possible (les deux outils sont
  complémentaires) si on veut un score consolidé sur perf + SEO.
