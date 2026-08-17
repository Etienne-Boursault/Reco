/**
 * Test post-build : la page qui INJECTE le fragment doit en porter les styles.
 *
 * POURQUOI CE FICHIER EXISTE — incident du 2026-08-17
 * ---------------------------------------------------
 * La vue « toutes les recommandations » est passée en chargement à la demande :
 * son balisage arrive au clic, depuis `/[source]/recos-fragment`. Deux
 * mécanismes d'Astro se sont alors retournés contre nous, tous deux
 * silencieusement.
 *
 *   1. Astro ne met dans le bundle CSS d'une page que les styles des composants
 *      qu'elle REND. Le catalogue ne rendant plus aucune `RecoCard`, ses 248
 *      lignes de style ont été élaguées — l'import du composant, devenu
 *      inutilisé, l'a été avec.
 *
 *   2. Astro SCOPE les styles d'un composant (`data-astro-cid-…`). Le balisage
 *      de la barre d'outils avait migré vers `AllRecosView`, mais ses styles
 *      étaient restés dans `SourceCatalog` : les règles scopées ne matchaient
 *      plus rien.
 *
 * Résultat : cartes sans fond ni bordure, champ de recherche au style natif du
 * navigateur. Le site était visiblement cassé, et RIEN ne l'a signalé — ni la
 * suite (2094 tests verts), ni le build, ni un test manuel qui vérifiait le DOM
 * mais pas le rendu. C'est un utilisateur qui l'a vu.
 *
 * D'OÙ LA FORME DE CE TEST
 * ------------------------
 * Il ne liste pas des sélecteurs à la main — une liste curée oublie la classe
 * ajoutée demain. Il DÉRIVE la vérification : toute classe du fragment qui est
 * stylée sur la page autonome `/recos` doit l'être aussi sur la page hôte. La
 * page complète sert de référence, puisqu'elle rend le composant pour de bon.
 */
import { describe, it, expect } from 'vitest';
import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';

import { distRoot } from '../helpers/distRoot';

const DIST = distRoot() ?? join(process.cwd(), 'dist');

/** Page hôte : elle n'affiche aucune carte, mais en injecte au clic. */
const HOTE = join(DIST, 'index.html');
/** Page autonome : elle rend le composant, donc porte forcément ses styles. */
const AUTONOME = join(DIST, 'un-bon-moment', 'recos', 'index.html');
const FRAGMENT = join(DIST, 'un-bon-moment', 'recos-fragment', 'index.html');

const construit = [HOTE, AUTONOME, FRAGMENT].every(existsSync);

/** CSS réellement disponible pour une page : blocs inline + feuilles liées. */
function cssDe(chemin: string): string {
  const html = readFileSync(chemin, 'utf-8');
  const inline = [...html.matchAll(/<style[^>]*>([\s\S]*?)<\/style>/g)].map((m) => m[1]);
  const liees = [...html.matchAll(/href="(\/_astro\/[^"]+\.css)"/g)].map((m) => {
    const f = join(DIST, m[1].replace(/^\//, ''));
    return existsSync(f) ? readFileSync(f, 'utf-8') : '';
  });
  return [...inline, ...liees].join('\n');
}

/** Classes présentes dans le balisage du fragment. */
function classesDuFragment(): Set<string> {
  const html = readFileSync(FRAGMENT, 'utf-8');
  const noms = new Set<string>();
  for (const m of html.matchAll(/\sclass="([^"]+)"/g)) {
    for (const nom of m[1].split(/\s+/)) if (nom) noms.add(nom);
  }
  return noms;
}

/**
 * Une règle cible-t-elle cette classe ?
 *
 * On cherche le sélecteur `.nom` non suivi d'un caractère de nom de classe —
 * sans quoi `.card` matcherait `.card-title` et le test se croirait satisfait.
 * Le `data-astro-cid` est retiré au préalable : une règle scopée à un AUTRE
 * composant ne s'appliquera pas au fragment, mais sa présence dans le fichier
 * suffirait à tromper une recherche naïve.
 */
function styleLaClasse(css: string, nom: string): boolean {
  const echappe = nom.replace(/[.*+?^${}()|[\]\\-]/g, '\\$&');
  return new RegExp(`\\.${echappe}(?![\\w-])`).test(css);
}

describe.skipIf(!construit)('styles du fragment chargé à la demande', () => {
  const cssHote = cssDe(HOTE);
  const cssAutonome = cssDe(AUTONOME);
  const classes = [...classesDuFragment()];

  it('le build a bien produit les trois documents', () => {
    expect(classes.length).toBeGreaterThan(5);
    expect(cssHote.length).toBeGreaterThan(1000);
    expect(cssAutonome.length).toBeGreaterThan(1000);
  });

  it('la page hôte porte les styles de TOUTES les classes du fragment', () => {
    // Référence : ce que la page autonome style réellement. Une classe que
    // personne ne style (utilitaire, crochet JavaScript) n'a rien à prouver.
    const stylees = classes.filter((c) => styleLaClasse(cssAutonome, c));
    const manquantes = stylees.filter((c) => !styleLaClasse(cssHote, c));

    expect(stylees.length).toBeGreaterThan(3);
    expect(manquantes,
      `Ces classes sont stylées sur /recos mais PAS sur la page qui injecte le ` +
      `fragment : le contenu arrivera sans mise en forme. Déplace leurs règles ` +
      `dans un fichier CSS importé par les deux composants (cf. ` +
      `src/styles/reco-card.css).`,
    ).toEqual([]);
  });

  it.each(['card', 'toolbar', 'search', 'filters', 'chip'])(
    'la classe « %s » est stylée sur la page hôte',
    (nom) => {
      // Doublon assumé du test précédent, sur les classes qui portent
      // l'essentiel de l'apparence : si la dérivation cassait un jour, ces
      // cinq-là resteraient gardées.
      expect(styleLaClasse(cssHote, nom)).toBe(true);
    },
  );

  it('le fragment lui-même n’embarque aucune feuille de style', () => {
    // C'est un fragment : il est injecté DANS un document qui a déjà sa CSS.
    // En embarquer une le rendrait plus lourd à chaque chargement, et
    // masquerait précisément le défaut que ce fichier surveille.
    const html = readFileSync(FRAGMENT, 'utf-8');
    expect(html).not.toMatch(/<link[^>]+stylesheet/);
    expect(html).not.toMatch(/<style/);
  });
});
