/**
 * mesureNavigateur.ts : l'état de mesure d'audience gardé dans le navigateur
 * (« AU-2 B », 2026-11-27 ; précision d'Étienne, 11 h 19 : « transparent pour
 * l'utilisateur, il faut qu'il puisse opt-out plus facilement qu'en allant
 * dans une page difficile d'accès »).
 *
 * CE QUI EST GARDÉ (une seule clé `localStorage`, `reco.mesure`)
 * ---------------------------------------------------------------
 *  - `ne` : le jour de naissance de la mesure (AAAA-MM-JJ, UTC) ;
 *  - `jour` + `etapes` : les étapes vues CE jour-là seulement (page d'épisode,
 *    fiche œuvre), remises à zéro le lendemain ;
 *  - `ligne` : le nombre de pages où la ligne de première visite a été vue.
 * Pas de liste de jours : `ne` est lui-même un jour de visite, donc « a déjà
 * visité un jour antérieur » se lit `ne < aujourd'hui`.
 *
 * COMBIEN DE TEMPS
 * ----------------
 * 13 mois au plus, NON PROLONGÉS : `ne` n'est jamais réécrit par une visite
 * (lignes directrices de la CNIL du 17/09/2020 sur les traceurs de mesure
 * d'audience). À `ne` + 13 mois, tout l'état est supprimé puis recréé neuf.
 * Un `ne` dans le futur, illisible ou invalide fait recréer l'état.
 *
 * CE QUI NE SORT JAMAIS DU NAVIGATEUR (R-1)
 * -----------------------------------------
 * Ni `ne`, ni les jours, ni aucun aléa : aucun identifiant n'existe. Le
 * serveur ne recevra (tranche C2) que trois oui/non : `revenant`,
 * `aVuEpisode`, `aVuFiche` (ce jour-là).
 *
 * LE REFUS (R-2)
 * --------------
 * `refuser()` efface tout et ne garde que le choix « refusé », sans échéance
 * (garder le choix de la personne ne demande pas de consentement).
 * `accepter()` (« Réactiver ») repart d'un état neuf. Sous refus, Global
 * Privacy Control ou Do Not Track à « 1 » (`suiviRefuse`, la détection de
 * `signalVue.ts`), `noterPage` rend `null` : rien à envoyer, rien de stocké
 * (sous GPC ou DNT, ce qui l'était avant est effacé, le refus excepté). GPC et
 * DNT donnent l'état `'navigateur'`, sans « Réactiver ».
 *
 * STOCKAGE QUI LÈVE (navigation privée, quota, stockage coupé)
 * ------------------------------------------------------------
 * Aucune exception ne sort, et rien n'est journalisé : la mesure ne doit
 * jamais gêner la page (même choix que `signalVue.ts`). Le module se comporte
 * comme sans stockage : état `'indisponible'`, ligne jamais affichée, et
 * `noterPage` rend quand même les oui/non (`revenant` faux, étape de la page
 * courante seule). Choix : on envoie le signal quand même, car il est alors
 * aussi pauvre que celui d'AU-1 A (le chemin), sans rien de retenu sur la
 * personne ; l'état `'indisponible'` laisse le pied de page masquer
 * l'interrupteur, qu'il ne saurait pas tenir.
 *
 * LA LIGNE ET LE PIED D'ACCORD (R-13)
 * -----------------------------------
 * Une seule fonction d'état, `etat()`, que la ligne et l'interrupteur lisent.
 * Deux onglets ouverts à la première visite partagent le même état : un seul
 * `ne`, et la ligne ne dure pas plus de deux pages en tout.
 *
 * LE CLIC SORTANT (D1, R-1, 2026-11-27)
 * -------------------------------------
 * `ouiNon(chemin)` rend les trois mêmes oui/non au clic sur un lien d'œuvre
 * (`clicSortant.ts`), en LECTURE SEULE : elle ne crée ni ne modifie jamais
 * l'état, que seule `noterPage` crée. `null` sans état, sous refus, GPC, DNT
 * ou stockage coupé : le clic part alors sans oui/non.
 *
 * Ordre d'appel attendu (C2) sur une page mesurable : `noterPage`, puis
 * `ligneAAfficher`, puis `ligneVue` si elle est affichée. Les dépendances sont
 * injectées : le module ne touche ni à `window`, ni à l'horloge.
 */
