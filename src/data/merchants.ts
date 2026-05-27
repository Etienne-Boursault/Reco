/**
 * Résolveur de liens « éthiques ».
 *
 * Politique éditoriale :
 *   - JAMAIS de lien Amazon.
 *   - On évite les enseignes/médias du groupe Bolloré (Vivendi/Canal+, Editis,
 *     Hachette Livre via Lagardère, etc.) listés dans AVOID_DOMAINS.
 *   - On privilégie les plateformes indépendantes / françaises (ethics: "indie").
 *
 * En l'absence d'URL exacte fournie par le pipeline, on génère des liens de
 * RECHERCHE à partir du type d'œuvre + titre + créateur. Les motifs d'URL sont
 * « best effort » : faciles à ajuster ici si une plateforme change son endpoint.
 */

export type RecoLinkKind = 'buy' | 'borrow' | 'streaming' | 'info' | 'official';
export type Ethics = 'indie' | 'neutral' | 'avoid';

export interface ResolvedLink {
  label: string;
  url: string;
  kind: RecoLinkKind;
  ethics: Ethics;
}

/** Domaines à ne jamais proposer (Amazon + galaxie Bolloré, non exhaustif). */
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
  externalIds?: { isbn?: string; tmdb?: string; imdb?: string; musicbrainz?: string };
}

/**
 * Renvoie une liste de liens éthiques pour une reco, classés du plus pertinent
 * au moins pertinent. Peut être vide si aucune plateforme dédiée ne convient.
 */
export function resolveLinks(reco: RecoLike): ResolvedLink[] {
  const q = enc(query(reco.title, reco.creator));
  const links: ResolvedLink[] = [];

  switch (reco.type) {
    case 'livre':
    case 'bd': {
      // Libraires indépendants français, jamais Amazon.
      if (reco.externalIds?.isbn) {
        links.push({
          label: 'Place des Libraires',
          url: `https://www.placedeslibraires.fr/liste/?q=${enc(reco.externalIds.isbn)}`,
          kind: 'buy',
          ethics: 'indie',
        });
      }
      links.push(
        {
          label: 'Place des Libraires',
          url: `https://www.placedeslibraires.fr/liste/?q=${q}`,
          kind: 'buy',
          ethics: 'indie',
        },
        {
          label: 'Lalibrairie.com',
          url: `https://www.lalibrairie.com/livres/recherche.html?q=${q}`,
          kind: 'buy',
          ethics: 'indie',
        },
      );
      break;
    }

    case 'musique':
    case 'album': {
      links.push(
        {
          label: 'Bandcamp',
          url: `https://bandcamp.com/search?q=${q}`,
          kind: 'streaming',
          ethics: 'indie',
        },
        {
          label: 'Qobuz',
          url: `https://www.qobuz.com/fr-fr/search?q=${q}`,
          kind: 'buy',
          ethics: 'indie',
        },
      );
      break;
    }

    case 'film':
    case 'serie': {
      // JustWatch : agrégateur neutre (où voir/streamer légalement).
      links.push({
        label: 'JustWatch',
        url: `https://www.justwatch.com/fr/recherche?q=${q}`,
        kind: 'streaming',
        ethics: 'neutral',
      });
      break;
    }

    case 'jeu': {
      links.push({
        label: 'Recherche',
        url: `https://duckduckgo.com/?q=${enc(query(reco.title, reco.creator) + ' jeu')}`,
        kind: 'info',
        ethics: 'neutral',
      });
      break;
    }
  }

  // Pas de lien « fourre-tout » (ex. Wikipédia) : trop souvent hors-sujet.
  // Les recos sans plateforme dédiée n'affichent simplement aucun lien.
  return links;
}
