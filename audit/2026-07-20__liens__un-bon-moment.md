# Audit des liens — un-bon-moment

**Date :** 2026-07-20 · **Outil :** `tools/link_check.py` (sonde HTTP, trois verdicts)

**1998 liens de recos validées** : 1898 vérifiés vivants, 100 non concluants, **0 morts**.

## Ce que la sonde établit — et ce qu'elle n'établit pas

Un verdict `alive` prouve que l'URL répond et sert une page réelle. Il ne prouve
**pas** qu'elle mène à la bonne œuvre : un domaine racheté ou une plateforme fermée
qui redirige répondent 200 tout autant. Voir le commit `08b6260`, qui a retiré
12 liens de ce type — dont un site d'humoriste devenu site de paris en ligne.

## Les non concluants

Aucun n'est un lien cassé.

| Cause | Nombre | Signification |
|---|---|---|
| 403 anti-bot | 69 | la plateforme refuse les robots (Fnac Spectacles, Decitre, Potemkine...) |
| 404 host opaque | 17 | Netflix / Deezer / HBO repondent 404 meme sur un identifiant reel |
| reseau / TLS | 11 | timeout ou certificat — jamais une preuve d'absence |
| autre (429, 503, 400) | 3 | transitoires |

Hosts concernés : www.fnacspectacles.com (38), www.netflix.com (13), www.deezer.com (3), www.decitre.fr (3), librairie.citebd.org (3), store.potemkine.fr (3), www.infoconcert.com (3), www.ombres-blanches.fr (2)…

## Effets de bord : deux problèmes de données

### 21 doublons probables

Recos distinctes pointant vers la même URL, dont les titres ne diffèrent que par
la transcription automatique. Le flag `duplicate_suspect` n'en signale que 25 au
total : ce détecteur en trouve que le flag rate.

| Recos | Titres | URL | Comment |
|---|---|---|---|
| ubm-1822, ubm-3156 | Continue tu m'intéresse · Continue, tu m'intéresses | https://podcasts.apple.com/fr/podcast/continue-tu-mint%C3%A9 | Introuvable sur Apple, le vrai titre : "Continue tu m'intéresse", le bon lien : https://podcasts.apple.com/fr/podcast/continue-tu-mint%C3%A9resses/id1812415752 | 
| ubm-1822, ubm-3156 | Continue tu m'intéresse · Continue, tu m'intéresses | https://shows.acast.com/continue-tu-minteresses | Comme au dessus - Le lien Acast est bon | 
| ubm-1158, ubm-1169, ubm-1737 | La prochaine fois que tu mordras la poussière · La prochaine fois tu mordras la poussière | https://www.placedeslibraires.fr/livre/9782253907824-la-proc | La Prochaine fois que tu mordras la poussière |
| ubm-0288, ubm-1395, ubm-1517, ubm-1793 | Pluribus · Puribus | https://tv.apple.com/fr/show/pluribus/umc.cmc.37axgovs2yozly | Pluribus - https://tv.apple.com/fr/show/pluribus/umc.cmc.37axgovs2yozlyh3c2cmwzlza |
| ubm-0648, ubm-0714, ubm-2436, ubm-2640, ubm-2716 | Bureau des Légendes · Le Bureau des Légendes · Le Bureau des légendes | https://www.allocine.fr/series/ficheserie-17907/streaming/ | Le Bureau des Légendes |
| ubm-2061, ubm-2077 | Canicule Sentimentale · Canicule Sentimentel | https://www.deezer.com/fr/show/1002058731 | Canicule sentimentale |
| ubm-2061, ubm-2077 | Canicule Sentimentale · Canicule Sentimentel | https://podcastaddict.com/podcast/canicule-sentimentale/5977 | Comme au dessus |
| ubm-2233, ubm-2761 | Adi Balcalide · Adi Balcalité | https://www.netflix.com/fr/title/81008236 | Adib Alkhalidey |
| ubm-2694, ubm-2984 | Validez · Validé | https://www.allocine.fr/series/ficheserie_gen_cserie=24293.h | Validé |
| ubm-2233, ubm-2761 | Adi Balcalide · Adi Balcalité | https://adibalkhalidey.com/ | Adib Alkhalidey |
| ubm-2253, ubm-2719 | Barbès Comedy Club · Barbès Comédie Club | https://lascenebarbes.fr/ | Barbès Comedy Club |
| ubm-0830, ubm-1083, ubm-1716 | Les mecs que je veux · Les mecs que je veux ken | https://podcasts.apple.com/fr/podcast/les-mecs-que-je-veux-k | Les mecs que je veux ken |
| ubm-0830, ubm-1083, ubm-1716 | Les mecs que je veux · Les mecs que je veux ken | https://shows.acast.com/les-mecs-que-je-veux-ken | Les mecs que je veux ken |
| ubm-1223, ubm-3048 | Julie Albertine · Julien Bertine | https://www.welovecomedy.fr/artistes/julie-albertine | Julie Albertine |
| ubm-2410, ubm-2950 | Laura Demange · Laura Dommange | https://www.lauradomenge.com/ | LAURA DOMENGE |
| ubm-0339, ubm-2081 | Bref de bons amis · De bons amis | https://www.disneyplus.com/fr-fr/browse/entity-52205147-9545 | Bref. De bons amis |
| ubm-0959, ubm-0992, ubm-2101 | Fiasco Rama · Fiasco Roman · Fiascorama | https://www.lalibrairie.com/livres/fiascorama_0-12649220_978 | Fiascorama |
| ubm-0959, ubm-0992, ubm-2101 | Fiasco Rama · Fiasco Roman · Fiascorama | https://www.buchetchastel.fr/catalogue/fiascorama/ | Fiascorama |
| ubm-1597, ubm-3188 | Floodcast · Le Flodcast | https://podcasts.apple.com/fr/podcast/floodcast/id1019768302 | FloodCast |
| ubm-1597, ubm-1665 | Floodcast · Le Flodcast | https://shows.acast.com/floodcast | Floodcast |
| ubm-2311, ubm-2574, ubm-2674 | Aurel · Aurel San | https://www.deezer.com/us/artist/259467 | Orelsan |

