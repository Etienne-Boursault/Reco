/**
 * Tests du builder d'URL d'embed YouTube nocookie.
 */
import { describe, it, expect } from 'vitest';
import { buildYoutubeEmbedUrl } from '../../src/lib/audio/timecode';

describe('buildYoutubeEmbedUrl', () => {
  it('utilise youtube-nocookie.com', () => {
    const url = buildYoutubeEmbedUrl('abc123XYZ_-');
    expect(url).toContain('youtube-nocookie.com');
    expect(url).not.toContain('www.youtube.com/embed');
  });

  it('inclut autoplay=0', () => {
    const url = buildYoutubeEmbedUrl('abc123XYZ_-');
    expect(url).toContain('autoplay=0');
  });

  it('inclut start si > 0', () => {
    const url = buildYoutubeEmbedUrl('abc123XYZ_-', { startSeconds: 133 });
    expect(url).toContain('start=133');
  });

  it('omet start si <= 0 ou absent', () => {
    expect(buildYoutubeEmbedUrl('abc')).not.toContain('start=');
    expect(buildYoutubeEmbedUrl('abc', { startSeconds: 0 })).not.toContain('start=');
    expect(buildYoutubeEmbedUrl('abc', { startSeconds: -5 })).not.toContain('start=');
  });

  it('inclut end si fourni', () => {
    const url = buildYoutubeEmbedUrl('abc', { startSeconds: 10, endSeconds: 40 });
    expect(url).toContain('end=40');
  });

  it('arrondit en entiers', () => {
    const url = buildYoutubeEmbedUrl('abc', { startSeconds: 12.9 });
    expect(url).toContain('start=12');
  });

  it('retourne null pour videoId invalide', () => {
    expect(buildYoutubeEmbedUrl(null)).toBeNull();
    expect(buildYoutubeEmbedUrl('')).toBeNull();
    expect(buildYoutubeEmbedUrl('foo/bar')).toBeNull();
    expect(buildYoutubeEmbedUrl('foo?bar')).toBeNull();
    expect(buildYoutubeEmbedUrl('a b')).toBeNull();
  });

  it('inclut rel=0 pour limiter les suggestions cross-channel', () => {
    const url = buildYoutubeEmbedUrl('abc');
    expect(url).toContain('rel=0');
  });
});
