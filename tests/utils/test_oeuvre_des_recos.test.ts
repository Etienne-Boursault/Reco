/**
 * Tests de `src/utils/oeuvreDesRecos.ts` — le lien d'une carte de reco vers
 * la fiche de son œuvre (ajouté après l'audit d'interface du 2026-10-07).
 */
import { describe, expect, it } from 'vitest';

import { lienOeuvre, oeuvreParReco } from '../../src/utils/oeuvreDesRecos';

describe('oeuvreParReco', () => {
  it('associe une reco à l’œuvre de la mention de même identifiant', () => {
    const m = oeuvreParReco([{ id: 'ubm-1', itemId: 'f203a89a', status: 'validated' }]);
    expect(m.get('ubm-1')).toBe('f203a89a');
  });

  it('une mention en brouillon compte : le site l’affiche', () => {
    const m = oeuvreParReco([{ id: 'ubm-1', itemId: 'x', status: 'draft' }]);
    expect(m.get('ubm-1')).toBe('x');
  });

  it('ignore une mention écartée — sa fiche peut ne pas exister', () => {
    const m = oeuvreParReco([{ id: 'ubm-1', itemId: 'x', status: 'discarded' }]);
    expect(m.has('ubm-1')).toBe(false);
  });
});

describe('lienOeuvre', () => {
  const oeuvres = new Map([['ubm-1', 'f203a89a']]);

  it('construit l’adresse de la fiche dans la source', () => {
    expect(lienOeuvre(oeuvres, 'un-bon-moment', 'ubm-1')).toBe('/un-bon-moment/oeuvre/f203a89a');
  });

  it('pas de lien pour une reco sans mention visible', () => {
    expect(lienOeuvre(oeuvres, 'un-bon-moment', 'ubm-2')).toBeUndefined();
  });

  it('pas de lien sans table du tout', () => {
    expect(lienOeuvre(undefined, 'un-bon-moment', 'ubm-1')).toBeUndefined();
  });
});
