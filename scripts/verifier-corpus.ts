#!/usr/bin/env node
/**
 * Vérifie les invariants du corpus (ADR 0061), en lecture seule.
 *
 *   node scripts/verifier-corpus.ts [--contenu src/content]
 *                                   [--reference tests/fixtures/corpus/divergences-connues.json]
 *                                   [--sans-reference] [--json]
 *                                   [--ecrire-reference [--commit <sha>]]
 *
 * TypeScript exécuté tel quel par Node (≥ 22.18, ou 23.6), sans dépendance.
 *
 * Code de sortie : 0 aucun problème ; 1 invariant bloquant, fichier illisible
 * ou écart hors de la référence ; 2 erreur d'usage.
 * `--ecrire-reference` réécrit la référence datée avec les écarts du corpus :
 * à relire dans la PR qui la change.
 */
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { analyser } from '../src/lib/catalog/invariants.ts';
import { comparerReference, formaterReference, lireReference } from '../src/lib/catalog/reference.ts';
import type { Ecart, Rapport } from '../src/lib/catalog/invariants.ts';
import { lireCorpus } from '../src/lib/catalog/lireCorpus.ts';

const RACINE = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const REFERENCE_PAR_DEFAUT = resolve(RACINE, 'tests/fixtures/corpus/divergences-connues.json');
const CONTENU_PAR_DEFAUT = resolve(RACINE, 'src/content');

interface Options {
  contenu: string;
  reference: string;
  sansReference: boolean;
  json: boolean;
  ecrireReference: boolean;
  commit?: string;
}

function lireOptions(args: string[]): Options {
  const o: Options = {
    contenu: CONTENU_PAR_DEFAUT,
    reference: REFERENCE_PAR_DEFAUT,
    sansReference: false,
    json: false,
    ecrireReference: false,
  };
  for (let i = 0; i < args.length; i += 1) {
    const a = args[i];
    const valeur = (): string => {
      const v = args[i + 1];
      if (v === undefined || v.startsWith('--')) throw new Error(`${a} attend une valeur`);
      i += 1;
      return v;
    };
    if (a === '--contenu') o.contenu = resolve(valeur());
    else if (a === '--reference') o.reference = resolve(valeur());
    else if (a === '--commit') o.commit = valeur();
    else if (a === '--sans-reference') o.sansReference = true;
    else if (a === '--json') o.json = true;
    else if (a === '--ecrire-reference') o.ecrireReference = true;
    else throw new Error(`option inconnue : ${a}`);
  }
  return o;
}

const liste = (ids: string[], max = 8): string =>
  ids.length <= max ? ids.join(', ') : `${ids.slice(0, max).join(', ')} … (+${ids.length - max})`;

const parChamp = (ecarts: Ecart[]): string =>
  [...new Set(ecarts.map((e) => e.champ))].map((c) => `${c} ${ecarts.filter((e) => e.champ === c).length}`).join(' · ');

