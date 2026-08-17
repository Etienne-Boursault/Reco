"""review_search_links.py — Liens de RECHERCHE pré-remplis pour /tableau.

Pourquoi
--------
Les APIs ne savent plus tout établir. JustWatch n'est plus exposé par TMDB
(`watch/providers.results.FR.link` pointe désormais vers themoviedb.org, et les
451 valeurs stockées étaient en réalité des URL TMDB sous un champ nommé
`justwatch` — depuis renommé `externalIds.watchPage`, cf.
`tools/migrate_watch_page.py`). AlloCiné n'a aucune API publique.
L'API Spotify répond 403 sur tous ses endpoints. Restent 118 recos film/série
sans fiche de référence et 94 recos musicales sans plateforme d'écoute : elles
se finiront à la main. Ce module prépare ce travail manuel en posant, à côté
des liens réellement établis, une recherche pré-remplie par plateforme
pertinente — de quoi partir en un clic au lieu de retaper le titre.

Pourquoi ce module ne s'appuie pas sur `review_links`
------------------------------------------------------
`review_links.py` fait des URL de recherche lui aussi, et 12 gabarits sont
communs aux deux modules. La duplication est réelle — mais fusionner casserait
deux propriétés, parce que les contrats sont OPPOSÉS :

- `review_links` répond « meilleure URL connue » : `auto_url("Deezer", reco)`
  renvoie `externalIds.deezer` s'il existe, et la recherche seulement en repli.
  Ici il faut l'inverse, TOUJOURS une recherche. Brancher le tableau dessus
  poserait des URL d'identifiant sous une étiquette « 🔍 recherche » — soit
  exactement le mensonge que ce module existe pour éviter.
- `review_links` est le MIROIR de `src/data/merchants.ts`, et sa valeur tient à
  ce qu'on puisse lire les deux fichiers côte à côte. Il doit donc refléter le
  site public même quand celui-ci se trompe : trois de ses URL sont cassées
  (cf. `_ECARTEES` ci-dessous) et les corriger LÀ-BAS désynchroniserait le
  miroir d'un fichier de `src/`. Ici, au contraire, une URL cassée est
  éliminatoire.
- Sa table `AUTO_PLATFORMS_BY_TYPE` énumère ce que le SITE affiche. AlloCiné,
  IMDb, SensCritique, TMDB, OpenLibrary n'y ont rien à faire, et c'est
  précisément ce dont la curation a besoin.

La duplication est donc assumée, mais SURVEILLÉE : `test_review_search_links`
compare les deux jeux de gabarits et échoue sur toute divergence non déclarée.
C'est ce test, et non une fusion, qui protège du drift.

La ligne à ne pas franchir
--------------------------
Ces URL ne sont JAMAIS écrites dans `src/content/recos/**.json` et n'existent
que dans le serveur de relecture. Présenter une URL de recherche comme la fiche
de l'œuvre tromperait le visiteur : sur le site public, « JustWatch » doit
mener à la fiche, pas à un formulaire vide. C'est un outil de curation interne,
pas une donnée du corpus.

Vérification des formes d'URL
-----------------------------
Chaque gabarit ci-dessous a été interrogé en HTTP avant d'être retenu (juillet
2026) : code de retour, ET présence du terme cherché dans la page quand le site
n'est pas une application JavaScript. Pour les SPA (Spotify, Bandcamp, Apple
Podcasts), la preuve est une contre-épreuve : la route de recherche répond 200
là où une route bidon sur le même hôte répond 404.

Cinq plateformes ont été ÉCARTÉES faute de forme GET stable. Les trois
premières sont aussi celles que `review_links` / `merchants.ts` publient
CASSÉES aujourd'hui — signalé, pas corrigé ici (ce serait toucher `src/`) :

- Lalibrairie.com   : la recherche est un POST avec jeton CSRF ; en GET,
                      `/livres/recherche.html?q=…` répond 404 (or c'est
                      exactement l'URL que `src/data/merchants.ts` publie).
- BilletReduc       : `/recherche/index.htm?txt=…` (forme du miroir) est un
                      soft-404 : même page pour une requête réelle et une
                      route bidon, sans jamais le terme cherché. La forme
                      retenue ici, `/search.htm?se=…`, elle, cherche.
  (Fnac Spectacles a QUITTÉ cette liste le 2026-08-16 : l'hôte refuse toujours
  les requêtes HTTP directes, mais une vérification EN NAVIGATEUR a tranché —
  la forme publiée par le site était cassée, la bonne est `/search/?searchterm=`.
  Un hôte injoignable en HTTP n'est donc pas un hôte invérifiable.)
- Babelio           : connexion réinitialisée à chaque tentative (empreinte
                      TLS) ; aucune preuve que la forme d'URL soit bonne.
- IGDB              : 403 Cloudflare ; SensCritique et Steam couvrent `jeu`.
- leslibraires.fr   : 403 sur toutes les routes.

Encodage
--------
Deux encodeurs, parce qu'un `+` ne veut pas dire « espace » partout :
`quote_plus` pour les paramètres de query string (`?q=`, `?term=`…), `quote`
pour les segments de CHEMIN (Deezer, Google Maps) où un `+` resterait un `+`
littéral. Les gabarits le disent d'eux-mêmes : `{q}` = query string,
`{p}` = chemin.
"""
from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import NamedTuple
from urllib.parse import quote, quote_plus

