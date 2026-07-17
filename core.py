"""Tagasiühilduvuse kiht.

Kogu arvutusloogika elab nüüd puhtas domeenikihis ``domain.calculations``
(ei sõltu Streamlitist ega andmeallikast). See moodul re-ekspordib domeeni
avaliku API, et olemasolevad impordid (``from core import ...``) ja testid
töötaksid muutumatult.
"""

from domain.calculations import *  # noqa: F401,F403
# Alakriipsuga privaatnimed ei tule ``import *`` kaudu kaasa, kuid mõned
# testid ja abifunktsioonid impordivad neid otse ``core``-ist.
from domain.calculations import (  # noqa: F401
    _axis_cut_count,
    _largest_usable_area,
    _largest_usable_offcut_area,
    _partial_layout,
    _simple_offcuts,
    _strategy_offcuts,
)
