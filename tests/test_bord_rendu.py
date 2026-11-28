"""Tests du rendu de `/bord` : `tools/bord_rendu.py` et `tools/bord_rendu_blocs.py`.

Le rendu est pur : chaque test lui donne ses données en dictionnaires (celles
de `bord_afaire`, `bord_chaine` et `bord_reseaux`), sans disque ni réseau. Le
fuseau est forcé à UTC, pour que les heures ne dépendent pas de `tzdata`.

Chaque bloc a son test d'injection (relecture du plan, R10) : une charge
`"><script>` et une adresse `javascript:` ressortent échappées ou neutres.
"""
from __future__ import annotations

import html
import re
from datetime import UTC, datetime

import pytest

import bord_rendu as br
import bord_rendu_blocs as bb

MAINTENANT = datetime(2026, 11, 29, 10, 51, tzinfo=UTC)  # un dimanche
CHARGE = '"><script>alert(1)</script>'
JS = "javascript:alert(1)"
EP = {"guid": "yt-11", "title": "Onze (Un Bon Moment, S6-E11)", "season": 6, "number": 11}


@pytest.fixture(autouse=True)
def _utc(monkeypatch):
    monkeypatch.setattr(bb, "_fuseau", lambda: UTC)


def _passage(debut="2026-11-29T10:17:00+00:00", fin="2026-11-29T10:17:41+00:00",
             lancees=(), echecs=()):
    return {"debut": debut, "fin": fin, "lancees": list(lancees), "echecs": list(echecs)}


def _etape(cle, libelle, etat="fait", heure=None, source="état de la chaîne"):
    return {"cle": cle, "libelle": libelle, "etat": etat, "heure": heure, "source": source}


def _chaine(**kw):
    chaine = {
        "episode": {"guid": "yt-11", "titre": "Onze (Un Bon Moment, S6-E11)",
                    "date": "2026-11-29"},
        "etapes": [
            _etape("detecte", "Détecté", source="fiche de l'épisode"),
            _etape("transcrit", "Transcrit", heure="2026-11-29T10:23:00+00:00",
                   source="fiche de l'épisode"),
            _etape("extrait", "Extrait", heure="2026-11-29T10:31:00+00:00"),
            _etape("finalise", "Finalisé", etat="a_venir"),
            _etape("publie", "Publié", etat="a_venir"),
        ],
        "erreurs": [],
        "etat_lu": True,
        "passages": [_passage()],
    }
    chaine.update(kw)
    return chaine


def _page(**kw):
    args = {"titre": "Un Bon Moment", "afaire": [], "chaine": _chaine(),
            "recents": [], "coches": {}, "maintenant": MAINTENANT}
    args.update(kw)
    return br.rendre_bord(**args)


def _sans_balise_active(page: str) -> None:
    """Ni balise `<script>` venue des données, ni lien `javascript:`."""
    assert "<script>alert" not in page
    assert 'href="javascript:' not in page
    assert '"><script>' not in page


# ---- La page --------------------------------------------------------------

def test_les_cinq_colonnes_dans_l_ordre_avec_l_audience_au_centre():
    colonnes = re.findall(r'<section class="bord-col" id="bord-(\w+)" data-col="\1"', _page())
    assert colonnes == ["afaire", "chaine", "audience", "reseaux", "systeme"]


def test_le_menu_des_sections_suit_le_meme_ordre():
    nav = _page().split('<nav class="bord-nav"', 1)[1].split("</nav>", 1)[0]
    assert re.findall(r'href="#bord-(\w+)"', nav) == [
        "afaire", "chaine", "audience", "reseaux", "systeme"]


def test_la_vue_est_auto_sans_script_et_le_reglage_se_pose_avant_l_affichage():
    page = _page()
    assert page.startswith('<!doctype html><html lang="fr" data-vue="auto">')
    tete = page.split("</head>", 1)[0]
    # Le script du réglage est dans <head>, avant le style : pas d'éclair de la vue auto.
    assert tete.index("localStorage") < tete.index("<style>")
    assert 'getItem("bord-vue")' in tete
    for vue in ("39", "13", "telephone"):
        assert f'"{vue}"' in tete
    assert "try{" in tete


