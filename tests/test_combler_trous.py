"""Tests de `tools/combler_trous.py` — retrouver les passages perdus par Whisper.

La réécoute est un double : aucun modèle ne tourne. Les textes reprennent le cas
réel de S6-E01 (le livre de Bref 2, perdu après 01:16:31).
"""
from __future__ import annotations

import pytest

import combler_trous as ct

BOUQUIN = (4591.0, "Le bouquin, il arrive très très bientôt, très vite.")
ANALYSE = (4603.0, "qui s'analyse par une spécialité philosophe, qui fait un petit texte au milieu.")
PHOTOS = (4609.0, "Il y a quelques jolies photos, le livre est beau.")
SUITE = (4611.0, "C'est un livre pour ceux qui ont bien aimé Bref 2 quoi.")
REECOUTE_BREF = [
    (4591.0, "Le bouquin arrive très très bientôt, très vite, à aller dans les bacs, du coup,"),
    (4596.0, "parce que vous ne pouvez pas streamer le bouquin."),
    (4599.0, "C'est un livre des scripts de Bref 2."),
    (4601.0, "Oh cool ! Et dedans il y a toute une analyse par une spécialité philosophe,"),
    (4605.0, "qui fait un petit texte au milieu, il y a quelques jolies photos."),
]


def _episode(*lignes):
    """Des lignes serrées autour de celles données : aucun autre saut suspect."""
    avant = [(4560.0 + 3 * k, f"Réplique numéro {k} de l'épisode.") for k in range(10)]
    fin = lignes[-1][0]
    apres = [(fin + 3 + 3 * k, f"Suite numéro {k} de l'épisode.") for k in range(10)]
    return [*avant, *lignes, *apres]


class Reecoute:
    """Double de la réécoute : rend `segments` et note les fenêtres demandées."""

    def __init__(self, segments=(), erreur=None):
        self.segments, self.erreur, self.fenetres = list(segments), erreur, []

    def __call__(self, clip):
        self.fenetres.append(clip)
        if self.erreur:
            raise self.erreur
        return list(self.segments)


def _texte(entrees):
    return " ".join(t for _d, t in entrees)


# ===== repérage ==============================================================
def test_a_short_line_followed_by_a_long_silence_is_suspect():
    entrees = _episode(BOUQUIN, ANALYSE, PHOTOS, SUITE)
    assert ct.candidats(entrees) == [10]


def test_a_long_line_explains_the_jump_by_itself():
    longue = (4591.0, "Et là, " + "vraiment " * 12 + "il parle longtemps sans s'arrêter.")
    assert ct.candidats(_episode(longue, ANALYSE)) == []


def test_the_window_lasts_at_least_twenty_seconds_and_ends_on_a_line():
    entrees = _episode(BOUQUIN, ANALYSE, PHOTOS, SUITE)
    assert ct.fenetres(entrees, [10]) == [(4591.0, 4611.0)]


def test_overlapping_windows_are_merged():
    entrees = [(0.0, "Un."), (10.0, "Deux."), (20.0, "Trois."), (40.0, "Quatre."), (41.0, "Cinq.")]
    assert ct.fenetres(entrees, ct.candidats(entrees)) == [(0.0, 40.0)]


def test_a_window_near_the_end_runs_to_the_end_of_the_audio():
    entrees = [(0.0, "Ça commence."), (2.0, "On y est."), (15.0, "Et c'est fini.")]
    assert ct.fenetres(entrees, ct.candidats(entrees)) == [(2.0, None)]


# ===== comblement ============================================================
def test_the_lost_sentence_is_found_and_nothing_else_moves():
    entrees = _episode(BOUQUIN, ANALYSE, PHOTOS, SUITE)
    reecoute = Reecoute(REECOUTE_BREF)

    apres, bilan = ct.combler(entrees, reecoute)

    assert reecoute.fenetres == [[4591.0, 4611.0]]
    assert "C'est un livre des scripts de Bref 2." in _texte(apres)
    assert bilan.candidats == 1 and bilan.combles == 1 and bilan.mots_ajoutes > 10
    # Les bords ne bougent pas : rien de recopié, rien de coupé.
    assert apres[:11] == entrees[:11]
    assert PHOTOS in apres and SUITE in apres
    assert _texte(apres).count("très très bientôt") == 1
    assert [d for d, _t in apres] == sorted(d for d, _t in apres)


def test_a_rehearing_that_says_the_same_thing_changes_nothing():
    entrees = _episode(BOUQUIN, ANALYSE, PHOTOS, SUITE)
    apres, bilan = ct.combler(entrees, Reecoute([BOUQUIN, ANALYSE, PHOTOS]))
    assert apres == entrees and bilan.combles == 0


