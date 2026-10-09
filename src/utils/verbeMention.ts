/**
 * verbeMention.ts — le verbe qui précède le nom sous une reco : « Reco de »,
 * « Présentée par » ou « Évoquée par ».
 *
 * POURQUOI CE MODULE EXISTE
 * -------------------------
 * Le drapeau `guestWork` ne dit PAS « œuvre de la personne qui en parle » : il
 * dit « œuvre de quelqu'un présent dans l'épisode ». Pulsions, le spectacle de
 * Kyan, le porte dans les neuf épisodes où il est cité — y compris quand c'est
 * un INVITÉ qui le recommande.
 *
 * L'audit d'interface du 2026-10-07 (item #9) avait remplacé « Reco de » par
 * « Présentée par » sur toutes les œuvres d'invité. Résultat : « Présentée par
 * Kheiron » sous le spectacle de Kyan, et de même pour Florent Bernard, Yassir
 * et Paul Mirabel — l'inverse de ce qui s'est passé. Relevé le même jour.
 *
 * « Présentée par X » n'est donc juste que si X fait partie des CRÉATEURS de
 * l'œuvre : c'est l'auto-promotion que la section « Leurs œuvres » regroupe.
 * Partout ailleurs, X recommande l'œuvre de quelqu'un d'autre : « Reco de X ».
 */

export type VerbeMention = 'Reco de' | 'Présentée par' | 'Évoquée par';

/** Minuscules, sans accents ni espaces de bord : « Bérengère » = « berengere ». */
function normaliser(nom: string): string {
  return nom
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase()
    .trim();
}

/** « Kyan Khojandi & Navo », « A, B et C » → la liste des personnes. */
function personnes(liste: string | null | undefined): string[] {
  return (liste ?? '')
    .split(/\s*(?:&|,|;|\bet\b)\s*/)
    .map(normaliser)
    .filter(Boolean);
}

/**
 * Vrai si au moins une des personnes qui en parlent est créatrice de l'œuvre.
 *
 * Un nom d'UN SEUL MOT vaut aussi pour le prénom d'un créateur : le corpus
 * écrit « Babor » dans `recommendedBy` et « Babor Lelefan » dans `creator`,
 * et ses spectacles s'affichaient « Reco de Babor ». Mesuré sur le corpus le
 * 2026-10-07 : cette règle ne change que ces trois cartes. Elle ne s'applique
 * qu'aux œuvres d'invité (cf. `verbeMention`), où le nom et l'œuvre viennent
 * du même épisode — un « Paul » y désigne la personne présente.
 */
export function parleDeSonOeuvre(
  recommendedBy: string | null | undefined,
  creator: string | null | undefined,
): boolean {
  const createurs = personnes(creator);
  const complets = new Set(createurs);
  const prenoms = new Set(createurs.map((c) => c.split(/\s+/)[0]));
  return personnes(recommendedBy).some(
    (p) => complets.has(p) || (!/\s/.test(p) && prenoms.has(p)),
  );
}

export function verbeMention(opts: {
  kind?: string | null;
  guestWork?: boolean | null;
  recommendedBy?: string | null;
  creator?: string | null;
}): VerbeMention {
  // La citation prime, comme partout ailleurs (cf. `splitEpisodeRecos`).
  if (opts.kind === 'citation') return 'Évoquée par';
  if (opts.guestWork === true && parleDeSonOeuvre(opts.recommendedBy, opts.creator)) {
    return 'Présentée par';
  }
  return 'Reco de';
}