import { suiviRefuse } from './signalVue';

/** Exportées : le test des mentions légales cite le code, pas une copie. */
export const CLE = 'reco.mesure';
/** La ligne reste sur deux pages. */
const PAGES_DE_LIGNE = 2;
export const MOIS_DE_VIE = 13;

export type Etape = 'episode' | 'fiche';
export type EtatMesure = 'active' | 'refusee' | 'navigateur' | 'indisponible';

export interface Signal {
  revenant: boolean;
  aVuEpisode: boolean;
  aVuFiche: boolean;
}

export interface Dependances {
  /** Une fonction : même l'accès à `window.localStorage` peut lever. */
  stockage: () => Storage;
  maintenant: () => Date;
  navigator: { globalPrivacyControl?: boolean; doNotTrack?: string | null };
}

interface Garde {
  ne: string;
  jour: string;
  etapes: Etape[];
  ligne: number;
}
type Contenu = { refus: true } | Garde | null;

const ETAPES: readonly string[] = ['episode', 'fiche'];

/** Les chemins de `src/pages/[source]/episode/[guid]` et `…/oeuvre/[itemId]`. */
export function etapeDuChemin(chemin: string): Etape | null {
  if (/^\/[^/]+\/episode\/[^/]+\/?$/.test(chemin)) return 'episode';
  if (/^\/[^/]+\/oeuvre\/[^/]+\/?$/.test(chemin)) return 'fiche';
  return null;
}

/** Un AAAA-MM-JJ qui existe vraiment (`toJSON` rend null pour une date invalide). */
const jourValide = (s: unknown): s is string =>
  typeof s === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(s) && new Date(`${s}T00:00:00Z`).toJSON() === `${s}T00:00:00.000Z`;

/** Le jour où la mesure née à `ne` prend fin : `ne` + 13 mois. */
function finDe(ne: string): string {
  const [a, m, j] = ne.split('-').map(Number);
  const fin = new Date(Date.UTC(a, m - 1 + MOIS_DE_VIE, j));
  // Un 31 janvier + 13 mois déborde : on retombe sur le dernier jour du mois visé.
  if (fin.getUTCDate() !== j) fin.setUTCDate(0);
  return fin.toJSON().slice(0, 10);
}

function lireContenu(brut: string | null, aujourdhui: string): Contenu {
  if (brut === null) return null;
  let o: Record<string, unknown> | null;
  try {
    o = JSON.parse(brut);
  } catch {
    return null;
  }
  if (o?.refus === true) return { refus: true };
  const ne = o?.ne;
  if (!jourValide(ne) || ne > aujourdhui || aujourdhui >= finDe(ne)) return null;
  const ligne = Number.isInteger(o?.ligne) ? Math.min(Math.max(o?.ligne as number, 0), PAGES_DE_LIGNE) : PAGES_DE_LIGNE;
  const etapes = o?.jour === aujourdhui && Array.isArray(o.etapes) ? o.etapes : [];
  return { ne, jour: aujourdhui, etapes: [...new Set(etapes.filter((e) => ETAPES.includes(e)))], ligne };
}

