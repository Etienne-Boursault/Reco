# ADR 0041 — Stratégie documentation + tutorial

- Statut : Acceptée
- Date : 2026-06-12
- Décideurs : équipe Reco
- Phase : 3 (kit self-hostable), vague 1, item #20

## Contexte

Le kit Reco vise une utilisation self-hostable et duplicable. À la
clôture de la Phase 2 (5793 pages build, 17 ADRs, pipeline éprouvé),
l'onboarding restait minimaliste : un README monolithique de ~420
lignes mélangeant pitch, architecture détaillée, walkthrough complet
et améliorations futures. La friction d'entrée pour un contributeur
externe ou un forker était élevée :

- Pas de quick start visuel (3 lignes maximum).
- Pas de progression pédagogique (du "je veux voir" au "je veux comprendre").
- Pas d'équivalent texte du screencast de démo.
- Vue d'ensemble système absente (pipeline ↔ DBs ↔ frontend).
- Pas de page d'index documentation centralisée.

Options envisagées :

1. **Site de documentation séparé** (Docusaurus, MkDocs, Astro Starlight) —
   pros : navigation/recherche/versioning ; cons : overhead build CI,
   dépendances supplémentaires, divergence possible avec le repo.
2. **README monolithique enrichi** — pros : single file, GitHub-native ;
   cons : longueur excessive, navigation pénible, friction lecture.
3. **README court + tutoriels markdown progressifs + architecture doc +
   screencast script** — pros : zéro dépendance, navigation par fichiers,
   versionné avec le code, lisible sur GitHub ; cons : MAJ multi-fichiers.
4. **Tutorial unique sans architecture doc** — pros : simple ; cons :
   manque de vue d'ensemble système.

## Décision

On retient l'option **3** : README court (≤300 lignes) + 5 tutoriels
progressifs dans `docs/tutorial/` + `docs/architecture.md` + script
narratif du screencast + page d'index `docs/index.md`.

Découpage :

- `README.md` (refonte) — banner + quick start + features + demo +
  install + architecture ASCII + liens doc + contributing + license +
  citation + badges.
- `docs/index.md` — TOC de toute la doc.
- `docs/tutorial/01-getting-started.md` — premier déploiement, 5 min.
- `docs/tutorial/02-add-podcast.md` — ajouter ton podcast (équivalent
  texte du screencast 5 min).
- `docs/tutorial/03-pipeline-walkthrough.md` — pipeline pas-à-pas.
- `docs/tutorial/04-deploy-static.md` — Netlify, Vercel, Pages,
  Cloudflare, self-host, adapter SSR.
- `docs/tutorial/05-customize.md` — theme, fonts, i18n, branding.
- `docs/architecture.md` — vue d'ensemble système + 3 SQLite + ADRs.
- `docs/screencast-script.md` — script narratif 5 min minuté pour
  enregistrement ultérieur.

## Conséquences

### Positives

- Onboarding progressif : un lecteur lit le README, démarre en 5 min,
  approfondit selon ses besoins.
- Contributions documentation faciles (markdown pur, pas de framework).
- Versionné dans le repo : `git blame` permet de retrouver le contexte.
- Lisible sur GitHub sans build, sans hébergement.
- Le script de screencast permet une refonte vidéo cohérente même si
  l'auteur change.
- Pas de dépendance JS/Python ajoutée (cohérent avec la sobriété
  du kit, ADR 0040).

### Négatives

- MAJ multi-fichiers à chaque release majeure (mitigation : checklist
  de release qui liste les fichiers doc).
- Pas de search interne ni de versioning par release (Git suffit pour
  le versioning ; search GitHub est acceptable pour la phase 3).
- Pas de génération PDF automatique (acceptable pour ce stade).

### Notes

- **Critère de bascule** vers MkDocs/Docusaurus : si `docs/tutorial/` >
  10 fichiers ou si le besoin de versionning par release devient
  critique. À revisiter en phase 4.
- Le screencast vidéo lui-même reste à enregistrer ultérieurement :
  le script (`docs/screencast-script.md`) sert de spec et de garantie
  de cohérence avec la doc texte.
- Cohérence terminologique enforcée : *Reco* (projet), *reco*
  (recommandation), *source*/*podcast* (interchangeables), *kit* (le
  template duplicable).
- Langue principale : FR (cohérent avec ADR 0025, single-locale par
  fork). Une version EN pourra être ajoutée si une demande externe se
  matérialise.
