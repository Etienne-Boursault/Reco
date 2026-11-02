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
    assert bilan.non_combles
    assert any("audio illisible" in r.getMessage() for r in caplog.records)


def test_without_suspect_nothing_is_heard_again():
    entrees = [(0.0, "Un."), (2.0, "Deux.")]
    reecoute = Reecoute()
    assert ct.combler(entrees, reecoute) == (entrees, ct.Bilan())
    assert reecoute.fenetres == []


@pytest.mark.parametrize("ponctuation", ["?", "!", "…"])
def test_lone_punctuation_does_not_count_as_words(ponctuation):
    assert ct._mots(["Donc", "on", "l'enlève", ponctuation]) == 3

# ===== dernière ligne hors de portée de la réécoute ==========================
# Cas réel de S6-E03 (2026-10-02) : la reco de Kyan, « toujours les pieds sur
# terre, Sonia Kronlund », avalée par la transcription longue. La réécoute la
# retrouvait, mais le recouvrement tombait à 0,565 et la fenêtre était jetée.
RECO_PERDUE = (4318.0, "Eh ben…")
PERSPECTIVE = (4331.0, ("tu as une autre perspective du petit microcosme que t'as "
                        "en te regardant en permanence."))
C_EST_BEAU = (4337.0, "C'est beau ce que tu dis.")
REECOUTE_PIEDS = [
    (4318.0, (" Eh bien, toujours les pieds sur terre, Sonia Croudlant. Vraiment un super "
              "podcast à écouter quotidiennement,")),
    (4324.32, (" une petite demi-heure, deux portraits de gens sur une thématique. "
               "C'est génial à écouter,")),
    (4329.16, (" ça ouvre sur le monde et ça te donne une autre perspective du petit "
               "microcosme que tu as en te regardant en permanence.")),
]


def _episode_pieds(*lignes):
    """Comme `_episode`, mais autour des horodatages réels de S6-E03 (4318 s)."""
    avant = [(4290.0 + 3 * k, f"Réplique numéro {k} de l'épisode.") for k in range(9)]
    fin = lignes[-1][0]
    apres = [(fin + 3 + 3 * k, f"Suite numéro {k} de l'épisode.") for k in range(9)]
    return [*avant, *lignes, *apres]


def test_a_last_line_the_rehearing_could_not_reach_does_not_sink_the_window():
    """La borne de fin tombe sur un début de ligne : « C'est beau ce que tu dis. »
    n'a qu'une seconde avant la fin de l'audio réécouté, donc la réécoute ne la
    rend pas. Ses 6 mots sur 23 ne doivent pas faire jeter le passage retrouvé."""
    entrees = _episode_pieds(RECO_PERDUE, PERSPECTIVE, C_EST_BEAU)
    apres, bilan = ct.combler(entrees, Reecoute(REECOUTE_PIEDS))
    assert bilan.combles == 1
    assert "les pieds sur terre" in _texte(apres)
    assert "Sonia" in _texte(apres)
    # Rien de l'existant n'est perdu ni déplacé.
    assert C_EST_BEAU in apres and _texte(apres).count("C'est beau ce que tu dis.") == 1
    assert [d for d, _t in apres] == sorted(d for d, _t in apres)


def test_a_rehearing_about_something_else_is_still_refused_when_the_last_line_is_unreached():
    """Le garde-fou ne doit pas tomber avec lui : une réécoute hors sujet ne
    reprend aucune ligne, donc elle reste refusée."""
    entrees = _episode_pieds(RECO_PERDUE, PERSPECTIVE, C_EST_BEAU)
    pub = [(4318.0, "Abonnez-vous à la chaîne et activez la cloche pour ne rien rater.")]
    apres, bilan = ct.combler(entrees, Reecoute(pub))
    assert apres == entrees and bilan.combles == 0


HORS_SUJET = [(4318.0, ("Je pense qu'en grandissant c'est beaucoup ça qu'on te raconte, "
                        "quand t'es plus jeune on te dit qu'après la mort tu vas dans une "
                        "ferme et on t'explique que tu flottes au-dessus des nuages."))]


