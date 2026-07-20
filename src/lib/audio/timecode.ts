/**
 * src/lib/audio/timecode.ts — Helpers purs pour timecodes audio.
 *
 * Module sans dépendance (pas d'Astro, pas de fs). Sert de socle aux
 * composants `AudioExcerpt.astro` / `AudioPlayer.astro` et reste testable
 * isolément côté vitest. Cf. ADR 0036.
 */

/**
 * Convertit un timecode `HH:MM:SS`, `MM:SS` ou `H:MM:SS` en secondes.
 * Retourne `null` si le format n'est pas reconnu ou si la valeur est
 * négative. Tolère les espaces autour.
 */
export function parseTimecode(ts: string | null | undefined): number | null {
  if (!ts || typeof ts !== 'string') return null;
  const trimmed = ts.trim();
  if (!trimmed) return null;
  const parts = trimmed.split(':').map((p) => p.trim());
  if (parts.length < 2 || parts.length > 3) return null;
  const nums = parts.map((p) => (/^\d+$/.test(p) ? Number(p) : NaN));
  if (nums.some((n) => Number.isNaN(n))) return null;
  let seconds: number;
  if (nums.length === 3) {
    seconds = nums[0] * 3600 + nums[1] * 60 + nums[2];
  } else {
    seconds = nums[0] * 60 + nums[1];
  }
  if (seconds < 0) return null;
  return seconds;
}

/**
 * Formate des secondes en libellé court `2m13s` ou `1h02m13s`.
 * Utile pour les boutons compacts ("Écouter à 2m13s").
 */
export function formatTimecode(seconds: number | null | undefined): string {
  if (typeof seconds !== 'number' || !Number.isFinite(seconds) || seconds < 0) {
    return '';
  }
  const s = Math.floor(seconds);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const r = s % 60;
  if (h > 0) {
    return `${h}h${String(m).padStart(2, '0')}m${String(r).padStart(2, '0')}s`;
  }
  if (m > 0) {
    return `${m}m${String(r).padStart(2, '0')}s`;
  }
  return `${r}s`;
}

/**
 * Formate des secondes en libellé long lisible pour aria-label.
 * Ex : 133 → "2 minutes 13 secondes" ; 3725 → "1 heure 2 minutes 5 secondes".
 */
export function formatTimecodeA11y(seconds: number | null | undefined): string {
  if (typeof seconds !== 'number' || !Number.isFinite(seconds) || seconds < 0) {
    return '';
  }
  const s = Math.floor(seconds);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const r = s % 60;
  const parts: string[] = [];
  if (h > 0) parts.push(h === 1 ? '1 heure' : `${h} heures`);
  if (m > 0) parts.push(m === 1 ? '1 minute' : `${m} minutes`);
  if (r > 0 || parts.length === 0) {
    parts.push(r === 1 ? '1 seconde' : `${r} secondes`);
  }
  return parts.join(' ');
}

/**
 * Construit une URL d'embed YouTube respectueuse de la vie privée
 * (`youtube-nocookie.com`). Pas d'autoplay, mode rel=0 (pas de vidéos
 * suggérées d'autres chaînes en fin). `start`/`end` en secondes entières.
 *
 * Retourne `null` si `videoId` est invalide.
 */
export function buildYoutubeEmbedUrl(
  videoId: string | null | undefined,
  options: { startSeconds?: number | null; endSeconds?: number | null } = {},
): string | null {
  if (!videoId || typeof videoId !== 'string') return null;
  // YouTube IDs : 11 caractères [A-Za-z0-9_-]. On reste tolérant pour les
  // fixtures (toute chaîne non vide sans `/` ni `?`) tout en bloquant les
  // injections évidentes d'attributs (querystring, fragment, espace).
  if (!/^[A-Za-z0-9_-]{1,32}$/.test(videoId)) return null;
  const params = new URLSearchParams();
  params.set('autoplay', '0');
  params.set('rel', '0');
  const { startSeconds, endSeconds } = options;
  if (typeof startSeconds === 'number' && Number.isFinite(startSeconds) && startSeconds > 0) {
    params.set('start', String(Math.floor(startSeconds)));
  }
  if (typeof endSeconds === 'number' && Number.isFinite(endSeconds) && endSeconds > 0) {
    params.set('end', String(Math.floor(endSeconds)));
  }
  return `https://www.youtube-nocookie.com/embed/${videoId}?${params.toString()}`;
}

/**
 * Extrait un videoId YouTube d'une URL `youtube.com/watch?v=…`,
 * `youtu.be/…` ou `youtube.com/embed/…`. Retourne `null` si non trouvé.
 */
export function extractYoutubeId(url: string | null | undefined): string | null {
  if (!url || typeof url !== 'string') return null;
  try {
    const u = new URL(url);
    const host = u.hostname.replace(/^www\./, '');
    if (host === 'youtu.be') {
      const id = u.pathname.replace(/^\//, '').split('/')[0];
      return id || null;
    }
    if (host.endsWith('youtube.com') || host.endsWith('youtube-nocookie.com')) {
      const v = u.searchParams.get('v');
      if (v) return v;
      const m = /^\/embed\/([^/?#]+)/.exec(u.pathname);
      if (m) return m[1];
    }
    return null;
  } catch {
    return null;
  }
}
