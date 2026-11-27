/**
 * signalVue.ts : le signal « page vue » envoyé par le navigateur
 * (AU-1 A, 2026-11-27).
 *
 * POURQUOI
 * --------
 * Une visite mesurée côté serveur ne dit pas si un navigateur a réellement
 * affiché la page : un robot qui sait demander du HTML passe pour un visiteur.
 * Une fois la page affichée, le navigateur envoie UN signal à `POST /api/vue`
 * (reçu par `src/lib/audience/signal.mjs`) : le chemin et trois oui/non tirés
 * de la mesure gardée dans le navigateur (`mesureNavigateur.ts`) : `revenant`,
 * `aVuEpisode`, `aVuFiche` (AU-2 B, R-1, 2026-11-27). Rien d'autre ne quitte
 * le navigateur : ni date de naissance de la mesure, ni identifiant. Le
 * serveur calcule lui-même l'empreinte du jour.
 *
 * CE QUI EST ASSUMÉ
 * -----------------
 * Un robot qui exécute le script ET ment (pas de `webdriver`, page « visible »)
 * passe pour un navigateur : le signal sépare les robots simples des navigateurs
 * réels, il ne prouve pas la présence d'un humain.
 *
 * QUAND IL PART
 * -------------
 * Une seule fois par document, jamais sur un retour par le cache avant-arrière
 * (aucun écouteur ne survit à l'envoi, et `pageshow` n'est pas écouté), et
 * seulement :
 *  - hors prérendu (`document.prerendering`, attente de `prerenderingchange`) ;
 *  - page visible (sinon au premier `visibilitychange` vers « visible ») ;
 *  - sans `navigator.webdriver` ;
 *  - si la mesure y consent : `mesure.noterPage` rend `null` sous refus de la
 *    personne, Global Privacy Control ou Do Not Track à « 1 » (R-2 et R-10), et
 *    alors rien ne part ;
 *  - sur une page mesurable : la garde de `pageMesurable`, la même que celle du
 *    clic sortant (`/meta` et pages `noindex`, ADR 0040 et ADR 0046, R-13).
 * `noterPage` est appelée AU MOMENT DE L'ENVOI, jamais au chargement : elle crée
 * l'état de la mesure (le « jour de naissance » du revenant), et un document
 * prérendu ou ouvert en arrière-plan qui n'est jamais affiché ne doit pas
 * compter comme une visite. L'envoi a lieu une fois par document : elle est
 * donc appelée une fois. Sous GPC ou DNT elle purge aussi l'état gardé, c'est
 * pourquoi ces réglages ne sont plus écartés d'emblée ici.
 * Toute erreur est avalée : ni `console.error`, ni rejet non géré.
 *
 * Le corps part en `text/plain` (celui de `sendBeacon` pour une chaîne) : le
 * serveur lit le corps comme du JSON quel que soit le type annoncé.
 */

interface Navigateur {
  sendBeacon?: (url: string, donnees?: BodyInit | null) => boolean;
  webdriver?: boolean;
  /** Pas encore dans lib.dom (spec GPC). */
  globalPrivacyControl?: boolean;
  doNotTrack?: string | null;
}

interface Document2 {
  visibilityState: string;
  /** Pas encore dans lib.dom (Speculation Rules). */
  prerendering?: boolean;
  querySelector(selecteur: string): { getAttribute(nom: string): string | null } | null;
  addEventListener(type: string, ecouteur: () => void, options?: { once: boolean }): void;
  removeEventListener(type: string, ecouteur: () => void): void;
}

/** Ce que le script lit de `mesureNavigateur.ts` (type local : pas de cycle d'import). */
interface Mesure {
  noterPage(chemin: string): { revenant: boolean; aVuEpisode: boolean; aVuFiche: boolean } | null;
}

export interface Dependances {
  navigator: Navigateur;
  mesure: Mesure;
  document: Document2;
  location: { pathname: string };
  fetch: (url: string, init: RequestInit) => Promise<unknown>;
}

const URL_SIGNAL = '/api/vue';

/**
 * La page doit-elle être mesurée ? Non pour `/meta` (annuaire du réseau, pas
 * d'audience) et pour les pages `noindex`. La regex du contenu est stricte
 * (`noindex`, `noindex,…`, `noindex …`) : un `description` qui parle de
 * « noindex » ne déclenche pas la garde par accident.
 */
export function pageMesurable(
  location: { pathname: string },
  document: Pick<Document2, 'querySelector'>,
): boolean {
  if (location.pathname === '/meta' || location.pathname.startsWith('/meta/')) return false;
  const contenu = (document.querySelector('meta[name="robots"]')?.getAttribute('content') ?? '')
    .trim()
    .toLowerCase();
  return !(contenu === 'noindex' || contenu.startsWith('noindex,') || contenu.startsWith('noindex '));
}

/**
 * Le navigateur refuse-t-il le suivi (Global Privacy Control, Do Not Track à
 * « 1 ») ? Partagée avec `mesureNavigateur.ts` (AU-2 B, 2026-11-27).
 */
export function suiviRefuse(
  navigator: Pick<Navigateur, 'globalPrivacyControl' | 'doNotTrack'>,
): boolean {
  return navigator.globalPrivacyControl === true || navigator.doNotTrack === '1';
}

/**
 * Câble l'envoi. Rend `false` si le signal est écarté d'emblée (page non
 * mesurable, robot déclaré), `true` s'il est armé (la mesure peut encore
 * refuser au moment de l'envoi).
 */
export function cablerSignalVue(deps: Dependances): boolean {
  const { navigator, document, location, fetch, mesure } = deps;
  if (navigator.webdriver === true || !pageMesurable(location, document)) return false;

  const envoyer = () => {
    try {
      const vu = mesure.noterPage(location.pathname);
      if (vu === null) return; // refus, GPC ou DNT : rien ne part
      const { revenant, aVuEpisode, aVuFiche } = vu; // champ par champ : rien d'autre ne sort
      const corps = JSON.stringify({ chemin: location.pathname, revenant, aVuEpisode, aVuFiche });
      if (navigator.sendBeacon?.(URL_SIGNAL, corps)) return;
      // `fetch` appelé détaché : `window.fetch` refuse un `this` étranger.
      fetch(URL_SIGNAL, {
        method: 'POST',
        headers: { 'Content-Type': 'text/plain;charset=UTF-8' },
        body: corps,
        keepalive: true,
      }).catch(() => {});
    } catch {
      /* silencieux : la mesure ne doit jamais gêner la page */
    }
  };

  const siVisible = () => {
    if (document.visibilityState === 'visible') return envoyer();
    const attendre = () => {
      if (document.visibilityState !== 'visible') return;
      document.removeEventListener('visibilitychange', attendre);
      envoyer();
    };
    document.addEventListener('visibilitychange', attendre);
  };

  if (document.prerendering) {
    document.addEventListener('prerenderingchange', siVisible, { once: true });
  } else {
    siVisible();
  }
  return true;
}
