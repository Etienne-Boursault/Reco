/**
 * Ce que `GET /api/bord` rend au tableau de bord de venus (tableau de bord,
 * R2 B du 27/11/2026 ; TB-1 C du 28/11/2026, l'audience au centre).
 *
 * UN MODULE PUR
 * -------------
 * Il reçoit deux lectures de `lireAudience` (7 et 30 jours) et les
 * signalements déjà lus, et choisit ce qui part. Il ne lit ni le disque ni
 * l'horloge : la route le fait pour lui.
 *
 * IL NE RECOMPTE RIEN
 * -------------------
 * Les chiffres sont ceux de l'agrégat, donc du tri de `classement.ts`, tels
 * quels : deux comptes écrits chacun de son côté finissent par diverger
 * (familles F2 et F10 du registre des constats). Un test vérifie que
 * `/audience` et `/api/bord` donnent les mêmes chiffres.
 *
 * L'ANCIEN TRI
 * ------------
 * Avant la bascule (premier jour complet qui porte des signaux), il n'y a pas
 * de colonnes : `tri` vaut `ancien`, `colonnes` vaut `null`, et seuls
 * `visiteurs` et `robots` ont un sens (la courbe humains/robots).
 *
 * LES SIGNALEMENTS (F15)
 * ------------------------
 * Le fichier d'un signalement porte le nom, l'adresse et le texte de la
 * personne qui l'a envoyé. Seuls l'identifiant, la reco, la catégorie et la
 * date sortent d'ici, champ par champ : jamais l'objet entier. Des
 * signalements illisibles sont dits `inconnu`, jamais « rien en attente ».
 */
import type { Agregat, Compte } from '../audience/agregat';
import type { Colonnes } from '../audience/classement';
import type { LectureAudience } from '../audience/vue';
import type { Report } from '../reports/types';

/** Les listes du tableau de bord : les 5 premières seulement. */
const PREMIERES = 5;

export type Tri = 'ancien' | 'trois-colonnes';

export interface FenetreBord {
  du: string | null;
  au: string | null;
  tri: Tri;
  bascule: string | null;
  panneSignal: string[];
  /** Sommées sur les jours d'après la bascule ; `null` avant. */
  colonnes: Colonnes | null;
  pagesVues: number;
  visiteurs: number;
  visitesRobots: number;
  clics: number;
  clicsPour100Visiteurs: number | null;
  pages: Compte[];
  /** Le nombre de pages de la fenêtre, pour que le rendu dise « + N autres » (F23). */
  pagesTotal: number;
  provenances: Compte[];
  provenancesTotal: number;
}

export interface JourBord {
  jour: string;
  tri: Tri;
  /** Visiteurs du jour (ancien tri avant la bascule, confirmés + incertains après). */
  visiteurs: number;
  /** Passages de robots du jour. */
  robots: number;
  colonnes: Colonnes | null;
}

export interface SignalementBord {
  id: string;
  recoId: string;
  categorie: string;
  /** ISO 8601, celle de l'envoi. */
  date: string;
}

export interface ResumeBord {
  /** ISO 8601 : l'heure où le résumé a été fait. */
  genere: string;
  perimetre: string;
  sept: FenetreBord | null;
  trente: FenetreBord | null;
  /** Les jours de la fenêtre de 7 jours qui ont des mesures, du plus ancien au plus récent. */
  jours: JourBord[];
  /** Le message d'une lecture en échec (7 jours d'abord) ; `null` si tout a été lu. */
  erreur: string | null;
  /**
   * `enAttente` : les 5 plus récents seulement ; `total` : combien attendent
   * (revue globale, S4). Un cache plus ancien n'a pas `total` : le côté Python
   * se rabat alors sur la longueur de la liste.
   */
  signalements: { etat: 'lu' | 'inconnu'; total: number; enAttente: SignalementBord[] };
}

function fenetre(a: Agregat | null): FenetreBord | null {
  if (!a) return null;
  return {
    du: a.du,
    au: a.au,
    tri: a.bascule ? 'trois-colonnes' : 'ancien',
    bascule: a.bascule,
    panneSignal: a.panneSignal,
    colonnes: a.colonnes,
    pagesVues: a.pagesVues,
    visiteurs: a.visiteurs,
    visitesRobots: a.visitesRobots,
    clics: a.clics,
    clicsPour100Visiteurs: a.clicsPour100Visiteurs,
    pages: a.topPages.slice(0, PREMIERES),
    pagesTotal: a.pagesDistinctes,
    provenances: a.provenances.slice(0, PREMIERES),
    provenancesTotal: a.provenancesDistinctes,
  };
}

/** Les signalements en attente, du plus récent au plus ancien. */
function enAttente(signalements: Report[]): SignalementBord[] {
  return signalements
    .filter((s) => s.status === 'pending')
    .map((s) => ({ id: s.id, recoId: s.recoId, categorie: s.category, date: s.submittedAt }))
    .sort((a, b) => Number(a.date < b.date) - Number(a.date > b.date));
}

function resumerSignalements(signalements: Report[] | null): ResumeBord['signalements'] {
  if (!signalements) return { etat: 'inconnu', total: 0, enAttente: [] };
  const attente = enAttente(signalements);
  return { etat: 'lu', total: attente.length, enAttente: attente.slice(0, PREMIERES) };
}

export function resumerBord({
  sept,
  trente,
  signalements,
  maintenant,
}: {
  sept: LectureAudience;
  trente: LectureAudience;
  /** Tous les signalements lus, ou `null` s'ils n'ont pas pu l'être. */
  signalements: Report[] | null;
  maintenant: Date;
}): ResumeBord {
  return {
    genere: maintenant.toISOString(),
    perimetre: sept.libelle,
    sept: fenetre(sept.donnees),
    trente: fenetre(trente.donnees),
    jours: (sept.donnees?.jours ?? []).map((j) => ({
      jour: j.jour,
      tri: j.colonnes ? 'trois-colonnes' : 'ancien',
      visiteurs: j.visiteurs,
      robots: j.robots,
      colonnes: j.colonnes,
    })),
    erreur: sept.erreur ?? trente.erreur,
    signalements: resumerSignalements(signalements),
  };
}
