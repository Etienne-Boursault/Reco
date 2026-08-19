/**
 * src/utils/iconesPlateformes.ts — l'icône d'un lien, d'après son hôte.
 *
 * POURQUOI CE MODULE EXISTE
 * -------------------------
 * Cette logique vivait dans `RecoCard.astro`, où elle sert depuis l'origine.
 * La fiche d'œuvre affichait ses liens en texte seul ; « les liens, c'est pas
 * mal mais les icônes, c'est mieux » (relecture du 2026-08-19). Recopier
 * quatre-vingts hôtes dans un second fichier aurait garanti leur divergence
 * au premier ajout de plateforme.
 *
 * TROIS NIVEAUX DE REPLI, DANS CET ORDRE
 * --------------------------------------
 * 1. un logo local sous `/icons/platforms/<host>.svg`, pour les hôtes de la
 *    liste blanche — et SEULEMENT eux : nommer un hôte sans déposer le SVG
 *    afficherait une image cassée ;
 * 2. à défaut, un pictogramme selon la NATURE du lien (`KIND_SYMBOL`) ;
 * 3. à défaut encore, le libellé en toutes lettres, côté composant.
 *
 * Aucune requête vers un tiers : les favicons distantes fuiteraient l'adresse
 * IP et le référent du visiteur vers la plateforme (ADR 0034).
 */

