"""Tests de tools/fix_reco_anomalies.py.

Le risque de ce module n'est pas de mal corriger — la table est curée — mais
d'écrire sur une donnée qui aurait changé depuis la vérification manuelle.
C'est ce garde-fou que la moitié des tests éprouvent.
"""
from __future__ import annotations

import pytest

import fix_reco_anomalies as fra


def _doc(rid, **kw):
    d = {"id": rid, "title": "T", "status": "validated"}
    d.update(kw)
    return d


# ---------------------------------------------------------------------------
# La table elle-même
# ---------------------------------------------------------------------------
def test_chaque_correction_porte_sa_justification():
    """Sans le « pourquoi », personne ne peut rejuger la décision plus tard —
    et une table de corrections qu'on ne peut pas relire devient intouchable."""
    for rid, fix in fra.CORRECTIONS.items():
        assert fix.get("pourquoi"), rid
        assert len(fix["pourquoi"]) > 40, rid
        assert fix.get("attendu"), f"{rid} : sans `attendu`, aucun garde-fou"
        # La liste vient du MODULE : la recopier ici la ferait diverger, et
        # une correction portant une opération récente passerait pour vide.
        assert any(k in fix for k in fra.CLES_EFFET), rid


def test_aucune_correction_ne_produit_un_type_vide():
    """`types` est un `z.array(recoType).min(1)` : un tableau vide casserait
    le build Astro sur une donnée qu'on aurait nous-mêmes écrite."""
    for rid, fix in fra.CORRECTIONS.items():
        if "types" in fix:
            assert fix["types"], rid


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------
def test_corrige_le_type_dune_piece_de_theatre():
    doc = _doc("ubm-0214", types=["spectacle", "video"])
    changes = fra.transform(doc)
    assert doc["types"] == ["spectacle"]
    assert len(changes) == 1 and changes[0].field == "types"


def test_corrige_type_ET_orthographe_du_createur():
    """Trois champs d'un coup, et la garde porte sur les trois.

    Le TITRE fait partie de l'état attendu depuis le 2026-08-18 : il portait
    lui aussi « Delerme » alors que le créateur était déjà corrigé, si bien que
    la même carte affichait les deux orthographes.
    """
    doc = _doc("ubm-1349", types=["autre", "musique"],
               creator="Vincent Delerme", title="Vincent Delerme")
    fra.transform(doc)
    assert doc["types"] == ["album"]
    assert doc["creator"] == "Vincent Delerm"
    assert doc["title"] == "Vincent Delerm"


def test_remplace_les_liens_dun_homonyme():
    """Le cas fondateur : la reco pointait un chef étoilé belge au lieu du
    vulgarisateur YouTube du même nom."""
    doc = _doc("ubm-1531", types=["video"], links=[
        {"url": "https://christophepauly.com/", "label": "Site"},
        {"url": "https://www.lecoqauxchamps.be/", "label": "Restaurant"},
    ])
    fra.transform(doc)
    assert doc["types"] == ["chaine"]
    assert [link["url"] for link in doc["links"]] == [
        "https://www.youtube.com/@Christophe_Pauly"]
    assert doc["creator"] == "Christophe Pauly"
    # Le lien posé reste conforme au schéma Zod.
    assert doc["links"][0]["kind"] == "official"
    assert doc["links"][0]["ethics"] == "neutral"


# ---------------------------------------------------------------------------
# Le garde-fou — la moitié de la valeur du module
# ---------------------------------------------------------------------------
def test_nécrit_rien_si_les_types_ont_change_depuis_la_verification():
    """Quelqu'un est passé après l'audit : la correction ne vaut plus, et
    l'écraser détruirait un travail plus récent que le nôtre."""
    doc = _doc("ubm-0214", types=["livre"])
    assert fra.transform(doc) == []
    assert doc["types"] == ["livre"]


def test_est_idempotent():
    doc = _doc("ubm-2791", types=["spectacle"])
    fra.transform(doc)
    assert doc["types"] == ["serie"]
    # Deuxième passage : `attendu` ne correspond plus, donc plus rien à faire.
    assert fra.transform(doc) == []


def test_ignore_une_reco_absente_de_la_table():
    doc = _doc("ubm-9999", types=["autre"])
    assert fra.transform(doc) == []
    assert doc["types"] == ["autre"]


def test_reco_sans_id():
    assert fra.transform({"title": "T"}) == []


