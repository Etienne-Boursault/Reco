# Liens pour les 104 recos actives sans aucun lien

Passe du 2026-07-26. Périmètre : recos non `discarded` n'ayant **ni** `links[]`,
**ni** `externalIds.*` en `http`, **ni** `watchProviders[].url` → 104 recos.

**Résultat : 76 liens posés, 28 laissées sans lien** (à vérifier à la main ou
introuvables). Vérifié après coup : le recompte retombe bien sur 28.

## Méthode — comment chaque lien a été prouvé

Aucun lien n'a été deviné : chaque URL a été **récupérée depuis une source
interrogeable**, jamais fabriquée à partir d'un titre. Le quota WebSearch n'a
pas été entamé (0 requête) — tout est passé par des APIs publiques sans clé et
par `yt-dlp`.

| Source | Ce qui prouve la correspondance |
|---|---|
| API Deezer | `title` + `artist` + **`contributors`** renvoyés par l'API |
| Place des Libraires | fiche produit réellement présente dans la page de résultats (EAN + titre + auteur) |
| JustWatch | page chargée : `<h1>` = titre + année, réalisateur présent dans la page |
| `yt-dlp` | titre, **nom de chaîne** et `channel_url` réels renvoyés par YouTube |
| API iTunes | `collectionName` + `artistName` + `feedUrl` |
| Wikipédia (API REST) | page existante + résumé lu pour écarter les homonymes |
| Sites officiels | page chargée, `<title>`/`<h1>` et mots-clés attendus vérifiés |

Trois garde-fous ont effectivement bloqué de faux liens :

- **Le lien Deezer hérité du doublon de `ubm-2760` était un faux match** :
  `track/3856161211` = « incondicional » de *iza tkm*, sans rapport avec Yseult.
  Non réutilisé.
- **`ubm-0375`** : la 1ʳᵉ vidéo Monsieur Phi trouvée (« Cette histoire vous fera
  des nœuds au cerveau ») est en fait sa propre nouvelle *Black Pills* — sa
  description l'a révélé. La bonne vidéo a été trouvée ensuite en listant la
  chaîne.
- **Handles YouTube devinés puis testés** : `@EtBim`, `@Zebrelo`, `@Domitor`,
  `@Splinalende`, `@MahautDrama` renvoient 404 → aucun lien posé. `@FreddyFred`
  existe mais son contenu ne correspond pas → écarté.

Attention méthodologique : `yt-dlp` renvoie par défaut les titres **traduits en
anglais**. Le forçage `youtube:lang=fr` a été nécessaire pour ne pas prendre une
chaîne francophone pour une chaîne anglophone (cas `TRY` et `Spline LND`).