### 24 liens imprécis

Œuvres réellement distinctes pointant vers une page générique (site d'artiste, page
de tournée). Ce n'est pas faux, mais un lecteur qui clique sur un album donné
n'atterrit pas dessus.

| Recos | Titres | URL | Comment |
|---|---|---|---|
| ubm-2565, ubm-2992 | 60 · Une Bonne Soirée | https://www.kyan.fr/ | Il y a d'autres liens: Soixante et Une Bonne sont sur C+ | 
| ubm-0487, ubm-3128 | I Will Survive · Les Chiens de Navarre | https://www.chiensdenavarre.com/i-will-survive | Le lien est bon |
| ubm-1704, ubm-2898 | Les Poupées russes · Trilogie des Auberges espagnoles | https://www.sooner.fr/films/les-poupees-russes | OK |
| ubm-1058, ubm-2423, ubm-3049 | Barbès Comédie Club · Charlie Soignon · Shirley | https://www.shirleysouagnon.com/ | OK |
| ubm-1328, ubm-2509, ubm-2511 | Grand Corps Malade · Mesdames · Midi 20 | https://www.grandcorpsmalade.fr/ | Peut-être chercher les liens sur les plateformes en plus |
| ubm-1092, ubm-2070 | Alexandre Kominek · Bâtard sensible | https://alexandrekominek.fr/ | OK |
| ubm-3095, ubm-3119 | Jour de pluie · Pierre Hillairet | https://www.billetreduc.com/spectacle-pierre-hillairet.htm | OK, à fusionner avec ubm-0178, ubm-0506, ubm-1876, ubm-3119 |
| ubm-3095, ubm-3119 | Jour de pluie · Pierre Hillairet | https://humorix.fr/humoriste/pierre-hillairet/ | OK |
| ubm-0178, ubm-0506, ubm-1876, ubm-3119 | Jour de pluie · Pierre Hilleret | https://www.billetreduc.com/spectacle/pierre-hillairet-dans- | OK, à fusionner avec ubm-0178, ubm-0506, ubm-1876, ubm-3119 |
| ubm-0919, ubm-1506, ubm-3143 | Albert Moucahibert · Votre cerveau vous joue des tours | https://www.placedeslibraires.fr/livre/9782290218181-votre-c | OK |
| ubm-0919, ubm-1506, ubm-3143 | Albert Moucahibert · Votre cerveau vous joue des tours | https://allary-editions.fr/products/albert-moukheiber-votre- | OK |
| ubm-1178, ubm-2190, ubm-2317 | Les Quatre Accords Toltèques · Les Quatre Accords toltèques · The Four Agreements | https://www.placedeslibraires.fr/livre/9782889539215-les-qua | OK |
| ubm-1374, ubm-1611, ubm-3118 | Adèle Fougazi · Adèle Fugazi · Le Temps d'une Pause | https://www.adelfugazi.fr/ | OK |
| ubm-0178, ubm-0506, ubm-1876 | Jour de pluie · Pierre Hilleret | https://theatredumarais.fr/spectacle/pierre-hillairet/ | OK, à fusionner avec ubm-0178, ubm-0506, ubm-1876, ubm-3119 |
| ubm-1130, ubm-2516 | Diam's · Discographie de Diams | https://www.deezer.com/us/artist/388 | OK |
| ubm-0961, ubm-2124 | Blandine Lehoux · La vie de ta mère | https://www.blandinelehout.com/ | OK |
| ubm-0689, ubm-0690 | Quand je marche · Quarantaine | https://www.qobuz.com/fr-fr/album/paradis-ben-mazue/ba9qtjkx | NOK, à rechercher ailleurs sur Qobuz ou autre |
| ubm-2050, ubm-2093 | Marine Leonardi · Mauvaise Graine | https://www.fnacspectacles.com/artist/marine-leonardi/marine | OK |
| ubm-2050, ubm-2093 | Marine Leonardi · Mauvaise Graine | https://marineleonardi.com/ | OK |
| ubm-0334, ubm-2574 | Aurel San · La Civilisation | https://orelsan.lnk.to/civilisation | C'est "Civilisation" de Orelsan et OK |
| ubm-1048, ubm-2628 | L'anxiété · Les Failles | https://www.deezer.com/us/album/111106342 | OK |
| ubm-1048, ubm-2628 | L'anxiété · Les Failles | https://www.qobuz.com/fr-fr/album/les-failles-pomme/agjlo3az | NOK, à rechercher ailleurs sur Qobuz ou autre |
| ubm-2295, ubm-2614 | TAG World Championship · World Chase Tag | https://www.worldchasetag.com/ | OK |
| ubm-1067, ubm-2477 | Don't F**k with Cats · Don't F**k with Cats: Hunting an Internet Killer | https://www.netflix.com/title/81031373 | OK |

## Reproduire

La vérification tourne à l'écriture de chaque lien :

    python tools/apply_links.py --links <fichier.json> --guid <episodeGuid>

Le détail lien par lien (1998 entrées) est dans le JSON de même nom.
