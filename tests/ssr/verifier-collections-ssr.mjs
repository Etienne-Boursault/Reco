#!/usr/bin/env node
/**
 * Vérifie que les collections se lisent PENDANT une requête, en SSR.
 *
 *   RECO_SSR=1 RECO_TEST_ROUTES=1 SITE_URL=https://unebonnere.co npm run build
 *   node tests/ssr/verifier-collections-ssr.mjs
 *
 * Le script monte le gestionnaire construit (`dist/server/entry.mjs`, mode
 * `middleware`) sur un port local éphémère, interroge `/__tests/collections`
 * (cf. `route-collections.ts`) et compare chaque compte au nombre de fichiers
 * de `src/content/`. Il dit aussi si les données sont embarquées dans
 * `dist/server/`, c'est-à-dire si le serveur les sert sans relire `src/content`.
 *
 * Code de sortie : 0 lecture réussie et comptes égaux, 1 échec, 2 build absent.
 */
import { createServer } from 'node:http';
import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const RACINE = fileURLToPath(new URL('../../', import.meta.url));
const ENTREE = join(RACINE, 'dist', 'server', 'entry.mjs');
const CONTENU = join(RACINE, 'src', 'content');

// Dossiers que les chargeurs de `src/content.config.ts` excluent eux-mêmes :
// la fixture croisée Python/TypeScript des œuvres et des mentions.
const EXCLUS = new Set(['__cross_stack_fixture__']);

/** Fichiers JSON d'un dossier, sous-dossiers compris, hors dossiers exclus. */
function fichiersJson(dossier) {
  const trouves = [];
  for (const entree of readdirSync(dossier)) {
    const chemin = join(dossier, entree);
    if (statSync(chemin).isDirectory()) {
      if (!EXCLUS.has(entree)) trouves.push(...fichiersJson(chemin));
    } else if (entree.endsWith('.json')) trouves.push(chemin);
  }
  return trouves;
}

/** Un fichier de `dist/server/` contient-il cette chaîne ? */
function serveurContient(chaine) {
  const parcourir = (dossier) =>
    readdirSync(dossier).some((entree) => {
      const chemin = join(dossier, entree);
      if (statSync(chemin).isDirectory()) return parcourir(chemin);
      return entree.endsWith('.mjs') && readFileSync(chemin, 'utf8').includes(chaine);
    });
  return parcourir(join(RACINE, 'dist', 'server'));
}

async function principal() {
  if (!existsSync(ENTREE)) {
    console.error(`Build SSR absent : ${ENTREE}. Lancer d'abord le build indiqué en tête du script.`);
    return 2;
  }
  const { handler } = await import(pathToFileURL(ENTREE).href);
  const serveur = createServer((req, res) =>
    handler(req, res, () => {
      res.statusCode = 404;
      res.end();
    }),
  );
  await new Promise((ok) => serveur.listen(0, '127.0.0.1', ok));
  const { port } = serveur.address();
  try {
    const reponse = await fetch(`http://127.0.0.1:${port}/__tests/collections`);
    if (reponse.status === 404) {
      console.error('Route de test absente : construire avec RECO_SSR=1 RECO_TEST_ROUTES=1.');
      return 2;
    }
    const comptes = await reponse.json();
    let ok = reponse.status === 200;
    for (const [nom, lu] of Object.entries(comptes)) {
      const attendu = fichiersJson(join(CONTENU, nom)).length;
      const egal = lu === attendu && lu > 0;
      ok &&= egal;
      console.log(`${egal ? 'ok ' : 'ÉCHEC'} ${nom} : ${lu} lues à l'exécution, ${attendu} fichiers`);
    }
    const unId = JSON.parse(readFileSync(fichiersJson(join(CONTENU, 'items'))[0], 'utf8')).id;
    console.log(`Données embarquées dans dist/server : ${serveurContient(unId) ? 'oui' : 'non'}`);
    return ok ? 0 : 1;
  } finally {
    serveur.close();
  }
}

process.exitCode = await principal();
