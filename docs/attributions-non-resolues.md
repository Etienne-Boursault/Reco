# Attributions non résolues — les 13 recos `attribution_suspect` sans relecture humaine

Document de **constat**, pas de correction : aucun fichier de `src/content/` n'a
été modifié. Complète `docs/recommendedby-attribution-2026-07-21.md`.

## Périmètre et méthode

Sélection (script Python sur `src/content/recos/**/*.json`) :
`agentReview.flags` contient `attribution_suspect` **et** `agentReview.reviewedByHuman`
n'est pas `true` → **13 recos**, exactement les deux groupes attendus :
12 avec un `recommendedBy` renseigné mais non validé, 1 sans nom ni relecture.

Répartition complète du flag dans le corpus :

| État du flag | Nombre |
|---|---|
| `attribution_suspect` déplacé dans `flagsResolved` (passe éditeur) | 353 |
| Encore dans `flags`, relu par l'humain, `recommendedBy` volontairement vide | 35 |
| Encore dans `flags`, **non relu**, nom renseigné (les vrais suspects) | 12 |
| Encore dans `flags`, **non relu**, sans nom | 1 |

**Écart avec la consigne à signaler :** les 13 portent tous `status: "discarded"`.
Le filtre `status != "discarded"` de l'énoncé, appliqué à la lettre, renvoie 0 ligne
(les 4 recos `validated` encore flaguées sont, elles, relues par l'humain). Les 13
documentés ici sont donc les 12 + 1 décrits, indépendamment du `status`.

**Transcripts :** les 10 épisodes concernés ont tous un transcript
(`tools/output/transcripts/un-bon-moment/<guid>.txt`, format `[hh:mm:ss] texte`,
Whisper large-v3, **non diarizé**). Aucun cas « transcript introuvable ».
Deux recos (ubm-0599, ubm-1023) avaient été discardées en juillet pour
« transcript inexploitable » : ce motif est **caduc**, le transcript existe et est lisible.

## Décompte par conclusion

| Conclusion | Nombre | Recos |
|---|---|---|
| Nom à corriger (ancrage dur) | 4 | ubm-0083, ubm-0619, ubm-1023, ubm-3178 |
| Nom à renseigner (champ vide, ancrage dur) | 1 | ubm-0599 |
| Mention à écarter — ce n'est pas une reco | 8 | ubm-0124, ubm-0125, ubm-0126, ubm-2280, ubm-2403, ubm-2734, ubm-3139, ubm-3200 |
| Nom confirmé | 0 | — |

Sur les 8 « mention à écarter », le locuteur reste **indéterminable** dans 3 cas
(ubm-2403, ubm-2734, ubm-3200) : le texte permet seulement d'exclure le nom affiché,
pas de nommer le vrai locuteur. Dans tous les cas, `recommendedBy` doit rester vide.

## Tableau des 13 cas

| id | Œuvre | Épisode | Nom affiché | Ce que dit le transcript | Conclusion | Citation exacte |
|---|---|---|---|---|---|---|
| ubm-0083 | Soupe miso (spectacle) | « avec Laurent Baffie » (`63614bd0…`) — invité unique | Kyan Khojandi | À 00:58:22 les animateurs demandent à l'invité de recommander quelque chose ; il enchaîne sur les spectacles du Théâtre Déjazet, dont le sien. Auto-promo d'un **invité** → se valide avec l'invité. | **Nom à corriger : Laurent Baffie** (déjà porté par la canonique ubm-0038) | « [00:59:07] autre spectacle / [00:59:09] au théâtre de Deezer / [00:59:11] soupe miso / [00:59:14] de Laurent Baffi » puis « [01:01:16] j'ai écrit toujours tout seul » |
| ubm-0124 | Enter the Gungeon (titre corrompu « Hunter: The Gungeon ») | « avec Maxime et Grim » (`65c7a407…`) | Navo | Grim est interpellé par son prénom, puis répond : récit de son premier stream, avec un avis **négatif** sur le jeu. Ce n'est pas une prescription. | **Mention à écarter** ; le locuteur est Grim, pas Navo → nom à vider | « [00:39:03] Non, Grim, est-ce que tu te rappelles de ton premier stream ? » puis « [00:39:16] Je vois Hunter The Gungeon… » et « [00:39:27] c'était pas ouf » |
| ubm-0125 | Minecraft | idem ubm-0124 | Navo | Même tour de parole de Grim, suite immédiate de l'anecdote. « C'était très bien » porte sur l'expérience de stream, pas sur le jeu. | **Mention à écarter** ; locuteur Grim, pas Navo → nom à vider | « [00:39:31] Mais au moins, c'était le premier stream. Après, c'était Minecraft, beaucoup de Minecraft. Mais c'était très bien. » |
| ubm-0126 | Une île (série Arte) | idem ubm-0124 | Navo | Anecdote « j'ai été coupé au montage ». Le locuteur dit être alors en école de journalisme ; or c'est **Maxime Biaggi** qui, à 00:26:37-00:27:12, se décrit comédien passé par une école de journalisme. Ancrage indirect mais convergent ; en tout cas ce n'est pas Navo. | **Mention à écarter** (récit personnel, pas une reco) → nom à vider | « [00:44:08] D'être coupé au montage et d'avoir dit à tout le monde d'aller regarder. » / « [00:44:13] Non, d'une série qui s'appelait Une île, avec Laetitia Casta sur Arte, je crois. » / « [00:44:44] En plus, je suis en journalisme » à rapprocher de « [00:26:37] Et Maxime, t'as une formation de comédien. » + « [00:27:10] je fais une école de journalisme » |
| ubm-0599 | Alain Souchon (concert) | Spécial « Floodcast » (`c950798f…`, ep-003) | *(vide)* | Segment « vos photos Instagram » : il commence par Flaubert (= Florent Bernard) à 00:02:33 ; l'anecdote du concert court de 00:07:12 à 00:10:36, la comptable y appelle le locuteur « monsieur Bernard » ; l'animateur ne passe à l'autre invité qu'à 00:11:05. Éloge net et argumenté. | **Nom à renseigner : Florent Bernard** — et motif de discard (« transcript inexploitable ») caduc ; reste à arbitrer côté œuvre (artiste, pas d'œuvre précise) | « [00:07:20] En fait, je suis très fan de D'Alain Souchon. » / « [00:09:17] J'ai adoré ce concert. » / ancrage : « [00:10:28] Pris de m'excuser, monsieur Bernard. » puis « [00:11:05] Adrien Meignel. [00:11:06] Je suis allé voir tes trois dernières photos sur Instagram. » |
| ubm-0619 | Némir — clip « Ma vie » | « avec l'humoriste Fadily Camara » (`8099be2e…`) — invitée unique | Kyan Khojandi | L'animateur nomme l'invitée et lui demande sa reco ; elle enchaîne Evie McKinney puis Némir, puis sa propre chaîne. | **Nom à corriger : Fadily Camara** (déjà porté par la canonique ubm-3170) | « [00:49:00] Fadily, on a une petite tradition. [00:49:01] Est-ce que tu as une chaîne YouTube à recommander ? » puis « [00:50:15] J'écoute beaucoup de Némir. […] [00:50:21] Et je regarde son clip sur ma vie. » |
| ubm-1023 | Derby Girl (série) | Spécial « Floodcast » (`c950798f…`, ep-003) | Navo | Séquence des « actus » de fin : le premier invité annonce Derby Girl, on lui parle ensuite de **ses** stories (« les stories d'Adrien »), puis l'animateur passe explicitement à Flaubert. Auto-promo d'un **invité** → se valide. | **Nom à corriger : Adrien Ménielle** ; motif de discard (« transcript inexploitable ») caduc | « [01:50:40] La série Derby Girl dans laquelle j'ai joué qui va sortir en mars. » ; ancrage : « [01:51:28] les stories d'Adrien toujours un peu marrantes » puis « [01:51:40] Flopper, t'as une actue toi ? » |
| ubm-2280 | « Je suis condamné par l'espoir » / créateur « Sacha Boulanger » | « avec Marina et Panayotis » (`65846581…`) | Kyan Khojandi | La phrase n'est pas un titre : c'est un fragment de discussion à 00:18:30. Le livre discuté est le roman de Panayotis Pascot, annoncé en intro (« La prochaine fois que tu mordras la poussière »). « Sacha Boulanger » n'apparaît nulle part (seul « Sacha Baron Cohen », dans un jeu à 00:51:59). | **Mention à écarter** — artefact d'extraction : ni œuvre ni auteur réels ; à ne pas restaurer | « [00:18:30] c'est de l'empathie envers ton daron je suis condamné par l'espoir et celui d'une résolution pour nous deux » ; intro : « [00:00:56] Panayotis vient de sortir son premier roman [00:01:01] qui s'appelle la prochaine fois que tu mordras la poussière » |
| ubm-2403 | Upright Citizens Brigade (titre corrompu « Upgrade Citizen Brigade ») | « avec Laurie et Pablo » (`65241146…`) | Laurie Peret | Laurie est **celle qu'on interroge** : c'est elle qui explique les matchs d'impro à la française. L'exemple américain vient de son interlocuteur, qui vient de poser la question précédente — un animateur selon toute vraisemblance, mais aucun ancrage nominal. Exemple rhétorique, aucune prescription. Confirme aussi que le timestamp « 10:32:00 » est un artefact pour 00:10:32. | **Mention à écarter** ; attribution « Laurie Peret » contredite, vrai locuteur **indéterminable** → nom à vider | « [00:10:02] Et à chaque fois, c'est des scènes de quoi ? » (l'interlocuteur) puis « [00:10:22] Parce que je sais qu'aux États-Unis ou au Canada, l'impro, ils ne le font pas du tout par match. […] [00:10:32] Par exemple, tous les gens de chez Upgrade Citizen Brigade, tu sais, il y a Amy Poehler » |
| ubm-2734 | Vine (plateforme) | « avec Pierre Croce et Amixem » (`a7ff74e4…`) | Navo | La question est adressée aux **invités** (« vous ») et la réponse vient d'un invité, propriétaire du chien Polo — les animateurs, eux, demandent « Polo, c'est un bulldog, non ? ». Donc pas Navo ; lequel des deux invités, impossible à trancher (aucun prénom prononcé). Vine est cité en comparaison nostalgique avec TikTok, puis comme contre-exemple (« j'ai peur que ça finisse comme Vine »). | **Mention à écarter** (mention instrumentale) ; locuteur **indéterminable** parmi les invités → nom à vider | « [00:33:49] Vous le faites parce qu'il faut le faire, vous le faites par passion. » / « [00:33:52] Moi, quand j'en ai fait, c'était pendant le confinement […] comme Vine à l'époque. » / « [00:35:16] Vine, c'était très créatif. [00:35:19] Je pense que c'était la plateforme la plus créative. » / « [00:35:29] j'ai peur que ça finisse comme Vine » |
| ubm-3139 | L'Île de la Tentation | Baptiste Lecaplain et Camille Lavabre (`6a40008f…`) | Greg Romano | « Greg Romano » est le meneur d'un jeu récurrent (chansons aux paroles réécrites, à deviner) : il est appelé et salué comme tel à 00:56:03. Le passage à 00:57:39 est l'**énoncé de la devinette**, pas un avis. | **Mention à écarter** (mention de jeu) ; « Greg Romano » n'est pas un prescripteur → nom à vider | « [00:56:03] est ce que greg […] romano est avec nous salut greg romano » puis « [00:57:33] c'est un choc mental puis une émission de télé [00:57:39] réalités l'île de la tentation en 2003 sur la chaîne tf1 » |
| ubm-3178 | Chaz (chaîne, transcrit « Chaises ») | « avec Yvick (Mister V) et Freddy Gladieux » (`a7c99d90…`, ep-007) | Navo | L'animateur nomme Yvick et lui demande sa reco ; la réponse suit immédiatement. | **Nom à corriger : Yvick (Mister V)** (déjà porté par la canonique ubm-0643) | « [01:17:24] Yvi que t'as une recommandation de chaîne YouTube à un artiste que tu veux booster ? » puis « [01:17:30] C'est un mec qui s'appelle Chaises ! [01:17:31] Mais c'est un comédien et pareil dans l'absurde et il me bute de rire ! » |
| ubm-3200 | Soupa Kitcho (Guillaume Grandot) | « avec Alice David et Bérengère Krief » (`8fea089a…`, ep-018) | Kyan Khojandi | Name-drop d'un ami dans une digression sur le surf. Le locuteur désigne une œuvre accrochée **dans le studio**, derrière son interlocuteur : c'est donc un animateur — Kyan ou Navo, rien ne permet de trancher. Un animateur n'est de toute façon pas un prescripteur tiers, et la mention est instrumentale. | **Mention à écarter** ; attribution « Kyan Khojandi » plausible mais **non prouvée** → nom à vider | « [01:19:17] J'ai mon pote, [01:19:18] Soupa, [01:19:19] à Biarritz. [01:19:20] Soupa qui a fait l'œuvre [01:19:21] qui est derrière toi, [01:19:22] C'est beau. [01:19:23] C'est Soupa Kitcho, [01:19:25] Guillaume Grandot. » |

## Notes de méthode

- Les transcripts n'étant **pas diarizés**, seuls deux types d'ancrage ont été
  acceptés : (a) la personne est nommée juste avant de prendre la parole, ou
  (b) l'invité est unique et le « je » est sans ambiguïté. Les 5 attributions
  proposées (ubm-0083, 0599, 0619, 1023, 3178) relèvent de (a) ou (b) ;
  ubm-0126 repose sur un recoupement biographique interne à l'épisode, plus
  faible, et n'est de toute façon pas une reco.
- Trois recos référencent une canonique déjà validée qui porte le **bon** nom
  (ubm-0038 → Laurent Baffie, ubm-3170 → Fadily Camara, ubm-0643 → Yvick) :
  la correction proposée ne fait que réconcilier le doublon avec sa canonique.
- Écarts de timecode entre source `acast` et transcript YouTube constatés :
  nuls ou très faibles (≤ 2 s) pour ubm-0083, 0599, 0619, 1023 ; ~1 min pour
  ubm-3200 (reco 01:18:18, passage réel 01:19:17). Les timecodes cités
  ci-dessus sont ceux du **transcript YouTube**.
