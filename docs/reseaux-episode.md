# Publier un épisode sur les réseaux

Après la relecture d'un épisode, quand ses recos validées sont dans `main` et sa page en ligne. Le
commentaire YouTube part tout seul depuis venus. Tout le reste suit ces étapes, en une passe.

Les comptes sont ceux d'« Une Bonne Reco » : Instagram et Threads `@unebonnere.co`, Spotify, Deezer,
SensCritique `unebonnereco`. Ils sont tous connectés dans le Chrome de l'éditeur.

## Où « Une Bonne Reco » publie

| Plateforme | Compte ou liste | Adresse |
|---|---|---|
| Site | unebonnere.co | https://unebonnere.co/ |
| Instagram | `@unebonnere.co` | https://www.instagram.com/unebonnere.co/ |
| Threads | `@unebonnere.co` | https://www.threads.com/@unebonnere.co |
| YouTube | chaîne « Une Bonne Reco » (commentaire sous chaque vidéo) | https://www.youtube.com/@unebonnereco |
| Spotify | playlist Saison 6 | https://open.spotify.com/playlist/7cLC4Tb2Uq9U3T5BDH6cLN |
| Spotify | playlist Saison 5 | https://open.spotify.com/playlist/0alKtRHpLqgRectbA3aofv |
| Spotify | playlist Saisons 1 à 4 (2020-2024) | https://open.spotify.com/playlist/0by8HhnsJTvt7HrAcYIB1U |
| Spotify | playlist Toutes les recos musicales | https://open.spotify.com/playlist/4MO9RDFbo5RRFVcUaL16uY |
| Deezer | playlist Saison 6 | https://www.deezer.com/fr/playlist/15885712903 |
| Deezer | playlist Saison 5 | https://www.deezer.com/fr/playlist/15885712963 |
| Deezer | playlist Saisons 1 à 4 (2020-2024) | https://www.deezer.com/fr/playlist/15885712763 |
| Deezer | playlist Toutes les recos musicales | https://www.deezer.com/fr/playlist/15885712683 |
| SensCritique | compte `unebonnereco` | https://www.senscritique.com/unebonnereco |
| SensCritique | liste des films | https://www.senscritique.com/liste/les_films_recommandes_dans_un_bon_moment/4414481 |
| SensCritique | liste des séries | https://www.senscritique.com/liste/les_series_recommandees_dans_un_bon_moment/4414486 |
| SensCritique | liste des livres | https://www.senscritique.com/liste/les_livres_recommandes_dans_un_bon_moment/4414489 |
| SensCritique | liste des BD | https://www.senscritique.com/liste/les_bd_recommandees_dans_un_bon_moment/4414494 |

Les stories Instagram (et le sticker lien) ne se publient que depuis l'application du téléphone : la
procédure ne prépare que l'image ou la vidéo.

## 1. Préparer

```bash
python -X utf8 tools/reseaux_episode.py S6-E06
```

Dans `Images/unebonnere.co/<date>-S6E06/` :

- `episode.json` : le brouillon du carrousel, avec une page par mention validée, dans l'ordre de
  l'épisode ;
- `plan.json` : les titres à ajouter aux playlists et les œuvres à ajouter aux listes SensCritique.

La musique ne prend que les recos **de cet épisode**. Les titres phares d'un artiste changent avec le
temps, et recalculer les anciens épisodes déplacerait des titres déjà publiés.

### Liens Spotify manquants

Sans Premium, la chaîne ne cherche pas de lien Spotify (voir « Spotify : API ou lecteur » plus bas).
La commande liste alors les recos musicales et les podcasts de l'épisode qui n'en ont pas, avec
l'onglet de recherche à utiliser. Les playlists se calculent d'après ces liens : il faut les poser
**avant** la suite.

Coller la partie Spotify de `tools/reseaux_episode_ui.js` dans un onglet open.spotify.com, puis pour
chaque reco listée :

```js
await __spChercher('Noor', 'artists')   // « id [texte de la ligne] », 5 candidats au plus
```

Choisir le candidat d'après le nom et le créateur. En cas de doute, ne rien poser et le signaler.

```bash
python -X utf8 tools/reseaux_episode.py --lien-spotify ubm-3290=https://open.spotify.com/artist/3fguWOo99xwsT4VgVeSvJO
python -X utf8 tools/reseaux_episode.py S6-E06   # relancer : les playlists tiennent compte des nouveaux liens
```

Les recos modifiées partent dans la même PR que `tools/data/`. Avec Premium, la liste est vide : la
chaîne a déjà posé les liens.

### Playlists à créer

