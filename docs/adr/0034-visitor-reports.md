# ADR 0034 — Signalements visiteurs

- Statut : Acceptée
- Date : 2026-06-11
- Décideurs : équipe Reco (Phase 2 Vague 2 — item #16)

## Contexte

Le catalogue affiche des recommandations extraites par pipeline (IA + relecture
humaine). Malgré la validation interne, des erreurs restent visibles publiquement :
mauvaise œuvre rattachée à une reco, faute d'orthographe dans le titre, lien
marchand cassé, contenu jugé inapproprié, suggestion d'enrichissement.

Aucun canal n'est offert aux visiteurs pour remonter ces signalements. Les seules
options actuelles sont l'email (non structuré, perd le contexte de la reco) ou
GitHub (barrière technique, nominatif).

Contraintes :
- **Self-hostable** : le kit est duplicable, pas de dépendance externe payante.
- **Privacy-friendly** : pas de tracker tiers (RGPD), pas d'IP en clair stockée.
- **Anti-spam basique** : pas de captcha Google (privacy), pas de modération auto.
- **Statique-compatible** : le site est `output: 'static'` (Astro 5), un endpoint
  POST nécessite un adapter Node/serverless au déploiement.

Options évaluées :
- **reCAPTCHA Google** : transmet l'empreinte visiteur à Google. Écarté pour RGPD.
- **Disqus / Hyvor Talk** : injecté côté tiers, lourd, données hors-site. Écarté.
- **Email contact only** : pas structuré (pas de status workflow, pas de lien
  vers la reco), pas exploitable en pipeline. Écarté.
- **Form statique + endpoint Astro** : 100 % self-hostable, sortie JSON
  exploitable par un CLI admin. **Retenu**.

## Décision

- Page formulaire **statique** par reco : `/[source]/report/[recoId]` (build-time
  via `getStaticPaths`, `noindex`). Lien depuis chaque RecoCard (P2.x ultérieur).
- Endpoint POST `/api/report` :
  - Tagué `export const prerender = false;` — appelable uniquement en `astro dev`
    ou avec un adapter serveur (`@astrojs/node`, Vercel, Netlify…). En build
    statique, le fichier est ignoré (Astro émet un warning, attendu).
  - Le fork-guide documente l'ajout de l'adapter pour la prod.
- Anti-spam multi-couches :
  - **Honeypot** : champ `<input name="website" hidden tabindex="-1">` — rempli ⇒
    réponse 204 silencieuse (le bot croit avoir réussi).
  - **Math captcha** : « Combien font 3 + 7 ? ». Challenge généré server-side,
    signé HMAC-SHA256 + expiry 15 min, validé sans état serveur.
  - **Rate-limit** : 1 report / IP / 5 min, in-memory (Map hash IP). Skip
    `127.0.0.1`/`::1` en dev. L'IP n'est jamais persistée (hash SHA-256 tronqué).
- Storage : JSON files `tools/output/reports/<source>/<reportId>.json`, gitignoré.
- Queue admin `/[source]/reports` : page statique `noindex` listant les pending
  (lecture build-time). Pas d'action UI ⇒ usage CLI séparé.
- CLI `tools/manage_reports.py` : `--list`, `--show`, `--resolve`, `--dismiss`,
  `--export`, avec lockfile pipeline pour éviter les races avec d'autres scripts.
- Crédit contributeurs : `wantCredit` stocké dans le report. Page publique
  `/contributeurs` **hors scope de cet item**, à générer build-time dans un
  P2.x ultérieur depuis les reports `resolved` + `wantCredit=true`.

## Conséquences

- **Positives**
  - Aucune dépendance externe, pas de fuite RGPD.
  - Storage JSON ⇒ trivial à inspecter, sauvegarder, exporter.
  - Captcha math signé HMAC ⇒ pas d'état serveur (scalable, restart-safe).
  - CLI = workflow admin auditable, avec lockfile pipeline.
  - Honeypot + captcha + rate-limit = bonne couverture du spam de base.

- **Négatives**
  - Build statique : une page par `(source, reco)` ⇒ croissance linéaire du
    nombre de fichiers HTML. Acceptable jusqu'à ~10 k recos, à revisiter au-delà
    (bascule en `?reco=` côté client).
  - Rate-limit in-memory : reset à chaque redéploiement. Suffisant pour le volume
    cible (kit petite échelle).
  - Captcha math basique : un bot adversarial dédié passe. Acceptable tant qu'on
    reste sous 100 reports/jour.
  - Pas de modération automatique LLM ⇒ effort humain proportionnel au volume.

- **Critères de bascule**
  - > 100 reports/jour OU > 30 % de spam ⇒ ajouter une étape LLM (filtre toxicité
    via Anthropic/OpenAI déjà disponibles dans le pipeline) OU passer en
    reCAPTCHA opt-in (banner consent).
  - > 10 k recos ⇒ refactorer la page form en route unique `/[source]/report`
    avec `?reco=...` côté client (réduit le nombre de pages HTML).
  - > 1 instance ⇒ remplacer le rate-limit in-memory par un store partagé (Redis,
    fichier verrou).
