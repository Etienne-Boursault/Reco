/**
 * Libellés d'affichage des types de recos.
 *
 * Centralisé ici pour éviter la duplication entre composants (cartes,
 * filtres, pages d'épisode). Cohérent avec l'enum `recoType` de
 * `src/content.config.ts` (mais ce module n'en dépend pas pour rester
 * utilisable côté client comme côté serveur).
 */

/** Libellé singulier — utilisé sur les cartes individuelles. */
export const TYPE_LABELS: Record<string, string> = {
  film: 'Film',
  serie: 'Série',
  livre: 'Livre',
  bd: 'BD',
  musique: 'Musique',
  album: 'Album',
  podcast: 'Podcast',
  jeu: 'Jeu',
  spectacle: 'Spectacle',
  lieu: 'Lieu',
  artiste: 'Artiste',
  video: 'Vidéo',
  autre: 'Autre',
};

/** Libellé pluriel — utilisé dans les filtres / chips de la page catalogue. */
export const TYPE_LABELS_PLURAL: Record<string, string> = {
  film: 'Films',
  serie: 'Séries',
  livre: 'Livres',
  bd: 'BD',
  musique: 'Musique',
  album: 'Albums',
  podcast: 'Podcasts',
  jeu: 'Jeux',
  spectacle: 'Spectacles',
  lieu: 'Lieux',
  artiste: 'Artistes',
  video: 'Vidéos',
  autre: 'Autres',
};

/** Formate « S2·E3 » / « #42 » / « » selon la disponibilité des champs. */
export function episodeLabel(e: { season?: number; number?: number }): string {
  if (e.season && e.number) return `S${e.season}·E${e.number}`;
  if (e.number) return `#${e.number}`;
  return '';
}
