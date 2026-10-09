/**
 * chapitres.ts — découper les recos d'un épisode en « moments » de l'écoute.
 *
 * POURQUOI CE MODULE EXISTE
 * -------------------------
 * La page épisode rangeait ses recos en trois sections par NATURE
 * (recommandations, œuvres des invités, œuvres évoquées). Or c'est l'ordre
 * de l'ÉCOUTE qui parle à quelqu'un qui a l'épisode dans les oreilles : ce
 * qu'on a cité en ouverture, ce qui revient dans le dernier quart d'heure.
 * Direction « Les chapitres », retenue parmi les maquettes du 2026-10-07 :
 * les recos se lisent de haut en bas, groupées en moments séparés par les
 * creux, et chaque creux est dit (« 24 minutes sans œuvre citée »).
 *
 * QUAND ON NE DÉCOUPE PAS
 * -----------------------
 * Le découpage n'a de sens que si TOUTES les recos de l'épisode ont un
 * minutage fiable. On renonce (et la page garde ses sections) dès que :
 *   - une reco n'a pas de minutage ;
 *   - un minutage n'est pas au format complet hh:mm:ss — le corpus porte
 *     encore des « mm:ss », et un format ambigu a déjà produit des
 *     minutages lus en heures (« 11:12:00 » pour 11 min 12 s, corrigé le
 *     2026-10-07) ;
 *   - un minutage dépasse la durée de l'épisode — le signe d'une telle
 *     erreur ;
 *   - il y a moins de deux recos : une seule n'a pas de chapitre.
 */

/**
 * Un creux au moins aussi long sépare deux moments : 12 minutes. À 10, S6·E3
 * coupait en deux un passage que l'écoute vit d'un tenant (10 min 42 s
 * entre deux œuvres) et annonçait « 10 minutes sans œuvre citée » — un
 * silence qui n'en est pas un dans un épisode d'une heure vingt.
 */
export const SEUIL_CREUX_S = 12 * 60;

/** Marge tolérée au-delà de la durée connue (générique, coupe de fin). */
const MARGE_FIN_S = 120;

const HHMMSS = /^(\d{1,2}):([0-5]\d):([0-5]\d)$/;

/** « 01:11:58 » → 4318 ; tout autre format → null. */
export function secondesStrictes(ts: string | null | undefined): number | null {
  const m = HHMMSS.exec((ts ?? '').trim());
  if (!m) return null;
  return Number(m[1]) * 3600 + Number(m[2]) * 60 + Number(m[3]);
}

/** « 4318 » → « 1:11:58 » ; « 303 » → « 5:03 » (affichage de la colonne). */
export function minutageCourt(s: number): string {
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const r = s % 60;
  const deux = (n: number) => String(n).padStart(2, '0');
  return h > 0 ? `${h}:${deux(m)}:${deux(r)}` : `${m}:${deux(r)}`;
}

export interface RecoMinutee<T> {
  reco: T;
  secondes: number;
}

export interface Moment<T> {
  titre: string;
  /** « 5:03 → 20:01 » */
  plage: string;
  recos: RecoMinutee<T>[];
  /** Creux qui SUIT ce moment, en minutes entières ; null pour le dernier. */
  creuxApresMin: number | null;
}

/**
 * Découpe les recos en moments, ou renvoie `null` quand la page doit garder
 * ses sections (cf. l'en-tête du module).
 *
 * @param duree Durée de l'épisode en secondes (`youtubeDuration`) ; sans
 *              elle, le dernier minutage en tient lieu.
 */
export function decouperEnMoments<T extends { timestamp?: string | null }>(
  recos: readonly T[],
  duree?: number | null,
): Moment<T>[] | null {
  if (recos.length < 2) return null;
  const minutees: RecoMinutee<T>[] = [];
  for (const reco of recos) {
    const s = secondesStrictes(reco.timestamp);
    if (s === null) return null;
    minutees.push({ reco, secondes: s });
  }
  minutees.sort((a, b) => a.secondes - b.secondes);
  const dernier = minutees[minutees.length - 1]!.secondes;
  const total = duree && duree > 0 ? duree : dernier;
  if (dernier > total + MARGE_FIN_S) return null;

  const groupes: RecoMinutee<T>[][] = [[minutees[0]!]];
  for (let i = 1; i < minutees.length; i++) {
    const ecart = minutees[i]!.secondes - minutees[i - 1]!.secondes;
    if (ecart >= SEUIL_CREUX_S) groupes.push([]);
    groupes[groupes.length - 1]!.push(minutees[i]!);
  }

  return groupes.map((g, i) => {
    const debut = g[0]!.secondes;
    const fin = g[g.length - 1]!.secondes;
    const suivant = groupes[i + 1];
    return {
      titre: titreDuMoment(debut, fin, total, groupes.length, i),
      plage: debut === fin ? minutageCourt(debut) : `${minutageCourt(debut)} → ${minutageCourt(fin)}`,
      recos: g,
      creuxApresMin: suivant ? Math.floor((suivant[0]!.secondes - fin) / 60) : null,
    };
  });
}

/**
 * Le nom d'un moment dit OÙ il tombe dans l'écoute, en mots : « Les vingt
 * premières minutes » se retient mieux que « 0:00 → 20:00 », qui reste
 * affiché à côté.
 */
export function titreDuMoment(
  debut: number,
  fin: number,
  total: number,
  nbMoments: number,
  index: number,
): string {
  if (nbMoments === 1) return 'Au fil de l’épisode';
  const minutes = (s: number) => Math.max(1, Math.ceil(s / 60));
  if (index === 0 && debut <= total * 0.15) {
    const n = minutes(fin);
    return n === 1 ? 'La première minute' : `Les ${n} premières minutes`;
  }
  if (index === nbMoments - 1 && fin >= total * 0.8) {
    const reste = total - debut;
    return reste <= 16 * 60 && reste >= 14 * 60
      ? 'Le dernier quart d’heure'
      : minutes(reste) === 1
        ? 'La dernière minute'
        : `Les ${minutes(reste)} dernières minutes`;
  }
  const milieu = (debut + fin) / 2;
  if (milieu >= total * 0.35 && milieu <= total * 0.65) return 'Au milieu de l’épisode';
  return `Vers la ${Math.round(milieu / 60)}e minute`;
}
