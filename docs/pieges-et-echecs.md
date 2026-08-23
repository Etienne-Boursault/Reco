# Pièges et échecs — ce qui n'a pas marché

Les tutoriels décrivent le chemin qui fonctionne. Celui-ci décrit les fossés
qui le bordent : chaque entrée est une chose qu'on a réellement cassée,
mesurée, puis corrigée sur ce dépôt. Rien ici n'est théorique.

À lire **avant** de lancer le pipeline sur votre podcast, pas après.

---

## Transcription

### Le modèle par défaut est trop petit

`tools/transcribe.py` porte `DEFAULT_MODEL = "small"`, et le tutoriel 3 le
reprend. Or sur les **110 épisodes** du corpus de référence, **110 ont été
transcrits en `large-v3`** (98) ou `large-v3-turbo` (12). Aucun n'a gardé le
défaut.

En dessous de `large`, sur du français conversationnel à plusieurs voix qui se
chevauchent, les noms propres deviennent inexploitables — et ce sont
précisément les noms propres qu'on cherche : un titre d'œuvre, un nom
d'auteur. Une recommandation dont le titre est mal transcrit est une
recommandation perdue, et rien en aval ne la rattrape.

> **Prenez `large-v3` dès le premier épisode.** Re-transcrire coûte plus cher
> que transcrire bien une fois : il faut aussi re-extraire, et re-relire.

### Ne jamais mélanger les sources audio

On transcrit depuis **la même source que celle qui sera ouverte par le
timecode**. YouTube par défaut, Acast seulement en repli.

Sinon un décalage apparaît — intro YouTube, sponsor — et le timecode tombe à
côté. La tentation est alors de « corriger » avec un offset calculé sur la
différence de durée : **cet offset est faux par construction**, car il suppose
que tout l'écart est en début de vidéo. Il ne l'est pas.

Le champ `transcriptSource` (`youtube` | `acast`) existe pour qu'on sache
toujours d'où vient un transcript.

### La diarisation ne résout pas le « qui recommande »

Les transcripts donnent les mots et leur horodatage, jamais qui parle. D'où
un champ `recommendedBy` souvent vide — c'est **délibéré**, pas un oubli.

`pyannote` a été testé à fond : **échec**. Il fusionne les voix masculines
proches, ce qui est exactement le cas d'un podcast à deux animateurs masculins.
Ne relancez pas cette piste sans idée neuve.

Ce qui marche, partiellement : une passe d'attribution **par le texte**, avec
une règle d'ancrage dur (la personne parle de sa propre œuvre, ou est nommée).
Mesuré sur trois épisodes contre vérité terrain :

| Cas | Exactitude |
|---|---|
| Épisode à invité **unique** | 100 % |
| Épisode à **2 invités ou plus** | ~80 % |

Les erreurs sont toutes des *inférences* (élimination par le genre ou le rôle) ;
aucun ancrage dur n'a jamais menti. Rendement final : 17 attributions sur 65
candidats, soit ~26 %. Bas, et assumé : **vide plutôt que faux**.

### Un GPU de 4 Go n'a qu'un seul locataire

Whisper turbo (~1,9 Go + cache KV) et un serveur LLM local (~2,2–3,8 Go) ne
tiennent pas ensemble. Arrêtez l'un avant de lancer l'autre.

Et surtout : un crash `cudaMalloc failed: out of memory` ou
`Abandon (core dumped)` au chargement **n'est pas un bug de vieille carte**.
C'est un manque de VRAM, le plus souvent un processus **zombie** d'un essai
interrompu qui squatte la mémoire :

```bash
nvidia-smi --query-compute-apps=pid,used_memory --format=csv
kill -9 <pid>
```

On a perdu du temps à incriminer l'architecture Maxwell. Le modèle tournait
très bien une fois la VRAM libérée.

---

## Rapprochement épisode ↔ vidéo

### Filtrer les extraits, sinon le matcher les préfère

Beaucoup de chaînes publient des **extraits** (4–17 min) *et* l'épisode complet
(≥ 60 min). Sans filtre de durée, le rapprochement tombe sur l'extrait, et tout
le pipeline transcrit 6 minutes au lieu de 90.

