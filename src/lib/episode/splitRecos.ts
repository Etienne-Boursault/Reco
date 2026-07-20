/**
 * src/lib/episode/splitRecos.ts — Répartition des recos d'un épisode pour la
 * page épisode (`/<source>/episode/<guid>`).
 *
 * DÉCISION PRODUIT (CR Story 4) : les œuvres d'invité·es (`guestWork`) RESTENT
 * comptées comme des recommandations dans tous les compteurs / stats /
 * galeries du site. La page épisode est le SEUL endroit qui les présente à
 * part, dans une sous-section dédiée, pour ne pas les confondre visuellement
 * avec les recommandations spontanées de l'équipe.
 *
 * Ce module isole cette répartition (fonction pure, testable) — d'où le nom
 * `spontaneous` (et non `trueRecos`, qui prêtait à confusion avec le
 * `trueRecos` de `[source]/index.astro` qui, lui, INCLUT les œuvres d'invités).
 *
 * Trois seaux mutuellement exclusifs, ordre d'entrée préservé :
 *  - `spontaneous` : vraies recos de l'équipe (kind=reco, pas guestWork).
 *  - `guestWorks`  : œuvres présentées par un·e invité·e (kind=reco, guestWork).
 *  - `citations`   : œuvres simplement évoquées (kind=citation) — inchangé.
 *
 * Cas legacy improbable : une reco `kind=citation` marquée `guestWork` reste
 * dans `citations` (la citation prime pour la présentation), pour ne pas la
 * dupliquer ni changer le comportement des citations existantes.
 */

/** Forme minimale attendue (duck-typing pour testabilité). */
export interface EpisodeRecoLike {
  kind?: string;
  guestWork?: boolean;
}

export interface SplitRecos<T extends EpisodeRecoLike> {
  spontaneous: T[];
  guestWorks: T[];
  citations: T[];
}

export function splitEpisodeRecos<T extends EpisodeRecoLike>(
  recos: readonly T[],
): SplitRecos<T> {
  const spontaneous: T[] = [];
  const guestWorks: T[] = [];
  const citations: T[] = [];
  for (const r of recos) {
    if ((r.kind ?? 'reco') === 'citation') {
      citations.push(r);
    } else if (r.guestWork === true) {
      // N6 : strictness `=== true` alignée sur RecoCard/MentionsTimeline
      // (convention unique dans le projet — pas de truthy implicite).
      guestWorks.push(r);
    } else {
      spontaneous.push(r);
    }
  }
  return { spontaneous, guestWorks, citations };
}
