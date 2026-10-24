# Contrats canoniques de la V2

**Statut** : proposé, avec l'[ADR 0055](../adr/0055-modele-canonique.md) (modèle canonique) et l'[ADR 0056](../adr/0056-identifiants-oeuvre-permanents.md) (identifiants). Spécification écrite le 24 octobre 2026, amendée le soir même par les décisions de l'éditeur : défaut de la reco pour `title` et `creator` (DV-03 B), registre des ids ni versionné ni déployé (§6.2), **aucun lien sur la mention** (§2.2, §4). Les statuts à jour sont dans [`decisions.json`](decisions.json).

Légende : **[V]** vérifié dans le code · **[M]** mesuré au commit `7c2bf3f3` (scripts ponctuels du 24/10, que les invariants de PR-01 remplacent) · **[R]** rapporté · **[H]** hypothèse · **[D]** décidé · **[P]** proposé.

## 1. Entités et identifiants

```text
Source 1 ──< Épisode 1 ──< Mention >── 1 Œuvre
                                Œuvre 1 ──< Clé de rattachement (registre)
                                Œuvre 1 ──< Redirection (dérivée du registre)
```

| Entité | Identifiant | Stabilité | Remarques |
|---|---|---|---|
| Source | `id` (slug) | permanent | |
| Épisode | `guid` (RSS) | permanent | 116 épisodes, dont **73 sans `season`** [M] |
| Œuvre | `id` (8 hex, suffixe `-n` en cas de collision) | permanent, jamais réutilisé (ADR 0056) | 2 689 vivantes, 277 supprimées dans l'historique [M] |
| Mention | `id` = identifiant de la reco (`ubm-NNNN`) | permanent | La reco et la mention partagent leur identifiant (`oeuvre/[itemId].astro:52-55`) [V] ; l'adresse `/<source>/report/<id>` en dépend |
| Candidat | id de reco en brouillon | atelier seulement | Devient une mention une fois validé ; ne sort jamais de venus |

Cardinalités :
- Une mention pointe vers **une** œuvre et **un** épisode.
- Plusieurs mentions d'une même œuvre dans un même épisode sont permises (minutages distincts) : aucune contrainte d'unicité sur `(itemId, episodeGuid)`.

## 2. Propriété des champs

Un champ a **un seul** propriétaire. Une copie est une vue recalculée. Pendant la transition, les champs d'œuvre et de mention recopiés sur la reco sont des **miroirs** (§7).

Colonnes :
- **Écarts [M]** : sur les 1 298 recos validées, entre la reco et sa mention ou son œuvre ;
- **Classe** : voir §3 ;
- **Lecteurs** : qui l'affiche aujourd'hui [V].

### 2.1 Œuvre

| Champ | Aujourd'hui | Public | Écarts [M] | Classe et règle | Lecteurs |
|---|---|---|---|---|---|
| `id` | œuvre | oui | — | registre (§6) | toutes les pages d'œuvre |
| `title` | reco, œuvre | oui | 25 valeurs différentes, dont 22 par la casse seulement | C3 : arbitrage par lot ; défaut **proposé** : la reco (DV-03 B), graphie vérifiée contre une source | carte de reco (reco) ; fiche, recherche (œuvre) |
| `creator` | reco, œuvre | oui | 59 valeurs différentes ; **69** seulement sur la reco ; 10 seulement sur l'œuvre | C2 pour les 79 (la valeur présente ; 4 valeurs de l'œuvre suspectes, signalées : « TF1 », « Netflix », « Deezer », « Dailyo ») ; C3 pour les 59, défaut proposé : la reco (DV-03 B) | idem |
| `types` | reco, œuvre | oui | 8 | C3 ; défaut proposé : l'œuvre (union historique des types) | icônes de la carte ; galeries |
| `year` | reco, œuvre | oui | 8 seulement sur la reco ; 9 seulement sur l'œuvre ; 0 contradiction | C2 | carte ; JSON-LD |
| `aliases` | reco (34), œuvre (65) | à confirmer (audit PR-03) | 1 alias de reco absent de l'œuvre | C2 (union) ; alimente aussi le registre (§6.3) | atelier (dédoublonnage) |
| `externalIds.*` | reco, œuvre, **formes différentes** | en partie | par clé, §4.4 | C1, C2 ou C3 par clé | `resolveLinks` (reco) ; `workExternalLinks` (œuvre) |
| `links` | **reco seulement** | oui | §4.1 | nouveau champ optionnel de l'œuvre ; §4.5 | carte (reco) ; fiche (union des recos) |
| `customLinks` | reco (11), œuvre (13) | oui | non mesuré par paire | union par URL sur l'œuvre ; contradiction : gardées toutes deux, signalées (§4.5) | carte (reco) ; fiche (œuvre) |
| `watchProviders` | reco (301, **jamais rendus**), œuvre (212) | oui (œuvre) | non mesuré par paire | union par URL ; `label` de la reco → `name` | fiche (œuvre) |
| `linkOverrides` | reco (15), œuvre (14, **jamais lues**) | oui (reco) | 11 identiques, 3 formes équivalentes, 1 absente de l'œuvre | §4.5 ; aucune n'est propre à une citation au HEAD | carte (reco) |
| `enrichedAt` | reco (558) ; œuvre : schéma seulement, 0 valeur | non | — | provenance, atelier ; sert seulement à trier les arbitrages | — |
| `enrichmentSuspect` | œuvre : schéma seulement, 0 valeur | non | — | atelier | — |
| `recommendedBy` | schéma de l'œuvre seulement, 0 valeur | **interdit** | — | champ de mention ; invariant : absent de l'œuvre | — |

