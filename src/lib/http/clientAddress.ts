/**
 * Lecture défensive de `APIContext.clientAddress`.
 *
 * Astro **lève** (`ClientAddressNotAvailable`) à la LECTURE de `clientAddress`
 * quand la route est pré-rendue. Deux conséquences contre-intuitives :
 *
 *   1. `async ({ request, clientAddress }) => …` ne compile pas un accès
 *      inoffensif : la déstructuration LIT la propriété au moment de l'appel,
 *      donc AVANT tout `try` écrit dans le corps du handler. Un `try/catch`
 *      placé plus bas est alors purement décoratif.
 *   2. Il faut prendre le contexte entier et ne lire la propriété qu'à
 *      l'intérieur du `try`.
 *
 * Ce piège avait été identifié et documenté dans `src/pages/api/click.ts`,
 * mais jamais reporté sur `src/pages/api/report.ts` — qui remontait donc une
 * exception au lieu de retomber sur une IP neutre. Le correctif vit désormais
 * à un seul endroit : impossible de l'oublier au prochain endpoint.
 */

/** Contexte minimal accepté — n'importe quel `APIContext` en est un. */
export interface ClientAddressCarrier {
  clientAddress?: string;
}

/**
 * Renvoie l'adresse cliente, ou `null` si elle est indisponible.
 *
 * Ne lève jamais. La propriété n'est lue qu'une seule fois : la tester avant
 * de la lire déclencherait le getter deux fois — donc deux fois l'exception.
 *
 * Une chaîne vide est renvoyée telle quelle : « fournie mais vide » n'est pas
 * « indisponible », et seul l'appelant sait quoi en faire.
 */
export function tryClientAddress(ctx: ClientAddressCarrier): string | null {
  try {
    const ip = ctx.clientAddress;
    return ip ?? null;
  } catch {
    return null;
  }
}
