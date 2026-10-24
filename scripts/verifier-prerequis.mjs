#!/usr/bin/env node
/**
 * Vérifie qu'aucune décision en attente ne bloque une PR de la V2.
 *
 *   node scripts/verifier-prerequis.mjs <PR> [--sortie] [--fichier <decisions.json>]
 *
 * Une décision `bloquant` bloque sa première PR et toutes celles qui en
 * dépendent dans `graphe`. Une décision marquée `"moment": "sortie"` ne bloque
 * sa propre PR qu'à la fusion (`--sortie`), mais bloque ses descendantes dès
 * le début. `tranché` et `différé` ne bloquent jamais.
 *
 * Code de sortie : 0 prérequis remplis, 1 décision bloquante, 2 erreur d'usage.
 */
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

export const FICHIER_PAR_DEFAUT = fileURLToPath(new URL('../docs/v2/decisions.json', import.meta.url));

/** Ensemble des PR dont `pr` dépend, directement ou non. */
export function ancetres(graphe, pr) {
  if (!(pr in graphe)) throw new Error(`PR inconnue : ${pr}`);
  const vus = new Set();
  const pile = [...graphe[pr]];
  while (pile.length > 0) {
    const p = pile.pop();
    if (vus.has(p)) continue;
    if (!(p in graphe)) throw new Error(`PR inconnue dans le graphe : ${p}`);
    vus.add(p);
    pile.push(...graphe[p]);
  }
  return vus;
}

/** Décisions qui empêchent de commencer (ou, avec `sortie`, de fusionner) `pr`. */
export function bloquantes(donnees, pr, { sortie = false } = {}) {
  const amont = ancetres(donnees.graphe, pr);
  return donnees.decisions.filter((d) => {
    if (d.statut !== 'bloquant') return false;
    if (amont.has(d.premierePR)) return true;
    return d.premierePR === pr && (d.moment !== 'sortie' || sortie);
  });
}

function principal(argv) {
  const args = argv.slice(2);
  const sortie = args.includes('--sortie');
  const iFichier = args.indexOf('--fichier');
  const iValeur = iFichier >= 0 ? iFichier + 1 : -1;
  const fichier = iFichier >= 0 ? args[iValeur] : FICHIER_PAR_DEFAUT;
  const pr = args.find((a, i) => !a.startsWith('--') && i !== iValeur);
  if (!pr || !fichier) {
    console.error('usage : node scripts/verifier-prerequis.mjs <PR> [--sortie] [--fichier <decisions.json>]');
    return 2;
  }
  const donnees = JSON.parse(readFileSync(fichier, 'utf8'));
  let liste;
  try {
    liste = bloquantes(donnees, pr, { sortie });
  } catch (erreur) {
    console.error(erreur.message);
    return 2;
  }
  if (liste.length === 0) {
    console.log(`${pr} : prérequis remplis.`);
    return 0;
  }
  console.log(`${pr} : bloquée par ${liste.length} décision(s) en attente :`);
  for (const d of liste) console.log(`- ${d.id} — ${d.sujet} (première PR bloquée : ${d.premierePR})`);
  return 1;
}

const lanceDirectement =
  process.argv[1] !== undefined &&
  resolve(process.argv[1]).toLowerCase() === fileURLToPath(import.meta.url).toLowerCase();
if (lanceDirectement) process.exitCode = principal(process.argv);
