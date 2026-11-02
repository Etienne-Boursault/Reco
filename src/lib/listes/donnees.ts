/**
 * src/lib/listes/donnees.ts — les playlists et les listes SensCritique d'une source.
 *
 * D'OÙ VIENNENT LES DONNÉES
 * -------------------------
 * Le site ne saisit rien à la main : il relit, au build, l'état que tiennent
 * les outils de publication (`tools/reseaux_episode.py`, skill
 * `reseaux-episode`) après chaque épisode.
 *  - `tools/data/playlists_spotify.json` et `playlists_deezer.json` : nom de
 *    la playlist (« Toutes les recos musicales », « Saison 6 »…) → `{id, titres}`.
 *    Le nombre affiché est la longueur de `titres`.
 *  - `tools/data/senscritique.json` : `listes.{film,serie,livre,bd}` → `url`
 *    et `ajoutees`, les fiches du site réellement présentes dans la liste, de
 *    la plus récente à la plus ancienne. `traitees` est ignoré : il compte
 *    aussi les œuvres que SensCritique n'a pas trouvées.
 *
 * Ces fichiers ne valent que pour une source — ils ne nomment pas le podcast,
 * et le site est multi-source (« une source = un podcast »). La table
 * `FICHIERS_PAR_SOURCE` dit donc quelle source les possède : une source qui
 * n'y figure pas n'a ni page « Listes et playlists » ni accès vers elle.
 *
 * Les fichiers sont une frontière du système : tout ce qui n'a pas la forme
 * attendue est écarté plutôt que rendu (un lien construit sur un identifiant
 * inattendu mènerait n'importe où).
 */
import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';

/** Les quatre listes SensCritique, dans l'ordre de la page. */
export const GENRES = ['film', 'serie', 'livre', 'bd'] as const;
export type Genre = (typeof GENRES)[number];

/** Nom de la playlist qui cumule toutes les saisons (cf. `tools/playlists_musique.py`). */
export const NOM_TOUTES = 'Toutes les recos musicales';

interface Fichiers {
  spotify: string;
  deezer: string;
  senscritique: string;
}

/** Les sources qui ont des listes, et où les lire (chemins relatifs à la racine). */
export const FICHIERS_PAR_SOURCE: Readonly<Record<string, Fichiers>> = {
  'un-bon-moment': {
    spotify: 'tools/data/playlists_spotify.json',
    deezer: 'tools/data/playlists_deezer.json',
    senscritique: 'tools/data/senscritique.json',
  },
};

export interface Playlist {
  /** Nom tel que publié : « Toutes les recos musicales », « Saison 6 ». */
  nom: string;
  /** Numéro de saison ; `null` pour la playlist qui cumule tout. */
  saison: number | null;
  spotify: string;
  deezer: string;
  /** Nombre de titres sur chaque plateforme (ils peuvent diverger un temps). */
  titres: { spotify: number; deezer: number };
}

export interface ListeSensCritique {
  genre: Genre;
  url: string;
  /** Identifiants des fiches du site présentes dans la liste, récentes d'abord. */
  oeuvres: string[];
}

export interface Listes {
  toutes: Playlist | null;
  /** Les saisons présentes sur les DEUX plateformes, de la plus récente à la plus ancienne. */
  saisons: Playlist[];
  senscritique: ListeSensCritique[];
}

type Brut = Record<string, unknown>;

function objet(valeur: unknown): Brut | null {
  return valeur && typeof valeur === 'object' && !Array.isArray(valeur) ? (valeur as Brut) : null;
}

/** `{id, titres}` d'une playlist, ou `null` si l'entrée n'a pas la forme attendue. */
function entreePlaylist(valeur: unknown): { id: string; titres: number } | null {
  const e = objet(valeur);
  const id = e && (typeof e.id === 'string' || typeof e.id === 'number') ? String(e.id) : '';
  if (!e || !/^[A-Za-z0-9]+$/.test(id) || !Array.isArray(e.titres)) return null;
  return { id, titres: e.titres.length };
}

function saisonDuNom(nom: string): number | null | undefined {
  if (nom === NOM_TOUTES) return null;
  const m = /^Saison (\d+)$/.exec(nom);
  return m ? Number(m[1]) : undefined;
}

