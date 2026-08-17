"""Tests de `tools/review_table.py` — RENDU de la page /tableau.

Ce fichier couvre `render_table_page` : colonnes triables, liens ouverts en
nouvel onglet, colonne de timecode et lecteur, filtre par épisode,
redimensionnement, propositions de types et recherches pré-remplies. La
COLLECTE est testée dans `test_review_table.py`, et l'échappement dans
`test_review_table_escaping.py`.
"""
from __future__ import annotations

import re

import review_table as rtab
from fixtures_review_table import _patch, _reco


# ===== render_table_page ===================================================
def _types_cell(out: str) -> str:
    """Cellule « Types » de la première ligne.

    La page embarque la feuille de style, qui contient les mêmes noms de
    classes (`.tbl-prop-arb`…) : chercher un marqueur dans TOUT le document
    donnerait un faux positif. On scope au fragment qui nous intéresse.
    """
    m = re.search(r'<td class="tbl-c-types">.*?</td>', out, re.DOTALL)
    return m.group(0) if m else ""



def test_render_page_has_one_row_per_active_reco(monkeypatch):
    _patch(monkeypatch, [_reco("ubm-1"), _reco("ubm-2"),
                         _reco("ubm-3", status="discarded")])
    out = rtab.render_table_page("src")
    assert out.count('<tr class="tbl-row"') == 2
    assert 'data-id="ubm-1"' in out and 'data-id="ubm-2"' in out


def test_render_page_columns_are_sortable(monkeypatch):
    _patch(monkeypatch, [_reco("ubm-1")])
    out = rtab.render_table_page("src")
    for key in ("title", "artist", "episode", "by", "types", "links",
                "comment", "check"):
        assert f'data-sort-key="{key}"' in out


def test_render_page_rows_carry_sort_keys(monkeypatch):
    _patch(monkeypatch, [_reco("ubm-1", title="Éloge", creator="Zoé",
                               recommendedBy="Bob")])
    out = rtab.render_table_page("src")
    assert 'data-k-title="eloge"' in out       # normalisé (sans accent)
    assert 'data-k-artist="zoe"' in out
    assert 'data-k-by="bob"' in out
    assert 'data-k-links="0"' in out
    assert 'data-k-check="0"' in out


def test_render_page_links_open_safely(monkeypatch):
    _patch(monkeypatch, [_reco("ubm-1", links=[
        {"url": "https://ok.example/a", "label": "Netflix", "ethics": "avoid"}])])
    out = rtab.render_table_page("src")
    assert 'href="https://ok.example/a"' in out
    assert 'target="_blank"' in out
    assert 'rel="noopener noreferrer"' in out
    # l'éthique du lien reste visible (classe portée par le <a>, pas la CSS)
    assert 'class="tbl-link tbl-link-avoid"' in out


def test_la_coche_est_la_derniere_colonne(monkeypatch):
    """Retour utilisateur 2026-08-15 : la coche se pose APRÈS avoir lu la
    ligne, sa place est donc au bout, pas en tête."""
    assert rtab._COLUMNS[-1][0] == "check"
    _patch(monkeypatch, [_reco("ubm-1")])
    out = rtab.render_table_page("src")
    entetes = re.findall(r'<th\b[^>]*data-sort-key="([^"]+)"', out)
    assert entetes[-1] == "check"
    # Et la CELLULE suit l'en-tête : une ligne dont l'ordre des <td> ne
    # correspond pas aux <th> décale silencieusement toutes les colonnes.
    ligne = re.search(r'<tr class="tbl-row".*?</tr>', out, re.DOTALL).group(0)
    cellules = re.findall(r'<td class="tbl-c-([a-z]+)"', ligne)
    assert cellules[-1] == "check"
    assert cellules == [c[0] if c[0] != "episode" else "episode"
                        for c in rtab._COLUMNS]


def test_le_filtre_liste_les_episodes_avec_leur_compte(monkeypatch):
    episodes = {
        "g1": {"guid": "g1", "title": "Ép. un", "number": 1, "date": "2020-01-01"},
        "g2": {"guid": "g2", "title": "Ép. deux", "number": 2, "date": "2020-02-01"},
    }
    _patch(monkeypatch, [_reco("ubm-1"), _reco("ubm-2"),
                         _reco("ubm-3", episodeGuid="g2")], episodes=episodes)
    out = rtab.render_table_page("src")
    assert 'id="tbl-filter-ep"' in out
    assert 'value="g1">#1 — Ép. un (2)' in out
    assert 'value="g2">#2 — Ép. deux (1)' in out
    # L'option « tout » annonce le volume total.
    assert "Tous (3 recos, 2 épisodes)" in out


