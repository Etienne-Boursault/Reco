# ADR 0028 — Frontière de personnalisation pour forks

- Statut : Acceptée
- Date : 2026-06-10
- Décideurs : équipe Reco
- ADRs liés : ADR 0021 (SEO/OG), ADR 0030 (tokens UI)

## Contexte

Reco est conçu comme un kit duplicable (« je fork, je rebrand, je
déploie »). Avant cette ADR, les chaînes branding étaient éparpillées :
`source-internet.fr` dans `template.ts`, `Reco` dans plusieurs `<meta>`,
baseline dans `[...slug].png.ts`. Forker imposait de chasser ces
constantes au grep — vecteur de régressions et de signaux résiduels du
domaine d'origine.

## Décision

Un seul fichier `src/config/site.ts` expose :

- `siteName` — affiché dans `og:site_name`, suffixe `<title>`, footer
  carte OG.
- `baseline` — accroche carte OG par défaut + description meta de
  l'index.
- `domainLabel` — affiché en pied de carte OG (texte purement visuel,
  pas l'URL canonique qui vient de `Astro.site`).
- `defaultAccent / defaultBg / defaultFg / defaultMuted` — couleurs OG
  par défaut, importées depuis `src/styles/tokens.ts` (cohérence UI/OG).

Le template OG, `MetaTags.astro`, et toute page d'index lit `siteConfig`.
Aucun autre fichier ne hardcode ces valeurs.

## Liste « ce qu'un fork modifie »

Forker = ouvrir 3 fichiers :

1. `src/config/site.ts` — branding (siteName, baseline, domaine).
2. `src/styles/tokens.ts` — palette UI/OG.
3. `src/content/sources/*.json` — sources que le fork couvre.

C'est tout. Tests, OG cards, JSON-LD, sitemap, robots — adaptés
automatiquement.

## Conséquences

- Onboarding fork mesurable en minutes, pas en heures.
- La fuite de la chaîne `Reco` dans un fork rebrandé devient une
  régression détectable (test post-build qui vérifie qu'aucun HTML ne
  contient `Reco` quand `siteConfig.siteName !== 'Reco'`).

## Frontière fork-vs-méta (P4 item #24, 2026-06-12)

Le « méta-site » (annuaire `source-internet.fr`, cf. ADR 0045) n'est
PAS un mode de fork — c'est un build opt-in du même kit, activé par
`META_MODE=1` (env var, cf. fork-guide §14). Trois conséquences :

- Un fork classique (= 1 podcast) tourne avec `META_MODE=0` (défaut)
  et n'expose aucune route `/_meta/*` ni dépendance à `tools/meta/`.
- L'agrégateur (méta-site) hérite du même kit mais ajoute le crawl
  des `/.well-known/reco-registry.json` publics et publie son propre
  branding via `src/config/site.ts` (cohérent avec la décision ci-dessus).
- La frontière reste un seul fichier de branding (`site.ts`) : pas de
  hardcode `source-internet.fr` ailleurs. Les routes `/_meta/*` lisent
  `siteConfig` exactement comme les pages podcast.

Tracking sortant (ADR 0046) et stats publiques (ADR 0047) sont des
modules opt-in additionnels (cf. fork-guide §15/§16) qui ne modifient
PAS la frontière fork : un fork peut les activer ou non sans toucher
à `site.ts`.
