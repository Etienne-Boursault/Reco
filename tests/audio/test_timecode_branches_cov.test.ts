/**
 * tests/audio/test_timecode_branches_cov.test.ts — Branches restantes de
 * `src/lib/audio/timecode.ts` : entrées vides, singulier « 1 heure »,
 * youtu.be sans id, URL non parseable.
 */
import { describe, it, expect } from 'vitest';
import {
  parseTimecode,
  formatTimecodeA11y,
  extractYoutubeId,
} from '../../src/lib/audio/timecode.ts';

describe('parseTimecode — entrées dégénérées', () => {
  it('chaîne d espaces seuls → null', () => {
    expect(parseTimecode('   ')).toBeNull();
    expect(parseTimecode('\t\n')).toBeNull();
  });

  it('valeur négative → null (le signe casse le format numérique)', () => {
    expect(parseTimecode('-1:30')).toBeNull();
  });

  it('00:00 → 0 seconde (et non null)', () => {
    expect(parseTimecode('00:00')).toBe(0);
  });
});

describe('formatTimecodeA11y — singuliers', () => {
  it('exactement 1 heure → « 1 heure »', () => {
    expect(formatTimecodeA11y(3600)).toBe('1 heure');
  });

  it('2 heures → pluriel', () => {
    expect(formatTimecodeA11y(7200)).toBe('2 heures');
  });

  it('1h 1min 1s → tous les singuliers', () => {
    expect(formatTimecodeA11y(3661)).toBe('1 heure 1 minute 1 seconde');
  });
});

describe('extractYoutubeId — cas dégradés', () => {
  it('youtu.be sans path → null', () => {
    expect(extractYoutubeId('https://youtu.be/')).toBeNull();
  });

  it('youtu.be avec id → id', () => {
    expect(extractYoutubeId('https://youtu.be/dQw4w9WgXcQ')).toBe('dQw4w9WgXcQ');
  });

  it('chaîne non-URL → null (catch)', () => {
    expect(extractYoutubeId('pas une url')).toBeNull();
  });

  it('youtube.com sans v ni /embed/ → null', () => {
    expect(extractYoutubeId('https://www.youtube.com/feed/subscriptions')).toBeNull();
  });
});
