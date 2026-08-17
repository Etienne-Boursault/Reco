"""
link_families.py — à quelle FAMILLE appartient un lien, et laquelle manque.

POURQUOI CE MODULE EXISTE
-------------------------
« Cette reco a-t-elle assez de liens ? » n'a pas de réponse universelle : un
film a besoin d'une fiche et d'un moyen de le voir, un livre d'un libraire, un
spectacle d'une billetterie. Compter les liens ne dit rien ; il faut savoir
LESQUELS.

Un premier tri, écrit à la va-vite, comparait les hôtes en ÉGALITÉ exacte. Il
manquait donc `cameronwinter.bandcamp.com` — un compte Bandcamp, donc un
musicien — et rangeait la reco parmi les indécidables. Il ignorait aussi une
douzaine d'hôtes qui disent pourtant clairement de quoi il s'agit :
`printemps-bourges.com` est un festival de musique, `welovecomedy.fr` un site
d'humour, `allary-editions.fr` un éditeur. La comparaison se fait ici en
SUFFIXE, et la table vient du corpus réel (369 hôtes relevés le 2026-08-17).

CE QUE CE MODULE NE FAIT PAS
----------------------------
Il ne devine rien. Un hôte inconnu reste `None` : mieux vaut une famille
absente qu'une famille inventée, puisque c'est sur elle qu'on décidera d'aller
chercher un lien — et chercher au mauvais endroit produit des homonymes.
"""
from __future__ import annotations

from urllib.parse import urlparse

__all__ = [
    "FAMILLES_ATTENDUES",
    "HOTES",
    "famille",
    "familles_manquantes",
    "familles_presentes",
    "hote_de",
]

#: Hôte → famille. Relevé sur le corpus, pas deviné. Un hôte peut servir
#: plusieurs usages (YouTube héberge des chaînes ET des clips) : on retient
#: l'usage DOMINANT dans ce corpus, et le type de la reco tranche le reste.
HOTES: dict[str, str] = {
    # --- Écoute musicale ---------------------------------------------------
    "deezer.com": "ecoute",
    "open.spotify.com": "ecoute",
    "spotify.com": "ecoute",
    "music.apple.com": "ecoute",
    "qobuz.com": "ecoute",
    "tidal.com": "ecoute",
    "music.youtube.com": "ecoute",
    "bandcamp.com": "ecoute",
    "soundcloud.com": "ecoute",
    "discogs.com": "ecoute",
    "genius.com": "ecoute",
    "infoconcert.com": "ecoute",
    "printemps-bourges.com": "ecoute",
    "lnk.to": "ecoute",
    # --- Fiche d'œuvre à l'écran -------------------------------------------
    "imdb.com": "fiche",
    "themoviedb.org": "fiche",
    "allocine.fr": "fiche",
    "senscritique.com": "fiche",
    "thetvdb.com": "fiche",
    # --- Où voir : streaming, VOD ------------------------------------------
    "netflix.com": "visionnage",
    "tv.apple.com": "visionnage",
    "primevideo.com": "visionnage",
    "disneyplus.com": "visionnage",
    "hbomax.com": "visionnage",
    "canalplus.com": "visionnage",
    "sooner.fr": "visionnage",
    "universcine.com": "visionnage",
    "lacinetek.com": "visionnage",
    "molotov.tv": "visionnage",
    "justwatch.com": "visionnage",
    "arte.tv": "visionnage",
    "france.tv": "visionnage",
    "auvio.rtbf.be": "visionnage",
    "filmotv.fr": "visionnage",
    "videofutur.fr": "visionnage",
    "orange.fr": "visionnage",
    "rakuten.tv": "visionnage",
    "mubi.com": "visionnage",
    "pathehome.com": "visionnage",
    "m6.fr": "visionnage",
    "6play.fr": "visionnage",
    # --- Libraires et éditeurs ---------------------------------------------
    "placedeslibraires.fr": "libraire",
    "parislibrairies.fr": "libraire",
    "lalibrairie.com": "libraire",
    "mollat.com": "libraire",
    "decitre.fr": "libraire",
    "librest.com": "libraire",
    "fnac.com": "libraire",
    "gallimard.fr": "libraire",
    "gallimard-bd.fr": "libraire",
    "albin-michel.fr": "libraire",
    "editions-delcourt.fr": "libraire",
    "editions.flammarion.com": "libraire",
    "allary-editions.fr": "libraire",
    "glenat.com": "libraire",
    "kana.fr": "libraire",
    "editionsdutresor.com": "libraire",
    "citebd.org": "libraire",
    "babelio.com": "libraire",
    # --- Billetterie et salles ---------------------------------------------
    "billetreduc.com": "billetterie",
    "fnacspectacles.com": "billetterie",
    "theatreonline.com": "billetterie",
    "billetweb.fr": "billetterie",
    "theatredumarais.fr": "billetterie",
    "lascenebarbes.fr": "billetterie",
    "barbescomedyclub.com": "billetterie",
    "offi.fr": "billetterie",
    "jds.fr": "billetterie",
    "encoreuntour.com": "billetterie",
    "ticketmaster.fr": "billetterie",
    "lavillette.com": "billetterie",
    "humorix.fr": "billetterie",
    "welovecomedy.fr": "billetterie",
    "feverup.com": "billetterie",
    # --- Vidéo en ligne ----------------------------------------------------
    "youtube.com": "video",
    "twitch.tv": "video",
    "dailymotion.com": "video",
    "vimeo.com": "video",
    # --- Podcasts ----------------------------------------------------------
    "shows.acast.com": "podcast",
    "acast.com": "podcast",
    "podcasts.apple.com": "podcast",
    "louiemedia.com": "podcast",
    # --- Jeux --------------------------------------------------------------
    "store.steampowered.com": "jeu",
    "itch.io": "jeu",
    "gog.com": "jeu",
    "nintendo.com": "jeu",
    "playstation.com": "jeu",
    # --- Applications ------------------------------------------------------
    "apps.apple.com": "application",
    "play.google.com": "application",
    # --- Réseaux sociaux ---------------------------------------------------
    "instagram.com": "reseau",
    "tiktok.com": "reseau",
    "facebook.com": "reseau",
    "x.com": "reseau",
    "twitter.com": "reseau",
    "bsky.app": "reseau",
    # --- Encyclopédie ------------------------------------------------------
    "wikipedia.org": "encyclopedie",
    "wikidata.org": "encyclopedie",
}

