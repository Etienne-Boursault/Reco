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
    # Boutiques de CAPTATION : on y achète le spectacle filmé, pas une
    # place. Elles répondent donc à « où le voir », pas à « où le voir
    # sur scène ».
    "darksmile.tv": "visionnage",
    "vod.blanchegardin.com": "visionnage",
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
    # Prêt numérique : on y emprunte l'ouvrage, ce qui répond bien à « où
    # le lire » — souvent le seul recours pour un livre épuisé.
    "archive.org": "libraire",
    # Boutique de So Press, qui édite et vend le magazine Society.
    "boutique.so": "libraire",
    # --- Billetterie et salles ---------------------------------------------
    # Liste des dates de tournée et renvoie vers la vente : une
    # billetterie, non un service d'écoute.
    "infoconcert.com": "billetterie",
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
    # Plateformes et studios relevés sur les recos typées `podcast` du corpus.
    # Un site PERSONNEL d'auteur (joerogan.com, billburr.com…) reste hors table :
    # il dit où trouver la personne, pas où écouter l'émission.
    "arteradio.com": "podcast",
    "binge.audio": "podcast",
    "audiomeans.fr": "podcast",
    "podcastaddict.com": "podcast",
    "lavoixdanstatete.com": "podcast",
    "orsomedia.io": "podcast",
    "2hdp.fr": "podcast",
    # --- Jeux --------------------------------------------------------------
    "store.steampowered.com": "jeu",
    "itch.io": "jeu",
    "gog.com": "jeu",
    "nintendo.com": "jeu",
    "playstation.com": "jeu",
    # --- Applications ------------------------------------------------------
    "apps.apple.com": "application",
    "play.google.com": "application",
    # Sites d'ÉDITEUR. Pour un logiciel, la page de l'éditeur est la référence
    # — souvent meilleure qu'une fiche de boutique, qui ne couvre qu'une
    # plateforme. Ces trois-là n'existent que sous cette forme dans le corpus.
    "splice.com": "application",
    "getbrick.com": "application",
    "geev.com": "application",
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

    # =====================================================================
    # SECOND RELEVÉ — 257 hôtes du corpus n'étaient pas classés, pour
    # 359 liens. La majorité sont des sites PERSONNELS d'artistes, qu'aucune
    # table ne peut énumérer et qui n'appartiennent à aucune famille. Ce qui
    # suit ne retient que les plateformes MULTI-ŒUVRES : celles où l'on peut
    # chercher une autre œuvre que celle qui les a fait entrer ici.
    #
    # ABSENT À DESSEIN — `amazon.fr` est bien un libraire, mais le compter
    # comme tel éteindrait le signalement sur les recos qui n'ont QUE ce
    # lien : or ce sont précisément celles où chercher un indépendant.
    # ABSENT À DESSEIN — `apple.com`, `linkedin.com` servent tout et
    # n'importe quoi : les classer rendrait la table menteuse.
    # =====================================================================
    # --- Libraires et éditeurs (2e relevé, 2026-08-17) -------------------
    "leslibraires.fr": "libraire",
    "librairie-de-paris.fr": "libraire",
    "librairie-des-femmes.fr": "libraire",
    "librairie-gallimard.com": "libraire",
    "librairie-sciencespo.fr": "libraire",
    "librairies-alip.fr": "libraire",
    "librairiesindependantes.com": "libraire",
    "libraires-ensemble.com": "libraire",
    "ombres-blanches.fr": "libraire",
    "furet.com": "libraire",
    "halldulivre.com": "libraire",
    "lesmots-leschoses.fr": "libraire",
    "buchetchastel.fr": "libraire",
    "pol-editeur.com": "libraire",
    "seuil.com": "libraire",
    "harpercollins.fr": "libraire",
    "jailu.com": "libraire",
    "la-pleiade.fr": "libraire",
    "folio-lesite.fr": "libraire",
    "editions-tredaniel.com": "libraire",
    "exemplaire-editions.fr": "libraire",
    "champsocial.com": "libraire",
    "lesimpressionsnouvelles.com": "libraire",
    "eyrolles.com": "libraire",
    "dupuis.com": "libraire",
    "dargaud.com": "libraire",
    "ki-oon.com": "libraire",
    "bdfugue.com": "libraire",
    "leloup.org": "libraire",
    # --- Fiches : presse spécialisée, bases, distributeurs ----------------
    # Un DISTRIBUTEUR (Le Pacte, A24, StudioCanal) présente l'œuvre sans la
    # diffuser : c'est une fiche, pas un moyen de la voir.
    "jeuxvideo.com": "fiche",
    "trictrac.net": "fiche",
    "ludovox.fr": "fiche",
    "manga-news.com": "fiche",
    "nanarland.com": "fiche",
    "lostmediawiki.com": "fiche",
    "musicbrainz.org": "fiche",
    "le-pacte.com": "fiche",
    "a24films.com": "fiche",
    "outplayfilms.com": "fiche",
    "studiocanal.fr": "fiche",
    "kinolorber.com": "fiche",
    "detourfilm.com": "fiche",
    "baborentertainment.com": "fiche",
    "cinematheque.fr": "fiche",
    "brefcinema.com": "fiche",
    # --- Jeux : boutiques et sites officiels ------------------------------
    "philibertnet.com": "jeu",
    "passiondujeu.fr": "jeu",
    "epicgames.com": "jeu",
    "geoguessr.com": "jeu",
    "cemantix.certitudes.org": "jeu",
    "undertale.com": "jeu",
    "polytopia.io": "jeu",
    "hempuli.com": "jeu",
    "latabledessavoirs.fr": "jeu",
    "wooga.com": "jeu",
    # --- Où voir (2e relevé) ---------------------------------------------
    "crunchyroll.com": "visionnage",
    "animationdigitalnetwork.com": "visionnage",
    "hbo.com": "visionnage",
    "pluto.tv": "visionnage",
    "madelen.ina.fr": "visionnage",
    "vod.mediatheque-numerique.com": "visionnage",
    "cinemasalademande.com": "visionnage",
    "store.potemkine.fr": "visionnage",
    "cinemutins.com": "visionnage",
    "intl.paramountplus.com": "visionnage",
    "francetelevisions.fr": "visionnage",
    # --- Billetterie et salles (2e relevé) --------------------------------
    "spectable.com": "billetterie",
    "shotgun.live": "billetterie",
    "casinodeparis.fr": "billetterie",
    "comedie-francaise.fr": "billetterie",
    "theatredesbeliersparisiens.com": "billetterie",
    "theatredelarenaissance.com": "billetterie",
    "theatrelabruyere.com": "billetterie",
    "lapetiteloge.fr": "billetterie",
    "lepointvirgule.com": "billetterie",
    "gaite.com": "billetterie",
    "panameartcafe.com": "billetterie",
    "lefridgecomedy.com": "billetterie",
    "academiedhumour.com": "billetterie",
    "stage-entertainment.fr": "billetterie",
    "lalettre-spectacle.fr": "billetterie",
    "ruqspectacles.fr": "billetterie",
    "20h40.fr": "billetterie",
    "lekings.be": "billetterie",
    "infinitix.be": "billetterie",
    "pathe.fr": "billetterie",
    "ugc.fr": "billetterie",
    "ticketingcine.com": "billetterie",
}