def test_retire_un_lien_designe(monkeypatch):
    """Retirer UN lien fautif sans réécrire toute la liste.

    Cas réel : les 5 recos de « The Office » portaient à la fois la fiche
    AlloCiné 564 (version BRITANNIQUE) et 199 (américaine). Tous les autres
    liens — IMDb, TMDB, Netflix — et les citations (« Steve Carell ») désignent
    la version américaine. Il faut donc ôter un lien, pas redéfinir les sept.
    """
    monkeypatch.setattr(fra, "CORRECTIONS", {
        "ubm-1": {
            "attendu": {"types": ["serie"]},
            "retirer_liens": ["ficheserie_gen_cserie=564"],
            "pourquoi": "cas synthétique",
        },
    })
    doc = _doc("ubm-1", types=["serie"], links=[
        {"url": "https://www.allocine.fr/series/ficheserie_gen_cserie=564.html"},
        {"url": "https://www.imdb.com/title/tt0386676/"},
    ])
    ch = fra.transform(doc)
    assert [link["url"] for link in doc["links"]] == [
        "https://www.imdb.com/title/tt0386676/"]
    assert len(ch) == 1 and ch[0].field == "links"


def test_retirer_un_lien_absent_ne_change_rien(monkeypatch):
    monkeypatch.setattr(fra, "CORRECTIONS", {
        "ubm-1": {"attendu": {"types": ["serie"]},
                  "retirer_liens": ["inexistant"], "pourquoi": "x"},
    })
    doc = _doc("ubm-1", types=["serie"],
               links=[{"url": "https://www.imdb.com/title/tt1/"}])
    assert fra.transform(doc) == []
    assert len(doc["links"]) == 1


# ---------------------------------------------------------------------------
# Retrait d'alias
#
# Un alias FAUX est plus nuisible qu'un alias manquant : c'est lui que lisent
# les outils d'appariement. Sur ubm-1547, l'alias « bref 2 » a fait attribuer à
# une reco parlant de « Bref » (2011) la fiche AlloCiné de « Bref.2 » (2025) —
# et m'a induit en erreur une seconde fois quand j'ai cru la réparer.
# ---------------------------------------------------------------------------
def test_retire_un_alias_cible(monkeypatch):
    monkeypatch.setattr(fra, "CORRECTIONS", {
        "ubm-1": {"attendu": {"types": ["serie"]},
                  "retirer_alias": ["bref 2"], "pourquoi": "cas synthétique"},
    })
    doc = _doc("ubm-1", types=["serie"], aliases=["bref 2", "bref"])
    ch = fra.transform(doc)
    assert doc["aliases"] == ["bref"]
    assert len(ch) == 1 and ch[0].field == "aliases"


def test_retrait_dalias_insensible_a_la_casse_et_aux_espaces(monkeypatch):
    """Les alias sont saisis à la main : « Bref 2 » et « bref 2  » désignent la
    même chose, et une comparaison stricte laisserait passer l'un des deux."""
    monkeypatch.setattr(fra, "CORRECTIONS", {
        "ubm-1": {"attendu": {"types": ["serie"]},
                  "retirer_alias": ["bref 2"], "pourquoi": "cas synthétique"},
    })
    doc = _doc("ubm-1", types=["serie"], aliases=["  Bref 2 ", "autre"])
    fra.transform(doc)
    assert doc["aliases"] == ["autre"]


def test_retirer_un_alias_absent_ne_change_rien(monkeypatch):
    monkeypatch.setattr(fra, "CORRECTIONS", {
        "ubm-1": {"attendu": {"types": ["serie"]},
                  "retirer_alias": ["inexistant"], "pourquoi": "x"},
    })
    doc = _doc("ubm-1", types=["serie"], aliases=["bref"])
    assert fra.transform(doc) == []
    assert doc["aliases"] == ["bref"]


def test_retrait_dalias_sur_une_reco_sans_alias(monkeypatch):
    monkeypatch.setattr(fra, "CORRECTIONS", {
        "ubm-1": {"attendu": {"types": ["serie"]},
                  "retirer_alias": ["bref 2"], "pourquoi": "x"},
    })
    doc = _doc("ubm-1", types=["serie"])
    assert fra.transform(doc) == []
    assert "aliases" not in doc


