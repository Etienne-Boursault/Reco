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

/**
 * Vrai si la chaîne est une URL absolue http(s) bien formée. Utilisé pour
 * filtrer les valeurs externes (website, youtube) qui pourraient être tout
 * et n'importe quoi (chaîne vide, chemin relatif, `javascript:`, …).
 */
export function isSafeUrl(u: unknown): boolean {
  if (typeof u !== 'string' || u.length === 0) return false;
  try {
    const parsed = new URL(u);
    return parsed.protocol === 'http:' || parsed.protocol === 'https:';
  } catch {
    return false;
  }
}

/** ID YouTube : 11 caractères alphanumériques + `_`/`-`. */
const YT_ID_RE = /^[\w-]{11}$/;
/** URL YouTube reconnue (youtube.com ou youtu.be). */
const YT_URL_RE = /^https?:\/\/(?:www\.|m\.)?(?:youtube\.com|youtu\.be)\//i;

/** Construit la requête de recherche à partir des champs de la reco.
 *  Évite la duplication quand le LLM met le même contenu dans title et
 *  creator (cas observé pour les types `artiste` où title=creator=nom). */
function query(title: string, creator?: string): string {
  const t = title.trim();
  const c = creator?.trim();
  if (!c) return t;
  // Dédupe : si creator est inclus dans title ou inversement, on garde le plus long.
  const tn = t.toLowerCase();
  const cn = c.toLowerCase();
  if (tn === cn || tn.includes(cn)) return t;
  if (cn.includes(tn)) return c;
  return `${t} ${c}`;
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
    /** URL JustWatch EXACTE du film/série (renvoyée par TMDB).
     *  Page qui a les vrais deeplinks « Watch on Netflix » etc. */
    justwatch?: string;
    /** URL Deezer / Spotify EXACTES (track / album / artist) — peuplées par
     *  tools/enrich_music.py. Préférées à une recherche quand disponibles. */
    deezer?: string;
    spotify?: string;
  };
  /** Liens explicites fournis par la reco — gardés tels quels (pas filtrés). */
  links?: { label: string; url: string; kind?: RecoLinkKind; ethics?: Ethics }[];
  /** Plateformes de streaming (info brute TMDB).
   *  ⚠️ Pas utilisées comme liens (les URLs ne sont que des recherches), mais
   *  conservées pour affichage informatif des plateformes où le film est dispo. */
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
    // Si on a l'ISBN, on cible la fiche exacte chez Place des Libraires.
    // Pas besoin du 2e lien générique « recherche par titre » qui ferait
    // doublon — on complète juste par Lalibrairie.com.
    out.push({
      label: 'Place des Libraires',
      url: `https://www.placedeslibraires.fr/liste/?q=${enc(reco.externalIds.isbn)}`,
      kind: 'buy', ethics: 'indie',
    });
  } else {
    out.push({
      label: 'Place des Libraires',
      url: `https://www.placedeslibraires.fr/liste/?q=${q}`,
      kind: 'buy', ethics: 'indie',
    });
  }
  out.push({
    label: 'Lalibrairie.com',
    url: `https://www.lalibrairie.com/livres/recherche.html?q=${q}`,
    kind: 'buy', ethics: 'indie',
  });
  return out;
}

function linksForMusic(reco: RecoLike): ResolvedLink[] {
  const q = enc(query(reco.title, reco.creator));
  // Bandcamp en 1er (modèle artiste-first), puis Deezer & Spotify avec URL
  // EXACTE quand on a été enrichi (sinon recherche), puis Qobuz / Apple / YT
  // Music / Tidal en recherche (pas d'API pour deeplinks publics).
  const deezerUrl = reco.externalIds?.deezer
    ?? `https://www.deezer.com/fr/search/${q}`;
  const spotifyUrl = reco.externalIds?.spotify
    ?? `https://open.spotify.com/search/${q}`;
  return [
    { label: 'Bandcamp',    url: `https://bandcamp.com/search?q=${q}`,             kind: 'streaming', ethics: 'indie'   },
    { label: 'Deezer',      url: deezerUrl,                                        kind: 'streaming', ethics: 'neutral' },
    { label: 'Spotify',     url: spotifyUrl,                                       kind: 'streaming', ethics: 'neutral' },
    { label: 'Qobuz',       url: `https://www.qobuz.com/fr-fr/search?q=${q}`,      kind: 'buy',       ethics: 'indie'   },
    { label: 'Apple Music', url: `https://music.apple.com/fr/search?term=${q}`,    kind: 'streaming', ethics: 'neutral' },
    { label: 'YT Music',    url: `https://music.youtube.com/search?q=${q}`,        kind: 'streaming', ethics: 'neutral' },
    { label: 'Tidal',       url: `https://tidal.com/search?q=${q}`,                kind: 'streaming', ethics: 'neutral' },
  ];
}

function linksForFilmOrSeries(reco: RecoLike): ResolvedLink[] {
  // 1) URL JustWatch EXACTE de la fiche (donnée par TMDB) — c'est là qu'il y
  //    a les vrais boutons « Watch on Netflix », « Watch on Apple TV », etc.
  if (reco.externalIds?.justwatch) {
    return [
      { label: 'JustWatch', url: reco.externalIds.justwatch, kind: 'streaming', ethics: 'neutral' },
    ];
  }
  // 2) Sinon : recherche JustWatch (pour les films non enrichis TMDB).
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
  if (isSafeUrl(reco.externalIds?.website)) {
    out.push({ label: 'Site officiel', url: reco.externalIds!.website!, kind: 'official', ethics: 'indie' });
  }
  out.push({ label: 'Fnac Spectacles', url: `https://www.fnacspectacles.com/recherche/?searchTerm=${q}`, kind: 'buy', ethics: 'neutral' });
  return out;
}

function linksForVideo(reco: RecoLike): ResolvedLink[] {
  // Vidéo ou chaîne YouTube : si on a l'URL exacte, on l'utilise. Sinon, recherche YT.
  // On valide :
  //  - soit un ID YouTube canonique (11 caractères [A-Za-z0-9_-]),
  //  - soit une URL absolue http(s) sur youtube.com / youtu.be.
  // Toute autre valeur est ignorée → on retombe sur la recherche.
  const yt = reco.externalIds?.youtube;
  if (typeof yt === 'string' && yt.length > 0) {
    if (YT_ID_RE.test(yt)) {
      return [{
        label: 'YouTube',
        url: `https://www.youtube.com/watch?v=${yt}`,
        kind: 'streaming', ethics: 'neutral',
      }];
    }
    if (isSafeUrl(yt) && YT_URL_RE.test(yt)) {
      return [{ label: 'YouTube', url: yt, kind: 'streaming', ethics: 'neutral' }];
    }
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
