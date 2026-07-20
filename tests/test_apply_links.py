"""Tests de tools/apply_links.py.

Aucun réseau : la vérification HTTP est injectée via un faux `verify_url`.
"""
from __future__ import annotations

import json

import pytest

import apply_links
from apply_links import (
    apply_links as run,
)
from apply_links import (
    host_avoided,
    index_recos_by_id,
    main,
    validate_link,
)
from link_check import ProbeResult

GUID = "guid-ep-1"


@pytest.fixture
def recos(tmp_path, monkeypatch):
    """Un dossier de recos temporaire, substitué à celui du dépôt."""
    d = tmp_path / "recos"
    d.mkdir()
    monkeypatch.setattr(apply_links, "recos_dir_for", lambda source_id: d)
    return d


def write_reco(d, rid: str, *, status="validated", guid=GUID, links=None):
    payload = {"id": rid, "episodeGuid": guid, "status": status,
               "title": rid, "sourceId": "un-bon-moment"}
    if links is not None:
        payload["links"] = links
    (d / f"{rid}.json").write_text(json.dumps(payload), encoding="utf-8")
    return d / f"{rid}.json"


@pytest.fixture
def alive(monkeypatch):
    """Toute URL est vivante — isole la logique d'écriture du réseau."""
    monkeypatch.setattr(apply_links, "verify_url",
                        lambda url, timeout, cache: ProbeResult("alive", "HTTP 200", "Titre"))


def link(**over):
    base = {"label": "Arte.tv", "url": "https://arte.tv/a", "kind": "streaming"}
    base.update(over)
    return base


# ---------------------------------------------------------------------------
# host_avoided
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(("host", "expected"), [
    ("amazon.fr", True),
    ("www.amazon.fr", True),
    ("AMAZON.FR", True),
    ("canalplus.com", True),
    ("notamazon.fr", False),        # pas de faux positif
    ("arte.tv", False),
])
def test_host_avoided(host, expected):
    assert host_avoided(host) is expected


# ---------------------------------------------------------------------------
# validate_link
# ---------------------------------------------------------------------------
def test_validate_link_normalise_un_lien_correct():
    got, why = validate_link(link(ethics="indie"))
    assert why == ""
    assert got == {"label": "Arte.tv", "url": "https://arte.tv/a",
                   "kind": "streaming", "ethics": "indie"}


def test_validate_link_defauts_kind_et_ethics():
    got, _ = validate_link({"label": "X", "url": "https://ex.fr/a"})
    assert got["kind"] == "info"
    assert got["ethics"] == "neutral"


def test_validate_link_force_avoid_sur_domaine_proscrit():
    # Arbitrage 2026-07-19 : on MARQUE, on ne supprime pas — sans quoi la reco
    # reste sans lien utile, ce qui est pire pour le lecteur.
    got, why = validate_link(link(url="https://www.amazon.fr/dp/X", ethics="indie"))
    assert why == ""
    assert got["ethics"] == "avoid"


@pytest.mark.parametrize(("entry", "motif"), [
    ("pas un objet", "entrée non-objet"),
    ({"label": " ", "url": "https://ex.fr"}, "label vide"),
    ({"label": "X", "url": "http://ex.fr"}, "URL non-https"),
    ({"label": "X", "url": "ftp://ex.fr"}, "URL non-https"),
    ({"label": "X", "url": "https://"}, "host vide"),
    ({"label": "X", "url": "https://ex.fr", "kind": "stream"}, "kind invalide"),
    ({"label": "X", "url": "https://ex.fr", "ethics": "bof"}, "ethics invalide"),
])
def test_validate_link_rejets(entry, motif):
    got, why = validate_link(entry)
    assert got is None
    assert motif in why


