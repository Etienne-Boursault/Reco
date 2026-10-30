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

### Rien de ce qu'on range dans `dist/` ne survit au build suivant

`astro build` vide `dist/` au début de chaque build. Le cache des cartes de
partage vivait dans `dist/.cache/og` : il n'avait **jamais** servi d'un build
à l'autre, ce qu'un fichier témoin a montré en une minute. Un cache se range à
la racine (`.cache/`, ignoré par git), où le `git reset --hard` du déploiement
ne le touche pas — et sa clé doit alors porter sur ce qui est **rendu**, pas
sur les données, sinon il ressert l'ancienne image après une retouche du
gabarit (ADR [0050](adr/0050-cartes-partage-cache-persistant.md)).

### `SITE_URL` manque dans un arbre de travail neuf

Le build exige `SITE_URL`. Un `git worktree add`, ou un agent lancé dans son
propre arbre, ne l'a pas : le build échoue avant d'avoir rien construit.
Lancer avec `SITE_URL=https://unebonnere.co npm run build`.

### Un déploiement coupe ~25 secondes, pas plus

Mesuré en sondant le site toutes les 2 s pendant un déploiement complet :
2 min 32 de bout en bout, dont **25 s** d'indisponibilité au tout dernier
moment, quand le processus redémarre. L'application sert pendant toute la
construction.

Si vous observez plusieurs minutes d'indisponibilité, ce n'est pas la durée
normale du build : **c'est que la construction a échoué**.

### Au runtime, le serveur ne connaît pas son propre domaine