### 2.2 Mention

| Champ | Aujourd'hui | Public | Écarts [M] | Classe et règle | Lecteurs |
|---|---|---|---|---|---|
| `itemId` | mention | oui | 0 orphelin | rattachement (C4), §6 | fiche, galeries, recherche |
| `episodeGuid`, `sourceId` | reco ; mention (`sourceRef`) | oui | 0 | — | toutes |
| `timestamp` | reco (texte libre) ; mention (`HH:MM:SS`) | oui | 0 | forme de la mention | carte, chronologie, lien profond YouTube |
| `transcriptSource` | reco ; mention (`sourceRef`) | oui | 0 | — | `EpisodeChapitres.astro:77`, `aggregator.ts:451` |
| `quote` | reco, mention | oui | 0 | — | carte, chronologie |
| `recommendedBy` | reco, mention | oui | 2 : 1 contradiction, 1 seulement sur la reco | C3 ; défaut proposé : la reco (dernière relue) ; C2 pour l'autre | carte, chronologie, recherche |
| `kind` | reco (1 338 explicites, sinon défaut), mention (3 107 explicites) | oui | 0 | C1 : toujours explicite dans la révision | carte, comptes, OG |
| `guestWork` | reco (256 `true`), mention (39 `true`) | oui | **197**, tous « reco `true`, mention absent » | C3 (absent vaut faux) ; lot unique décidé (DV-04 A) ; §7 | carte, OG (reco) ; chronologie (mention) |
| `status` | reco, mention | filtre | 0 | — | toutes |
| `extractors` | reco, mention | oui | 0 | — | `index.astro:37` |
| `note` | reco seulement (1) | oui | — | devient un champ optionnel de la mention | JSON-LD de la page épisode (`episode/[guid].astro:171`) |
| Liens | — | — | — | **aucun champ de lien sur la mention** (décision du 24/10) : les liens appartiennent à l'œuvre, §4.2 | — |
| `extractionHistory`, `agentReview`, `linksRejected` | reco (hors schéma Zod pour les deux derniers), mention | non | — | atelier | — |

### 2.3 Épisode et source

Propriétaire unique, aucune copie aujourd'hui. Champs **non lus par une page** au HEAD, donc exclus de la révision [V, recherche dans `src/pages`, `src/components`, `src/lib`, `src/utils`, `src/layouts`] :
- épisode : `guestsParsed`, `guestsExcluded`, `transcriptStatus`, `transcriptModel`, `transcriptSource`, `youtubeUnavailable`, `matchSuspect*` ;
- source : la liste est à figer par l'audit des champs lus de PR-03.

La liste blanche définitive se calcule en PR-03 sur ce que les pages **consomment** : recherche des accès `.data.<champ>` et des propriétés des composants, puis test « champ interdit ».

## 3. Valeurs absentes, `null`, explicites, et classes de divergence

### 3.1 Représentation canonique

