/**
 * Résolveur de liens « éthiques » par type de reco.
 *
 * Politique éditoriale :
 *   - JAMAIS de lien Amazon (libraire, marketplace). Prime Video est inclus
 *     mais marqué `ethics: 'avoid'` (alternative recommandée).
 *   - On évite les enseignes/médias du groupe Bolloré (Vivendi/Canal+, Editis,
 *     Hachette Livre via Lagardère, etc.) — voir AVOID_DOMAINS.
 *   - On privilégie les plateformes indépendantes / françaises (ethics: 'indie').
 *
 * En l'absence d'URL exacte fournie par le pipeline, on génère des liens de
 * RECHERCHE à partir du type d'œuvre + titre + créateur. Les motifs d'URL sont
 * « best effort » : faciles à ajuster ici si une plateforme change son endpoint.
 *
 * Pour les films/séries, l'enrichissement TMDB (watch providers FR) est prévu
 * via un script séparé `tools/enrich_tmdb.py` qui peuplera `reco.watchProviders`.
 * En attendant, JustWatch est utilisé en agrégateur.
 */

export type RecoLinkKind = 'buy' | 'borrow' | 'streaming' | 'info' | 'official' | 'social';
export type Ethics = 'indie' | 'neutral' | 'avoid';

export interface ResolvedLink {
  label: string;
  url: string;
  kind: RecoLinkKind;
  ethics: Ethics;
}

/** Domaines à ne jamais proposer (Amazon hors Prime + galaxie Bolloré). */
export const AVOID_DOMAINS = [
  'amazon.fr',
  'amazon.com',
  // Distribution / médias liés au groupe Bolloré (Vivendi, Lagardère…)
  'canalplus.com',
  'cnews.fr',
  'europe1.fr',
  'parismatch.com',
  'lejdd.fr',
  // Éditeurs des groupes Editis / Hachette (liens marchands directs évités)
  'editis.com',
  'hachette.fr',
];

const enc = (s: string) => encodeURIComponent(s.trim());

/** Construit la requête de recherche à partir des champs de la reco. */
function query(title: string, creator?: string): string {
  return creator ? `${title} ${creator}` : title;
}

interface RecoLike {
  title: string;
  creator?: string;
  type: string;
  externalIds?: {
    isbn?: string;
    tmdb?: string;
    imdb?: string;
    musicbrainz?: string;
    youtube?: string;
    instagram?: string;
    website?: string;
  };
  /** Liens explicites fournis par la reco — gardés tels quels (pas filtrés). */
  links?: { label: string; url: string; kind?: RecoLinkKind; ethics?: Ethics }[];
  /** Plateformes de streaming (renseigné par enrich_tmdb.py pour film/serie). */
  watchProviders?: {
    label: string;
    url: string;
    ethics?: Ethics;
  }[];
}

// =====================================================================
// Résolveurs par type
// =====================================================================

function linksForBookOrComic(reco: RecoLike): ResolvedLink[] {
  const q = enc(query(reco.title, reco.creator));
  const out: ResolvedLink[] = [];
  if (reco.externalIds?.isbn) {
    out.push({
      label: 'Place des Libraires',
      url: `https://www.placedeslibraires.fr/liste/?q=${enc(reco.externalIds.isbn)}`,
      kind: 'buy', ethics: 'indie',
    });
  }
  out.push(
    { label: 'Place des Libraires', url: `https://www.placedeslibraires.fr/liste/?q=${q}`, kind: 'buy', ethics: 'indie' },
    { label: 'Lalibrairie.com',     url: `https://www.lalibrairie.com/livres/recherche.html?q=${q}`, kind: 'buy', ethics: 'indie' },
  );
  return out;
}

function linksForMusic(reco: RecoLike): ResolvedLink[] {
  const q = enc(query(reco.title, reco.creator));
  // Bandcamp en 1er (modèle artiste-first). Puis les grandes plateformes
  // accessibles facilement comme demandé : Deezer, Spotify, Qobuz, Apple,
  // YT Music, Tidal.
  return [
    { label: 'Bandcamp',    url: `https://bandcamp.com/search?q=${q}`,                       kind: 'streaming', ethics: 'indie'   },
    { label: 'Deezer',      url: `https://www.deezer.com/fr/search/${q}`,                     kind: 'streaming', ethics: 'neutral' },
    { label: 'Spotify',     url: `https://open.spotify.com/search/${q}`,                      kind: 'streaming', ethics: 'neutral' },
    { label: 'Qobuz',       url: `https://www.qobuz.com/fr-fr/search?q=${q}`,                 kind: 'buy',       ethics: 'indie'   },
    { label: 'Apple Music', url: `https://music.apple.com/fr/search?term=${q}`,               kind: 'streaming', ethics: 'neutral' },
    { label: 'YT Music',    url: `https://music.youtube.com/search?q=${q}`,                   kind: 'streaming', ethics: 'neutral' },
    { label: 'Tidal',       url: `https://tidal.com/search?q=${q}`,                           kind: 'streaming', ethics: 'neutral' },
  ];
}

