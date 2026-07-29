/**
 * Tests du CONTRAT DE DONNÉES (`src/content.config.ts`).
 *
 * Ces schémas Zod sont la source de vérité du projet : le pipeline Python
 * (tools/) doit produire des JSON qui les satisfont, et le build Astro casse
 * sinon. On les valide ici hors build, en confrontant chaque collection à des
 * objets valides ET invalides :
 *   - champs obligatoires manquants,
 *   - regexes (id, recoPrefix, couleur hexa, timestamp),
 *   - enums (types d'œuvre, ethics, status, kind, severity…),
 *   - valeurs par défaut appliquées au parse,
 *   - coercition de date,
 *   - asymétries VOULUES entre collections (`guestWork` nullable côté mention
 *     mais pas côté reco ; `linkOverrides` validé en URL côté reco seulement).
 *
 * Les schémas ne sont pas exportés individuellement : on passe par
 * `collections.<nom>.schema`, ce qu'Astro expose.
 */
import { describe, it, expect } from 'vitest';
import { collections } from '../../src/content.config';

type AnySchema = {
  safeParse: (v: unknown) => { success: boolean; data?: any; error?: any };
  parse: (v: unknown) => any;
  shape: Record<string, any>;
};

const schemaOf = (name: keyof typeof collections): AnySchema =>
  (collections[name] as unknown as { schema: AnySchema }).schema;

const sources = schemaOf('sources');
const episodes = schemaOf('episodes');
const recos = schemaOf('recos');
const items = schemaOf('items');
const mentions = schemaOf('mentions');

/** Assertion courte : le parse échoue. */
function rejects(schema: AnySchema, value: unknown) {
  expect(schema.safeParse(value).success).toBe(false);
}

/** Assertion courte : le parse réussit, et renvoie la donnée normalisée. */
function accepts(schema: AnySchema, value: unknown) {
  const res = schema.safeParse(value);
  expect(
    res.success,
    res.success ? '' : JSON.stringify(res.error?.issues),
  ).toBe(true);
  return res.data;
}

// ---------------------------------------------------------------------------
// Structure générale
// ---------------------------------------------------------------------------
describe('collections exportées', () => {
  it('expose exactement les cinq collections du projet', () => {
    expect(Object.keys(collections).sort()).toEqual([
      'episodes',
      'items',
      'mentions',
      'recos',
      'sources',
    ]);
  });

  it('chaque collection a un loader et un schéma', () => {
    for (const name of Object.keys(collections)) {
      const c = collections[name as keyof typeof collections] as any;
      expect(typeof c.loader, name).not.toBe('undefined');
      expect(typeof c.schema.safeParse, name).toBe('function');
    }
  });
});

// ---------------------------------------------------------------------------
// SOURCES
// ---------------------------------------------------------------------------
const THEME_OK = {
  colors: {
    bg: '#000000',
    surface: '#111111',
    text: '#ffffff',
    muted: '#888888',
    accent: '#ff0000',
  },
};

const SOURCE_MIN = {
  id: 'un-bon-moment',
  title: 'Un Bon Moment',
  theme: THEME_OK,
};

