/**
 * Règle C (`05`, 3 novembre) : un code qui vérifie des données ne fait
 * confiance à aucune forme, et une règle reprise d'un autre fichier est tenue
 * par un test de concordance.
 */
import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { analyser, COLLECTIONS, FORMATS } from '../../src/lib/catalog/invariants.ts';
import { DOSSIERS_EXCLUS } from '../../src/lib/catalog/lireCorpus.ts';
import type { Corpus, Json } from '../../src/lib/catalog/invariants.ts';

const SCHEMA = readFileSync(new URL('../../src/content.config.ts', import.meta.url), 'utf8');

/** Deux recos validées d'une même œuvre, pour passer aussi par le classement des liens. */
function corpus(): Corpus {
  const reco = (id: string): Json => ({
    id, status: 'validated', episodeGuid: 'e1', title: 'T', creator: 'C', types: ['film'], year: 2001,
    recommendedBy: 'R', quote: 'Q', timestamp: '00:01:00', kind: 'reco', guestWork: true, aliases: ['A'],
    externalIds: { tmdb: '1', watchPage: 'https://www.themoviedb.org/movie/1/watch', youtubeChannelId: 'UC1' },
    links: [{ label: 'YouTube', url: 'https://www.youtube.com/@a' }],
  });
  const mention = (id: string): Json => ({
    id, status: 'validated', itemId: 'i1', sourceRef: { episodeGuid: 'e1', timestamp: '00:01:00' },
    recommendedBy: 'R', quote: 'Q', kind: 'reco', guestWork: true,
  });
  return {
    sources: [{ chemin: 'sources/s.json', donnees: { id: 's' } }],
    episodes: [{ chemin: 'episodes/s/e1.json', donnees: { guid: 'e1' } }],
    items: [{
      chemin: 'items/s/i1.json',
      donnees: { id: 'i1', title: 'T', creator: 'C', types: ['film'], aliases: ['A'], externalIds: { tmdb: 1 } },
    }],
    recos: [{ chemin: 'recos/s/1.json', donnees: reco('ubm-1') }, { chemin: 'recos/s/2.json', donnees: reco('ubm-2') }],
    mentions: [
      { chemin: 'mentions/s/ubm-1.json', donnees: mention('ubm-1') },
      { chemin: 'mentions/s/ubm-2.json', donnees: mention('ubm-2') },
    ],
    redirections: { '/s/oeuvre/vieux': '/s/oeuvre/i1' },
  };
}

const HOSTILES: unknown[] = [3, 'texte', '', [], [1, null, 'x'], {}, { a: { b: 1 } }, null, true];

const CHAMPS: Record<'sources' | 'episodes' | 'recos' | 'items' | 'mentions', string[]> = {
  sources: ['id'],
  episodes: ['guid'],
  recos: ['id', 'status', 'episodeGuid', 'title', 'creator', 'types', 'year', 'recommendedBy', 'quote',
    'timestamp', 'kind', 'guestWork', 'aliases', 'externalIds', 'links'],
  items: ['id', 'title', 'creator', 'types', 'year', 'aliases', 'externalIds', 'recommendedBy'],
  mentions: ['id', 'status', 'itemId', 'sourceRef', 'recommendedBy', 'quote', 'kind', 'guestWork'],
};

/** Les valeurs de HOSTILES qui ont la bonne forme pour ce champ ; toutes les autres doivent être rapportées. */
const VALIDES: Record<string, unknown[]> = {
  title: ['texte'], creator: ['texte'], recommendedBy: ['texte'], quote: ['texte'], timestamp: ['texte'],
  episodeGuid: ['texte'], itemId: ['texte'], year: [3], guestWork: [true],
  types: [[]], aliases: [[]], links: [[]], externalIds: [{}], sourceRef: [{}, { a: { b: 1 } }],
};
/** Les identifiants ont leurs propres règles (sans-id, format, doublon), testées ailleurs. */
const IDENTIFIANTS = new Set(['id', 'guid']);

