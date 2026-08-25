/**
 * Écriture des visites — un fichier par jour, une ligne par page vue.
 *
 * MÊME FORME QUE LES CLICS
 * ------------------------
 * `tools/output/clicks/` existait déjà, en JSONL quotidien. Les visites
 * prennent la même forme dans `tools/output/audience/` : un outil d'agrégation
 * qui sait lire l'un sait lire l'autre, et `tools/output/` est ignoré par git,
 * donc les données survivent au `git reset --hard` du déploiement.
 *
 * UNE ÉCRITURE NE DOIT JAMAIS CASSER UNE PAGE
 * -------------------------------------------
 * Ce module est appelé sur le chemin de chaque requête. Un disque plein, un
 * dossier en lecture seule, un descripteur épuisé : rien de tout cela ne doit
 * remonter jusqu'au visiteur. `enregistrer` avale donc ses erreurs et rend un
 * booléen — l'appelant peut le journaliser, jamais échouer dessus.
 */
import { appendFileSync, mkdirSync } from 'node:fs';
import { join, resolve } from 'node:path';

/** Racine des fichiers de visite. */
export function racineAudience(cwd = process.cwd()) {
  return resolve(cwd, 'tools', 'output', 'audience');
}

/** Le fichier du jour, en UTC — pour que le découpage soit stable partout. */
export function fichierDuJour(sourceId, date = new Date(), cwd = process.cwd()) {
  const jour = date.toISOString().slice(0, 10);
  return join(racineAudience(cwd), sourceId, `${jour}.jsonl`);
}

/**
 * Ajoute une ligne. Rend `true` si elle est écrite, `false` sinon.
 *
 * `appendFileSync` plutôt qu'un flux : une ligne courte sur un site à faible
 * trafic ne justifie pas de tenir un descripteur ouvert, et l'ajout est
 * atomique sous PIPE_BUF. Si le volume grandit, c'est ici — et seulement ici —
 * qu'il faudra revenir.
 */
export function enregistrer(evenement, sourceId, cwd = process.cwd(), journal = console) {
  try {
    if (!/^[a-z0-9_-]{1,128}$/.test(sourceId)) return false;
    const chemin = fichierDuJour(sourceId, new Date(evenement.ts), cwd);
    mkdirSync(join(racineAudience(cwd), sourceId), { recursive: true });
    const ligne = JSON.stringify(evenement) + '\n';
    if (Buffer.byteLength(ligne, 'utf8') > 4000) return false;
    appendFileSync(chemin, ligne, 'utf8');
    return true;
  } catch (err) {
    // Une seule fois : sur un disque plein, le journal se remplirait plus vite
    // que les données qu'on n'arrive plus à écrire.
    if (!enregistrer._prevenu) {
      enregistrer._prevenu = true;
      journal.warn?.('[audience] écriture impossible :', err?.message ?? err);
    }
    return false;
  }
}