def test_a_few_extra_words_are_a_variant_not_a_lost_passage():
    entrees = _episode(BOUQUIN, ANALYSE, PHOTOS, SUITE)
    variante = [(4591.0, "Le bouquin, il arrive très très bientôt, très vite, voilà quoi."),
                ANALYSE, PHOTOS]
    apres, bilan = ct.combler(entrees, Reecoute(variante))
    assert apres == entrees and bilan.combles == 0


def test_a_rehearing_about_something_else_is_not_trusted():
    entrees = _episode(BOUQUIN, ANALYSE, PHOTOS, SUITE)
    musique = [(4591.0, ("Sous-titres réalisés par la communauté, merci d'avoir regardé "
                         "cette vidéo, abonnez-vous à la chaîne pour ne rien rater."))]
    apres, bilan = ct.combler(entrees, Reecoute(musique))
    assert apres == entrees and bilan.combles == 0


def test_text_the_rehearing_adds_outside_its_anchors_is_left_out():
    """Avant la première ancre, on ne saurait pas où le placer : un texte que
    l'épisode a déjà, horodaté plus tôt, serait recopié en double."""
    entrees = _episode(BOUQUIN, ANALYSE, PHOTOS, SUITE)
    deja_la = [(4589.0, "Réplique numéro 9 de l'épisode, encore une fois et en entier."),
               *REECOUTE_BREF]
    apres, _bilan = ct.combler(entrees, Reecoute(deja_la))
    assert _texte(apres).count("Réplique numéro 9") == 1
    assert "C'est un livre des scripts de Bref 2." in _texte(apres)


def test_a_one_word_suspect_line_still_anchors_the_rehearing():
    entrees = [(4591.0, "Ouais."), (4603.0, "Bref, on en était où ?"),
               (4605.0, "On parlait du livre.")]
    reecoute = [(4591.0, "Ouais. Et il y a le livre des scripts de Bref 2 qui sort mercredi."),
                (4603.0, "Bref, on en était où ?"), (4605.0, "On parlait du livre.")]
    apres, bilan = ct.combler(entrees, Reecoute(reecoute))
    assert bilan.combles == 1
    assert (4591.0, "Ouais. Et il y a le livre des scripts de Bref 2 qui sort mercredi.") in apres


def test_a_gap_at_the_start_of_the_episode():
    entrees = [(0.0, "Bonjour à tous."), (12.0, "On commence tout de suite.")]
    reecoute = [(0.0, "Bonjour à tous. Aujourd'hui on reçoit deux invités formidables."),
                (12.0, "On commence tout de suite.")]
    apres, bilan = ct.combler(entrees, Reecoute(reecoute))
    assert bilan.combles == 1
    assert apres == [(0.0, "Bonjour à tous. Aujourd'hui on reçoit deux invités formidables."),
                     (12.0, "On commence tout de suite.")]


def test_a_gap_near_the_end_is_heard_up_to_the_end_of_the_audio():
    entrees = [(0.0, "Ça commence."), (2.0, "Merci à vous tous."), (15.0, "Salut.")]
    reecoute_fin = Reecoute([(2.0, "Merci à vous tous. Allez voir le spectacle au Zénith."),
                             (15.0, "Salut.")])
    apres, bilan = ct.combler(entrees, reecoute_fin)
    assert reecoute_fin.fenetres == [[2.0]]
    assert bilan.combles == 1 and apres[-1] == (15.0, "Salut.")
    assert "spectacle au Zénith" in _texte(apres)


def test_a_failing_rehearing_keeps_the_transcript(caplog):
    entrees = _episode(BOUQUIN, ANALYSE, PHOTOS, SUITE)
    apres, bilan = ct.combler(entrees, Reecoute(erreur=RuntimeError("audio illisible")))
    assert apres == entrees and bilan.combles == 0
    assert any("audio illisible" in r.getMessage() for r in caplog.records)


def test_without_suspect_nothing_is_heard_again():
    entrees = [(0.0, "Un."), (2.0, "Deux.")]
    reecoute = Reecoute()
    assert ct.combler(entrees, reecoute) == (entrees, ct.Bilan())
    assert reecoute.fenetres == []


@pytest.mark.parametrize("ponctuation", ["?", "!", "…"])
def test_lone_punctuation_does_not_count_as_words(ponctuation):
    assert ct._mots(["Donc", "on", "l'enlève", ponctuation]) == 3
