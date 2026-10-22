"""Tests de tools/vignettes_episodes.py — les vignettes servies par le site.

Les noms doivent rester ceux de `src/utils/vignettes.ts` : la valeur de
l'empreinte Acast est fixee des deux cotes.
"""
from __future__ import annotations

from pathlib import Path

import pytest

import vignettes_episodes as ve

ACAST = "https://open-images.acast.com/shows/x/y.png?width=640&height=360"
YT = {"guid": "g1", "youtubeUrl": "https://www.youtube.com/watch?v=dpM43BlLhZI"}


def test_noms_youtube_et_acast_identiques_au_site() -> None:
    assert ve.vignettes(YT) == {
        "yt-dpM43BlLhZI-mq.jpg": "https://i.ytimg.com/vi/dpM43BlLhZI/mqdefault.jpg",
        "yt-dpM43BlLhZI-hq.jpg": "https://i.ytimg.com/vi/dpM43BlLhZI/hqdefault.jpg",
    }
    # Valeur fixee aussi dans tests/utils/test_vignettes.test.ts.
    assert ve.vignettes({"imageUrl": ACAST}) == {"ep-f7b805aabc0c.png": ACAST}


def test_extension_inconnue_et_episode_sans_image() -> None:
    (nom,) = ve.vignettes({"imageUrl": "https://exemple.test/image"})
    assert nom.endswith(".jpg")
    assert ve.vignettes({"youtubeUrl": "https://youtu.be/abc"}) == {}


def test_recuperer_ecrit_les_absentes_seulement(tmp_path: Path) -> None:
    (tmp_path / "yt-dpM43BlLhZI-mq.jpg").write_bytes(b"deja")
    appels: list[str] = []

    def telecharger(url: str) -> bytes:
        appels.append(url)
        return b"image"

    ecrits = ve.recuperer(YT, dossier=tmp_path, telecharger=telecharger)

    assert [p.name for p in ecrits] == ["yt-dpM43BlLhZI-hq.jpg"]
    assert appels == ["https://i.ytimg.com/vi/dpM43BlLhZI/hqdefault.jpg"]
    assert (tmp_path / "yt-dpM43BlLhZI-mq.jpg").read_bytes() == b"deja"
    assert sorted(p.name for p in ve.fichiers(YT, dossier=tmp_path)) == [
        "yt-dpM43BlLhZI-hq.jpg", "yt-dpM43BlLhZI-mq.jpg"]


def test_image_vide_refusee_sans_fichier_partiel(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        ve.recuperer(YT, dossier=tmp_path, telecharger=lambda _url: b"")
    assert list(tmp_path.iterdir()) == []


def test_recuperer_tout_continue_apres_une_panne(tmp_path: Path) -> None:
    def telecharger(url: str) -> bytes:
        if "panne" in url:
            raise OSError("reseau")
        return b"image"

    ecrits, pannes = ve.recuperer_tout(
        [{"guid": "g0", "imageUrl": "https://exemple.test/panne.jpg"}, YT],
        dossier=tmp_path, telecharger=telecharger)

    assert ecrits == 2
    assert pannes == ["g0: OSError: reseau"]