def test_validate_link_rejette_kind_hors_enum_produit_par_un_agent():
    # Les `kind` hors schéma (watch, stream, channel, showtimes) sont la preuve
    # matérielle qu'un agent n'a pas lu le brief. Ce filtre les a tous arrêtés.
    for bogus in ("watch", "stream", "channel", "showtimes"):
        got, why = validate_link(link(kind=bogus))
        assert got is None and "kind invalide" in why


def test_validate_link_url_illisible():
    got, why = validate_link({"label": "X", "url": "https://[oops"})
    assert got is None
    assert "illisible" in why or "host vide" in why


# ---------------------------------------------------------------------------
# index_recos_by_id
# ---------------------------------------------------------------------------
def test_index_recos_filtre_sur_le_guid(recos):
    write_reco(recos, "ubm-1")
    write_reco(recos, "ubm-2", guid="autre-guid")
    assert set(index_recos_by_id("un-bon-moment", GUID)) == {"ubm-1"}


# ---------------------------------------------------------------------------
# apply_links
# ---------------------------------------------------------------------------
def test_ecrit_les_liens(recos, alive):
    path = write_reco(recos, "ubm-1")
    stats = run({"ubm-1": [link()]}, "un-bon-moment", GUID)
    assert stats["written"] == 1 and stats["links"] == 1
    assert json.loads(path.read_text(encoding="utf-8"))["links"][0]["url"] == "https://arte.tv/a"


def test_dry_run_necrit_rien(recos, alive):
    path = write_reco(recos, "ubm-1")
    stats = run({"ubm-1": [link()]}, "un-bon-moment", GUID, dry_run=True)
    assert stats["written"] == 1
    assert "links" not in json.loads(path.read_text(encoding="utf-8"))


def test_reco_absente_est_comptee_manquante(recos, alive):
    stats = run({"ubm-inconnu": [link()]}, "un-bon-moment", GUID)
    assert stats["missing"] == 1


def test_reco_non_validee_est_ignoree(recos, alive):
    write_reco(recos, "ubm-1", status="draft")
    assert run({"ubm-1": [link()]}, "un-bon-moment", GUID)["not_validated"] == 1


def test_links_existants_preserves_sans_force(recos, alive):
    path = write_reco(recos, "ubm-1", links=[{"label": "Vieux", "url": "https://old.fr"}])
    stats = run({"ubm-1": [link()]}, "un-bon-moment", GUID)
    assert stats["skipped_existing"] == 1
    assert json.loads(path.read_text(encoding="utf-8"))["links"][0]["label"] == "Vieux"


def test_force_ecrase_les_links_existants(recos, alive):
    path = write_reco(recos, "ubm-1", links=[{"label": "Vieux", "url": "https://old.fr"}])
    run({"ubm-1": [link()]}, "un-bon-moment", GUID, force=True)
    assert json.loads(path.read_text(encoding="utf-8"))["links"][0]["label"] == "Arte.tv"


def test_lien_invalide_est_rejete(recos, alive):
    write_reco(recos, "ubm-1")
    stats = run({"ubm-1": [link(kind="stream")]}, "un-bon-moment", GUID)
    assert stats["rejected"] == 1 and stats["written"] == 0


def test_aucun_lien_valide_laisse_la_reco_inchangee(recos, alive):
    path = write_reco(recos, "ubm-1")
    run({"ubm-1": [link(url="http://nope.fr")]}, "un-bon-moment", GUID)
    assert "links" not in json.loads(path.read_text(encoding="utf-8"))


def test_entrees_vides_laissent_inchange(recos, alive):
    write_reco(recos, "ubm-1")
    assert run({"ubm-1": None}, "un-bon-moment", GUID)["written"] == 0


def test_url_morte_est_ecartee(recos, monkeypatch):
    monkeypatch.setattr(apply_links, "verify_url",
                        lambda u, t, c: ProbeResult("dead", "HTTP 404"))
    write_reco(recos, "ubm-1")
    stats = run({"ubm-1": [link()]}, "un-bon-moment", GUID)
    assert stats["dead"] == 1 and stats["written"] == 0


