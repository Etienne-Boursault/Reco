/**
 * Le tri de l'audience en trois colonnes : visiteurs confirmés, incertains,
 * robots (décision d'Étienne du 27/11, « AU-1 A »).
 *
 * Le tri porte sur des VISITEURS-JOURS (une empreinte, un jour) et sur leurs
 * visites. Il ne relie jamais deux jours : le sel change chaque jour.
 *
 * LA TABLE (R-6), lue dans l'ordre, pour chaque visite
 *   1. robot déclaré                         : robot
 *   2. sans langue                           : robot
 *   3. signal valide, adresse de particulier : confirmé
 *   4. adresse d'hébergeur                   : robot sans signal, incertain avec
 *   5. sinon                                 : incertain
 *
 * UN SIGNAL NE CONFIRME QU'AVEC SA PAGE (R-5). Il faut une visite du même
 * visiteur-jour, sur le même chemin, à une heure d'écart au plus. Les deux
 * horodatages sont arrondis à l'heure (`heureRonde`) : un écart réel de
 * quelques secondes devient 0 ou 1 h. La fenêtre est symétrique, car l'arrondi
 * et le décalage des horloges ne garantissent pas l'ordre. Un signal sans page
 * correspondante est orphelin et ne confirme rien. Une adresse d'hébergeur,
 * même avec signal, reste incertaine : un VPN ou un relais n'est pas un
 * particulier. Un visiteur `null` (pas de sel) n'est jamais confirmé.
 *
 * L'ANCIEN TRI. Une ligne sans champ `hebergeur` date d'avant la tranche A :
 * ni hébergeur ni confirmation possibles, elle suit l'ancien tri (robot
 * déclaré ou sans langue : robot ; sinon incertain).
 *
 * LA BASCULE (R-7). Avant le premier jour complet qui porte des signaux, on
 * garde l'ancien compte seul. Le premier jour de signaux est tenu pour
 * incomplet (le déploiement a eu lieu en cours de journée), sauf s'il est le
 * premier jour lu : `shortcut: la période lue décide, la bascule se déplace
 * avec elle, à figer si l'on garde un jour de bascule explicite`.
 *
 * RESTE ASSUMÉ
 *   - un robot qui exécute le script et ment passe pour confirmé ;
 *   - une adresse qui change dans la journée (mobile, Wi-Fi) rend le signal
 *     orphelin : le visiteur reste incertain, jamais confirmé à tort ;
 *   - un signal écrit après minuit UTC n'est jamais rattaché à une page de la
 *     veille : le sel a changé.
 */
export interface Signal {
  ts: string;
  nature: 'signal';
  chemin: string;
  hebergeur: boolean;
  visiteur: string | null;
}

/** Ce que le tri lit d'une visite. */
export interface LigneVisite {
  ts: string;
  chemin: string;
  robot: boolean;
  langue: string | null;
  hebergeur?: boolean;
  visiteur: string | null;
}

export type Classe = 'confirme' | 'incertain' | 'robot';

export interface Effectif {
  visiteursJours: number;
  visites: number;
}

export interface Colonnes {
  confirmes: Effectif;
  incertains: Effectif;
  robots: Effectif;
}

const HEURE = 3_600_000;
/** Sous ce nombre de visites, l'absence de signal n'est pas une panne. */
const MIN_VISITES_PANNE = 5;

/** `/a-propos` et `/a-propos/` sont la même page : une seule ligne. */
export function cheminNormalise(chemin: string): string {
  return chemin.length > 1 ? chemin.replace(/\/+$/, '') || '/' : chemin;
}

export function estSignal(ligne: object): ligne is Signal {
  return (ligne as { nature?: string }).nature === 'signal';
}

