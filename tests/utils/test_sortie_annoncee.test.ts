/**
 * Tests de `src/utils/sortieAnnoncee.ts` — la mention « Sortie annoncée le … »
 * des cartes (R4 B, 27/11/2026, tranche F).
 *
 * Deux pièges visés : une date posée à la main (`2026-11-20`) qui sortirait le
 * 19 quand le site est construit à l'ouest de Greenwich (`new Date('2026-11-20')`
 * est minuit UTC), et un « maintenant » lu dans le fuseau du poste de
 * construction au lieu de celui de Paris.
 */
import { afterEach, describe, expect, it } from 'vitest';

import { sortieAnnoncee } from '../../src/utils/sortieAnnoncee';

const MIDI = new Date('2026-11-10T12:00:00Z');
const TZ_INITIAL = process.env.TZ;

afterEach(() => {
  if (TZ_INITIAL === undefined) delete process.env.TZ;
  else process.env.TZ = TZ_INITIAL;
});

describe('sortieAnnoncee — le libellé de la date', () => {
  it('écrit les chiffres de la date, sans les convertir : le 20, jamais le 19', () => {
    // Un fuseau très à l'ouest : l'implémentation naïve (`new Date(s)` puis
    // `toLocaleDateString`) rend « 19 novembre 2026 ».
    for (const tz of ['America/Los_Angeles', 'Pacific/Honolulu', 'Asia/Tokyo', 'UTC']) {
      process.env.TZ = tz;
      expect(sortieAnnoncee('2026-11-20', MIDI)).toBe('20 novembre 2026');
    }
  });

  it('nomme les douze mois', () => {
    const attendu = [
      'janvier', 'février', 'mars', 'avril', 'mai', 'juin',
      'juillet', 'août', 'septembre', 'octobre', 'novembre', 'décembre',
    ];
    attendu.forEach((mois, i) => {
      const m = String(i + 1).padStart(2, '0');
      expect(sortieAnnoncee(`2027-${m}-15`, MIDI)).toBe(`15 ${mois} 2027`);
    });
  });

  it('écrit « 1er » le premier du mois, et retire le zéro des autres jours', () => {
    expect(sortieAnnoncee('2026-12-01', MIDI)).toBe('1er décembre 2026');
    expect(sortieAnnoncee('2026-12-05', MIDI)).toBe('5 décembre 2026');
  });
});

describe('sortieAnnoncee — tant que la date n’est pas passée', () => {
  it('rend rien sans date', () => {
    expect(sortieAnnoncee(undefined, MIDI)).toBeNull();
  });

  it('rend rien pour un texte qui n’est pas une date AAAA-MM-JJ', () => {
    expect(sortieAnnoncee('bientôt', MIDI)).toBeNull();
    expect(sortieAnnoncee('20261120', MIDI)).toBeNull();
    expect(sortieAnnoncee('2026-13-01', MIDI)).toBeNull();
  });

  it('rend rien dès le lendemain de la date', () => {
    const lendemain = new Date('2026-11-20T23:30:00Z'); // 00 h 30 à Paris, le 21
    expect(sortieAnnoncee('2026-11-20', lendemain)).toBeNull();
  });

  it('affiche encore le jour même de la date', () => {
    expect(sortieAnnoncee('2026-11-20', new Date('2026-11-20T10:00:00Z'))).toBe('20 novembre 2026');
  });

  it('compte le jour à Paris, pas dans le fuseau du poste : minuit passé à Paris', () => {
    // 19 novembre 23 h 30 UTC = 20 novembre 00 h 30 à Paris. Même instant,
    // quel que soit le fuseau du poste.
    const instant = new Date('2026-11-19T23:30:00Z');
    for (const tz of ['America/Los_Angeles', 'UTC']) {
      process.env.TZ = tz;
      expect(sortieAnnoncee('2026-11-19', instant)).toBeNull(); // Paris : le 20, passée
      expect(sortieAnnoncee('2026-11-20', instant)).toBe('20 novembre 2026');
    }
  });

  it('une date très lointaine reste affichée, une date très ancienne non (ne vire pas avec le temps)', () => {
    expect(sortieAnnoncee('2099-01-01', new Date())).toBe('1er janvier 2099');
    expect(sortieAnnoncee('2001-01-01', new Date())).toBeNull();
  });
});

describe('sortieAnnoncee — la ceinture des types non servis (tour 1 de revue, PR #227)', () => {
  it('rend rien pour un type que la relance ne sert pas, même avec une date à venir', () => {
    expect(sortieAnnoncee('2099-01-01', MIDI, ['film'])).toBeNull();
    expect(sortieAnnoncee('2099-01-01', MIDI, [])).toBeNull();
  });

  it('rend la date dès qu’un des types est servi', () => {
    expect(sortieAnnoncee('2099-01-01', MIDI, ['film', 'livre'])).toBe('1er janvier 2099');
  });

  it('ne juge pas les types quand l’appelant n’en donne pas', () => {
    expect(sortieAnnoncee('2099-01-01', MIDI)).toBe('1er janvier 2099');
  });
});
