/**
 * Tests du chargeur de signalements « situation de l'artiste »
 * (`src/data/creatorFlags.ts`).
 *
 * Deux volets :
 *   1. Sur les données RÉELLES (`creator-flags.json`, curées à la main) :
 *      normalisation des noms, résolution, entrées nulles/vides.
 *   2. Sur des données INJECTÉES (mock du JSON) pour exercer les gardes de
 *      robustesse : fichier sans clé `flags`, entrées malformées (nom absent,
 *      situation ou source manquante, entrée `null`), doublons de nom et nom
 *      qui se normalise en chaîne vide.
 *
 * Le module construit son index au chargement : chaque scénario injecté passe
 * donc par `vi.resetModules()` + import dynamique.
 */
import { describe, it, expect, vi, afterEach } from 'vitest';
import {
  creatorFlag,
  normalizeName,
  flagCount,
  type CreatorFlag,
} from '../../src/data/creatorFlags';
import rawFlags from '../../src/data/creator-flags.json';

const REAL_FLAGS = (rawFlags as { flags?: CreatorFlag[] }).flags ?? [];

// ---------------------------------------------------------------------------
// normalizeName
// ---------------------------------------------------------------------------
describe('normalizeName', () => {
  it('passe en minuscules', () => {
    expect(normalizeName('WOODY ALLEN')).toBe('woody allen');
  });

  it('retire les diacritiques', () => {
    expect(normalizeName('Gérard Depardieu')).toBe('gerard depardieu');
    expect(normalizeName('Seb Méllia')).toBe('seb mellia');
  });

  it('remplace la ponctuation par des espaces', () => {
    expect(normalizeName('David O. Russell')).toBe('david o russell');
    expect(normalizeName("L'Artiste-Peintre")).toBe('l artiste peintre');
  });

  it('écrase les séparateurs consécutifs en un seul espace', () => {
    expect(normalizeName('Jean   ---   Luc')).toBe('jean luc');
  });

  it('rogne les espaces de bord', () => {
    expect(normalizeName('  Woody Allen  ')).toBe('woody allen');
    expect(normalizeName('!!!Woody!!!')).toBe('woody');
  });

  it('renvoie une chaîne vide pour une entrée vide ou uniquement ponctuée', () => {
    expect(normalizeName('')).toBe('');
    expect(normalizeName('   ')).toBe('');
    expect(normalizeName('!!! ??? ...')).toBe('');
  });

  it('conserve les chiffres', () => {
    expect(normalizeName('Studio 4')).toBe('studio 4');
  });

  it('est idempotente', () => {
    const once = normalizeName('Gérard Depardieu');
    expect(normalizeName(once)).toBe(once);
  });
});

