#!/usr/bin/env node
/**
 * tests/a11y/check_a11y.mjs — Vérifications WCAG AA statiques sur le build Astro.
 *
 * Approche : pas de Playwright/Puppeteer (lourd à installer en CI pour un kit
 * self-hostable). On scanne le HTML statique produit par `astro build` et on
 * cherche les violations les plus courantes (heuristiques alignées sur
 * axe-core). Couvre :
 *   - <html lang="..">                  → WCAG 3.1.1
 *   - Skip link (#main + .skip-link)    → WCAG 2.4.1
 *   - <main id="main">                  → WCAG 1.3.1 / 2.4.1
 *   - <img alt="..">                    → WCAG 1.1.1
 *   - <a> sans contenu accessible       → WCAG 2.4.4
 *   - Boutons icône avec aria-label     → WCAG 4.1.2
 *   - Heading hierarchy (pas de h1→h3)  → WCAG 1.3.1
 *   - Présence de :focus-visible CSS    → WCAG 2.4.7
 *
 * Usage :
 *   npm run build   # produit dist/
 *   node tests/a11y/check_a11y.mjs [--dist ./dist]
 * Exit 0 = OK, 1 = violations détectées.
 */
import { readFileSync, readdirSync, statSync, existsSync } from 'node:fs';
import { join, relative, resolve } from 'node:path';

