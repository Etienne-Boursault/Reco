"""music_links_editions.py — un même enregistrement, plusieurs parutions.

« Roméo kiffe Juliette » existe chez Apple et Spotify sur l'album *3ème temps*
(2010) ET sur la compilation *Collection (2003-2019)*. Pour `verdict`, deux
identités distinctes survivaient aux garde-fous : il refusait (« ambiguous »),
et la reco de S6-E04 n'a eu que son lien Deezer. Ce n'était pourtant pas un
doute sur l'œuvre — seulement sur la PARUTION.

Ce module reconnaît ce cas et choisit la parution originale. Il ne tranche
QUE si tous les candidats retenus ont le même titre (au noyau près) et le même
artiste ; et dès que deux ISRC différents apparaissent, ce sont deux
enregistrements (réenregistrement, autre interprète…) : on laisse le refus.
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from common import normalize_text
from title_variants import split_suffix

if TYPE_CHECKING:  # pragma: no cover
    from music_links_matching import Candidate


def _core(title: str) -> str:
    return normalize_text(split_suffix(title)[0] or title)


def _rank(cand: Candidate) -> tuple[int, str]:
    """Ordre de préférence : hors compilation d'abord, puis la plus ancienne.

    Une date absente passe après les dates connues (« 9 » > tout chiffre).
    """
    return (1 if cand.compilation else 0, cand.release or "9")


def same_recording(kept: Sequence[Candidate]) -> Candidate | None:
    """La parution à retenir si `kept` n'est qu'un enregistrement, sinon None."""
    if len(kept) < 2 or any(not c.title for c in kept):
        return None  # page artiste : pas de titre pour ancrer la comparaison
    if len({_core(c.title) for c in kept}) != 1:
        return None
    if len({normalize_text(c.artist) for c in kept}) != 1:
        return None
    if len({c.isrc for c in kept if c.isrc}) > 1:
        return None
    return min(kept, key=_rank)