def test_the_bilan_carries_the_windows_left_alone_and_their_longest_silence():
    """Ce que l'éditeur reçoit par Matrix : où, et combien de temps de silence —
    c'est la durée qui dit si le passage vaut l'écoute. La réécoute entend bien
    plus que la transcription, mais ne s'y cale pas : du texte manque peut-être."""
    entrees = _episode_pieds(RECO_PERDUE, PERSPECTIVE, C_EST_BEAU)
    _apres, bilan = ct.combler(entrees, Reecoute(HORS_SUJET))
    assert bilan.combles == 0
    assert [debut for debut, _silence in bilan.non_combles] == [4318.0]
    assert bilan.non_combles[0][1] == pytest.approx(13.0)


def test_a_window_whose_rehearing_hears_nothing_more_is_not_reported():
    """S6-E07 : les trois faux « passages muets » (00:03:17, 00:40:14, 01:32:16)
    n'avaient, à la réécoute, pas plus de mots que la transcription."""
    entrees = _episode_pieds(RECO_PERDUE, PERSPECTIVE, C_EST_BEAU)
    _apres, bilan = ct.combler(entrees, Reecoute([(4318.0, "Eh ben…")]))
    assert bilan.combles == 0 and bilan.non_combles == []


def test_a_filled_window_is_not_reported_as_left_alone():
    entrees = _episode_pieds(RECO_PERDUE, PERSPECTIVE, C_EST_BEAU)
    _apres, bilan = ct.combler(entrees, Reecoute(REECOUTE_PIEDS))
    assert bilan.combles == 1 and bilan.non_combles == []


def test_the_windows_left_alone_are_named_in_the_log(caplog):
    entrees = _episode_pieds(RECO_PERDUE, PERSPECTIVE, C_EST_BEAU)
    ct.combler(entrees, Reecoute([(4318.0, "Eh ben…")]))
    assert any("laissées telles quelles" in r.getMessage() and "01:11:58" in r.getMessage()
               for r in caplog.records)


# ===== boucles sans saut horodaté ============================================
def _boucle_frere():
    return [
        (5409.0, "Il est éminemment drôle ce monsieur."),
        (5411.0, "Un grand plaisir."),
        *((5412.0 + n, "Frère.") for n in range(30)),
        (5442.0, "Il aurait pu se sortir les pouces et briller au firmament."),
        (5445.0, "Il n'a pas choisi de sortir de Suisse."),
    ]


def _reprise_frere():
    return [
        (5409.0, "Il est éminemment drôle ce monsieur."),
        (5411.0, "Un grand plaisir."),
        (5412.0, "Et j'avais vu en première partie une Suissesse, Fiona G."),
        (5415.0, "Oui, qui a un Instagram totalement illisible."),
        (5422.0, "Elle est sur Inter maintenant."),
        (5430.0, "Blaise Bersinger, un humoriste suisse très talentueux."),
        (5439.0, "Ne l'enfonce pas non plus."),
        (5441.6, "Il aurait pu se sortir les pouces et briller au firmament."),
        (5445.0, "Il n'a pas choisi de sortir de Suisse."),
    ]


def test_thirty_repeated_lines_are_replaced_only_between_matching_anchors():
    entrees = _boucle_frere()
    reprise = Reecoute(_reprise_frere())

    apres, bilan = ct.combler(entrees, Reecoute(), reprise, duree_audio=5579.0)

    assert reprise.fenetres == [[5392.0, 5462.0]]
    assert bilan.boucles_reparees == [(5412.0, 30)]
    assert bilan.boucles_non_reparees == []
    assert "Fiona G." in _texte(apres) and "Blaise Bersinger" in _texte(apres)
    assert "Frère." not in _texte(apres)
    assert apres[0:2] == entrees[0:2]
    assert apres[-2:] == entrees[-2:]
    assert [d for d, _t in apres] == sorted(d for d, _t in apres)


def test_a_relisten_without_both_anchors_never_overwrites_a_loop():
    entrees = _boucle_frere()
    reprise = Reecoute([(5412.0, "Une publicité sans rapport avec l'épisode."),
                        (5430.0, "Un autre texte inventé par le modèle."),
                        (5441.0, "Merci de vous abonner.")])

    apres, bilan = ct.combler(entrees, Reecoute(), reprise)

    assert apres == entrees
    assert bilan.boucles_reparees == []
    assert bilan.boucles_non_reparees == [(5412.0, 30)]


