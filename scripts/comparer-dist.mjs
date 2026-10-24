#!/usr/bin/env node
/**
 * Compare deux sorties de build, fichier par fichier, par empreinte SHA-256.
 *
 *   node scripts/comparer-dist.mjs <dist-avant> <dist-apres>
 *
 * Sert aux PR qui ne doivent RIEN changer au site (un refactor, un nouveau
 * port de lecture) : construire avant et après, avec le même `SITE_URL`, puis
 * comparer. Seules les valeurs qui changent d'un build à l'autre sans que le
 * code ni les données changent sont neutralisées avant le hachage ; la liste
 * est ci-dessous, et rien d'autre ne l'est.
 *
 * Code de sortie : 0 identiques, 1 différences (listées), 2 erreur d'usage.
 */
import { createHash } from 'node:crypto';
import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

/**
 * Valeurs qui dépendent de l'horloge ou du hasard du build, et non du site.
 * Relevé le 2026-10-25 : deux builds du même commit différaient sur 1 302
 * fichiers, tous expliqués par ces six règles. Chacune est limitée aux
 * fichiers où la valeur varie, pour ne masquer aucun vrai changement ailleurs.
 */
export const NORMALISATIONS = [
  {
    raison: 'sitemap : `lastmod` vaut la date du build (astro.config.mjs)',
    fichiers: /(^|\/)sitemap-(index|\d+)\.xml$/,
    motif: /<lastmod>[^<]*<\/lastmod>/g,
    remplacement: '<lastmod></lastmod>',
  },
  {
    raison: 'JSON : `generatedAt` vaut la date du build',
    fichiers: /\.json$/,
    motif: /"generatedAt":\s*"[^"]*"/g,
    remplacement: '"generatedAt":""',
  },
  {
    raison: 'pages de statistiques : `dateModified` du JSON-LD vaut la date du build',
    fichiers: /(^|\/)stats\/index\.html$/,
    motif: /"dateModified":"[^"]*"/g,
    remplacement: '"dateModified":""',
  },
  {
    raison: 'formulaires de signalement : jeton de captcha tiré au build',
    fichiers: /(^|\/)report\/[^/]+\/index\.html$/,
    motif: /name="captchaToken" value="[^"]*"/g,
    remplacement: 'name="captchaToken" value=""',
  },
  {
    raison: 'formulaires de signalement : question du captcha tirée au build',
    fichiers: /(^|\/)report\/[^/]+\/index\.html$/,
    motif: /(<span data-captcha-question[^>]*>)[^<]*(<\/span>)/g,
    remplacement: '$1$2',
  },
  {
    raison: '`/api/captcha` pré-rendu : jeton et question tirés au build',
    fichiers: /(^|\/)api\/captcha$/,
    motif: /"(token|question)":"[^"]*"/g,
    remplacement: '"$1":""',
  },
];

/** Fichiers écrits hors du build Astro, par la commande de déploiement. */
export const IGNORES = [/(^|\/)version\.txt$/];

/** Chemins relatifs (séparateur `/`) de tous les fichiers d'un dossier. */
export function fichiers(racine) {
  const trouves = [];
  const parcourir = (dossier) => {
    for (const entree of readdirSync(dossier)) {
      const chemin = join(dossier, entree);
      if (statSync(chemin).isDirectory()) parcourir(chemin);
      else trouves.push(relative(racine, chemin).split('\\').join('/'));
    }
  };
  parcourir(racine);
  return trouves.filter((f) => !IGNORES.some((motif) => motif.test(f))).sort();
}

/** Contenu d'un fichier après les seules normalisations listées. */
export function normaliser(chemin, contenu) {
  let texte = null;
  for (const n of NORMALISATIONS) {
    if (!n.fichiers.test(chemin)) continue;
    texte ??= contenu.toString('utf8');
    texte = texte.replace(n.motif, n.remplacement);
  }
  return texte === null ? contenu : Buffer.from(texte, 'utf8');
}

/** Empreinte SHA-256 d'un fichier normalisé. */
export function empreinte(racine, chemin) {
  const contenu = normaliser(chemin, readFileSync(join(racine, chemin)));
  return createHash('sha256').update(contenu).digest('hex');
}

/** Fichiers identiques, différents, ou présents d'un seul côté. */
export function comparer(avant, apres) {
  const a = new Set(fichiers(avant));
  const b = new Set(fichiers(apres));
  const resultat = { identiques: 0, differents: [], seulementAvant: [], seulementApres: [] };
  for (const f of a) {
    if (!b.has(f)) resultat.seulementAvant.push(f);
    else if (empreinte(avant, f) === empreinte(apres, f)) resultat.identiques += 1;
    else resultat.differents.push(f);
  }
  for (const f of b) if (!a.has(f)) resultat.seulementApres.push(f);
  return resultat;
}

function principal(argv) {
  const [avant, apres] = argv.slice(2).map((d) => resolve(d));
  if (!avant || !apres || !existsSync(avant) || !existsSync(apres)) {
    console.error('usage : node scripts/comparer-dist.mjs <dist-avant> <dist-apres>');
    return 2;
  }
  const r = comparer(avant, apres);
  const ecarts = r.differents.length + r.seulementAvant.length + r.seulementApres.length;
  console.log(`${r.identiques} fichiers identiques, ${ecarts} écart(s).`);
  for (const f of r.differents) console.log(`différent      ${f}`);
  for (const f of r.seulementAvant) console.log(`seulement avant ${f}`);
  for (const f of r.seulementApres) console.log(`seulement après ${f}`);
  return ecarts === 0 ? 0 : 1;
}

const lanceDirectement =
  process.argv[1] !== undefined &&
  resolve(process.argv[1]).toLowerCase() === fileURLToPath(import.meta.url).toLowerCase();
if (lanceDirectement) process.exitCode = principal(process.argv);