function afficher(r: Rapport, cliquet: { nouveaux: Ecart[]; disparus: Ecart[] } | null, reference: string): string {
  const c = r.comptes;
  const lignes = [
    `Fichiers : épisodes ${c.episodes.fichiers} · recos ${c.recos.fichiers} · œuvres ${c.items.fichiers} · mentions ${c.mentions.fichiers} · sources ${c.sources.fichiers}`,
    `Doublons : ${Object.values(c).reduce((n, x) => n + Object.keys(x.doublons).length, 0)} · erreurs de lecture : ${Object.values(c).reduce((n, x) => n + x.erreurs.length, 0)}`,
    `Statuts des recos : ${JSON.stringify(r.statuts.recos)} · des mentions : ${JSON.stringify(r.statuts.mentions)}`,
    `Mentions sans reco : ${JSON.stringify(r.orphelins.mentionSansReco)} · recos sans mention : ${JSON.stringify(r.orphelins.recoSansMention)}`,
    '',
    `Invariants bloquants : ${r.bloquants.length}`,
    ...r.bloquants.map((v) => `  ✗ ${v.regle} — ${v.message} : ${liste(v.ids)}`),
    `Avertissements : ${r.avertissements.length}`,
    ...r.avertissements.map((v) => `  ! ${v.regle} — ${v.message} (${v.ids.length}) : ${liste(v.ids)}`),
    '',
    `Écarts entre les recos validées et leur mention ou leur œuvre : ${r.ecarts.length}`,
    ...Object.entries(r.resumeEcarts).map(
      ([champ, s]) => `  ${champ} : ${s.total} (C1 ${s.C1} · C2 ${s.C2} · C3 ${s.C3})`,
    ),
    `Recos validées sans écart sur les neuf champs comparés : ${r.recosValideesSansEcart}`,
    `Liens des œuvres citées par au moins deux recos validées (${r.liens.oeuvresMultiRecos}) : identiques ${r.liens.identiques} · inclus ${r.liens.inclus} · complémentaires ${r.liens.complementaires} · même libellé, URL différentes ${r.liens.memeLibelleUrlDifferentes}`,
  ];
  if (cliquet !== null) {
    lignes.push('', `Référence : ${reference}`);
    lignes.push(`  écarts nouveaux : ${cliquet.nouveaux.length}${cliquet.nouveaux.length ? ` (${parChamp(cliquet.nouveaux)})` : ''}`);
    lignes.push(`  écarts disparus : ${cliquet.disparus.length}${cliquet.disparus.length ? ` (${parChamp(cliquet.disparus)})` : ''}`);
    for (const e of cliquet.nouveaux.slice(0, 20)) lignes.push(`  + ${e.id} ${e.champ} ${e.classe}`);
    for (const e of cliquet.disparus.slice(0, 20)) lignes.push(`  - ${e.id} ${e.champ} ${e.classe}`);
    if (cliquet.nouveaux.length + cliquet.disparus.length > 0) {
      lignes.push(
        '  Un écart nouveau se corrige dans les données, ou s’ajoute à la référence s’il est voulu ;',
        '  un écart disparu se retire de la référence : node scripts/verifier-corpus.ts --ecrire-reference',
      );
    }
  }
  return lignes.join('\n');
}

export function principal(args: string[]): number {
  let o: Options;
  try {
    o = lireOptions(args);
  } catch (e) {
    console.error((e as Error).message);
    return 2;
  }
  let rapport: Rapport;
  try {
    rapport = analyser(lireCorpus(o.contenu));
  } catch (e) {
    console.error((e as Error).message);
    return 2;
  }

  if (o.ecrireReference) {
    mkdirSync(dirname(o.reference), { recursive: true });
    const date = new Date().toISOString().slice(0, 10);
    writeFileSync(o.reference, formaterReference({ schemaVersion: 1, date, ...(o.commit ? { commit: o.commit } : {}), ecarts: rapport.ecarts }));
    console.log(`Référence écrite : ${o.reference} (${rapport.ecarts.length} écarts, ${date})`);
    return rapport.bloquants.length > 0 ? 1 : 0;
  }

  let cliquet: { nouveaux: Ecart[]; disparus: Ecart[] } | null = null;
  let erreurReference: string | null = null;
  if (!o.sansReference) {
    if (!existsSync(o.reference)) {
      erreurReference = `référence absente : ${o.reference} (la créer avec --ecrire-reference)`;
    } else {
      try {
        cliquet = comparerReference(rapport.ecarts, lireReference(readFileSync(o.reference, 'utf8')).ecarts);
      } catch (e) {
        erreurReference = (e as Error).message;
      }
    }
  }

  if (o.json) console.log(JSON.stringify({ ...rapport, cliquet, erreurReference }, null, 2));
  else {
    console.log(afficher(rapport, cliquet, o.reference));
    if (erreurReference !== null) console.log(`\n${erreurReference}`);
  }
  const echec =
    rapport.bloquants.length > 0 ||
    erreurReference !== null ||
    (cliquet !== null && cliquet.nouveaux.length + cliquet.disparus.length > 0);
  if (!o.json) console.log(echec ? '\nRésultat : ÉCHEC' : '\nRésultat : OK');
  return echec ? 1 : 0;
}

const lanceDirectement =
  process.argv[1] !== undefined &&
  resolve(process.argv[1]).toLowerCase() === fileURLToPath(import.meta.url).toLowerCase();
if (lanceDirectement) process.exitCode = principal(process.argv.slice(2));