def test_a_short_real_repetition_is_not_reheard():
    entrees = [(0.0, "Bonjour."), *((i + 1.0, "Non.") for i in range(4)),
               (5.0, "On continue.")]
    reprise = Reecoute(_reprise_frere())

    apres, bilan = ct.combler(entrees, Reecoute(), reprise)

    assert apres == entrees and reprise.fenetres == []
    assert bilan.boucles_reparees == bilan.boucles_non_reparees == []


def test_seven_repeated_lines_are_a_spoken_repetition_left_silent():
    """59 suites de 5 à 7 lignes dans le dépôt, presque toutes parlées."""
    entrees = [(0.0, "On commence."), *((i + 1.0, "Bonne année !") for i in range(7)),
               (8.0, "On continue.")]
    reprise = Reecoute(_reprise_frere())

    apres, bilan = ct.combler(entrees, Reecoute(), reprise)

    assert apres == entrees and reprise.fenetres == []
    assert bilan.boucles_non_reparees == []


def test_eight_repeated_lines_are_reported_without_automatic_replacement():
    entrees = [(0.0, "On commence."), *((i + 1.0, "Frère.") for i in range(8)),
               (9.0, "On continue.")]
    reprise = Reecoute(_reprise_frere())

    apres, bilan = ct.combler(entrees, Reecoute(), reprise)

    assert apres == entrees and reprise.fenetres == []
    assert bilan.boucles_non_reparees == [(1.0, 8)]


def test_an_eleven_line_repetition_is_reported_without_automatic_replacement():
    entrees = [(0.0, "On commence."), *((i + 1.0, "C'est bon.") for i in range(11)),
               (12.0, "On continue.")]
    reprise = Reecoute(_reprise_frere())

    apres, bilan = ct.combler(entrees, Reecoute(), reprise)

    assert apres == entrees and reprise.fenetres == []
    assert bilan.boucles_non_reparees == [(1.0, 11)]


def test_a_failed_loop_relisten_is_reported_without_losing_the_text():
    entrees = _boucle_frere()
    apres, bilan = ct.combler(entrees, Reecoute(),
                              Reecoute(erreur=RuntimeError("audio illisible")))
    assert apres == entrees
    assert bilan.boucles_non_reparees == [(5412.0, 30)]


def test_interleaved_phrase_repetitions_are_reported_without_automatic_replacement():
    entrees = [(0.0, "Introduction.")]
    for i in range(8):
        entrees.extend([(2 * i + 1.0, "C'est une bonne raison."),
                        (2 * i + 2.0, "Une autre phrase.")])
    entrees.append((18.0, "Suite de l'épisode."))

    apres, bilan = ct.combler(entrees, Reecoute())

    assert apres == entrees
    assert bilan.boucles_non_reparees == []
    assert len(bilan.repetitions_suspectes) == 1
    assert bilan.repetitions_suspectes[0][2] >= 8


def test_a_repeated_phrase_inside_one_line_is_reported():
    repetitions = ct.repetitions_de_phrases([(1.0, "et euh " * 30)])
    assert len(repetitions) == 1
    assert repetitions[0][2] >= 8


def test_exact_loop_is_not_reported_twice_as_a_phrase_repetition():
    entrees = [(float(i), "C'est bon.") for i in range(11)]
    assert ct.repetitions_de_phrases(entrees) == []



# ===== génériques inventés ===================================================
@pytest.mark.parametrize("ligne", [
    "Sous-titrage Société Radio-Canada",
    "Sous-titrage ST' 501",
    "– Sous-titrage ST' 501",
    "Sous-titres par Jérémy Diaz.",
    "Sous-titres réalisés par la communauté d'Amara.org",
])
def test_known_subtitle_credits_are_recognised(ligne):
    assert ct.GENERIQUE.match(ligne)


@pytest.mark.parametrize("ligne", [
    "Il est sous-titré, au moins en anglais, peut-être en français.",
    "Rien que les sous-titres.",
    "Comment vous faites les sous-titres ?",
    "Sous-titres par mon frère",
    "Abonnez-vous à la chaîne.",
])
def test_spoken_mentions_of_subtitles_are_kept(ligne):
    assert not ct.GENERIQUE.match(ligne)


