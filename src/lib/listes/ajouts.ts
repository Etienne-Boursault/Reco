/**
 * src/lib/listes/ajouts.ts — quelles fiches viennent d'entrer dans les listes.
 *
 * LA MUSIQUE : UNE RÈGLE RECOPIÉE, FAUTE DE CORRESPONDANCE
 * --------------------------------------------------------
 * Les playlists publiées ne listent que des identifiants de titres Spotify
 * (`titres`), sans dire de quelle fiche du site chacun vient : un artiste y
 * entre par ses trois titres phares, un album par trois de ses morceaux. On
 * ne peut donc pas remonter d'un titre à sa fiche.
 *
 * On applique à la place la règle même qui remplit les playlists
 * (`tools/playlists_musique.py::entrees`) : une mention validée qui n'est pas
 * une simple citation, d'une fiche de type musique, album ou artiste, hors
 * humoristes exclus, avec un lien open.spotify.com. Ce script ne regarde que
 * les liens des recos ; on accepte aussi un lien Spotify posé sur la fiche,
 * qui en ferait tout autant une fiche musicale. Les « derniers ajouts » sont
 * ces fiches, de la plus récemment mentionnée à la plus ancienne.
 *
 * Limite assumée : entre la relecture d'un épisode et la mise à jour des
 * playlists (`/reseaux-episode`), ses fiches apparaissent ici un peu avant
 * leurs titres là-bas.
 */
import { episodeLabel } from '../../utils/recoTypes';

/** Types qui font entrer une fiche dans les playlists (cf. `TYPES` du script). */
export const TYPES_MUSICAUX: readonly string[] = ['musique', 'album', 'artiste'];

/**
 * Humoristes dont Spotify héberge les spectacles : un lien Spotify ne fait
 * pas d'eux une reco musicale. COPIE de `EXCLUS` dans
 * `tools/playlists_musique.py` (Greer Barnes, Richard Pryor, Anthony
 * Jeselnik) : les deux listes doivent rester identiques.
 */
export const EXCLUS_MUSIQUE: ReadonlySet<string> = new Set(['162d3378', 'd432f454', 'af1553d5']);

export interface FicheAjout {
  id: string;
  types: readonly string[];
  externalIds?: { spotify?: string | null } | null;
  customLinks?: readonly { url: string }[] | null;
}

export interface MentionAjout {
  id: string;
  itemId: string;
  status?: string | null;
  kind?: string | null;
  sourceRef: { episodeGuid?: string | null };
}

export interface RecoAjout {
  links?: readonly { url: string }[] | null;
}

export interface EpisodeAjout {
  guid: string;
  date?: Date;
  season?: number;
  number?: number;
}

/** Une fiche entrée dans une liste, et l'épisode qui l'y a fait entrer. */
export interface Ajout {
  itemId: string;
  episodeGuid: string | null;
}

const SPOTIFY = 'open.spotify.com';

function aUnLienSpotify(liens: readonly { url: string }[] | null | undefined): boolean {
  return (liens ?? []).some((l) => l.url.includes(SPOTIFY));
}

/** Les mentions qui font entrer une fiche dans les playlists musicales. */
export function mentionsMusicales(
  items: ReadonlyMap<string, FicheAjout>,
  mentions: readonly MentionAjout[],
  recos: ReadonlyMap<string, RecoAjout>,
): MentionAjout[] {
  return mentions.filter((m) => {
    const item = items.get(m.itemId);
    if (!item || m.status !== 'validated' || m.kind === 'citation' || EXCLUS_MUSIQUE.has(m.itemId)) return false;
    if (!item.types.some((t) => TYPES_MUSICAUX.includes(t))) return false;
    return (
      aUnLienSpotify(recos.get(m.id)?.links) ||
      Boolean(item.externalIds?.spotify) ||
      aUnLienSpotify(item.customLinks)
    );
  });
}

function dateDe(episodes: ReadonlyMap<string, EpisodeAjout>, guid: string | null | undefined): number {
  return (guid && episodes.get(guid)?.date?.getTime()) || 0;
}

/**
 * Pour chaque fiche, la mention de l'épisode le plus récent.
 *
 * À date égale (même épisode), l'ordre inverse du titre : le script range les
 * fiches d'un épisode par titre, la dernière ajoutée est donc la dernière dans
 * cet ordre.
 */