def test_retrait_du_dernier_alias_supprime_la_cle(monkeypatch):
    """Un `aliases: []` n'est pas la même chose qu'une absence d'alias : le
    schéma le tolère, mais il laisserait croire à une vérification faite."""
    monkeypatch.setattr(fra, "CORRECTIONS", {
        "ubm-1": {"attendu": {"types": ["serie"]},
                  "retirer_alias": ["bref 2"], "pourquoi": "x"},
    })
    doc = _doc("ubm-1", types=["serie"], aliases=["bref 2"])
    ch = fra.transform(doc)
    assert "aliases" not in doc
    assert len(ch) == 1


def test_ne_reecrit_que_ce_qui_differe():
    """Une correction partiellement déjà appliquée ne doit toucher QUE le
    reste : réécrire à l'identique produirait un diff vide mais un fichier
    réécrit, donc du bruit dans l'historique."""
    doc = _doc("ubm-1531", types=["video"],
               creator="Christophe Pauly",          # déjà bon
               links=[{"url": "https://www.youtube.com/@Christophe_Pauly",
                       "label": "Chaîne YouTube", "kind": "official",
                       "ethics": "neutral"}])       # déjà bons
    champs = {c.field for c in fra.transform(doc)}
    assert champs == {"types"}                       # seul le type manquait


@pytest.mark.parametrize("rid", sorted(fra.CORRECTIONS))
def test_chaque_correction_sapplique_sur_son_etat_attendu(rid):
    """Chaque ligne doit être ACTIVE : une correction qui ne s'applique jamais
    est une ligne morte qui laisse croire que le problème est réglé."""
    fix = fra.CORRECTIONS[rid]
    # Les valeurs de `attendu` sont recopiées TELLES QUELLES : `list(v)` sur
    # une chaîne la découperait en caractères, et le document construit ne
    # correspondrait plus à l'état que la garde attend.
    doc = _doc(rid, **{k: (list(v) if isinstance(v, list) else v)
                       for k, v in fix["attendu"].items()})
    # On force une différence pour que la correction ait quelque chose à faire
    # — SAUF si `attendu` épingle déjà ce champ, auquel cas l'écraser ferait
    # échouer la garde et le test mesurerait le contraire de son intention.
    if "creator" in fix and "creator" not in fix["attendu"]:
        doc["creator"] = "autre chose"
    if "recommande_par" in fix and "recommendedBy" not in fix["attendu"]:
        doc["recommendedBy"] = "autre personne"
    if "liens" in fix:
        doc["links"] = [{"url": "https://exemple.invalide/", "label": "X"}]
    if "retirer_liens" in fix:
        # Le document doit CONTENIR le lien à retirer, sinon la correction
        # n'aurait rien à faire et le test ne prouverait rien.
        doc["links"] = [{"url": f"https://exemple.invalide/{frag}", "label": "X"}
                        for frag in fix["retirer_liens"]]
    assert fra.transform(doc), f"{rid} ne s'applique pas sur son état attendu"


def test_une_correction_sans_changement_de_type_ne_touche_pas_aux_types(monkeypatch):
    """Contrat de la fonction, éprouvé indépendamment de la table du jour.

    Aucune des 5 corrections curées n'est dans ce cas — le garde-fou `attendu`
    l'exclut — mais `transform` doit rester juste si on ajoute demain une ligne
    qui ne corrige QUE le créateur. Substituer la table teste le code plutôt
    que la donnée."""
    monkeypatch.setattr(fra, "CORRECTIONS", {
        "ubm-0001": {
            "attendu": {"types": ["film"]},
            "types": ["film"],                 # identique : rien à réécrire
            "creator": "Bon Nom",
            "pourquoi": "cas synthétique, pour le contrat de la fonction",
        },
    })
    doc = _doc("ubm-0001", types=["film"], creator="Mauvais Nom")
    champs = {c.field for c in fra.transform(doc)}
    assert champs == {"creator"}
    assert doc["types"] == ["film"]


def test_build_parser_dry_run_par_defaut():
    assert fra.build_parser().parse_args([]).apply is False