describe('schéma sources', () => {
  it('accepte une source minimale', () => {
    const d = accepts(sources, SOURCE_MIN);
    expect(d.hosts).toEqual([]);
  });

  it('applique les polices et accentText par défaut du thème', () => {
    const d = accepts(sources, SOURCE_MIN);
    expect(d.theme.fontDisplay).toBe('Reco Display');
    expect(d.theme.fontBody).toBe('Reco Body');
    expect(d.theme.colors.accentText).toBe('#ffffff');
  });

  it('refuse une source sans titre', () => {
    rejects(sources, { id: 'abc', theme: THEME_OK });
  });

  it('refuse une source sans thème', () => {
    rejects(sources, { id: 'abc', title: 'T' });
  });

  it('refuse un thème incomplet (couleur manquante)', () => {
    rejects(sources, {
      ...SOURCE_MIN,
      theme: { colors: { bg: '#000000', surface: '#111111' } },
    });
  });

  it.each([
    ['un-bon-moment', true],
    ['abc', true],
    ['a1', true],
    ['abc-123-def', true],
    ['Un-Bon-Moment', false], // majuscules interdites
    ['-abc', false], // tiret en tête
    ['abc-', false], // tiret en fin
    ['abc--def', false], // tirets consécutifs
    ['abc_def', false], // underscore interdit
    ['', false],
  ])('id « %s » → accepté: %s', (id, ok) => {
    const res = sources.safeParse({ ...SOURCE_MIN, id });
    expect(res.success).toBe(ok);
  });

  it.each([
    ['ubm', true],
    ['ab', true],
    ['abcdefgh', true],
    ['a', false], // < 2
    ['abcdefghi', false], // > 8
    ['ABC', false], // majuscules
    ['ab-cd', false], // tiret interdit
  ])('recoPrefix « %s » → accepté: %s', (recoPrefix, ok) => {
    expect(sources.safeParse({ ...SOURCE_MIN, recoPrefix }).success).toBe(ok);
  });

  it.each([
    ['#ff0000', true],
    ['#FF00aa', true],
    ['#f00', false], // forme courte refusée
    ['ff0000', false], // # manquant
    ['#gg0000', false], // hors hexa
    ['#ff00000', false], // 7 chiffres
  ])('siteColorAccent « %s » → accepté: %s', (siteColorAccent, ok) => {
    expect(
      sources.safeParse({ ...SOURCE_MIN, siteColorAccent }).success,
    ).toBe(ok);
  });

  it('valide les URLs (rssUrl, website, youtubeChannel)', () => {
    accepts(sources, {
      ...SOURCE_MIN,
      rssUrl: 'https://feeds.acast.com/x.rss',
      website: 'https://example.org',
      youtubeChannel: 'https://youtube.com/@chaine',
    });
    rejects(sources, { ...SOURCE_MIN, rssUrl: 'pas-une-url' });
    rejects(sources, { ...SOURCE_MIN, website: '/relatif' });
  });

  it('restreint transcriptDefaultSource à youtube|acast', () => {
    accepts(sources, { ...SOURCE_MIN, transcriptDefaultSource: 'youtube' });
    accepts(sources, { ...SOURCE_MIN, transcriptDefaultSource: 'acast' });
    rejects(sources, { ...SOURCE_MIN, transcriptDefaultSource: 'spotify' });
  });

  it('accepte les liens « Soutenir » sur les plateformes autorisées', () => {
    const d = accepts(sources, {
      ...SOURCE_MIN,
      support: [
        { platform: 'kofi', url: 'https://ko-fi.com/x' },
        { platform: 'liberapay', url: 'https://liberapay.com/x', label: 'Don' },
      ],
    });
    expect(d.support).toHaveLength(2);
  });

  it('refuse uTip (service fermé, retiré de l’enum)', () => {
    rejects(sources, {
      ...SOURCE_MIN,
      support: [{ platform: 'utip', url: 'https://utip.io/x' }],
    });
  });

  it('refuse un lien de soutien sans URL valide', () => {
    rejects(sources, {
      ...SOURCE_MIN,
      support: [{ platform: 'paypal', url: 'paypal.me/x' }],
    });
  });

  it('refuse un schemaVersion non entier', () => {
    accepts(sources, { ...SOURCE_MIN, schemaVersion: 3 });
    rejects(sources, { ...SOURCE_MIN, schemaVersion: 3.5 });
  });

  it('accepte les listes de patterns et avoidBrands', () => {
    const d = accepts(sources, {
      ...SOURCE_MIN,
      extractionAnchorPatterns: ['je recommande'],
      youtubeTitleSuffixPatterns: ['\\(best of\\)'],
      avoidBrands: ['Amazon'],
      enabled: true,
      spotifyShowId: 'abc123',
    });
    expect(d.avoidBrands).toEqual(['Amazon']);
  });
});

