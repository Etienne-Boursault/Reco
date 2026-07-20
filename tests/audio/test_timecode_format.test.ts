/**
 * Tests des helpers timecode (parse/format).
 */
import { describe, it, expect } from 'vitest';
import {
  parseTimecode,
  formatTimecode,
  formatTimecodeA11y,
  extractYoutubeId,
} from '../../src/lib/audio/timecode';

describe('parseTimecode', () => {
  it('parse MM:SS', () => {
    expect(parseTimecode('2:13')).toBe(133);
    expect(parseTimecode('0:05')).toBe(5);
  });
  it('parse HH:MM:SS', () => {
    expect(parseTimecode('01:02:13')).toBe(3733);
    expect(parseTimecode('00:00:30')).toBe(30);
  });
  it('tolère les espaces', () => {
    expect(parseTimecode('  1:02  ')).toBe(62);
  });
  it('rejette les formats invalides', () => {
    expect(parseTimecode('')).toBeNull();
    expect(parseTimecode(null)).toBeNull();
    expect(parseTimecode(undefined)).toBeNull();
    expect(parseTimecode('abc')).toBeNull();
    expect(parseTimecode('1:2:3:4')).toBeNull();
    expect(parseTimecode('1')).toBeNull();
    expect(parseTimecode('-1:00')).toBeNull();
  });
});

describe('formatTimecode', () => {
  it('formate en m/s', () => {
    expect(formatTimecode(133)).toBe('2m13s');
    expect(formatTimecode(5)).toBe('5s');
    expect(formatTimecode(60)).toBe('1m00s');
  });
  it('formate avec heures', () => {
    expect(formatTimecode(3733)).toBe('1h02m13s');
  });
  it('gère valeurs invalides', () => {
    expect(formatTimecode(null)).toBe('');
    expect(formatTimecode(undefined)).toBe('');
    expect(formatTimecode(-1)).toBe('');
    expect(formatTimecode(NaN)).toBe('');
  });
});

describe('formatTimecodeA11y', () => {
  it('formate en chaine longue lisible', () => {
    expect(formatTimecodeA11y(133)).toBe('2 minutes 13 secondes');
    expect(formatTimecodeA11y(60)).toBe('1 minute');
    expect(formatTimecodeA11y(3725)).toBe('1 heure 2 minutes 5 secondes');
    expect(formatTimecodeA11y(1)).toBe('1 seconde');
    expect(formatTimecodeA11y(0)).toBe('0 secondes');
  });
  it('gère invalides', () => {
    expect(formatTimecodeA11y(null)).toBe('');
    expect(formatTimecodeA11y(-5)).toBe('');
  });
});

describe('extractYoutubeId', () => {
  it('extrait depuis watch?v=', () => {
    expect(extractYoutubeId('https://www.youtube.com/watch?v=abc123XYZ_-')).toBe('abc123XYZ_-');
  });
  it('extrait depuis youtu.be', () => {
    expect(extractYoutubeId('https://youtu.be/abc123XYZ_-')).toBe('abc123XYZ_-');
  });
  it('extrait depuis embed', () => {
    expect(extractYoutubeId('https://www.youtube-nocookie.com/embed/abc123XYZ_-')).toBe(
      'abc123XYZ_-',
    );
  });
  it('retourne null si url invalide', () => {
    expect(extractYoutubeId('')).toBeNull();
    expect(extractYoutubeId('https://example.com/foo')).toBeNull();
    expect(extractYoutubeId(null)).toBeNull();
  });
});