function linksForFilmOrSeries(reco: RecoLike): ResolvedLink[] {
  // Priorité aux plateformes finales détectées (TMDB watch providers).
  if (reco.watchProviders && reco.watchProviders.length > 0) {
    return reco.watchProviders.map((p) => ({
      label: p.label,
      url: p.url,
      kind: 'streaming' as const,
      ethics: p.ethics ?? 'neutral',
    }));
  }
  // Fallback : JustWatch (agrégateur neutre).
  const q = enc(query(reco.title, reco.creator));
  return [
    { label: 'JustWatch', url: `https://www.justwatch.com/fr/recherche?q=${q}`, kind: 'streaming', ethics: 'neutral' },
  ];
}

function linksForPodcast(reco: RecoLike): ResolvedLink[] {
  const q = enc(query(reco.title, reco.creator));
  return [
    { label: 'Apple Podcasts',  url: `https://podcasts.apple.com/fr/search?term=${q}`, kind: 'streaming', ethics: 'neutral' },
    { label: 'Spotify',         url: `https://open.spotify.com/search/${q}/shows`,     kind: 'streaming', ethics: 'neutral' },
    { label: 'Deezer',          url: `https://www.deezer.com/fr/search/${q}/podcast`,  kind: 'streaming', ethics: 'neutral' },
  ];
}

function linksForGame(reco: RecoLike): ResolvedLink[] {
  const q = enc(query(reco.title, reco.creator));
  return [
    { label: 'Steam',  url: `https://store.steampowered.com/search/?term=${q}`, kind: 'buy', ethics: 'neutral' },
    { label: 'Itch.io', url: `https://itch.io/search?q=${q}`,                   kind: 'buy', ethics: 'indie'   },
  ];
}

function linksForLiveShow(reco: RecoLike): ResolvedLink[] {
  const q = enc(query(reco.title, reco.creator));
  return [
    { label: 'Fnac Spectacles', url: `https://www.fnacspectacles.com/recherche/?searchTerm=${q}`, kind: 'buy', ethics: 'neutral' },
    { label: 'BilletReduc',     url: `https://www.billetreduc.com/recherche/index.htm?txt=${q}`,  kind: 'buy', ethics: 'neutral' },
  ];
}

function linksForPlace(reco: RecoLike): ResolvedLink[] {
  const q = enc(query(reco.title, reco.creator));
  return [
    { label: 'Google Maps', url: `https://www.google.com/maps/search/${q}`,            kind: 'info', ethics: 'neutral' },
    { label: 'Recherche',   url: `https://duckduckgo.com/?q=${q}`,                     kind: 'info', ethics: 'neutral' },
  ];
}

function linksForArtist(reco: RecoLike): ResolvedLink[] {
  // Un artiste/personne : Instagram + site officiel + recherche spectacles.
  // Les liens explicites (externalIds.instagram, externalIds.website) priment ;
  // sinon on génère des recherches.
  const q = enc(query(reco.title, reco.creator));
  const out: ResolvedLink[] = [];
  if (reco.externalIds?.instagram) {
    out.push({ label: 'Instagram', url: `https://www.instagram.com/${reco.externalIds.instagram.replace(/^@/, '')}/`, kind: 'social', ethics: 'neutral' });
  } else {
    out.push({ label: 'Instagram', url: `https://www.google.com/search?q=site%3Ainstagram.com+${q}`, kind: 'social', ethics: 'neutral' });
  }
  if (reco.externalIds?.website) {
    out.push({ label: 'Site officiel', url: reco.externalIds.website, kind: 'official', ethics: 'indie' });
  }
  out.push({ label: 'Fnac Spectacles', url: `https://www.fnacspectacles.com/recherche/?searchTerm=${q}`, kind: 'buy', ethics: 'neutral' });
  return out;
}

function linksForVideo(reco: RecoLike): ResolvedLink[] {
  // Vidéo ou chaîne YouTube : si on a l'URL exacte, on l'utilise. Sinon, recherche YT.
  if (reco.externalIds?.youtube) {
    const id = reco.externalIds.youtube;
    const url = id.startsWith('http') ? id : `https://www.youtube.com/watch?v=${id}`;
    return [{ label: 'YouTube', url, kind: 'streaming', ethics: 'neutral' }];
  }
  const q = enc(query(reco.title, reco.creator));
  return [
    { label: 'YouTube', url: `https://www.youtube.com/results?search_query=${q}`, kind: 'streaming', ethics: 'neutral' },
  ];
}

function linksForOther(reco: RecoLike): ResolvedLink[] {
  const q = enc(query(reco.title, reco.creator));
  return [
    { label: 'Recherche', url: `https://duckduckgo.com/?q=${q}`, kind: 'info', ethics: 'neutral' },
  ];
}

// =====================================================================
// API publique
// =====================================================================

/**
 * Renvoie une liste de liens éthiques pour une reco, classés du plus pertinent
 * au moins pertinent. Peut être vide si aucune plateforme dédiée ne convient.
 */
export function resolveLinks(reco: RecoLike): ResolvedLink[] {
  switch (reco.type) {
    case 'livre':
    case 'bd':
      return linksForBookOrComic(reco);
    case 'musique':
    case 'album':
      return linksForMusic(reco);
    case 'film':
    case 'serie':
      return linksForFilmOrSeries(reco);
    case 'podcast':
      return linksForPodcast(reco);
    case 'jeu':
      return linksForGame(reco);
    case 'spectacle':
      return linksForLiveShow(reco);
    case 'lieu':
      return linksForPlace(reco);
    case 'artiste':
      return linksForArtist(reco);
    case 'video':
      return linksForVideo(reco);
    default:
      return linksForOther(reco);
  }
}