describe('règle C : des valeurs du mauvais type sont rapportées, jamais fatales', () => {
  for (const [collection, champs] of Object.entries(CHAMPS) as [keyof typeof CHAMPS, string[]][]) {
    for (const champ of champs) {
      it(`${collection}.${champ}`, () => {
        for (const valeur of HOSTILES) {
          const c = corpus();
          const entree = c[collection][0];
          const id = String(entree.donnees?.id);
          entree.donnees = { ...entree.donnees, [champ]: valeur };
          const cas = `${collection}.${champ} = ${JSON.stringify(valeur)}`;
          let r: ReturnType<typeof analyser> | undefined;
          expect(() => (r = analyser(c)), cas).not.toThrow();
          // Sur une œuvre, recommendedBy bloque quelle que soit sa valeur (test dédié).
          if (IDENTIFIANTS.has(champ) || `${collection}.${champ}` === 'items.recommendedBy') continue;
          const rapportee = [...r!.bloquants, ...r!.avertissements].some(
            (v) => (v.regle === 'type-champ' || v.regle === 'valeur-vide') && v.ids.includes(`${collection}:${id}.${champ}`),
          );
          const valide = (VALIDES[champ] ?? []).some((x) => JSON.stringify(x) === JSON.stringify(valeur));
          expect(rapportee, cas).toBe(!valide);
        }
      });
    }
  }

  it('type-champ est bloquant, valeur-vide un avertissement', () => {
    const c = corpus();
    (c.recos[0].donnees as Json).guestWork = 'true';
    (c.recos[0].donnees as Json).creator = '';
    const r = analyser(c);
    expect(r.bloquants.find((v) => v.regle === 'type-champ')?.ids).toEqual(['recos:ubm-1.guestWork']);
    expect(r.avertissements.find((v) => v.regle === 'valeur-vide')?.ids).toEqual(['recos:ubm-1.creator']);
  });

  it('les statuts et les natures hors de leur liste sont rapportés', () => {
    const c = corpus();
    (c.recos[0].donnees as Json).status = 'valide';
    (c.mentions[0].donnees as Json).kind = 'Reco';
    expect(analyser(c).bloquants.find((v) => v.regle === 'type-champ')?.ids).toEqual(['mentions:ubm-1.kind', 'recos:ubm-1.status']);
  });

  it('externalIds, liens et sourceRef : valeurs internes du mauvais type', () => {
    for (const valeur of HOSTILES) {
      const c = corpus();
      const reco = c.recos[0].donnees as Json;
      reco.externalIds = { tmdb: valeur, watchPage: valeur, youtubeChannelId: valeur };
      reco.links = [valeur, { url: valeur, label: valeur }];
      (c.mentions[0].donnees as Json).sourceRef = { episodeGuid: valeur, timestamp: valeur };
      let r: ReturnType<typeof analyser> | undefined;
      expect(() => (r = analyser(c)), JSON.stringify(valeur)).not.toThrow();
      const malFormes = r!.bloquants.find((v) => v.regle === 'type-champ')?.ids ?? [];
      const texteOuNombre = typeof valeur === 'string' || typeof valeur === 'number';
      // Un lien qui n'est pas un objet à `url` texte est toujours mal formé.
      expect(malFormes.includes('recos:ubm-1.links'), JSON.stringify(valeur)).toBe(true);
      expect(malFormes.includes('recos:ubm-1.externalIds'), JSON.stringify(valeur)).toBe(!texteOuNombre);
      expect(malFormes.includes('mentions:ubm-1.sourceRef'), JSON.stringify(valeur)).toBe(typeof valeur !== 'string');
    }
  });

  it('redirections : adresses et cibles du mauvais type', () => {
    for (const valeur of HOSTILES) {
      const c = corpus();
      c.redirections = { '/s/oeuvre/x': valeur, [String(valeur)]: '/s/oeuvre/i1' };
      const r = analyser(c);
      expect(r.bloquants.some((v) => v.regle === 'redirection-format')).toBe(true);
    }
  });
});

describe('règle C : concordance avec src/content.config.ts', () => {
  /** Collection → dossiers exclus par les motifs en `!` de son chargeur. */
  function exclusionsDuSchema(): Record<string, string[]> {
    const trouve: Record<string, string[]> = {};
    const chargeur = /pattern:\s*(\[[^\]]*\]|'[^']*')\s*,\s*base:\s*'\.\/src\/content\/(\w+)'/g;
    for (const [, motifs, collection] of SCHEMA.matchAll(chargeur)) {
      trouve[collection] = [...motifs.matchAll(/'!\*\*\/([^/']+)\/\*\*'/g)].map((m) => m[1]).sort();
    }
    return trouve;
  }

  it('les dossiers exclus sont ceux des chargeurs, collection par collection', () => {
    const schema = exclusionsDuSchema();
    expect(Object.keys(schema).sort()).toEqual([...COLLECTIONS].sort());
    for (const collection of COLLECTIONS) {
      expect([...(DOSSIERS_EXCLUS[collection] ?? [])].sort(), collection).toEqual(schema[collection]);
    }
  });

  it('les formats fermés de la source, de l’œuvre et de la mention sont ceux du schéma', () => {
    const regex = (champ: string): string[] =>
      [...SCHEMA.matchAll(new RegExp(`\\b${champ}: z\\.string\\(\\)\\.regex\\(/(.+?)/\\)`, 'g'))].map((m) => m[1]);
    // Le premier `id` est celui des sources, les deux suivants ceux des œuvres et des mentions.
    expect(regex('id')).toEqual([FORMATS.source.source, FORMATS.oeuvre.source, FORMATS.citation.source]);
    expect(regex('itemId')).toEqual([FORMATS.oeuvre.source]);
  });
});