def test_le_choix_de_la_vue_offre_les_quatre_vues_et_reste_cache_sans_script():
    page = _page()
    choix = page.split('<div class="bord-vues"', 1)[1].split("</div>", 1)[0]
    assert " hidden" in choix.split(">", 1)[0]
    assert re.findall(r'data-vue-choix="(\w+)"', choix) == list(br.VUES)
    assert br.VUES == ("auto", "39", "13", "telephone")


def test_la_page_se_recharge_toutes_les_cinq_minutes_sans_le_message():
    # Vers `/bord` nu : recharger `/bord?flash=…` réafficherait le message (1d-2).
    assert '<meta http-equiv="refresh" content="300;url=/bord">' in _page(flash="Fait.")


def test_la_page_n_envoie_pas_le_battement_de_la_relecture():
    assert "/activite" not in _page()


def test_ni_la_cle_d_audience_ni_le_jeton_github_n_entrent_dans_la_page(monkeypatch):
    monkeypatch.setenv("RECO_AUDIENCE_KEY", "fausse-cle-audience-123")
    monkeypatch.setenv("RECO_GITHUB_TOKEN", "faux-jeton-github-456")
    page = _page()
    assert "fausse-cle-audience-123" not in page
    assert "faux-jeton-github-456" not in page


def test_l_en_tete_lie_la_relecture_et_donne_la_date_du_jour():
    page = _page()
    entete = page.split('<header class="bord-entete">', 1)[1].split("</header>", 1)[0]
    assert '<a class="bord-relecture" href="/">' in entete
    assert "dimanche 29 novembre" in entete


def test_le_titre_et_le_message_flash_sont_echappes():
    page = _page(titre=CHARGE, flash=CHARGE, flash_kind="error")
    _sans_balise_active(page)
    assert 'class="flash flash-error"' in page


def test_le_style_et_le_script_de_la_page_sont_en_ligne(monkeypatch, tmp_path):
    css, js = tmp_path / "bord.css", tmp_path / "bord.js"
    css.write_text(".bord{color:red}", encoding="utf-8")
    js.write_text("window.bordPret=1;", encoding="utf-8")
    monkeypatch.setattr(br, "_CSS", css)
    monkeypatch.setattr(br, "_JS", js)
    page = _page()
    assert "<style>.bord{color:red}</style>" in page
    assert "<script>window.bordPret=1;</script></body>" in page


def test_un_style_ou_un_script_absent_ne_casse_pas_la_page(monkeypatch, tmp_path):
    monkeypatch.setattr(br, "_CSS", tmp_path / "absent.css")
    monkeypatch.setattr(br, "_JS", tmp_path / "absent.js")
    page = _page()
    assert "<style></style>" in page
    assert page.endswith("</body></html>")


# ---- L'état de la chaîne, en tête -----------------------------------------

def _etat_entete(passages, en_cours=None):
    page = _page(chaine=_chaine(passages=passages, en_cours=en_cours))
    m = re.search(r'<span class="bord-etat-chaine" data-etat="(\w+)">(.*?)</span></span>', page)
    return m.group(1), html.unescape(re.sub(r"<[^>]+>", "", m.group(2)))


def test_la_chaine_est_en_marche_apres_un_passage_recent():
    assert _etat_entete([_passage()]) == ("ok", "Chaîne en marche · passage il y a 33 min")


def test_la_chaine_est_en_retard_au_dela_de_deux_heures_et_demie():
    vieux = _passage(fin="2026-11-29T08:20:00+00:00")
    assert _etat_entete([vieux]) == ("alerte", "Chaîne en retard · passage il y a 2 h 31")


# Tour 1, F8 repris : le passage en cours se connaît par le fichier `en-cours` de tick.sh.
_FINI_IL_Y_A_2H45 = _passage(debut="2026-11-29T07:50:00+00:00", fin="2026-11-29T08:06:00+00:00")


def test_un_passage_en_cours_depuis_quarante_minutes_n_est_pas_un_retard():
    assert _etat_entete([_FINI_IL_Y_A_2H45], "2026-11-29T10:11:00+00:00") == (
        "ok", "Chaîne : passage en cours depuis 40 min")