def test_chaque_ligne_porte_le_guid_de_son_episode(monkeypatch):
    """Le filtre s'appuie sur `data-ep`, pas sur la clé de tri chronologique
    (`data-k-episode`), qui mélange date et timecode et ne désigne donc pas un
    épisode de façon stable."""
    _patch(monkeypatch, [_reco("ubm-1")])
    out = rtab.render_table_page("src")
    assert 'data-ep="g1"' in out


def test_le_filtre_est_hors_de_la_zone_de_defilement(monkeypatch):
    """Sinon il partirait hors de l'écran dès qu'on fait défiler les colonnes
    horizontalement — or c'est la commande qu'on utilise le plus."""
    _patch(monkeypatch, [_reco("ubm-1")])
    out = rtab.render_table_page("src")
    assert out.index('id="tbl-filter-ep"') < out.index('class="reco-table-scroll"')


EP_VIDEO = {"g1": {"guid": "g1", "title": "Ép. 1", "number": 3,
                   "date": "2021-02-14",
                   "youtubeUrl": "https://www.youtube.com/watch?v=abc12345678",
                   "youtubeDuration": 3600, "audioDuration": 3600}}


def test_la_colonne_timecode_ouvre_le_lecteur(monkeypatch):
    """Le lien vise `target="ytplayer"` : c'est ce qui charge l'encart au lieu
    de quitter la page. Même mécanisme que la page d'épisode."""
    _patch(monkeypatch, [_reco("ubm-1", timestamp="00:12:34")], episodes=EP_VIDEO)
    out = rtab.render_table_page("src")
    cellule = re.search(r'<td class="tbl-c-timecode">(.*?)</td>', out, re.DOTALL)
    assert cellule is not None
    assert 'target="ytplayer"' in cellule.group(1)
    assert "12:34" in cellule.group(1)


def test_le_lecteur_est_present_et_hors_de_la_zone_de_defilement(monkeypatch):
    """L'encart est positionné en fixe : un ancêtre défilant deviendrait son
    référentiel et il partirait sur le côté avec les colonnes."""
    _patch(monkeypatch, [_reco("ubm-1", timestamp="00:12:34")], episodes=EP_VIDEO)
    out = rtab.render_table_page("src")
    assert "data-player-wrap" in out
    assert 'name="ytplayer"' in out
    assert "data-audio-bar" in out
    assert out.index("data-player-wrap") < out.index('class="reco-table-scroll"')


def test_le_timecode_bascule_sur_laudio_sans_video(monkeypatch):
    """Épisode audio-only : le timecode doit rester cliquable et piloter le
    lecteur audio, pas disparaître."""
    episodes = {"g1": {"guid": "g1", "title": "Ép. 1",
                       "audioUrl": "https://cdn.example/ep1.mp3"}}
    _patch(monkeypatch, [_reco("ubm-1", timestamp="00:05:00")], episodes=episodes)
    out = rtab.render_table_page("src")
    cellule = re.search(r'<td class="tbl-c-timecode">(.*?)</td>', out, re.DOTALL)
    assert "tc-audio" in cellule.group(1)
    assert "data-audio-secs" in cellule.group(1)


def test_lhorodatage_nest_plus_affiche_deux_fois(monkeypatch):
    """Il vivait dans la colonne Épisode ; il a sa colonne désormais."""
    _patch(monkeypatch, [_reco("ubm-1", timestamp="00:12:34")], episodes=EP_VIDEO)
    out = rtab.render_table_page("src")
    ligne = re.search(r'<tr class="tbl-row".*?</tr>', out, re.DOTALL).group(0)
    assert ligne.count("12:34") == 1
    assert 'class="tbl-ts"' not in ligne


def test_les_recos_sans_timecode_sont_poussees_en_fin_de_tri(monkeypatch):
    """Trier par timecode sert à parcourir un épisode dans l'ordre, pas à
    remonter d'abord les 300 recos qui n'en ont pas."""
    _patch(monkeypatch, [_reco("ubm-1", timestamp="00:00:10"),
                         _reco("ubm-2", timestamp=None)], episodes=EP_VIDEO)
    out = rtab.render_table_page("src")
    cles = re.findall(r'data-id="(ubm-\d)"[^>]*?data-k-timecode="(\d+)"', out)
    par_id = dict(cles)
    assert int(par_id["ubm-1"]) == 10
    assert int(par_id["ubm-2"]) > 10**8