# ---------------------------------------------------------------------------
# Ajout de liens
#
# Distinct de `liens`, qui REDÉFINIT la liste. Beaucoup de recos musicales
# n'ont aucune plateforme d'écoute mais portent d'autres liens (site officiel,
# billetterie) : les écraser pour poser un Deezer serait un mauvais échange.
# ---------------------------------------------------------------------------
def test_ajoute_un_lien_sans_toucher_aux_existants(monkeypatch):
    monkeypatch.setattr(fra, "CORRECTIONS", {
        "ubm-1": {"attendu": {"types": ["album"]},
                  "ajouter_liens": [{"label": "Deezer", "kind": "streaming",
                                     "ethics": "neutral",
                                     "url": "https://www.deezer.com/artist/14"}],
                  "pourquoi": "cas synthétique de vérification"},
    })
    doc = _doc("ubm-1", types=["album"],
               links=[{"url": "https://exemple.fr/officiel", "label": "Site"}])
    ch = fra.transform(doc)
    assert [link["url"] for link in doc["links"]] == [
        "https://exemple.fr/officiel", "https://www.deezer.com/artist/14"]
    assert len(ch) == 1 and ch[0].field == "links"


def test_ajout_ignore_une_plateforme_DEJA_presente(monkeypatch):
    """Sans cette garde, une seconde exécution empilerait les doublons."""
    monkeypatch.setattr(fra, "CORRECTIONS", {
        "ubm-1": {"attendu": {"types": ["album"]},
                  "ajouter_liens": [{"label": "Deezer", "kind": "streaming",
                                     "ethics": "neutral",
                                     "url": "https://www.deezer.com/artist/14"}],
                  "pourquoi": "cas synthétique de vérification"},
    })
    doc = _doc("ubm-1", types=["album"],
               links=[{"url": "https://deezer.com/album/999", "label": "Deezer"}])
    assert fra.transform(doc) == []
    assert len(doc["links"]) == 1


def test_ajout_sur_une_reco_sans_aucun_lien(monkeypatch):
    monkeypatch.setattr(fra, "CORRECTIONS", {
        "ubm-1": {"attendu": {"types": ["album"]},
                  "ajouter_liens": [{"label": "Deezer", "kind": "streaming",
                                     "ethics": "neutral",
                                     "url": "https://www.deezer.com/artist/14"}],
                  "pourquoi": "cas synthétique de vérification"},
    })
    doc = _doc("ubm-1", types=["album"])
    fra.transform(doc)
    assert len(doc["links"]) == 1


def test_hote_tolere_une_url_illisible():
    assert fra._hote("https://[::1") == ""
    assert fra._hote(None) == ""
    assert fra._hote("https://WWW.Deezer.com/artist/1") == "deezer.com"


def test_corrige_un_titre_descriptif(monkeypatch):
    """Un titre qui DÉCRIT l'œuvre au lieu de la nommer la rend introuvable :
    personne ne cherche « Documentaire sur Orelsan »."""
    monkeypatch.setattr(fra, "CORRECTIONS", {
        "ubm-1": {"attendu": {"types": ["serie"]},
                  "titre": "Montre jamais ça à personne",
                  "pourquoi": "cas synthétique de vérification du titre"},
    })
    doc = _doc("ubm-1", types=["serie"], title="Documentaire sur Orelsan")
    ch = fra.transform(doc)
    assert doc["title"] == "Montre jamais ça à personne"
    assert len(ch) == 1 and ch[0].field == "title"


def test_un_titre_deja_bon_ne_declenche_rien(monkeypatch):
    monkeypatch.setattr(fra, "CORRECTIONS", {
        "ubm-1": {"attendu": {"types": ["serie"]}, "titre": "Déjà juste",
                  "pourquoi": "cas synthétique de vérification du titre"},
    })
    doc = _doc("ubm-1", types=["serie"], title="Déjà juste")
    assert fra.transform(doc) == []


# ---------------------------------------------------------------------------
# Retrait d'identifiants externes
#
# Ces champs ne s'affichent NULLE PART, et c'est ce qui les rend dangereux :
# une passe d'enrichissement peut promouvoir des mois plus tard un
# `externalIds.deezer` pose sur un photographe, en lien d'écoute vers un
# homonyme. Cas réel : ubm-1896, « Odieux Boby ».
# ---------------------------------------------------------------------------
def test_retire_un_identifiant_externe_faux(monkeypatch):
    monkeypatch.setattr(fra, "CORRECTIONS", {
        "ubm-1": {"attendu": {"types": ["artiste"]},
                  "retirer_external_ids": ["deezer"],
                  "pourquoi": "cas synthétique de retrait d'identifiant"},
    })
    doc = _doc("ubm-1", types=["artiste"],
               externalIds={"deezer": "https://www.deezer.com/artist/1",
                            "instagram": "quelquun"})
    ch = fra.transform(doc)
    assert doc["externalIds"] == {"instagram": "quelquun"}
    assert len(ch) == 1 and ch[0].field == "externalIds"