def test_un_passage_en_cours_depuis_trois_heures_est_bloque():
    ancien = _passage(debut="2026-11-29T05:50:00+00:00", fin="2026-11-29T06:00:00+00:00")
    assert _etat_entete([ancien], "2026-11-29T07:51:00+00:00") == (
        "alerte", "Chaîne en retard · passage bloqué depuis 3 h 00")


def test_un_passage_en_cours_sans_passage_note_compte():
    assert _etat_entete([], "2026-11-29T10:41:00+00:00") == (
        "ok", "Chaîne : passage en cours depuis 10 min")
    assert _etat_entete(None, "2026-11-29T10:41:00+00:00") == (
        "ok", "Chaîne : passage en cours depuis 10 min")
    assert _etat_entete([], "2026-11-29T10:50:50+00:00") == (
        "ok", "Chaîne : passage en cours depuis 1 min")


def test_un_en_cours_plus_ancien_que_la_derniere_fin_est_ignore():
    # Fichier resté d'un passage dont la note a réussi à moitié : la fin le périme.
    assert _etat_entete([_passage()], "2026-11-29T10:00:00+00:00") == (
        "ok", "Chaîne en marche · passage il y a 33 min")


def test_un_en_cours_illisible_est_ignore():
    assert _etat_entete([_passage()], "pas une date") == (
        "ok", "Chaîne en marche · passage il y a 33 min")
    assert _etat_entete([], "pas une date") == ("inconnu", "Chaîne : aucun passage noté")


def test_les_echecs_du_dernier_passage_priment_sur_le_passage_en_cours():
    etat, texte = _etat_entete([_passage(echecs=["publier"])], "2026-11-29T10:45:00+00:00")
    assert (etat, texte) == ("alerte", "Chaîne : 1 étape en échec · passage il y a 33 min")


def test_un_passage_en_echec_se_voit_en_tete():
    etat, texte = _etat_entete([_passage(echecs=["publier", "commenter"])])
    assert etat == "alerte"
    assert texte == "Chaîne : 2 étapes en échec · passage il y a 33 min"


def test_un_passage_a_l_instant():
    assert _etat_entete([_passage(fin="2026-11-29T10:50:30+00:00")]) == (
        "ok", "Chaîne en marche · passage à l'instant")


def test_sans_journal_des_passages_l_etat_est_inconnu():
    assert _etat_entete(None) == ("inconnu", "Chaîne : état inconnu")
    assert _etat_entete([]) == ("inconnu", "Chaîne : aucun passage noté")
    assert _etat_entete([_passage(fin="pas une date")]) == ("inconnu", "Chaîne : état inconnu")


# ---- Bloc « À faire d'abord » ---------------------------------------------

def _item(bloc, texte, guid=None, inconnu=False):
    return {"bloc": bloc, "texte": texte, "guid": guid, "inconnu": inconnu}


def test_a_faire_liste_les_taches_et_lie_la_relecture():
    contenu, nb = bb.bloc_afaire([
        _item("relecture", "relire S6·E12 (14 recos)", "yt-12 &x"),
        _item("publication", "fusionner la PR de S6·E11", "yt-11"),
        _item("signalements", "signalements : inconnu", inconnu=True),
    ])
    assert nb == 2  # une ligne « inconnu » n'est pas une tâche
    assert 'data-bloc="relecture"' in contenu
    assert "relire S6·E12 (14 recos)" in contenu
    assert '<a class="bord-bouton" href="/ep?guid=yt-12%20%26x">Ouvrir la relecture</a>' in contenu
    assert contenu.count('class="bord-bouton"') == 1
    assert 'data-bloc="signalements" data-inconnu' in contenu
    assert "Signalements" in contenu and "Publication" in contenu


def test_a_faire_vide():
    contenu, nb = bb.bloc_afaire([])
    assert nb == 0
    assert "Rien à faire." in contenu