def test_la_table_est_enveloppee_dans_un_conteneur_de_defilement(monkeypatch):
    """La table doit rester une VRAIE table, le défilement va au conteneur.

    Quand la table portait elle-même `display:block; overflow-x:auto`, deux
    choses cassaient en silence : `table-layout` ne s'applique qu'à un
    `display:table` (les largeurs de colonnes redevenaient de simples
    suggestions), et `position:sticky` se calait sur la table elle-même, dont
    la hauteur épouse le contenu et ne défile donc jamais — l'en-tête collant
    ne collait à rien. Ce test verrouille la structure qui répare les deux.
    """
    _patch(monkeypatch, [_reco("ubm-1")])
    out = rtab.render_table_page("src")
    assert '<div class="reco-table-scroll">' in out
    i_div = out.index('class="reco-table-scroll"')
    i_table = out.index('id="reco-table"')
    assert i_div < i_table, "la table doit être DANS le conteneur"
    assert out.index("</table>") < out.index("</div>", i_table)


def test_chaque_entete_porte_une_poignee_de_redimensionnement(monkeypatch):
    """Une poignée par colonne, y compris la dernière.

    La dernière en a besoin comme les autres : le tableau défile
    horizontalement, son bord droit est donc atteignable.
    """
    _patch(monkeypatch, [_reco("ubm-1")])
    out = rtab.render_table_page("src")
    entetes = re.findall(r"<th\b[^>]*>.*?</th>", out, re.DOTALL)
    assert len(entetes) == len(rtab._COLUMNS)
    for th in entetes:
        assert 'class="tbl-resize"' in th, f"poignée manquante : {th[:80]}"
        assert 'role="separator"' in th
        assert 'tabindex="0"' in th, "la largeur doit être réglable au clavier"
        assert "aria-label=" in th


def test_la_poignee_est_soeur_du_bouton_de_tri_pas_son_enfant(monkeypatch):
    """LE piège du redimensionnement : un `mousedown` sur la poignée ne doit
    jamais atteindre le bouton de tri, sans quoi chaque glissement trierait la
    colonne en prime. Imbriquée dans le bouton, aucun `stopPropagation` ne
    pourrait le garantir — c'est la STRUCTURE qui doit l'interdire."""
    _patch(monkeypatch, [_reco("ubm-1")])
    out = rtab.render_table_page("src")
    for th in re.findall(r"<th\b[^>]*>.*?</th>", out, re.DOTALL):
        bouton = re.search(r"<button\b.*?</button>", th, re.DOTALL)
        assert bouton is not None
        assert "tbl-resize" not in bouton.group(0)
        # La poignée vient bien APRÈS le bouton fermé.
        assert th.index("tbl-resize") > th.index("</button>")


def test_tous_les_liens_de_la_ligne_ouvrent_un_nouvel_onglet(monkeypatch):
    """Les liens INTERNES aussi, pas seulement les liens externes.

    Le tableau porte un état volatil : ordre de tri, filtre, et commentaire en
    cours de frappe non encore envoyé au sidecar. Une navigation dans le même
    onglet le perd, et le retour arrière rend la page à son état initial.
    Les liens externes avaient déjà `target` ; le titre et l'épisode, non.
    """
    _patch(monkeypatch, [_reco("ubm-1", links=[
        {"url": "https://ok.example/a", "label": "Netflix", "ethics": None}])])
    out = rtab.render_table_page("src")

    # Chaque ancre de la ligne — hors barre de navigation — porte une cible.
    for cellule in ("tbl-c-title", "tbl-c-episode", "tbl-c-links"):
        debut = out.index(f'class="{cellule}"')
        fragment = out[debut:out.index("</td>", debut)]
        assert "<a " in fragment, f"aucun lien dans {cellule}"
        for ancre in fragment.split("<a ")[1:]:
            entete = ancre.split(">")[0]
            assert 'target="_blank"' in entete, f"{cellule} : cible manquante"
            assert "rel=\"noopener" in entete, f"{cellule} : rel manquant"


def test_render_page_escapes_hostile_content(monkeypatch):
    _patch(monkeypatch, [_reco("ubm-1", title='<script>alert("x")</script>',
                               creator='" onmouseover="evil()')],
           curation={"ubm-1": {"comment": "</textarea><script>boom</script>",
                               "checked": False, "updatedAt": ""}})
    out = rtab.render_table_page("src")
    assert "<script>alert" not in out
    assert "<script>boom" not in out
    assert 'onmouseover="evil()' not in out


