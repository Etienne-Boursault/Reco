/**
 * Tests du résolveur de liens éthiques (`src/data/merchants.ts`).
 *
 * Couvre :
 *   - `isSafeUrl` (garde protocolaire http/https),
 *   - `isAvoidedUrl` (politique anti-Amazon / anti-Bolloré, cf. AVOID_DOMAINS),
 *   - `query()` (dédup title/creator, observée via l'URL de recherche générée),
 *   - chaque résolveur par type (`linksFor*`) : URL exacte vs recherche,
 *   - `resolveLinks` multi-types (dédup URL, ordre, fallback `['autre']`),
 *   - validation du handle Instagram (aucune interpolation non validée).
 */
import { describe, it, expect } from 'vitest';
import {
  resolveLinks,
  isSafeUrl,
  isAvoidedUrl,
  AVOID_DOMAINS,
  type ResolvedLink,
} from '../../src/data/merchants';

/** Raccourci : construit une reco minimale mono-type. */
function reco(
  type: string,
  extra: Record<string, unknown> = {},
): Parameters<typeof resolveLinks>[0] {
  return { title: 'Titre', types: [type], ...extra } as Parameters<
    typeof resolveLinks
  >[0];
}

/** Trouve un lien par label exact dans une liste résolue. */
function byLabel(links: ResolvedLink[], label: string): ResolvedLink | undefined {
  return links.find((l) => l.label === label);
}