def test_le_dernier_identifiant_retire_supprime_la_cle(monkeypatch):
    """Un `externalIds: {}` laisserait croire à une vérification faite."""
    monkeypatch.setattr(fra, "CORRECTIONS", {
        "ubm-1": {"attendu": {"types": ["artiste"]},
                  "retirer_external_ids": ["deezer"],
                  "pourquoi": "cas synthétique de retrait d'identifiant"},
    })
    doc = _doc("ubm-1", types=["artiste"],
               externalIds={"deezer": "https://www.deezer.com/artist/1"})
    fra.transform(doc)
    assert "externalIds" not in doc


def test_retirer_un_identifiant_absent_ne_change_rien(monkeypatch):
    monkeypatch.setattr(fra, "CORRECTIONS", {
        "ubm-1": {"attendu": {"types": ["artiste"]},
                  "retirer_external_ids": ["spotify"],
                  "pourquoi": "cas synthétique de retrait d'identifiant"},
    })
    doc = _doc("ubm-1", types=["artiste"],
               externalIds={"deezer": "https://www.deezer.com/artist/1"})
    assert fra.transform(doc) == []
    assert doc["externalIds"] == {"deezer": "https://www.deezer.com/artist/1"}


def test_retrait_sur_une_reco_sans_externalIds(monkeypatch):
    monkeypatch.setattr(fra, "CORRECTIONS", {
        "ubm-1": {"attendu": {"types": ["artiste"]},
                  "retirer_external_ids": ["deezer"],
                  "pourquoi": "cas synthétique de retrait d'identifiant"},
    })
    doc = _doc("ubm-1", types=["artiste"])
    assert fra.transform(doc) == []


def test_un_createur_a_None_RETIRE_la_cle(monkeypatch):
    """Ecrire `null` arreterait le build : la collection `recos` declare
    `creator: z.string().optional()` SANS `nullable`. Seule l'absence de cle
    exprime valablement l'absence de createur."""
    monkeypatch.setattr(fra, 'CORRECTIONS', {
        'ubm-1': {'attendu': {'types': ['lieu']}, 'creator': None,
                  'pourquoi': 'cas synthetique de vidage du createur'},
    })
    doc = _doc('ubm-1', types=['lieu'], creator='Un Lieu')
    ch = fra.transform(doc)
    assert 'creator' not in doc
    assert len(ch) == 1 and ch[0].after is None


def test_vider_un_createur_deja_absent_ne_change_rien(monkeypatch):
    monkeypatch.setattr(fra, 'CORRECTIONS', {
        'ubm-1': {'attendu': {'types': ['lieu']}, 'creator': None,
                  'pourquoi': 'cas synthetique de vidage du createur'},
    })
    doc = _doc('ubm-1', types=['lieu'])
    assert fra.transform(doc) == []


def test_la_garde_refuse_si_une_valeur_SCALAIRE_a_change(monkeypatch):
    """Le pendant du garde-fou sur les types, pour les champs texte.

    Une premiere version triait les CARACTERES d'une chaine : « Anis Rallye »
    et « Riens Allaye » y passaient pour identiques, et la garde laissait
    ecrire sur une donnee qui avait change depuis la verification.
    """
    monkeypatch.setattr(fra, 'CORRECTIONS', {
        'ubm-1': {'attendu': {'creator': 'Graphie attendue'},
                  'creator': 'Graphie corrigee',
                  'pourquoi': 'cas synthetique de garde sur un scalaire'},
    })
    doc = _doc('ubm-1', creator='Quelquun est passe apres')
    assert fra.transform(doc) == []
    assert doc['creator'] == 'Quelquun est passe apres'


def test_la_garde_scalaire_LAISSE_passer_l_etat_attendu(monkeypatch):
    monkeypatch.setattr(fra, 'CORRECTIONS', {
        'ubm-1': {'attendu': {'creator': 'Graphie attendue'},
                  'creator': 'Graphie corrigee',
                  'pourquoi': 'cas synthetique de garde sur un scalaire'},
    })
    doc = _doc('ubm-1', creator='Graphie attendue')
    assert len(fra.transform(doc)) == 1
    assert doc['creator'] == 'Graphie corrigee'