def test_a_faire_compte_s_affiche_en_tete_de_colonne_et_dans_le_menu():
    page = _page(afaire=[_item("relecture", "relire", "yt-1"), _item("publication", "pr", "yt-2")])
    tete = page.split('id="bord-afaire"', 1)[1].split("</h2>", 1)[1]
    assert tete.startswith('<span class="bord-nb">2</span>')
    assert '<a href="#bord-afaire">À faire d\'abord <span class="bord-nb">2</span></a>' in page


def test_a_faire_neutralise_l_injection():
    contenu, _ = bb.bloc_afaire([_item(CHARGE, CHARGE, JS), _item("relecture", JS, CHARGE)])
    _sans_balise_active(contenu)
    assert "/ep?guid=javascript%3Aalert%281%29" not in contenu  # guid d'un bloc sans lien
    assert "/ep?guid=%22%3E%3Cscript%3E" in contenu


def test_un_texte_trop_long_est_tronque():
    contenu, _ = bb.bloc_afaire([_item("liens", "x" * 500)])
    assert "x" * bb.LONGUEUR + "…" in contenu
    assert "x" * (bb.LONGUEUR + 1) not in contenu


# ---- Bloc « Chaîne » ------------------------------------------------------

def test_chaine_montre_l_episode_et_ses_etapes():
    contenu = bb.bloc_chaine(_chaine())
    assert "Onze" in contenu and "Un Bon Moment, S6-E11" not in contenu
    etats = re.findall(r'<li class="bord-etape" data-etat="(\w+)"', contenu)
    assert etats == ["fait", "fait", "fait", "a_venir", "a_venir"]
    assert "dim. 10 h 23" in contenu and "dim. 10 h 31" in contenu
    assert ">fait</span>" in contenu  # « Détecté » n'a jamais d'heure (R7)
    assert ">à venir</span>" in contenu
    assert 'title="source : télémétrie"' not in contenu
    assert 'title="source : fiche de l&#x27;épisode"' in contenu


def test_chaine_une_etape_inconnue_et_une_heure_illisible():
    chaine = _chaine(etapes=[_etape("extrait", "Extrait", etat="inconnu", source="inconnu"),
                             _etape("transcrit", "Transcrit", heure="hier")])
    contenu = bb.bloc_chaine(chaine)
    assert '<li class="bord-etape" data-etat="inconnu"' in contenu
    assert ">inconnu</span>" in contenu
    assert ">fait</span>" in contenu  # l'heure illisible n'est pas affichée


def test_chaine_sans_episode():
    contenu = bb.bloc_chaine(_chaine(episode=None, etapes=[]))
    assert "Aucun épisode en cours." in contenu


def test_chaine_un_episode_sans_fiche_montre_son_guid():
    chaine = _chaine(episode={"guid": "yt-abc", "titre": None, "date": None})
    assert "yt-abc" in bb.bloc_chaine(chaine)


def test_chaine_les_erreurs_signalees():
    contenu = bb.bloc_chaine(_chaine(erreurs=["transcription : délai", "extraction : 500"]))
    assert '<ul class="bord-erreurs">' in contenu
    assert "transcription : délai" in contenu and "extraction : 500" in contenu


def test_chaine_aucune_erreur_seulement_quand_l_etat_est_lu():
    assert "Erreurs en cours : aucune." in bb.bloc_chaine(_chaine())
    sans_etat = _chaine(etapes=[_etape("publie", "Publié", etat="inconnu", source="inconnu")],
                        etat_lu=False)
    assert "Erreurs en cours : inconnu." in bb.bloc_chaine(sans_etat)


def test_chaine_etat_lu_sans_episode_dit_aucune_erreur():
    # Tour 1, F3 : l'état lu et vide ne se déduit pas des étapes.
    contenu = bb.bloc_chaine(_chaine(episode=None, etapes=[]))
    assert "Erreurs en cours : aucune." in contenu


