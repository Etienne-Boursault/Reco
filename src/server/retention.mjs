/**
 * Durées de conservation — ce que la page de mentions légales promet.
 *
 * POURQUOI ICI
 * ------------
 * Les mesures (visites, clics) et les signalements s'écrivent sur le serveur
 * de production, dans `tools/output/`. Jusqu'au 2026-10-22, rien ne les
 * effaçait jamais. Une durée annoncée sans rien pour la faire respecter
 * serait une promesse fausse : c'est donc le serveur lui-même qui fait le
 * ménage, au démarrage puis une fois par jour.
 *
 * LES DEUX RÈGLES
 * ---------------
 * - Visites et clics : supprimés au bout de 13 mois, durée de référence de
 *   la CNIL pour la mesure d'audience. Le tableau de bord n'en lit que 30
 *   jours.
 * - Signalements : le signalement reste — il retrace une correction —, mais
 *   le nom et l'e-mail laissés par le visiteur sont effacés au bout de 12
 *   mois, du fichier comme de la notification Matrix (`retention-matrix.mjs`,
 *   passée par `server.mjs` dans `purges`).
 */
import { existsSync, readdirSync, readFileSync, renameSync, rmSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

export const MOIS_MESURES = 13;
export const MOIS_COORDONNEES = 12;
const JOUR_MS = 24 * 60 * 60 * 1000;

/** La date d'il y a `mois` mois, au format `AAAA-MM-JJ`. */
export function borne(maintenant, mois) {
  const d = new Date(maintenant);
  d.setUTCMonth(d.getUTCMonth() - mois);
  return d.toISOString().slice(0, 10);
}

/** Les sous-dossiers d'un dossier, ou rien s'il n'existe pas. */
function sousDossiers(dossier) {
  if (!existsSync(dossier)) return [];
  return readdirSync(dossier, { withFileTypes: true })
    .filter((e) => e.isDirectory())
    .map((e) => join(dossier, e.name));
}

/**
 * Supprime les fichiers quotidiens de visites et de clics antérieurs à la
 * borne. Seuls les noms `AAAA-MM-JJ.jsonl` sont touchés : un fichier au nom
 * inattendu n'est pas de la mesure, on n'y touche pas.
 */
export function purgerMesures(racine, maintenant = new Date(), mois = MOIS_MESURES) {
  const limite = borne(maintenant, mois);
  let supprimes = 0;
  for (const genre of ['audience', 'clicks']) {
    for (const dossier of sousDossiers(join(racine, 'tools', 'output', genre))) {
      for (const nom of readdirSync(dossier)) {
        const jour = /^(\d{4}-\d{2}-\d{2})\.jsonl$/.exec(nom)?.[1];
        if (jour && jour < limite) {
          rmSync(join(dossier, nom));
          supprimes += 1;
        }
      }
    }
  }
  return supprimes;
}

/**
 * Efface le nom et l'e-mail des signalements plus anciens que la borne.
 *
 * Écriture atomique (fichier temporaire puis renommage) : une coupure en plein
 * milieu ne doit pas laisser un signalement illisible.
 */
export function anonymiserSignalements(racine, maintenant = new Date(), mois = MOIS_COORDONNEES) {
  const limite = borne(maintenant, mois);
  let anonymises = 0;
  for (const dossier of sousDossiers(join(racine, 'tools', 'output', 'reports'))) {
    for (const nom of readdirSync(dossier).filter((n) => n.endsWith('.json'))) {
      const chemin = join(dossier, nom);
      let signalement;
      try {
        signalement = JSON.parse(readFileSync(chemin, 'utf8'));
      } catch {
        continue; // Illisible : ce n'est pas à la purge de le réparer.
      }
      const auteur = signalement?.submitter;
      const date = typeof signalement?.submittedAt === 'string' ? signalement.submittedAt.slice(0, 10) : null;
      if (!auteur || !date || date >= limite || (!('name' in auteur) && !('email' in auteur))) continue;
      delete auteur.name;
      delete auteur.email;
      writeFileSync(`${chemin}.tmp`, `${JSON.stringify(signalement, null, 2)}\n`, 'utf8');
      renameSync(`${chemin}.tmp`, chemin);
      anonymises += 1;
    }
  }
  return anonymises;
}

/**
 * Applique les deux règles maintenant, puis chaque jour.
 *
 * `purges` : purges asynchrones en plus (notifications Matrix), chacune
 * rendant le nombre d'éléments effacés.
 *
 * Une erreur est journalisée, jamais propagée : servir le site passe avant
 * le ménage. Le minuteur ne retient pas le processus (`unref`), pour ne pas
 * gêner l'arrêt propre au redéploiement.
 */
export function planifierRetention(racine, { journal = console, intervalleMs = JOUR_MS, purges = [] } = {}) {
  const passer = () => {
    try {
      const mesures = purgerMesures(racine);
      const signalements = anonymiserSignalements(racine);
      if (mesures || signalements) {
        journal.log(`[retention] ${mesures} fichier(s) de mesure supprimé(s), ${signalements} signalement(s) anonymisé(s)`);
      }
    } catch (err) {
      journal.error('[retention] échec :', err);
    }
    for (const purge of purges) {
      Promise.resolve()
        .then(purge)
        .then((effaces) => {
          if (effaces) journal.log(`[retention] ${effaces} notification(s) de signalement effacée(s)`);
        })
        .catch((err) => journal.error('[retention] échec :', err));
    }
  };
  passer();
  const minuteur = setInterval(passer, intervalleMs);
  minuteur.unref();
  return minuteur;
}
