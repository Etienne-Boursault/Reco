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
 * recherche, statistiques). Il laissait en ligne six mentions `draft` sans reco
 * quand il a été écrit ; le corpus n'en compte plus aucune au 2026-10-24, et la
 * chaîne automatique ne crée jamais de mention en brouillon. Le modèle canonique
 * (ADR 0055, proposé) aligne les deux règles sur `validated`.
 */
export function recoPubliee(status: string | undefined): boolean {
  return status === 'validated';
}