def test_chaine_les_derniers_passages():
    passages = [
        _passage(),
        _passage(debut="2026-11-29T08:17:00+00:00", fin="2026-11-29T08:20:12+00:00",
                 lancees=["extraire", "chercher-liens"], echecs=["publier"]),
        _passage(debut="pas une date"),
    ]
    contenu = bb.bloc_chaine(_chaine(passages=passages))
    lignes = re.findall(r'<li data-echec="(\d)"><span>(.*?)</span><span class="bord-mut">'
                        r'(.*?)</span></li>', contenu)
    assert lignes == [
        ("0", "10 h 17 · rien de neuf", "41 s"),
        ("1", "08 h 17 · lancé : extraire, chercher-liens · en échec : publier", "3 min 12"),
        ("0", "? · rien de neuf", "?"),
    ]


def test_chaine_sans_journal_des_passages():
    assert "Derniers passages : inconnu." in bb.bloc_chaine(_chaine(passages=None))
    assert "Aucun passage noté." in bb.bloc_chaine(_chaine(passages=[]))


def test_chaine_neutralise_l_injection():
    chaine = _chaine(
        episode={"guid": CHARGE, "titre": CHARGE, "date": JS},
        etapes=[_etape(CHARGE, CHARGE, etat=CHARGE, heure=CHARGE, source=CHARGE)],
        erreurs=[CHARGE, JS],
        passages=[_passage(lancees=[CHARGE], echecs=[JS]), {"lancees": CHARGE, "echecs": 3}],
    )
    contenu = bb.bloc_chaine(chaine)
    _sans_balise_active(contenu)
    assert 'data-etat="inconnu"' in contenu  # un état hors de la liste n'entre pas en attribut


# ---- Bloc « Réseaux » -----------------------------------------------------

def _recent(guid="yt-11", episode=EP, fusionne=False):
    return {"guid": guid, "fusionne": fusionne, "episode": episode}


def test_reseaux_une_ligne_par_reseau_une_colonne_par_episode():
    contenu, nb = bb.bloc_reseaux([_recent(), _recent("yt-10", None)], {})
    lignes = re.findall(r'<th scope="row">(.*?)</th>', contenu)
    assert lignes == ["Instagram", "Threads", "Spotify", "Deezer", "SensCritique",
                      "commentaire YouTube"]
    assert re.findall(r'<th scope="col">(.*?)</th>', contenu) == ["Réseau", "S6·E11", "yt-10"]
    assert nb == 12


def test_reseaux_une_case_a_cocher_est_un_formulaire_post():
    contenu, _ = bb.bloc_reseaux([_recent()], {})
    forme = contenu.split('<form method="post" action="/bord/reseau" class="bord-case-form">', 1)[1]
    forme = forme.split("</form>", 1)[0]
    assert '<input type="hidden" name="guid" value="yt-11">' in forme
    assert '<input type="hidden" name="reseau" value="instagram">' in forme
    assert '<input type="hidden" name="fait" value="1">' in forme
    assert ('<button type="submit" class="bord-case" data-fait="0" '
            'aria-label="Instagram, S6·E11 : marquer comme fait" '
            'data-nom="Instagram, S6·E11">À faire</button>') in forme


def test_reseaux_un_long_titre_garde_l_action_dans_le_libelle():
    # Tour 1, F5 : on coupe le nom, jamais l'action lue par le lecteur d'écran.
    titre = "Un titre : très long, avec un deux-points " + "x" * 200
    ep = {"guid": "yt-11", "title": titre}
    contenu, _ = bb.bloc_reseaux([_recent(episode=ep)], {})
    cellule = contenu.split('name="reseau" value="instagram">', 1)[1].split("</form>", 1)[0]
    nom = re.search(r'data-nom="(.*?)"', cellule).group(1)
    assert len(nom) <= 60 + len("…") and nom.startswith("Instagram, ")
    assert f'aria-label="{nom} : marquer comme fait"' in cellule


def test_reseaux_une_case_cochee_se_decoche():
    coches = {"yt-11": {"deezer": "2026-11-28T09:30:00+00:00"}}
    contenu, nb = bb.bloc_reseaux([_recent()], coches)
    assert nb == 5
    cellule = contenu.split('name="reseau" value="deezer">', 1)[1].split("</form>", 1)[0]
    assert '<input type="hidden" name="fait" value="0">' in cellule
    assert 'data-fait="1"' in cellule
    assert 'aria-label="Deezer, S6·E11 : décocher"' in cellule
    assert 'data-nom="Deezer, S6·E11"' in cellule
    assert 'title="coché le 28/11"' in cellule
    assert ">✓</button>" in cellule


