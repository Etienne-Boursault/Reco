/**
 * La vignette d'un épisode, servie par le site lui-même.
 *
 * Les fichiers sont téléchargés une fois par `tools/vignettes_episodes.py`
 * dans `public/vignettes/` : les noms calculés ici doivent rester identiques
 * aux siens. Charger `i.ytimg.com` envoyait l'adresse IP de chaque visiteur à
 * Google sans qu'il ait cliqué (mentions légales, 2026-10-22).
 *
 * Pas de repli vers l'adresse d'origine : un fichier manquant donne `null`,
 * et la carte s'affiche sans image plutôt que de rompre la promesse.
 */
import { createHash } from 'node:crypto';
import { existsSync } from 'node:fs';
import { join } from 'node:path';

const EXTENSIONS = new Set(['.jpg', '.jpeg', '.png', '.webp']);

export interface EpisodeImage {
  youtubeUrl?: string;
  imageUrl?: string;
}

/** `mq` : 320×180, catalogue. `hq` : 480×360, page de l'épisode. */
export type Taille = 'mq' | 'hq';

export function youtubeId(url?: string): string | null {
  return url?.match(/[?&]v=([\w-]+)/)?.[1] ?? null;
}

/** Le nom du fichier, qu'il existe ou non. */
export function nomVignette(episode: EpisodeImage, taille: Taille): string | null {
  const id = youtubeId(episode.youtubeUrl);
  if (id) return `yt-${id}-${taille}.jpg`;
  if (!episode.imageUrl) return null;
  const point = new URL(episode.imageUrl).pathname.lastIndexOf('.');
  const extension = point >= 0 ? new URL(episode.imageUrl).pathname.slice(point).toLowerCase() : '';
  const empreinte = createHash('sha1').update(episode.imageUrl).digest('hex').slice(0, 12);
  return `ep-${empreinte}${EXTENSIONS.has(extension) ? extension : '.jpg'}`;
}

/** Le chemin public de la vignette, ou `null` si elle n'a pas été téléchargée. */
export function vignette(
  episode: EpisodeImage,
  taille: Taille,
  racine: string = process.cwd(),
): string | null {
  const nom = nomVignette(episode, taille);
  if (!nom || !existsSync(join(racine, 'public', 'vignettes', nom))) return null;
  return `/vignettes/${nom}`;
}
