/**
 * invite.ts — ce que la page d'un invité montre, calculé à part pour être testé.
 *
 * LA PAGE (direction B « Bibliothèque », retenue le 2026-10-07)
 * ------------------------------------------------------------
 * 1. Ses passages : les épisodes où la personne était présente.
 * 2. Ses œuvres : ce qu'elle a présenté et dont elle est CRÉATRICE.
 * 3. Ce qu'elle recommande, groupé par type d'œuvre.
 * 4. Les œuvres seulement évoquées, en une ligne.
 *
 * « SES ŒUVRES » N'EST PAS LE DRAPEAU `guestWork`
 * -----------------------------------------------
 * `guestWork` dit « œuvre de quelqu'un présent dans l'épisode ». Florent
 * Bernard recommande Pulsions, le spectacle de Kyan : la mention porte
 * `guestWork`, mais Pulsions n'est pas son œuvre. Seul le créateur fait foi
 * (`parleDeSonOeuvre`, cf. `utils/verbeMention.ts`).
 *
 * QUI EST « LA PERSONNE »
 * -----------------------
 * La règle des pages invité ne change pas : une mention appartient à la page
 * dont le nom ÉGALE son `recommendedBy` (casse et espaces ignorés). Une reco
 * attribuée collectivement (« A & B ») reste sur la page « A & B » et ne
 * compte ni pour A ni pour B.
 */
import { parleDeSonOeuvre } from '../../utils/verbeMention';

export interface MentionInvite {
  id?: string;
  itemId: string;
  recommendedBy?: string | null;
  kind?: 'reco' | 'citation';
  status?: 'draft' | 'validated' | 'discarded';
  sourceRef: { episodeGuid?: string | null };
}

export interface OeuvreInvite {
  id: string;
  title: string;
  types: readonly string[];
  creator?: string | null;
}

export interface EpisodeInvite {
  guid: string;
  title: string;
  number?: number;
  season?: number;
  date?: Date;
  guests?: readonly string[];
}

/** Une œuvre sur la page, avec les épisodes où la personne en a parlé. */
export interface LigneInvite {
  oeuvre: OeuvreInvite;
  episodes: EpisodeInvite[];
}

export interface GroupeInvite {
  /** Premier type de l'œuvre : c'est lui qui la range. */
  type: string;
  lignes: LigneInvite[];
}

export interface BibliothequeInvite {
  passages: EpisodeInvite[];
  sesOeuvres: LigneInvite[];
  recommandations: GroupeInvite[];
  evoquees: LigneInvite[];
  /** Nombre de recommandations (œuvres distinctes, ses œuvres exclues). */
  nbRecommandations: number;
}

function cle(nom: string | null | undefined): string {
  return (nom ?? '').normalize('NFC').trim().toLowerCase();
}

function parDate(a: EpisodeInvite, b: EpisodeInvite): number {
  return (a.date?.getTime() ?? 0) - (b.date?.getTime() ?? 0);
}

/**
 * Les épisodes où la personne était là : invitée de l'épisode (`guests`) ou
 * autrice d'une mention publique. Du plus ancien au plus récent.
 */
export function passagesDeLInvite(
  nom: string,
  episodes: readonly EpisodeInvite[],
  mentions: readonly MentionInvite[],
): EpisodeInvite[] {
  const qui = cle(nom);
  const guids = new Set<string>();
  for (const m of mentions) {
    if (m.status === 'discarded' || cle(m.recommendedBy) !== qui) continue;
    if (m.sourceRef.episodeGuid) guids.add(m.sourceRef.episodeGuid);
  }
  return episodes
    .filter((e) => guids.has(e.guid) || (e.guests ?? []).some((g) => cle(g) === qui))
    .sort(parDate);
}

/** Regroupe les mentions par œuvre, chaque œuvre avec ses épisodes datés. */
function lignes(
  mentions: readonly MentionInvite[],
  oeuvres: ReadonlyMap<string, OeuvreInvite>,
  episodes: ReadonlyMap<string, EpisodeInvite>,
): LigneInvite[] {
  const parOeuvre = new Map<string, Map<string, EpisodeInvite>>();
  for (const m of mentions) {
    if (!oeuvres.has(m.itemId)) continue;
    const eps = parOeuvre.get(m.itemId) ?? new Map<string, EpisodeInvite>();
    const ep = m.sourceRef.episodeGuid ? episodes.get(m.sourceRef.episodeGuid) : undefined;
    if (ep) eps.set(ep.guid, ep);
    parOeuvre.set(m.itemId, eps);
  }
  return [...parOeuvre.entries()]
    .map(([id, eps]) => ({ oeuvre: oeuvres.get(id)!, episodes: [...eps.values()].sort(parDate) }))
    .sort(
      (a, b) =>
        b.episodes.length - a.episodes.length ||
        a.oeuvre.title.localeCompare(b.oeuvre.title, 'fr', { sensitivity: 'base' }),
    );
}

export function bibliothequeDeLInvite(
  nom: string,
  oeuvres: readonly OeuvreInvite[],
  mentions: readonly MentionInvite[],
  episodes: readonly EpisodeInvite[],
): BibliothequeInvite {
  const qui = cle(nom);
  const siennes = mentions.filter(
    (m) => m.status !== 'discarded' && cle(m.recommendedBy) === qui,
  );
  const parId = new Map(oeuvres.map((o) => [o.id, o]));
  const parGuid = new Map(episodes.map((e) => [e.guid, e]));

  const estSienne = (m: MentionInvite) => parleDeSonOeuvre(nom, parId.get(m.itemId)?.creator);
  const sesOeuvres = lignes(siennes.filter((m) => m.kind !== 'citation' && estSienne(m)), parId, parGuid);
  const recos = lignes(siennes.filter((m) => m.kind !== 'citation' && !estSienne(m)), parId, parGuid);
  // Une œuvre recommandée ailleurs n'est pas « seulement évoquée ».
  const dejaListees = new Set([...sesOeuvres, ...recos].map((l) => l.oeuvre.id));
  const evoquees = lignes(
    siennes.filter((m) => m.kind === 'citation' && !dejaListees.has(m.itemId)),
    parId,
    parGuid,
  );

  const groupes = new Map<string, LigneInvite[]>();
  for (const l of recos) {
    const type = l.oeuvre.types[0] ?? 'autre';
    groupes.set(type, [...(groupes.get(type) ?? []), l]);
  }
  const recommandations = [...groupes.entries()]
    .map(([type, ls]) => ({ type, lignes: ls }))
    .sort((a, b) => b.lignes.length - a.lignes.length || a.type.localeCompare(b.type));

  return {
    passages: passagesDeLInvite(nom, episodes, mentions),
    sesOeuvres,
    recommandations,
    evoquees,
    nbRecommandations: recos.length,
  };
}

/** « Florent Bernard » → « FB » ; « Orelsan » → « O » (deux lettres au plus). */
export function initiales(nom: string): string {
  return nom
    .split(/[\s-]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((mot) => mot[0]!.toLocaleUpperCase('fr'))
    .join('');
}

/**
 * Le prénom, pour « Ce que Florent recommande ». Le nom entier s'il est seul,
 * ou si la page est celle d'un groupe (« Kyan Khojandi & Florent Bernard ») :
 * « Ce que Kyan recommande » y serait faux.
 */
export function prenom(nom: string): string {
  if (/&|,|\set\s/.test(nom)) return nom.trim();
  return nom.trim().split(/\s+/)[0] ?? nom;
}