def test_reseaux_une_date_de_coche_illisible_garde_la_case_cochee():
    contenu, _ = bb.bloc_reseaux([_recent()], {"yt-11": {"spotify": "hier"}})
    cellule = contenu.split('name="reseau" value="spotify">', 1)[1].split("</form>", 1)[0]
    assert 'data-fait="1"' in cellule and "title=" not in cellule


def test_reseaux_fichier_illisible_refuse_les_cases():
    contenu, nb = bb.bloc_reseaux([_recent()], None)
    assert nb is None
    assert 'role="alert"' in contenu and "illisible" in contenu
    assert "<form" not in contenu
    assert contenu.count(">inconnu</td>") == 6


def test_reseaux_sans_etat_ou_sans_episode():
    contenu, nb = bb.bloc_reseaux(None, {})
    assert nb is None and "Épisodes publiés : inconnu." in contenu
    contenu, nb = bb.bloc_reseaux([], {})
    assert nb == 0 and "Aucun épisode publié." in contenu


def test_reseaux_neutralise_l_injection():
    episode = {"title": CHARGE}
    contenu, _ = bb.bloc_reseaux([_recent(CHARGE, episode), _recent(JS, None)],
                                 {CHARGE: {"instagram": CHARGE}})
    _sans_balise_active(contenu)
    assert 'value="&quot;&gt;&lt;script&gt;alert(1)&lt;/script&gt;"' in contenu


def test_reseaux_compte_en_tete_de_colonne():
    page = _page(recents=[_recent()], coches={})
    tete = page.split('id="bord-reseaux"', 1)[1].split("</h2>", 1)[1]
    assert tete.startswith('<span class="bord-nb">6</span>')


# ---- Les places en attente ------------------------------------------------

def _colonne(page, cle):
    return page.split(f'id="bord-{cle}"', 1)[1].split("</section>", 1)[0]


def test_le_systeme_et_les_sorties_ont_leur_place_en_attente():
    page = _page()
    systeme = _colonne(page, "systeme")
    assert "data-attente" in systeme and "Liens morts" in systeme
    reseaux = _colonne(page, "reseaux")
    assert "Sorties à venir" in reseaux and "Signalements" in reseaux


def test_l_audience_remplit_le_centre_et_sans_elle_dit_inconnu():
    audience = _colonne(_page(audience={"etat": "cle-absente", "donnees": None}), "audience")
    assert "data-attente" not in audience
    assert 'data-etat="cle-absente"' in audience and "Clé absente" in audience
    assert 'data-etat="inconnu"' in _colonne(_page(), "audience")


def test_les_signalements_vont_dans_la_colonne_des_reseaux():
    # Le détail du bloc : `test_bord_rendu_audience.py`.
    sig = {"etat": "lu", "enAttente": [{"id": "rep-0", "recoId": "ubm-0",
                                        "categorie": "error", "date": "2026-11-27"}]}
    reseaux = _colonne(_page(audience={"etat": "ok", "donnees": {"signalements": sig}}),
                       "reseaux")
    assert "ubm-0" in reseaux and "Signalements" in reseaux


def test_bloc_attente_echappe_son_titre():
    _sans_balise_active(bb.bloc_attente(CHARGE))


# ---- Le fuseau ------------------------------------------------------------

def test_le_fuseau_de_paris_sinon_utc(monkeypatch):
    monkeypatch.undo()  # retire le fuseau forcé par la fixture

    def absent(nom):
        raise bb.ZoneInfoNotFoundError(nom)

    monkeypatch.setattr(bb, "ZoneInfo", absent)
    assert bb._fuseau() is UTC
    monkeypatch.setattr(bb, "ZoneInfo", lambda nom: f"fuseau {nom}")
    assert bb._fuseau() == "fuseau Europe/Paris"


def test_une_heure_sans_fuseau_est_en_utc():
    assert bb._heure("2026-11-29 10:23:00", jour=True) == "dim. 10 h 23"
