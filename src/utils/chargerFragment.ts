/**
 * Chargement à la demande de la vue « toutes les recommandations ».
 *
 * POURQUOI CE MODULE EXISTE
 * -------------------------
 * Cette vue pesait 2681 Ko et 24 887 balises — 96 % du document — alors qu'elle
 * est masquée au chargement. Elle arrive désormais au premier clic sur son
 * onglet, depuis `/[source]/recos-fragment`.
 *
 * La logique vit ici plutôt que dans le `<script>` du composant parce que v8
 * n'instrumente pas les scripts client des `.astro` : elle n'y compterait ni
 * au numérateur ni au dénominateur de la couverture, et pourrait casser sans
 * qu'aucun chiffre ne bronche. C'est la règle que la configuration de test du
 * dépôt énonce déjà pour `gridFilter.ts` et `search.ts`.
 *
 * CE QUI SE JOUE POUR L'ACCESSIBILITÉ
 * -----------------------------------
 * Le fragment est injecté dans un CONTENEUR ENFANT, jamais dans la section
 * entière. Une région `aria-live` doit exister dans le DOM avant que son
 * contenu ne change : remplacer la section détruirait la zone d'annonce en
 * même temps qu'on lui demande de parler, et rien ne serait dit.
 *
 * Sans ces annonces, activer l'onglet au lecteur d'écran donnait un silence
 * pendant la requête, puis mille deux cents cartes sans un mot — et un échec
 * réseau était indiscernable d'un onglet vide.
 */

/** Ce que le module a besoin de trouver dans la section. */
const SELECTEUR_CIBLE = '[data-recos-cible]';
const ID_STATUT = 'recos-statut';
const SELECTEUR_CARTES = '#reco-grid > *';

export type ResultatChargement = 'charge' | 'echec' | 'sans-url';

/**
 * Charge le fragment de `section.dataset.fragment` et l'injecte.
 *
 * @param section        la section `role="tabpanel"` qui porte `data-fragment`
 * @param apresInjection recâblage à faire une fois le contenu en place (les
 *                       filtres, qui ne peuvent pas être câblés avant que leurs
 *                       éléments existent)
 * @param recuperer      injecté pour les tests ; `fetch` en production
 */
export async function chargerFragment(
  section: HTMLElement,
  apresInjection: () => void = () => {},
  recuperer: typeof fetch = globalThis.fetch,
): Promise<ResultatChargement> {
  const url = section.dataset.fragment;
  if (!url) return 'sans-url';

  // Le fragment est injecté plus bas via innerHTML. L'URL vient d'un attribut
  // data-fragment posé au build, donc maîtrisée — mais rien dans le code ne le
  // garantit. On exige un chemin relatif : un data-fragment détourné ne peut
  // alors pas faire charger du HTML d'une autre origine.
  if (/^[a-z][a-z0-9+.-]*:|^\/\//i.test(url)) return 'sans-url';

  const cible = section.querySelector<HTMLElement>(SELECTEUR_CIBLE);
  const statut = document.getElementById(ID_STATUT);
  const dire = (message: string) => {
    if (statut) statut.textContent = message;
  };

  section.setAttribute('aria-busy', 'true');
  dire('Chargement des recommandations…');

  try {
    const reponse = await recuperer(url);
    if (!reponse.ok) throw new Error(String(reponse.status));
    const html = await reponse.text();
    if (cible) cible.innerHTML = html;
    apresInjection();
    const n = section.querySelectorAll(SELECTEUR_CARTES).length;
    // L'accord suit le nombre : « 1 recommandation affichée ».
    dire(n === 1 ? '1 recommandation affichée.' : `${n} recommandations affichées.`);
    return 'charge';
  } catch {
    // Le lien de repli reste en place — c'est un chemin qui MARCHE, il mène à
    // la page complète. Mais il faut le dire : sans message, l'onglet a
    // simplement l'air vide.
    dire('Le chargement a échoué. Le lien ci-dessous mène à la page complète.');
    return 'echec';
  } finally {
    section.setAttribute('aria-busy', 'false');
  }
}