export const PLATFORM_ICON_BASE = '/icons/platforms/';
export const WHITELISTED_ICON_HOSTS = new Set<string>([
  // Logos par plateforme déployés sous `public/icons/platforms/<host>.svg`
  // (2026-07-19). Le host est le hostname COMPLET (cf. `iconForHost`). Ajouter
  // une entrée ici SANS créer le SVG correspondant afficherait une image
  // cassée → n'ajouter que des hosts dont le fichier existe.
  'www.youtube.com',
  'music.youtube.com',
  'open.spotify.com',
  'www.deezer.com',
  'music.apple.com',
  'podcasts.apple.com',
  'tidal.com',
  'www.qobuz.com',
  'bandcamp.com',
  'store.steampowered.com',
  'itch.io',
  'www.justwatch.com',
  'www.instagram.com',
  'www.google.com',
  'www.fnacspectacles.com',
  'www.billetreduc.com',
  'www.placedeslibraires.fr',
  'www.lalibrairie.com',
  'duckduckgo.com',
  // Vague 2 (2026-07-19) : plateformes apparues avec les liens CURÉS par les
  // agents (les précédentes ne couvraient que les liens auto-générés).
  'www.allocine.fr',
  'www.netflix.com',
  'tv.apple.com',
  'www.disneyplus.com',
  'www.hbomax.com',
  'www.intl.paramountplus.com',
  'www.sooner.fr',
  'www.universcine.com',
  'www.filmotv.fr',
  'www.lacinetek.com',
  'www.senscritique.com',
  'shows.acast.com',
  'www.dailymotion.com',
  'en.tipeee.com',
  'fr.tipeee.com',
  'www3.nhk.or.jp',
  'www.gog.com',
  'www.gallimard.fr',
  'www.editions-delcourt.fr',
  'allary-editions.fr',
  'librairie.citebd.org',
  'www.theatreonline.com',
  'humorix.fr',
  'www.afca.asso.fr',
  'www.cnc.fr',
  'fr.wikipedia.org',
  // Vague 3 (2026-07-28) : plateformes streaming/VOD les plus fréquentes,
  // qui retombaient sur le placeholder link.svg (favicons manquantes).
  'www.primevideo.com',
  'www.themoviedb.org',
  'www.canalplus.com',
  'video.orange.fr',
  'video-a-la-demande.orange.fr',
  'www.pathehome.com',
  'rakuten.tv',
  'play.google.com',
  'boutique.arte.tv',
  'play.max.com',
  'www.molotov.tv',
  'www.fnac.com',
  'www.tiktok.com',
  'mubi.com',
  'www.sfrplay.fr',
  'www.premieremax.com',
  'www.videofutur.fr',
  // Vague 4 (2026-07-29) : lot BORNÉ de marques dont le logo est simple et
  // non ambigu. Les autres hosts de la traîne (librairies indépendantes, sites
  // perso d'artistes, éditeurs) restent VOLONTAIREMENT au symbole de repli :
  // un logo inventé « plausible » serait pire qu'un symbole honnête.
  'www.twitch.tv',
  'watch.plex.tv',
  'www.tf1.fr',
  // Vague 5 (2026-08-19) : hôtes DÉJÀ fréquents dans les liens du corpus
  // et qui n'avaient aucune icône — `www.imdb.com` à lui seul apparaît dans
  // 353 liens. Leur tuile est la favicon officielle du site, récupérée une
  // fois par `tools/recuperer_favicons.py` et intégrée en data URI.
  'www.imdb.com',
  'www.kyan.fr',
  'verino.fr',
  'www.infoconcert.com',
  'www.mollat.com',
  'theatredumarais.fr',
  'www.offi.fr',
  'encoreuntour.com',
  'le-pacte.com',
  'www.parislibrairies.fr',
  'www.decitre.fr',
  'www.jds.fr',
  'www.albin-michel.fr',
  'www.librest.com',
  'apps.apple.com',
  'louiemedia.com',
  'www.m6.fr',
]);
// Normalisation host → host whitelisté canonique. Couvre les VARIANTES d'un
// même host (sous-domaines d'artistes Bandcamp/itch.io, YouTube mobile, alias
// régionaux…) pour réutiliser la favicon existante SANS dupliquer de SVG —
// meilleur ratio effort/effet (audit favicons 2026-07-29 : ~40 recos gagnées,
// 0 fichier créé). Les alias ne pointent que vers des marques STRICTEMENT
// identiques (même logo) pour ne jamais afficher un logo trompeur.
export const HOST_ALIASES: Record<string, string> = {
  'm.youtube.com': 'www.youtube.com',
  'sooner.fr': 'www.sooner.fr',
  'www.rakuten.tv': 'rakuten.tv',
  'vod.viva.videofutur.fr': 'www.videofutur.fr',
  'en.wikipedia.org': 'fr.wikipedia.org',
  'play.acast.com': 'shows.acast.com',
  'www.arte.tv': 'boutique.arte.tv',
  // Domaine principal de Paramount+ ; `www.intl.paramountplus.com` est la
  // déclinaison internationale du MÊME service (logo identique).
  'www.paramountplus.com': 'www.intl.paramountplus.com',
  // Gallimard BD est un label des Éditions Gallimard (même maison, même
  // marque ombrelle) : réutiliser la tuile Gallimard n'affirme rien de faux.
  // NB : `www.librairie-gallimard.com` (librairie) n'est PAS aliasé — c'est
  // un commerce distinct de la maison d'édition.
  'www.gallimard-bd.fr': 'www.gallimard.fr',
};
// Marques multi-sous-domaines : tout sous-domaine → domaine racine whitelisté.
export const ROOT_DOMAIN_BRANDS = ['bandcamp.com', 'itch.io'];
export function normalizeHost(host: string): string {
  if (!host) return host;
  if (HOST_ALIASES[host]) return HOST_ALIASES[host];
  for (const root of ROOT_DOMAIN_BRANDS) {
    if (host === root || host.endsWith(`.${root}`)) return root;
  }
  return host;
}
export function iconForHost(host: string): string {
  if (!host) return '';
  const h = normalizeHost(host);
  if (WHITELISTED_ICON_HOSTS.has(h)) return `${PLATFORM_ICON_BASE}${h}.svg`;
  // Pas de favicon self-hosted pour ce host → on NE rend PAS le globe
  // `link.svg` (lu comme une image cassée / une erreur). La carte affiche à la
  // place un symbole selon la NATURE du lien (cf. KIND_SYMBOL + template).
  return '';
}

// Symbole de repli quand aucune favicon n'existe : pictogramme selon la nature
// du lien (streaming, achat, emprunt, info, officiel, social). Purement
// décoratif (aria-hidden) — le nom accessible reste porté par l'aria-label de
// l'<a> (OutboundLink). Défaut : maillon générique 🔗.
export const KIND_SYMBOL: Record<string, string> = {
  streaming: '▶️',
  buy: '🛒',
  borrow: '📚',
  info: 'ℹ️',
  official: '🏠',
  social: '👤',
};

/** L'hôte d'une URL, en minuscules. Chaîne vide si l'URL est invalide. */
export function hostDeLUrl(url: string): string {
  try {
    return new URL(url).hostname.toLowerCase();
  } catch {
    return '';
  }
}
