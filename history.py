"""Tagasiühilduvuse kiht.

Ajaloo ja päringute salvestus elab nüüd ``repositories.history_store`` kihis.
See moodul re-ekspordib selle avaliku API, et olemasolevad impordid
(``from history import ...``) ja testid töötaksid muutumatult.
"""

from repositories.history_store import *  # noqa: F401,F403
from repositories.history_store import _normalize  # noqa: F401
