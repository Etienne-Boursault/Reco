/**
 * Tests du libellé du raccourci de recherche (src/utils/raccourciRecherche).
 *
 * Règle : « ⌘ K » sur un appareil Apple, « Ctrl K » partout ailleurs — y
 * compris quand la plateforme est inconnue, car c'est la valeur rendue par le
 * serveur avant toute détection (audit d'interface du 2026-10-07).
 */
import { describe, it, expect } from 'vitest';
import {
  estPlateformeApple,
  libelleRaccourci,
  RACCOURCI_PAR_DEFAUT,
} from '../../src/utils/raccourciRecherche';

describe('estPlateformeApple', () => {
  it('reconnaît macOS via userAgentData', () => {
    expect(estPlateformeApple({ userAgentData: { platform: 'macOS' } })).toBe(true);
  });

  it('reconnaît iOS via userAgentData', () => {
    expect(estPlateformeApple({ userAgentData: { platform: 'iOS' } })).toBe(true);
  });

  it('userAgentData prime sur platform', () => {
    expect(
      estPlateformeApple({ userAgentData: { platform: 'Windows' }, platform: 'MacIntel' }),
    ).toBe(false);
  });

  it('se replie sur platform (Safari, Firefox)', () => {
    expect(estPlateformeApple({ platform: 'MacIntel' })).toBe(true);
    expect(estPlateformeApple({ platform: 'iPhone' })).toBe(true);
    expect(estPlateformeApple({ platform: 'iPad' })).toBe(true);
  });

  it('Windows et Linux ne sont pas Apple', () => {
    expect(estPlateformeApple({ platform: 'Win32' })).toBe(false);
    expect(estPlateformeApple({ platform: 'Linux x86_64' })).toBe(false);
    expect(estPlateformeApple({ userAgentData: { platform: 'Android' } })).toBe(false);
  });

  it('plateforme inconnue ou navigateur absent → non Apple', () => {
    expect(estPlateformeApple({})).toBe(false);
    expect(estPlateformeApple(undefined)).toBe(false);
  });
});

describe('libelleRaccourci', () => {
  it('⌘ K sur Apple', () => {
    expect(libelleRaccourci({ platform: 'MacIntel' })).toBe('⌘ K');
  });

  it('Ctrl K ailleurs, identique au rendu serveur', () => {
    expect(libelleRaccourci({ platform: 'Win32' })).toBe('Ctrl K');
    expect(libelleRaccourci(undefined)).toBe(RACCOURCI_PAR_DEFAUT);
  });
});