#: Type de reco → familles ATTENDUES. Une famille absente de cette table n'est
#: jamais réclamée : on ne signale un manque que là où il est vraiment un
#: manque. `artiste` n'attend rien — le type couvre aussi bien un musicien
#: qu'un humoriste, et réclamer un lien d'écoute pour tous produirait des
#: homonymes (cf. `enrich_music_links`, « POURQUOI `artiste` EST OPT-IN »).
FAMILLES_ATTENDUES: dict[str, tuple[str, ...]] = {
    "film": ("fiche", "visionnage"),
    "serie": ("fiche", "visionnage"),
    "musique": ("ecoute",),
    "album": ("ecoute",),
    "livre": ("libraire",),
    "bd": ("libraire",),
    "spectacle": ("billetterie",),
    "podcast": ("podcast",),
    "chaine": ("video",),
    "jeu": ("jeu",),
    "application": ("application",),
}


def hote_de(url: object) -> str:
    """Hôte d'une URL, sans `www.` ni casse. Vide si l'URL est illisible.

    `urlparse` LÈVE sur un IPv6 malformé (« https://[::1 ») : une seule URL
    saisie de travers ne doit pas faire tomber tout un audit.
    """
    try:
        return (urlparse(str(url)).hostname or "").lower().removeprefix("www.")
    except ValueError:
        return ""


def famille(url: object) -> str | None:
    """Famille d'un lien, ou None si l'hôte n'est pas répertorié.

    Comparaison en SUFFIXE : `cameronwinter.bandcamp.com` est un compte
    Bandcamp, `fr.wikipedia.org` une Wikipédia. Une égalité stricte manquait
    les deux.

    >>> famille("https://cameronwinter.bandcamp.com/album/heavy-metal")
    'ecoute'
    >>> famille("https://exemple-inconnu.fr/page") is None
    True
    """
    h = hote_de(url)
    if not h:
        return None
    # Le suffixe le plus LONG gagne : « music.apple.com » (écoute) doit primer
    # sur un éventuel « apple.com » générique.
    correspondances = [(cle, fam) for cle, fam in HOTES.items()
                       if h == cle or h.endswith("." + cle)]
    if not correspondances:
        return None
    return max(correspondances, key=lambda kv: len(kv[0]))[1]


def familles_presentes(liens) -> set[str]:
    """Familles couvertes par les liens d'une reco."""
    out = set()
    for lien in (liens or []):
        url = lien.get("url") if isinstance(lien, dict) else lien
        if (f := famille(url)):
            out.add(f)
    return out


def familles_manquantes(types, liens) -> set[str]:
    """Familles attendues par les types de la reco et qu'aucun lien ne couvre.

    Un type inconnu de `FAMILLES_ATTENDUES` n'attend rien : mieux vaut ne rien
    réclamer que réclamer à tort, puisque c'est sur cette liste qu'on ira
    chercher — et chercher au mauvais endroit produit des faux liens.
    """
    attendues: set[str] = set()
    for t in (types or []):
        attendues.update(FAMILLES_ATTENDUES.get(t, ()))
    return attendues - familles_presentes(liens)
