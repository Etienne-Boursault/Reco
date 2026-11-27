/**
 * src/utils/sortieAnnoncee.ts — la mention « Sortie annoncée le … » d'une carte
 * (R4 B, 27/11/2026, tranche F).
 *
 * `releaseDate` est une date posée à la main, `AAAA-MM-JJ` (cf. `content.config.ts`).
 * Deux règles pour qu'elle ne bouge jamais d'un jour :
 *  - le libellé s'écrit DEPUIS LES CHIFFRES de la chaîne : `new Date('2026-11-20')`
 *    est minuit UTC, donc le 19 à l'ouest de Greenwich ;
 *  - « aujourd'hui » se lit à Paris (comme `tools/date_sortie.py`), pas dans le
 *    fuseau du poste qui construit le site. « Maintenant » est un paramètre :
 *    le test ne dépend pas de l'horloge.
 *
 * Ceinture (tour 1 de revue, PR #227) : un type que la relance ne sert pas n'affiche rien,
 * même si une date est restée dans le fichier ; la vraie garde est la donnée
 * (`tools/review_edit_sortie.py` retire la date). Liste gardée par un test
 * contre `date_sortie.TYPES_V1`.
 *
 * Date absolue plutôt que « dans 3 jours » : elle reste vraie même si la page
 * a été construite plusieurs jours avant. La mention reste affichée le jour
 * même de la date et disparaît le lendemain.
 */

const MOIS = [
  'janvier', 'février', 'mars', 'avril', 'mai', 'juin',
  'juillet', 'août', 'septembre', 'octobre', 'novembre', 'décembre',
];

const TYPES_SERVIS = ['album', 'musique', 'livre', 'jeu'];

const FORMAT = /^(\d{4})-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$/;

/** « 20 novembre 2026 » si la date n'est pas passée, sinon `null`. */
export function sortieAnnoncee(
  releaseDate: string | undefined,
  maintenant: Date,
  types?: readonly string[],
): string | null {
  const m = FORMAT.exec(releaseDate ?? '');
  if (!m) return null;
  if (types && !types.some((t) => TYPES_SERVIS.includes(t))) return null;
  // `sv-SE` écrit AAAA-MM-JJ : la comparaison de deux chaînes est celle des dates.
  const aujourdhui = maintenant.toLocaleDateString('sv-SE', { timeZone: 'Europe/Paris' });
  if (m[0] < aujourdhui) return null;
  const jour = Number(m[3]);
  return `${jour === 1 ? '1er' : jour} ${MOIS[Number(m[2]) - 1]} ${m[1]}`;
}
