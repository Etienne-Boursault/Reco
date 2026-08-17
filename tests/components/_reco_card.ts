/**
 * Utilitaires partagés par les tests de `RecoCard`.
 *
 * Le fichier de tests d'origine dépassait 500 lignes ; il a été scindé en deux
 * — la résolution des icônes de plateforme d'un côté, tout le reste de
 * l'autre. Ces trois utilitaires leur sont communs et vivent donc ici : un jeu
 * de rendu dupliqué diverge toujours, et les deux moitiés finissent par ne
 * plus tester la même carte.
 *
 * Ce n'est PAS un fichier de tests (vitest ne collecte que `*.test.ts`).
 */
import { experimental_AstroContainer as AstroContainer } from 'astro/container';
import { Window } from 'happy-dom';

import RecoCard from '../../src/components/RecoCard.astro';

export async function render(reco: Record<string, unknown>): Promise<string> {
  const container = await AstroContainer.create();
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return container.renderToString(RecoCard as any, { props: { reco } });
}

/**
 * Parse le HTML rendu pour raisonner sur la STRUCTURE (parenté, ordre) plutôt
 * que sur des sous-chaînes. L'agencement de la carte — qui est enfant de qui —
 * ne se vérifie pas honnêtement à coups d'`indexOf`. La carte est un `<li>` :
 * on l'enveloppe dans un `<ul>` pour que le parseur ne le déplace pas.
 *
 * Environnement `node` ici (cf. vitest.config.ts) : on instancie `Window`
 * explicitement au lieu de basculer tout le fichier en `happy-dom`, l'Astro
 * Container API n'ayant aucune raison de tourner dans un DOM simulé.
 */
/** Rendu avec props COMPLÈTES (sourceId, audio…), là où `render` ne passe
 *  que la reco. Les deux existent parce que la plupart des tests n'ont besoin
 *  que de la reco, et gagnent à ne pas déclarer le reste. */
export async function renderProps(props: Record<string, unknown>): Promise<string> {
  const container = await AstroContainer.create();
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return container.renderToString(RecoCard as any, { props });
}

export function parse(html: string): Document {
  const win = new Window();
  win.document.body.innerHTML = `<ul>${html}</ul>`;
  return win.document as unknown as Document;
}

export const baseReco = {
  id: 'ubm-0001',
  title: 'Mon spectacle',
  creator: 'Untel',
  types: ['spectacle'],
};
