/**
 * Invariants du catalogue public (ADR 0061).
 *
 * Une seule implémentation, sans dépendance : la CI l'appelle aujourd'hui par
 * `scripts/verifier-corpus.ts` ; le constructeur des publications et le
 * contrôle des sauvegardes l'appelleront ensuite. Le module compte, vérifie et
 * classe. Il n'écrit jamais rien.
 *
 * Trois règles bloquantes de l'ADR 0061 portent sur des données que le corpus
 * n'a pas encore : l'épisode retiré mais public (le registre des retraits), la
 * clé et le rang des liens d'une œuvre, le nom d'une vignette. Elles arrivent
 * avec ces données.
 *
 * Classes d'écart entre une reco et sa mention ou son œuvre (ADR 0055) :
 * - C1 : la même chose écrite autrement (deux formes d'une même URL) ;
 * - C2 : une seule des deux copies porte la valeur ;
 * - C3 : deux valeurs différentes.
 *
 * Deux différences de pure représentation qu'imposent les schémas actuels ne
 * sont pas comptées : `tmdb` en texte sur la reco et en nombre sur l'œuvre,
 * `kind` absent qui vaut `reco`. La normalisation les effacera. `02` § 3.2 les
 * range pourtant en C1, « correction automatique et comptée » : cet écart avec
 * la documentation est soumis à l'éditeur le 3 novembre, et le code ne change
 * qu'après sa réponse.
 */

import { canoniserUrl, classerLiens } from './liens.ts';

export type Json = Record<string, unknown>;

/** Un fichier lu : ses données, ou l'erreur qui a empêché de les lire. */
export interface Entree {
  chemin: string;
  donnees?: Json;
  erreur?: string;
}

export const COLLECTIONS = ['sources', 'episodes', 'recos', 'items', 'mentions'] as const;
export type Collection = (typeof COLLECTIONS)[number];

export interface Corpus {
  sources: Entree[];
  episodes: Entree[];
  recos: Entree[];
  items: Entree[];
  mentions: Entree[];
  /** Ancienne adresse → nouvelle adresse (`redirections-oeuvres.json`). */
  redirections: Record<string, unknown>;
  erreurRedirections?: string;
}

export type Classe = 'C1' | 'C2' | 'C3';

export interface Ecart {
  /** Identifiant de la reco, ou de l'œuvre pour le champ `liens`. */
  id: string;
  champ: string;
  classe: Classe;
}

export interface Violation {
  regle: string;
  message: string;
  ids: string[];
}

export interface ComptesCollection {
  fichiers: number;
  idsDistincts: number;
  /** Identifiant → fichiers qui le portent. Le premier, par ordre de chemin, est celui qui est analysé. */
  doublons: Record<string, string[]>;
  erreurs: { chemin: string; erreur: string }[];
  sansId: string[];
}

export interface ResumeChamp {
  total: number;
  C1: number;
  C2: number;
  C3: number;
}

/** Classement des liens des œuvres citées par au moins deux recos validées. */
export interface ResumeLiens {
  oeuvresMultiRecos: number;
  identiques: number;
  inclus: number;
  complementaires: number;
  memeLibelleUrlDifferentes: number;
}

export interface Rapport {
  comptes: Record<Collection, ComptesCollection>;
  statuts: { recos: Record<string, number>; mentions: Record<string, number> };
  orphelins: {
    mentionSansOeuvre: string[];
    mentionSansEpisode: string[];
    recoSansEpisode: string[];
    recoSansMention: Record<string, number>;
    mentionSansReco: Record<string, number>;
    oeuvreSansMention: string[];
  };
  bloquants: Violation[];
  avertissements: Violation[];
  ecarts: Ecart[];
  resumeEcarts: Record<string, ResumeChamp>;
  /** Recos validées sans écart sur les neuf champs comparés à leur mention ou à leur œuvre. */
  recosValideesSansEcart: number;
  liens: ResumeLiens;
}

/** Champs de la reco comparés à sa mention ou à son œuvre (hors `externalIds`, liens et alias). */
export const CHAMPS_COMPARES = [
  'title',
  'creator',
  'types',
  'year',
  'recommendedBy',
  'quote',
  'timestamp',
  'kind',
  'guestWork',
] as const;

