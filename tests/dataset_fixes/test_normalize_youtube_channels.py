"""Tests de tools/normalize_youtube_channels.py.

AUCUN accès réseau : `transform_factory` reçoit un résolveur injecté, et les
tests lui fournissent une table en mémoire. Le seul contact avec du HTML réel
se fait sur des extraits figés, capturés le 2026-08-15.
"""
from __future__ import annotations

import json

import pytest

import normalize_youtube_channels as nyc

FOULO_ID = "UCLXDNUOO3EQ80VmD9nQBHPg"
FOULO_AT = "https://www.youtube.com/@Fouloscopie"
FOULO_CH = f"https://www.youtube.com/channel/{FOULO_ID}"
AUTRE_ID = "UCghR6gNuBneEKkDuKtXQM4w"


# ---------------------------------------------------------------------------
# channel_key — reconnaître (et surtout NE PAS reconnaître) une URL de chaîne
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(("url", "attendu"), [
    (FOULO_AT, ("handle", "@Fouloscopie")),
    ("https://youtube.com/@Fouloscopie", ("handle", "@Fouloscopie")),
    (FOULO_CH, ("channel", FOULO_ID)),
    ("https://www.youtube.com/c/verinaze", ("legacy", "verinaze")),
    ("https://www.youtube.com/user/PewDiePie", ("legacy", "PewDiePie")),
    ("https://www.youtube.com/@Fouloscopie/videos", ("handle", "@Fouloscopie")),
    ("  https://www.youtube.com/@Fouloscopie  ", ("handle", "@Fouloscopie")),
    # `m.` = version MOBILE du même site, donc la même chaîne. Oubliée au
    # premier jet : un lien du corpus (ubm-1740) y a échappé.
    ("https://m.youtube.com/user/tiradodaniel", ("legacy", "tiradodaniel")),
    ("https://m.youtube.com/@Fouloscopie", ("handle", "@Fouloscopie")),
    ("https://m.youtube.com/channel/" + FOULO_ID, ("channel", FOULO_ID)),
])
def test_channel_key_reconnait(url, attendu):
    assert nyc.channel_key(url) == attendu


@pytest.mark.parametrize("url", [
    "https://music.youtube.com/channel/UCylVomQnFRQl_gOlXFNPf8g",
    "https://music.youtube.com/@disizfr",
])
def test_channel_key_laisse_youtube_music_tranquille(url):
    """YouTube Music est un service DISTINCT : ses liens mènent à une page
    d'écoute, pas à une chaîne vidéo. Les convertir changerait la destination.

    Deux cas réels du corpus : « Dissiz » y porte le MÊME identifiant que sa
    chaîne vidéo, « Willylancien » un identifiant DIFFÉRENT (chaîne générée
    par YouTube Music). Ni l'un ni l'autre n'est un doublon à fusionner.

    Piège de regex au passage : l'alternative `m\\.` du motif d'hôte ne doit
    pas capturer le « m » de « music ».
    """
    assert nyc.channel_key(url) is None


@pytest.mark.parametrize("url", [
    "https://www.youtube.com/watch?v=dQw4w9WgXcQ",   # une VIDÉO, pas une chaîne
    "https://www.youtube.com/playlist?list=PL123",
    "https://www.deezer.com/@Fouloscopie",           # bon chemin, mauvais hôte
    "https://example.com/channel/UCabc",
    "",
])
def test_channel_key_ignore_ce_qui_nest_pas_une_chaine(url):
    """Une URL de vidéo ne doit JAMAIS être réécrite en URL de chaîne : elle
    désigne une œuvre précise, pas son auteur."""
    assert nyc.channel_key(url) is None


def test_handle_url():
    assert nyc.handle_url("@Fouloscopie") == FOULO_AT


# ---------------------------------------------------------------------------
# parse_channel_page — le 200 ne prouve rien
# ---------------------------------------------------------------------------
def _page(*, handle=None, chan=None, titre=None) -> str:
    out = []
    if titre:
        out.append(f'<meta property="og:title" content="{titre}">')
    if chan:
        out.append('<link rel="canonical" '
                   f'href="https://www.youtube.com/channel/{chan}">')
    if handle:
        out.append('{"canonicalBaseUrl":"/' + handle + '"}')
    return "<html>" + "".join(out) + "</html>"


def test_parse_page_complete():
    res = nyc.parse_channel_page(
        _page(handle="@Fouloscopie", chan=FOULO_ID, titre="Fouloscopie"))
    assert res["handle"] == "@Fouloscopie"
    assert res["channelId"] == FOULO_ID
    assert res["title"] == "Fouloscopie"
    assert res["reason"] == nyc.REASON_OK


def test_parse_page_dune_chaine_inexistante():
    """YouTube répond 200 avec une page vide de marqueurs. C'est le TITRE qui
    prouve l'existence, jamais le code HTTP."""
    res = nyc.parse_channel_page("<html>rien du tout</html>")
    assert res["reason"] == nyc.REASON_UNKNOWN
    assert res["handle"] is None and res["channelId"] is None


