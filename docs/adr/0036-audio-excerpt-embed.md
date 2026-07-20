# ADR 0036 — Embed audio extrait timecode (Phase 2 item #12)

- **Statut** : Accepté
- **Date** : 2026-06-11
- **Phase** : 2 — Vague 2 (différenciateurs)
- **Roadmap item** : #12 Embed audio extrait timecode

## Contexte

Reco indexe des recommandations de podcasts. Pour chaque mention validée on
dispose souvent d'un timecode (`HH:MM:SS`) et, selon la source du transcript,
soit d'une URL YouTube de l'épisode, soit d'une URL Acast vers la page
publique. Les autres sites de recos (Goodreads, Letterboxd, Babelio) renvoient
vers la plateforme de l'œuvre — **aucun** ne propose d'écouter directement le
passage où l'œuvre est évoquée.

C'est précisément le différenciateur Reco : « j'entends d'abord l'extrait,
je décide ensuite si ça me parle ».

## Décision

Pour chaque mention avec timecode, afficher un bouton « Écouter à T'm'S' » qui
révèle en place un lecteur :

1. **YouTube** (cas majoritaire) — `<iframe>` `youtube-nocookie.com/embed/<id>`
   avec `start=<seconds>`, `autoplay=0`, `rel=0`. L'iframe est rendue avec
   `data-src` plutôt que `src` ; le `src` n'est appliqué qu'au clic. Premier
   reveal = première requête réseau YouTube (lazy load explicite).
2. **Acast** (fallback) — pas d'embed standardisé exposé par Acast. On affiche
   un lien externe `target="_blank"` vers l'URL Acast existante.
3. **Aucune source utilisable** — composant rend `null`. Pas de bouton mort.

Côté code :

- `src/lib/audio/timecode.ts` — helpers purs (`parseTimecode`, `formatTimecode`,
  `formatTimecodeA11y`, `buildYoutubeEmbedUrl`, `extractYoutubeId`).
- `src/components/AudioExcerpt.astro` — composant principal (bouton +
  iframe lazy + fermeture).
- `src/components/AudioPlayer.astro` — wrapper bas niveau `<audio>` pour un
  futur cas Acast preview MP3. Non utilisé aujourd'hui.
- Intégration dans `MentionsTimeline.astro` (chaque mention avec timecode YT)
  et prop optionnelle `audio` dans `RecoCard.astro`.

## Alternatives écartées

- **`<audio>` MP3 direct sur Acast** : Acast n'expose pas d'URL audio stable
  sur la page publique. Bascule possible si l'API change.
- **Embed Spotify podcast** : limité aux podcasts hébergés Spotify (Un Bon
  Moment est sur Acast), pas applicable au corpus principal.
- **YouTube IFrame Player API (JS SDK)** : permettrait un scrubbing custom,
  mais ajoute ~85 Ko de JS, casse `prefers-reduced-motion`, complique la CSP.
  Le rapport coût/UX est défavorable pour un kit duplicable.
- **Web Audio API custom** : overkill (pas de besoin de mix, EQ, etc.).

## A11y (WCAG AA)

- `aria-label` du bouton déroule le timecode en clair :
  « Écouter cet extrait à 2 minutes 13 secondes — *Titre épisode* ».
- `aria-expanded` / `aria-pressed` synchronisés sur le state reveal.
- `aria-controls` pointe vers l'`id` de la région révélée.
- `<iframe title="…">` descriptif.
- Pas d'autoplay (`autoplay=0` côté URL ; jamais d'`<audio autoplay>`).
- Pas d'animation reveal (compatible `prefers-reduced-motion: reduce`).
- Fermeture renvoie le focus sur le bouton trigger.

## Performance & Privacy

- Domaine `youtube-nocookie.com` : aucun cookie YouTube avant interaction.
- `data-src` → `src` : zéro requête réseau YouTube tant que le visiteur ne
  clique pas.
- Fermeture vide `src` : coupe la lecture et les traceurs.
- Pas d'inline JS : compatible CSP stricte (la logique reveal est en
  `<script>` externe via délégation `data-audio-toggle`).

## Conséquences

### Positives

- Différenciateur UX clair vs concurrents.
- Zéro coût serveur (iframe externe).
- Privacy respectée (`nocookie`, lazy).
- Kit reste duplicable (helpers purs testés isolément).

### Négatives

- Dépendance YouTube : si la chaîne supprime l'épisode, l'iframe affiche un
  message d'erreur YouTube (acceptable — c'est aussi le cas du deep-link
  actuel).
- Pas de scrubbing fin (l'iframe nocookie ne permet pas de manipuler
  `currentTime` depuis le parent sans le SDK IFrame).

### Critères de bascule

- Si Acast expose une preview MP3 stable → activer `AudioPlayer.astro` en
  fallback à la place du lien externe.
- Si le besoin de scrubbing custom émerge → réévaluer l'intégration IFrame
  Player API.

## Tests

- `tests/audio/test_timecode_format.test.ts` — parse/format/extract.
- `tests/audio/test_youtube_url.test.ts` — URL embed nocookie, params start/end.
- `tests/audio/test_audio_excerpt.test.ts` — rendu conditionnel (YT / Acast / vide).
- `tests/audio/test_a11y_audio.test.ts` — aria-label lisible, expanded/pressed.

## Fichiers touchés

- `src/lib/audio/timecode.ts` (nouveau)
- `src/components/AudioExcerpt.astro` (nouveau)
- `src/components/AudioPlayer.astro` (nouveau)
- `src/components/MentionsTimeline.astro` (intégration)
- `src/components/RecoCard.astro` (prop `audio` optionnelle)
- `src/i18n/fr.ts` (clés `audio.*`)
- `vitest.config.ts` (`tests/audio/**`)