| Règle | Contenu | Au HEAD [M] |
|---|---|---|
| R-V1 | Dans la révision, un champ optionnel est **présent avec une valeur non nulle, ou absent**. `null` n'y figure jamais. | 0 `null` explicite dans tout le corpus |
| R-V2 | Le normaliseur traduit un `null` V1 en absence et le **compte** dans son rapport. | — |
| R-V3 | Drapeaux dont l'absence vaut faux (`guestWork`, `youtubeUnavailable`, `matchSuspect`, `enrichmentSuspect`) : `true` ou absent. `false` est traduit en absence et compté. Pas de tri-état (même choix que `content.config.ts:275-283`). | aucun `false` |
| R-V4 | Listes : absent et vide sont équivalents (`links`, `customLinks`, `watchProviders`, `aliases`, `guests`). Forme canonique : absent. La projection rend les défauts Zod (`[]`). | — |
| R-V5 | Énumérations à défaut Zod (`kind`, `status`) : toujours **explicites** dans la révision, pour ne pas dépendre d'un défaut qui pourrait changer. | `kind` absent sur 1 761 recos |
| R-V6 | Chaîne vide : **signalée**, jamais normalisée en silence. Un lot approuvé peut la traduire en absence. | 0 `creator` vide |
| R-V7 | Types : `externalIds.tmdb` est un **entier** dans le modèle (forme de l'œuvre) ; la vue reco le rend en chaîne (forme V1). Les dates sont des instants ISO UTC dans la révision, et redeviennent des `Date` dans `CatalogReader` pour les champs `z.coerce.date()`. | `tmdb` : texte sur la reco, entier sur l'œuvre |
| R-V8 | **Effacer** une valeur, c'est la retirer chez son propriétaire. Pas de valeur sentinelle. « Inconnu » et « sans objet » ne sont pas distingués aujourd'hui, et ne le sont pas davantage ici. | — |

### 3.2 Classes de divergence

| Classe | Définition | Traitement | Exemple mesuré |
|---|---|---|---|
| C0 | Égal | rien | 975 recos validées sans écart sur les neuf champs comparés (hors liens et `externalIds`) |
| C1 | **Représentation** : `null`/absent, défaut Zod, type, forme équivalente d'une même URL (§4.5) | Normalisation déterministe, comptée, **sans** arbitrage individuel ; la liste des règles C1 est approuvée une fois | `tmdb` texte/entier ; Steam avec ou sans le nom du jeu |
| C2 | **Complétion** : une seule couche porte la valeur | Union ; listée ; approuvée par lot | 69 créateurs seulement sur la reco |
| C3 | **Contradiction** : deux valeurs | Arbitrage obligatoire ; un défaut peut être **proposé**, jamais appliqué sans décision ; pour les liens, gel sur l'œuvre (§4.5) | 25 titres ; 197 `guestWork` |
| C4 | **Rattachement** : la mention pointe vers la mauvaise œuvre | Hors normalisation : relecture, fusion ou scission (§6) | cas *Intouchables* [R] |

### 3.3 Fichier d'arbitrage

Un arbitrage est une donnée, versionnée avec le lot qu'il applique :

```json
{ "lot": "2026-11-guestwork-1", "regle": "C3", "champ": "guestWork",
  "entites": [ { "mention": "ubm-0123", "valeurs": [
      { "valeur": true, "source": "reco" },
      { "valeur": null, "source": "mention", "note": "absent" } ],
    "proposition": true, "decision": true } ],
  "decidePar": "editeur", "le": "2026-11-03" }
```

- Aucun lot n'écrit sans `decision` renseignée sur chaque entité.
- `decidePar` est un rôle, pas un nom (§11 du protocole).
- PoC : ces fichiers vivent dans `poc/conflits/`. PR-MC-donnees : dans `docs/arbitrages/`, joints au commit du lot.

## 4. Liens

### 4.1 Inventaire [M]

| Élément | Valeur |
|---|---|
| Recos validées sans `links`, donc liens générés à l'affichage (`resolveLinks`) | 4 sur 1 298 |
| Œuvres citées par ≥ 2 recos validées | 127 : 113 jeux identiques, 4 inclus l'un dans l'autre, 6 complémentaires, 4 avec un même libellé et deux URL |
| Ces 4 conflits | tous des **formes équivalentes** (Steam, YouTube `@poignée` / `/channel/UC…`, Instagram `?hl=fr`) |
| Recos validées où un **même libellé** porte plusieurs URL | 24 (YT Music 17, YouTube 7…) : deux objets différents, pas un conflit |
| Attributs des liens de reco | `kind` et `ethics` présents sur 100 % des liens |

Conséquence : un ensemble de liens est une **liste ordonnée** qui admet plusieurs URL par libellé. Ce n'est pas une table « plateforme → URL ».

### 4.2 Structures

```ts
// Élément commun : aucun attribut ne se perd en changeant de couche.
type Lien = { url: string; label: string;
              kind?: 'buy'|'borrow'|'streaming'|'info'|'official'|'social';
              ethics?: 'indie'|'neutral'|'avoid';
              logoUrl?: string; region?: string };

Oeuvre {
  links?:          Lien[]                  // NOUVEAU sur l'œuvre
  customLinks?:    Lien[]                  // label, url, logoUrl
  watchProviders?: { name; url; region?; ethics? }[]
  linkOverrides?:  Record<label, url>
}
// Mention : aucun champ de lien (décision du propriétaire, 24/10).
```

- Tout lien vaut pour toutes les citations de l'œuvre. Aucun cas au HEAD n'exigeait un lien propre à une citation [M] : les 15 surcharges de recos sont génériques, et aucun conflit n'est réel.
- Une version précise qui doit avoir son propre lien (un live, une édition) est une **œuvre à part**.
- Ajouter plus tard un champ de lien optionnel sur la mention reste possible sans rien casser ; le retirer demanderait une migration.
- `linkOverrides` garde sa sémantique actuelle : remplacer l'URL d'un lien **par libellé** (`RecoCard.astro:103-111`).

### 4.3 Ordre de résolution

Il reproduit le code actuel ; les règles de dédoublonnage de chaque vue restent les siennes.

**Carte de la mention `m`, œuvre `o`** (page épisode, `/recos`, accueil) :
1. base = `o.links` ; si elle est vide : `resolveLinks(vueReco(m))`, comme aujourd'hui ;
2. surcharges = `o.linkOverrides`, appliquées par libellé à la base ;
3. liens perso = `o.customLinks`, placés **devant** ;
4. inchangé : `isSafeUrl`, marquage `avoid`, dédoublonnage par libellé **et** URL, six liens au plus (`RecoCard.astro:160-202`).

**Fiche de l'œuvre `o`** :
1. inchangé : `o.customLinks`, `o.watchProviders`, liens dérivés des `externalIds`, dédoublonnés par libellé (`aggregator.ts:269-314`) ;
2. puis `o.links`, dédoublonnés par URL ; les liens de recherche s'effacent devant un lien direct du même hôte (`aggregator.ts:345-412`) ;
3. inchangé : la fiche **n'applique pas** `linkOverrides` et n'affiche pas les `customLinks` des recos. Changer cela serait une décision produit, hors de ce chantier.

**Équivalence avec aujourd'hui.** Si `o.links` est l'union des liens des recos, la fiche est identique. La carte diffère seulement pour les œuvres dont les recos n'avaient pas toutes les mêmes liens (14 œuvres) : chaque différence est listée.

### 4.4 `externalIds`

Union par clé, avec les règles suivantes [M] :

| Clé | Seulement reco | Seulement œuvre | Deux valeurs | Règle |
|---|---|---|---|---|
| `tmdb`, `tmdbType` | 57 | 35 | 0 | C2 ; `tmdb` entier (R-V7) |
| `watchPage` | 45 | 33 | 4, toutes équivalentes (TMDB avec ou sans le nom) | C2 ; C1 pour les 4 |
| `instagram` | 5 | 35 | 0 | C2 |
| `isbn` | 21 | 0 | 0 | C2 |
| `deezer` | 58 | — (absente du schéma d'œuvre) | — | C2 ; **ajout optionnel** au schéma d'œuvre (Zod et Python) |
| `youtubeChannelId` | 152 | 0 | 0 | C2 |
| `imdb` | 1 | — (absente du schéma d'œuvre) | — | C2 ; ajout optionnel |
| `tiktok` | 0 | 1 | 0 | C2 |

Clés du schéma de reco absentes des recos validées (`website`, `youtube`, `spotify`, `musicbrainz`) : ajout optionnel au schéma d'œuvre pour ne rien perdre plus tard. `spotify` désigne une **URL** sur la reco et un **chemin** sur l'œuvre (`aggregator.ts:294-296`) : 0 valeur au HEAD, mais le modèle garde une URL complète et la vue de l'œuvre la lit telle quelle.

### 4.5 Conflits de liens et équivalences

**Classement** de chaque paire de liens de même libellé, ou de même hôte, entre les recos d'une œuvre :

| Résultat | Traitement |
|---|---|
| Identiques | une entrée sur l'œuvre |
| **Équivalentes** par une règle de la liste fermée ci-dessous | une entrée sur l'œuvre, sous le représentant validé (DV-02) ; les deux formes restent dans la provenance (atelier) |
| Complémentaires (libellés différents) | union sur l'œuvre (C2, listée) |
| **Contradictoires** (même plateforme, objets différents ou non prouvés égaux) | **Aucun choix par défaut** (gel, DV-01 A). Toutes les URL en conflit restent sur l'œuvre, marquées « à trancher » dans le rapport d'arbitrage : la fiche est inchangée, et chaque carte de l'œuvre montre toutes ces URL (différence listée). Le conflit entre dans la liste d'arbitrage, avec la reco d'origine, `enrichedAt` (pour trier, pas pour décider), la plateforme, le type d'objet et la région. |

**Issues d'un arbitrage** (DV-01) :
- (a) garder une seule URL sur l'œuvre ; les autres sont retirées et le retrait est journalisé dans l'atelier, comme `linksRejected` aujourd'hui ;
- (b) déclarer que l'autre URL désigne une autre œuvre (une édition, un live) : nouvelle œuvre ou scission (§6.3), et la citation concernée y est rattachée ;
- (c) garder plusieurs URL sur l'œuvre, s'il s'agit de deux objets réels de la même œuvre : la liste le permet.

**Règles d'équivalence** : liste fermée, chaque règle avec ses tests. Aucune ne s'applique par ressemblance.

| Plateforme | Règle | Cas au HEAD |
|---|---|---|
| Steam | `store.steampowered.com/app/<n>[/<nom>][/]` : même `<n>` | 2 |
| TMDB | `themoviedb.org/<movie\|tv>/<n>[-<nom>]<suite>` : même type, même `<n>`, même suite | 4 (`watchPage`) |
| Deezer | `deezer.com[/<langue>]/<artist\|album\|track\|playlist>/<n>` : même type et `<n>` | 3 (surcharges) |
| Spotify | `open.spotify.com[/intl-<langue>]/<type>/<id>` : même type et `<id>` | 1 (surcharge) |
| Instagram | `instagram.com/<poignée>[/][?…]` : même poignée, sans tenir compte de la casse | 1 |
| YouTube (chaîne) | `/@<poignée>` ≡ `/channel/<UC…>` **seulement** si le `youtubeChannelId` enregistré pour l'œuvre ou la reco vaut cet `UC…` ; sinon, contradiction jusqu'à l'arbitrage | 1 (*Nardwuar*) |
| Toutes | Retrait des seuls paramètres `hl`, `utm_*`, `si` | inclus ci-dessus |

### 4.6 Région

`region` est absent des 1 634 diffuseurs [M], et aucune page ne le lit [V]. Le champ reste optionnel et conservé ; aucune logique régionale n'est inventée. Deux diffuseurs qui ne diffèrent que par la région sont deux entrées de la liste (fixture F4).

## 5. Ensembles publics

Fonctions **pures**, une seule implémentation (`src/lib/catalog/publication.ts`), utilisées par le constructeur, les invariants et les tests.

```ts
type EtatPublication = { publicsActifs: Set<Guid>; finalises: Set<Guid> };

estEpisodePublic(e, etat)   = etat.publicsActifs.has(e.guid) || etat.finalises.has(e.guid)
estMentionPublique(m, etat) = m.status === 'validated' && estEpisodePublic(episodeDe(m), etat)
estOeuvrePublique(o, etat)  = existe m : m.itemId === o.id && estMentionPublique(m, etat)
```

| Point | Règle |
|---|---|
| Règle actuelle [V] | **tous** les épisodes du dépôt ont une page (`episode/[guid].astro:29-33`) ; une reco est publique si `validated` (`recoPubliee.ts:15-17`) ; une mention si elle n'est pas écartée (`aggregator.ts:94-96`) |
| Au HEAD [M] | 116 épisodes, dont 1 sans reco validée ; aucun brouillon, donc les deux règles de mention donnent le même site |
| Mode « dépôt » (avant PR-CUT) | `publicsActifs` = tous les épisodes du dépôt : reproduit la règle actuelle, la parité est assurée par construction |
| Mode « atelier » (après PR-CUT) | `publicsActifs` = épisodes de la révision active ; `finalises` = `state["finalized"]` de `tools/output/pipeline/<source>.json` (`traiter_nouveaux_episodes.py:402`, `:495`) [V] |
| Amorçage | La première révision « atelier » prend `publicsActifs` = épisodes de `origin/main` au jour J de PR-CUT |
| Retrait | Un épisode ne quitte le public que par une commande explicite `retirerEpisode(guid)`, listée dans le diff. Retirer sa dernière mention ne le retire pas. |
| Œuvre sans mention publique | pas de page (404), comme aujourd'hui (`buildWorkIndex`, `aggregator.ts:138-194`) ; une œuvre fusionnée répond 301 (§6) |
| Brouillons | jamais publics : les deux règles actuelles sont unifiées sur `validated`, sans effet au HEAD |

Confirmation de la règle par le propriétaire : DV-08.

## 6. Identité des œuvres

### 6.1 Faits [M]

- 277 ids d'œuvre ont été supprimés dans l'historique Git.
- Pour 235 d'entre eux, `generate_item_id` (`identity.py:104-144`) redonnerait **le même id** à une nouvelle œuvre de même titre et créateur. Le rapprochement de `publier_episode._resolveur` ne trouve en effet que les œuvres **vivantes**, par titre et créateur, sans les alias (`publier_episode.py:79-95` ; `item_repo.py:91-103`).
- 233 de ces ids sont la source d'une redirection 301 : la page de la nouvelle œuvre serait inaccessible, car la redirection passe avant tout (`serveur.mjs:40`).
- 33 seraient rattachés à une œuvre vivante (même clé, un type commun) ; 9 recevraient un suffixe.
- Une redirection part d'une œuvre vivante : `8b112235` → `6426d70c` (N-02).

### 6.2 Registre des identifiants

**Ni versionné ni déployé** (décision du 24/10, DV-09). Tant que le corpus vit dans Git, le registre est **dérivé** de l'historique à chaque émission : c'est le calcul du script de mesure du 24/10, 1,1 s sur un portable pour 564 commits [M] ; un cache non suivi peut le garder entre deux passages. Condition : un clone complet sur venus (`git rev-parse --is-shallow-repository` doit répondre `false` ; vérifié sur le portable seulement). Après PR-CUT, il est stocké dans les données éditoriales de venus (hors clone, sauvegardées par Proton), puis devient la table `ids_emis` de SQLite (PR-13). La vitrine n'en a jamais besoin : elle ne lit que les redirections.

Exemple illustratif, construit sur des cas réels du corpus :

```json
{ "schemaVersion": 1, "source": "un-bon-moment",
  "ids": {
    "6426d70c": { "etat": "vivant",   "cles": [["balade mentale", "theo drieu kevin fauvre"],
                                               ["chaine christophe pauly", "theo drieu kevin fauvre"],
                                               ["chaine christophe pauly", ""]] },
    "324225cf": { "etat": "fusionne", "vers": "cdd07217", "le": "2026-10-23",
                  "cles": [["nardwuar vs", "nardwuar"]] },
    "5bf5e02f": { "etat": "supprime",
                  "cles": [["le fabuleux destin d amelie poulain", "jean pierre jeunet"]] } } }
```

- `cles` : toutes les clés de rattachement (titre et créateur normalisés par `_normalize_text`) que l'œuvre a portées : titre courant, anciens titres, alias. La première est la clé courante. Un alias donne deux clés : avec le créateur de l'œuvre, et sans créateur.
- **Dérivation** (PR-ID) : œuvres vivantes ; redirections (état `fusionne`) ; ids supprimés sans redirection (état `supprime`), leurs clés étant relues dans le dernier état Git de chaque fichier ; anciens titres relus dans l'historique de chaque fiche (coût non mesuré). C'est le calcul du script de mesure du 24/10, rendu idempotent. Ses comptes sont relus dans la PR.
- Le registre ne perd jamais un id.

### 6.3 Règles

| Règle | Contenu |
|---|---|
| R-ID-1 Émission | Un id neuf n'appartient ni au registre (tous états) ni aux fichiers vivants. Le suffixe `-n` est cherché dans cette union. |
| R-ID-2 Rattachement | Avant toute émission : (1) clé égale à une clé d'œuvre **vivante** et un type commun → rattachement (règle actuelle) ; (2) clé égale à une clé d'un id **fusionné** → rattachement **proposé** à la cible finale (chaîne `vers` suivie) ; (3) clé égale à celle d'un id **supprimé** → id neuf, signalé à la relecture. Comportement de (2) en mode automatique : DV-09. |
| R-ID-3 Ambiguïté | Une clé qui désigne plusieurs œuvres vivantes de même type n'est **plus** résolue par l'ordre des ids (`identity.py:167-176`, `publier_episode.py:75-77`). Elle est signalée ; la relecture choisit. |
| R-ID-4 Correction de titre | L'id ne change jamais. La nouvelle clé passe en tête de `cles` ; l'ancienne reste, et sert au rattachement. |
| R-ID-5 Fusion | Le perdant passe à `fusionne` avec `vers`. Ses mentions sont repointées **avant** la suppression du fichier (PR-01b), et ses clés lui restent. La redirection est dérivée de cet état. |
| R-ID-6 Scission | Si la partie séparée **est** l'ancienne fiche, son id est réactivé (`fusionne` → `vivant`) et la redirection disparaît : l'ancienne adresse redésigne la même œuvre, une adresse désigne donc toujours la même œuvre. Sinon, id neuf. Dans les deux cas, le diff liste toutes les pages touchées. |
| R-ID-7 Suppression sans fusion | État `supprime` ; l'adresse répond 404, comme aujourd'hui. |
| R-ID-8 Écrivain unique de l'identité | Un seul module (`tools/domain/registre_oeuvres.py`) émet, rattache, fusionne, scinde et supprime. Test statique : aucun appel à `generate_item_id` et aucune suppression de fichier d'œuvre en dehors de lui. |

### 6.4 Écrivains à couvrir

Relevé par recherche de chaînes [V], à compléter par l'inventaire exhaustif de PR-MC :

| Famille | Outils |
|---|---|
| Créent des œuvres | `publier_episode.py` (`_resolveur`) ; `migrate_reco_to_item_mention.py` et `repository/migration/reco_to_item_mention.py` (registre en mémoire seulement ; réécrivent toutes les œuvres, cf. mémoire du projet) : **refus** de `--apply` dès que le registre existe |
| Suppriment ou fusionnent | `fusion_items_doublons.py`, `fusionner_doublons_cures.py`, `redirections_oeuvres.py` |
| Changent titre, créateur ou types (donc les clés) | `aligner_titres_item_reco.py`, `aligner_types_item_reco.py`, `corriger_attributions_erronees.py`, `corrections_audit_2026_10.py`, `fix_creator_aliases.py`, `dataset_fixes.py`, la relecture (formulaire d'édition, après PR-MC-outils-2) |

### 6.5 Redirections

| Règle | Contenu |
|---|---|
| Source unique | Les redirections sont **dérivées** du registre (état `fusionne`) ; `redirections-oeuvres.json` devient un artefact produit. Invariant de transition : table = dérivation. |
| Dans la révision | Segment `redirections` de la révision (ADR 0058), lu dans le même instantané que la requête. |
| Invariants | Source qui est une œuvre vivante **avec page** : bloquant. Sans page : avertissement (cas `8b112235`). Cible sans page : avertissement (9 cas, ADR 0053). Pas de chaîne, pas de boucle. |
| Après activation | Une fusion ou une scission ne prend effet qu'avec la révision qui la porte ; un retour arrière rétablit la table de la révision visée, cohérente par construction. |

## 7. Requalification et miroirs

### 7.1 Commande

```text
requalifierMention(id, { kind?, guestWork?, recommendedBy?, status? }, auteur: 'humain'|'agent'|'lot')
  sous le verrou pipeline :
  1. lire la mention (propriétaire) et la reco (miroir) ;
  2. appliquer la décision (mêmes règles que review_actions.py) ;
  3. écrire la mention, puis la reco (écritures atomiques) ;
  4. événement review_events (ADR 0054, inchangé).
```

- Sémantique : `guestWork` vaut `true` ou est absent. `validate` et `citation` le retirent ; `guest-work` le pose ; `discard` garde `kind` et `guestWork` (`review_actions.py:43-46`).
- Appelants : `review_routes._apply_save_action` (`review_routes.py:532-545`), `apply_verdicts.py`, `poser_leur_oeuvre.py`, et `publier_episode.py` pour les mentions **existantes** : resynchronisation des seuls champs de mention, là où `publier_episode.py:138-140` les ignore aujourd'hui.
- Panne entre les étapes 3a et 3b : l'invariant « miroir = propriétaire » le détecte ; rejouer la commande est idempotent.

### 7.2 Cliquet en phase JSON

- La base de référence datée de PR-01 contient les 197 écarts connus.
- Le constructeur **refuse** une révision qui contient un écart absent de cette base.
- La base ne fait que se réduire. À l'issue de PR-MC-donnees, elle est vide pour les champs normalisés.

### 7.3 Miroirs

Les recos JSON restent l'entrée de la relecture jusqu'à SQLite (PR-14). Leurs champs d'œuvre et de mention sont des miroirs, régénérés par chaque écriture chez le propriétaire. Ils disparaissent quand **tous** les écrivains sont migrés.

## 8. Fixtures difficiles du PoC

Un **seul** corpus synthétique, source `fixtures-r2`, ids distincts, rangé dans `poc/fixtures/`. Le corpus pilote (saison 6 et 17 mentions de fermeture) n'est pas élargi [D]. Les données sont inventées ou réduites, sans citation réelle.

Chaque fixture a cinq attendus :
- **(N)** modèle normalisé (instantané JSON) ;
- **(A)** conflits listés, avec leur classe ;
- **(P)** projection V1 : égale à l'entrée, après application des décisions et des normalisations C1 ;
- **(R)** rendu : différences HTML, recherche, OG, routes et sitemap, toutes listées ;
- **(I)** invariants : bloquants et avertissements attendus.

| ID | Entrée | Attendus |
|---|---|---|
| **F1** `guestWork` contradictoire | Œuvre O1 ; M1 : reco `true`, mention absent (motif réel, 197 cas) ; M2 : reco absent, mention `true` (motif inverse, 0 cas) ; M3 : `true` des deux côtés | (N) une valeur par mention, sans agrégation entre mentions. (A) M1 : C3, proposition `true` ; M2 : C3 **sans** proposition ; M3 : C0. (R) badge « Leur œuvre » de la chronologie et section de la page épisode conformes aux décisions. (I) cliquet : un quatrième écart ajouté après la base de référence fait échouer la construction. |
| **F2** Homonymie | O2a « Vice », film, créateur A ; O2b « Vice », série, créateur B ; O2c et O2d : même clé et même type (motif réel « game of thrones ») ; candidat « Vice » sans créateur ; deux mentions de O2a dans un même épisode | (N) O2a et O2b distinctes ; les deux mentions d'un même épisode conservées. (A) le candidat qui touche O2c et O2d est **ambigu**, signalé, pas rattaché au premier id (R-ID-3). (R) aucune page fusionnée. (I) aucun. |
| **F3** Fusion puis scission | r1 : O3b fusionnée dans O3a ; r2 : scission, O3b redevient elle-même | (N) registre `vivant → fusionne → vivant`, aucun id neuf. (R) r1 : `/oeuvre/O3b` répond 301 vers O3a, et O3a liste toutes les mentions ; r2 : `/oeuvre/O3b` répond 200 et la redirection a disparu. Le diff r1 → r2 liste les deux fiches, les pages épisode, les entrées de recherche et le sitemap. (I) à chaque révision, aucune source de redirection n'est vivante. |
| **F4** URL concurrentes | Album O4 : M4a, Deezer `album/111` (édition standard) ; M4b, Deezer `album/222` (édition deluxe) ; film O4' : deux diffuseurs de même nom, régions FR et BE ; plus les paires équivalentes réelles (Steam, TMDB, Deezer `/fr/`, Instagram `?hl=fr`, YouTube avec `youtubeChannelId`) | (N) équivalences : une entrée par classe, sous le représentant validé ; contradiction : les deux URL gardées sur O4, marquées « à trancher » ; diffuseurs FR et BE gardés tous les deux. (A) une contradiction, avec provenance ; les équivalences en C1. (P) identique, sauf les liens des cartes de M4a et M4b (listés). (R) avant arbitrage : fiche inchangée, cartes de M4a et M4b avec les deux liens Deezer. Après la décision « l'édition deluxe est une autre œuvre » : O4-deluxe créée, M4b y est rattachée, chaque fiche et chaque carte montre son seul lien. (I) aucun attribut perdu ; aucun champ de lien sur une mention. |
| **F5** Absent, `null`, explicite | `guestWork` : absent, `null`, `false`, `true` ; `creator` : absent, `null`, `"Nom"`, `""` ; `year: null` ; `links: []` contre absent ; `kind` absent contre `"reco"` ; `tmdb: "1871"` contre `1871` | (N) `guestWork` : absent, absent, absent, `true` ; `creator` : absent, absent, `"Nom"`, et `""` **signalée et conservée** ; `year` absent ; `links` absent ; `kind: "reco"` ; `tmdb: 1871`. (P) égalité des sorties Zod, modulo ces règles C1. (R) aucune différence HTML. (I) test « aucun `null` dans la révision ». |
| **F6** Œuvre partagée entre saisons | O6 citée en S5 (M6a), deux fois dans un même épisode de S6 (M6b, M6c), et dans un épisode **sans saison** (M6d) | (N) fermeture du sous-graphe complète : M6a, M6d et leurs épisodes. (R) la fiche liste quatre mentions dans l'ordre des dates ; `recoCount`, tendance et statistiques par saison inchangés. (I) aucun. |
| **F7** Requalification après publication | r1 active : M7 validée, `kind: reco`, `guestWork: true` ; l'éditeur la requalifie en citation | (N) mention et reco égales, sans `guestWork`. (R) le diff r1 → r2 liste la page de l'épisode (la carte passe de « Leurs œuvres » à « Citations »), la fiche (« Recommandée N fois » diminue de 1, `aggregator.ts:180`), la carte OG de l'épisode (comptes) et les statistiques. (I) aucun écart résiduel ; activation seulement après approbation. |
| **F8** Id supprimé qui réapparaît | Registre : Y « Nardwuar vs » fusionnée dans X ; Z « Le Fabuleux Destin d'Amélie Poulain » supprimée sans redirection ; deux candidats portent ces clés | (N) premier candidat rattaché à X, ou refusé selon DV-09, jamais l'id Y ; second candidat : id neuf différent de Z, signalé. (I) `generate_item_id` ne rend jamais un id du registre ; le test statique R-ID-8 passe. |
| **F9** Redirection depuis une œuvre vivante | Œuvre vivante portée par une seule mention écartée, source d'une redirection (motif `8b112235`) | (I) avertissement. Si la mention devient validée, erreur **bloquante** : une page publique serait masquée par la 301. |

## 9. Projection, aller-retour et tests

### 9.1 Vue reco

```text
vueReco(m) = { id, sourceId, episodeGuid, timestamp, quote, recommendedBy, kind,
               guestWork, status, extractors, transcriptSource, note      ← mention
             , title, creator, types, year, externalIds (forme reco)      ← œuvre
             , links, linkOverrides, customLinks                          ← œuvre (§4.3)
             }
```

Les pages qui lisent des recos reçoivent la même forme qu'aujourd'hui, via `CatalogReader`.

### 9.2 Aller-retour fidèle

`projection(normaliser(V1))` est égale à `V1` au sens suivant :
- égalité profonde des **sorties Zod** des collections (ce que les pages consomment) ;
- après application des décisions d'arbitrage listées et des seules règles C1 approuvées.

Tout autre écart fait échouer le test. Le HTML est comparé sur toutes les routes du sous-graphe, après les seules normalisations listées dans le test (`lastmod`, `generatedAt`, `version.txt`).

### 9.3 Tests par PR

| PR | Tests du contrat |
|---|---|
| PoC-S6 | F1 à F9 ; aller-retour S6 ; classement de tous les conflits du corpus |
| PR-ID | R-ID-1 à R-ID-8 ; amorçage : 277 supprimés, 276 redirections, aucun id vivant perdu |
| PR-MC | `proprietaires.json` lu par TypeScript et Python ; `vueReco` d'une mention sans écart = reco d'origine ; ordre de résolution des liens (§4.3) ; R-V1 à R-V8 |
| PR-MC-sync | séquence `guest-work → validate → citation` sur mention existante ; test statique des écrivains |
| PR-MC-donnees | par lot : décisions toutes renseignées, diff `dist/` égal à la liste, aucun attribut de lien perdu, base de référence réduite |
| PR-03 | `estEpisodePublic` sur les 116 épisodes réels ; « aucun `null` » ; « champ interdit » ; « copie interdite » |