def test_render_page_comment_and_checkbox_are_editable(monkeypatch):
    _patch(monkeypatch, [_reco("ubm-1")],
           curation={"ubm-1": {"comment": "noté", "checked": True,
                               "updatedAt": "2026-07-31T10:00:00+00:00"}})
    out = rtab.render_table_page("src")
    assert 'class="tbl-comment"' in out
    assert ">noté</textarea>" in out
    assert 'class="tbl-check"' in out and "checked" in out


def test_render_page_shows_type_proposal_with_accept_box(monkeypatch):
    _patch(monkeypatch, [_reco("ubm-1", types=["autre"])],
           proposals={"ubm-1": {"types": ["film"], "reason": "long métrage"}})
    out = rtab.render_table_page("src")
    assert 'class="tbl-accept"' in out
    assert 'data-types="film"' in out
    assert "long métrage" in out


def test_render_page_states_the_proposal_as_a_replacement(monkeypatch):
    """« Remplacer par … · retire … » — un « → Film » se lirait comme un AJOUT,
    donc l'inverse de ce que la coche fait."""
    _patch(monkeypatch, [_reco("ubm-1", types=["autre", "lieu"])],
           proposals={"ubm-1": {"types": ["lieu"]}})
    cell = _types_cell(rtab.render_table_page("src"))
    assert "Remplacer par : Lieu" in cell
    assert "· retire Autre" in cell


def test_render_page_marks_proposals_needing_arbitration(monkeypatch):
    _patch(monkeypatch, [_reco("ubm-1", types=["autre"])],
           proposals={"ubm-1": {"types": ["artiste"], "reason": "chaîne perso",
                                "confidence": "inference",
                                "arbitrage": "Artiste ou chaîne YouTube ?"}})
    cell = _types_cell(rtab.render_table_page("src"))
    assert 'class="tbl-prop tbl-prop-arb"' in cell
    assert "⚖" in cell
    # justification ET question d'arbitrage dans l'info-bulle
    assert "chaîne perso — Artiste ou chaîne YouTube ?" in cell


def test_render_page_marks_inferred_proposals(monkeypatch):
    _patch(monkeypatch, [_reco("ubm-1", types=["autre"])],
           proposals={"ubm-1": {"types": ["film"], "confidence": "inference"}})
    cell = _types_cell(rtab.render_table_page("src"))
    assert 'class="tbl-prop tbl-prop-weak"' in cell and "≈" in cell


def test_render_page_does_not_mark_certain_proposals(monkeypatch):
    _patch(monkeypatch, [_reco("ubm-1", types=["autre"])],
           proposals={"ubm-1": {"types": ["film"], "confidence": "certain"}})
    cell = _types_cell(rtab.render_table_page("src"))
    assert "tbl-prop-weak" not in cell and "tbl-prop-arb" not in cell
    assert 'class="tbl-prop"' in cell


def test_render_page_has_exactly_one_accept_box_per_proposal(monkeypatch):
    """Invariant de comptage : autant de coches que de propositions retenues.

    Le corps du tableau est le SEUL périmètre où compter : la page inline la
    feuille de style ET le JS client, qui contiennent eux aussi la chaîne
    `tbl-accept` (le listener délégué). Compter sur tout le document donne 161
    pour 160 — c'est exactement l'écart qu'on a passé du temps à traquer.
    """
    _patch(monkeypatch, [_reco("ubm-1", types=["autre"]),
                         _reco("ubm-2", types=["autre"]),
                         _reco("ubm-3", types=["film"])],
           proposals={"ubm-1": {"types": ["film"]},
                      "ubm-2": {"types": ["livre"]},
                      "ubm-3": {"types": ["film"]}})   # sans effet → écartée
    out = rtab.render_table_page("src")
    tbody = out.split("<tbody>", 1)[1].split("</tbody>", 1)[0]
    assert tbody.count("tbl-accept") == 2
    assert out.count("tbl-accept") > tbody.count("tbl-accept")  # style + JS


def test_render_page_without_proposals_has_no_accept_box(monkeypatch):
    _patch(monkeypatch, [_reco("ubm-1")])
    assert "tbl-accept" not in _types_cell(rtab.render_table_page("src"))


def test_render_page_proposal_without_reason(monkeypatch):
    _patch(monkeypatch, [_reco("ubm-1", types=["autre"])],
           proposals={"ubm-1": {"types": ["film"], "reason": ""}})
    out = rtab.render_table_page("src")
    assert 'class="tbl-accept"' in out