// ---------------------------------------------------------------------------
// EPISODES
// ---------------------------------------------------------------------------
const EPISODE_MIN = { sourceId: 'ubm', guid: 'guid-1', title: 'Épisode 1' };

describe('schéma episodes', () => {
  it('accepte un épisode minimal et applique les valeurs par défaut', () => {
    const d = accepts(episodes, EPISODE_MIN);
    expect(d.guests).toEqual([]);
    expect(d.guestsParsed).toEqual([]);
    expect(d.guestsExcluded).toEqual([]);
    expect(d.transcriptStatus).toBe('none');
  });

  it('résout sourceId en référence de collection', () => {
    const d = accepts(episodes, EPISODE_MIN);
    expect(d.sourceId).toEqual({ id: 'ubm', collection: 'sources' });
  });

  it('refuse un épisode sans guid', () => {
    rejects(episodes, { sourceId: 'ubm', title: 'T' });
  });

  it('refuse un épisode sans titre', () => {
    rejects(episodes, { sourceId: 'ubm', guid: 'g' });
  });

  it('coerce une date ISO en objet Date', () => {
    const d = accepts(episodes, { ...EPISODE_MIN, date: '2026-03-12' });
    expect(d.date).toBeInstanceOf(Date);
    expect(d.date.toISOString()).toBe('2026-03-12T00:00:00.000Z');
  });

  it('refuse une date non parsable', () => {
    rejects(episodes, { ...EPISODE_MIN, date: 'un jour de mars' });
  });

  it('refuse un numéro d’épisode non entier', () => {
    accepts(episodes, { ...EPISODE_MIN, number: 42, season: 2 });
    rejects(episodes, { ...EPISODE_MIN, number: 4.2 });
    rejects(episodes, { ...EPISODE_MIN, season: 1.5 });
  });

  it('refuse une durée non entière', () => {
    accepts(episodes, {
      ...EPISODE_MIN,
      audioDuration: 3600,
      youtubeDuration: 3580,
    });
    rejects(episodes, { ...EPISODE_MIN, audioDuration: 3600.5 });
  });

  it('valide les URLs audio / YouTube / image', () => {
    accepts(episodes, {
      ...EPISODE_MIN,
      audioUrl: 'https://cdn.acast.com/a.mp3',
      youtubeUrl: 'https://youtu.be/abc',
      imageUrl: 'https://cdn.acast.com/a.jpg',
    });
    rejects(episodes, { ...EPISODE_MIN, audioUrl: 'a.mp3' });
  });

  it.each(['none', 'auto', 'validated'])(
    'accepte transcriptStatus « %s »',
    (transcriptStatus) => {
      accepts(episodes, { ...EPISODE_MIN, transcriptStatus });
    },
  );

  it('refuse un transcriptStatus inconnu', () => {
    rejects(episodes, { ...EPISODE_MIN, transcriptStatus: 'en-cours' });
  });

  it.each(['info', 'warning', 'error', 'critical'])(
    'matchSuspectReasons accepte la severity « %s » (ADR 0019, 4 niveaux)',
    (severity) => {
      accepts(episodes, {
        ...EPISODE_MIN,
        matchSuspect: true,
        matchSuspectReasons: [{ kind: 'duration', detail: 'écart', severity }],
      });
    },
  );

  it('refuse une severity hors des 4 niveaux unifiés', () => {
    rejects(episodes, {
      ...EPISODE_MIN,
      matchSuspectReasons: [
        { kind: 'duration', detail: 'écart', severity: 'debug' },
      ],
    });
  });

  it('refuse une raison de suspicion incomplète', () => {
    rejects(episodes, {
      ...EPISODE_MIN,
      matchSuspectReasons: [{ kind: 'duration', severity: 'warning' }],
    });
  });

  it('accepte les champs de suivi du match YT/Acast', () => {
    const d = accepts(episodes, {
      ...EPISODE_MIN,
      youtubeTitle: 'Titre YT',
      youtubeUnavailable: true,
      transcriptModel: 'large-v3',
      matchSuspectAuditedAt: '2026-07-24T10:00:00Z',
      description: 'desc',
      guests: ['Invité'],
      guestsParsed: ['Invité'],
      guestsExcluded: ['seb de bon matin'],
    });
    expect(d.youtubeUnavailable).toBe(true);
    expect(d.guestsExcluded).toEqual(['seb de bon matin']);
  });
});

