/**
 * sommaire.ts — la liste des galeries d'une source, avec leur nombre d'œuvres.
 *
 * POURQUOI CE MODULE EXISTE
 * -------------------------
 * Deux pages annoncent ces nombres : le sommaire interne `/[source]/galeries`
 * et, depuis l'audit d'interface du 2026-10-07, l'onglet « Par type » du
 * catalogue. Un compte réécrit à chaque endroit finit par diverger — c'est
 * déjà arrivé : le sommaire annonçait 450 films là où la page en montrait 198
 * (relecture du 2026-08-19). Les deux passent donc par ici, et ici passe par
 * `selectByType`, la fonction même qui remplit les galeries.
 */
import { publicMentions, selectByType, type ItemLike, type MentionLike } from './aggregate';
import { GALERIES_PAR_TYPE, PAGES_DEDIEES, type Galerie } from './typesGaleries';

export interface EntreeSommaire extends Galerie {
  /** Nombre d'œuvres que la page de la galerie affiche. */
  n: number;
  /**
   * Jusqu'à trois titres d'aperçu : les œuvres les plus citées de la galerie,
   * dans l'ordre même de sa page. Un titre n'apparaît que sur UNE carte : les
   * galeries se recoupent (Musique contient les albums, Livres et BD les BD),
   * et le même titre revenait d'une carte à l'autre — relevé sur les
   * maquettes de l'onglet le 2026-10-07. La galerie la plus fournie garde
   * le titre, les suivantes passent au suivant.
   */
  apercu: string[];
}

/** Nombre de titres d'aperçu par carte. */
const TITRES_PAR_CARTE = 3;

/**
 * Les galeries non vides, de la plus fournie à la moins fournie.
 *
 * Une galerie vide est ÉCARTÉE : sa page n'est pas construite, la lister
 * donnerait un lien mort.
 *
 * @param items    Toutes les œuvres (elles sont filtrées ici par mention).
 * @param mentions Les mentions DE LA SOURCE ; les `discarded` sont écartées
 *                 ici, comme sur les pages elles-mêmes.
 */
export function sommaireGaleries(
  items: readonly ItemLike[],
  mentions: readonly MentionLike[],
): EntreeSommaire[] {
  const publiques = publicMentions(mentions);
  const mentionnes = new Set(publiques.map((m) => m.itemId));
  const vus = items.filter((it) => mentionnes.has(it.id));
  const galeries = [...PAGES_DEDIEES, ...GALERIES_PAR_TYPE]
    .map((g) => ({ g, oeuvres: selectByType(vus, publiques, g.types) }))
    .filter(({ oeuvres }) => oeuvres.length > 0)
    .sort((a, b) => b.oeuvres.length - a.oeuvres.length);

  const dejaPris = new Set<string>();
  return galeries.map(({ g, oeuvres }) => {
    const apercu: string[] = [];
    for (const o of oeuvres) {
      if (apercu.length === TITRES_PAR_CARTE) break;
      const cle = o.title.toLocaleLowerCase('fr');
      if (dejaPris.has(cle)) continue;
      dejaPris.add(cle);
      apercu.push(o.title);
    }
    return { ...g, n: oeuvres.length, apercu };
  });
}