export function creerMesure(deps: Dependances) {
  const aujourdhui = () => deps.maintenant().toISOString().slice(0, 10);
  const refuseParLeNavigateur = () => suiviRefuse(deps.navigator);

  /** `undefined` : le stockage lève. `null` : aucun état valide (absent, expiré, illisible). */
  function lire(): Contenu | undefined {
    try {
      return lireContenu(deps.stockage().getItem(CLE), aujourdhui());
    } catch {
      return undefined;
    }
  }

  function ecrire(contenu: Contenu): void {
    try {
      deps.stockage().setItem(CLE, JSON.stringify(contenu));
    } catch {
      /* quota ou stockage coupé : on fait comme sans stockage */
    }
  }

  const neuf = (ligne: number): Garde => ({ ne: aujourdhui(), jour: aujourdhui(), etapes: [], ligne });

  /** Sous GPC ou DNT : efface l'état de mesure, garde seulement le refus. */
  function purger(): void {
    const contenu = lire();
    if (contenu && 'refus' in contenu) return;
    try {
      deps.stockage().removeItem(CLE);
    } catch {
      /* rien à effacer si le stockage est coupé */
    }
  }

  /** L'état unique que la ligne et l'interrupteur du pied de page lisent. */
  function etat(): EtatMesure {
    if (refuseParLeNavigateur()) return 'navigateur';
    const contenu = lire();
    if (contenu === undefined) return 'indisponible';
    return contenu && 'refus' in contenu ? 'refusee' : 'active';
  }

  /**
   * Note la page courante et rend les trois oui/non à envoyer, ou `null` s'il
   * ne faut rien envoyer (refus, GPC, DNT). La première page mesurable crée
   * l'état ; `ne` n'est ensuite jamais réécrit.
   */
  function noterPage(chemin: string): Signal | null {
    if (refuseParLeNavigateur()) {
      purger();
      return null;
    }
    const contenu = lire();
    if (contenu && 'refus' in contenu) return null;
    const garde = contenu ?? neuf(0);
    const { etapes, signal } = avecPage(garde, chemin);
    // Sans stockage, `contenu` est undefined : rien n'est écrit, `revenant` reste faux.
    if (contenu !== undefined) ecrire({ ...garde, etapes });
    return signal;
  }

  /**
   * Les trois oui/non pour un clic sortant (D1, R-1, 2026-11-27), en LECTURE
   * SEULE : seule `noterPage` crée l'état. `null` sans état, sous refus, GPC,
   * DNT ou stockage coupé : le clic part alors sans oui/non.
   */
  function ouiNon(chemin: string): Signal | null {
    if (refuseParLeNavigateur()) return null;
    const contenu = lire();
    return contenu && !('refus' in contenu) ? avecPage(contenu, chemin).signal : null;
  }

  /** Les étapes du jour, la page courante comprise, et le signal qui en découle. */
  function avecPage(garde: Garde, chemin: string): { etapes: Etape[]; signal: Signal } {
    const etape = etapeDuChemin(chemin);
    const etapes = etape && !garde.etapes.includes(etape) ? [...garde.etapes, etape] : garde.etapes;
    return {
      etapes,
      signal: {
        revenant: garde.ne < aujourdhui(),
        aVuEpisode: etapes.includes('episode'),
        aVuFiche: etapes.includes('fiche'),
      },
    };
  }

  function refuser(): EtatMesure {
    if (!refuseParLeNavigateur() && lire() !== undefined) ecrire({ refus: true });
    return etat();
  }

  /** « Réactiver » : état neuf, sans remontrer la ligne (la personne vient de choisir). */
  function accepter(): EtatMesure {
    if (!refuseParLeNavigateur() && lire() !== undefined) ecrire(neuf(PAGES_DE_LIGNE));
    return etat();
  }

  /** Change `ligne` de l'état existant ; sans état, ne crée rien. */
  function majLigne(f: (n: number) => number): void {
    const contenu = lire();
    if (contenu && !('refus' in contenu)) ecrire({ ...contenu, ligne: f(contenu.ligne) });
  }

  function ligneAAfficher(): boolean {
    if (etat() !== 'active') return false;
    const contenu = lire();
    return !!contenu && !('refus' in contenu) && contenu.ligne < PAGES_DE_LIGNE;
  }

  return {
    etat,
    noterPage,
    ouiNon,
    refuser,
    accepter,
    ligneAAfficher,
    /** La ligne vient d'être affichée sur une page de plus. */
    ligneVue: () => majLigne((n) => Math.min(n + 1, PAGES_DE_LIGNE)),
    /** Clic sur « OK » : la ligne ne reviendra plus. */
    fermerLigne: () => majLigne(() => PAGES_DE_LIGNE),
  };
}