// ---------------------------------------------------------------------------
// RECOS
// ---------------------------------------------------------------------------
const RECO_MIN = {
  id: 'ubm-0001',
  sourceId: 'ubm',
  episodeGuid: 'guid-1',
  title: 'Interstellar',
  types: ['film'],
};

describe('schéma recos', () => {
  it('accepte une reco minimale et applique les défauts', () => {
    const d = accepts(recos, RECO_MIN);
    expect(d.links).toEqual([]);
    expect(d.status).toBe('draft');
    expect(d.kind).toBe('reco');
  });

  it('refuse une reco sans types', () => {
    const { types, ...sansTypes } = RECO_MIN;
    rejects(recos, sansTypes);
  });

  it('refuse un tableau de types vide (min 1)', () => {
    rejects(recos, { ...RECO_MIN, types: [] });
  });

  it('refuse un type d’œuvre inconnu', () => {
    rejects(recos, { ...RECO_MIN, types: ['nft'] });
  });

  it('accepte les types multiples', () => {
    const d = accepts(recos, { ...RECO_MIN, types: ['film', 'livre'] });
    expect(d.types).toEqual(['film', 'livre']);
  });

  it('couvre les 14 types déclarés', () => {
    const options: string[] = recos.shape.types.element.options;
    expect(options).toHaveLength(14);
    for (const type of options) {
      accepts(recos, { ...RECO_MIN, types: [type] });
    }
  });

  it('refuse une reco sans episodeGuid', () => {
    const { episodeGuid, ...sansGuid } = RECO_MIN;
    rejects(recos, sansGuid);
  });

  it('refuse un year non entier', () => {
    accepts(recos, { ...RECO_MIN, year: 2014 });
    rejects(recos, { ...RECO_MIN, year: 2014.5 });
  });

  // --- links ---------------------------------------------------------------
  it('applique kind=info et ethics=neutral par défaut sur un lien', () => {
    const d = accepts(recos, {
      ...RECO_MIN,
      links: [{ label: 'Fiche', url: 'https://example.org/x' }],
    });
    expect(d.links[0].kind).toBe('info');
    expect(d.links[0].ethics).toBe('neutral');
  });

  it.each(['buy', 'borrow', 'streaming', 'info', 'official', 'social'])(
    'accepte le lien de kind « %s »',
    (kind) => {
      accepts(recos, {
        ...RECO_MIN,
        links: [{ label: 'L', url: 'https://example.org', kind }],
      });
    },
  );

  it.each(['indie', 'neutral', 'avoid'])(
    'accepte l’ethics « %s » (Amazon/Bolloré sont marqués avoid, pas supprimés)',
    (ethics) => {
      accepts(recos, {
        ...RECO_MIN,
        links: [{ label: 'L', url: 'https://example.org', ethics }],
      });
    },
  );

  it('refuse un kind de lien inconnu', () => {
    rejects(recos, {
      ...RECO_MIN,
      links: [{ label: 'L', url: 'https://example.org', kind: 'affiliate' }],
    });
  });

  it('refuse un lien sans URL valide ou sans label', () => {
    rejects(recos, { ...RECO_MIN, links: [{ label: 'L', url: 'example.org' }] });
    rejects(recos, { ...RECO_MIN, links: [{ url: 'https://example.org' }] });
  });

  // --- externalIds ---------------------------------------------------------
  it('accepte des externalIds partiels', () => {
    const d = accepts(recos, {
      ...RECO_MIN,
      externalIds: { tmdb: '157336', tmdbType: 'movie', imdb: 'tt0816692' },
    });
    expect(d.externalIds.tmdb).toBe('157336');
  });

  it('accepte un objet externalIds vide', () => {
    accepts(recos, { ...RECO_MIN, externalIds: {} });
  });

  it('exige un identifiant TMDB sous forme de chaîne côté reco', () => {
    rejects(recos, { ...RECO_MIN, externalIds: { tmdb: 157336 } });
  });

  it('restreint tmdbType à movie|tv', () => {
    accepts(recos, { ...RECO_MIN, externalIds: { tmdbType: 'tv' } });
    rejects(recos, { ...RECO_MIN, externalIds: { tmdbType: 'anime' } });
  });

  it('valide les URLs exactes (justwatch, deezer, spotify, website)', () => {
    accepts(recos, {
      ...RECO_MIN,
      externalIds: {
        justwatch: 'https://www.justwatch.com/fr/film/interstellar',
        deezer: 'https://www.deezer.com/album/1',
        spotify: 'https://open.spotify.com/album/1',
        website: 'https://example.org',
      },
    });
    rejects(recos, { ...RECO_MIN, externalIds: { deezer: 'deezer.com/album/1' } });
  });

  it('accepte les handles sociaux en chaîne libre (sans @)', () => {
    const d = accepts(recos, {
      ...RECO_MIN,
      externalIds: { instagram: 'verino', tiktok: 'verino', youtube: 'abc123' },
    });
    expect(d.externalIds.instagram).toBe('verino');
  });

  // --- overrides et liens manuels -----------------------------------------
  it('linkOverrides exige des URLs valides côté reco', () => {
    accepts(recos, {
      ...RECO_MIN,
      linkOverrides: { 'Place des Libraires': 'https://placedeslibraires.fr/x' },
    });
    rejects(recos, {
      ...RECO_MIN,
      linkOverrides: { JustWatch: 'pas-une-url' },
    });
  });

  it('accepte des customLinks avec logo optionnel', () => {
    const d = accepts(recos, {
      ...RECO_MIN,
      customLinks: [
        { label: 'Site', url: 'https://example.org' },
        { label: 'Autre', url: 'https://x.org', logoUrl: 'https://x.org/l.png' },
      ],
    });
    expect(d.customLinks).toHaveLength(2);
  });

  it('refuse un customLink sans label', () => {
    rejects(recos, {
      ...RECO_MIN,
      customLinks: [{ url: 'https://example.org' }],
    });
  });

  it('accepte des watchProviders avec ethics optionnelle', () => {
    accepts(recos, {
      ...RECO_MIN,
      watchProviders: [
        { label: 'Netflix', url: 'https://netflix.com', ethics: 'neutral' },
        { label: 'Arte', url: 'https://arte.tv' },
      ],
    });
  });

  it('refuse un watchProvider avec une ethics inconnue', () => {
    rejects(recos, {
      ...RECO_MIN,
      watchProviders: [
        { label: 'X', url: 'https://x.org', ethics: 'excellent' },
      ],
    });
  });

  // --- workflow ------------------------------------------------------------
  it.each(['draft', 'validated', 'discarded'])(
    'accepte le status « %s »',
    (status) => {
      accepts(recos, { ...RECO_MIN, status });
    },
  );

  it('refuse un status inconnu', () => {
    rejects(recos, { ...RECO_MIN, status: 'published' });
  });

  it.each(['reco', 'citation'])('accepte le kind « %s »', (kind) => {
    accepts(recos, { ...RECO_MIN, kind });
  });

  it('refuse un kind inconnu', () => {
    rejects(recos, { ...RECO_MIN, kind: 'mention' });
  });

  it('guestWork est booléen, non nullable côté reco (asymétrie L3 assumée)', () => {
    accepts(recos, { ...RECO_MIN, guestWork: true });
    accepts(recos, { ...RECO_MIN, guestWork: false });
    // Le writer de recos ne doit JAMAIS émettre `guestWork: null`.
    rejects(recos, { ...RECO_MIN, guestWork: null });
  });

  // --- traçabilité ---------------------------------------------------------
  it('accepte extractors, aliases et enrichedAt', () => {
    const d = accepts(recos, {
      ...RECO_MIN,
      extractors: ['anthropic', 'openai'],
      aliases: ['Inter Stellar'],
      enrichedAt: { 'externalIds.tmdb': '2026-04-15T10:00:00Z' },
    });
    expect(d.extractors).toEqual(['anthropic', 'openai']);
  });

  it('refuse un enrichedAt à valeur non-chaîne', () => {
    rejects(recos, { ...RECO_MIN, enrichedAt: { tmdb: 1234 } });
  });

  it.each(['acast', 'youtube'])(
    'accepte transcriptSource « %s »',
    (transcriptSource) => {
      accepts(recos, { ...RECO_MIN, transcriptSource });
    },
  );

  it('refuse un transcriptSource inconnu', () => {
    rejects(recos, { ...RECO_MIN, transcriptSource: 'spotify' });
  });

  it('accepte une entrée complète d’extractionHistory', () => {
    const d = accepts(recos, {
      ...RECO_MIN,
      extractionHistory: [
        {
          at: '2026-04-15T10:00:00Z',
          transcriptModel: 'large-v3',
          transcriptSource: 'youtube',
          llmProvider: 'anthropic',
          llmModel: 'claude-opus-5',
          worker: 'mac-mini',
          timestamp_at_extraction: '01:12:30',
        },
      ],
    });
    expect(d.extractionHistory).toHaveLength(1);
  });

  it('refuse un llmProvider hors anthropic|openai côté reco', () => {
    rejects(recos, {
      ...RECO_MIN,
      extractionHistory: [
        {
          at: '2026-04-15T10:00:00Z',
          transcriptModel: 'large-v3',
          transcriptSource: 'youtube',
          llmProvider: 'mistral',
          llmModel: 'x',
          worker: 'w',
          timestamp_at_extraction: '00:00:00',
        },
      ],
    });
  });

  it('refuse une entrée d’extractionHistory incomplète', () => {
    rejects(recos, {
      ...RECO_MIN,
      extractionHistory: [{ at: '2026-04-15T10:00:00Z' }],
    });
  });
});