const ROOT = resolve(new URL('../..', import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1'));
const argDist = process.argv.find((a) => a.startsWith('--dist='));
const DIST = resolve(argDist ? argDist.slice('--dist='.length) : join(ROOT, 'dist'));

const violations = [];
function fail(file, rule, detail) {
  violations.push({ file: relative(DIST, file), rule, detail });
}

function walk(dir, out = []) {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    const s = statSync(p);
    if (s.isDirectory()) walk(p, out);
    else if (name.endsWith('.html')) out.push(p);
  }
  return out;
}

/**
 * Routes declarees `export const partial = true` dans `src/pages`.
 *
 * Un partial Astro est emis SANS <html>, <head> ni skip-link : c'est un
 * fragment injecte dans une page deja chargee, pas un document. Le scanner le
 * voyait comme une page nue et remontait quatre violations qui n'en sont pas
 * (releve du 2026-08-18 sur `/[source]/recos-fragment`).
 *
 * On les reconnait a leur DECLARATION, jamais a leur nom de fichier : un
 * nouveau partial est ainsi couvert d'office, tandis qu'une vraie page qui
 * perdrait son <html> par accident reste attrapee.
 */
function routesPartielles() {
  const racine = join(ROOT, 'src', 'pages');
  if (!existsSync(racine)) return [];
  const motifs = [];
  const parcourir = (dir) => {
    for (const name of readdirSync(dir)) {
      const chemin = join(dir, name);
      if (statSync(chemin).isDirectory()) { parcourir(chemin); continue; }
      if (!name.endsWith('.astro')) continue;
      const src = readFileSync(chemin, 'utf8');
      if (!/^\s*export\s+const\s+partial\s*=\s*true/m.test(src)) continue;
      // On derive la ROUTE COMPLETE, pas le nom de fichier : un partial nomme
      // `index.astro` donnerait sinon le motif `/index(/index.html)?$`, qui
      // exclurait le site entier en silence.
      const route = relative(racine, chemin)
        .replace(/\\/g, '/')
        .replace(/\.astro$/, '')
        .replace(/\/index$/, '');
      // Les segments dynamiques (`[source]`, `[...rest]`) valent n'importe
      // quel segment une fois la route rendue.
      const motif = route
        .split('/')
        .map((seg) => (/^\[.+\]$/.test(seg)
          ? '[^/]+'
          : seg.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')))
        .join('/');
      motifs.push(new RegExp(`/${motif}(/index\\.html|\\.html)?$`));
    }
  };
  parcourir(racine);
  return motifs;
}


/** Extrait toutes les balises img sous forme {raw, attrs}. */
function extractTags(html, tag) {
  const re = new RegExp(`<${tag}\\b[^>]*>`, 'gi');
  return [...html.matchAll(re)].map((m) => m[0]);
}
function attr(tag, name) {
  const m = tag.match(new RegExp(`\\b${name}\\s*=\\s*("([^"]*)"|'([^']*)'|([^\\s>]+))`, 'i'));
  return m ? (m[2] ?? m[3] ?? m[4] ?? '') : null;
}
function hasAttr(tag, name) {
  return new RegExp(`\\b${name}(\\s|=|>)`, 'i').test(tag);
}

function checkHtml(file) {
  const html = readFileSync(file, 'utf8');

  // 0. Pages de REDIRECTION (meta refresh) : stubs générés par Astro (ex.
  // mode mono-source `/un-bon-moment` → `/`). Ce ne sont pas des pages
  // réelles — pas de <html>/skip-link/#main attendus — et elles portent déjà
  // rel=canonical + noindex. On les saute (cf. redirection SourceCatalog).
  if (/<meta\b[^>]*http-equiv=("|')?refresh\1/i.test(html)) return;

  // 1. <html lang="..">
  const htmlTag = html.match(/<html\b[^>]*>/i)?.[0];
  if (!htmlTag) fail(file, 'html-lang', 'pas de balise <html>');
  else if (!attr(htmlTag, 'lang')) fail(file, 'html-lang', '<html> sans attribut lang');

  // 2. Skip link
  if (!/class=("|')[^"']*\bskip-link\b/.test(html)) {
    fail(file, 'skip-link', 'pas de .skip-link sur la page');
  }
  if (!/href=("|')#main\1/.test(html)) {
    fail(file, 'skip-link', 'skip-link ne pointe pas vers #main');
  }

  // 3. Ancre #main présente
  if (!/\bid=("|')main\1/.test(html)) {
    fail(file, 'skip-target', 'pas de #main comme cible de skip-link');
  }

  // 3b. Unicité des id (M22) : tout id doit être unique sur la page.
  const allIds = [...html.matchAll(/\sid=("([^"]+)"|'([^']+)')/g)].map(
    (m) => m[2] ?? m[3],
  );
  const seen = new Set();
  const dupes = new Set();
  for (const i of allIds) {
    if (seen.has(i)) dupes.add(i);
    else seen.add(i);
  }
  for (const d of dupes) {
    fail(file, 'duplicate-id', `id="${d}" présent plusieurs fois`);
  }

  // 3c. aria-controls (M21) : chaque référence doit pointer vers un id existant.
  const ariaControls = [...html.matchAll(/\baria-controls=("([^"]+)"|'([^']+)')/g)].map(
    (m) => m[2] ?? m[3],
  );
  for (const target of ariaControls) {
    // Plusieurs ids séparés par espace possibles.
    for (const t of target.split(/\s+/).filter(Boolean)) {
      if (!seen.has(t)) {
        fail(file, 'aria-controls-target', `aria-controls="${t}" ne pointe sur aucun id`);
      }
    }
  }

  // 4. Images : alt obligatoire (vide ok pour décoratives)
  for (const tag of extractTags(html, 'img')) {
    if (attr(tag, 'alt') === null) {
      fail(file, 'img-alt', `<img> sans attribut alt: ${tag.slice(0, 80)}`);
    }
  }

  // 5. <a> sans contenu accessible : on inspecte les liens vides
  // (heuristique : <a ...></a> sans aria-label et sans texte enfant)
  const linkRe = /<a\b([^>]*)>([\s\S]*?)<\/a>/gi;
  let m;
  while ((m = linkRe.exec(html))) {
    const attrs = m[1];
    const inner = m[2].replace(/<[^>]+>/g, '').trim();
    const hasAriaLabel = /\baria-label\s*=/.test(attrs);
    const hasAriaLabelledBy = /\baria-labelledby\s*=/.test(attrs);
    // L'inner peut contenir un <img alt="..."> qui suffit comme nom accessible.
    const innerImgAlt = m[2].match(/<img\b[^>]*\balt=("([^"]*)"|'([^']*)')/i);
    const imgAccName = innerImgAlt ? (innerImgAlt[2] ?? innerImgAlt[3] ?? '').trim() : '';
    if (!inner && !hasAriaLabel && !hasAriaLabelledBy && !imgAccName) {
      fail(file, 'link-name', `<a> sans nom accessible: ${m[0].slice(0, 100)}`);
    }
  }

  // 6. Boutons : interdit <button></button> sans label
  const btnRe = /<button\b([^>]*)>([\s\S]*?)<\/button>/gi;
  while ((m = btnRe.exec(html))) {
    const attrs = m[1];
    const inner = m[2].replace(/<[^>]+>/g, '').trim();
    if (!inner && !/\baria-label\s*=/.test(attrs) && !/\baria-labelledby\s*=/.test(attrs)) {
      fail(file, 'button-name', `<button> sans nom accessible: ${m[0].slice(0, 100)}`);
    }
  }

  // 7. Heading hierarchy : pas de saut > 1 niveau
  const headings = [...html.matchAll(/<h([1-6])\b/gi)].map((x) => Number(x[1]));
  let prev = 0;
  for (const h of headings) {
    if (prev !== 0 && h > prev + 1) {
      fail(file, 'heading-order', `saut de niveau h${prev} → h${h}`);
      break; // un seul rapport par page
    }
    prev = h;
  }
}

function checkCss() {
  const cssGlobal = join(ROOT, 'src', 'styles', 'global.css');
  if (!existsSync(cssGlobal)) {
    violations.push({ file: 'src/styles/global.css', rule: 'css-missing', detail: 'fichier absent' });
    return;
  }
  const css = readFileSync(cssGlobal, 'utf8');
  if (!/:focus-visible/.test(css)) {
    violations.push({
      file: 'src/styles/global.css',
      rule: 'focus-visible',
      detail: 'pas de règle :focus-visible globale',
    });
  }
  if (!/prefers-reduced-motion/.test(css)) {
    violations.push({
      file: 'src/styles/global.css',
      rule: 'reduced-motion',
      detail: 'pas de support prefers-reduced-motion',
    });
  }
  if (!/\.skip-link/.test(css)) {
    violations.push({
      file: 'src/styles/global.css',
      rule: 'skip-link-css',
      detail: 'pas de classe .skip-link stylée',
    });
  }
}

function main() {
  checkCss();
  if (!existsSync(DIST)) {
    // L14 : sans dist/, on ne peut PAS valider les pages → exit 1.
    // Le check CSS reste lancé pour signaler les régressions CSS rapidement.
    console.error(
      `[a11y] dist/ introuvable (${DIST}). Lance d'abord 'npm run build'.\n` +
        `Le check CSS a quand même tourné — violations CSS:`,
    );
    if (violations.length === 0) {
      console.log('  (aucune)');
    } else {
      for (const v of violations) {
        console.error(`  - [${v.rule}] ${v.file}: ${v.detail}`);
      }
    }
    process.exit(1);
  } else {
    const files = walk(DIST);
    // Ignorer les pages /verifier (internes, noindex — pas du périmètre public).
    // M19 : regex robuste — match `verifier` en fin de path (avec /index.html
    // ou en tant que fichier .html), insensible aux séparateurs Windows.
    const partiels = routesPartielles();
    const pub = files.filter((f) => {
      const p = f.replace(/\\/g, '/');
      if (/\/verifier(\/index\.html|\.html)?$/.test(p)) return false;
      // Meme forme que l'exclusion ci-dessus, mais pour chaque route
      // declaree partielle (cf. `routesPartielles`).
      for (const motif of partiels) {
        if (motif.test(p)) return false;
      }
      return true;
    });
    for (const f of pub) checkHtml(f);
    console.log(`[a11y] ${pub.length} pages HTML scannées.`);
  }

  if (violations.length === 0) {
    console.log('[a11y] OK — aucune violation détectée.');
    process.exit(0);
  }
  console.error(`[a11y] ${violations.length} violation(s):`);
  for (const v of violations.slice(0, 50)) {
    console.error(`  - [${v.rule}] ${v.file}: ${v.detail}`);
  }
  if (violations.length > 50) console.error(`  ... (${violations.length - 50} de plus)`);
  process.exit(1);
}

main();