Le filtre `≥ 30 min` est en place dans `match_youtube.py`. Gardez-le.

### Les titres YouTube ne ressemblent pas aux titres RSS

Sur la chaîne de référence, les épisodes sont publiés sous des **titres de
format**, sans rapport avec le titre RSS :

| Motif YouTube | Exemple |
|---|---|
| `A Good Time with X` | `A Good Time with JEREMY FERRARI` |
| `THE JOHNNY DEPP GAME WITH X` | `… WITH FABIEN OLICARD AND VÉRINO` |
| `Guess the punchline with X` | `Guess the punchline with PAUL MIRABEL` |

Un rapprochement par similarité de titre échoue en silence sur ces cas. Prévoyez
une table de motifs connus, et vérifiez le résultat.

### `yt-dlp` renvoie les titres traduits en anglais

Piège coûteux : sans précision de langue, `yt-dlp` sert les **titres
auto-traduits**, et vous comparez un titre français à sa traduction anglaise.

```bash
yt-dlp --extractor-args "youtube:lang=fr" …
```

### Un multi-match silencieux écrase des données

Un `for ep in episodes: if mot_cle in ep.title` peut correspondre à **plusieurs**
épisodes. C'est arrivé : deux épisodes contenaient le même nom d'invité, et
l'un a été écrasé en croyant ne toucher que l'autre.

> **Levez une erreur dès qu'il y a plus d'un match.** Ne prenez jamais le
> premier « au cas où ».

### Deux épisodes au même numéro = un mauvais rapprochement

Quand deux épisodes partagent `(season, number)`, c'est presque toujours qu'une
même vidéo a été aiguillée sur deux épisodes RSS. L'effet est toxique : le
transcript **et les recommandations** de l'épisode mal rapproché décrivent le
contenu de l'autre vidéo.

Diagnostic : comparer `title` (RSS) et `youtubeTitle` par similarité après
normalisation ; le score le plus haut désigne le vrai. Sur le perdant, retirer
le rapprochement **et supprimer transcript + recommandations** — sinon les
fausses données restent.

---

## Enrichissement : ce que les API ne donnent pas

Vérifié empiriquement le 2026-07-31. À revérifier avant de bâtir dessus.

| API | État |
|---|---|
| **Spotify** | Inutilisable. Le jeton s'obtient (HTTP 200), puis **tous** les endpoints répondent 403 « Active premium subscription required for the owner of the app ». Coder dessus produit du code mort. |
| **TMDB → JustWatch** | Ne donne plus d'URL JustWatch, mais une URL `themoviedb.org`. Le champ reste utile (il liste les plateformes FR), mais l'appeler « JustWatch » est un mensonge — 145 valeurs du corpus portaient ce nom à tort. |
| **AlloCiné** | Aucune API publique. Ni scraping, ni fabrication d'URL. |

Le repli honnête est un **lien de recherche** : il n'affirme rien sur
l'identité de l'œuvre, contrairement à une URL de fiche devinée. Mais réservez-le
à l'outil de relecture — sur le site public, présenté comme la fiche, il
tromperait le visiteur.

### L'égalité de titre ne prouve pas l'identité

« Intouchables » a été rapproché d'un polar italien de 1969 dont le titre
français est aussi « Les Intouchables ». Contre-vérifier **année + réalisateur**
rattrape ce cas.

### `creator` n'est pas le réalisateur

Ce champ contient souvent un acteur, un studio ou une plateforme. Une
contre-vérification naïve créateur ↔ réalisateur produit **~80 % de faux
positifs**. Taux d'erreur résiduel après garde-fous : ~1 mauvais rapprochement
sur 126.

---

## Vérification des liens

**Un code HTTP 200 ne prouve rien.** YouTube répond 200 à n'importe quel
identifiant de playlist bien formé, y compris inventé. Le discriminant est la
présence d'un `<title>` — absent des coquilles vides, et situé à ~700 Ko dans
la page, derrière le bundle JavaScript.

Une première version du vérificateur rejetait Fnac Spectacles, Paramount+,
Qobuz et Wikipédia — tous valides. D'où trois verdicts et jamais deux :
**vivant** / **mort** / **inconnu**, ce dernier étant laissé passer et compté à
part.

