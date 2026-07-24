/**
 * Signalements « situation de l'artiste » — chargement + résolution.
 *
 * Données curées à la main dans `creator-flags.json` (cf. le README voisin).
 * Ce module se contente de charger ce fichier et d'exposer une recherche par
 * nom de créateur : il n'invente RIEN, il n'affiche que ce qui est déclaré et
 * sourcé. Le même JSON est lu côté serveur de relecture par
 * `tools/creator_flags.py` (normalisation identique).
 */
import raw from './creator-flags.json';

export type FlagSeverity = 'accusation' | 'condamnation';

export interface CreatorFlag {
  /** Orthographes du créateur à faire correspondre (casse/accents ignorés). */
  names: string[];
  /** Texte factuel et sourcé affiché dans la bulle. */
  situation: string;
  /** URL de la source (obligatoire côté curation). */
  source: string;
  /** `accusation` (présomption d'innocence) ou `condamnation`. */
  severity?: FlagSeverity;
}

interface FlagsFile {
  flags?: CreatorFlag[];
}

/** Normalise un nom pour la comparaison : minuscules, sans accents ni ponctuation. */
export function normalizeName(name: string): string {
  return name
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, ' ')
    .trim();
}

const FLAGS: CreatorFlag[] = ((raw as FlagsFile).flags ?? []).filter(
  (f) => f && Array.isArray(f.names) && f.situation && f.source,
);

/** Index nom normalisé -> signalement (première déclaration gagne). */
const BY_NAME = new Map<string, CreatorFlag>();
for (const flag of FLAGS) {
  for (const name of flag.names) {
    const key = normalizeName(name);
    if (key && !BY_NAME.has(key)) BY_NAME.set(key, flag);
  }
}

/** Signalement pour un créateur, ou `null` si aucun. */
export function creatorFlag(name: string | null | undefined): CreatorFlag | null {
  if (!name) return null;
  return BY_NAME.get(normalizeName(name)) ?? null;
}

/** Nombre de signalements chargés (diagnostic/tests). */
export const flagCount = FLAGS.length;