/**
 * Formats fermés des identifiants (ADR 0058), ceux de `src/content.config.ts`
 * pour la source, l'œuvre et la mention. L'identifiant d'une reco est celui de
 * sa citation : il suit le format de la mention.
 */
export const FORMATS = {
  source: /^[a-z0-9]+(?:-[a-z0-9]+)*$/,
  episode: /^[A-Za-z0-9._~-]{1,300}$/,
  oeuvre: /^[a-z0-9-]{1,64}$/,
  citation: /^[a-z0-9-]{1,64}$/,
} as const;

const vide = (v: unknown): boolean => v === undefined || v === null || v === '';
const texte = (v: unknown): string | undefined => (typeof v === 'string' && v !== '' ? v : undefined);
const estObjet = (v: unknown): v is Json => v !== null && typeof v === 'object' && !Array.isArray(v);
const objet = (v: unknown): Json => (estObjet(v) ? v : {});

/**
 * Règle C (`05`, 3 novembre) : la forme attendue de chaque champ que l'analyse
 * lit. Une valeur d'une autre forme est rapportée, au lieu d'être lue comme
 * absente ou comme une valeur par défaut (un `guestWork` à `'true'` passerait
 * pour faux).
 */
type Forme = 'texte' | 'nombre' | 'vrai' | 'textes' | 'statut' | 'kind' | 'ids' | 'liens' | 'sourceRef';
const FORMES: Record<'recos' | 'items' | 'mentions', Record<string, Forme>> = {
  recos: {
    status: 'statut', episodeGuid: 'texte', title: 'texte', creator: 'texte', types: 'textes', year: 'nombre',
    recommendedBy: 'texte', quote: 'texte', timestamp: 'texte', kind: 'kind', guestWork: 'vrai',
    aliases: 'textes', externalIds: 'ids', links: 'liens',
  },
  items: { title: 'texte', creator: 'texte', types: 'textes', year: 'nombre', aliases: 'textes', externalIds: 'ids' },
  mentions: {
    status: 'statut', itemId: 'texte', sourceRef: 'sourceRef', recommendedBy: 'texte', quote: 'texte',
    kind: 'kind', guestWork: 'vrai',
  },
};

const estTexte = (v: unknown): boolean => typeof v === 'string';
const estNombre = (v: unknown): boolean => typeof v === 'number' && Number.isFinite(v);

function bienForme(forme: Forme, v: unknown): boolean {
  switch (forme) {
    case 'texte':
      return estTexte(v);
    case 'nombre':
      return estNombre(v);
    case 'vrai': // R-V3 : un drapeau vaut vrai, ou il est absent.
      return v === true;
    case 'textes':
      return Array.isArray(v) && v.every(estTexte);
    case 'statut':
      return v === 'draft' || v === 'validated' || v === 'discarded';
    case 'kind':
      return v === 'reco' || v === 'citation';
    case 'ids':
      return estObjet(v) && Object.values(v).every((x) => estTexte(x) || estNombre(x));
    case 'liens':
      return Array.isArray(v) && v.every((l) => estObjet(l) && estTexte(l.url) && (l.label === undefined || estTexte(l.label)));
    case 'sourceRef':
      return estObjet(v) && [v.episodeGuid, v.timestamp].every((x) => x === undefined || estTexte(x));
  }
}
const statutDe = (d: Json): string => texte(d.status) ?? 'draft';
const parOrdre = (a: string, b: string): number => (a < b ? -1 : a > b ? 1 : 0);

/** C2 si une seule valeur existe, C3 si les deux diffèrent, rien sinon. */
export function classer(
  a: unknown,
  b: unknown,
  egaux: (x: unknown, y: unknown) => boolean = (x, y) => x === y,
): Classe | null {
  const va = vide(a);
  const vb = vide(b);
  if (va && vb) return null;
  if (va || vb) return 'C2';
  return egaux(a, b) ? null : 'C3';
}