/** Les visiteurs dont un signal a sa page (même chemin, à une heure près). */
function visiteursConfirmes(visites: LigneVisite[], signaux: Signal[]): Set<string> {
  const pages = new Map<string, LigneVisite[]>();
  for (const v of visites) {
    if (v.visiteur) pages.set(v.visiteur, [...(pages.get(v.visiteur) ?? []), v]);
  }
  const confirmes = new Set<string>();
  for (const s of signaux) {
    const chemin = cheminNormalise(s.chemin);
    const quand = Date.parse(s.ts);
    const trouvee = (s.visiteur ? pages.get(s.visiteur) : undefined)?.some(
      (v) => cheminNormalise(v.chemin) === chemin && Math.abs(Date.parse(v.ts) - quand) <= HEURE,
    );
    if (trouvee) confirmes.add(s.visiteur as string);
  }
  return confirmes;
}

/** La colonne de chaque visite d'un jour, dans l'ordre des visites. */
export function classer(visites: LigneVisite[], signaux: Signal[]): Classe[] {
  const confirmes = visiteursConfirmes(visites, signaux);
  return visites.map((v) => {
    if (v.robot || !v.langue) return 'robot';
    if (v.hebergeur === undefined) return 'incertain';
    const signale = v.visiteur !== null && confirmes.has(v.visiteur);
    if (v.hebergeur) return signale ? 'incertain' : 'robot';
    return signale ? 'confirme' : 'incertain';
  });
}

const RANG: Record<Classe, number> = { confirme: 0, incertain: 1, robot: 2 };

/** Visites et visiteurs-jours de chaque colonne : la meilleure colonne emporte le visiteur. */
export function compterColonnes(visites: LigneVisite[], classes: Classe[]): Colonnes {
  const meilleure = new Map<string, Classe>();
  const visitesPar: Record<Classe, number> = { confirme: 0, incertain: 0, robot: 0 };
  visites.forEach((v, i) => {
    const c = classes[i];
    visitesPar[c]++;
    const vue = v.visiteur ? meilleure.get(v.visiteur) : undefined;
    if (v.visiteur && (!vue || RANG[c] < RANG[vue])) meilleure.set(v.visiteur, c);
  });
  const visiteursPar: Record<Classe, number> = { confirme: 0, incertain: 0, robot: 0 };
  for (const c of meilleure.values()) visiteursPar[c]++;
  const effectif = (c: Classe): Effectif => ({ visiteursJours: visiteursPar[c], visites: visitesPar[c] });
  return { confirmes: effectif('confirme'), incertains: effectif('incertain'), robots: effectif('robot') };
}

/** La somme des colonnes des jours qui en ont ; `null` si aucun n'en a. */
export function sommerColonnes(liste: (Colonnes | null)[]): Colonnes | null {
  const jours = liste.filter((c): c is Colonnes => c !== null);
  if (!jours.length) return null;
  const somme = (cle: keyof Colonnes): Effectif => ({
    visiteursJours: jours.reduce((n, c) => n + c[cle].visiteursJours, 0),
    visites: jours.reduce((n, c) => n + c[cle].visites, 0),
  });
  return { confirmes: somme('confirmes'), incertains: somme('incertains'), robots: somme('robots') };
}

/** Le premier jour complet qui porte des signaux ; `jours` du plus ancien au plus récent. */
export function dateDeBascule(jours: { jour: string; signaux: number }[]): string | null {
  const avecSignal = jours.filter((j) => j.signaux > 0).map((j) => j.jour);
  if (!avecSignal.length) return null;
  return avecSignal[0] === jours[0].jour ? avecSignal[0] : (avecSignal[1] ?? null);
}

/**
 * Les deux derniers jours complets (UTC) qui ont des visites de personnes mais
 * aucun signal : le script ne part plus, ou le serveur ne l'enregistre plus.
 */
export function joursEnPanne(
  jours: { jour: string; signaux: number; colonnes: Colonnes | null }[],
  bascule: string | null,
  aujourdhui: Date,
): string[] {
  if (!bascule) return [];
  const recents = [1, 2].map((n) => {
    const d = new Date(aujourdhui);
    d.setUTCDate(d.getUTCDate() - n);
    return d.toISOString().slice(0, 10);
  });
  return jours
    .filter((j) => recents.includes(j.jour) && j.jour >= bascule && j.signaux === 0)
    .filter((j) => j.colonnes && j.colonnes.confirmes.visites + j.colonnes.incertains.visites >= MIN_VISITES_PANNE)
    .map((j) => j.jour);
}
