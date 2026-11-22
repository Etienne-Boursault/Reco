"""Bords des longues boucles : cas relevés sur les anciens épisodes (2026-11-02).

Sur 9 longues boucles refusées, 8 l'étaient faute de bord alors que leur
réécoute était propre. Ces tests reprennent leurs formes, en plus court.
"""
from __future__ import annotations

import combler_trous as ct


class Reecoute:
    def __init__(self, segments):
        self.segments, self.fenetres = list(segments), []

    def __call__(self, clip):
        self.fenetres.append(clip)
        return list(self.segments)


def _texte(entrees):
    return " ".join(t for _d, t in entrees)


DEBUT = [(100.0, "On parlait de la tournée d'été tout à l'heure."),
         (103.0, "Oui, celle qui passe par Lyon et Marseille.")]
FIN = [(160.0, "Est-ce que tu veux recommander quelque chose aujourd'hui ?"),
       (163.0, "Oui, un livre que j'ai adoré cet été.")]
REPRISE = [(100.0, "On parlait de la tournée d'été tout à l'heure."),
           (103.0, "Oui, celle qui passe par Lyon et Marseille."),
           (106.0, "Et là, il y a eu ce concert incroyable à Nantes."),
           (120.0, "La salle entière chantait avec lui, c'était fou."),
           (140.0, "Et après le concert, on est allés manger ensemble."),
           (160.0, "Est-ce que tu veux recommander quelque chose aujourd'hui ?"),
           (163.0, "Oui, un livre que j'ai adoré cet été.")]


def test_two_loops_stuck_together_are_replaced_as_one():
    """Clément Cotentin : 26 lignes d'un texte, une ligne, puis 361 d'un autre."""
    entrees = [*DEBUT,
               *((106.0 + n, "Cléopâtrement Aurélien.") for n in range(16)),
               (122.0, "Cléopâtreur."),
               *((123.0 + n, "Cléopâtre Aurélien.") for n in range(30)),
               *FIN]

    apres, reparees, refusees = ct.reparer_boucles(entrees, Reecoute(REPRISE))

    assert reparees == [(106.0, 46)] and refusees == []
    assert "Cléopâtre" not in _texte(apres)
    assert "concert incroyable à Nantes" in _texte(apres)
    assert apres[:2] == DEBUT and apres[-2:] == FIN


def test_misheard_lines_next_to_the_loop_are_skipped_to_find_its_edge():
    """Jeu de chaîne de noms : les lignes qui touchent la boucle sont fausses aussi."""
    entrees = [*DEBUT,
               (105.0, "Moni Cardi Bicente."),
               (105.5, "Moni Cardi."),
               *((106.0 + n, "C'est validé.") for n in range(30)),
               (150.0, "Lizarazou Lizarazou."),
               (152.0, "Lizarazou Bellucci."),
               *FIN]

    apres, reparees, _refusees = ct.reparer_boucles(entrees, Reecoute(REPRISE))

    assert reparees == [(106.0, 30)]
    assert "C'est validé." not in _texte(apres)
    assert "Moni Cardi" not in _texte(apres) and "Lizarazou" not in _texte(apres)
    assert apres[:2] == DEBUT and apres[-2:] == FIN


def test_an_edge_beyond_six_lines_is_not_searched():
    mal_entendues = [(104.0 + k / 10, f"Charabia numéro {k}.") for k in range(7)]
    entrees = [*DEBUT, *mal_entendues, *((106.0 + n, "C'est validé.") for n in range(30)), *FIN]

    apres, reparees, refusees = ct.reparer_boucles(entrees, Reecoute(REPRISE))

    assert apres == entrees and reparees == [] and refusees == [(106.0, 30)]


def test_a_rehearing_sentence_that_straddles_the_end_of_the_loop_anchors_it():
    """« Bloqués » : la phrase réécoutée commence 3 s avant la fin de la boucle."""
    entrees = [*DEBUT, *((106.0 + n, "Aurel in the booth.") for n in range(30)), *FIN]
    reprise = [*REPRISE[:5],
               (157.0, ("Bon. Est-ce que tu veux recommander quelque chose aujourd'hui ?"
                        " Oui, un livre que j'ai adoré cet été."))]

    apres, reparees, _refusees = ct.reparer_boucles(entrees, Reecoute(reprise))

    assert reparees == [(106.0, 30)]
    assert "Aurel in the booth" not in _texte(apres)
    assert apres[-2:] == FIN


def test_a_sentence_repeated_inside_the_loop_is_part_of_it():
    """Zazie et Vianney : « Il n'y a David Guetta. » ×3 au milieu de la boucle."""
    entrees = [*DEBUT,
               *((106.0 + n, "To be free.") for n in range(20)),
               *((126.0 + n, "Il n'y a pas David Guetta ici.") for n in range(3)),
               *((129.0 + n, "To be free.") for n in range(20)),
               *FIN]

    _apres, reparees, refusees = ct.reparer_boucles(entrees, Reecoute(REPRISE))

    assert reparees == [(106.0, 40)] and refusees == []


def test_real_sentences_inside_the_loop_must_still_be_heard_again():
    entrees = [*DEBUT,
               *((106.0 + n, "To be free.") for n in range(20)),
               (126.0, "Et là je me rappelle très bien de cette soirée chez Paul."),
               *((127.0 + n, "To be free.") for n in range(20)),
               *FIN]

    apres, reparees, refusees = ct.reparer_boucles(entrees, Reecoute(REPRISE))

    assert apres == entrees and reparees == [] and refusees == [(106.0, 40)]
