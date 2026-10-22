# Changelog

Tous les changements notables de Reco sont documentés ici.
Format basé sur [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/) ; ce projet suit [Semver](https://semver.org/lang/fr/).

## [Non publié]

### Ajouté
- Page `/mentions-legales` (#123) : éditeur anonyme (régime LCEN des non-professionnels), hébergeur, données mesurées et leurs durées, droits et recours CNIL, crédits TMDB et DB-IP ; lien dans le pied de page (ADR 0052).
- Durées de conservation appliquées par le serveur (#123) : `src/server/retention.mjs` supprime visites et clics à 13 mois et efface nom et e-mail des signalements à 12 mois, au démarrage puis chaque jour.
- Vignettes d'épisodes servies par le site (#125) : `public/vignettes/` (229 fichiers), `tools/vignettes_episodes.py`, `src/utils/vignettes.ts` ; venus récupère la vignette avant de publier un épisode.
- Redirections 301 des fiches d'œuvre fusionnées (#118) : `src/content/redirections-oeuvres.json` (274 entrées), alimentée par les outils de fusion, servie par `src/server/redirections.mjs` (ADR 0053).
- Commentaire YouTube des recos (#120) : venus poste les recos minutées et le lien de l'épisode sous chaque nouvelle vidéo, depuis la chaîne « Une Bonne Reco » ; inerte tant que `RECO_YT_COMMENTAIRES=1` et le jeton OAuth (`tools/youtube_autoriser.py`) ne sont pas posés.
- Tableau d'audience (#119, #121, #122) : graphique des visiteurs par jour, second graphique des robots, « clics pour 100 visiteurs », total des tentatives d'intrusion.
- Chaîne venus : calage de chaque citation sur la transcription après l'extraction (#101) ; invités lus dans le titre de l'épisode (#102) ; étape `chercher-liens` avant la relecture, liens visibles et retirables sur la carte (`linksRejected`) (#106).
- Relecture en mode focus : une reco à la fois, encadré « À vérifier », raccourcis V / C / D, bilan de fin d'épisode (#103).
- Liens : appariement des rééditions, variantes de titre, même œuvre reprise du corpus, plateformes vidéo, jeux, YouTube Music, pages artiste Apple Music (#105).
- Favicons officielles de 218 sites, TMDB compris, intégrées en data URI (#113) ; logo YouTube pour `youtu.be` (#112).
- JSON-LD `WebSite` « Une Bonne Reco » sur l'accueil mono-source ; le site ne se dit plus éditeur du podcast (#110).
- ADRs 0052 (données des visiteurs), 0053 (redirections des fiches fusionnées).
- Refonte de l'interface du 2026-10-07 ([rapport](docs/interface-rapport-2026-10-07.md)) : fiche œuvre « La récurrence » (chiffres, frise des mentions, « Qui en parle », « Où la trouver »), page invité « Bibliothèque », page épisode en chapitres d'écoute, statistiques en constats, onglet « Par type » et lien « Statistiques » dans le pied de page.
- Carte de partage « Étiquette » pour l'accueil, les galeries, les épisodes et **chaque** œuvre (1 202 PNG) ; cache persistant `.cache/og` à clé sur le rendu (ADR 0050).
- Le titre d'une carte de reco mène à la fiche de son œuvre ; les invités d'un épisode mènent à leur page.
- ADRs 0050 (cartes de partage et cache), 0051 (conventions d'interface).
- Phase 4 « Méta-agrégateur » (sem 11-13 roadmap) : méta-site `/meta/*` (ADR 0045) + endpoint `.well-known/reco-registry.json`, tracking clics sortants privacy-first (ADR 0046), stats publiques globales (ADR 0047) avec sidecar `stats.json` et JSON-LD Dataset.
- ADRs 0045, 0046, 0047 + extension 0028 (frontière fork-vs-méta).
- Helper `src/lib/stats/page.ts::loadStatsForPage` (DRY pages stats).
- SSRF guard `tools/meta/url_safety.py` (whitelist HTTPS + bloque IPs privées/link-local).
- Phase 3 « Kit déployable » (sem 8-10 roadmap) : Docker compose, wizard CLI `reco init`, README + tutoriels, LICENSE MIT + CITATION + CI publique, page À propos + manifeste éthique, poll RSS hebdo + notification webhook Discord/Slack/Email.
- ADRs 0037 (Docker), 0038 (Wizard), 0039 (License), 0040 (Manifeste), 0041 (Doc strategy), 0042 (Cron RSS).

### Modifié
- Audience : un visiteur est une requête humaine qui obtient une page — ni robot déclaré, ni requête sans `Accept-Language`, ni préchargement au survol, ni erreur (#119, #121) ; critère appliqué aussi à l'historique. Pages vues 3 848 → 1 918 sur 30 jours.
- `/a-propos` ne nomme plus l'éditeur et renvoie aux mentions légales (#123) ; adresse de contact `contact@unebonnere.co` (#117).
- Contenu : S6-E04 (#104), S6-E05 (#111, #116), minutages, citations, noms, invités et titres vérifiés (#99), corrections de l'audit du 2026-10-20 — neuf fusions de doublons, créateurs et types corrigés (#118).
- Dépendances (Dependabot) : astro, happy-dom 21, outillage de développement, openai, anthropic, filelock, python-dotenv (#92, #95–#98, #107, #114). satori 0.60 refusé : il déforme les cartes de partage (#115 fermée).
- Appui (`:active`) sur tout élément interactif, survols réservés à la souris, cibles de 44 px (signalement, retours, pied de page, chronologie) ; les liens de retour passent au-dessus des grands titres.
- Grands chiffres et icônes de type dans la couleur d'accent partout ; icônes au trait à la place des emojis, cartes de reco comprises.
- « Présentée par » réservé aux créateurs de l'œuvre ; sinon « Reco de » / « Recommandée par ».
- Cartes égalisées par rangée et non plus sur tout le catalogue ; deux colonnes sur téléphone à l'accueil ; galeries en une ligne par œuvre sur téléphone.
- Données : minutages de l'épisode #10, invités de la saison 6, créateurs de La Flamme et de Bloqués, mentions doublons écartées.

### Corrigé
- Audience : « clics par visiteur » s'arrondissait à 0 (0,033) ; provenance interne comptée faute de `SITE_URL` au démarrage chez Infomaniak (la page lit `Astro.site`) ; `/a-propos` et `/a-propos/` comptées séparément ; sondes de failles listées comme liens morts (#121, #122).

### Sécurité
- Vie privée : plus aucune ressource tierce chargée à l'affichage d'une page (vignettes YouTube et Acast retirées, #125) ; plus aucune donnée conservée sans limite (#123).
- Phase 4 V2 — 111 issues corrigées (11 CRITICAL, 22 HIGH, 40 MEDIUM, 28 LOW, 20 NIT) : SSRF `build_meta` fix, leak chemin serveur 500, fuite IP DuckDuckGo retirée, `_meta/` renommé `meta/` (Astro exclut préfixe `_`), validation Zod registry avant émission, HMAC IP+salt rate-limiter, cap POST body 8 KiB, normalisation slug FS lowercase, JSON-LD `PodcastSeries`.

## [0.2.0] — 2026-06-11

### Ajouté
- Phase 2 (10 items #8-#17) : SQLite cache + FTS5, recherche full-text MiniSearch + Cmd+K, galeries par invité/type, page œuvre canonique, embed audio timecode, OG cards Satori + sitemap, A11y WCAG AA strict, embeddings sémantiques fastembed, signalements visiteurs, re-enrich proactif TMDB/Music.
- 17 ADRs Phase 2 (0020-0036), incluant audit_core, design tokens, fork-guide, i18n single-locale.
- `docs/fork-guide.md` complet (env vars, modules, adapter SSR, multi-source).

### Modifié
- Layout.astro : SearchPalette globale, fallback mailto reports, retrait Google Fonts (Anton via Inter system).
- 5 cross-références ADR vers ADR 0030 (tokens) corrigées.

### Sécurité
- Captcha durci (hash payload sha256, jti UUID LRU, TTL 4h), Anton retiré (RGPD), assertSlug path traversal, isSafeHttpUrl XSS DOM.

## [0.1.0] — 2026-06-10

### Ajouté
- Phase 1 « Fondations critiques » (sem 1-4 roadmap) : config externe, modèle Item/Mention/Source + migration 2866 recos, schemaVersion + migrations, golden set + eval harness, schema linter dataset, détection match YT/Acast suspect, détection enrichissement TMDB incorrect.
- ADRs 0001-0019, dont audit_core unifié.
- 2683 tests Python, build Astro initial 107 pages.

[Non publié]: https://github.com/etienneboursault/reco/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/etienneboursault/reco/releases/tag/v0.2.0
[0.1.0]: https://github.com/etienneboursault/reco/releases/tag/v0.1.0
