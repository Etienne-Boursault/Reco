# Screencast script — "Ajouter ton podcast en 5 minutes"

> Script narratif pour le screencast d'onboarding (à enregistrer en
> 1920×1080, 60 fps, micro USB cardioïde). Durée cible : **5 minutes**.

## Setup avant enregistrement

- Terminal propre (zsh ou PowerShell, prompt minimal, font 16 pt).
- Browser propre (1 onglet vide).
- VS Code prêt (fenêtre Reco déjà ouverte).
- `.env` propre avec clés API (NE PAS afficher → flouter en post).
- Démo source : `mon-podcast` (slug court, visuel sur écran).

---

## 0:00 — 0:30 · Intro + démo finale (30 s)

**Visuel** : intro logo Reco animé (3 s), puis cut sur la démo finale —
le site live `/mon-podcast/` avec recos colorées.

**Voix off** :

> Reco est un kit open-source pour transformer ton podcast en catalogue
> des œuvres recommandées. RSS, transcription, extraction LLM, relecture
> humaine, site statique : tout est inclus. En 5 minutes, on ajoute un
> nouveau podcast et on le met en ligne. C'est parti.

---

## 0:30 — 1:00 · Quick start `docker compose up` (30 s)

**Visuel** : terminal, on tape les commandes.

```bash
git clone https://github.com/etienneboursault/reco.git
cd reco
cp .env.example .env
docker compose up
```

**Voix off** :

> On clone le repo, on copie le `.env.example`, et on lance Docker
> Compose. Au premier lancement le build prend 3 minutes ; là, c'est
> déjà fait. Le site démo de *Un Bon Moment* tourne sur `localhost:4321`,
> le review server sur `localhost:8000`.

**Visuel** : ouvrir browser sur les 2 ports. Montrer le site, montrer la review.

---

## 1:00 — 2:00 · Wizard `reco init` (1 min)

**Visuel** : terminal (split avec VS Code).

```bash
npx reco init
```

**Voix off** :

> Pour ajouter ton podcast, on lance le wizard. Nom, slug, URL du flux
> RSS, chaîne YouTube si tu en as une, les hôtes — et les trois couleurs
> de ton thème.

**Visuel** : montrer la validation WCAG AA s'afficher en vert.

> Le wizard vérifie automatiquement que le contraste respecte WCAG AA.
> Si tu mets du rose sur du blanc, il refuse et te propose une variante.

**Visuel** : ouvrir `src/content/sources/mon-podcast.json` dans VS Code.

> Le fichier généré, c'est la source unique de vérité. Tu peux le
> ré-éditer à la main si besoin.

---

## 2:00 — 3:00 · Build pipeline démo (1 min)

**Visuel** : terminal.

```bash
docker compose --profile pipeline run --rm reco-pipeline
```

**Voix off** :

> Le pipeline va chercher les épisodes RSS, les associe aux vidéos
> YouTube, lance la transcription Whisper, puis l'extraction LLM
> cross-validée Anthropic plus OpenAI. Les recos confirmées par les
> deux modèles sont marquées d'une étoile.

**Visuel** : log scrolle (accélérer en post). Couper sur le résultat —
review server qui affiche les nouvelles recos `draft`.

> Pour la démo on a un fixture qui court-circuite Whisper. En vrai
> compte 10 à 30 minutes selon la taille du catalogue.

---

## 3:00 — 4:00 · Personnaliser theme + manifeste (1 min)

**Visuel** : VS Code, on édite le source JSON.

**Voix off** :

> Les couleurs se changent dans le source JSON. La gamme tokens est
> dérivée automatiquement, contrast revérifié à chaque build.

**Visuel** : ouvrir `docs/manifeste-ethique.md`.

> Le kit livre un manifeste éthique opinioné : on évite Amazon et le
> groupe Bolloré, on privilégie les indépendants. Si ton fork diverge,
> tu édites ce fichier — c'est lui qui est linké en footer du site.

**Visuel** : montrer le site avec les nouvelles couleurs après rebuild.

---

## 4:00 — 5:00 · Déployer Netlify drop + félicitations (1 min)

**Visuel** : terminal.

```bash
npm run build
```

**Voix off** :

> Build statique, 5000 pages générées en 30 secondes.

**Visuel** : ouvrir <https://app.netlify.com/drop>, glisser `dist/`.

> Et drag-and-drop sur Netlify Drop. 30 secondes plus tard, le site est
> en ligne avec un sous-domaine `.netlify.app`.

**Visuel** : le site live, on clique une reco, ça ouvre la fiche.

**Voix off** :

> Voilà. Un fork prêt en 5 minutes. Toute la doc est dans `docs/tutorial/`.
> Pour aller plus loin : multi-source, search frontend, visitor reports,
> SSR adapter pour les fonctionnalités dynamiques.
>
> Le code est sous licence MIT. Fork, modifie, déploie. Si tu publies
> un fork, un lien en footer fait plaisir mais n'est pas obligatoire.

**Visuel** : carton de fin → URL GitHub + `docs/index.md`.

---

## Post-prod

- Sous-titres FR (hard-coded ou .vtt embarqué YouTube).
- Couper les blancs > 800 ms.
- Accélérer les segments de log (×4 à ×8).
- Watermark discret bas-droit avec URL repo.
- Intro/outro musique CC0 (pas de Bolloré, pas d'Amazon Music).

## Checklist enregistrement

- [ ] Mode "Do Not Disturb" activé.
- [ ] Notifications terminal/IDE désactivées.
- [ ] Browser sans extensions visibles.
- [ ] `.env` flouté en post-prod.
- [ ] Test audio 10 s avant prise (niveau -12 dB).
- [ ] Export master 1080p60 + version 720p compressée.