__all__ = [
    "SEARCH_PLATFORMS",
    "SEARCH_PLATFORMS_BY_TYPE",
    "search_links",
]


class _Platform(NamedTuple):
    """Une plateforme interrogeable par URL de recherche.

    `hosts` sert à NE PAS proposer une recherche déjà résolue : si la reco
    porte un lien sur l'un de ces hôtes, la puce est tue. Les hôtes sont notés
    sans `www.` et comparés par suffixe, ce qui attrape aussi les
    sous-domaines (`daftpunk.bandcamp.com` compte comme Bandcamp).
    """

    label: str
    template: str
    hosts: tuple[str, ...]


#: Plateformes par clé interne. Deux clés peuvent partager un `label` (Deezer
#: musique / Deezer podcast) : la déduplication se fait sur le label affiché,
#: pour ne jamais montrer deux puces « Deezer » sur la même ligne.
SEARCH_PLATFORMS: dict[str, _Platform] = {
    # --- Film / série ------------------------------------------------------
    "allocine": _Platform(
        "AlloCiné", "https://www.allocine.fr/rechercher/?q={q}",
        ("allocine.fr",)),
    "justwatch": _Platform(
        "JustWatch", "https://www.justwatch.com/fr/recherche?q={q}",
        ("justwatch.com",)),
    "senscritique": _Platform(
        "SensCritique", "https://www.senscritique.com/search?query={q}",
        ("senscritique.com",)),
    "tmdb": _Platform(
        "TMDB", "https://www.themoviedb.org/search?query={q}",
        ("themoviedb.org",)),
    "imdb": _Platform(
        "IMDb", "https://www.imdb.com/find/?q={q}",
        ("imdb.com",)),
    # --- Musique -----------------------------------------------------------
    "deezer": _Platform(
        "Deezer", "https://www.deezer.com/fr/search/{p}",
        ("deezer.com",)),
    "deezer_podcast": _Platform(
        "Deezer", "https://www.deezer.com/fr/search/{p}/podcast",
        ("deezer.com",)),
    "spotify": _Platform(
        "Spotify", "https://open.spotify.com/search/{p}",
        ("spotify.com",)),
    "bandcamp": _Platform(
        "Bandcamp", "https://bandcamp.com/search?q={q}",
        ("bandcamp.com",)),
    "qobuz": _Platform(
        "Qobuz", "https://www.qobuz.com/fr-fr/search?q={q}",
        ("qobuz.com",)),
    "apple_music": _Platform(
        "Apple Music", "https://music.apple.com/fr/search?term={q}",
        ("music.apple.com",)),
    "apple_podcasts": _Platform(
        "Apple Podcasts", "https://podcasts.apple.com/fr/search?term={q}",
        ("podcasts.apple.com",)),
    # --- Livre / BD — librairies indépendantes d'abord (cf. politique
    #     éditoriale : Amazon est marqué `avoid`, on ne l'ajoute pas ici).
    "place_libraires": _Platform(
        "Place des Libraires",
        "https://www.placedeslibraires.fr/listeliv.php"
        "?base=allbooks&mots_recherche={q}",
        ("placedeslibraires.fr",)),
    "librairies_indep": _Platform(
        "Librairies indép.",
        "https://www.librairiesindependantes.com/product/search/?query={q}",
        ("librairiesindependantes.com",)),
    "openlibrary": _Platform(
        "OpenLibrary", "https://openlibrary.org/search?q={q}",
        ("openlibrary.org",)),
    # --- Jeu / spectacle / lieu / vidéo ------------------------------------
    "steam": _Platform(
        "Steam", "https://store.steampowered.com/search/?term={q}",
        ("steampowered.com",)),
    "billetreduc": _Platform(
        "BilletReduc", "https://www.billetreduc.com/search.htm?se={q}",
        ("billetreduc.com",)),
    # Réintégré le 2026-08-16 : l'hôte refuse les requêtes HTTP directes, mais
    # la vérification EN NAVIGATEUR a montré que la forme du site était cassée
    # et donné la bonne (`/search/?searchterm=`, minuscules).
    "fnac_spectacles": _Platform(
        "Fnac Spectacles", "https://www.fnacspectacles.com/search/?searchterm={q}",
        ("fnacspectacles.com",)),
    "google_maps": _Platform(
        "Google Maps", "https://www.google.com/maps/search/{p}",
        ("google.com",)),
    "youtube": _Platform(
        "YouTube", "https://www.youtube.com/results?search_query={q}",
        ("youtube.com", "youtu.be")),
    # --- Repli universel ---------------------------------------------------
    "web": _Platform(
        "Web", "https://duckduckgo.com/?q={q}",
        ("duckduckgo.com",)),
}

