"""Tagasiühilduvuse kiht.

Materjalide kataloogi andmejuurdepääs elab nüüd ``repositories.material_catalog``
kihis. See moodul re-ekspordib selle avaliku API, et olemasolevad impordid
(``from materials import ...``) ja testid töötaksid muutumatult.
"""

from repositories.material_catalog import *  # noqa: F401,F403
from repositories.material_catalog import (  # noqa: F401
    _canonical_group,
    _dimensions_from_name,
    _display_group,
    _exact_material_name,
    _has_usable_sheet_format,
    _is_supported_article,
    _number,
    _number_text,
    _with_cast_modifier,
)
