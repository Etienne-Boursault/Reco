/**
 * Liens : règles d'équivalence d'URL, en liste fermée, et classement des liens des
 * œuvres citées par plusieurs recos (`docs/v2/contrats-canoniques.md` §4.5).
 */
import type { Classe, Json } from './invariants.ts';

const texte = (v: unknown): string | undefined => (typeof v === 'string' && v !== '' ? v : undefined);
const objet = (v: unknown): Json => (v !== null && typeof v === 'object' && !Array.isArray(v) ? (v as Json) : {});

// --- URL : règles d'équivalence, liste fermée ----------------------------------------

const parametreRetire = (nom: string): boolean => nom === 'hl' || nom === 'si' || nom.startsWith('utm_');

/** `?a=1&hl=fr` → `?a=1` ; une requête vide ou entièrement retirée → chaîne vide. */
function requeteNettoyee(requete: string): string {
  const gardes = requete
    .replace(/^\?/, '')
    .split('&')
    .filter((p) => {
      if (p === '') return false;
      let nom = p.split('=')[0];
      try {
        nom = decodeURIComponent(nom);
      } catch {
        // Encodage invalide : on garde le nom brut.
      }
      return !parametreRetire(nom);
    });
  return gardes.length > 0 ? `?${gardes.join('&')}` : '';
}

/** Retire `hl`, `si` et `utm_*` de la chaîne de requête, sans rien toucher d'autre. */
function sansParametresRetires(url: string): string {
  const diese = url.indexOf('#');
  const fragment = diese >= 0 ? url.slice(diese) : '';
  const avant = diese >= 0 ? url.slice(0, diese) : url;
  const q = avant.indexOf('?');
  if (q < 0) return url;
  return avant.slice(0, q) + requeteNettoyee(avant.slice(q)) + fragment;
}

/**
 * Forme canonique d'une URL selon la liste fermée de `contrats-canoniques.md` §4.5.
 * Aucune règle ne s'applique par ressemblance : une URL hors de ces plateformes ne
 * perd que ses paramètres `hl`, `si` et `utm_*`.
 */
export function canoniserUrl(url: string): string {
  let u: URL;
  try {
    u = new URL(url);
  } catch {
    return url;
  }
  const hote = u.hostname.toLowerCase();
  const chemin = u.pathname;
  const finSur = (domaine: string): boolean => hote === domaine || hote.endsWith(`.${domaine}`);
  let m: RegExpMatchArray | null;

  if (finSur('steampowered.com') && (m = chemin.match(/^\/app\/(\d+)(?:\/[^/]*)?\/?$/))) {
    return `https://store.steampowered.com/app/${m[1]}/`;
  }
  if (finSur('themoviedb.org') && (m = chemin.match(/^\/(movie|tv)\/(\d+)(?:-[^/]*)?(\/.*)?$/))) {
    return `https://www.themoviedb.org/${m[1]}/${m[2]}${m[3] ?? ''}${requeteNettoyee(u.search)}`;
  }
  if (finSur('deezer.com') && (m = chemin.match(/^(?:\/[a-z]{2}(?:-[a-z]{2})?)?\/(artist|album|track|playlist)\/(\d+)\/?$/))) {
    return `https://www.deezer.com/${m[1]}/${m[2]}`;
  }
  if (hote === 'open.spotify.com' && (m = chemin.match(/^(?:\/intl-[a-z]{2})?\/(artist|album|track|playlist|show|episode)\/([A-Za-z0-9]+)\/?$/))) {
    return `https://open.spotify.com/${m[1]}/${m[2]}`;
  }
  if (finSur('instagram.com') && (m = chemin.match(/^\/([A-Za-z0-9._]+)\/?$/))) {
    return `https://www.instagram.com/${m[1].toLowerCase()}/`;
  }
  if (finSur('youtube.com')) {
    if ((m = chemin.match(/^\/@([^/]+)\/?$/))) return `youtube:@${m[1].toLowerCase()}`;
    if ((m = chemin.match(/^\/channel\/(UC[\w-]+)\/?$/))) return `youtube:channel:${m[1]}`;
  }
  return sansParametresRetires(url);
}