#: Type de reco → attentes. Chaque attente est un groupe d'ALTERNATIVES :
#: elle est satisfaite dès qu'une seule des familles du groupe est présente,
#: et son premier élément est le nom sous lequel le manque est signalé.
#:
#: Une famille absente de cette table n'est jamais réclamée : on ne signale un
#: manque que là où il est vraiment un manque. `artiste` n'attend rien — le
#: type couvre aussi bien un musicien qu'un humoriste, et réclamer un lien
#: d'écoute pour tous produirait des homonymes (cf. `enrich_music_links`,
#: « POURQUOI `artiste` EST OPT-IN »).
#:
#: POURQUOI UN SPECTACLE ACCEPTE UNE CAPTATION
#: Réclamer une billetterie pour « Baby J », « Foresti Party » ou « L'autre,
#: c'est moi » n'a pas de sens : ces spectacles sont finis, il n'y a aucune
#: place à vendre, et ce qu'on peut en proposer au lecteur EST la captation.
#: Dix-sept recos étaient ainsi signalées pour un manque que rien ne pouvait
#: combler. Un spectacle attend donc « un moyen d'y accéder », billet quand il
#: tourne encore, captation sinon.
FAMILLES_ATTENDUES: dict[str, tuple[tuple[str, ...], ...]] = {
    "film": (("fiche",), ("visionnage",)),
    "serie": (("fiche",), ("visionnage",)),
    "musique": (("ecoute",),),
    "album": (("ecoute",),),
    "livre": (("libraire",),),
    "bd": (("libraire",),),
    "spectacle": (("billetterie", "visionnage"),),
    "podcast": (("podcast",),),
    "chaine": (("video",),),
    # Un jeu s'obtient là où on l'achète, et cela dépend de sa forme : store
    # d'applications pour un jeu mobile (« Make More Views » porte sa fiche
    # App Store), libraire ou éditeur pour un jeu de plateau ou une chasse au
    # trésor (les Éditions du Trésor vendent les leurs à leur catalogue).
    # L'inverse n'est PAS vrai — ni une application ni un livre ne sont un
    # jeu — d'où des alternatives dans ce sens seulement.
    "jeu": (("jeu", "application", "libraire"),),
    "application": (("application",),),
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


#: Hôtes qui servent PLUSIEURS familles selon le chemin. La table `HOTES`
#: associe un hôte à une famille et une seule ; ces hôtes-là lui échappent, et
#: les y forcer produit des comptes faux dans les deux sens.
#:
#: Le fragment est cherché DANS le chemin, jamais à sa fin seule : Spotify
#: intercale parfois une locale (`/intl-fr/show/…`).
_CHEMINS: dict[str, tuple[tuple[str, str], ...]] = {
    # TMDB sert la FICHE d'une œuvre et sa page « où regarder ». Sans cette
    # distinction, un lien de visionnage TMDB comptait pour une fiche — et
    # 125 recos fraîchement pourvues restaient signalées « sans visionnage ».
    "themoviedb.org": (("/watch", "visionnage"),),
    # Spotify et Deezer diffusent de la MUSIQUE et des PODCASTS. Les ranger
    # entièrement du côté « écoute » signalait comme dépourvues de podcast
    # trente-quatre recos qui en portaient un — le lien était là, l'audit ne
    # savait pas le lire.
    "open.spotify.com": (("/show/", "podcast"), ("/episode/", "podcast")),
    "spotify.com": (("/show/", "podcast"), ("/episode/", "podcast")),
    "deezer.com": (("/show/", "podcast"), ("/episode/", "podcast")),
    # Une PLAYLIST YouTube n'est pas une vidéo parmi d'autres : c'est une
    # œuvre entière, rangée dans l'ordre. Onze séries web du corpus — Groom,
    # Pitch, Serge, Le Trône des Frogz… — se regardent là et nulle part
    # ailleurs, et étaient signalées « sans moyen de voir ».
    #
    # La distinction avec `/watch` est délibérée : une vidéo isolée peut être
    # une bande-annonce ou un extrait, une playlist ne l'est jamais.
    "youtube.com": (("/playlist", "visionnage"),),
    # `apple.com` et `linkedin.com` servent trop de choses pour qu'une famille
    # unique ne mente pas : ils restent HORS de `HOTES`, et seul le chemin
    # exact d'un produit les qualifie. Hors de ce chemin, ils n'ont aucune
    # famille — ce qui est le comportement voulu.
    "apple.com": (("/apple-fitness-plus", "application"),),
    "linkedin.com": (("/learning", "application"),),
}


def famille(url: object) -> str | None:
    """Famille d'un lien, ou None si l'hôte n'est pas répertorié.

    Comparaison en SUFFIXE : `cameronwinter.bandcamp.com` est un compte
    Bandcamp, `fr.wikipedia.org` une Wikipédia. Une égalité stricte manquait
    les deux.

    Le CHEMIN tranche quand l'hôte ne suffit pas : voir `_CHEMINS`.

    >>> famille("https://cameronwinter.bandcamp.com/album/heavy-metal")
    'ecoute'
    >>> famille("https://www.themoviedb.org/movie/1-x/watch?locale=FR")
    'visionnage'
    >>> famille("https://exemple-inconnu.fr/page") is None
    True
    """
    h = hote_de(url)
    if not h:
        return None
    chemin = str(url).split("?", 1)[0]
    for cle, regles in _CHEMINS.items():
        if h != cle and not h.endswith("." + cle):
            continue
        for fragment, fam in regles:
            # `/watch` termine le chemin, `/show/` s'y trouve au milieu : on
            # accepte les deux formes plutôt que d'imposer une position.
            if fragment in chemin or chemin.rstrip("/").endswith(fragment.rstrip("/")):
                return fam
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
    presentes = familles_presentes(liens)
    manquantes: set[str] = set()
    for t in (types or []):
        for alternatives in FAMILLES_ATTENDUES.get(t, ()):
            if not presentes.intersection(alternatives):
                # Le PREMIER de la liste nomme le manque : c'est celui qu'on
                # ira chercher en priorité.
                manquantes.add(alternatives[0])
    return manquantes
