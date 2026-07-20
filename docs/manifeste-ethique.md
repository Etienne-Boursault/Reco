# Manifeste éthique de Reco

> Ce manifeste engage le projet **Reco** (instance par défaut publiée sur
> `source-internet.fr`) et constitue la posture éditoriale recommandée pour
> tous les forks qui souhaitent s'en réclamer. Il est public, évolutif via
> Pull Request, et opposable.

## 1. Préambule

Reco est un kit open-source qui rassemble les œuvres recommandées dans des
podcasts indépendants : films, séries, livres, BD, musiques, jeux, lieux.
Un agrégateur n'est jamais neutre — chaque choix éditorial (sources
indexées, marchands liés, fournisseurs intégrés, données collectées) est
politique. Ce manifeste explicite nos choix pour que personne ne s'y
trompe : ni les visiteurs, ni les contributeurs, ni les forks.

## 2. Anti-Bolloré

Le groupe Bolloré a, via Vivendi puis Lagardère, agrégé une part majeure
du paysage médiatique et éditorial francophone. Cette concentration est
documentée par [Acrimed](https://www.acrimed.org/) et par les pages
Wikipédia [Groupe Bolloré](https://fr.wikipedia.org/wiki/Groupe_Bolloré),
[Vivendi](https://fr.wikipedia.org/wiki/Vivendi) et
[Lagardère SA](https://fr.wikipedia.org/wiki/Lagardère_SA).

**Principes :**

- Reco ne fait pas la promotion d'œuvres dont l'éditeur ou le distributeur
  identifié appartient à un groupe contrôlé par Bolloré
  (à date : Hachette Livre, Editis, Plon, Place des Éditeurs, Fayard,
  Grasset, Stock, Robert Laffont, etc.).
- Une œuvre recommandée par un podcast et publiée chez l'un de ces
  éditeurs reste **visible** dans le catalogue (on ne falsifie pas le
  discours du podcast), mais :
  - elle est **signalée** comme telle (badge, mention dans la fiche) ;
  - aucun lien d'achat n'est généré vers une plateforme tierce pour ces
    œuvres tant qu'un canal indépendant n'a pas été identifié.
- Les contributeurs peuvent signaler une œuvre via le formulaire
  `/api/report` (cf. ADR 0034) si l'appartenance Bolloré est détectée
  manuellement.

**Roadmap technique** : un blocage automatique basé sur une liste
d'éditeurs maintenue dans `src/content/sources/*.json` est prévu (cf.
roadmap item #25). Tant qu'il n'est pas livré, la modération se fait par
revue humaine et par signalement.

## 3. Librairies indépendantes (jamais Amazon)

**Principes :**

- Reco ne lie **jamais** vers Amazon, Audible, Kindle Store ou tout
  service du groupe Amazon, quelle que soit la disponibilité ou la
  commodité.
- Pour les livres, Reco priorise dans cet ordre :
  1. l'éditeur indépendant directement (boutique propre) ;
  2. [Place des Libraires](https://www.placedeslibraires.fr/) (réseau
     national des librairies indépendantes françaises) ;
  3. [Lalibrairie.com](https://www.lalibrairie.com/) (réseau Initiales) ;
  4. [Librest](https://www.librest.com/) (réseau parisien) ;
  5. autres librairies locales identifiées.
- Pour la musique et les films, Reco priorise les plateformes
  rémunératrices pour les créateurs et créatrices (Bandcamp, sites
  éditeurs, services publics) avant les agrégateurs marchands.

## 4. Vie privée & RGPD

**Aucun tracker tiers. Aucun cookie marketing. Aucun cookie analytique.**

- Polices auto-hébergées (Inter via `@fontsource`) — pas de Google Fonts
  (cf. ADR 0029 §Anton retiré 2026-06-11).
- Embeds vidéo via `youtube-nocookie.com` uniquement (cf. ADR 0036).
- Les signalements visiteurs (`/api/report`) hashent et saltent l'IP
  avant stockage (cf. ADR 0034 et P2.16) — l'IP brute ne touche jamais
  le disque.
- Pas de Plausible, pas de Matomo, pas de Google Analytics. Les seules
  statistiques publiées sont des stats de catalogue (nombre de recos,
  d'épisodes), calculées build-time, sans données visiteur.

## 5. Open source

- Code sous licence **MIT** (cf. ADR licence du dépôt). Forker est
  encouragé.
- Une attribution visible (lien vers le dépôt amont) est demandée à tout
  fork public, sans imposer la conservation du présent manifeste.
- Les dépendances tierces sont auditées (cf. CI `npm audit` + `pip
  check`) et leurs licences sont compatibles MIT.

## 6. Accessibilité

- Conformité **WCAG 2.1 niveau AA** vérifiée build-time
  (cf. ADR 0022 et `tests/a11y/check_a11y.mjs`).
- 0 violation tolérée sur le build de production.
- Contraste validé via `tests/a11y/check_contrast.mjs` sur tous les
  thèmes de source.
- Navigation clavier complète, `skip-link`, `lang` correct, hiérarchie
  de titres unique par page.

## 7. Self-hostable

- Le kit est duplicable : un déploiement = un podcast (ou plusieurs si
  désiré), sans dépendance à un service propriétaire de Reco.
- Documentation `docs/fork-guide.md` couvre la personnalisation des
  thèmes, du branding (`src/config/site.ts`, cf. ADR 0028), des sources
  et du manifeste lui-même.
- Aucune télémétrie, aucun ping vers un serveur centralisé.

## 8. Transparence

- **ADRs publics** (`docs/adr/`) : chaque décision structurante est
  documentée, datée, et conserve les alternatives écartées.
- **Roadmap publique** (`docs/roadmap-meta-agregateur.md`) : ordre de
  priorité visible, statut par item.
- **Manifeste évolutif** : les modifications de ce document passent par
  Pull Request publique sur le dépôt amont. Les forks qui s'en écartent
  doivent publier leur propre version dérivée.

---

*Dernière révision : 2026-06-11. Voir l'historique Git pour les
modifications.*
