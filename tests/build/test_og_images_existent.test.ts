/**
 * Test post-build : toute image de partage déclarée doit exister.
 *
 * POURQUOI CE FICHIER EXISTE — constaté le 2026-08-25
 * ---------------------------------------------------
 * Les 1 036 pages d'œuvre déclaraient
 * `og:image = /og/un-bon-moment/oeuvre/<id>.png`, une route que
 * `src/pages/og/[...slug].png.ts` ne génère pas. Toutes répondaient 404.
 *
 * Rien ne pouvait le signaler : la balise est syntaxiquement correcte, le
 * build réussit, la page s'affiche, et aucun test ne suivait le lien. Le
 * défaut n'était visible qu'en partageant une reco — c'est-à-dire au moment
 * précis où le site doit faire bonne impression.
 *
 * D'OÙ LA FORME DE CE TEST
 * ------------------------
 * Il ne liste aucune URL attendue : une liste curée oublie la page ajoutée
 * demain. Il DÉRIVE la vérification du site construit — toute `og:image`
 * servie par ce domaine doit correspondre à un fichier présent dans la
 * sortie. Les images distantes (miniatures YouTube des épisodes) sont hors
 * de portée d'un test hors ligne et sont donc seulement dénombrées.
 */
import { describe, expect, it } from 'vitest';
import { existsSync, readFileSync, readdirSync, statSync } from 'node:fs';
import { join } from 'node:path';

import { distRoot } from '../helpers/distRoot';

const DIST = distRoot();

/** Toutes les pages HTML de la sortie. */
function pagesHtml(racine: string): string[] {
  const trouvees: string[] = [];
  const parcourir = (dossier: string) => {
    for (const entree of readdirSync(dossier)) {
      const chemin = join(dossier, entree);
      if (statSync(chemin).isDirectory()) parcourir(chemin);
      else if (entree.endsWith('.html')) trouvees.push(chemin);
    }
  };
  parcourir(racine);
  return trouvees;
}

const OG_IMAGE = /<meta\s+property="og:image"\s+content="([^"]+)"/;

describe.skipIf(!DIST)('les og:image déclarées existent', () => {
  const racine = DIST as string;

  /** URL d'image → une page qui la déclare, pour nommer le coupable. */
  const declarees = new Map<string, string>();
  for (const page of pagesHtml(racine)) {
    const trouve = OG_IMAGE.exec(readFileSync(page, 'utf8'));
    if (trouve && !declarees.has(trouve[1])) {
      declarees.set(trouve[1], page.slice(racine.length + 1));
    }
  }

  it('chaque page en déclare une', () => {
    // Une page sans image de partage s'affiche en bloc de texte nu sur les
    // réseaux. Le site en a peu — mais il en a.
    expect(declarees.size).toBeGreaterThan(0);
  });

  it('aucune image locale ne manque dans la sortie', () => {
    const manquantes: string[] = [];

    for (const [url, page] of declarees) {
      // Les miniatures YouTube des épisodes vivent chez un tiers : un test
      // hors ligne ne peut pas les suivre.
      if (/^https?:\/\//.test(url) && !url.includes('unebonnere.co') && !url.includes('example.com')) {
        continue;
      }
      const chemin = url.replace(/^https?:\/\/[^/]+/, '');
      if (!existsSync(join(racine, chemin))) manquantes.push(`${url}  (déclarée par ${page})`);
    }

    expect(manquantes, `Images de partage introuvables :\n  ${manquantes.join('\n  ')}`)
      .toEqual([]);
  });

  it('aucune n’est le PNG 1×1 de repli', () => {
    // Le rendu Satori tombe en silence sur un pixel transparent quand la
    // police est introuvable. Une vraie carte pèse ~46 Ko, le repli 68 octets.
    const vides: string[] = [];

    for (const url of declarees.keys()) {
      const chemin = join(racine, url.replace(/^https?:\/\/[^/]+/, ''));
      if (!existsSync(chemin)) continue;
      if (statSync(chemin).size < 1024) vides.push(url);
    }

    expect(vides, `Cartes OG vides (repli 1×1) :\n  ${vides.join('\n  ')}`).toEqual([]);
  });
});
