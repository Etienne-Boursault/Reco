/* review_client_activite.js — temps de relecture ACTIF (télémétrie locale).
 *
 * Un battement part toutes les 15 s, seulement si l'onglet est visible ET
 * qu'une interaction (clic, touche, défilement, saisie) a eu lieu depuis moins
 * de 60 s. Onglet masqué ou inactif : rien ne part, le compteur s'arrête. Le
 * serveur fixe la valeur d'un battement (15 s) et écarte les doublons ; le
 * rapport fait l'union des intervalles (deux onglets ne comptent pas double).
 *
 * Rien ne quitte la machine : la page de relecture est locale. Le battement
 * porte une session tirée au hasard par l'onglet, la page (/ep, /doutes…) et
 * l'épisode affiché — ni texte, ni identité.
 */
(function () {
  "use strict";
  var TICK = 15000, IDLE = 60000;
  var derniere = Date.now();
  var session = (window.crypto && window.crypto.randomUUID)
    ? window.crypto.randomUUID()
    : String(Date.now()) + "-" + Math.random().toString(36).slice(2, 12);
  // Les POST de la page (Valider, Corriger…) portent la session : le journal
  // relie une décision au temps actif de l'onglet qui l'a prise.
  document.cookie = "reco_revue_session=" + session + "; path=/; SameSite=Strict";

  ["pointerdown", "keydown", "wheel", "scroll", "input", "touchstart"].forEach(function (nom) {
    window.addEventListener(nom, function () { derniere = Date.now(); },
                            { passive: true, capture: true });
  });

  function battre() {
    if (document.visibilityState !== "visible") return;
    if (Date.now() - derniere > IDLE) return;
    var params = new URLSearchParams(window.location.search);
    var corps = new URLSearchParams({
      session: session,
      page: window.location.pathname,
      guid: params.get("guid") || params.get("ep") || ""
    });
    fetch("/activite", { method: "POST", body: corps, keepalive: true,
                         credentials: "same-origin" }).catch(function () {});
  }
  window.setInterval(battre, TICK);
})();
