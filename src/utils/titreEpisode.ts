/**
 * titreEpisode.ts — le titre d'un épisode tel qu'on l'AFFICHE.
 *
 * POURQUOI CE MODULE EXISTE
 * -------------------------
 * Depuis la saison 5, le flux publie ses titres avec un suffixe qui répète le
 * nom du podcast et le numéro : « Babor et Jenny Letellier irremplaçables
 * (Un Bon Moment, S6-E03) ». Partout où le site affiche ce titre, le numéro
 * est DÉJÀ là, dans le badge « S6·E3 » posé juste à côté. Le suffixe ne disait
 * donc rien de neuf, et il coûtait cher : sur les vignettes du catalogue,
 * coupées à deux lignes, c'est précisément lui qui était mangé par les points
 * de suspension ; sur la page épisode, il occupait une ligne entière du grand
 * titre (audit d'interface du 2026-10-07, item #7).
 *
 * CE QUI EST RETIRÉ, ET CE QUI NE L'EST PAS
 * -----------------------------------------
 * Seul le suffixe qui DOUBLE le badge disparaît : nom du podcast + saison +
 * épisode. « (Un Bon Moment, hors-série) » reste, car « hors-série » n'est
 * écrit nulle part ailleurs. Un titre qui, sans son suffixe, serait vide est
 * rendu tel quel : mieux vaut une redondance qu'un titre absent.
 *
 * C'est un traitement d'AFFICHAGE. La donnée n'est pas modifiée, et les usages
 * qui ne sont pas lus à côté du badge — `<title>` du document, description,
 * JSON-LD, clé de recherche — gardent le titre complet : un moteur de
 * recherche, un partage ou une requête « S6-E03 » n'ont pas le badge sous les
 * yeux.
 */

/** Échappe une chaîne pour l'insérer littéralement dans une expression régulière. */
function echapperRegex(texte: string): string {
  return texte.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

/**
 * Retire du titre le suffixe « (<podcast>, S<n>-E<n>) » qui répète le badge.
 *
 * @param titre   Titre de l'épisode, tel que publié dans le flux.
 * @param podcast Nom du podcast (`source.data.title`). Sans lui, rien n'est
 *                retiré : on ne devine pas quel nom le suffixe doit porter.
 */
export function titreEpisodeAffiche(
  titre: string | null | undefined,
  podcast: string | null | undefined,
): string {
  const brut = titre ?? '';
  if (!brut || !podcast?.trim()) return brut;
  const suffixe = new RegExp(
    `\\s*\\(\\s*${echapperRegex(podcast.trim())}\\s*,\\s*S\\d+\\s*[-·]?\\s*E\\d+\\s*\\)\\s*$`,
    'iu',
  );
  const court = brut.replace(suffixe, '').trim();
  return court || brut;
}