---

## Build et déploiement

### Une dépendance de build en `devDependencies` tue la production

L'hébergeur installe avec `npm ci --omit=dev`. Toute dépendance nécessaire à la
**construction** doit donc être en `dependencies`.

Les polices `@fontsource/*`, importées par `src/styles/global.css`, étaient
rangées en `devDependencies`. Elles disparaissaient à l'installation :

```
[vite] Unable to resolve `@import "@fontsource/inter/400.css"`
```

Conséquence : Astro vide `dist/` **avant** de reconstruire, donc une
construction ratée ne laisse pas l'ancienne version en place — elle laisse le
site **mort**. Quarante minutes hors ligne.

Le job CI `build-prod` reproduit désormais l'hébergeur à l'identique et vérifie
que `dist/server/entry.mjs` existe à l'arrivée.

### `astro build` ne vérifie pas les types

Un build vert ne dit rien des types. `npx astro check` est un passage distinct,
et il attrape ce que le build laisse filer — cinq erreurs réelles au dernier
comptage, dont un commentaire placé au milieu d'une liste d'attributs, toléré
par le compilateur Astro et refusé par TypeScript.

### Un déploiement coupe ~25 secondes, pas plus

Mesuré en sondant le site toutes les 2 s pendant un déploiement complet :
2 min 32 de bout en bout, dont **25 s** d'indisponibilité au tout dernier
moment, quand le processus redémarre. L'application sert pendant toute la
construction.

Si vous observez plusieurs minutes d'indisponibilité, ce n'est pas la durée
normale du build : **c'est que la construction a échoué**.

---

## Déléguer à des agents

### Une consigne est un vœu ; un garde-fou refuse

Ce qui doit être vrai se met dans le code, pas dans le prompt. Le plafond de
six liens par carte est appliqué **à l'écriture** : aucune fiche ne le dépasse.
Les règles qui n'étaient que demandées ont régulièrement été contournées, sans
mauvaise volonté — un agent optimise ce qu'on lui décrit, pas ce qu'on espère.

### Aucun agent n'écrit dans le corpus

Ils rendent des candidats sourcés ; la vérification a lieu avant écriture. Sur
une campagne de vingt-trois agents en parallèle, cette règle a intercepté :

- un lien Deezer menant à **un autre podcast de la même animatrice** ;
- un jeu télévisé canadien de 1974 sur le point d'être posé sur une série de
  stand-up française, au seul motif d'un titre identique.

Le contrôle rattrape aussi l'éditeur : un lien rejeté à tort s'est avéré bon —
l'émission avait été renommée, et l'identifiant Apple déjà présent dans le
corpus le prouvait.

### Un agent qui tranche seul produit une erreur silencieuse

Toute incertitude doit aller dans un champ dédié (`agentReview.flags` +
`agentReview.note`), relu en une passe groupée. Un agent qui devine une
attribution incertaine fabrique une donnée fausse que plus rien ne signale ;
un agent qui la signale produit une décision à prendre.

### Écrire la politique éditoriale AVANT de déléguer

Sans règles écrites, deux agents rendent deux corpus incohérents, et le
désaccord ne se voit qu'à la publication. Sur ce projet, dix règles ont été
fixées après un **test à l'aveugle** — l'agent d'un côté, l'éditeur de l'autre,
sur les mêmes épisodes, puis comparaison. Détail dans
[`fork-guide.md`](fork-guide.md) §8 ter.

---

## Vérifier ce qu'on mesure

Deux fausses alertes ont coûté du temps sur ce dépôt, et toutes deux venaient
de l'outil de mesure, pas du système mesuré :

- `grep -c` compte les **lignes** contenant le motif, pas les occurrences.
  Le sitemap tient sur une seule ligne : il paraissait contenir 1 URL au lieu
  de 1377.
- `PIL.Image.getcolors(maxcolors=N)` renvoie `None` quand l'image compte
  **plus** de N couleurs — donc `None` veut dire « riche », pas « vide ». La
  condition lue à l'envers rejetait les 38 vraies favicons.

> Avant de conclure qu'un système est cassé, vérifiez la commande qui vous l'a
> fait croire.
