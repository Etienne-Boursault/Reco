# Contribuer à Reco

Merci de l'intérêt que vous portez au projet. Reco est un kit
open-source FR-first pour publier un catalogue de recommandations
issues de podcasts. Toute contribution (code, doc, design, retours)
est bienvenue.

Avant de contribuer, merci de lire et respecter notre
[Code of Conduct](./CODE_OF_CONDUCT.md).

## Sommaire

1. [Démarrage rapide](#démarrage-rapide)
2. [Forker pour ajouter un podcast](#forker-pour-ajouter-un-podcast)
3. [Lancer les tests](#lancer-les-tests)
4. [Stratégie de branches](#stratégie-de-branches)
5. [Convention de commits](#convention-de-commits)
6. [Processus ADR](#processus-adr)
7. [Checklist PR](#checklist-pr)
8. [Style de code](#style-de-code)
9. [Signaler un bug / proposer une feature](#signaler-un-bug--proposer-une-feature)
10. [Vulnérabilité de sécurité](#vulnérabilité-de-sécurité)

## Démarrage rapide

### Option Docker (recommandée pour reviewers)

```bash
docker compose up
# site dispo sur http://localhost:4321
```

### Option locale (Node 20 + Python 3.12)

```bash
# Frontend
npm ci
npm run dev

# Pipeline Python
python -m venv .venv
source .venv/bin/activate   # Windows : .venv\Scripts\activate
pip install -r tools/requirements.txt
```

## Forker pour ajouter un podcast

Voir [`docs/fork-guide.md`](./docs/fork-guide.md) — guide pas-à-pas
pour héberger votre propre instance avec un autre podcast (RSS Acast,
YouTube, etc.).

Points clés :
- Configurer `tools/sources.yaml` (SSOT, voir ADR 0001).
- Lancer `tools/reco_init.py` (assistant interactif).
- Respecter [`docs/manifeste-ethique.md`](./docs/manifeste-ethique.md).

## Lancer les tests

```bash
# Python (≈ 2974 tests)
pytest tests/

# JS / Vitest (SEO, OG, ≈ 217 tests)
npm test
npm run test:seo

# A11y (statique + contraste WCAG AA)
npm run test:a11y
npm run test:contrast

# Build SSG (≈ 5790 pages)
SITE_URL=https://example.com npm run build
```

La CI publique (cf. `.github/workflows/ci.yml`) rejoue ces étapes
sur chaque PR.

## Stratégie de branches

- `main` est protégée — pas de push direct, tout passe par PR.
- Une branche par feature/fix : `feat/<slug>`, `fix/<slug>`,
  `docs/<slug>`, `chore/<slug>`.
- Versionning : [SemVer](https://semver.org/lang/fr/) (`vMAJOR.MINOR.PATCH`).
  Bascule de majeure réservée aux ruptures (cf. ADR concernée).

## Convention de commits

[Conventional Commits](https://www.conventionalcommits.org/fr/) :

```
type(scope): résumé court à l'impératif

Corps optionnel : pourquoi, et pas seulement quoi.

ADR-0039
```

Types : `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `perf`,
`a11y`, `seo`, `ci`.

Footer `ADR-XXXX` si le commit met en œuvre une décision
architecturale enregistrée.

## Processus ADR

Toute décision structurelle (techno, schéma, contrat d'API, ruptures
de compat) passe par un ADR dans `docs/adr/`. Voir
`docs/adr/template.md` et les ADR 0001-0036 pour le style.

Une PR qui change un comportement structurel **doit** inclure son ADR.

## Checklist PR

Avant de demander une review, vérifier :

- [ ] Tests Python verts (`pytest tests/`).
- [ ] Tests JS / Vitest verts (`npm test`).
- [ ] A11y : `npm run test:a11y` + `npm run test:contrast` verts.
- [ ] Build SSG OK (`npm run build`).
- [ ] Docs à jour (README, fork-guide si impact public).
- [ ] ADR ajouté si décision structurelle.
- [ ] Pas de secret commité (`tools/.env`, clés API…).
- [ ] Breaking change ? Mentionné explicitement dans la description PR.

Le template `.github/PULL_REQUEST_TEMPLATE.md` reprend cette checklist.

## Style de code

### Python

- Cible Python 3.12.
- `ruff` pour le lint (config dans `pyproject.toml` à terme).
- `black` pour le formatage (line-length 100).
- Type-hints sur les fonctions publiques.

### TypeScript / Astro

- Prettier (config par défaut, 2 espaces).
- Pas de `any` injustifié.
- Composants Astro `< 500 lignes` (règle projet).

## Signaler un bug / proposer une feature

Utiliser les templates d'issues dans `.github/ISSUE_TEMPLATE/` :

- `bug_report` — un bug reproductible.
- `feature_request` — une idée d'évolution.
- `documentation` — une coquille ou un manque dans la doc.
- `fork_help` — vous tentez de forker pour votre podcast et bloquez.

## Vulnérabilité de sécurité

**Ne pas** ouvrir d'issue publique pour une faille de sécurité.
Suivre la procédure dans [`SECURITY.md`](./SECURITY.md).
