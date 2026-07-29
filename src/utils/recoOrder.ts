/**
 * Ordre d'affichage des recommandations.
 *
 * Les pages appelaient `getCollection('recos')` SANS tri : l'ordre affiché
 * était donc celui d'énumération du chargeur de fichiers d'Astro, un détail
 * d'implémentation sur lequel rien ne garantissait la stabilité. La migration
 * Astro 5 → 7 l'a démontré en le changeant — mêmes recos, ordre différent,
 * aucun test rouge. Le défaut était latent depuis toujours ; la migration
 * s'est contentée de le rendre visible.
 *
 * L'ordre retenu est CHRONOLOGIQUE — l'instant où la recommandation est
 * prononcée dans l'épisode. C'est le seul qui ait du sens pour un auditeur qui
 * réécoute, et les 1209 recos actives portent toutes un `timestamp`.
 *
 * Le tri est TOTAL (départage par `id`) : deux recos au même timestamp
 * s'ordonnent toujours pareil, donc deux builds successifs produisent le même
 * HTML. Sans ce départage, on remplacerait un ordre instable par un autre.
 */
import { parseTimecode } from '../lib/audio/timecode';

/** Forme minimale attendue — duck-typing, pour rester testable sans fixture Astro. */
export interface OrderableReco {
  id: string;
  timestamp?: string | null;
}

/**
 * Position en secondes, ou `+Infinity` si le timecode est absent ou illisible.
 *
 * `+Infinity` plutôt que `0` : une reco sans position connue se range en FIN
 * de liste, là où elle ne perturbe pas la lecture chronologique — jamais au
 * milieu, et surtout jamais en tête comme le ferait un `0`.
 */
function positionOf(reco: OrderableReco): number {
  return parseTimecode(reco.timestamp) ?? Number.POSITIVE_INFINITY;
}

/** Comparateur chronologique, départagé par `id`. Convient à `Array.sort`. */
export function compareRecosByTimestamp(a: OrderableReco, b: OrderableReco): number {
  const pa = positionOf(a);
  const pb = positionOf(b);
  if (pa !== pb) return pa - pb;
  return a.id < b.id ? -1 : a.id > b.id ? 1 : 0;
}

/** Copie triée — ne mute pas le tableau reçu (les collections Astro sont partagées). */
export function sortRecosByTimestamp<T extends OrderableReco>(recos: readonly T[]): T[] {
  return [...recos].sort(compareRecosByTimestamp);
}