def test_an_invented_credit_is_removed_and_its_hole_is_heard_again():
    """S6-E07, 00:39:50 : le générique couvrait un passage du blind test."""
    entrees = [(2380.0, "Allez, chanson suivante."), (2384.0, "Écoutez bien."),
               (2390.0, "Sous-titrage Société Radio-Canada"),
               (2399.0, "C'est Daft Punk !"), (2401.0, "Bravo.")]
    reecoute = Reecoute([(2384.0, "Écoutez bien."),
                         (2386.0, "Sous-titrage ST' 501"),
                         (2390.0, "Je crois que c'est un groupe français des années 90."),
                         (2399.0, "C'est Daft Punk !")])

    apres, bilan = ct.combler(entrees, reecoute)

    assert bilan.generiques_retires == [2390.0]
    assert "Sous-titrage" not in _texte(apres)
    assert reecoute.fenetres, "le trou laissé par le générique doit être réécouté"
    assert "groupe français des années 90" in _texte(apres)
    assert [d for d, _t in apres] == sorted(d for d, _t in apres)


# ===== boucle en morceaux ====================================================
def _boucle_en_morceaux():
    """S6-E07 en production : 7 « Frère. », 4 vraies phrases, puis 30 « Frère. »."""
    return [
        (5389.0, "C'est pour ça que je le connais pas, je regarde les trucs..."),
        (5392.0, "Miaou."),
        *((5393.0 + n, "Frère.") for n in range(7)),
        (5400.0, "Mais en plus tu peux t'en foutre des chroniques, il fait un truc un peu différent"),
        (5405.0, "Le spectacle de Louis Catlat."),
        (5409.0, "Il est éminemment drôle ce monsieur."),
        (5411.0, "Un grand plaisir."),
        *((5412.0 + n, "Frère.") for n in range(30)),
        (5442.0, "Il aurait pu se sortir les pouces et briller au firmament."),
        (5445.0, "Il n'a pas choisi de sortir de Suisse."),
    ]


def _reprise_en_morceaux():
    return [
        (5389.0, "C'est pour ça que je le connais pas, je regarde les trucs..."),
        (5392.0, "Miaou."),
        (5394.0, "Qui sont pas des trucs de... Je peux pas dire, ça s'appelle Un Bon Moment."),
        (5400.0, "Mais en plus tu peux t'en foutre des chroniques, il fait un truc un peu différent"),
        (5405.0, "Le spectacle de Louis Catlat."),
        (5409.0, "Il est éminemment drôle ce monsieur. Un grand plaisir."),
        (5412.0, "Et j'avais vu en première partie une Suissesse, Fiona G."),
        (5415.0, "Oui, qui a un Instagram totalement illisible."),
        (5430.0, "Blaise Bersinger, un humoriste suisse très talentueux."),
        (5441.6, "Il aurait pu se sortir les pouces et briller au firmament."),
        (5445.0, "Il n'a pas choisi de sortir de Suisse."),
    ]


def test_the_pieces_of_one_loop_form_a_single_zone():
    assert ct.zones_de_boucle(_boucle_en_morceaux()) == [(2, 43, 37)]


def test_a_loop_in_pieces_is_replaced_as_a_whole():
    entrees = _boucle_en_morceaux()
    reprise = Reecoute(_reprise_en_morceaux())

    apres, bilan = ct.combler(entrees, Reecoute(), reprise, duree_audio=5579.0)

    assert bilan.boucles_reparees == [(5393.0, 37)]
    assert "Frère." not in _texte(apres)
    assert "Fiona G." in _texte(apres) and "Louis Catlat" in _texte(apres)
    assert [d for d, _t in apres] == sorted(d for d, _t in apres)


def test_a_relisten_that_drops_the_real_sentences_of_a_zone_is_refused():
    """La parole prise entre les morceaux ne doit pas disparaître au remplacement."""
    entrees = _boucle_en_morceaux()
    sans_la_parole = [s for s in _reprise_en_morceaux()
                      if not s[1].startswith(("Mais en plus", "Le spectacle", "Il est"))]
    apres, bilan = ct.combler(entrees, Reecoute(), Reecoute(sans_la_parole))
    assert apres == entrees
    assert bilan.boucles_non_reparees == [(5393.0, 37)]


def test_two_short_spoken_repetitions_far_apart_stay_separate():
    entrees = [(0.0, "On commence."), *((1.0 + n, "Non.") for n in range(4)),
               *((10.0 + n, f"Phrase {n} de l'épisode.") for n in range(30)),
               *((40.0 + n, "Non.") for n in range(4)), (45.0, "Suite.")]
    assert ct.zones_de_boucle(entrees) == []