Chez Infomaniak, la commande de démarrage ne définit pas `SITE_URL`, et le
proxy placé devant l'application ne transmet pas le domaine public :
`Astro.url` ne le porte pas non plus. Le tableau d'audience comptait donc
chaque clic interne comme une arrivée depuis `unebonnere.co`, en tête des
provenances. Ce qui doit connaître le domaine en production lit
**`Astro.site`**, fixé au build (PR #122).

### Une PR empilée meurt avec la branche qu'elle vise

Une PR ouverte sur la branche d'une autre PR n'est **pas** reciblée sur `main`
quand cette branche est supprimée par `gh pr merge --delete-branch` : GitHub
la ferme, et elle ne peut plus être rouverte. Il faut en ouvrir une nouvelle
depuis la même branche (#124 → #125), ou fusionner la première sans supprimer
sa branche.

Méthode qui marche (pile #129 → #133, 2026-10-22) : fusionner la première,
**recibler** la suivante sur `main` (`gh pr edit N --base main`) puis la
fusionner, et ainsi de suite ; ne supprimer les branches qu'à la fin.

### Une pile de PR n'a pas de CI

La CI ne se déclenche que sur les PR **vers `main`**. Dans une pile, seule la
première est testée ; les suivantes ne reçoivent que CodeRabbit, et un vert
« 1 pass » ne prouve rien. Pour tester la pile entière sans rien fusionner :
une PR **brouillon** de la dernière branche vers `main`, fermée dès la CI
terminée (#134). Vérifier ensuite que `main` fusionné est identique à l'arbre
testé (`git diff` vide).

---

## Interface

### Un style scopé n'atteint pas l'élément rendu par un composant enfant

Une règle du `<style>` d'un composant Astro ne s'applique qu'aux éléments
écrits dans ce composant. Les 44 px donnés au lien « ▶ YouTube » de la
chronologie n'ont jamais pris : le lien est rendu par `OutboundLink`. Aucune
erreur, aucun avertissement — seule une mesure dans le navigateur l'a montré.
Ancrer la règle : `.timeline :global(.tl-ts)`.

### Un grand titre peut avaler le lien qui le précède

Sur la page d'un invité, le nom en Bebas sur 7 rem, interligne 0,88, déborde
de sa boîte vers le haut. Venant après le lien « retour au podcast » dans le
document, il passait par-dessus et captait les clics : le lien était visible
et mort. Les liens de retour portent désormais `position: relative; z-index: 1`
(`global.css`). Pour vérifier, `document.elementFromPoint` au centre du lien
doit renvoyer le lien, pas le titre.

### Le défilement doux trompe les tests de clic

`scroll-behavior: smooth` fait qu'un `scrollTo` rend la main avant d'arriver.
Un test qui défile puis mesure ou clique tombe à côté. Dans Playwright,
`window.scrollTo({ top, behavior: 'instant' })`.

### `astro preview` survit à l'arrêt de sa tâche

Arrêter la tâche qui l'a lancé laisse le serveur Node en vie, port 4321
occupé — et `npm ci` échoue ensuite en `EPERM` sur les fichiers qu'il tient
ouverts. Trouver le processus par son port et l'arrêter.

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

## Modèles et mesures

### Un repli silencieux cache une erreur

La lecture des capacités d'un modèle (« accepte-t-il l'effort ? ») avait un
repli sur une règle tirée de son nom. Avec le SDK `anthropic` 1.11, les
capacités sont des objets, pas des dictionnaires : la lecture levait un
`TypeError` **à chaque fois**, le repli prenait le relais, et rien ne se voyait
— le message était au niveau `INFO`. Découvert par hasard dans le journal du
banc d'essai (#128). La même inspection a montré que l'API publie les dates de
retrait (`retires_at`, `deprecated_at`), alors que la documentation de #127
affirmait le contraire sans l'avoir vérifié.

> Un repli doit être rare. S'il sert à chaque appel, c'est une panne. Et une
> limite d'API s'affirme après avoir regardé la réponse, pas avant.

### Une méthode disparaît sans décision

En juin, les épisodes historiques étaient extraits **deux fois** (Haiku 4.5 et
gpt-4o-mini), et la relecture voyait leur accord (« confirmé par 2 LLM » : 856
recos sur 3 082). La chaîne de venus, écrite le 2026-09-17, n'a gardé qu'un
modèle — sans que le commit le dise —, et le passage à Opus 5 a été mesuré
contre des modèles **seuls**, jamais contre l'union des deux. L'éditeur croyait
la double extraction toujours en place un mois plus tard.

> Quand on réécrit un chemin, lister ce que l'ancien faisait et dire ce qu'on
> en abandonne.

### Un réglage déclaratif ne doit pas remplacer un contrôle

Première version de la cohorte de référence (#133) : un profil déclaré
(`RECO_PIPELINE_PROFILE`) remplaçait l'empreinte de configuration. Changer de
modèle sans renommer le profil aurait mêlé deux configurations dans les
moyennes, sans alerte. L'empreinte change d'elle-même : le profil n'est plus
qu'une étiquette.

### Une mesure ne doit pas coûter ce qu'elle mesure

Le journal de relecture (#132) compare l'état des recos avant et après chaque
action. Sa première version relisait le cache de la page **après** l'action :
elle rechargeait les ~3 000 recos que le handler venait volontairement
d'invalider. C'est un test du cache (`test_undo_save_sans_rien_a_annuler_invalide`)
qui l'a vu. La photo ne lit plus que les fichiers visés, plus le listage du
dossier.

### Deux processus qui créent une base SQLite se la disputent

Passer en journal WAL (`PRAGMA journal_mode=wal`) exige un verrou exclusif que
SQLite **n'attend pas**, même avec `busy_timeout` : deux processus qui ouvrent
la base neuve en même temps — la chaîne et la page de relecture, sur venus —
obtiennent « database is locked ». On ne change le mode que s'il diffère, avec
quelques nouvelles tentatives (`telemetry/store.py`). Et un point-virgule dans
un commentaire SQL coupe une instruction en deux quand on découpe un script à
la main.

### Une boucle de Whisper efface une recommandation, et aucun contrôle ne la voit

**À corriger plus tard** (constaté le 2026-10-30 sur S6-E07, rien n'est encore
modifié dans l'outillage).

Entre 01:29:52 et 01:30:40, la transcription longue a écrit « Frère. » 37
fois, une ligne par seconde. Le vrai passage tenait en 30 secondes : la
première partie de Louis Cattelat, puis la recommandation de Fiona Gianilla.
L'extraction ne pouvait pas la deviner ; l'éditeur l'a repérée à la relecture.

Pourquoi la chaîne n'a rien dit :

- `combler_trous` cherche un **saut** d'au moins 9 s entre deux lignes. Une
  boucle produit des lignes rapprochées : aucun saut, aucun candidat.
- Les 4 « passages muets » signalés sur Matrix étaient de **faux positifs** :
  réécoutés le 2026-10-30, ils contiennent un blind-test (00:40:14), une
  histoire de « dieu de l'arrache » (00:56:16), la fin de l'émission
  (01:32:16) et un échange sur le livre (00:03:17). Aucune recommandation
  perdue. Le message regardait donc au mauvais endroit.
- En silence, Whisper invente aussi des génériques : « Sous-titrage Société
  Radio-Canada » à 00:39:50.

Mesure sur les 7 épisodes de la saison 6 : 21 séquences d'au moins 4 lignes
identiques d'affilée, presque toutes de vraies répétitions parlées (4 à 7
lignes). Deux sont à vérifier : « C'est bon. » ×11 à 00:45:58 sur S6-E01, et
« Dark Matter. » ×6 à 01:24:16 sur S6-E07. La seule boucle longue est celle-ci.

Ce qui a rendu le passage : la réécoute de la fenêtre avec
`condition_on_previous_text=False` et `vad_filter=False`, beam 5, sur l'audio
retéléchargé (`clip_timestamps=[5385, 5450]`).

Pistes, dans l'ordre :

1. Dans `combler_trous` (ou à côté), repérer **N lignes identiques d'affilée**
   (N ≥ 8 suffit pour ne pas toucher aux répétitions parlées) et réécouter la
   fenêtre avec `condition_on_previous_text=False`.
2. Passer `condition_on_previous_text=False` à la transcription longue : c'est
   ce réglage qui entretient la boucle. À mesurer d'abord sur un épisode
   complet, car il peut dégrader la ponctuation (cf. l'amorce `hotwords`).
3. Dire dans le message Matrix quelles boucles ont été vues et réécoutées, et
   écarter les génériques connus (« Sous-titrage … »).

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

Le tableau d'audience, lui, a menti trois fois en affichant des chiffres
plausibles :

- **« 0 clic par visiteur »** : 39 clics pour 1 182 visiteurs font 0,033,
  arrondi au dixième. Le rapport est désormais donné pour 100 visiteurs.
- **Les survols comptaient comme des pages vues** : `prefetch: hover`
  d'Astro charge une page dès qu'on survole son lien. Le navigateur le dit
  (`Sec-Purpose: prefetch`, ou `Sec-Fetch-Mode` autre que `navigate`).
- **La moitié des « visiteurs » étaient des scripts** : un robot qui se fait
  passer pour Chrome ne contient pas « bot » dans son agent, mais n'envoie
  presque jamais `Accept-Language`. Indices concordants : 95 % « ordinateur »,
  pays de centres de données, presque tout sur l'accueil.

> Un tableau de bord ne tombe pas en panne : il affiche un chiffre plausible.
> Recoupez-le avec un signal indépendant (ici, les clics et les pays).
