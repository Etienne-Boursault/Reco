/**
 * Le garde du tableau de bord.
 *
 * POURQUOI UNE CLÉ, ET PAS SEULEMENT `noindex`
 * --------------------------------------------
 * Le dépôt a déjà appris cette leçon, à ses dépens : `/[source]/reports`
 * rendait le nom et l'adresse e-mail des personnes qui signalent une erreur,
 * protégée par `noindex`, `robots.txt` et un filtre de sitemap. Ce ne sont que
 * des mesures de DÉCOUVRABILITÉ, jamais d'ACCÈS — et `robots.txt` publie
 * justement le motif d'URL qu'il prétend cacher (revue de sécurité du
 * 2026-07-29).
 *
 * Le tableau de bord n'expose pas de données personnelles — c'est tout l'objet
 * du module de mesure — mais il expose la fréquentation d'un site, ce qui
 * appartient à son éditeur. D'où une clé.
 *
 * CE QUE CETTE PROTECTION VAUT, ET CE QU'ELLE NE VAUT PAS
 * ------------------------------------------------------
 * La clé passe dans l'URL. C'est assumé : un tableau de bord doit s'ouvrir
 * depuis un signet, sur un téléphone, sans dialogue d'authentification. En
 * contrepartie elle apparaît dans l'historique du navigateur, et la page pose
 * `Referrer-Policy: no-referrer` pour qu'elle ne fuie pas par un lien sortant.
 * Ce n'est pas une authentification : c'est un secret partagé, du niveau d'un
 * lien de partage non listé. Pour des données plus sensibles, il faudrait
 * autre chose.
 *
 * Sans clé configurée, la page n'existe pas : mieux vaut une absence qu'une
 * porte ouverte par oubli.
 */
import { timingSafeEqual } from 'node:crypto';

/** Longueur minimale : en deçà, la clé se devine. */
export const LONGUEUR_MINIMALE = 16;

/** La clé attendue, ou `null` si le tableau de bord doit rester fermé. */
export function cleAttendue(env = process.env) {
  const cle = env.RECO_AUDIENCE_KEY;
  return typeof cle === 'string' && cle.length >= LONGUEUR_MINIMALE ? cle : null;
}

/**
 * Compare la clé fournie à celle attendue, sans fuite par le temps.
 *
 * `timingSafeEqual` exige deux tampons de même longueur : comparer les
 * longueurs d'abord révélerait celle de la clé, donc on compare des condensats
 * de longueur fixe — non, plus simple et sans dépendance : on complète le
 * tampon fourni à la longueur attendue. Une longueur différente échoue de
 * toute façon, mais en temps constant.
 */
export function cleValide(fournie, attendue) {
  if (typeof fournie !== 'string' || typeof attendue !== 'string') return false;
  if (attendue.length < LONGUEUR_MINIMALE) return false;

  const a = Buffer.from(attendue, 'utf8');
  const b = Buffer.alloc(a.length);
  Buffer.from(fournie, 'utf8').copy(b);

  // La comparaison de longueur vient APRÈS, et son résultat est combiné : le
  // temps de réponse ne dépend pas de l'endroit où la clé diverge.
  const memeContenu = timingSafeEqual(a, b);
  return memeContenu && Buffer.byteLength(fournie, 'utf8') === a.length;
}

/** Le tableau de bord est-il ouvert à cette requête ? */
export function acces(cleFournie, env = process.env) {
  const attendue = cleAttendue(env);
  if (attendue === null) return { ouvert: false, raison: 'non-configure' };
  if (!cleValide(cleFournie, attendue)) return { ouvert: false, raison: 'cle-invalide' };
  return { ouvert: true, raison: null };
}
