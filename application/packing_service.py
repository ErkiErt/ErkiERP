"""Rakenduskiht (use case) pakkimisjuhise koostamiseks.

UI/lõikeleht kutsub seda teenust ja saab struktureeritud pakkimisplaani
lõiketulemuse (``result``) põhjal. Sõltuvussuund: ``ui → application → domain``.
See moodul ei impordi Streamlitit ega esitlusloogikat.

NB: pakkimisplaan on SISEMINE tootmisjuhis — seda ei lisata kliendi hinda.
"""

from domain.packing import build_packing_plan


def build_packing_plan_for_result(result):
    """Koosta lõiketulemuse põhjal pakkimisplaan (kast või riba/alus).

    Kasutab tellija sisestatud algmõõte (``original_detail_*``), et pakkimine
    lähtuks tegelikust detaili suurusest, mitte pöördstrateegia järgi vahetatud
    mõõtudest.
    """
    detail_w = result.get('original_detail_width_mm') or result.get('detail_width_mm')
    detail_l = result.get('original_detail_length_mm') or result.get('detail_length_mm')
    thickness = result.get('thickness_mm')
    count = result.get('detail_count')
    return build_packing_plan(detail_w, detail_l, thickness, count)
