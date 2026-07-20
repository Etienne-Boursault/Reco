# ADR 0030 — Design tokens & theming multi-source

> **Renumérotation 2026-06-11** : initialement créé avec le numéro 0020 mais 0020 était déjà pris par `0020-sqlite-cache-fts5.md` (Dev #8 Phase 2). Renommé en 0030 par la coordination finale Vague 1.

- Statut : Acceptée
- Date : 2026-06-10
- Décideurs : équipe Reco
- Lié à : ADR 0022 (a11y AA), ADR 0001 (sources SSOT)

> Note : ce numéro (0020) comble le gap de la numérotation ADR
> (0019 → 0021). Les ADRs 0024+ restent réservés.

## Contexte

La palette de couleurs vivait dans deux endroits :

- `src/styles/global.css` — variables CSS `--bg`, `--surface`, etc.
- `tests/a11y/check_contrast.mjs` — tableau JS hardcodé des hex.

Conséquences :

- **Duplication** : modifier le thème par défaut imposait deux endroits à
  toucher. Risque silencieux que `check_contrast.mjs` valide une palette
  qui n'est plus celle du site.
- **Multi-source non testé** : chaque source (`src/content/sources/*.json`)
  peut surcharger `theme.colors` via `<Layout theme={...}>`. Aucun filet
  ne validait que la palette d'une nouvelle source respectait WCAG AA.
- **Fork-unfriendly** : un fork qui change uniquement les couleurs d'une
  source n'avait aucun retour automatique sur le contraste.

## Décision

Création de `src/styles/tokens.ts` comme **single source of truth** de la
palette par défaut ET de la matrice de cas de contraste WCAG AA :

```ts
export const defaultTheme: ThemeColors = {
  bg: '#0e0e10', surface: '#17171c', text: '#f6f4ee',
  muted: '#9a99a3', accent: '#ffd23f', accentText: '#0e0e10',
};
export const contrastCases: ContrastCase[] = [
  { name: 'texte / bg', fg: 'text', bg: 'bg', min: 4.5 },
  // …
];
```

`check_contrast.mjs` :

1. Parse `tokens.ts` (regex sur l'objet littéral exporté — pas de runtime
   TS, donc pas de dépendance ajoutée).
2. Valide les `contrastCases` sur `defaultTheme`.
3. **Boucle sur `src/content/sources/*.json`** : extrait `theme.colors` et
   ré-applique exactement les mêmes cas.
4. Exit 1 dès la première violation, sur n'importe quelle source.

Les valeurs CSS dans `global.css` restent en cohérence avec `tokens.ts`
mais ne sont PAS générées build-time pour l'instant — c'est un trade-off
volontaire (un build-time generator ajouterait un script, peu de valeur
tant que la palette par défaut bouge rarement). La revue PR exige que
toute modif de palette touche les deux fichiers en même temps (un check
diff manuel suffit pour un kit aussi petit).

## Conséquences

### Positives

- Zéro duplication entre les tests et la SSOT.
- Chaque nouvelle source forcera une validation AA → un fork qui ajoute
  son podcast verra immédiatement si sa palette casse le contraste.
- Forward-compat avec un éventuel générateur CSS build-time (le format
  des tokens est stable).

### Négatives

- Parser regex pour `tokens.ts` : si on déplace la déclaration vers un
  format différent (ex. fonction `getTheme()`), il faudra l'adapter.
  Mitigation : un test unitaire futur sur `check_contrast.mjs` pourrait
  charger l'objet via `tsx` une fois Node 22 + `--experimental-strip-types`
  stable.

### Notes

- Le contrat « les valeurs hex dans `global.css` = `tokens.ts` » est
  documenté en haut de `global.css`. Toute divergence sera détectée par
  les premiers retours utilisateur·rices (et c'est une bonne raison
  d'ajouter un test plus tard).
- Schéma `sources` Zod : `theme.colors` valide déjà la présence des
  champs requis ; le check contraste ajoute la dimension qualitative.
