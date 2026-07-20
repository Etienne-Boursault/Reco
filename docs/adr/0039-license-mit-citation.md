# ADR 0039 — Licence MIT + citation, gouvernance contributive, CI publique

- Statut : Acceptée
- Date : 2026-06-11
- Décideurs : équipe Reco
- Lié à : ADR 0024 (CI a11y), ADR 0028 (fork boundary), ADR 0029 (fonts licenses)

## Contexte

La Phase 2 du projet est clôturée (2974 pytest + 217 vitest, build 5791
pages OK). La Phase 3 ouvre Reco à l'extérieur : forks de podcasts
tiers, contributions externes, dépôt public à terme. Trois manques
sont identifiés :

1. **Cadre légal absent** — pas de `LICENSE` à la racine. Sans licence
   explicite, le code est par défaut « tous droits réservés », ce qui
   bloque tout fork légitime.
2. **Pas de gouvernance contributive documentée** — pas de
   `CONTRIBUTING.md`, pas de Code of Conduct, pas de politique de
   divulgation de vulnérabilités. Les contributeurs ne savent ni
   comment ouvrir une PR ni à qui reporter une faille.
3. **CI partielle** — seul `a11y.yml` tourne (cf. ADR 0024). Les tests
   Python (2974) et Vitest (217) ne sont pas garde-foutés en CI
   publique. Régression possible sur main sans alerte.

L'objectif : poser un socle « kit open-source » avant l'ouverture
publique du dépôt et l'annonce.

## Options étudiées

### Choix de licence

| Option | Pro | Contra |
|---|---|---|
| **MIT** | Adoption max, lisibilité, compatible Apache/GPL en aval | Pas de clause brevet, pas de copyleft |
| **MIT + ATTRIBUTION REQUEST** (choisi) | MIT + nudge éthique pour crédit | La clause « non-binding » n'est pas opposable |
| **Apache 2.0** | Clause brevet explicite, NOTICE standard | Complexité (en-têtes par fichier) pour bénéfice marginal sur ce projet |
| **GPL-3.0** | Forks restent libres | Bloque les forks commerciaux légitimes (radios privées, médias) |
| **AGPL-3.0** | Couvre l'hébergement SaaS | Idem GPL + dissuade encore plus de l'auto-héberger |
| **CC-BY-SA 4.0** | Crédit obligatoire | Inadaptée au code source (pensée pour œuvres créatives) |

### CI publique

| Option | Pro | Contra |
|---|---|---|
| **GitHub Actions** (choisi) | Gratuit, intégré, déjà utilisé pour `a11y.yml` | Couplage à GitHub |
| GitLab CI | Auto-hébergeable | Coût migration, exode des contributeurs |
| Circle/Travis | Historique | Free tier réduit, friction setup |

## Décision

### Licence — MIT avec ATTRIBUTION REQUEST non-binding

On retient **MIT** pour maximiser l'adoption et la compatibilité, et
on ajoute une clause `ATTRIBUTION REQUEST (non-binding)` qui demande
(sans contraindre) qu'un fork hébergé publiquement crédite le projet
d'origine. Cette clause est juridiquement non-opposable, c'est
explicite ; elle sert de signal éthique aligné avec le manifeste.

### Métadonnées de citation

- `CITATION.cff` (Citation File Format 1.2) pour usage académique et
  reconnaissance par GitHub (badge « Cite this repository »).
- `NOTICE` à la racine pour reconnaître les composants tiers
  redistribués (Inter font OFL 1.1 notamment, cf. ADR 0029).

### Gouvernance contributive

- `CONTRIBUTING.md` — démarrage, tests, branches, commits
  (Conventional Commits + footer `ADR-XXXX`), processus ADR,
  checklist PR.
- `CODE_OF_CONDUCT.md` — Contributor Covenant 2.1, contact placeholder
  `conduct@source-internet.fr`.
- `SECURITY.md` — canaux (GitHub Security Advisories prioritaire,
  e-mail en repli), fenêtre 48 h / 7 j / 30 j.