// ---------------------------------------------------------------------------
// ITEMS
// ---------------------------------------------------------------------------
const ITEM_MIN = { id: 'interstellar', types: ['film'], title: 'Interstellar' };

describe('schéma items', () => {
  it('accepte un item minimal et pose schemaVersion=1', () => {
    const d = accepts(items, ITEM_MIN);
    expect(d.schemaVersion).toBe(1);
  });

  it.each([
    ['interstellar', true],
    ['a', true],
    ['abc-123', true],
    ['a'.repeat(64), true],
    ['a'.repeat(65), false],
    ['', false],
    ['Interstellar', false], // majuscules
    ['inter stellar', false], // espace
    ['inter_stellar', false], // underscore
  ])('id « %s » → accepté: %s', (id, ok) => {
    expect(items.safeParse({ ...ITEM_MIN, id }).success).toBe(ok);
  });

  it('refuse un titre vide (min 1)', () => {
    rejects(items, { ...ITEM_MIN, title: '' });
  });

  it('refuse un tableau de types vide', () => {
    rejects(items, { ...ITEM_MIN, types: [] });
  });

  it('accepte le type « article », absent de l’enum reco', () => {
    accepts(items, { ...ITEM_MIN, types: ['article'] });
    // Contre-preuve : ce type n'existe pas côté reco.
    rejects(recos, { ...RECO_MIN, types: ['article'] });
  });

  it.each([
    [1800, true],
    [2100, true],
    [1799, false],
    [2101, false],
    [2014.5, false],
  ])('year %s → accepté: %s', (year, ok) => {
    expect(items.safeParse({ ...ITEM_MIN, year }).success).toBe(ok);
  });

  it('accepte year et creator nuls (colonnes optionnelles du repo)', () => {
    const d = accepts(items, { ...ITEM_MIN, year: null, creator: null });
    expect(d.year).toBeNull();
  });

  it('exige un schemaVersion ≥ 1', () => {
    accepts(items, { ...ITEM_MIN, schemaVersion: 2 });
    rejects(items, { ...ITEM_MIN, schemaVersion: 0 });
  });

  it('accepte des externalIds nullables (tmdb numérique côté item)', () => {
    const d = accepts(items, {
      ...ITEM_MIN,
      externalIds: {
        tmdb: 157336,
        tmdbType: 'movie',
        spotify: null,
        musicbrainz: null,
        openlibrary: null,
        isbn: null,
        justwatch: null,
        instagram: null,
        tiktok: null,
      },
    });
    expect(d.externalIds.tmdb).toBe(157336);
  });

  it('refuse un tmdb en chaîne côté item (asymétrie assumée avec reco)', () => {
    rejects(items, { ...ITEM_MIN, externalIds: { tmdb: '157336' } });
    // Contre-preuve côté reco : la chaîne y est la forme attendue.
    accepts(recos, { ...RECO_MIN, externalIds: { tmdb: '157336' } });
  });

  it('watchProviders utilise « name » (et non « label ») côté item', () => {
    accepts(items, {
      ...ITEM_MIN,
      watchProviders: [
        { name: 'Netflix', url: 'https://netflix.com', region: 'FR' },
        { name: 'Arte', url: 'https://arte.tv', region: null, ethics: null },
      ],
    });
    rejects(items, {
      ...ITEM_MIN,
      watchProviders: [{ label: 'Netflix', url: 'https://netflix.com' }],
    });
  });

  it('linkOverrides n’est PAS validé en URL côté item (asymétrie avec reco)', () => {
    accepts(items, { ...ITEM_MIN, linkOverrides: { X: 'pas-une-url' } });
    rejects(recos, { ...RECO_MIN, linkOverrides: { X: 'pas-une-url' } });
  });

  it('accepte les flags d’audit (enrichmentSuspect, enrichedAt)', () => {
    const d = accepts(items, {
      ...ITEM_MIN,
      enrichmentSuspect: true,
      enrichedAt: { year: '2026-04-15T10:00:00Z' },
      aliases: ['Inter Stellar'],
      customLinks: [{ label: 'Site', url: 'https://example.org' }],
      recommendedBy: null,
    });
    expect(d.enrichmentSuspect).toBe(true);
  });

  it('refuse un customLink item sans URL valide', () => {
    rejects(items, {
      ...ITEM_MIN,
      customLinks: [{ label: 'Site', url: 'example.org' }],
    });
  });
});

