/**
 * Lecture et agrégation des mesures — visites et clics sortants.
 *
 * POURQUOI ON LIT À LA DEMANDE
 * ----------------------------
 * Un tableau de bord pré-calculé au build serait figé à la date du dernier
 * déploiement. Les fichiers sont du JSONL quotidien : quelques milliers de
 * lignes par jour au plus, que Node lit en quelques millisecondes. Le jour où
 * le volume l'exigera, c'est ici — et seulement ici — qu'il faudra intercaler
 * un cache ou une base.
 *
 * CE QUE CE MODULE NE FAIT PAS
 * ----------------------------
 * Il ne relie jamais deux visites entre elles. Les identifiants de visiteur
 * sont comptés par jour, dans un ensemble, puis oubliés — on obtient un
 * nombre, jamais une trajectoire.
 */
import { existsSync, readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';

export interface Visite {
  ts: string;
  chemin: string;
  statut: number;
  robot: boolean;
  appareil: string;
  provenance: string | null;
  langue: string | null;
  pays: string | null;
  visiteur: string | null;
  dureeMs: number | null;
}

export interface Clic {
  ts: string;
  url: string;
  category: string;
  sourceId: string;
  recoId: string | null;
  ref: string | null;
}

/** Un jour de mesure : ce que la courbe affiche. */
export interface Jour {
  jour: string;
  pages: number;
  visiteurs: number;
  robots: number;
  clics: number;
}

export interface Compte {
  cle: string;
  n: number;
}

export interface Agregat {
  /** Bornes réellement couvertes par les données lues. */
  du: string | null;
  au: string | null;
  jours: Jour[];
  pagesVues: number;
  visiteurs: number;
  visitesRobots: number;
  clics: number;
  /**
   * Clics vers une œuvre rapportés au nombre de visiteurs.
   *
   * PAS un pourcentage : un visiteur peut cliquer plusieurs fois, et la valeur
   * dépasse alors 100. Le premier jet l'affichait justement comme un « taux de
   * découverte » — les données d'essai donnaient 664 %, ce qui n'a aucun sens.
   *
   * Un vrai taux supposerait de savoir COMBIEN de visiteurs ont cliqué au
   * moins une fois, donc de relier un clic à un visiteur. C'est précisément ce
   * que le module de mesure refuse de faire : les clics ne portent aucun
   * identifiant de visiteur, et c'est délibéré.
   */
  clicsParVisiteur: number | null;
  topPages: Compte[];
  provenances: Compte[];
  appareils: Compte[];
  langues: Compte[];
  paysConnus: Compte[];
  /** `true` si aucune visite ne porte de pays : la mesure est absente. */
  paysIndisponible: boolean;
  erreurs404: Compte[];
  plateformes: Compte[];
  dureeMedianeMs: number | null;
}

/** Les jours disponibles pour une racine donnée, du plus ancien au plus récent. */
function joursDisponibles(dossier: string): string[] {
  if (!existsSync(dossier)) return [];
  return readdirSync(dossier)
    .filter((f) => /^\d{4}-\d{2}-\d{2}\.jsonl$/.test(f))
    .map((f) => f.slice(0, 10))
    .sort();
}

/**
 * Lit un fichier JSONL en ignorant les lignes illisibles.
 *
 * Une ligne tronquée — coupure au milieu d'une écriture — ne doit pas faire
 * échouer la lecture des milliers d'autres.
 */
function lireJsonl<T>(chemin: string): T[] {
  if (!existsSync(chemin)) return [];
  const lignes: T[] = [];
  for (const ligne of readFileSync(chemin, 'utf8').split('\n')) {
    if (!ligne.trim()) continue;
    try {
      lignes.push(JSON.parse(ligne) as T);
    } catch {
      // Ligne corrompue : on l'écarte sans bruit.
    }
  }
  return lignes;
}

function compter(valeurs: (string | null)[], limite = 12): Compte[] {
  const par = new Map<string, number>();
  for (const v of valeurs) {
    if (v === null || v === undefined || v === '') continue;
    par.set(v, (par.get(v) ?? 0) + 1);
  }
  return [...par.entries()]
    .map(([cle, n]) => ({ cle, n }))
    .sort((a, b) => b.n - a.n || a.cle.localeCompare(b.cle))
    .slice(0, limite);
}

function mediane(valeurs: number[]): number | null {
  if (!valeurs.length) return null;
  const tri = [...valeurs].sort((a, b) => a - b);
  const milieu = Math.floor(tri.length / 2);
  return tri.length % 2 ? tri[milieu] : Math.round((tri[milieu - 1] + tri[milieu]) / 2);
}

/**
 * Assemble le tableau de bord depuis les fichiers des `nbJours` derniers jours.
 *
 * `aujourdhui` est injectable : sans cela, les tests dépendraient de l'horloge
 * et se mettraient à échouer un jour donné.
 */
export function agreger({
  racine,
  sourceId,
  nbJours = 30,
  aujourdhui = new Date(),
}: {
  racine: string;
  sourceId: string;
  nbJours?: number;
  aujourdhui?: Date;
}): Agregat {
  const dossierVisites = join(racine, 'tools', 'output', 'audience', sourceId);
  const dossierClics = join(racine, 'tools', 'output', 'clicks', sourceId);

  const borne = new Date(aujourdhui);
  borne.setUTCDate(borne.getUTCDate() - (nbJours - 1));
  const depuis = borne.toISOString().slice(0, 10);

  const jours = [
    ...new Set([...joursDisponibles(dossierVisites), ...joursDisponibles(dossierClics)]),
  ].filter((j) => j >= depuis).sort();

  const visites: Visite[] = [];
  const clics: Clic[] = [];
  const parJour: Jour[] = [];

  for (const jour of jours) {
    const v = lireJsonl<Visite>(join(dossierVisites, `${jour}.jsonl`));
    const c = lireJsonl<Clic>(join(dossierClics, `${jour}.jsonl`));
    visites.push(...v);
    clics.push(...c);

    const humaines = v.filter((x) => !x.robot);
    parJour.push({
      jour,
      pages: humaines.length,
      // Les identifiants ne sont comparés qu'À L'INTÉRIEUR d'une journée : le
      // sel change de portée chaque jour, deux jours ne se recousent pas.
      visiteurs: new Set(humaines.map((x) => x.visiteur).filter(Boolean)).size,
      robots: v.length - humaines.length,
      clics: c.length,
    });
  }

  const humaines = visites.filter((v) => !v.robot);
  const visiteurs = new Set(humaines.map((v) => v.visiteur).filter(Boolean)).size;

  return {
    du: jours[0] ?? null,
    au: jours[jours.length - 1] ?? null,
    jours: parJour,
    pagesVues: humaines.length,
    visiteurs,
    visitesRobots: visites.length - humaines.length,
    clics: clics.length,
    // La mesure qui approche le mieux la fonction du site — faire découvrir —
    // sans relier un clic à un visiteur. Arrondie au dixième.
    clicsParVisiteur:
      visiteurs > 0 ? Math.round((clics.length / visiteurs) * 10) / 10 : null,
    topPages: compter(humaines.filter((v) => v.statut === 200).map((v) => v.chemin)),
    provenances: compter(humaines.map((v) => v.provenance)),
    appareils: compter(humaines.map((v) => v.appareil), 4),
    langues: compter(humaines.map((v) => v.langue), 8),
    paysConnus: compter(humaines.map((v) => v.pays), 12),
    paysIndisponible: humaines.length > 0 && humaines.every((v) => !v.pays),
    // Les 404 disent quels liens périmés circulent encore.
    erreurs404: compter(visites.filter((v) => v.statut === 404).map((v) => v.chemin)),
    plateformes: compter(clics.map((c) => c.category), 10),
    dureeMedianeMs: mediane(
      humaines.map((v) => v.dureeMs).filter((d): d is number => typeof d === 'number'),
    ),
  };
}
