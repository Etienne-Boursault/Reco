# Reco — Claude Code

## Rules

- Do what has been asked; nothing more, nothing less
- NEVER create files unless absolutely necessary — prefer editing existing files
- NEVER create documentation files unless explicitly requested
- NEVER save working files or tests to root — use `/src`, `/tests`, `/docs`, `/config`, `/scripts`
- ALWAYS read a file before editing it
- NEVER commit secrets, credentials, or .env files
- Keep files under 500 lines
- Validate input at system boundaries
- Une liste coupée à l'affichage (`[:N]`) l'est selon un ordre voulu (date, gravité), jamais selon l'ordre d'un dictionnaire, et dit combien d'éléments restent (« + N autres ») : famille F23 de `docs/capitalisation-constats.md`
- Une lecture ratée (fichier illisible, dossier absent, fichier sauté) se dit « inconnu », jamais « vide » ni « aucun » : un lecteur qui saute un fichier le compte et le fait remonter. Famille F22 de `docs/capitalisation-constats.md`
- Un `--apercu` n'écrit aucun fichier et n'appelle aucun réseau : son test compare le dossier d'état avant et après, et la documentation ne le dit inerte que s'il l'est. Famille F19 de `docs/capitalisation-constats.md`
- Une réponse lue sous une borne de taille (API, cache) ne transporte que ce qui s'affiche : couper à la source et envoyer le total à part, jamais toute la liste. Famille F25 de `docs/capitalisation-constats.md`
- Un processus détaché lancé depuis un affichage a un plafond (marqueur de lancement, horloge qui recule ou avance comprise) et un test qui prouve qu'un second affichage ne relance rien. Famille F26 de `docs/capitalisation-constats.md`

## Build & Test

- ALWAYS run tests after code changes
- ALWAYS verify build succeeds before committing

```bash
npm run build          # astro build
npm run test:seo       # vitest run
npm run test:a11y:all  # build + a11y + contraste
npm run test:og        # vitest run tests/og
```
