/**
 * Tests des libellés de types de recos (`src/utils/recoTypes.ts`).
 *
 * Ce module est le point unique de vérité pour l'affichage des types (cartes,
 * filtres, pages d'épisode). On vérifie :
 *   - la cohérence des trois tables (mêmes clés, valeurs non vides),
 *   - l'alignement avec l'enum `recoType` de `src/content.config.ts`,
 *   - le comportement des lookups sur un type inconnu (`undefined`, pas de
 *     crash — les composants font `?? type`),
 *   - `episodeLabel()` sur toutes ses branches, y compris les cas non
 *     nominaux (champs absents, valeurs nulles, zéro).
 */
import { describe, it, expect } from 'vitest';
import {
  TYPE_LABELS,
  TYPE_EMOJIS,
  TYPE_LABELS_PLURAL,
  episodeLabel,
} from '../../src/utils/recoTypes';

// ---------------------------------------------------------------------------
// Cohérence des tables
// ---------------------------------------------------------------------------
describe('tables de types', () => {
  it('les trois tables couvrent exactement les mêmes clés', () => {
    const labels = Object.keys(TYPE_LABELS).sort();
    expect(Object.keys(TYPE_EMOJIS).sort()).toEqual(labels);
    expect(Object.keys(TYPE_LABELS_PLURAL).sort()).toEqual(labels);
  });

  it('aucune valeur vide', () => {
    for (const table of [TYPE_LABELS, TYPE_EMOJIS, TYPE_LABELS_PLURAL]) {
      for (const [key, value] of Object.entries(table)) {
        expect(value, `clé ${key}`).toBeTruthy();
        expect(value.trim(), `clé ${key}`).not.toBe('');
      }
    }
  });

  it('expose les libellés attendus pour quelques types clés', () => {
    expect(TYPE_LABELS.film).toBe('Film');
    expect(TYPE_LABELS.serie).toBe('Série');
    expect(TYPE_LABELS.chaine).toBe('Chaîne YouTube');
    expect(TYPE_LABELS_PLURAL.jeu).toBe('Jeux');
    expect(TYPE_LABELS_PLURAL.chaine).toBe('Chaînes YouTube');
  });

  it('garde les invariables au singulier au pluriel (BD, musique)', () => {
    expect(TYPE_LABELS_PLURAL.bd).toBe(TYPE_LABELS.bd);
    expect(TYPE_LABELS_PLURAL.musique).toBe(TYPE_LABELS.musique);
  });

  it('un type inconnu renvoie undefined dans chaque table (pas de crash)', () => {
    expect(TYPE_LABELS.inconnu).toBeUndefined();
    expect(TYPE_EMOJIS.inconnu).toBeUndefined();
    expect(TYPE_LABELS_PLURAL.inconnu).toBeUndefined();
  });

  it('la chaîne vide n’est pas une clé valide', () => {
    expect(TYPE_LABELS['']).toBeUndefined();
  });

  it('n’hérite pas des clés d’Object.prototype pour un lookup arbitraire', () => {
    // Les tables sont des littéraux : `toString` existe via le prototype.
    // On vérifie qu'aucun type métier ne s'appuie dessus par accident.
    expect(Object.prototype.hasOwnProperty.call(TYPE_LABELS, 'toString')).toBe(
      false,
    );
  });

  it('les emojis sont non vides et distincts entre types', () => {
    const emojis = Object.values(TYPE_EMOJIS);
    expect(new Set(emojis).size).toBe(emojis.length);
  });
});

// ---------------------------------------------------------------------------
// Alignement avec le schéma de contenu
// ---------------------------------------------------------------------------
describe('alignement avec l’enum recoType du schéma', () => {
  it('couvre tous les types déclarés dans src/content.config.ts', async () => {
    const { collections } = await import('../../src/content.config');
    // `types` est un `z.array(recoType).min(1)` : on descend au type élément.
    const recosSchema = (
      collections.recos as unknown as { schema: { shape: Record<string, any> } }
    ).schema;
    const enumValues: string[] = recosSchema.shape.types.element.options;

    expect(enumValues.length).toBeGreaterThan(0);
    for (const type of enumValues) {
      expect(TYPE_LABELS[type], `libellé manquant pour ${type}`).toBeTruthy();
      expect(TYPE_EMOJIS[type], `emoji manquant pour ${type}`).toBeTruthy();
      expect(
        TYPE_LABELS_PLURAL[type],
        `pluriel manquant pour ${type}`,
      ).toBeTruthy();
    }
    // Et aucun libellé orphelin côté UI.
    expect(Object.keys(TYPE_LABELS).sort()).toEqual([...enumValues].sort());
  });
});

// ---------------------------------------------------------------------------
// episodeLabel
// ---------------------------------------------------------------------------
describe('episodeLabel', () => {
  it('saison + numéro → « S2·E3 »', () => {
    expect(episodeLabel({ season: 2, number: 3 })).toBe('S2·E3');
  });

  it('numéro seul → « #42 »', () => {
    expect(episodeLabel({ number: 42 })).toBe('#42');
  });

  it('saison seule (sans numéro) → chaîne vide', () => {
    expect(episodeLabel({ season: 4 })).toBe('');
  });

  it('objet vide → chaîne vide', () => {
    expect(episodeLabel({})).toBe('');
  });

  it('champs explicitement undefined → chaîne vide', () => {
    expect(episodeLabel({ season: undefined, number: undefined })).toBe('');
  });

  it('numéro 0 est traité comme absent (garde falsy assumée)', () => {
    // `if (e.number)` : 0 est falsy. Aucun podcast ne numérote à 0, la
    // convention du projet démarre à 1.
    expect(episodeLabel({ number: 0 })).toBe('');
    expect(episodeLabel({ season: 1, number: 0 })).toBe('');
  });

  it('saison 0 retombe sur la forme courte « #N »', () => {
    expect(episodeLabel({ season: 0, number: 7 })).toBe('#7');
  });

  it('accepte des valeurs nulles (données JSON dégradées)', () => {
    const degraded = { season: null, number: null } as unknown as {
      season?: number;
      number?: number;
    };
    expect(episodeLabel(degraded)).toBe('');
  });

  it('gère des numéros à plusieurs chiffres', () => {
    expect(episodeLabel({ season: 12, number: 345 })).toBe('S12·E345');
  });

  it('utilise le point médian U+00B7 comme séparateur', () => {
    expect(episodeLabel({ season: 1, number: 1 })).toBe('S1·E1');
  });
});
