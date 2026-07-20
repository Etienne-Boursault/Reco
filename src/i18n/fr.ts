/**
 * src/i18n/fr.ts — Strings français (locale par défaut).
 *
 * Namespace flat : { 'a11y.skipLink': '…' }. Pas de framework i18n — un
 * objet typé suffit pour un kit duplicable. Cf. ADR 0026.
 *
 * Pour dupliquer le kit en anglais : copier ce fichier en `en.ts`, traduire
 * les valeurs, et exposer `lang: 'en'` sur la source (`source.data.lang`).
 */

export const fr = {
  // A11y
  'a11y.skipLink': 'Aller au contenu principal',
  'a11y.externalLinkSuffix': '(nouvel onglet)',
  'a11y.noResult': 'Aucun résultat.',
  'a11y.noEpisodeFound': 'Aucun épisode trouvé.',
  'a11y.noscript':
    'JavaScript est désactivé. Les filtres et la recherche ne fonctionneront pas, mais le catalogue reste consultable.',

  // Headings cachés (structure)
  'heading.allRecos': 'Toutes les recommandations',
  'heading.episodesWithRecos': 'Épisodes avec recommandations',

  // Navigation
  'nav.backHome': 'tous les podcasts',
  'nav.prevEpisode': 'Épisode précédent',
  'nav.nextEpisode': 'Épisode suivant',
  'nav.episodeNav': 'Navigation entre épisodes',
  'nav.tabsLabel': 'Vue du catalogue',

  // Footer
  'footer.tagline': 'Projet ouvert et duplicable — une source = un podcast.',
  'footer.about': 'À propos',
  'footer.manifesto': 'Manifeste éthique',
  'footer.nav.label': 'Liens secondaires',

  // À propos (item #22)
  'about.title': 'À propos de Reco',
  'about.subtitle':
    'Reco rassemble les œuvres recommandées dans des podcasts, sans tracker, sans Amazon, avec des liens vers des librairies indépendantes.',
  'about.section.who': 'Qui sommes-nous',
  'about.section.why': 'Pourquoi Reco',
  'about.section.how': 'Comment ça marche',
  'about.section.credits': 'Crédits & ressources',
  'about.section.links': 'Liens utiles',
  'about.cta.contribute': 'Contribuer / forker le kit',

  // Manifeste éthique (item #22)
  'manifesto.title': 'Manifeste éthique',
  'manifesto.subtitle':
    'Ce que Reco refuse de relayer, ce que Reco priorise, et pourquoi.',
  'manifesto.preambule.title': 'Préambule',
  'manifesto.anti-bollore.title': 'Anti-Bolloré',
  'manifesto.libraries.title': 'Librairies indépendantes',
  'manifesto.privacy.title': 'Vie privée & RGPD',
  'manifesto.opensource.title': 'Open source',
  'manifesto.a11y.title': 'Accessibilité',
  'manifesto.selfhost.title': 'Self-hostable',
  'manifesto.transparency.title': 'Transparence',
  'manifesto.toc.label': 'Sommaire du manifeste',

  // Galeries (item #10)
  'gallery.films.title': 'Tous les films',
  'gallery.series.title': 'Toutes les séries',
  'gallery.livres.title': 'Tous les livres',
  'gallery.musique.title': 'Toute la musique',
  'gallery.guest.titlePrefix': 'Recommandations de',
  'gallery.empty': 'Aucune recommandation pour cette galerie.',
  'gallery.mentionsSuffix': 'mentions',
  'gallery.mentionSuffix': 'mention',
  'gallery.backToSource': 'retour au podcast',

  // Extrait audio (item #12)
  'audio.listenAt': 'Écouter à',
  'audio.listen': 'Écouter cet extrait',
  'audio.close': 'Fermer le lecteur',
  'audio.closeIcon': '✕',
  'audio.iframeTitle': 'Extrait YouTube de l’épisode',
  'audio.openOnAcast': 'Écouter sur Acast',
  'audio.openOnAcastA11y': 'Ouvrir l’extrait sur Acast',

  // Recherche (item #9)
  'search.title': 'Recherche',
  'search.metaTitle': 'Recherche — Reco',
  'search.placeholder': 'Rechercher une œuvre, un épisode, un invité…',
  'search.paletteOpen': 'Ouvrir la recherche',
  'search.paletteHint': 'Échap pour fermer · ↑↓ pour naviguer · Entrée pour ouvrir',
  'search.groupItems': 'Œuvres',
  'search.groupEpisodes': 'Épisodes',
  'search.groupGuests': 'Invités',
  'search.noResults': 'Aucun résultat pour cette recherche.',
  'search.loading': 'Chargement de l’index…',
  'search.error': 'Index indisponible — réessaie plus tard.',
  'search.hint': 'Tape au moins deux caractères pour lancer la recherche.',
  'search.resultsAria': 'Résultats de recherche',

  // Signalements (item #16, X3)
  'report.link': 'Signaler',
  'report.linkA11y': 'Signaler un problème sur cette recommandation',

  // Reco — badges de nature (Story 4). Libellés harmonisés (badge = bouton).
  // Politique 2026-07-07 : guestWork couvre l'auto-promo des invité·es ET des
  // hosts → libellé « Leur œuvre » (l'œuvre de qui parle dans l'épisode).
  'reco.guestWork.badge': 'Leur œuvre',
  'reco.guestWork.badgeA11y':
    'Œuvre présentée par un·e invité·e ou un host de l’épisode (auto-promotion)',
  'reco.citation.badge': 'Mentionné',
  'reco.citation.badgeA11y':
    'Œuvre mentionnée dans l’épisode mais pas explicitement recommandée',

  // Page épisode — sections & ledes (M2). Apostrophes typographiques (N1).
  'episode.section.recommendations': 'Recommandations',
  'episode.section.guestWorks': 'Leurs œuvres',
  'episode.section.citations': 'Mentionné dans l’épisode',
  'episode.lede.guestWorks':
    'Œuvres présentées par les invité·es ou les hosts de l’épisode (spectacle, album, livre…) — distinctes des recommandations.',
  'episode.lede.citations':
    'Œuvres évoquées par l’équipe ou les invité·es mais pas explicitement recommandées.',
  // Compteur d'en-tête (L1/N2). `{count}` = spontanées + « leurs œuvres »
  // (cohérent avec la carte annuaire et la meta OG). Breakdown facultatif
  // « dont … » quand il y a des œuvres présentées, sinon rien.
  'episode.count.recommendations.one': '1 recommandation',
  'episode.count.recommendations.many': '{count} recommandations',
  'episode.count.guestWorks.one': 'dont 1 œuvre présentée dans l’épisode',
  'episode.count.guestWorks.many': 'dont {count} œuvres présentées dans l’épisode',
  'episode.count.citations.one': '1 mention',
  'episode.count.citations.many': '{count} mentions',

  // Œuvre (item #11, X2)
  'work.openA11y': 'Voir la page complète de l’œuvre',

  // Œuvre — page canonique (Phase 2 H10/X-3).
  // L4 : « Recommandée » ne compte QUE les recos (kind !== citation, œuvres
  // d'invité·es incluses). Une œuvre seulement évoquée (0 reco) bascule sur
  // la formulation « Mentionnée » (basée sur le total des mentions).
  'work.year.a11y': 'Année {year}',
  'work.stats.reco.one': 'Recommandée 1 fois',
  'work.stats.reco.many': 'Recommandée {count} fois',
  'work.stats.mention.one': 'Mentionnée 1 fois',
  'work.stats.mention.many': 'Mentionnée {count} fois',
  'work.description.reco.one': 'Recommandée 1 fois dans le podcast {source}.',
  'work.description.reco.many': 'Recommandée {count} fois dans le podcast {source}.',
  'work.description.mention.one': 'Mentionnée dans le podcast {source}.',
  'work.description.mention.many': 'Mentionnée {count} fois dans le podcast {source}.',
  'work.links.a11y': 'Liens externes',
  'work.heading.mention.one': 'Mention dans le podcast',
  'work.heading.mention.many': '{count} mentions dans le podcast',
  'work.heading.similar': 'Du même créateur',

  // MentionsTimeline
  'work.mentions.unknownEpisode': 'Épisode inconnu',
  'work.mentions.byReco': 'Recommandée par',
  'work.mentions.byCitation': 'Évoquée par',
  'work.mentions.youtubeA11y': 'Ouvrir sur YouTube',
  'work.mentions.youtubeFallback': 'YouTube',

  // TrendingBadge
  'work.trending.label':
    'Mentionnée {count} fois au cours des {months} derniers mois',

  // Reports — formulaire (item #16, X3)
  'report.form.context.prefix': 'Signalement concernant :',
  'report.form.category.legend': 'Catégorie du signalement',
  'report.form.category.error': 'Erreur (mauvaise œuvre, titre, créateur·rice…)',
  'report.form.category.brokenLink': 'Lien cassé',
  'report.form.category.inappropriate': 'Contenu inapproprié',
  'report.form.category.suggestion': 'Suggestion / ajout d’information',
  'report.form.details.label': 'Détails',
  'report.form.details.hint':
    'Décris brièvement le problème (max {max} caractères).',
  'report.form.name.label': 'Ton nom (optionnel)',
  'report.form.email.label': 'Email (optionnel)',
  'report.form.email.hint':
    'Pour qu’on puisse te recontacter si on a besoin de précisions.',
  'report.form.wantCredit': 'Je veux être crédité·e comme contributeur·rice',
  'report.form.honeypot': 'Ne pas remplir',
  'report.form.submit': 'Envoyer le signalement',
  'report.form.mailto.label': 'Envoyer par email',
  'report.form.mailto.noscriptPrefix': 'Si le formulaire ne s’envoie pas,',
  'report.form.mailto.noscriptLink': 'écrivez-nous par email',
  'report.form.mailto.subjectPrefix': '[Signalement]',
  'report.form.mailto.bodySource': 'Source',
  'report.form.mailto.bodyReco': 'Reco',
  'report.form.mailto.bodyCategoryHint':
    'Catégorie : (error / broken-link / inappropriate / suggestion)',
  'report.form.mailto.bodyDetails': 'Détails :',
  'report.form.mailto.bodyCategoryLabel': 'Catégorie',
  'report.form.mailto.bodyFrom': 'De',
  'report.form.status.sending': 'Envoi en cours…',
  'report.form.status.success': 'Merci ! Signalement envoyé ({id}).',
  'report.form.status.errorPrefix': 'Erreur',
  'report.form.status.endpoint405':
    'Le formulaire n’est pas activé côté serveur. Utilise le lien email ci-dessous.',
  'report.form.status.network':
    'Erreur réseau. Utilise le lien email ci-dessous ou réessaie plus tard.',

  // Reports — page formulaire (/[source]/report/[recoId])
  'report.page.metaTitle': 'Signaler — {title}',
  'report.page.back': '← retour au catalogue',
  'report.page.title': 'Signaler un problème',
  'report.page.lede':
    'Tu as repéré une erreur, un lien cassé, ou tu veux nous suggérer une amélioration sur cette recommandation ? Merci !',

  // Reports — queue admin (/[source]/reports)
  'report.admin.metaTitle': 'Signalements — {source}',
  'report.admin.back': 'retour au catalogue',
  'report.admin.title': 'Signalements visiteurs',
  'report.admin.stats.pending': 'en attente',
  'report.admin.stats.resolved': 'résolus',
  'report.admin.stats.dismissed': 'écartés',
  'report.admin.hintPrefix': 'Queue interne — non destinée au public. Pour résoudre/écarter un report, utilise',
  'report.admin.empty': 'Aucun signalement en attente. 🎉',
  'report.admin.recoLabel': 'Reco :',
  'report.admin.wantCredit': '★ veut être crédité·e',
  'report.admin.cat.error': 'Erreur',
  'report.admin.cat.brokenLink': 'Lien cassé',
  'report.admin.cat.inappropriate': 'Inapproprié',
  'report.admin.cat.suggestion': 'Suggestion',

  /*
   * Compteurs génériques (cross-fixer MX-7).
   *
   * F-M-7 : namespace partagé entre `meta.stats.*` (Fixer #24, page
   * annuaire source-internet.fr) et `stats.card.*` (Fixer #26, /stats).
   * Utilisé directement par `src/pages/[source]/stats.astro` pour les
   * cartes de la vue source.
   *
   * Les clés `meta.stats.*` et `stats.card.*` restent comme alias
   * rétro-compat (consumers re-pointeront dans une PR ultérieure, après
   * livraison Fixer #24 / #26). NE PAS purger maintenant — c'est encore
   * référencé dans `[source]/stats.astro`.
   *
   * Convention :
   *  - `items` : œuvres référencées (toutes mentions confondues).
   *  - `mentions` : occurrences (1 œuvre peut être mentionnée plusieurs fois).
   *  - `episodes` : épisodes datés.
   *  - `guests` : invité·es distincts (≃ contributeurs externes).
   *  - `podcasts` : sources indexées (forks Reco).
   *  - `uniqueWorks` / `uniqueGuests` : sous-ensembles dédupliqués.
   *  - `recommendations` : alias narratif de `mentions` quand le contexte
   *    parle de « recommandations » plutôt que de « mentions ».
   */
  'common.counters.items': 'œuvres référencées',
  'common.counters.mentions': 'mentions',
  'common.counters.episodes': 'épisodes',
  'common.counters.guests': 'invité·es',
  'common.counters.podcasts': 'podcasts indexés',
  'common.counters.uniqueWorks': 'œuvres uniques',
  'common.counters.uniqueGuests': 'invités uniques',
  'common.counters.recommendations': 'recommandations',

  // Méta-site (item #24) — source-internet.fr
  'meta.title': 'Source internet — l’annuaire des podcasts Reco',
  'meta.subtitle':
    'Les podcasts qui partagent leurs recommandations en JSON ouvert, sans tracker, sans Amazon.',
  'meta.metaTitle': 'Source internet — annuaire des podcasts Reco',
  'meta.podcastCount.one': '1 podcast indexé',
  'meta.podcastCount.many': '{count} podcasts indexés',
  'meta.stats.items': 'œuvres référencées',
  'meta.stats.mentions': 'mentions',
  'meta.stats.episodes': 'épisodes',
  'meta.stats.guests': 'invité·es',
  'meta.cta.visit': 'Visiter le site',
  'meta.cta.visitA11y': 'Ouvrir {site} dans un nouvel onglet',
  'meta.empty':
    'Aucun podcast n’est encore référencé. Reviens plus tard ou ajoute le tien.',
  'meta.podcast.back': '← retour à l’annuaire',
  'meta.podcast.hosts': 'Animation',
  'meta.podcast.rss': 'Flux RSS',
  'meta.podcast.manifesto': 'Manifeste du fork',
  'meta.podcast.lastUpdated': 'Dernière mise à jour',

  // Stats publiques (item #26 / ADR 0047)
  'stats.title': 'Statistiques publiques',
  'stats.metaTitle': 'Statistiques publiques',
  'stats.subtitle':
    'Tout le catalogue Reco en un coup d’œil — sans tracker, calculé build-time.',
  'stats.subtitle.source':
    'Statistiques de {source} — sans tracker, calculé build-time.',
  'stats.heading.global': 'Vue d’ensemble',
  'stats.heading.topGuests': 'Invités les plus prolifiques',
  'stats.heading.topWorks': 'Œuvres les plus mentionnées',
  'stats.heading.typeDistribution': 'Répartition par type d’œuvre',
  'stats.heading.monthly': 'Épisodes par mois',
  'stats.card.podcasts': 'podcasts indexés',
  'stats.card.episodes': 'épisodes',
  'stats.card.recommendations': 'recommandations',
  'stats.card.uniqueWorks': 'œuvres uniques',
  'stats.card.uniqueGuests': 'invités uniques',
  'stats.empty.topGuests': 'Aucun invité à classer pour l’instant.',
  'stats.empty.topWorks': 'Aucune œuvre à classer pour l’instant.',
  'stats.empty.typeDistribution': 'Pas encore assez de données.',
  'stats.empty.monthly': 'Pas encore d’épisodes datés.',
  'stats.col.mentions': 'mentions',
  'stats.col.episodes': 'épisodes',
  'stats.topList.nameHeader': 'Nom',
  'stats.chart.categoryHeader': 'Catégorie',
  'stats.chart.empty': 'Pas de données disponibles',
  'stats.typeDistribution.note':
    'Une œuvre est comptée sur son type principal (premier déclaré).',
  'stats.dataset.description':
    'Compteurs publics Reco : podcasts, épisodes, recommandations, œuvres uniques, invités.',
  'stats.generatedAt': 'Calculé le {date}',
  'stats.privacyNote':
    'Données calculées au build, agrégées, anonymes — aucun tracker ne court côté visiteur.',
  'stats.back.source': 'retour au podcast',
} as const;

export type I18nKey = keyof typeof fr;