// ---------------------------------------------------------------------------
// creatorFlag — données réelles
// ---------------------------------------------------------------------------
describe('creatorFlag — données curées réelles', () => {
  it('flagCount reflète le nombre d’entrées valides du JSON', () => {
    expect(flagCount).toBe(REAL_FLAGS.length);
  });

  it('renvoie null pour null', () => {
    expect(creatorFlag(null)).toBeNull();
  });

  it('renvoie null pour undefined', () => {
    expect(creatorFlag(undefined)).toBeNull();
  });

  it('renvoie null pour la chaîne vide', () => {
    expect(creatorFlag('')).toBeNull();
  });

  it('renvoie null pour un créateur non signalé', () => {
    expect(creatorFlag('Agnès Varda')).toBeNull();
  });

  it('renvoie null pour un nom qui se normalise en chaîne vide', () => {
    expect(creatorFlag('!!!')).toBeNull();
  });

  it.runIf(REAL_FLAGS.length > 0)(
    'retrouve chaque nom déclaré, sous toutes ses orthographes',
    () => {
      for (const flag of REAL_FLAGS) {
        for (const name of flag.names) {
          const found = creatorFlag(name);
          expect(found, `nom « ${name} » introuvable`).not.toBeNull();
          expect(found?.situation).toBe(flag.situation);
        }
      }
    },
  );

  it.runIf(REAL_FLAGS.length > 0)(
    'la recherche ignore la casse, les accents et la ponctuation',
    () => {
      const [name] = REAL_FLAGS[0].names;
      const expected = creatorFlag(name);
      expect(expected).not.toBeNull();
      expect(creatorFlag(name.toUpperCase())).toBe(expected);
      expect(creatorFlag(`  ${name}.  `)).toBe(expected);
    },
  );

  it.runIf(REAL_FLAGS.length > 0)(
    'chaque signalement chargé porte une situation et une source (invariant de curation)',
    () => {
      for (const flag of REAL_FLAGS) {
        expect(flag.situation.length).toBeGreaterThan(0);
        expect(flag.source).toMatch(/^https?:\/\//);
        if (flag.severity !== undefined) {
          expect(['accusation', 'condamnation']).toContain(flag.severity);
        }
      }
    },
  );
});

// ---------------------------------------------------------------------------
// Gardes de robustesse — JSON injecté
// ---------------------------------------------------------------------------
/** Recharge le module avec un contenu JSON arbitraire. */
async function loadWith(json: unknown) {
  vi.resetModules();
  vi.doMock('../../src/data/creator-flags.json', () => ({ default: json }));
  return import('../../src/data/creatorFlags');
}

describe('creatorFlags — chargement dégradé', () => {
  afterEach(() => {
    vi.doUnmock('../../src/data/creator-flags.json');
    vi.resetModules();
  });

  it('fichier sans clé « flags » → aucun signalement', async () => {
    const mod = await loadWith({});
    expect(mod.flagCount).toBe(0);
    expect(mod.creatorFlag('Woody Allen')).toBeNull();
  });

  it('liste vide → aucun signalement', async () => {
    const mod = await loadWith({ flags: [] });
    expect(mod.flagCount).toBe(0);
  });

  it('écarte une entrée nulle', async () => {
    const mod = await loadWith({
      flags: [null, { names: ['A'], situation: 's', source: 'u' }],
    });
    expect(mod.flagCount).toBe(1);
    expect(mod.creatorFlag('A')).not.toBeNull();
  });

  it('écarte une entrée dont « names » n’est pas un tableau', async () => {
    const mod = await loadWith({
      flags: [{ names: 'A', situation: 's', source: 'u' }],
    });
    expect(mod.flagCount).toBe(0);
  });

  it('écarte une entrée sans « names »', async () => {
    const mod = await loadWith({ flags: [{ situation: 's', source: 'u' }] });
    expect(mod.flagCount).toBe(0);
  });

  it('écarte une entrée sans « situation »', async () => {
    const mod = await loadWith({ flags: [{ names: ['A'], source: 'u' }] });
    expect(mod.flagCount).toBe(0);
  });

  it('écarte une entrée sans « source » (source obligatoire côté curation)', async () => {
    const mod = await loadWith({ flags: [{ names: ['A'], situation: 's' }] });
    expect(mod.flagCount).toBe(0);
  });

  it('ignore un nom qui se normalise en chaîne vide', async () => {
    const mod = await loadWith({
      flags: [{ names: ['!!!', 'Vrai Nom'], situation: 's', source: 'u' }],
    });
    expect(mod.flagCount).toBe(1);
    expect(mod.creatorFlag('!!!')).toBeNull();
    expect(mod.creatorFlag('Vrai Nom')).not.toBeNull();
  });

  it('en cas de doublon, la première déclaration gagne', async () => {
    const mod = await loadWith({
      flags: [
        { names: ['Doublon'], situation: 'première', source: 'u1' },
        { names: ['doublon'], situation: 'seconde', source: 'u2' },
      ],
    });
    expect(mod.flagCount).toBe(2);
    expect(mod.creatorFlag('Doublon')?.situation).toBe('première');
  });

  it('indexe toutes les orthographes d’une même entrée', async () => {
    const mod = await loadWith({
      flags: [
        {
          names: ['Victor Bonnefoy', 'InThePanda', 'In The Panda'],
          situation: 's',
          source: 'u',
        },
      ],
    });
    const ref = mod.creatorFlag('Victor Bonnefoy');
    expect(ref).not.toBeNull();
    expect(mod.creatorFlag('inthepanda')).toBe(ref);
    expect(mod.creatorFlag('In The Panda')).toBe(ref);
  });
});
