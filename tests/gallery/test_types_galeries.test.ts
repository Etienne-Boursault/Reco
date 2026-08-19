/**
 * Tests de `src/lib/gallery/typesGaleries.ts`.
 *
 * CE QUE LA RELECTURE A VU
 * ------------------------
 * Capture du sommaire `/galeries` : les quatorze types du corpus y sont
 * listés, mais neuf d'entre eux pointaient tous vers `/recos`. Demande du
 * 2026-08-19 : « tous les types renvoient à chaque fois vers la page /recos
 * alors que je souhaitais avoir un accès par types comme /series mais pour
 * chacun des types et donc qu'ils aient tous une galerie ».
 *
 * Cette table est la source unique de la route dynamique. Les tests
 * ci-dessous protègent les deux propriétés dont dépend le build : aucun type
 * oublié, aucun slug en double avec une page dédiée.
 */
import { describe, expect, it } from 'vitest';

import {
  GALERIES_PAR_TYPE,
  PAGES_DEDIEES,
  galerieDuSlug,
} from '../../src/lib/gallery/typesGaleries';

/** Les types que le schéma admet — `src/content.config.ts`, enum `itemType`. */
const TYPES_DU_SCHEMA = [
  'film', 'serie', 'livre', 'bd', 'musique', 'album', 'artiste', 'podcast',
  'video', 'chaine', 'jeu', 'spectacle', 'lieu', 'application', 'autre',
];

const TOUTES = [...GALERIES_PAR_TYPE, ...PAGES_DEDIEES];

describe('couverture des types', () => {
  it('donne une galerie à chaque type du schéma', () => {
    // C'est LE test de la demande : un type sans galerie reste invisible.
    const couverts = new Set(TOUTES.flatMap((g) => g.types));
    const oublies = TYPES_DU_SCHEMA.filter((t) => !couverts.has(t));
    expect(oublies).toEqual([]);
  });

  it('n’invente aucun type absent du schéma', () => {
    // Une faute de frappe produirait une galerie vide et muette.
    for (const g of TOUTES) {
      for (const t of g.types) expect(TYPES_DU_SCHEMA).toContain(t);
    }
  });

  it('sert « autre », le type de repli', () => {
    expect(galerieDuSlug('autres')?.types).toEqual(['autre']);
  });
});

describe('les slugs', () => {
  it('ne recoupent jamais ceux des pages dédiées', () => {
    // Deux routes pour la même adresse : Astro construirait deux fois la page.
    const dedies = new Set(PAGES_DEDIEES.map((g) => g.slug));
    for (const g of GALERIES_PAR_TYPE) expect(dedies.has(g.slug)).toBe(false);
  });

  it('sont uniques', () => {
    const slugs = TOUTES.map((g) => g.slug);
    expect(new Set(slugs).size).toBe(slugs.length);
  });

  it('tiennent dans une URL — ni accent, ni majuscule, ni espace', () => {
    for (const g of TOUTES) expect(g.slug).toMatch(/^[a-z0-9-]+$/);
  });
});

describe('les libellés', () => {
  it('sont tous renseignés', () => {
    for (const g of TOUTES) {
      expect(g.court.length).toBeGreaterThan(1);
      expect(g.titre.length).toBeGreaterThan(2);
      expect(g.unGe.length).toBeGreaterThan(2);
      expect(g.plusieurs.length).toBeGreaterThan(2);
      expect(g.vide.length).toBeGreaterThan(2);
    }
  });

  it('distinguent le singulier du pluriel', () => {
    // Un copier-coller laisserait « 12 spectacle recommandé ».
    for (const g of TOUTES) expect(g.unGe).not.toBe(g.plusieurs);
  });

  it('emploient l’apostrophe typographique, comme le reste du site', () => {
    for (const g of TOUTES) expect(g.vide).not.toContain("'");
  });

  it('donnent un nom court sans article', () => {
    // « Tous les films » dans une colonne de quatorze entrées répétait un
    // article que la mise en page rendait inutile (relecture du 2026-08-19).
    for (const g of TOUTES) {
      expect(g.court).not.toMatch(/^(Tous|Toutes|Tout|Le|La|Les)/);
      expect(g.court.length).toBeLessThan(g.titre.length);
    }
  });

  it('ne donnent jamais deux fois le même nom court', () => {
    const courts = TOUTES.map((g) => g.court);
    expect(new Set(courts).size).toBe(courts.length);
  });
});

describe('galerieDuSlug', () => {
  it('retrouve une galerie dynamique', () => {
    expect(galerieDuSlug('spectacles')?.types).toEqual(['spectacle']);
    expect(galerieDuSlug('jeux')?.titre).toBe('Tous les jeux');
  });

  it('ignore les pages dédiées — elles ont leur propre fichier', () => {
    expect(galerieDuSlug('films')).toBeUndefined();
    expect(galerieDuSlug('musique')).toBeUndefined();
  });

  it('renvoie undefined pour un slug inconnu', () => {
    expect(galerieDuSlug('nimporte-quoi')).toBeUndefined();
    expect(galerieDuSlug('')).toBeUndefined();
  });
});