#: Recherches proposées par type de reco. L'ordre fait foi pour l'affichage :
#: la plateforme la plus susceptible de trancher vient en premier.
SEARCH_PLATFORMS_BY_TYPE: dict[str, tuple[str, ...]] = {
    "film":        ("justwatch", "allocine", "senscritique", "tmdb", "imdb"),
    "serie":       ("justwatch", "allocine", "senscritique", "tmdb", "imdb"),
    "musique":     ("deezer", "spotify", "bandcamp", "qobuz", "apple_music"),
    "album":       ("deezer", "spotify", "bandcamp", "qobuz", "apple_music"),
    # `artiste` récolte les plateformes d'écoute (brief), plus une recherche
    # web : dans ce corpus, un « artiste » est souvent un·e humoriste, pour
    # qui Deezer ne dira rien.
    "artiste":     ("deezer", "spotify", "bandcamp", "qobuz", "apple_music",
                    "web"),
    "livre":       ("place_libraires", "librairies_indep", "openlibrary"),
    "bd":          ("place_libraires", "librairies_indep", "openlibrary"),
    "podcast":     ("deezer_podcast", "apple_podcasts"),
    "jeu":         ("senscritique", "steam"),
    "spectacle":   ("billetreduc", "fnac_spectacles", "web"),
    "lieu":        ("google_maps", "web"),
    "chaine":      ("youtube", "web"),
    "video":       ("youtube", "web"),
    "application": ("web",),
    "autre":       ("web",),
}

#: Repli pour une reco sans type, ou d'un type hors vocabulaire : au minimum
#: une recherche web, jamais une ligne sans porte de sortie.
_DEFAULT_KEYS: tuple[str, ...] = ("web",)


def _query(title: str, creator: str) -> str:
    """« Titre Artiste », l'un des deux seul, ou "" si les deux manquent.

    Sans rien à chercher, une recherche pré-remplie ne cherche rien : mieux
    vaut aucune puce qu'une puce qui ouvre un formulaire vide.
    """
    parts = (str(title or "").strip(), str(creator or "").strip())
    return " ".join(p for p in parts if p)


def _covered_hosts(links: Iterable[dict] | None) -> set[str]:
    """Hôtes déjà couverts par les VRAIS liens de la reco, sans `www.`.

    Découpage manuel plutôt qu'`urlparse` : ce dernier lève ValueError sur
    certaines URL mal formées, et on est sur un chemin d'affichage qui ne doit
    jamais casser le rendu du tableau.
    """
    hosts: set[str] = set()
    for link in links or ():
        url = link.get("url") if isinstance(link, dict) else None
        if not url:
            continue
        host = str(url).split("//", 1)[-1].split("/", 1)[0]
        host = host.split("@")[-1].split(":")[0].lower().removeprefix("www.")
        if host:
            hosts.add(host)
    return hosts


def _is_covered(signature: tuple[str, ...], hosts: set[str]) -> bool:
    """Un des hôtes de la reco appartient-il à cette plateforme ?

    Comparaison par suffixe pour attraper les sous-domaines : une page
    d'artiste `xxx.bandcamp.com` vaut bien un lien Bandcamp.
    """
    return any(host == sig or host.endswith("." + sig)
               for sig in signature for host in hosts)


def search_links(title: str, creator: str, types: Sequence[str] | None,
                 links: Iterable[dict] | None) -> list[dict]:
    """Recherches pré-remplies MANQUANTES pour une reco.

    Retourne `[{label, url, hint}, …]` : une plateforme déjà présente parmi les
    liens de la reco est tue (on ne propose pas de chercher ce qui est trouvé).
    Le résultat sert UNIQUEMENT au tableau de relecture — cf. l'en-tête du
    module.
    """
    query = _query(title, creator)
    if not query:
        return []
    hosts = _covered_hosts(links)
    keys: list[str] = []
    for reco_type in types or ():
        keys.extend(SEARCH_PLATFORMS_BY_TYPE.get(reco_type, _DEFAULT_KEYS))
    if not keys:
        keys = list(_DEFAULT_KEYS)
    out: list[dict] = []
    seen: set[str] = set()
    for key in keys:
        platform = SEARCH_PLATFORMS[key]
        if platform.label in seen:
            continue
        seen.add(platform.label)
        if _is_covered(platform.hosts, hosts):
            continue
        out.append({
            "label": platform.label,
            "url": platform.template.format(q=quote_plus(query),
                                            p=quote(query)),
            # Court à dessein : répété ~3800 fois dans la page. Le « pas la
            # fiche » est aussi porté par le style pointillé et l'info-bulle
            # du replieur, il n'a pas à être développé sur chaque puce.
            "hint": f"Recherche « {query} » sur {platform.label}"
                    f" — pas la fiche",
        })
    return out
