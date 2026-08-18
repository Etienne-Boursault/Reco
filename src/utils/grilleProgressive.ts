/**
 * grilleProgressive.ts — filtrer et afficher une grande grille sans la relire
 * entière à chaque frappe.
 *
 * CE QUI N'ALLAIT PAS
 * -------------------
 * `applyGridFilter` parcourait TOUTES les cartes à chaque passe et écrivait
 * `style.display` sur chacune, y compris celles dont l'état ne changeait pas.
 * Il relisait aussi leurs `dataset` — `card.dataset.types.split(',')` — à
 * chaque fois.
 *
 * Sur les 1 213 cartes de `/recos`, une passe coûtait 125 à 327 ms dans
 * Chrome. La page fait 96 000 pixels de haut et le navigateur a gelé deux
 * fois pendant les mesures du 2026-08-18.
 *
 * CE QUE CE MODULE FAIT AUTREMENT
 * -------------------------------
 *   1. L'INDEX est construit UNE FOIS. Les types deviennent un `Set`, le
 *      texte est lu une seule fois. Le filtrage travaille ensuite en mémoire,
 *      sans toucher au DOM.
 *
 *   2. L'ÉCRITURE EST DIFFÉRENTIELLE. On ne modifie que les cartes dont la
 *      visibilité change réellement. Passer de « titani » à « titanic » n'en
 *      change presque aucune ; l'ancienne version les réécrivait toutes, et
 *      chaque écriture invalide la mise en page.
 *
 *   3. LE RENDU EST PROGRESSIF. Seules les premières correspondances sont
 *      affichées ; la suite vient quand on descend.
 *
 * CE QU'IL NE FAIT PAS, ET POURQUOI
 * ---------------------------------
 * Il ne RETIRE jamais une carte du DOM. Les cartes non affichées sont
 * masquées, pas supprimées : c'est ce qui préserve le repli sans JavaScript
 * — la page `/[source]/recos` doit rester lisible sans script — et
 * l'indexation par les moteurs.
 *
 * Il ne réduit donc ni les 2,8 Mo de HTML ni les ~800 ms d'analyse du
 * document. Ce plafond-là ne peut tomber qu'en ne rendant pas les cartes côté
 * serveur, ce qui coûterait le repli sans JavaScript.
 */
import { fuzzyMatch } from './search';

/** Une carte, préparée pour être filtrée sans relire le DOM. */
interface Entree {
  el: HTMLElement;
  types: Set<string>;
  texte: string;
  /** Dernier état appliqué, pour n'écrire que les changements. */
  affichee: boolean;
}

export interface Critere {
  /** `all`, ou l'un des types de `data-types`. */
  type: string;
  /** Texte libre, comparé en tolérant les fautes de frappe. */
  terme: string;
}

export interface OptionsGrille {
  grille: HTMLElement;
  /** Région `aria-live` recevant le message de résultat vide. */
  statut?: Element | null;
  messageVide: string;
  /** Nombre de cartes révélées d'un coup. */
  lot?: number;
}

/** Assez pour remplir plusieurs écrans sans en calculer mille. */
const LOT_PAR_DEFAUT = 60;

export class GrilleProgressive {
  private readonly index: Entree[];
  private readonly statut: Element | null;
  private readonly messageVide: string;
  private readonly lot: number;
  /** Les correspondances du dernier filtre, dans l'ordre du document. */
  private retenues: Entree[] = [];
  /** Combien de retenues sont actuellement affichées. */
  private affichees = 0;

  constructor(options: OptionsGrille) {
    this.statut = options.statut ?? null;
    this.messageVide = options.messageVide;
    this.lot = options.lot ?? LOT_PAR_DEFAUT;
    this.index = Array.from(options.grille.children).map((el) => {
      const carte = el as HTMLElement;
      const types = carte.dataset.types;
      return {
        el: carte,
        // Un `Set` plutôt qu'un tableau : l'appartenance est le seul test
        // qu'on fera, des milliers de fois.
        types: new Set(types ? types.split(',') : []),
        texte: carte.dataset.search ?? '',
        // Toutes les cartes sont visibles dans le HTML initial — c'est ce que
        // voit un visiteur sans JavaScript.
        affichee: true,
      };
    });
  }

  /**
   * Applique un critère. Renvoie le nombre TOTAL de correspondances, qui peut
   * dépasser le nombre affiché : le compteur doit annoncer l'étendue du
   * corpus, pas la taille du lot.
   */
  filtrer(critere: Critere): number {
    const { type, terme } = critere;
    this.retenues = this.index.filter(
      (e) =>
        (type === 'all' || e.types.has(type)) &&
        (!terme || fuzzyMatch(terme, e.texte)),
    );
    // Un nouveau critère repart du premier lot : sinon, restreindre la
    // recherche laisserait l'écran plein de résultats d'avant.
    this.affichees = 0;
    this.reveler(Math.min(this.lot, this.retenues.length));

    if (this.statut) {
      this.statut.textContent = this.retenues.length === 0 ? this.messageVide : '';
    }
    return this.retenues.length;
  }

  /** Révèle le lot suivant. Renvoie le nombre de cartes ajoutées. */
  afficherPlus(): number {
    const cible = Math.min(this.affichees + this.lot, this.retenues.length);
    const ajoutees = cible - this.affichees;
    if (ajoutees > 0) this.reveler(cible);
    return ajoutees;
  }

  /** Combien de correspondances attendent encore d'être révélées. */
  resteAAfficher(): number {
    return this.retenues.length - this.affichees;
  }

  /**
   * La dernière carte affichée — celle qu'on observe pour savoir quand
   * révéler la suite. `null` quand tout est déjà là.
   */
  sentinelle(): HTMLElement | null {
    if (this.resteAAfficher() <= 0 || this.affichees === 0) return null;
    return this.retenues[this.affichees - 1].el;
  }

  /**
   * Porte l'affichage à `cible` cartes retenues, et masque tout le reste.
   *
   * On ne touche QUE ce qui change : écrire `style.display` invalide la mise
   * en page de l'élément, même quand la valeur est identique.
   */
  private reveler(cible: number): void {
    const doitEtreVisible = new Set<HTMLElement>();
    for (let i = 0; i < cible; i++) doitEtreVisible.add(this.retenues[i].el);

    for (const entree of this.index) {
      const visible = doitEtreVisible.has(entree.el);
      if (visible === entree.affichee) continue;
      // La chaîne vide, et non `block` : on rend la main à la feuille de
      // styles, une carte pouvant être en `flex` ou en `grid`.
      entree.el.style.display = visible ? '' : 'none';
      entree.affichee = visible;
    }
    this.affichees = cible;
  }
}
