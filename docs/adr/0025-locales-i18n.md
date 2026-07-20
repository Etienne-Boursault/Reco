# ADR 0025 — Locales & stratégie i18n minimale

- Statut : Acceptée
- Date : 2026-06-10
- Décideurs : équipe Reco
- Lié à : ADR 0022 (a11y), ADR 0001 (sources SSOT)

## Contexte

Plusieurs strings d'UX et d'a11y étaient hardcodées en français dans les
fichiers `.astro` (skip-link, libellés ARIA, message « Aucun résultat »).
Pour un kit duplicable visé par d'autres podcasts (potentiellement
anglophones), c'est un point de friction.

Cependant :

- Adopter un framework i18n complet (`astro-i18n`, `i18next`, …) pour 30
  chaînes est disproportionné.
- Le contenu (épisodes, recos) reste dans la langue du podcast — on ne
  traduit PAS le contenu, seulement la **chrome UI**.

## Décision

**Approche minimale, 1 locale par déploiement** :

- `src/i18n/fr.ts` — objet typé `{ [key: string]: string }` avec un
  namespace plat (`a11y.skipLink`, `nav.backHome`, …).
- `src/i18n/index.ts` — helpers `t(key, locale?)` et `langToOgLocale()`.
- `<Layout lang="fr">` (défaut) → propage au `<html lang>` et aux appels
  `t(...)`. Une source peut surcharger via une prop optionnelle (champ
  `lang` non strict dans le schema sources pour rester forward-compat).

Pas de runtime detection, pas de fallback en cascade complexe : si la
locale demandée n'existe pas, on retombe sur `fr`.

## Conséquences

### Positives

- Zéro dépendance ajoutée.
- Forker en EN = copier `fr.ts` → `en.ts`, traduire, mettre `lang: 'en'`
  sur la source. Documenté dans `docs/fork-guide.md`.
- Typage TypeScript exhaustif (`I18nKey = keyof typeof fr`) → un appel
  `t('foo.bar')` invalide est rattrapé au build.

### Négatives

- Pas de pluralisation, pas d'interpolation avancée. Acceptable pour des
  chaînes courtes ; si un besoin émerge (compteurs « 1 reco / N recos »),
  on basculera vers `@formatjs/intl-messageformat` à ce moment-là.
- Une seule locale active à la fois par site. Pas de switcher EN/FR. Hors
  périmètre du kit aujourd'hui (un déploiement = un public).

### Notes

- Les libellés contenus dans les `.json` de sources (titres, taglines)
  restent dans leur langue d'origine — c'est du contenu, pas de la chrome.
- `langToOgLocale('fr') = 'fr_FR'` exposé en helper pour cohérence avec
  les meta OG (consommé par `MetaTags.astro`, zone Dev #13, qu'on
  n'altère PAS dans cet item).