def test_url_non_verifiable_est_acceptee_et_comptee(recos, monkeypatch):
    # Un 403 anti-bot ne prouve rien : on laisse passer plutôt que de perdre
    # un lien valide, mais l'incertitude doit remonter dans les compteurs.
    monkeypatch.setattr(apply_links, "verify_url",
                        lambda u, t, c: ProbeResult("unknown", "HTTP 403 (non concluant)"))
    write_reco(recos, "ubm-1")
    stats = run({"ubm-1": [link()]}, "un-bon-moment", GUID)
    assert stats["unverified"] == 1 and stats["written"] == 1


def test_no_verify_saute_la_sonde(recos, monkeypatch):
    def boom(*a, **k):
        raise AssertionError("verify_url ne doit pas être appelé")

    monkeypatch.setattr(apply_links, "verify_url", boom)
    write_reco(recos, "ubm-1")
    assert run({"ubm-1": [link()]}, "un-bon-moment", GUID, verify=False)["written"] == 1


def test_titre_de_la_cible_est_affiche(recos, monkeypatch, capsys):
    # Affichage indispensable : un lien vivant peut pointer vers la MAUVAISE
    # œuvre (playlist réelle d'une autre émission). Seul l'œil humain tranche.
    monkeypatch.setattr(apply_links, "verify_url",
                        lambda u, t, c: ProbeResult("alive", "HTTP 200", "Tous les épisodes"))
    write_reco(recos, "ubm-1")
    run({"ubm-1": [link()]}, "un-bon-moment", GUID)
    assert "Tous les épisodes" in capsys.readouterr().out


def test_timeout_est_transmis_a_la_sonde(recos, monkeypatch):
    recu: list[float] = []
    monkeypatch.setattr(apply_links, "verify_url",
                        lambda u, t, c: recu.append(t) or ProbeResult("alive", "HTTP 200", "T"))
    write_reco(recos, "ubm-1")
    run({"ubm-1": [link()]}, "un-bon-moment", GUID, timeout=42.0)
    assert recu == [42.0]


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def _links_file(tmp_path, payload):
    p = tmp_path / "liens.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    return str(p)


def test_main_succes_renvoie_0(recos, alive, tmp_path):
    write_reco(recos, "ubm-1")
    code = main(["--links", _links_file(tmp_path, {"ubm-1": [link()]}), "--guid", GUID])
    assert code == 0


def test_main_renvoie_1_si_reco_manquante(recos, alive, tmp_path):
    code = main(["--links", _links_file(tmp_path, {"ubm-x": [link()]}), "--guid", GUID])
    assert code == 1


def test_main_renvoie_1_si_lien_rejete(recos, alive, tmp_path):
    write_reco(recos, "ubm-1")
    payload = {"ubm-1": [link(kind="stream")]}
    assert main(["--links", _links_file(tmp_path, payload), "--guid", GUID]) == 1


def test_main_renvoie_1_si_url_morte(recos, monkeypatch, tmp_path):
    monkeypatch.setattr(apply_links, "verify_url",
                        lambda u, t, c: ProbeResult("dead", "HTTP 404"))
    write_reco(recos, "ubm-1")
    assert main(["--links", _links_file(tmp_path, {"ubm-1": [link()]}), "--guid", GUID]) == 1


def test_main_no_verify_avertit(recos, tmp_path, capsys):
    write_reco(recos, "ubm-1")
    main(["--links", _links_file(tmp_path, {"ubm-1": [link()]}),
          "--guid", GUID, "--no-verify"])
    assert "DÉSACTIVÉE" in capsys.readouterr().out


def test_main_accepte_dry_run_et_source(recos, alive, tmp_path):
    write_reco(recos, "ubm-1")
    code = main(["--links", _links_file(tmp_path, {"ubm-1": [link()]}),
                 "--guid", GUID, "--dry-run", "--source", "un-bon-moment",
                 "--force", "--timeout", "3"])
    assert code == 0
