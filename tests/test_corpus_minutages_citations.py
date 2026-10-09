"""Invariant : chaque reco publiée a une citation et un minutage qui pointe dans l'épisode.

POURQUOI CE FICHIER EXISTE
--------------------------
Le 2026-10-07, une mesure sur les 1 259 recos publiées a trouvé, à la main :

- 3 minutages au-delà de la fin de l'épisode (« 11:12:00 » pour un épisode de
  1 h 23 : des mm:ss enregistrés en hh:mm:00 dès l'extraction) ;
- 4 minutages à 00:00:00, qui ouvrent l'épisode à son début ;
- 10 minutages écrits mm:ss, que le site lit bien mais que la page de
  validation et les outils lisent de travers ;
- 3 recos publiées sans citation ;
- 11 mentions en désaccord avec leur reco (minutage ou citation) : la fiche de
  l'œuvre affichait autre chose que la carte de la reco.

Tout a été corrigé. Ce fichier n'est pas un correcteur : c'est une GARDE, qui
fait échouer la CI au lieu de laisser le défaut attendre qu'un visiteur le voie.
Elle ne demande pas les transcriptions (absentes de la CI) : qu'un minutage
pointe sur la bonne phrase se vérifie ailleurs, par `caler_citations.py`.
"""
from __future__ import annotations

import json
import re

import pytest

from common import CONTENT_DIR

_HHMMSS = re.compile(r"\d{2}:\d{2}:\d{2}")


def _lire(dossier: str) -> list[dict]:
    out = []
    for chemin in sorted((CONTENT_DIR / dossier).rglob("*.json")):
        # Les dossiers `__…__` sont des fixtures scellées, exclues du site.
        if any(part.startswith("__") for part in chemin.relative_to(CONTENT_DIR).parts):
            continue
        out.append(json.loads(chemin.read_text(encoding="utf-8")))
    return out


def _secondes(minutage: str) -> int:
    h, m, s = (int(x) for x in minutage.split(":"))
    return h * 3600 + m * 60 + s


@pytest.fixture(scope="module")
def recos() -> list[dict]:
    docs = [r for r in _lire("recos") if r.get("status") == "validated"]
    # Sans cette garde, tous les tests ci-dessous passeraient sur zéro reco.
    assert len(docs) > 500, "corpus introuvable ou vide"
    return docs


@pytest.fixture(scope="module")
def mentions() -> dict[str, dict]:
    return {m["id"]: m for m in _lire("mentions") if m.get("status") == "validated"}


@pytest.fixture(scope="module")
def durees() -> dict[str, int]:
    """Durée de chaque épisode : la plus longue connue (YouTube ou Acast)."""
    out = {}
    for e in _lire("episodes"):
        connues = [d for d in (e.get("youtubeDuration"), e.get("audioDuration")) if d]
        if connues:
            out[e["guid"]] = max(connues)
    return out


def _minutages(recos: list[dict], mentions: dict[str, dict]) -> list[tuple[str, str, str]]:
    """(id, guid, minutage) de chaque reco publiée et de chaque mention publiée."""
    out = [(r["id"], r.get("episodeGuid", ""), r.get("timestamp") or "") for r in recos]
    for m in mentions.values():
        ref = m.get("sourceRef") or {}
        out.append((m["id"] + " (mention)", ref.get("episodeGuid", ""), ref.get("timestamp") or ""))
    return out


def test_un_minutage_s_ecrit_hh_mm_ss(recos, mentions):
    fautifs = [f"{i} « {t} »" for i, _g, t in _minutages(recos, mentions) if not _HHMMSS.fullmatch(t)]
    assert not fautifs, f"minutages hors format hh:mm:ss : {fautifs}"


def test_un_minutage_ne_vaut_pas_zero(recos, mentions):
    fautifs = [i for i, _g, t in _minutages(recos, mentions) if t == "00:00:00"]
    assert not fautifs, f"minutages à 00:00:00 (le début de l'épisode, pas la citation) : {fautifs}"


def test_un_minutage_tombe_dans_l_episode(recos, mentions, durees):
    fautifs = [f"{i} {t} > {durees[g]} s"
               for i, g, t in _minutages(recos, mentions)
               if _HHMMSS.fullmatch(t) and g in durees and _secondes(t) > durees[g]]
    assert not fautifs, f"minutages au-delà de la fin de l'épisode : {fautifs}"


def test_une_reco_publiee_a_une_citation(recos):
    fautifs = [r["id"] for r in recos if not (r.get("quote") or "").strip()]
    assert not fautifs, f"recos publiées sans citation : {fautifs}"


def test_une_mention_dit_la_meme_chose_que_sa_reco(recos, mentions):
    fautifs = []
    for r in recos:
        m = mentions.get(r["id"])
        if m is None:
            continue
        ref = m.get("sourceRef") or {}
        if ref.get("timestamp") != r.get("timestamp"):
            fautifs.append(f"{r['id']} minutage {r.get('timestamp')} ≠ {ref.get('timestamp')}")
        if (m.get("quote") or "") != (r.get("quote") or ""):
            fautifs.append(f"{r['id']} citation")
    assert not fautifs, f"mentions en désaccord avec leur reco : {fautifs}"


def test_la_garde_voit_les_defauts_qu_elle_doit_refuser():
    """Contre-épreuve : la garde n'est pas aveugle aux défauts mesurés le 2026-10-07."""
    assert not _HHMMSS.fullmatch("25:06")
    assert _secondes("11:12:00") > 5018  # l'épisode #10 dure 1 h 23
