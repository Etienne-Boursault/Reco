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
  /** Absent des mesures d'avant le 2026-10-21 : elles restent comptées. */
  prechargement?: boolean;
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
  /** Pages préchargées au survol d'un lien, jamais comptées comme vues. */
  prechargements: number;
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
  prechargements: number;
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
   *
   * Pour 100 visiteurs, et non par visiteur : le rapport réel tourne autour de
   * 0,03. Arrondi au dixième, il s'affichait « 0 » le 2026-10-22 avec 39 clics
   * pour 1 182 visiteurs — un chiffre faux qui avait l'air d'une panne.
   */
  clicsPour100Visiteurs: number | null;
  /**
   * Clics écartés du ratio, faute de savoir qui est venu ce jour-là.
   *
   * Les deux mesures n'ont pas commencé le même jour : les clics étaient
   * enregistrés depuis le 2026-08-19, les visites depuis le 2026-08-25. Le
   * ratio divisait donc sept jours de clics par une journée de visiteurs.
   * Ce compteur permet à la page de dire ce qu'elle a laissé de côté plutôt
   * que de l'escamoter.
   */
  clicsHorsPeriode: number;
  topPages: Compte[];
  provenances: Compte[];
  appareils: Compte[];
  langues: Compte[];
  paysConnus: Compte[];
  /** `true` si aucune visite ne porte de pays : la mesure est absente. */
  paysIndisponible: boolean;
  erreurs404: Compte[];
  /** Requêtes de robots qui cherchent une faille (`/.env`, `/wp-login.php`). */
  sondes: number;
  plateformes: Compte[];
  dureeMedianeMs: number | null;
}

/**
 * Une page réellement consultée : ni préchargée au survol, ni en erreur.
 *
 * Les 404 d'un navigateur humain sont surtout des robots déguisés qui sondent
 * `/wp-login.php` ou `/.env` : ils restent dans « Liens morts qui circulent »,
 * pas dans la fréquentation.
 */
function estConsultation(v: Visite): boolean {
  return !v.prechargement && v.statut < 400;
}

/**
 * Une requête humaine : ni robot déclaré, ni requête sans langue.
 *
 * Un navigateur envoie toujours `Accept-Language` ; un script presque jamais.
 * Le 2026-10-22, la moitié des pages vues n'en portaient pas, venaient
 * « d'ordinateurs » aux États-Unis ou à Singapour et frappaient l'accueil :
 * des robots qui se font passer pour Chrome. Le critère se lit dans les
 * mesures déjà écrites, il s'applique donc aussi à l'historique.
 */
function estHumaine(v: Visite): boolean {
  return !v.robot && Boolean(v.langue);
}

/**
 * Une sonde de faille : un robot qui essaie `/.env`, `/.git/config`,
 * `/wp-login.php`. Ce ne sont pas des liens morts — personne ne les a jamais
 * publiés —, et ils remplissaient toute la liste des 404.
 */
const SONDE = new RegExp(
  [
    // Fichiers cachés : `/.env`, `/.git/config`, `/backend/.env`.
    String.raw`(^|/)\.[^/]`,
    // Extensions de code, de configuration ou d'archive : le site n'en sert aucune.
    String.raw`\.(php\d?|aspx?|jsp|cgi|sql|bak|old|zip|tar|gz|rar|7z|ya?ml|env|ini|conf|cfg|toml|properties|log|sh|py|pem|key)$`,
    // Noms que seuls les scanners demandent (`/env`, `/phpinfo`, `/Dockerfile`).
    String.raw`(^|/)(wp-[^/]*|cgi-bin|phpinfo|_profiler|phpmyadmin|credentials|dockerfile|env|actuator|server-status|vendor)(/|$)`,
  ].join('|'),
  'i',
);

export function estSonde(chemin: string): boolean {
  return SONDE.test(chemin);
}

/** `/a-propos` et `/a-propos/` sont la même page : une seule ligne. */
function cheminNormalise(chemin: string): string {
  return chemin.length > 1 ? chemin.replace(/\/+$/, '') || '/' : chemin;
}

/**
 * Le site lui-même n'est pas une provenance.
 *
 * Le serveur écarte la navigation interne en comparant le référent à
 * `SITE_URL` — absente de la commande de démarrage chez Infomaniak, si bien
 * que `unebonnere.co` arrivait en tête des provenances. La page passe donc
 * aussi l'hôte sous lequel on la consulte, pour nettoyer l'historique.
 */
function estInterne(provenance: string | null, hote: string | null): boolean {
  if (!provenance || !hote) return false;
  const racine = hote.replace(/^www\./, '');
  return provenance === racine || provenance.endsWith(`.${racine}`);
}

/**
 * Les personnes distinctes d'une journée : celles qui ont obtenu au moins une
 * page. Un préchargement compte — il suppose une page déjà ouverte, et vient
 * de la même adresse —, une erreur non.
 */