def test_parse_page_chaine_reelle_sans_pseudo():
    res = nyc.parse_channel_page(_page(chan=FOULO_ID, titre="Vieille chaîne"))
    assert res["reason"] == nyc.REASON_NO_HANDLE
    assert res["channelId"] == FOULO_ID
    assert res["handle"] is None


# ---------------------------------------------------------------------------
# resolve — cache et pannes
# ---------------------------------------------------------------------------
class _Session:
    """Session HTTP factice. Compte les appels pour prouver l'effet du cache."""

    def __init__(self, corps="", exc=None):
        self.corps, self.exc, self.appels = corps, exc, 0

    def get(self, url, timeout=None):
        self.appels += 1
        if self.exc:
            raise self.exc
        return type("R", (), {"text": self.corps})()


def test_resolve_met_en_cache_et_ninterroge_quune_fois():
    s = _Session(_page(handle="@Fouloscopie", chan=FOULO_ID, titre="Fouloscopie"))
    cache: dict = {}
    a = nyc.resolve(FOULO_CH, cache, s, pause=0)
    b = nyc.resolve(FOULO_CH, cache, s, pause=0)
    assert a["handle"] == b["handle"] == "@Fouloscopie"
    assert s.appels == 1, "la seconde résolution doit venir du cache"


def test_resolve_ne_met_PAS_en_cache_une_panne_reseau():
    """Une panne est transitoire : la mettre en cache condamnerait la chaîne
    pour toutes les relances suivantes."""
    s = _Session(exc=OSError("connexion perdue"))
    cache: dict = {}
    res = nyc.resolve(FOULO_CH, cache, s, pause=0)
    assert res["reason"] == nyc.REASON_HTTP
    assert cache == {}


# ---------------------------------------------------------------------------
# transform — le cœur
# ---------------------------------------------------------------------------
def _resolveur(table: dict):
    def r(url: str):
        return nyc.Resolution(table.get(url) or {
            "handle": None, "channelId": None, "title": None,
            "reason": nyc.REASON_UNKNOWN})
    return r


TABLE = {
    FOULO_CH: {"handle": "@Fouloscopie", "channelId": FOULO_ID,
               "title": "Fouloscopie", "reason": nyc.REASON_OK},
    FOULO_AT: {"handle": "@Fouloscopie", "channelId": FOULO_ID,
               "title": "Fouloscopie", "reason": nyc.REASON_OK},
}


def _doc(urls, **kw):
    d = {"id": "ubm-1", "title": "T",
         "links": [{"url": u, "label": "YouTube", "kind": "official",
                    "ethics": "neutral"} for u in urls]}
    d.update(kw)
    return d


def test_convertit_une_url_channel_en_pseudo():
    rapport: dict = {}
    doc = _doc([FOULO_CH])
    changes = nyc.transform_factory(_resolveur(TABLE), rapport)(doc)
    assert doc["links"][0]["url"] == FOULO_AT
    assert doc["externalIds"]["youtubeChannelId"] == FOULO_ID
    assert len(changes) == 2          # l'URL, puis l'identifiant conservé


def test_supprime_le_doublon_quand_les_deux_formes_coexistent():
    """Le cas décrit par l'utilisateur : Fouloscopie listée deux fois."""
    rapport: dict = {}
    doc = _doc([FOULO_CH, FOULO_AT])
    nyc.transform_factory(_resolveur(TABLE), rapport)(doc)
    assert [link["url"] for link in doc["links"]] == [FOULO_AT]
    assert doc["externalIds"]["youtubeChannelId"] == FOULO_ID


def test_le_premier_lien_survit_et_garde_ses_metadonnees():
    """Fusionner ne doit pas perdre le libellé ni l'éthique du lien gardé."""
    rapport: dict = {}
    doc = {"id": "ubm-1", "links": [
        {"url": FOULO_CH, "label": "Chaîne YouTube", "kind": "official",
         "ethics": "indie"},
        {"url": FOULO_AT, "label": "YouTube", "kind": "info", "ethics": "neutral"},
    ]}
    nyc.transform_factory(_resolveur(TABLE), rapport)(doc)
    assert len(doc["links"]) == 1
    assert doc["links"][0]["label"] == "Chaîne YouTube"
    assert doc["links"][0]["ethics"] == "indie"


def test_ne_fusionne_PAS_deux_chaines_differentes():
    """Chaîne principale + chaîne secondaire : ce ne sont pas des doublons.
    Les confondre supprimerait un vrai lien."""
    autre = "https://www.youtube.com/channel/" + AUTRE_ID
    table = dict(TABLE)
    table[autre] = {"handle": "@Chuntzit", "channelId": AUTRE_ID,
                    "title": "Chris Fleming", "reason": nyc.REASON_OK}
    rapport: dict = {}
    doc = _doc([FOULO_CH, autre])
    changes = nyc.transform_factory(_resolveur(table), rapport)(doc)
    assert changes == []
    assert [link["url"] for link in doc["links"]] == [FOULO_CH, autre]
    assert rapport["conflits"][0]["channelIds"] == sorted([AUTRE_ID, FOULO_ID])