// --- Liens des œuvres citées plusieurs fois -------------------------------------------

interface Lien {
  url: string;
  label: string;
}

function liensDe(reco: Json): Lien[] {
  const liste = Array.isArray(reco.links) ? reco.links : [];
  return liste
    .map(objet)
    .filter((l) => typeof l.url === 'string')
    .map((l) => ({ url: l.url as string, label: texte(l.label) ?? '' }));
}

const egaux = (a: Set<string>, b: Set<string>): boolean => a.size === b.size && [...a].every((x) => b.has(x));
const inclus = (a: Set<string>, b: Set<string>): boolean => [...a].every((x) => b.has(x));

export interface ClassementLiens {
  brut: 'identiques' | 'inclus' | 'complementaires' | 'memeLibelleUrlDifferentes';
  classe: Classe | null;
}

/**
 * Classe les liens d'une œuvre citée par plusieurs recos.
 *
 * `brut` compare les URL telles quelles (les quatre familles mesurées le
 * 24/10). `classe` applique les règles d'équivalence : une chaîne YouTube
 * `/channel/UC…` vaut la `@poignée` de l'œuvre seulement si cet `UC…` est
 * l'identifiant de chaîne enregistré pour l'œuvre ou l'une de ses recos, et
 * si l'œuvre n'a qu'une poignée.
 */
export function classerLiens(recos: Json[], idsChaine: Set<string>): ClassementLiens {
  const liens = recos.map(liensDe);
  const urls = liens.map((ls) => new Set(ls.map((l) => l.url)));
  const reference = urls[0] ?? new Set<string>();

  let brut: ClassementLiens['brut'];
  if (urls.every((e) => egaux(e, reference))) {
    brut = 'identiques';
  } else {
    const parLibelle = new Map<string, Set<string>>();
    for (const l of liens.flat()) parLibelle.set(l.label, (parLibelle.get(l.label) ?? new Set()).add(l.url));
    const union = new Set(urls.flatMap((e) => [...e]));
    if ([...parLibelle.values()].some((e) => e.size > 1)) brut = 'memeLibelleUrlDifferentes';
    else if (urls.some((e) => egaux(e, union))) brut = 'inclus';
    else brut = 'complementaires';
  }

  const poignees = new Set(
    liens.flat().map((l) => canoniserUrl(l.url)).filter((c) => c.startsWith('youtube:@')),
  );
  const poigneeUnique = poignees.size === 1 ? [...poignees][0] : undefined;
  const cle = (url: string): string => {
    const c = canoniserUrl(url);
    const chaine = c.startsWith('youtube:channel:') ? c.slice('youtube:channel:'.length) : undefined;
    return chaine !== undefined && poigneeUnique !== undefined && idsChaine.has(chaine) ? poigneeUnique : c;
  };
  const cles = liens.map((ls) => new Set(ls.map((l) => cle(l.url))));
  const premier = cles[0] ?? new Set<string>();
  if (cles.every((e) => egaux(e, premier))) return { brut, classe: brut === 'identiques' ? null : 'C1' };

  const parLibelle = new Map<string, Set<string>[]>();
  liens.forEach((ls) => {
    const ici = new Map<string, Set<string>>();
    for (const l of ls) ici.set(l.label, (ici.get(l.label) ?? new Set()).add(cle(l.url)));
    for (const [libelle, e] of ici) parLibelle.set(libelle, [...(parLibelle.get(libelle) ?? []), e]);
  });
  const contradiction = [...parLibelle.values()].some((ensembles) =>
    ensembles.some((a) => ensembles.some((b) => !inclus(a, b) && !inclus(b, a))),
  );
  return { brut, classe: contradiction ? 'C3' : 'C2' };
}
