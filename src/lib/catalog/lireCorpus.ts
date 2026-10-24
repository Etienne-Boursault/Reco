/**
 * Lit le corpus JSON tel que le site le charge, fichier par fichier.
 *
 * Chaque fichier est lu séparément : une erreur de lecture est rapportée,
 * jamais ignorée, et deux fichiers qui portent le même identifiant restent deux
 * entrées (l'analyse les liste comme doublons). Les dossiers que les chargeurs
 * de `src/content.config.ts` excluent (`__cross_stack_fixture__`) le sont ici
 * aussi : ce ne sont pas des données publiques.
 */
import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative, sep } from 'node:path';
import { COLLECTIONS } from './invariants.ts';
import type { Corpus, Entree, Json } from './invariants.ts';

export const DOSSIERS_EXCLUS: ReadonlySet<string> = new Set(['__cross_stack_fixture__']);
export const FICHIER_REDIRECTIONS = 'redirections-oeuvres.json';

function fichiersJson(dossier: string): string[] {
  if (!existsSync(dossier)) return [];
  const trouves: string[] = [];
  const entrees = readdirSync(dossier, { withFileTypes: true }).sort((a, b) => (a.name < b.name ? -1 : 1));
  for (const e of entrees) {
    const chemin = join(dossier, e.name);
    if (e.isDirectory()) {
      if (!DOSSIERS_EXCLUS.has(e.name)) trouves.push(...fichiersJson(chemin));
    } else if (e.name.endsWith('.json')) {
      trouves.push(chemin);
    }
  }
  return trouves;
}

function lireJson(chemin: string): { donnees?: Json; erreur?: string } {
  try {
    const valeur: unknown = JSON.parse(readFileSync(chemin, 'utf8'));
    if (valeur === null || typeof valeur !== 'object' || Array.isArray(valeur)) {
      return { erreur: 'le fichier ne contient pas un objet JSON' };
    }
    return { donnees: valeur as Json };
  } catch (e) {
    return { erreur: (e as Error).message };
  }
}

/** Lit `<contenu>/<collection>/**.json` et la table des redirections. */
export function lireCorpus(contenu: string): Corpus {
  if (!existsSync(contenu) || !statSync(contenu).isDirectory()) {
    throw new Error(`dossier de contenu introuvable : ${contenu}`);
  }
  const lire = (collection: string): Entree[] =>
    fichiersJson(join(contenu, collection)).map((chemin) => ({
      chemin: relative(contenu, chemin).split(sep).join('/'),
      ...lireJson(chemin),
    }));
  const [sources, episodes, recos, items, mentions] = COLLECTIONS.map(lire) as [
    Entree[],
    Entree[],
    Entree[],
    Entree[],
    Entree[],
  ];
  const corpus: Corpus = { sources, episodes, recos, items, mentions, redirections: {} };
  const fichier = join(contenu, FICHIER_REDIRECTIONS);
  if (existsSync(fichier)) {
    const { donnees, erreur } = lireJson(fichier);
    if (donnees !== undefined) corpus.redirections = donnees;
    else corpus.erreurRedirections = erreur;
  }
  return corpus;
}