/** Deux listes de types égales à l'ordre près. Un `types` qui n'est pas une liste est comparé tel quel : l'écart est rapporté, l'analyse ne s'arrête pas. */
const memesTypes = (x: unknown, y: unknown): boolean =>
  Array.isArray(x) && Array.isArray(y)
    ? JSON.stringify([...x].sort()) === JSON.stringify([...y].sort())
    : JSON.stringify(x) === JSON.stringify(y);

// --- Analyse --------------------------------------------------------------------------

interface Index {
  parId: Map<string, Json>;
  comptes: ComptesCollection;
}

function indexer(entrees: Entree[], cle: (d: Json) => unknown): Index {
  const tries = [...entrees].sort((a, b) => parOrdre(a.chemin, b.chemin));
  const chemins = new Map<string, string[]>();
  const parId = new Map<string, Json>();
  const comptes: ComptesCollection = { fichiers: tries.length, idsDistincts: 0, doublons: {}, erreurs: [], sansId: [] };
  for (const e of tries) {
    if (e.donnees === undefined) {
      comptes.erreurs.push({ chemin: e.chemin, erreur: e.erreur ?? 'illisible' });
      continue;
    }
    const id = texte(cle(e.donnees));
    if (id === undefined) {
      comptes.sansId.push(e.chemin);
      continue;
    }
    chemins.set(id, [...(chemins.get(id) ?? []), e.chemin]);
    if (!parId.has(id)) parId.set(id, e.donnees);
  }
  comptes.idsDistincts = parId.size;
  for (const [id, fichiers] of chemins) if (fichiers.length > 1) comptes.doublons[id] = fichiers;
  return { parId, comptes };
}

function compter(valeurs: Iterable<string>): Record<string, number> {
  const c: Record<string, number> = {};
  for (const v of valeurs) c[v] = (c[v] ?? 0) + 1;
  return c;
}

const ADRESSE_OEUVRE = /^\/([^/]+)\/oeuvre\/([^/]+)$/;

/** Une adresse d'œuvre dont la source et l'œuvre suivent leur format fermé. */
function oeuvreDeAdresse(adresse: unknown): string | null {
  const m = typeof adresse === 'string' ? adresse.match(ADRESSE_OEUVRE) : null;
  return m !== null && FORMATS.source.test(m[1]) && FORMATS.oeuvre.test(m[2]) ? m[2] : null;
}

