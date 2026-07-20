# Pull Request

## Résumé

<!-- 1-3 phrases : quoi et pourquoi. -->

## Issue / contexte

Closes #
<!-- Lien vers issue ou ADR. -->

## Type

- [ ] feat
- [ ] fix
- [ ] docs
- [ ] refactor
- [ ] test
- [ ] chore / ci

## Checklist

- [ ] Tests Python verts (`pytest tests/`)
- [ ] Tests JS verts (`npm test` / `npm run test:seo`)
- [ ] A11y verte (`npm run test:a11y` + `npm run test:contrast`)
- [ ] Build SSG OK (`SITE_URL=https://example.com npm run build`)
- [ ] Documentation mise à jour si nécessaire (README, fork-guide…)
- [ ] ADR ajouté si décision structurelle (`docs/adr/`)
- [ ] Pas de secret commité (`tools/.env`, clés API)
- [ ] Breaking change ? Si oui, décrit ci-dessous.

## Breaking changes

<!-- Décrire l'impact et la migration. Sinon : « Aucun ». -->

## Notes pour le reviewer

<!-- Pièges connus, choix discutables, screenshots a11y/SEO, etc. -->