Une **ALERTE** signale une playlist à créer, par exemple au début d'une saison 7. Il faut alors la
créer sur Spotify et sur Deezer, publique, avec la même description. On l'ajoute ensuite aux deux
fichiers `tools/data/playlists_*.json`, puis on relance la commande.

## 2. Relire le carrousel

Dans `episode.json` :

- raccourcir les citations, qui doivent tenir en 3 ou 4 lignes ;
- compléter les « qui » vides ;
- préciser `createur` si besoin : une plateforme (« Sur Apple TV »), un lieu (« au Funambule »).

Ensuite :

```bash
python -X utf8 tools/carrousel_episode.py "<dossier>"
```

La commande produit les PNG (1080×1350), `legende-instagram.txt`, `legende-threads.txt` (500
caractères au plus) et `alts.json`. Il faut regarder les PNG, puis les **montrer à l'éditeur avant de
publier**.

## 3. Instagram, puis Threads (avec l'accord de l'éditeur)

- **Instagram (web)** : passer par Créer, puis Publication. Viser le `input[type=file]` **du
  dialogue** « Créer une nouvelle publication », recadrer en 4:5, puis coller la légende et les
  textes alternatifs. Pour ces champs React, il faut le setter natif de `value` puis un événement
  `input`.
- **Threads** : dialogue « Nouveau fil ». Le sujet est « Un bon moment », et on n'en met qu'un seul,
  sans hashtag. Le même `input[type=file]` accepte les 14 images.
- `file_upload` refuse le dossier `Images` : copier les PNG dans le scratchpad de la session.

## 4. Spotify et Deezer

Coller la partie Spotify de `tools/reseaux_episode_ui.js` dans un onglet open.spotify.com, puis :

```js
await __spCapter()
await __spIsrc([...tous les ids de plan.spotify])   // « id=ISRC id=ISRC … »
```

```bash
python -X utf8 tools/playlists_deezer.py "<dossier>/plan.json" "<sortie de __spIsrc>"
```

L'ISRC donne le même enregistrement sur Deezer. Les lignes **A VERIFIER** sont des titres retrouvés
par la recherche, à contrôler un par un.

Pour chaque playlist du plan, faire l'ajout dans son onglet :

- `await __spAjouter('<id>', [...])` dans l'onglet Spotify ;
- `await __dzAjouter(<id>, [...])` dans un onglet deezer.com, après y avoir collé la partie Deezer.

Chaque appel relit la playlist et répond `conforme: true` si l'ordre est le bon.

## 5. SensCritique

Coller la partie SensCritique dans un onglet senscritique.com, puis `await __scCapter()`.

Pour chaque œuvre du plan :

1. `await __scChercher('<titre>', '<movie|tvShow|book|comicBook>', <id de la liste>)` ;
2. choisir le bon candidat d'après le titre, l'année et le créateur. On n'ajoute pas en cas de doute ;
3. `await __scAjouter(<liste>, <id SensCritique>, '<fiche>')`.

L'œuvre s'ajoute **en tête** de la liste, qui va du plus récent au plus ancien, avec le lien vers sa
fiche.

## 6. Enregistrer

```bash
python -X utf8 tools/reseaux_episode.py --enregistrer "<dossier>/plan.json"
```

Cette commande met à jour les états de Spotify et de SensCritique, et relit Deezer en ligne. Elle
affiche ensuite le nombre de titres de chaque playlist sur les deux plateformes, qui doit être le même
des deux côtés.

Ensuite, commiter `tools/data/` dans une PR, avec les recos dont on a posé le lien Spotify.

## Spotify : API ou lecteur

Une seule ligne du `.env` de venus choisit, sans commit ni redéploiement :

- **`RECO_SPOTIFY=0`** (sans Premium) : la chaîne n'interroge pas l'API, qui répondrait 403. Les liens
  Spotify se posent à la publication, comme décrit plus haut ;
- **ligne absente** (avec Premium, même une offre d'essai) : la chaîne cherche les liens Spotify
  avant la relecture, avec Deezer et les autres. La liste des manquants est alors vide.

Les identifiants `SPOTIFY_CLIENT_ID` et `SPOTIFY_CLIENT_SECRET` restent en place dans les deux cas.
Quand un abonnement reprend ou s'arrête, il suffit de retirer ou de remettre la ligne.

## Pourquoi ces chemins détournés

Spotify refuse son API aux comptes sans Premium (403), et Deezer n'ouvre plus d'application. Quant à
SensCritique, il n'a pas d'API publique. Les fonctions de `reseaux_episode_ui.js` passent donc par les
requêtes du site lui-même, depuis un onglet connecté. Elles fonctionnent même fenêtre masquée, ce que
l'interface ne permet pas : la liste de titres du lecteur Spotify ne se met pas à jour quand la
fenêtre est masquée.