Contrôle d'intégrité avant écriture : le round-trip JSON a été validé sur les
**3009 fichiers** du dépôt (re-sérialisation identique à l'octet près), donc le
diff ne touche que le champ `links`. `npm run build` passe (2666 pages), ce qui
valide les 76 liens contre le schéma Zod.

---

## 1. Liens posés (76)

### Musique — API Deezer (16)

| Reco | Titre | Lien | Preuve |
|---|---|---|---|
| ubm-0104 | Love'n'Tenderness / Eddy de Pretto | `track/2433524015` | **Le titre existe vraiment** : « LOVE'n'TENDRESSE ». Lève le doute de la relecture |
| ubm-0424 | Melodrama / Théodora et Disiz | `track/3558373981` | `contributors = [disiz, Theodora]` — l'attribution est confirmée par l'API |
| ubm-0687 | Mistral Gagnant / Renaud | `track/5151905` | album *Mistral gagnant* |
| ubm-0799 | Aimée / Julien Doré | `album/268316612` | 20 titres |
| ubm-1424 | Kiss the Beast / Sébastien Tellier | `album/824175871` | 12 titres |
| ubm-1448 | On s'en rappellera pas / Disiz | `album/858182392` | 20 titres |
| ubm-1662 | Shake Shook Shaken / The Dø | `album/8729983` | 12 titres |
| ubm-1955 | Summer / Joe Hisaishi | `track/879779942` | album *Kikujiro (OST)* |
| ubm-2514 | Le Fil / Camille | `album/40789961` | 18 titres |
| ubm-2715 | Akwaba / KT Gorique | `album/614025672` | 22 titres |
| ubm-2900 | Ah La France / Orelsan | `track/1969452647` | ⚠️ intitulé « CP\_006\_Ah la France » (démo de *Civilisation Édition Ultime*) |
| ubm-2912 | Civilisation / Orelsan | `album/270762122` | 15 titres |
| ubm-2996 | Vivarda / Vincent Delerm | `track/715682922` | titre réel « Vie varda » (album *Panorama*) — confirme la correction du relecteur |
| ubm-3009 | Na Na Na | `track/608710482` | `contributors = [Vincent Delerm, Mathieu Boogaerts]` — le duo est confirmé |
| ubm-0684 | Ma tête, mon cœur et mes couilles / GCM | `track/142750186` | ⚠️ Deezer tronque le titre en « Ma tête, mon cœur » (album *Midi 20*) |
| ubm-1265 | Mister Mystère / -M- | MusicBrainz `a62f5170…` | ⚠️ **pas de lien Deezer** : seul le *single* y est, pas l'album. Fiche MusicBrainz à la place |

### Artistes — API Deezer (6)

`ubm-0429` Spider ZED · `ubm-2354` LauCarré · `ubm-2185` Pleymo ·
`ubm-2997` Peter Von Poehl · `ubm-2904` Mona Guba · `ubm-2760` Yseult (+ Wikipédia).

**`ubm-2904` — preuve inattendue et solide** : la discographie de *mona guba*
contient un morceau intitulé **« Un Bon Moment (freestyle) »**. Le lien avec le
podcast est établi, ce n'est pas une homonymie.

### Livres — Place des Libraires (7, tous `indie`)

| Reco | Ouvrage retenu | EAN |
|---|---|---|
| ubm-1404 + ubm-1574 | Les quatre accords toltèques / Miguel Ruiz | 9782889539215 |
| ubm-2491 | Comedian rhapsodie / Thomas VDB | 9782757896808 |
| ubm-2890 | L'amour, c'est surcoté / Mourad Winter | 9782266351010 |
| ubm-2444 | La boîte de petits pois / Holly R & GiedRé | 9782756099200 |
| ubm-2544 | Poèmes d'Andrée Chedid, **préfacés par Matthieu Chedid** | 9782290022139 |
| ubm-0594 | Rire pour ne pas mourir / Jean-Marie Bigard | 9782915056419 |

**`ubm-0594`** : la relecture précédente n'avait pas pu confirmer l'existence du
livre (budget WebSearch épuisé) et le soupçonnait d'être un artefact — **il
existe bel et bien**.

**`ubm-2544`** : l'édition retenue est celle préfacée par Matthieu Chedid,
l'invité qui recommande sa grand-mère — la plus pertinente des 7 disponibles.

### Films / séries — JustWatch (10)

`ubm-0925` Ni pour, ni contre (2003) · `ubm-2330` En corps (2022) ·
`ubm-2518` Patients (2017) · `ubm-2928` Man on the Moon (1999) ·
`ubm-3134` Drive (2011) · `ubm-2463` Kaamelott · `ubm-1652` Loups Garous ·
`ubm-1053` Bill Burr: I'm Sorry You Feel That Way · `ubm-1205` Humoristes du
monde · `ubm-1937` Bref.

JustWatch est un **agrégateur** (déjà utilisé par `merchants.ts`), pas une
plateforme : poser ce lien ne préjuge pas d'un abonnement Netflix/Canal.

- **`ubm-1053`** : la page confirme l'année **2014**, donc bien le spectacle « en
  noir et blanc » — la déduction du relecteur (contre *Walk Your Way Out*, 2017)
  était juste.
- **`ubm-1205`** : la page « Humoristes du monde » contient bien *Alkhalidey*.
- **`ubm-1937`** : ⚠️ le lien pointe la série **Bref** (h1 « Bref (2011) ») ;
  *Bref 2* en est la saison 2, il n'existe pas de page distincte.

### YouTube — chaînes et vidéos vérifiées via `yt-dlp` (16)

| Reco | Cible | Remarque |
|---|---|---|
| ubm-0375 | *[Lecture audio] « La Carte » de Marcel Aymé* | **32 min** — colle à la citation « une demi-heure… lui qui lit cette nouvelle » |
| ubm-0624 | chaîne **France tv nature** | les vidéos « ZAPPING SAUVAGE » sont sur cette chaîne (ex-*Zapping Sauvage*) |
| ubm-1038 | Stardust – La Chaîne Air & Espace | 4/4 résultats sur la chaîne |
| ubm-2228 | chaîne **Tistrya** | la relecture la disait « non vérifiable, aucun résultat » → **elle existe** (paranormal, 1 M de vues) |
| ubm-2372 | chaîne Eleonore Costes | série « GENRE HUMAINE » présente |
| ubm-2421 | chaîne Les Fables d'Odah & Dako | la chaîne elle-même est renvoyée par la recherche |
| ubm-2472 | chaîne L'Histoire racontée par des chaussettes | contenu conforme + promo Yacine Belhousse |
| ubm-2708 | vidéo *LES FRÈRES MALÉFIQUES* | la vidéo exacte, sur la chaîne de Jérémie Dethelot |
| ubm-2709 | chaîne Shirley Souagnon | série « SHIRLEY #NN DEFINITION » |
| ubm-2075 | chaîne **TRY** | francophone (vérifié en forçant `lang=fr`) |
| ubm-2678 | chaîne **Spline LND** | orthographe jusqu'ici « non vérifiable » → chaîne trouvée |
| ubm-2143 | Mahaut Drama (Montreux Comedy) | nom de scène confirmé |
| ubm-2879 | John Sulo (Montreux Comedy) | également présent sur Comédie+ |
| ubm-3103 | Alex Nguyen (YouHumour) | passage en intégralité |
| ubm-2949 | chaîne Julie-Albertine | « La minute de Julie-Albertine », Teva Comedy Show |
| ubm-2835 | chronique France Inter de **Lisa Delmoitiez** | ⚠️ le titre de la reco (« Elisadelle Moitié ») reste à corriger |

### Sites officiels (4) + podcast (1)

- `ubm-1514` **yohannmetay.com** — la page contient « dossard » et « 512 »
- `ubm-1456` **getbrick.com** (`getbrick.app` y redirige) — « Take Back Control
  of Your Screen Time », correspond au « petit bloc » de la citation
- `ubm-1454` **apple.com/fr/apple-fitness-plus/**
- `ubm-1875` **theohaggai.com** — `<h1>` = « Théo Haggaï »
- `ubm-2349` **FloodCast** sur Apple Podcasts (`id1019768302`, flux Acast) — les
  2 autres « FloodCast » renvoyés par l'API sont brésiliens

### Fiches Wikipédia (16)

`ubm-1401` Ricky Gervais · `ubm-2836` Phoebe Waller-Bridge · `ubm-2141` Euzhan
Palcy · `ubm-2800` Hakim Jemili · `ubm-2325` + `ubm-2379` Kheiron ·
`ubm-2868` Laura Laune · `ubm-0327` Bérengère Krief · `ubm-3091` Roman
Frayssinet · `ubm-3006` Jean Poiret **et** Michel Serrault (2 liens) ·
`ubm-1594` Alfred Hitchcock · `ubm-1532` HIStory World Tour ·
`ubm-2002` Rosa Bursztein · `ubm-1932` Manon Bril · `ubm-2011` Kyan Khojandi ·
`ubm-1425` Pierre Soulages.

Choix assumé : pour ces recos, **l'œuvre précise n'a pas de page vérifiable**
(spectacle en tournée, expo terminée, reco générale). La fiche de l'artiste est
le lien vérifié le plus proche — à remplacer par une billetterie si tu en as une.
`ethics: indie` retenu (Wikimedia = non lucratif) ; dis-moi si tu préfères
`neutral`, c'est un choix éditorial et non une contrainte du schéma.

Pour `ubm-1532`, la fiche **HIStory World Tour** (1996-1997) confirme au passage
le `year: 1997` du champ.

---

## 2. À vérifier à la main (14)

### Candidat trouvé mais identité non prouvée

L'URL est donnée pour que tu tranches en quelques secondes ; elle n'a **pas** été
écrite dans le JSON.

| Reco | Candidat | Pourquoi je m'abstiens |
|---|---|---|
| ubm-2155 | Tortoza — `deezer.com/artist/3667561` (694 fans, albums 2023-2025) | Le nom colle exactement, mais rien ne prouve que c'est l'auteur de la **musique de fin du podcast**. Toi, tu le sais immédiatement |
| ubm-2880 | Omar Dhobb — `youtube.com/watch?v=7LGflCmK3Kc` (best-of Paname Comedy Club) | « Omar\_DBB » ≈ « Omar Dhobb » phonétiquement, orthographe non confirmée |
| ubm-1234 | PLANET SHAGA — `youtube.com/channel/UCPnxhyAxViN6eEXglzsEiww` | Artiste musical ; la reco est de type « autre », aucun recoupement |
| ubm-2835 | podcast *Imagine Ça Parle De Ça* (Fanny Ruwet) — `id1565366066` | Lisa Delmoitiez en serait co-autrice : lien **indirect**, pas son œuvre propre |

### Plateformes non vérifiables / arbitrage éditorial

| Reco | Situation |
|---|---|
| ubm-2415 | *Le grand débat* (Édouard Baer & **Dieudonné**) : n'existe que via des ré-uploads de chaînes tierces, aucune source officielle. **Arbitrage éditorial** requis vu la personne concernée — rien posé |
| ubm-3147 | *NTM Authentiques, un an avec le suprême* : documentaire réel mais uniquement en ré-upload non officiel ; pas de page JustWatch |
| ubm-3110 | *Funny AF with Kevin Hart* : plateforme US (LOL Network/Peacock), pas de page JustWatch FR |
| ubm-3197 | *Burning Love* (Ben Stiller) : pas de page JustWatch FR |
| ubm-0355 / ubm-2313 / ubm-2566 | *Pulsions* (Kyan Khojandi) : aucune page JustWatch, aucune captation officielle trouvée |
| ubm-1425 | L'expo **« Soulages, une autre lumière »** est terminée et l'URL d'événement du Musée du Luxembourg est en 404 → lien posé = fiche Soulages |
| ubm-2500 | *Melly Hirtz* / marque **WEIM** (sacs) : aucun résultat YouTube. À chercher côté Instagram / site de la marque, que je ne peux pas authentifier |
| ubm-1382 | *Linda Fandel* (humoriste) : aucun résultat probant |

## 3. Introuvables (14)

Recherches faites, **rien de vérifiable** — cohérent avec les notes de relecture.

- `ubm-0164` **Never Ending Shampoo Gag** — format viral, des dizaines de
  versions, aucune canonique (déjà noté par la relecture).
- `ubm-0641` **Et Bim** · `ubm-0642` **Freddy Fred** · `ubm-1070` **Domitor** ·
  `ubm-1458` **Zébrelo** · `ubm-1857` **Slay** — recherches + handles testés,
  aucune chaîne correspondante.
- `ubm-1649` **Colocs** — websérie non retrouvée.
- `ubm-2876` **Discours de Denis Villeneuve** — référence trop vague (0 résultat).
- `ubm-2205` **Eau de vie / Eddy de Pretto** — 0 résultat ; le titre est un
  artefact de nom de fichier (« Odevi vdef max mix »), pas un titre publié.
- `ubm-1179` **3 minutes pour comprendre** — c'est une **collection** (Le Courrier
  du Livre) : ~8 tomes existent, impossible de savoir lequel sans réécoute.
- `ubm-2092` **Message Personnel** — aucun candidat ne recoupe « un bouquin
  préparation ».
- `ubm-1375` **Cette éducation me déteste** / Anis Rhali — absent de l'annuaire
  Apple Podcasts.
- `ubm-2747` **Insomniac** / Marion Séclin — absent également (existe surtout en
  texte sur Instagram d'après la relecture).
- `ubm-2745` **Ça sera (peut-être) mieux après** — œuvre **non produite** (en
  cours d'écriture).
- `ubm-3057` **Lève-toi et tombe** — spectacle défunt, jamais capté (« pas de
  traces pour les gens »).
- `ubm-2964` **Kawaii Bukkake** — absent de Deezer et de YouTube ; cohérent avec
  « groupe blague ».

---

## 4. Titres encore à corriger

Ces recos ont **un lien correct mais un `title`/`creator` encore fautif** : le
lien pointe vers l'œuvre réelle, pas vers le titre affiché.

| Reco | `title` actuel | Devrait être |
|---|---|---|
| ubm-2997 | Peter Von Paul | **Peter von Poehl** |
| ubm-3006 | Poire et Serreau | **Poiret et Serrault** |
| ubm-2835 | Elisadelle Moitié | **Lisa Delmoitiez** |
| ubm-2444 | Une case en moins *(nom de collection)* | **La Boîte de petits pois** |
| ubm-2996 | Vivarda | **Vie Varda** |
| ubm-2143 | Mahaut Di Sciullo | nom de scène **Mahaut Drama** |
| ubm-0684 | Ma tête, mon cœur et mes couilles | Deezer l'orthographie « Ma tête, mon cœur » |

Rien n'a été commité — le diff est à relire (`git diff`).