def test_render_page_empty_source(monkeypatch):
    _patch(monkeypatch, [])
    out = rtab.render_table_page("src")
    assert "Aucune reco active" in out
    assert "<table" not in out


def test_render_page_shows_flash_banner(monkeypatch):
    _patch(monkeypatch, [_reco("ubm-1")])
    out = rtab.render_table_page("src", flash="Enregistré.", flash_kind="success")
    assert "Enregistré." in out
    assert "flash-success" in out


def test_render_page_counts_in_subtitle(monkeypatch):
    _patch(monkeypatch, [_reco("ubm-1"), _reco("ubm-2")],
           curation={"ubm-1": {"comment": "", "checked": True, "updatedAt": ""}})
    out = rtab.render_table_page("src")
    assert "2 recos actives" in out
    assert "1 validée" in out


def test_render_page_links_back_to_the_episode(monkeypatch):
    _patch(monkeypatch, [_reco("ubm-1")])
    out = rtab.render_table_page("src")
    assert "/ep?guid=g1" in out


def _links_cell(out: str) -> str:
    """Cellule « Liens » de la première ligne (cf. `_types_cell` : la feuille
    de style embarquée porte les mêmes noms de classes)."""
    m = re.search(r'<td class="tbl-c-links">.*?</td>', out, re.DOTALL)
    return m.group(0) if m else ""


def test_render_page_search_links_are_folded_behind_a_button(monkeypatch):
    """~3500 puces sur 1200 lignes : dépliées, elles noieraient les vrais
    liens et tripleraient la surface à peindre."""
    _patch(monkeypatch, [_reco("ubm-1", types=["film"])])
    cell = _links_cell(rtab.render_table_page("src"))
    assert '<details class="tbl-search">' in cell
    assert "<summary" in cell and "🔍" in cell


def test_render_page_search_links_open_safely(monkeypatch):
    _patch(monkeypatch, [_reco("ubm-1", title="Mortel", types=["film"])])
    cell = _links_cell(rtab.render_table_page("src"))
    assert 'href="https://www.justwatch.com/fr/recherche?q=Mortel"' in cell
    assert cell.count('target="_blank" rel="noopener noreferrer"') >= 1


def test_render_page_search_links_are_visually_distinct(monkeypatch):
    """Un lien posé DÉSIGNE l'œuvre ; celui-ci désigne une recherche à faire.
    Deux classes distinctes, pour deux natures distinctes."""
    _patch(monkeypatch, [_reco("ubm-1", types=["film"], links=[
        {"url": "https://ok.example/a", "label": "Netflix"}])])
    cell = _links_cell(rtab.render_table_page("src"))
    assert 'class="tbl-link tbl-link-none"' in cell     # lien posé
    assert 'class="tbl-search-link"' in cell            # recherche à faire


def test_render_page_search_links_carry_an_explicit_tooltip(monkeypatch):
    _patch(monkeypatch, [_reco("ubm-1", title="Mortel", creator="F. Garcia",
                               types=["film"])])
    cell = _links_cell(rtab.render_table_page("src"))
    assert "Recherche « Mortel F. Garcia » sur JustWatch" in cell
    assert "pas la fiche" in cell


def test_render_page_search_links_do_not_inflate_the_links_sort_key(monkeypatch):
    """`data-k-links` compte les VRAIS liens : sinon trier « par liens » pour
    trouver ce qui manque remonterait justement ce qui manque le plus."""
    _patch(monkeypatch, [_reco("ubm-1", types=["film"], links=[
        {"url": "https://ok.example/a", "label": "Netflix"}])])
    out = rtab.render_table_page("src")
    assert 'data-k-links="1"' in out
    assert out.split("<tbody>", 1)[1].count('class="tbl-search-link"') >= 3


def test_render_page_without_anything_to_search(monkeypatch):
    """Reco sans titre ni créateur : pas de replieur vide dans la cellule."""
    _patch(monkeypatch, [_reco("ubm-1", title="", creator="", types=["film"])])
    assert "tbl-search" not in _links_cell(rtab.render_table_page("src"))


def test_render_page_escapes_search_links(monkeypatch):
    """Le titre part dans l'URL ET dans l'info-bulle : deux chemins à
    échapper."""
    _patch(monkeypatch, [_reco("ubm-1", title='"><script>boom</script>',
                               types=["film"])])
    cell = _links_cell(rtab.render_table_page("src"))
    assert "<script>boom" not in cell
    assert '"><script' not in cell
