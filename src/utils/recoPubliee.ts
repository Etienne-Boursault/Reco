/**
 * Une reco n'est publique qu'une fois VALIDÉE.
 *
 * Jusqu'au 2026-09-17, le site masquait seulement les recos `discarded` : une
 * reco `draft` — sortie de l'extraction, jamais relue — s'affichait. Sans effet
 * tant que le corpus n'en contenait aucune ; plus depuis qu'une chaîne
 * automatique (`tools/traiter_nouveaux_episodes.py`) en écrit AVANT la relecture.
 * Une poussée faite à la main ne doit pas suffire à publier un brouillon.
 *
 * Les MENTIONS gardent leur filtre `!== 'discarded'` (galeries, pages d'œuvre,
 * recherche, statistiques) : six mentions `draft` sans reco associée sont en
 * ligne, dont trois seules à porter leur œuvre — les masquer supprimerait ces
 * pages. La chaîne automatique, elle, ne crée jamais de mention en brouillon.
 */
export function recoPubliee(status: string | undefined): boolean {
  return status === 'validated';
}
