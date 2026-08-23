/**
 * Le filet : servir une page correcte quand le site ne peut pas démarrer.
 *
 * POURQUOI CE MODULE EXISTE
 * -------------------------
 * `server.mjs` importait `dist/server/entry.mjs` en haut de fichier. Quand ce
 * fichier manque, le module ne se charge pas : le processus meurt AVANT
 * d'ouvrir le port. Le site n'est pas dégradé, il est mort — et l'hébergeur
 * sert alors sa propre page, en anglais, hors charte.
 *
 * Ce cas n'est pas théorique. Le 2026-08-21, une construction a échoué (une
 * police rangée en `devDependencies`, absente sous `npm ci --omit=dev`), et
 * comme Astro vide `dist/` AVANT de reconstruire, l'entrée n'existait plus.
 * Quarante minutes hors ligne.
 *
 * POURQUOI 503 ET PAS 404
 * -----------------------
 * `404` dit à un moteur de recherche que la page n'existe pas — il finit par
 * la désindexer. `503` dit « indisponible, reviens », et `Retry-After` dit
 * quand. C'est la différence entre une panne et une disparition.
 *
 * POURQUOI LA PAGE NE DÉPEND DE RIEN
 * ----------------------------------
 * Ni CSS externe, ni police distante, ni image : quand ce module sert, c'est
 * précisément que `dist/` est absent ou incomplet. Tout ce dont la page a
 * besoin est dans la chaîne qu'elle renvoie.
 */
import http from 'node:http';

/** Charte par défaut — celle de la source de référence. */
const THEME = {
  bg: '#0e0e10',
  surface: '#17171c',
  text: '#f6f4ee',
  muted: '#9a99a3',
  accent: '#ffd23f',
};

/** Échappe ce qui part dans le HTML. Les valeurs viennent d'un JSON de source. */
export function echapper(valeur) {
  return String(valeur ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

/**
 * La page servie pendant l'indisponibilité.
 *
 * Le texte évite deux écueils : parler technique à quelqu'un qui vient
 * écouter des recommandations, et laisser croire que le contenu est perdu.
 */
export function pageMaintenance({
  titre = 'Un Bon Moment',
  lien = 'https://www.youtube.com/@KyanKhojandi',
  libelleLien = 'Le podcast sur YouTube',
  theme = THEME,
} = {}) {
  const c = { ...THEME, ...theme };
  return `<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${echapper(titre)} — le site revient dans un instant</title>
<meta name="robots" content="noindex">
<style>
  :root { color-scheme: dark; }
  body {
    margin: 0; min-height: 100vh; display: grid; place-items: center;
    padding: 1.5rem; background: ${echapper(c.bg)}; color: ${echapper(c.text)};
    font-family: system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif;
    line-height: 1.6;
  }
  main {
    max-width: 32rem; background: ${echapper(c.surface)}; border-radius: 12px;
    padding: clamp(1.5rem, 5vw, 2.5rem);
  }
  h1 { margin: 0 0 1rem; font-size: clamp(1.4rem, 4vw, 1.9rem); line-height: 1.2; }
  .marque {
    margin: 0 0 1.5rem; color: ${echapper(c.accent)}; font-weight: 700;
    letter-spacing: 0.08em; text-transform: uppercase; font-size: 0.78rem;
  }
  p { margin: 0 0 1rem; color: ${echapper(c.muted)}; }
  a {
    display: inline-block; margin-top: 0.5rem; color: ${echapper(c.accent)};
    font-weight: 600; text-decoration: none;
  }
  a:hover, a:focus-visible { text-decoration: underline; }
  a:focus-visible { outline: 2px solid ${echapper(c.accent)}; outline-offset: 3px; }
</style>
</head>
<body>
<main>
  <p class="marque">${echapper(titre)}</p>
  <h1>Le site se remet en place.</h1>
  <p>Une mise à jour est en cours et ne s’est pas terminée comme prévu.
     Rien n’est perdu — revenez dans quelques minutes.</p>
  <a href="${echapper(lien)}">${echapper(libelleLien)} →</a>
</main>
</body>
</html>
`;
}

/**
 * Répond à toute requête par la page, en 503.
 *
 * Tout, sans exception : si `dist/` est incomplet, servir les quelques
 * fichiers qui restent donnerait un site à moitié fonctionnel, où certaines
 * pages marchent et d'autres non. Mieux vaut un message clair et unique.
 */
export function repondreMaintenance(req, res, options = {}) {
  const { retryAfter = 120, ...reste } = options;
  const corps = pageMaintenance(reste);
  // HEAD ne doit pas porter de corps, mais garde les en-têtes.
  const tete = {
    'Content-Type': 'text/html; charset=utf-8',
    'Content-Length': Buffer.byteLength(corps),
    'Retry-After': String(retryAfter),
    'Cache-Control': 'no-store',
  };
  res.writeHead(503, tete);
  res.end(req.method === 'HEAD' ? undefined : corps);
}

/** Crée le serveur dégradé, sans l'ouvrir. */
export function creerServeurMaintenance(options = {}) {
  return http.createServer((req, res) => repondreMaintenance(req, res, options));
}