// ---------------------------------------------------------------------------
// MENTIONS
// ---------------------------------------------------------------------------
const MENTION_MIN = {
  id: 'ubm-ep1-interstellar',
  itemId: 'interstellar',
  sourceRef: { sourceId: 'ubm' },
};

describe('schéma mentions', () => {
  it('accepte une mention minimale et applique les défauts', () => {
    const d = accepts(mentions, MENTION_MIN);
    expect(d.kind).toBe('reco');
    expect(d.status).toBe('draft');
    expect(d.schemaVersion).toBe(1);
  });

  it('refuse un id hors du motif slug', () => {
    rejects(mentions, { ...MENTION_MIN, id: 'Mention Un' });
    rejects(mentions, { ...MENTION_MIN, itemId: 'Inter Stellar' });
  });

  it('refuse une mention sans sourceRef', () => {
    const { sourceRef, ...sansRef } = MENTION_MIN;
    rejects(mentions, sansRef);
  });

  it('refuse un sourceRef sans sourceId', () => {
    rejects(mentions, { ...MENTION_MIN, sourceRef: {} });
  });

  it.each([
    ['01:12:30', true],
    ['00:00:00', true],
    ['1:12:30', false], // heures sur 1 chiffre
    ['01:12', false], // secondes manquantes
    ['011230', false],
    ['01:12:30.5', false],
  ])('timestamp « %s » → accepté: %s', (timestamp, ok) => {
    const res = mentions.safeParse({
      ...MENTION_MIN,
      sourceRef: { sourceId: 'ubm', timestamp },
    });
    expect(res.success).toBe(ok);
  });

  it('accepte des champs de sourceRef explicitement nuls', () => {
    const d = accepts(mentions, {
      ...MENTION_MIN,
      sourceRef: {
        sourceId: 'ubm',
        episodeGuid: null,
        timestamp: null,
        transcriptSource: null,
      },
    });
    expect(d.sourceRef.episodeGuid).toBeNull();
  });

  it('restreint transcriptSource à youtube|acast', () => {
    accepts(mentions, {
      ...MENTION_MIN,
      sourceRef: { sourceId: 'ubm', transcriptSource: 'acast' },
    });
    rejects(mentions, {
      ...MENTION_MIN,
      sourceRef: { sourceId: 'ubm', transcriptSource: 'deezer' },
    });
  });

  it('guestWork accepte null côté mention (asymétrie L3 avec reco)', () => {
    const d = accepts(mentions, { ...MENTION_MIN, guestWork: null });
    expect(d.guestWork).toBeNull();
    accepts(mentions, { ...MENTION_MIN, guestWork: true });
    // Contre-preuve : côté reco, `null` est refusé.
    rejects(recos, { ...RECO_MIN, guestWork: null });
  });

  it('accepte recommendedBy et quote nuls (transcripts non diarizés)', () => {
    const d = accepts(mentions, {
      ...MENTION_MIN,
      recommendedBy: null,
      quote: null,
    });
    expect(d.recommendedBy).toBeNull();
  });

  it('accepte un llmProvider libre côté mention (asymétrie avec reco)', () => {
    accepts(mentions, {
      ...MENTION_MIN,
      extractionHistory: [
        {
          transcriptModel: 'large-v3',
          transcriptSource: 'youtube',
          llmProvider: 'mistral',
          llmModel: 'x',
          worker: 'w',
          at: '2026-04-15T10:00:00Z',
        },
      ],
    });
  });

  it('accepte des champs nuls dans extractionHistory', () => {
    accepts(mentions, {
      ...MENTION_MIN,
      extractionHistory: [
        {
          transcriptModel: null,
          transcriptSource: null,
          llmProvider: 'anthropic',
          llmModel: 'claude',
          worker: null,
          at: '2026-04-15T10:00:00Z',
        },
      ],
    });
  });

  it('extra accepte chaîne, nombre et booléen — mais pas un objet', () => {
    const base = {
      transcriptModel: null,
      transcriptSource: null,
      llmProvider: 'anthropic',
      llmModel: 'claude',
      worker: null,
      at: '2026-04-15T10:00:00Z',
    };
    accepts(mentions, {
      ...MENTION_MIN,
      extractionHistory: [
        { ...base, extra: { s: 'x', n: 1, b: true } },
      ],
    });
    rejects(mentions, {
      ...MENTION_MIN,
      extractionHistory: [{ ...base, extra: { o: { imbrique: true } } }],
    });
  });

  it('refuse une entrée d’extractionHistory sans « at »', () => {
    rejects(mentions, {
      ...MENTION_MIN,
      extractionHistory: [
        {
          transcriptModel: null,
          transcriptSource: null,
          llmProvider: 'anthropic',
          llmModel: 'claude',
          worker: null,
        },
      ],
    });
  });

  it.each(['draft', 'validated', 'discarded'])(
    'accepte le status « %s »',
    (status) => {
      accepts(mentions, { ...MENTION_MIN, status });
    },
  );

  it('refuse un status de mention inconnu', () => {
    rejects(mentions, { ...MENTION_MIN, status: 'archived' });
  });
});
