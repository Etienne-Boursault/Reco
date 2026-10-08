/**
 * oeuvreDesRecos.ts — de quelle fiche d'œuvre parle une reco ?
 *
 * POURQUOI CE MODULE EXISTE
 * -------------------------
 * Les cartes de reco sont ce que le visiteur voit le plus — page épisode,
 * « Toutes les recos » —, et aucune ne menait à la fiche de son œuvre : on y
 * arrivait seulement par les galeries ou la recherche. Voir « Bref » sur
 * l'épisode #10 ne permettait pas de découvrir qu'il avait été cité dans
 * quatorze épisodes (relevé après l'audit d'interface du 2026-10-07).
 *
 * LA JOINTURE
 * -----------
 * Une reco et sa mention partagent leur IDENTIFIANT, et la mention porte
 * l'œuvre (`itemId`). C'est la seule jointure entre les deux collections ; la
 * fiche d'œuvre s'en sert déjà pour aller chercher les liens des recos.
 *
 * Seules les mentions VISIBLES comptent : une fiche n'est construite que pour
 * une œuvre qui en a au moins une (`buildWorkIndex`). Pointer depuis une
 * mention écartée mènerait, pour une œuvre qui n'a qu'elle, à une page
 * introuvable — la carte garde alors son titre sans lien.
 */

export interface MentionPourLien {
  id: string;
  itemId: string;
  status?: string | null;
}

/** Associe l'identifiant de chaque reco à l'œuvre de sa mention visible. */
export function oeuvreParReco(mentions: readonly MentionPourLien[]): Map<string, string> {
  const out = new Map<string, string>();
  for (const m of mentions) {
    if (m.status === 'discarded') continue;
    out.set(m.id, m.itemId);
  }
  return out;
}

/** Adresse de la fiche d'une œuvre, ou `undefined` si la reco n'en a pas. */
export function lienOeuvre(
  oeuvres: ReadonlyMap<string, string> | undefined,
  sourceId: string,
  recoId: string,
): string | undefined {
  const itemId = oeuvres?.get(recoId);
  return itemId ? `/${sourceId}/oeuvre/${itemId}` : undefined;
}
