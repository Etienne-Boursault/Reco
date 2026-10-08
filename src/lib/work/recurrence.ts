/**
 * recurrence.ts — ce que la fiche d'une œuvre dit de son retour dans le
 * podcast : depuis quand on en parle, à quel rythme, et qui.
 *
 * POURQUOI CE MODULE EXISTE
 * -------------------------
 * Depuis l'audit d'interface du 2026-10-07, chaque carte de reco mène à la
 * fiche de son œuvre : on y arrive pour voir qu'une œuvre REVIENT. La
 * direction « La récurrence » des maquettes, retenue le même jour, le montre
 * en trois chiffres, une frise des mentions et un bloc « Qui en parle ».
 *
 * Tous les calculs vivent ici, au build, et non dans le gabarit : ils sont
 * testables, et le gabarit n'a plus qu'à placer des valeurs.
 *
 * Toutes les dates sont lues en UTC, comme ailleurs sur le site : sans cela,
 * l'année d'une mention du 1er janvier dépendrait du fuseau de la machine qui
 * construit le site.
 */
import type { JoinedMention } from './aggregator';
import { episodeLabel } from '../../utils/recoTypes';

/** Une mention est une RECOMMANDATION sauf si c'est une citation (œuvres
 *  d'invité incluses), comme le compte `recoCount` de l'agrégateur. */
export function estRecommandee(jm: JoinedMention): boolean {
  return jm.mention.kind !== 'citation';
}

function dateValide(jm: JoinedMention): Date | null {
  const d = jm.episode?.date;
  return d instanceof Date && !Number.isNaN(d.getTime()) ? d : null;
}

/** « mars 2020 » */
export function moisAnnee(d: Date): string {
  return d.toLocaleDateString('fr-FR', { month: 'long', year: 'numeric', timeZone: 'UTC' });
}

/** « 4 mai 2026 » */
function jourMoisAnnee(d: Date): string {
  return d.toLocaleDateString('fr-FR', {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
    timeZone: 'UTC',
  });
}

// ---------------------------------------------------------------------------
// La période
// ---------------------------------------------------------------------------

export interface Periode {
  debut: Date;
  fin: Date;
  /** Écart en années civiles (2020 → 2026 = 6). 0 : tout tient dans une année. */
  ans: number;
  /** Le grand chiffre : « 6 ans », « 1 an », ou l'année seule (« 2026 »). */
  chiffre: string;
  /** Sa légende : « de mars 2020 à mai 2026 », « en mai 2026 »… */
  legende: string;
}

/** De la première à la dernière mention datée ; `null` sans aucune date. */
export function periode(mentions: readonly JoinedMention[]): Periode | null {
  const dates = mentions.map(dateValide).filter((d): d is Date => d !== null);
  if (dates.length === 0) return null;
  const debut = new Date(Math.min(...dates.map((d) => d.getTime())));
  const fin = new Date(Math.max(...dates.map((d) => d.getTime())));
  const ans = fin.getUTCFullYear() - debut.getUTCFullYear();
  if (ans > 0) {
    return {
      debut,
      fin,
      ans,
      chiffre: ans > 1 ? `${ans} ans` : '1 an',
      legende: `de ${moisAnnee(debut)} à ${moisAnnee(fin)}`,
    };
  }
  const annee = String(fin.getUTCFullYear());
  const memeMois = debut.getUTCMonth() === fin.getUTCMonth();
  const moisDebut = debut.toLocaleDateString('fr-FR', { month: 'long', timeZone: 'UTC' });
  return {
    debut,
    fin,
    ans: 0,
    chiffre: annee,
    legende: memeMois ? `en ${moisAnnee(fin)}` : `de ${moisDebut} à ${moisAnnee(fin)}`,
  };
}

// ---------------------------------------------------------------------------
// La frise
// ---------------------------------------------------------------------------

export interface PointFrise {
  /** Position horizontale, en % de la largeur de la frise. */
  gauche: number;
  /** Rangée (0 = au ras de l'axe) : deux points trop proches s'empilent. */
  voie: number;
  recommandee: boolean;
  href: string;
  /** Nom accessible du point : « S5·E29 · 4 mai 2026 · recommandée ». */
  libelle: string;
}

export interface Frise {
  /** Une graduation par année, au milieu de l'année. */
  annees: { annee: number; gauche: number }[];
  points: PointFrise[];
  /** Nombre de rangées occupées (≥ 1) : la hauteur de la frise en dépend. */
  voies: number;
}

/**
 * Écart horizontal minimal entre deux points d'une même rangée, en fraction
 * de la largeur. Chaque point est une cible de 44 px : à 0,14, deux voisins ne
 * se chevauchent pas tant que la frise mesure au moins 315 px, soit la
 * largeur d'un téléphone de 360 px une fois les marges ôtées. La frise est
 * statique : l'empilement est calculé UNE fois, pour la plus petite largeur.
 */
export const ECART_MIN = 0.14;

/**
 * La frise des mentions datées, de janvier de la première année à la fin de
 * la dernière. `null` quand elles tiennent toutes dans une même année (une
 * frise d'une seule graduation ne montrerait rien) ou qu'aucune n'est datée.
 */
