# Liens trouvés mais NON posés — arbitrage rendu

*Relevé du 2026-08-17, arbitré le 2026-08-18 par l'éditeur du site.*

## Décision

**Tout est conservé, sauf les deux longs métrages**, qui restent de côté.
Pour « Inside Jamel Comedy Club », l'éditeur a fourni une playlist YouTube
(huit épisodes, vérifiée) qui remplace le dépôt archive.org proposé.

Posés depuis : la playlist Jamel Comedy Club (`ubm-0649`, `ubm-0674`),
« This is John » (`ubm-0777`) et « Désiré » (`ubm-1794`), tous deux des
courts métrages.

**Restent de côté, sans lien de visionnage :**

| reco | œuvre | durée | pourquoi |
|---|---|---|---|
| `ubm-0036` | Les Clés de bagnole (Laurent Baffie, 2003) | 86 min | long métrage |
| `ubm-3147` | NTM Authentiques (1998) | 83 min | long métrage documentaire |

Le reste de ce document conserve le relevé d'origine, pour mémoire.

---


## De quoi il s'agit

La recherche déléguée du 2026-08-17 a trouvé, pour six recommandations, une
copie **intégrale et regardable** de l'œuvre. La vérification (`yt-dlp` : titre,
durée, chaîne) confirme dans chaque cas qu'il s'agit bien de l'œuvre entière et
non d'un extrait.

Elle confirme aussi ce que le rapport ne disait pas : **aucune de ces copies
n'est déposée par un ayant droit**. Ce sont des remises en ligne par des
comptes tiers. Les poser rendrait service au lecteur ; cela ferait aussi du
site un annuaire de copies non autorisées.

Ce n'est pas une décision d'outil. Trois options :

1. **Poser les liens** — le lecteur y gagne, le site assume le renvoi.
2. **Poser avec `ethics: "avoid"`** — le lien existe, l'interface le signale,
   comme pour Amazon et Bolloré.
3. **Ne rien poser** — les recos restent signalées « sans moyen de voir », ce
   qui est le cas aujourd'hui.

Pour appliquer l'option retenue, ajouter les entrées choisies à
`tools/fix_liens_verifies.py` (table `LIENS`), qui vérifie le titre attendu
avant d'écrire.

## Les six cas

### Œuvres protégées remises en ligne par des comptes tiers

| reco | œuvre | lien | ce qui a été vérifié |
|---|---|---|---|
| `ubm-0036` | Les Clés de bagnole (Laurent Baffie, 2003) | `youtube.com/watch?v=wXCz0lMR6fo` | 86 min 38 s, compte « pp contact ». TMDB `movie/16930` annonce 90 min : durées compatibles, c'est le long-métrage entier. |
| `ubm-1794` | Désiré (Albert Dupontel, 1993) | `youtube.com/watch?v=jLuM_rqT4Po` | 15 min 49 s, compte « Comby JB ». TMDB `movie/334317` donne 16 min, même synopsis (un accouchement en 2050). |
| `ubm-3147` | NTM Authentiques (1998) | `youtube.com/watch?v=o--Fp1G5XPA` | 83 min, compte « MrResktwo ». C'est le documentaire complet — les copies en quatre parties trouvées ailleurs totalisent 58 min et sont donc tronquées. |
| `ubm-0777` | This is John (Jay & Mark Duplass, 2003) | `youtube.com/watch?v=4I1Ylynes8A` | 7 min 29 s, compte « Alex L. ». TMDB `movie/275061` confirme le court-métrage. |

### Émission déposée sur archive.org

| reco | œuvre | lien | ce qui a été vérifié |
|---|---|---|---|
| `ubm-0649`, `ubm-0674` | Inside Jamel Comedy Club | `archive.org/details/inside-jcc` | Huit épisodes complets en MP4 (8,3 Go), lecteur intégré. Dépôt d'un tiers, pas du producteur. |

## Ce qui a été posé, par contraste

Pour situer la limite retenue : les liens **conservés** proviennent tous soit
de la chaîne officielle de l'auteur (Éléonore Costes, Swann Périssé, Roman
Frayssinet, Shirley Souagnon, Jérémie Dethelot), soit de celle du producteur
(Kurzgesagt, Golden Moustache/M6), soit d'une plateforme légitime (Canal+,
Disney+, france.tv, TMDB « où regarder »).

Deux liens d'abord écartés par excès de prudence ont finalement été posés,
n'ayant rien à voir avec ce sujet : les pages « où regarder » de TMDB pour
« Run » (Lionsgate+) et « In Transit » (LaCinetek, Sooner).
