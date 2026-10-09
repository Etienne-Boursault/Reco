/**
 * Tests de `src/utils/iconesTypes.ts` — chaque type du schéma a son icône.
 */
import { describe, expect, it } from 'vitest';

import { GALERIES_PAR_TYPE, PAGES_DEDIEES } from '../../src/lib/gallery/typesGaleries';
import { ICONE_TYPE, iconeDuType } from '../../src/utils/iconesTypes';

describe('iconesTypes', () => {
  it('chaque type porté par une galerie a une icône dédiée', () => {
    for (const g of [...PAGES_DEDIEES, ...GALERIES_PAR_TYPE]) {
      for (const type of g.types) expect(ICONE_TYPE[type], type).toBeTruthy();
    }
  });

  it('un type inconnu retombe sur l’icône « autre »', () => {
    expect(iconeDuType('inconnu')).toBe(ICONE_TYPE.autre);
    expect(iconeDuType(undefined)).toBe(ICONE_TYPE.autre);
  });
});
