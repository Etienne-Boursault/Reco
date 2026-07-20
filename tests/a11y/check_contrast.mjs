#!/usr/bin/env node
/**
 * tests/a11y/check_contrast.mjs — Vérifie les ratios WCAG AA de la palette
 * par défaut ET de chaque thème de source (multi-podcast).
 *
 * SSOT palette : `src/styles/tokens.ts` (zéro duplication). Pour chaque
 * source découverte sous `src/content/sources/*.json`, on lit `theme.colors`
 * et on revalide les mêmes cas de contraste.
 *
 * Formule de luminance et de ratio : WCAG 2.1 (sRGB → linéaire → pondération).
 *   - texte normal : ratio ≥ 4.5:1
 *   - texte large / éléments non-textuels : ratio ≥ 3:1
 *
 * Usage : node tests/a11y/check_contrast.mjs
 * Exit 0 = OK, 1 = au moins une violation.
 *
 * Cf. P0-2 (CR archi) — multi-source contrast + SSOT.
 */
import { readFileSync, readdirSync, existsSync } from 'node:fs';
import { join, resolve } from 'node:path';
import process from 'node:process';

const ROOT = resolve(
  new URL('../..', import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1'),
);

// --- Couleurs / contraste --------------------------------------------------
function hex(c) {
  const m = c.replace('#', '').match(/^([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i);
  if (!m) throw new Error(`hex invalide: ${c}`);
  return [
    parseInt(m[1], 16) / 255,
    parseInt(m[2], 16) / 255,
    parseInt(m[3], 16) / 255,
  ];
}
const lin = (v) => (v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4));
function lum([r, g, b]) {
  return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
}
function ratio(a, b) {
  const la = lum(hex(a));
  const lb = lum(hex(b));
  const [hi, lo] = la > lb ? [la, lb] : [lb, la];
  return (hi + 0.05) / (lo + 0.05);
}

// --- Parser TS minimal -----------------------------------------------------
// On évite la dépendance à un transpileur TS au runtime : on lit le fichier
// `tokens.ts` et on extrait `defaultTheme` + `contrastCases` au regex.
// Robuste tant qu'on garde le format exporté actuel (object literal direct).
function loadTokens() {
  const file = join(ROOT, 'src', 'styles', 'tokens.ts');
  const src = readFileSync(file, 'utf8');
  // defaultTheme : extrait l'objet entre accolades.
  const themeMatch = src.match(/defaultTheme\s*:\s*ThemeColors\s*=\s*\{([\s\S]*?)\};/);
  if (!themeMatch) throw new Error('tokens.ts : defaultTheme introuvable');
  const theme = {};
  for (const m of themeMatch[1].matchAll(/(\w+)\s*:\s*'([^']+)'/g)) {
    theme[m[1]] = m[2];
  }
  // contrastCases : tableau d'objets { name, fg, bg, min }.
  const casesMatch = src.match(/contrastCases\s*:\s*ContrastCase\[\]\s*=\s*\[([\s\S]*?)\];/);
  if (!casesMatch) throw new Error('tokens.ts : contrastCases introuvable');
  const cases = [];
  const re = /\{\s*name:\s*'([^']+)'\s*,\s*fg:\s*'(\w+)'\s*,\s*bg:\s*'(\w+)'\s*,\s*min:\s*([\d.]+)\s*\}/g;
  let m;
  while ((m = re.exec(casesMatch[1])) !== null) {
    cases.push({ name: m[1], fg: m[2], bg: m[3], min: parseFloat(m[4]) });
  }
  return { theme, cases };
}

// --- Multi-source : itère sur src/content/sources/*.json -------------------
function loadSources() {
  const dir = join(ROOT, 'src', 'content', 'sources');
  if (!existsSync(dir)) return [];
  const files = readdirSync(dir).filter((n) => n.endsWith('.json'));
  const sources = [];
  for (const f of files) {
    try {
      const data = JSON.parse(readFileSync(join(dir, f), 'utf8'));
      if (data?.theme?.colors) {
        sources.push({
          id: data.id ?? f.replace(/\.json$/, ''),
          title: data.title ?? data.id,
          colors: data.theme.colors,
        });
      }
    } catch {
      /* ignore JSON malformés (le build Astro les rapportera). */
    }
  }
  return sources;
}

// --- Validation d'un thème -------------------------------------------------
function validateThemeContrast(label, theme, cases) {
  let failed = 0;
  console.log(`\n[contrast] ${label}`);
  for (const c of cases) {
    const fg = theme[c.fg];
    const bg = theme[c.bg];
    if (!fg || !bg) {
      console.log(`  -- ${c.name}: clé manquante (fg=${c.fg}, bg=${c.bg})`);
      continue;
    }
    const r = ratio(fg, bg);
    const ok = r >= c.min;
    console.log(`  ${ok ? 'OK ' : 'KO '} ${c.name}: ${r.toFixed(2)}:1 (≥ ${c.min}:1)`);
    if (!ok) failed++;
  }
  return failed;
}

// --- Main ------------------------------------------------------------------
function main() {
  let failed = 0;
  const { theme, cases } = loadTokens();
  failed += validateThemeContrast('palette par défaut (tokens.ts)', theme, cases);

  const sources = loadSources();
  if (sources.length === 0) {
    console.log('\n[contrast] aucune source trouvée — palette par défaut uniquement.');
  } else {
    for (const s of sources) {
      failed += validateThemeContrast(`source: ${s.id} (${s.title})`, s.colors, cases);
    }
  }

  if (failed === 0) {
    console.log('\n[contrast] OK — toutes les combinaisons respectent WCAG AA.');
    process.exit(0);
  }
  console.error(`\n[contrast] ${failed} combinaison(s) en dessous du seuil WCAG.`);
  process.exit(1);
}

main();