export function plusRecentesParFiche(
  mentions: readonly MentionAjout[],
  episodes: ReadonlyMap<string, EpisodeAjout>,
  titres: ReadonlyMap<string, string>,
): Ajout[] {
  const parFiche = new Map<string, MentionAjout>();
  for (const m of mentions) {
    const deja = parFiche.get(m.itemId);
    if (!deja || dateDe(episodes, m.sourceRef.episodeGuid) > dateDe(episodes, deja.sourceRef.episodeGuid)) {
      parFiche.set(m.itemId, m);
    }
  }
  const titre = (id: string) => titres.get(id) ?? '';
  return [...parFiche.values()]
    .sort((a, b) => {
      const ecart = dateDe(episodes, b.sourceRef.episodeGuid) - dateDe(episodes, a.sourceRef.episodeGuid);
      if (ecart !== 0) return ecart;
      return titre(a.itemId) < titre(b.itemId) ? 1 : titre(a.itemId) > titre(b.itemId) ? -1 : 0;
    })
    .map((m) => ({ itemId: m.itemId, episodeGuid: m.sourceRef.episodeGuid ?? null }));
}

/**
 * Les premières fiches d'une liste SensCritique qui ont une page sur le site.
 *
 * @param ids      `ajoutees`, de la plus récente à la plus ancienne.
 * @param recentes Pour chaque fiche visible, sa mention la plus récente
 *                 (`plusRecentesParFiche` sur les mentions publiques). Une
 *                 fiche absente n'a pas de page : on passe à la suivante.
 */
export function premieresDeLaListe(ids: readonly string[], recentes: ReadonlyMap<string, Ajout>, n: number): Ajout[] {
  const out: Ajout[] = [];
  for (const id of ids) {
    if (out.length === n) break;
    const a = recentes.get(id);
    if (a) out.push(a);
  }
  return out;
}

/** Une vignette de « derniers ajouts » : la fiche, et l'épisode qui l'a fait entrer. */
export interface Vignette<F> {
  item: F;
  /** Badge de l'épisode (« S6·E7 »), vide si l'épisode n'a pas de numéro. */
  detail: string;
}

export interface Corpus<F extends FicheAjout & { title: string }> {
  items: readonly F[];
  /** Mentions DE LA SOURCE, tous statuts : le tri se fait ici. */
  mentions: readonly MentionAjout[];
  recos: ReadonlyMap<string, RecoAjout>;
  episodes: readonly EpisodeAjout[];
}

/**
 * Les derniers ajouts de chaque liste, prêts à rendre.
 *
 * @param genres Pour chaque liste SensCritique, ses `oeuvres` (récentes d'abord).
 */
export function derniersAjouts<F extends FicheAjout & { title: string }>(
  corpus: Corpus<F>,
  genres: readonly { genre: string; oeuvres: readonly string[] }[],
  combien: { musique: number; liste: number },
): { musique: Vignette<F>[]; listes: Map<string, Vignette<F>[]> } {
  const fiches = new Map(corpus.items.map((i) => [i.id, i]));
  const titres = new Map(corpus.items.map((i) => [i.id, i.title]));
  const episodes = new Map(corpus.episodes.map((e) => [e.guid, e]));
  const vignette = (a: Ajout): Vignette<F> => ({
    item: fiches.get(a.itemId) as F,
    detail: episodeLabel((a.episodeGuid && episodes.get(a.episodeGuid)) || {}),
  });
  const musique = plusRecentesParFiche(mentionsMusicales(fiches, corpus.mentions, corpus.recos), episodes, titres)
    .slice(0, combien.musique)
    .map(vignette);
  // Une fiche n'a de page que si l'une de ses mentions est visible
  // (cf. `oeuvreDesRecos.ts`) : on ne lie que celles-là.
  const visibles = corpus.mentions.filter((m) => m.status !== 'discarded' && fiches.has(m.itemId));
  const recentes = new Map(plusRecentesParFiche(visibles, episodes, titres).map((a) => [a.itemId, a]));
  const listes = new Map(genres.map((g) => [g.genre, premieresDeLaListe(g.oeuvres, recentes, combien.liste).map(vignette)]));
  return { musique, listes };
}

/** Vrai si l'épisode a fait entrer au moins une fiche dans les playlists. */
export function episodeAMusique<F extends FicheAjout>(
  corpus: Pick<Corpus<F & { title: string }>, 'items' | 'mentions' | 'recos'>,
  episodeGuid: string,
): boolean {
  const fiches = new Map(corpus.items.map((i) => [i.id, i as FicheAjout]));
  const duJour = corpus.mentions.filter((m) => m.sourceRef.episodeGuid === episodeGuid);
  return mentionsMusicales(fiches, duJour, corpus.recos).length > 0;
}