- `.github/ISSUE_TEMPLATE/` — `bug_report`, `feature_request`,
  `documentation`, `fork_help` (issue dédiée pour les forkeurs).
- `.github/PULL_REQUEST_TEMPLATE.md` — checklist tests + ADR + a11y.

### CI publique

Trois workflows complètent `a11y.yml` existant :

1. **`ci.yml`** (bloquant) — sur `push main` et `pull_request` :
   `lint-python` (ruff, non bloquant tant que config absente),
   `test-python` (pytest matrix Ubuntu + macOS),
   `lint-js` (`astro check`, non bloquant),
   `test-vitest` (SEO + OG),
   `build` (SSG avec `SITE_URL=https://example.com`),
   `ci-summary` (gate agrégé).
2. **`release.yml`** — sur tag `v*.*.*` :
   `changelog-check`, `build-and-test`, `build-docker` (GHCR, conditionné
   à la présence d'un Dockerfile pour ne pas casser tant que Dev #18
   n'a pas livré), `github-release` (notes auto).
   Pas de publication npm pour l'instant (nom à confirmer).
3. **`security.yml`** — hebdo + sur PR touchant les manifestes :
   `npm audit`, `pip-audit`, `dependency-review-action` sur PR.

### Garde-fous CI

- `permissions: contents: read` par défaut sur tous les workflows ;
  `release.yml` escalade à `contents: write` + `packages: write` pour
  les seuls jobs concernés.
- `concurrency` configuré pour annuler les vieux runs PR.
- Caches `npm` et `pip` activés sur tous les jobs.
- `secrets.GITHUB_TOKEN` uniquement ; aucun secret métier en CI.
- `continue-on-error` sur les jobs informatifs (lint Python sans
  config, audit security, npm audit), à durcir progressivement.

### Dependabot

`.github/dependabot.yml` — PR hebdo pour npm (groupé : astro,
dev-tooling) et pip, mensuel pour github-actions et docker.

## Conséquences

### Positives

- Cadre légal clair → forks et redistributions deviennent légitimes.
- Citation académique standardisée (CFF reconnu par Zenodo / GitHub).
- Contributeurs onboardés en < 5 min via `CONTRIBUTING.md`.
- Régressions Python / build / SEO rattrapées en CI dès la PR.
- Failles de sécurité ont un canal privé documenté.
- Maintenance des dépendances déléguée à Dependabot.

### Négatives

- La clause `ATTRIBUTION REQUEST` n'est pas opposable. Risque résiduel
  de forks sans crédit (mitigation : visibilité communautaire).
- La CI matrix (Ubuntu + macOS) double le temps minute Actions sur
  `test-python`. Acceptable sur free tier tant que le rythme de PR
  reste raisonnable.
- Le nom de package npm `reco` n'est pas réservé : si on publie un
  jour, il faudra probablement scope (`@source-internet/reco`).

### Critères de bascule

- **Abus massif de forks sans crédit** → envisager un CLA (Contributor
  License Agreement) ou bascule Apache 2.0 (clause brevet) — pas de
  bascule GPL/AGPL (incompatible avec l'objectif kit ré-utilisable).
- **CI lente ou flaky** → retirer macOS de la matrix `test-python`,
  garder Ubuntu only.
- **Lint Python stabilisé** → retirer `|| true` sur le job
  `lint-python` (rendre bloquant).
- **Publication npm décidée** → ajouter `publish-npm` dans
  `release.yml` avec `secrets.NPM_TOKEN`.
- **Email `conduct@` / `security@`** → réserver et configurer dans
  l'organisation avant l'ouverture publique du dépôt.

## Notes

- ADR 0024 (CI a11y) reste en vigueur. `ci.yml` ne duplique pas les
  jobs a11y.
- L'image Docker dans `release.yml` est conditionnée par
  `hashFiles('Dockerfile') != ''` pour cohabiter avec Dev #18 (Vague 1
  Phase 3) qui livrera le Dockerfile.
- Le placeholder e-mail (`conduct@`, `security@source-internet.fr`)
  doit être remplacé avant le passage en dépôt public.