// ---------------------------------------------------------------------------
// isSafeUrl
// ---------------------------------------------------------------------------
describe('isSafeUrl', () => {
  it('accepte http et https', () => {
    expect(isSafeUrl('http://example.com')).toBe(true);
    expect(isSafeUrl('https://example.com/path?q=1')).toBe(true);
  });

  it('rejette javascript:, data: et autres protocoles', () => {
    expect(isSafeUrl('javascript:alert(1)')).toBe(false);
    expect(isSafeUrl('data:text/html;base64,PHN2Zz4=')).toBe(false);
    expect(isSafeUrl('ftp://example.com')).toBe(false);
    expect(isSafeUrl('mailto:x@y.com')).toBe(false);
  });

  it('rejette la chaîne vide, un chemin relatif et une valeur non parsable', () => {
    expect(isSafeUrl('')).toBe(false);
    expect(isSafeUrl('/relative/path')).toBe(false);
    expect(isSafeUrl('pas une url')).toBe(false);
  });

  it('rejette les valeurs non-string', () => {
    expect(isSafeUrl(undefined)).toBe(false);
    expect(isSafeUrl(null)).toBe(false);
    expect(isSafeUrl(42)).toBe(false);
    expect(isSafeUrl({})).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// isAvoidedUrl (D1 — branchement de AVOID_DOMAINS)
// ---------------------------------------------------------------------------
describe('isAvoidedUrl', () => {
  it('rejette Amazon et la galaxie Bolloré (match host + sous-domaines)', () => {
    expect(isAvoidedUrl('https://www.amazon.fr/dp/123')).toBe(true);
    expect(isAvoidedUrl('https://amazon.com/dp/123')).toBe(true);
    expect(isAvoidedUrl('https://boutique.canalplus.com/x')).toBe(true);
    expect(isAvoidedUrl('https://www.cnews.fr/article')).toBe(true);
    expect(isAvoidedUrl('https://europe1.fr/podcasts')).toBe(true);
  });

  it('accepte (ne bannit pas) les plateformes indépendantes/neutres', () => {
    expect(isAvoidedUrl('https://www.placedeslibraires.fr/x')).toBe(false);
    expect(isAvoidedUrl('https://bandcamp.com/search?q=x')).toBe(false);
    expect(isAvoidedUrl('https://www.justwatch.com/fr/film/dune')).toBe(false);
  });

  it('ne matche pas un domaine qui contient juste le nom en substring', () => {
    // « notamazon.fr » n'est PAS amazon.fr → pas de faux positif.
    expect(isAvoidedUrl('https://notamazon.fr/x')).toBe(false);
    expect(isAvoidedUrl('https://amazon.fr.evil.com/x')).toBe(false);
  });

  it('renvoie false sur entrée invalide ou non-string', () => {
    expect(isAvoidedUrl('')).toBe(false);
    expect(isAvoidedUrl('pas une url')).toBe(false);
    expect(isAvoidedUrl(undefined)).toBe(false);
    expect(isAvoidedUrl(null)).toBe(false);
  });

  it('AVOID_DOMAINS contient bien Amazon et des marques Bolloré', () => {
    expect(AVOID_DOMAINS).toContain('amazon.fr');
    expect(AVOID_DOMAINS).toContain('canalplus.com');
  });
});

// ---------------------------------------------------------------------------
// query() — dédup title/creator (observée via l'URL DuckDuckGo de `autre`)
// ---------------------------------------------------------------------------
describe('query() (via linksForOther)', () => {
  function ddgQuery(links: ResolvedLink[]): string {
    const l = byLabel(links, 'Recherche');
    const u = new URL(l!.url);
    return u.searchParams.get('q') ?? '';
  }

  it('sans creator : garde le titre seul', () => {
    const q = ddgQuery(resolveLinks(reco('autre', { title: 'Dune' })));
    expect(q).toBe('Dune');
  });

  it('title === creator : ne duplique pas', () => {
    const q = ddgQuery(
      resolveLinks(reco('autre', { title: 'Radiohead', creator: 'Radiohead' })),
    );
    expect(q).toBe('Radiohead');
  });

  it('creator inclus dans le titre : garde le titre (le plus long)', () => {
    const q = ddgQuery(
      resolveLinks(
        reco('autre', { title: 'The Beatles Anthology', creator: 'The Beatles' }),
      ),
    );
    expect(q).toBe('The Beatles Anthology');
  });

  it('titre inclus dans le creator : garde le creator (le plus long)', () => {
    const q = ddgQuery(
      resolveLinks(reco('autre', { title: 'Beatles', creator: 'The Beatles' })),
    );
    expect(q).toBe('The Beatles');
  });

  it('title et creator distincts : concatène', () => {
    const q = ddgQuery(
      resolveLinks(reco('autre', { title: 'Dune', creator: 'Frank Herbert' })),
    );
    expect(q).toBe('Dune Frank Herbert');
  });
});

// ---------------------------------------------------------------------------
// linksForBookOrComic (livre / bd)
// ---------------------------------------------------------------------------
describe('livre / bd', () => {
  it('sans ISBN : Place des Libraires + Lalibrairie en recherche', () => {
    const links = resolveLinks(reco('livre', { title: 'Dune' }));
    const pdl = byLabel(links, 'Place des Libraires');
    const lal = byLabel(links, 'Lalibrairie.com');
    expect(pdl?.url).toContain('mots_recherche=Dune');
    expect(pdl?.ethics).toBe('indie');
    expect(lal?.url).toContain('recherche.html?q=Dune');
    expect(lal?.ethics).toBe('indie');
  });

  it('avec ISBN : Place des Libraires cible l’ISBN exact', () => {
    const links = resolveLinks(
      reco('livre', { title: 'Dune', externalIds: { isbn: '9782070360024' } }),
    );
    const pdl = byLabel(links, 'Place des Libraires');
    expect(pdl?.url).toContain('mots_recherche=9782070360024');
  });

  it('type bd emprunte le même résolveur', () => {
    const links = resolveLinks(reco('bd', { title: 'Persepolis' }));
    expect(byLabel(links, 'Place des Libraires')).toBeDefined();
  });
});

// ---------------------------------------------------------------------------
// linksForMusic (musique / album)
// ---------------------------------------------------------------------------
describe('musique / album', () => {
  it('sans enrichissement : Deezer & Spotify en recherche, Bandcamp en tête', () => {
    const links = resolveLinks(reco('musique', { title: 'OK Computer' }));
    expect(links[0].label).toBe('Bandcamp');
    expect(byLabel(links, 'Deezer')?.url).toContain('deezer.com/fr/search/');
    expect(byLabel(links, 'Spotify')?.url).toContain('open.spotify.com/search/');
  });

  it('avec URL Deezer/Spotify exactes : utilise ces URLs', () => {
    const links = resolveLinks(
      reco('album', {
        title: 'OK Computer',
        externalIds: {
          deezer: 'https://www.deezer.com/album/12345',
          spotify: 'https://open.spotify.com/album/abc',
        },
      }),
    );
    expect(byLabel(links, 'Deezer')?.url).toBe('https://www.deezer.com/album/12345');
    expect(byLabel(links, 'Spotify')?.url).toBe('https://open.spotify.com/album/abc');
  });
});

// ---------------------------------------------------------------------------
// linksForFilmOrSeries (film / serie)
// ---------------------------------------------------------------------------
describe('film / serie', () => {
  it('sans JustWatch exact : recherche JustWatch', () => {
    const links = resolveLinks(reco('film', { title: 'Dune' }));
    expect(links).toHaveLength(1);
    expect(links[0].label).toBe('JustWatch');
    expect(links[0].url).toContain('justwatch.com/fr/recherche?q=Dune');
  });

  it('avec JustWatch exact : lien direct vers la fiche', () => {
    const links = resolveLinks(
      reco('serie', {
        title: 'Dune',
        externalIds: { justwatch: 'https://www.justwatch.com/fr/film/dune' },
      }),
    );
    expect(links).toHaveLength(1);
    expect(links[0].url).toBe('https://www.justwatch.com/fr/film/dune');
  });
});

// ---------------------------------------------------------------------------
// linksForVideo (video) — ID vs URL vs recherche + garde de sécurité
// ---------------------------------------------------------------------------
describe('video', () => {
  it('ID YouTube canonique (11 chars) : watch?v=', () => {
    const links = resolveLinks(
      reco('video', { title: 'X', externalIds: { youtube: 'dQw4w9WgXcQ' } }),
    );
    expect(links[0].url).toBe('https://www.youtube.com/watch?v=dQw4w9WgXcQ');
  });

  it('URL YouTube absolue : utilise l’URL telle quelle', () => {
    const links = resolveLinks(
      reco('video', {
        title: 'X',
        externalIds: { youtube: 'https://youtu.be/dQw4w9WgXcQ' },
      }),
    );
    expect(links[0].url).toBe('https://youtu.be/dQw4w9WgXcQ');
  });

  it('valeur non-YouTube / non-sûre : retombe sur la recherche', () => {
    const links = resolveLinks(
      reco('video', {
        title: 'Ma Vidéo',
        externalIds: { youtube: 'javascript:alert(1)' },
      }),
    );
    expect(links[0].url).toContain('youtube.com/results?search_query=');
  });

  it('URL non-YouTube (autre host) : ignorée → recherche', () => {
    const links = resolveLinks(
      reco('video', {
        title: 'Ma Vidéo',
        externalIds: { youtube: 'https://vimeo.com/12345' },
      }),
    );
    expect(links[0].url).toContain('youtube.com/results?search_query=');
  });

  it('champ youtube vide : recherche', () => {
    const links = resolveLinks(
      reco('video', { title: 'Ma Vidéo', externalIds: { youtube: '' } }),
    );
    expect(links[0].url).toContain('youtube.com/results?search_query=');
  });

  it('sans externalIds : recherche', () => {
    const links = resolveLinks(reco('video', { title: 'Ma Vidéo' }));
    expect(links[0].url).toContain('youtube.com/results?search_query=');
  });
});

// ---------------------------------------------------------------------------
// linksForArtist (artiste) — Instagram validé + website
// ---------------------------------------------------------------------------
describe('artiste', () => {
  it('handle Instagram valide : lien direct (avec @ retiré)', () => {
    const links = resolveLinks(
      reco('artiste', { title: 'Jean', externalIds: { instagram: '@jean.dupont' } }),
    );
    expect(byLabel(links, 'Instagram')?.url).toBe(
      'https://www.instagram.com/jean.dupont/',
    );
  });

  it('handle Instagram invalide : retombe sur une recherche (pas d’interpolation brute)', () => {
    const links = resolveLinks(
      reco('artiste', {
        title: 'Jean',
        externalIds: { instagram: 'bad/../path?x=1' },
      }),
    );
    const ig = byLabel(links, 'Instagram');
    // Ne DOIT PAS injecter le handle hostile dans le path instagram.com.
    expect(ig?.url).not.toContain('bad/../path');
    expect(ig?.url).toContain('google.com/search');
  });

  it('sans handle : recherche Instagram via Google', () => {
    const links = resolveLinks(reco('artiste', { title: 'Jean' }));
    expect(byLabel(links, 'Instagram')?.url).toContain('site%3Ainstagram.com');
  });

  it('website http(s) sûr : ajoute « Site officiel »', () => {
    const links = resolveLinks(
      reco('artiste', {
        title: 'Jean',
        externalIds: { website: 'https://jean.example' },
      }),
    );
    expect(byLabel(links, 'Site officiel')?.url).toBe('https://jean.example');
  });

  it('website non-sûr (javascript:) : pas de « Site officiel »', () => {
    const links = resolveLinks(
      reco('artiste', {
        title: 'Jean',
        externalIds: { website: 'javascript:alert(1)' },
      }),
    );
    expect(byLabel(links, 'Site officiel')).toBeUndefined();
  });
});

// ---------------------------------------------------------------------------
// Autres résolveurs mono-type
// ---------------------------------------------------------------------------
describe('podcast / jeu / spectacle / lieu / autre', () => {
  it('podcast : Apple Podcasts + Spotify + Deezer', () => {
    const links = resolveLinks(reco('podcast', { title: 'X' }));
    expect(links.map((l) => l.label)).toEqual([
      'Apple Podcasts',
      'Spotify',
      'Deezer',
    ]);
  });

  it('jeu : Steam + Itch.io (indie)', () => {
    const links = resolveLinks(reco('jeu', { title: 'Celeste' }));
    expect(byLabel(links, 'Steam')).toBeDefined();
    expect(byLabel(links, 'Itch.io')?.ethics).toBe('indie');
  });

  it('spectacle : Fnac Spectacles + BilletReduc', () => {
    const links = resolveLinks(reco('spectacle', { title: 'X' }));
    expect(links.map((l) => l.label)).toEqual(['Fnac Spectacles', 'BilletReduc']);
  });

  it('lieu : Google Maps + Recherche', () => {
    const links = resolveLinks(reco('lieu', { title: 'Musée' }));
    expect(byLabel(links, 'Google Maps')?.url).toContain('google.com/maps/search/');
    expect(byLabel(links, 'Recherche')?.url).toContain('duckduckgo.com');
  });

  it('type inconnu : résolveur « autre » (DuckDuckGo)', () => {
    const links = resolveLinks(reco('inconnu', { title: 'X' }));
    expect(links).toHaveLength(1);
    expect(links[0].label).toBe('Recherche');
    expect(links[0].url).toContain('duckduckgo.com');
  });
});

// ---------------------------------------------------------------------------
// resolveLinks — multi-types, dédup, ordre, fallback
// ---------------------------------------------------------------------------
describe('resolveLinks (agrégation)', () => {
  it('dédup par URL entre types identiques (film + serie)', () => {
    const links = resolveLinks(reco('film', { title: 'Dune', types: ['film', 'serie'] } as never));
    // film et serie produisent la même recherche JustWatch → 1 seul lien.
    expect(links).toHaveLength(1);
    expect(links[0].label).toBe('JustWatch');
  });

  it('ordre : les liens suivent l’ordre de reco.types', () => {
    const links = resolveLinks({
      title: 'Dune',
      types: ['livre', 'musique'],
    } as Parameters<typeof resolveLinks>[0]);
    // Livre d'abord (Place des Libraires), puis musique (Bandcamp).
    expect(links[0].label).toBe('Place des Libraires');
    expect(byLabel(links, 'Bandcamp')).toBeDefined();
    const idxBook = links.findIndex((l) => l.label === 'Place des Libraires');
    const idxMusic = links.findIndex((l) => l.label === 'Bandcamp');
    expect(idxBook).toBeLessThan(idxMusic);
  });

  it('types vide : fallback sur « autre »', () => {
    const links = resolveLinks({
      title: 'X',
      types: [],
    } as unknown as Parameters<typeof resolveLinks>[0]);
    expect(links).toHaveLength(1);
    expect(links[0].label).toBe('Recherche');
  });

  it('chaque lien porte kind + ethics typés', () => {
    const links = resolveLinks(reco('livre', { title: 'Dune' }));
    for (const l of links) {
      expect(typeof l.label).toBe('string');
      expect(isSafeUrl(l.url)).toBe(true);
      expect(['buy', 'borrow', 'streaming', 'info', 'official', 'social']).toContain(l.kind);
      expect(['indie', 'neutral', 'avoid']).toContain(l.ethics);
    }
  });
});