def test_laisse_intact_un_lien_non_resolu():
    """Chaîne supprimée, sans pseudo, ou réseau en panne : on n'invente rien."""
    rapport: dict = {}
    doc = _doc(["https://www.youtube.com/channel/UCinconnuinconnuinconnu"])
    assert nyc.transform_factory(_resolveur({}), rapport)(doc) == []
    assert doc["links"][0]["url"].endswith("UCinconnuinconnuinconnu")
    assert "externalIds" not in doc


def test_ne_touche_pas_aux_liens_qui_ne_sont_pas_des_chaines():
    rapport: dict = {}
    video = "https://www.youtube.com/watch?v=abc"
    doc = _doc([video, "https://deezer.com/album/1", FOULO_CH])
    nyc.transform_factory(_resolveur(TABLE), rapport)(doc)
    assert [link["url"] for link in doc["links"]] == [
        video, "https://deezer.com/album/1", FOULO_AT]


def test_une_reco_sans_lien_de_chaine_nest_pas_touchee():
    rapport: dict = {}
    doc = _doc(["https://deezer.com/album/1"])
    assert nyc.transform_factory(_resolveur(TABLE), rapport)(doc) == []
    assert "externalIds" not in doc


def test_est_idempotent():
    """Deuxième passage : plus rien à changer. Sans quoi chaque exécution
    produirait un diff et polluerait l'historique."""
    rapport: dict = {}
    t = nyc.transform_factory(_resolveur(TABLE), rapport)
    doc = _doc([FOULO_CH, FOULO_AT])
    t(doc)
    assert t(doc) == []


def test_nécrase_pas_un_identifiant_deja_correct():
    rapport: dict = {}
    doc = _doc([FOULO_AT], externalIds={"youtubeChannelId": FOULO_ID})
    assert nyc.transform_factory(_resolveur(TABLE), rapport)(doc) == []


def test_ignore_un_identifiant_de_chaine_malforme():
    """Le schéma Zod exige `^UC[\\w-]{22}$` : on n'y écrit rien d'autre, sous
    peine de casser le build sur une donnée qu'on aurait nous-mêmes posée."""
    table = {FOULO_AT: {"handle": "@X", "channelId": "pas-un-uc",
                        "title": "X", "reason": nyc.REASON_OK}}
    rapport: dict = {}
    doc = _doc([FOULO_AT])
    nyc.transform_factory(_resolveur(table), rapport)(doc)
    assert "externalIds" not in doc


def test_ignore_une_entree_de_links_qui_nest_pas_un_objet():
    rapport: dict = {}
    doc = {"id": "ubm-1", "links": ["pas un objet", {"url": FOULO_CH}]}
    nyc.transform_factory(_resolveur(TABLE), rapport)(doc)
    assert doc["links"][-1]["url"] == FOULO_AT


def test_reco_sans_champ_links():
    rapport: dict = {}
    doc = {"id": "ubm-1", "title": "T"}
    assert nyc.transform_factory(_resolveur(TABLE), rapport)(doc) == []


# ---------------------------------------------------------------------------
# Cache sur disque
# ---------------------------------------------------------------------------
def test_cache_aller_retour(tmp_path, monkeypatch):
    monkeypatch.setattr(nyc, "CACHE_PATH", tmp_path / "cache.json")
    nyc._save_cache({FOULO_CH: {"handle": "@Fouloscopie"}})
    assert nyc._load_cache()[FOULO_CH]["handle"] == "@Fouloscopie"


def test_cache_absent_ou_illisible(tmp_path, monkeypatch):
    monkeypatch.setattr(nyc, "CACHE_PATH", tmp_path / "rien.json")
    assert nyc._load_cache() == {}
    (tmp_path / "casse.json").write_text("{pas du json", encoding="utf-8")
    monkeypatch.setattr(nyc, "CACHE_PATH", tmp_path / "casse.json")
    assert nyc._load_cache() == {}


def test_le_motif_uc_est_le_meme_que_celui_du_schema_zod():
    """Les deux doivent rester d'accord : le script écrit ce que Zod valide."""
    from pathlib import Path
    racine = Path(__file__).resolve().parents[2]
    zod = (racine / "src" / "content.config.ts").read_text(encoding="utf-8")
    assert "youtubeChannelId: z.string().regex(/^UC[\\w-]{22}$/)" in zod
    assert nyc._RE_UC.pattern == r"^UC[\w-]{22}$"


def test_build_parser_expose_les_options_communes():
    args = nyc.build_parser().parse_args([])
    assert args.apply is False        # dry-run par défaut
    assert args.pause == 0.3
    assert json.dumps(vars(args))     # sérialisable : sert au rapport