export function frise(
  mentions: readonly JoinedMention[],
  sourceId: string,
  ecartMin = ECART_MIN,
): Frise | null {
  const datees = mentions
    .map((jm) => ({ jm, d: dateValide(jm) }))
    .filter((x): x is { jm: JoinedMention; d: Date } => x.d !== null && x.jm.episode !== null)
    .sort((a, b) => a.d.getTime() - b.d.getTime());
  if (datees.length === 0) return null;
  const premiere = datees[0]!.d.getUTCFullYear();
  const derniere = datees[datees.length - 1]!.d.getUTCFullYear();
  if (premiere === derniere) return null;

  const debut = Date.UTC(premiere, 0, 1);
  const fin = Date.UTC(derniere + 1, 0, 1);
  const position = (t: number): number => ((t - debut) / (fin - debut)) * 100;

  const annees = [];
  for (let a = premiere; a <= derniere; a += 1) {
    annees.push({ annee: a, gauche: arrondi(position(Date.UTC(a, 6, 1))) });
  }

  // Empilement glouton : chaque point va dans la plus basse rangée où le
  // précédent est assez loin à gauche.
  const derniereParVoie: number[] = [];
  const points = datees.map(({ jm, d }) => {
    const x = position(d.getTime()) / 100;
    let voie = derniereParVoie.findIndex((prec) => x - prec >= ecartMin);
    if (voie === -1) {
      voie = derniereParVoie.length;
      derniereParVoie.push(x);
    } else {
      derniereParVoie[voie] = x;
    }
    const recommandee = estRecommandee(jm);
    const ep = jm.episode!;
    const numero = episodeLabel(ep);
    return {
      gauche: arrondi(x * 100),
      voie,
      recommandee,
      href: `/${sourceId}/episode/${ep.guid}`,
      libelle: [numero, jourMoisAnnee(d), recommandee ? 'recommandée' : 'évoquée']
        .filter(Boolean)
        .join(' · '),
    };
  });

  return { annees, points, voies: Math.max(1, derniereParVoie.length) };
}

function arrondi(n: number): number {
  return Math.round(n * 100) / 100;
}

// ---------------------------------------------------------------------------
// Qui en parle
// ---------------------------------------------------------------------------

export interface Voix {
  nom: string;
  /** Mentions où cette personne parle de l'œuvre. */
  n: number;
  /** n rapporté au total des mentions, en % (largeur de la barre). */
  part: number;
}

export interface QuiEnParle {
  voix: Voix[];
  /** Mentions sans `recommendedBy` : personne n'a pu être identifié. */
  sansAttribution: number;
  total: number;
  /** Vrai si une mention porte plusieurs noms : la somme dépasse alors le total. */
  aDesVoixCommunes: boolean;
}

/** « Kyan Khojandi & Navo » → ['Kyan Khojandi', 'Navo']. */
function personnes(recommendedBy: string | null | undefined): string[] {
  return (recommendedBy ?? '')
    .split(/\s*(?:&|,|;|\bet\b)\s*/)
    .map((p) => p.trim())
    .filter(Boolean);
}

export function quiEnParle(mentions: readonly JoinedMention[]): QuiEnParle {
  const total = mentions.length;
  const compte = new Map<string, number>();
  let sansAttribution = 0;
  let aDesVoixCommunes = false;
  for (const jm of mentions) {
    const noms = [...new Set(personnes(jm.mention.recommendedBy))];
    if (noms.length === 0) {
      sansAttribution += 1;
      continue;
    }
    if (noms.length > 1) aDesVoixCommunes = true;
    for (const nom of noms) compte.set(nom, (compte.get(nom) ?? 0) + 1);
  }
  const voix = [...compte.entries()]
    .map(([nom, n]) => ({ nom, n, part: total > 0 ? arrondi((n / total) * 100) : 0 }))
    .sort((a, b) => b.n - a.n || a.nom.localeCompare(b.nom, 'fr'));
  return { voix, sansAttribution, total, aDesVoixCommunes };
}

// ---------------------------------------------------------------------------
// Année par année
// ---------------------------------------------------------------------------

export interface GroupeAnnee {
  /** `null` : mentions dont l'épisode n'a pas de date. */
  annee: number | null;
  mentions: JoinedMention[];
}

/**
 * Les mentions regroupées par année, la plus récente d'abord, en gardant
 * l'ordre reçu à l'intérieur de chaque année. Les mentions sans date ferment
 * la liste.
 */
export function parAnnee(mentions: readonly JoinedMention[]): GroupeAnnee[] {
  const groupes = new Map<number | null, JoinedMention[]>();
  for (const jm of mentions) {
    const d = dateValide(jm);
    const annee = d ? d.getUTCFullYear() : null;
    const liste = groupes.get(annee) ?? [];
    liste.push(jm);
    groupes.set(annee, liste);
  }
  return [...groupes.entries()]
    .map(([annee, liste]) => ({ annee, mentions: liste }))
    .sort((a, b) => {
      if (a.annee === null) return 1;
      if (b.annee === null) return -1;
      return b.annee - a.annee;
    });
}