function compterVisiteurs(humaines: Visite[]): number {
  return new Set(
    humaines.filter((x) => x.statut < 400).map((x) => x.visiteur).filter(Boolean),
  ).size;
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
 * Les sources réellement mesurées, visites ET clics confondus.
 *
 * `sourceDuChemin` range sous `_site` tout ce qui ne commence pas par un
 * segment de source connue : l'accueil, les 404, les pages transverses. Cette
 * source n'est donc jamais déclarée dans `RECO_SOURCES` — il faut la découvrir
 * sur le disque, sinon le tableau de bord ignore la page d'entrée du site.
 */
export function sourcesDisponibles(racine: string): string[] {
  const dossiers = ['audience', 'clicks'].map((g) => join(racine, 'tools', 'output', g));
  const noms = new Set<string>();
  for (const dossier of dossiers) {
    if (!existsSync(dossier)) continue;
    for (const entree of readdirSync(dossier, { withFileTypes: true })) {
      if (entree.isDirectory()) noms.add(entree.name);
    }
  }
  return [...noms].sort();
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
  hoteDuSite = null,
}: {
  racine: string;
  /**
   * Une source, ou plusieurs à fusionner. Le tableau de bord passe la liste
   * complète : lire `un-bon-moment` seul cacherait l'accueil et les 404, qui
   * vivent sous `_site`.
   */
  sourceId: string | string[];
  nbJours?: number;
  aujourdhui?: Date;
  /** L'hôte du tableau de bord : ses propres pages ne sont pas une provenance. */
  hoteDuSite?: string | null;
}): Agregat {
  const sources = Array.isArray(sourceId) ? sourceId : [sourceId];
  const dossiers = sources.map((s) => ({
    visites: join(racine, 'tools', 'output', 'audience', s),
    clics: join(racine, 'tools', 'output', 'clicks', s),
  }));

  const borne = new Date(aujourdhui);
  borne.setUTCDate(borne.getUTCDate() - (nbJours - 1));
  const depuis = borne.toISOString().slice(0, 10);

  const jours = [
    ...new Set(
      dossiers.flatMap((d) => [...joursDisponibles(d.visites), ...joursDisponibles(d.clics)]),
    ),
  ].filter((j) => j >= depuis).sort();

  const visites: Visite[] = [];
  const clics: Clic[] = [];
  const parJour: Jour[] = [];

  for (const jour of jours) {
    const v = dossiers.flatMap((d) => lireJsonl<Visite>(join(d.visites, `${jour}.jsonl`)));
    const c = dossiers.flatMap((d) => lireJsonl<Clic>(join(d.clics, `${jour}.jsonl`)));
    visites.push(...v);
    clics.push(...c);

    const humaines = v.filter(estHumaine);
    parJour.push({
      jour,
      pages: humaines.filter(estConsultation).length,
      // Les identifiants ne sont comparés qu'À L'INTÉRIEUR d'une journée : le
      // sel change de portée chaque jour, deux jours ne se recousent pas.
      visiteurs: compterVisiteurs(humaines),
      robots: v.length - humaines.length,
      prechargements: humaines.filter((x) => x.prechargement).length,
      clics: c.length,
    });
  }

  const humaines = visites.filter(estHumaine);
  const consultees = humaines.filter(estConsultation);
  const introuvables = visites.filter((v) => v.statut === 404);
  // Additionner les visiteurs de chaque jour, et non dédoublonner sur la
  // période : un même identifiant d'un jour à l'autre ne serait qu'un hasard,
  // le sel changeant chaque jour.
  const visiteurs = parJour.reduce((n, j) => n + j.visiteurs, 0);

  // Un ratio n'a de sens que sur une période commune aux deux mesures. On ne
  // retient donc que les clics des jours où l'on sait aussi qui est venu.
  const joursAvecVisites = new Set(parJour.filter((j) => j.visiteurs > 0).map((j) => j.jour));
  const clicsComparables = parJour
    .filter((j) => joursAvecVisites.has(j.jour))
    .reduce((n, j) => n + j.clics, 0);

  return {
    du: jours[0] ?? null,
    au: jours[jours.length - 1] ?? null,
    jours: parJour,
    pagesVues: consultees.length,
    visiteurs,
    visitesRobots: visites.length - humaines.length,
    prechargements: humaines.filter((v) => v.prechargement).length,
    clics: clics.length,
    // La mesure qui approche le mieux la fonction du site — faire découvrir —
    // sans relier un clic à un visiteur. Arrondie au dixième.
    clicsPour100Visiteurs:
      visiteurs > 0 ? Math.round((clicsComparables / visiteurs) * 1000) / 10 : null,
    clicsHorsPeriode: clics.length - clicsComparables,
    topPages: compter(
      consultees.filter((v) => v.statut === 200).map((v) => cheminNormalise(v.chemin)),
    ),
    provenances: compter(
      consultees.map((v) => (estInterne(v.provenance, hoteDuSite) ? null : v.provenance)),
    ),
    appareils: compter(consultees.map((v) => v.appareil), 4),
    langues: compter(consultees.map((v) => v.langue), 8),
    paysConnus: compter(consultees.map((v) => v.pays), 12),
    paysIndisponible: consultees.length > 0 && consultees.every((v) => !v.pays),
    // Les 404 disent quels liens périmés circulent encore.
    erreurs404: compter(
      introuvables.filter((v) => !estSonde(v.chemin)).map((v) => cheminNormalise(v.chemin)),
    ),
    sondes: introuvables.filter((v) => estSonde(v.chemin)).length,
    plateformes: compter(clics.map((c) => c.category), 10),
    dureeMedianeMs: mediane(
      consultees.map((v) => v.dureeMs).filter((d): d is number => typeof d === 'number'),
    ),
  };
}