export function analyser(corpus: Corpus): Rapport {
  const sources = indexer(corpus.sources, (d) => d.id);
  const episodes = indexer(corpus.episodes, (d) => d.guid);
  const recos = indexer(corpus.recos, (d) => d.id);
  const items = indexer(corpus.items, (d) => d.id);
  const mentions = indexer(corpus.mentions, (d) => d.id);

  const bloquants: Violation[] = [];
  const avertissements: Violation[] = [];
  const signaler = (liste: Violation[], regle: string, message: string, ids: string[]): void => {
    if (ids.length > 0) liste.push({ regle, message, ids: [...new Set(ids)].sort(parOrdre) });
  };

  // Lecture et identifiants.
  const collections = { sources, episodes, recos, items, mentions };
  for (const [nom, ix] of Object.entries(collections)) {
    signaler(bloquants, 'lecture', `${nom} : fichier illisible`, ix.comptes.erreurs.map((e) => e.chemin));
    signaler(bloquants, 'sans-id', `${nom} : fichier sans identifiant`, ix.comptes.sansId);
    signaler(bloquants, 'doublon', `${nom} : identifiant porté par plusieurs fichiers`, Object.keys(ix.comptes.doublons));
  }
  const formats: [string, Index, RegExp][] = [
    ['sources', sources, FORMATS.source],
    ['episodes', episodes, FORMATS.episode],
    ['recos', recos, FORMATS.citation],
    ['items', items, FORMATS.oeuvre],
    ['mentions', mentions, FORMATS.citation],
  ];
  for (const [nom, ix, format] of formats) {
    signaler(bloquants, 'format-identifiant', `${nom} : identifiant hors de son format fermé`, [...ix.parId.keys()].filter((id) => !format.test(id)));
  }

  // Règle C : un champ d'une autre forme que celle attendue est bloquant ; un
  // champ présent mais vide (R-V6) ou `null` (R-V1) est signalé.
  const malFormes: string[] = [];
  const videsOuNull: string[] = [];
  const formes: ['recos' | 'items' | 'mentions', Index][] = [['recos', recos], ['items', items], ['mentions', mentions]];
  for (const [nom, ix] of formes) {
    for (const [id, d] of ix.parId) {
      for (const [champ, forme] of Object.entries(FORMES[nom])) {
        if (!(champ in d)) continue;
        const v = d[champ];
        if (v === null || v === '') videsOuNull.push(`${nom}:${id}.${champ}`);
        else if (!bienForme(forme, v)) malFormes.push(`${nom}:${id}.${champ}`);
      }
    }
  }
  signaler(bloquants, 'type-champ', 'champ d’une autre forme que celle attendue', malFormes);
  signaler(avertissements, 'valeur-vide', 'champ présent mais vide ou null, à retirer (R-V1, R-V6)', videsOuNull);
  if (corpus.erreurRedirections !== undefined) {
    bloquants.push({ regle: 'lecture', message: `redirections illisibles : ${corpus.erreurRedirections}`, ids: [] });
  }

  // Orphelins.
  const episodeDeMention = (m: Json): string | undefined => texte(objet(m.sourceRef).episodeGuid);
  const mentionSansOeuvre: string[] = [];
  const mentionSansEpisode: string[] = [];
  const recoSansEpisode: string[] = [];
  const mentionsParOeuvre = new Map<string, Json[]>();
  for (const [id, m] of mentions.parId) {
    const itemId = texte(m.itemId);
    if (itemId === undefined || !items.parId.has(itemId)) mentionSansOeuvre.push(id);
    else mentionsParOeuvre.set(itemId, [...(mentionsParOeuvre.get(itemId) ?? []), m]);
    const guid = episodeDeMention(m);
    if (guid === undefined || !episodes.parId.has(guid)) mentionSansEpisode.push(id);
  }
  for (const [id, r] of recos.parId) {
    const guid = texte(r.episodeGuid);
    if (guid === undefined || !episodes.parId.has(guid)) recoSansEpisode.push(id);
  }
  const recoSansMention = [...recos.parId].filter(([id]) => !mentions.parId.has(id));
  const mentionSansReco = [...mentions.parId].filter(([id]) => !recos.parId.has(id));
  const oeuvreSansMention = [...items.parId.keys()].filter((id) => !mentionsParOeuvre.has(id));

  signaler(bloquants, 'mention-oeuvre-absente', 'mention dont l’œuvre n’existe pas', mentionSansOeuvre);
  signaler(bloquants, 'mention-episode-absent', 'mention dont l’épisode n’existe pas', mentionSansEpisode);
  signaler(bloquants, 'reco-episode-absent', 'reco dont l’épisode n’existe pas', recoSansEpisode);
  signaler(
    avertissements,
    'reco-validee-sans-mention',
    'reco validée sans mention : la carte existe, la fiche ne la compte pas',
    recoSansMention.filter(([, r]) => statutDe(r) === 'validated').map(([id]) => id),
  );
  signaler(avertissements, 'oeuvre-sans-mention', 'œuvre qu’aucune mention ne cite', oeuvreSansMention);

  // Statuts.
  const ecartStatut: string[] = [];
  for (const [id, r] of recos.parId) {
    const m = mentions.parId.get(id);
    if (m !== undefined && (statutDe(r) === 'validated') !== (statutDe(m) === 'validated')) ecartStatut.push(id);
  }
  signaler(avertissements, 'ecart-statut', 'reco et mention de statuts différents (une seule est validée)', ecartStatut);

  // Brouillons publics (ADR 0061 ; « brouillons : jamais publics », `02` § 6) :
  // le site affiche toute mention qui n'est pas écartée.
  signaler(
    bloquants,
    'brouillon-public',
    'mention en brouillon, donc visible sur les fiches',
    [...mentions.parId].filter(([, m]) => statutDe(m) === 'draft').map(([id]) => id),
  );

  // `recommendedBy` appartient à la mention, jamais à l'œuvre (ADR 0061 ; `02`
  // § 2.1 : « absent de l'œuvre ») : la clé seule suffit, vide ou `null` compris.
  signaler(
    bloquants,
    'recommendedBy-sur-oeuvre',
    'œuvre qui porte un recommendedBy (champ de mention)',
    [...items.parId].filter(([, it]) => 'recommendedBy' in it).map(([id]) => id),
  );

  // Redirections.
  const visibles = new Set(
    [...mentionsParOeuvre].filter(([, ms]) => ms.some((m) => statutDe(m) !== 'discarded')).map(([id]) => id),
  );
  const formatInvalide: string[] = [];
  const sourcesRedir = new Map<string, string>();
  for (const [de, vers] of Object.entries(corpus.redirections)) {
    const a = oeuvreDeAdresse(de);
    const b = oeuvreDeAdresse(vers);
    if (a === null || b === null) formatInvalide.push(de);
    else sourcesRedir.set(a, b);
  }
  signaler(bloquants, 'redirection-format', 'redirection qui ne relie pas deux adresses d’œuvre au format fermé', formatInvalide);
  const sourceAvecPage: string[] = [];
  const sourceSansPage: string[] = [];
  const cibleAbsente: string[] = [];
  const cibleSansPage: string[] = [];
  const chaine: string[] = [];
  for (const [de, vers] of sourcesRedir) {
    if (items.parId.has(de)) (visibles.has(de) ? sourceAvecPage : sourceSansPage).push(de);
    if (!items.parId.has(vers)) cibleAbsente.push(vers);
    else if (!visibles.has(vers)) cibleSansPage.push(vers);
    // ADR 0053 : une chaîne A → B → C est raccourcie, une cible n'est donc jamais redirigée.
    if (sourcesRedir.has(vers)) chaine.push(de);
  }
  signaler(bloquants, 'redirection-source-vivante-avec-page', 'redirection depuis une œuvre vivante qui a une page : la page serait masquée', sourceAvecPage);
  signaler(bloquants, 'redirection-chaine', 'redirection vers une adresse elle-même redirigée', chaine);
  signaler(avertissements, 'redirection-source-vivante-sans-page', 'redirection depuis une œuvre vivante sans page', sourceSansPage);
  signaler(avertissements, 'redirection-cible-absente', 'redirection vers une œuvre qui n’existe pas', cibleAbsente);
  signaler(avertissements, 'redirection-cible-sans-page', 'redirection vers une œuvre sans page (404)', cibleSansPage);

  // Écarts entre chaque reco validée et sa mention ou son œuvre.
  const ecarts: Ecart[] = [];
  const recosParOeuvre = new Map<string, Json[]>();
  let sansEcart = 0;
  for (const [id, r] of [...recos.parId].sort(([a], [b]) => parOrdre(a, b))) {
    const m = mentions.parId.get(id);
    if (statutDe(r) !== 'validated' || m === undefined) continue;
    const itemId = texte(m.itemId) ?? '';
    const it = items.parId.get(itemId);
    const ajouter = (champ: string, classe: Classe | null): void => {
      if (classe !== null) ecarts.push({ id, champ, classe });
    };
    const avant = ecarts.length;
    const sr = objet(m.sourceRef);
    if (it !== undefined) {
      recosParOeuvre.set(itemId, [...(recosParOeuvre.get(itemId) ?? []), r]);
      ajouter('title', classer(r.title, it.title));
      ajouter('creator', classer(r.creator, it.creator));
      ajouter('types', classer(r.types, it.types, memesTypes));
      ajouter('year', classer(r.year, it.year));
    }
    ajouter('recommendedBy', classer(r.recommendedBy, m.recommendedBy));
    ajouter('quote', classer(r.quote, m.quote));
    ajouter('timestamp', classer(r.timestamp, sr.timestamp));
    // Le schéma lit un `kind` absent comme `reco` (`.default('reco')`) ; R-V5
    // (`02` § 3.1) veut qu'il soit toujours écrit, ce que fera la normalisation.
    ajouter('kind', (texte(r.kind) ?? 'reco') === (texte(m.kind) ?? 'reco') ? null : 'C3');
    // R-V3 (`02` § 3.1) : un drapeau absent vaut faux. Vrai sur une copie et absent
    // sur l'autre, ce sont donc deux valeurs différentes, C3, et non une valeur
    // présente d'un seul côté (C2) : c'est l'attendu du cas d'essai F1 (`02` § 10).
    // Les 197 écarts du corpus (`02` § 2.2) sont de cette forme.
    ajouter('guestWork', (r.guestWork === true) === (m.guestWork === true) ? null : 'C3');
    if (ecarts.length === avant) sansEcart += 1;
    if (it === undefined) continue;

    const aliasOeuvre = new Set(Array.isArray(it.aliases) ? it.aliases : []);
    if (Array.isArray(r.aliases) && r.aliases.some((a) => !aliasOeuvre.has(a))) ajouter('aliases', 'C2');

    const er = objet(r.externalIds);
    const ei = objet(it.externalIds);
    for (const cle of [...new Set([...Object.keys(er), ...Object.keys(ei)])].sort(parOrdre)) {
      const a = er[cle];
      const b = ei[cle];
      let classe: Classe | null;
      // R-V7 (`02` § 3.1) : `tmdb` est un entier, en texte sur la reco aujourd'hui.
      // `02` § 3.2 range « texte ou nombre » en C1, correction comptée ; ce
      // vérificateur ne la compte pas encore (voir l'en-tête).
      if (cle === 'tmdb') classe = classer(a, b, (x, y) => String(x) === String(y));
      // `02` § 4.6 : les 4 `watchPage` différentes sont toutes équivalentes (C1).
      else if (cle === 'watchPage') {
        classe = classer(a, b);
        if (classe === 'C3' && canoniserUrl(String(a)) === canoniserUrl(String(b))) classe = 'C1';
      } else classe = classer(a, b);
      ajouter(`externalIds.${cle}`, classe);
    }
  }

  // Liens des œuvres citées par au moins deux recos validées.
  const liens: ResumeLiens = { oeuvresMultiRecos: 0, identiques: 0, inclus: 0, complementaires: 0, memeLibelleUrlDifferentes: 0 };
  for (const [itemId, rs] of [...recosParOeuvre].sort(([a], [b]) => parOrdre(a, b))) {
    if (rs.length < 2) continue;
    liens.oeuvresMultiRecos += 1;
    const ids = new Set(
      [items.parId.get(itemId), ...rs]
        .map((d) => texte(objet(objet(d).externalIds).youtubeChannelId))
        .filter((v): v is string => v !== undefined),
    );
    const { brut, classe } = classerLiens(rs, ids);
    liens[brut] += 1;
    if (classe !== null) ecarts.push({ id: itemId, champ: 'liens', classe });
  }

  const resumeEcarts: Record<string, ResumeChamp> = {};
  for (const e of ecarts) {
    const r = (resumeEcarts[e.champ] ??= { total: 0, C1: 0, C2: 0, C3: 0 });
    r.total += 1;
    r[e.classe] += 1;
  }

  return {
    comptes: {
      sources: sources.comptes,
      episodes: episodes.comptes,
      recos: recos.comptes,
      items: items.comptes,
      mentions: mentions.comptes,
    },
    statuts: {
      recos: compter([...recos.parId.values()].map(statutDe)),
      mentions: compter([...mentions.parId.values()].map(statutDe)),
    },
    orphelins: {
      mentionSansOeuvre: mentionSansOeuvre.sort(parOrdre),
      mentionSansEpisode: mentionSansEpisode.sort(parOrdre),
      recoSansEpisode: recoSansEpisode.sort(parOrdre),
      recoSansMention: compter(recoSansMention.map(([, r]) => statutDe(r))),
      mentionSansReco: compter(mentionSansReco.map(([, m]) => statutDe(m))),
      oeuvreSansMention: oeuvreSansMention.sort(parOrdre),
    },
    bloquants,
    avertissements,
    ecarts: ecarts.sort((a, b) => parOrdre(a.id, b.id) || parOrdre(a.champ, b.champ)),
    resumeEcarts,
    recosValideesSansEcart: sansEcart,
    liens,
  };
}