/**
 * Les playlists présentes sur Spotify ET sur Deezer.
 *
 * Une playlist qui n'existe que d'un côté n'est pas montrée : le visiteur
 * attend les deux boutons, et un seul trahirait un état de publication
 * intermédiaire. Les noms inconnus (l'ancienne « Saisons 1 à 4 ») sont ignorés.
 */
export function lirePlaylists(
  spotify: unknown,
  deezer: unknown,
): { toutes: Playlist | null; saisons: Playlist[] } {
  const ps = objet(objet(spotify)?.playlists) ?? {};
  const pd = objet(objet(deezer)?.playlists) ?? {};
  let toutes: Playlist | null = null;
  const saisons: Playlist[] = [];
  for (const nom of Object.keys(ps)) {
    const saison = saisonDuNom(nom);
    const s = entreePlaylist(ps[nom]);
    const d = entreePlaylist(pd[nom]);
    if (saison === undefined || !s || !d) continue;
    const p: Playlist = {
      nom,
      saison,
      spotify: `https://open.spotify.com/playlist/${s.id}`,
      deezer: `https://www.deezer.com/fr/playlist/${d.id}`,
      titres: { spotify: s.titres, deezer: d.titres },
    };
    if (saison === null) toutes = p;
    else saisons.push(p);
  }
  saisons.sort((a, b) => (b.saison as number) - (a.saison as number));
  return { toutes, saisons };
}

/** Les listes SensCritique valides, dans l'ordre de `GENRES`. */
export function lireSensCritique(senscritique: unknown): ListeSensCritique[] {
  const listes = objet(objet(senscritique)?.listes) ?? {};
  const out: ListeSensCritique[] = [];
  for (const genre of GENRES) {
    const l = objet(listes[genre]);
    const url = typeof l?.url === 'string' ? l.url : '';
    if (!l || !url.startsWith('https://www.senscritique.com/liste/') || !Array.isArray(l.ajoutees)) continue;
    const oeuvres = l.ajoutees.filter((id): id is string => typeof id === 'string');
    out.push({ genre, url, oeuvres });
  }
  return out;
}

function lireJson(chemin: string): unknown {
  if (!existsSync(chemin)) return null;
  try {
    return JSON.parse(readFileSync(chemin, 'utf-8'));
  } catch {
    return null;
  }
}

/** Le pied de page lit les listes sur chacune des ~2 700 pages : une lecture par build suffit. */
const cache = new Map<string, Listes | null>();

/**
 * Les listes d'une source, ou `null` si elle n'en a aucune.
 *
 * @param racine Racine du dépôt (les tests passent un dossier de fixtures).
 */
export function chargerListes(sourceId: string | undefined, racine: string = process.cwd()): Listes | null {
  const fichiers = sourceId ? FICHIERS_PAR_SOURCE[sourceId] : undefined;
  if (!fichiers) return null;
  const cle = `${racine}|${sourceId}`;
  if (cache.has(cle)) return cache.get(cle) ?? null;
  const { toutes, saisons } = lirePlaylists(
    lireJson(join(racine, fichiers.spotify)),
    lireJson(join(racine, fichiers.deezer)),
  );
  const senscritique = lireSensCritique(lireJson(join(racine, fichiers.senscritique)));
  const listes = toutes || saisons.length > 0 || senscritique.length > 0 ? { toutes, saisons, senscritique } : null;
  cache.set(cle, listes);
  return listes;
}

/** Vide le cache (tests). */
export function viderCacheListes(): void {
  cache.clear();
}

/** Nombre de listes affichées : une playlist compte une fois pour ses deux plateformes. */
export function nombreDeListes(listes: Listes): number {
  return (listes.toutes ? 1 : 0) + listes.saisons.length + listes.senscritique.length;
}

/**
 * La playlist où ranger la musique d'un épisode : celle de sa saison, sinon
 * celle qui cumule tout. Un hors-série n'a pas de saison dans les données.
 */
export function playlistDeLaSaison(listes: Listes, saison: number | null | undefined): Playlist | null {
  return listes.saisons.find((p) => p.saison === saison) ?? listes.toutes;
}

/** La liste SensCritique d'un genre, si elle existe. */
export function listeDuGenre(listes: Listes, genre: Genre): ListeSensCritique | undefined {
  return listes.senscritique.find((l) => l.genre === genre);
}
