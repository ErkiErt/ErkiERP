"""Rakenduskiht (use case'id) müügipakkumise arvutamiseks.

Siin elab lõikeplaani ja hinnastuse arvutamise voog, mida varem hoidis
Streamliti UI (``app.py``) oma esitusloogika sees. UI kutsub neid teenuseid ja
vastutab ainult sisendi kogumise ning tulemuse kuvamise eest.

Sõltuvussuund: ``ui → application → domain``. See moodul ei impordi Streamlitit
ega andmeallika detaile.
"""

from domain.calculations import (
    BLADES,
    add_blade_reasons,
    apply_monotonic_quote_floor,
    build_best_result_for_blade,
    choose_best_result,
    max_single_stock_capacity,
)


def compute_quote(inp):
    """Arvuta parim lõikeplaan üle kõigi ketaste ja rakenda hinnastuse alammäär.

    Tagastab paari ``(best_result, blade_results)``. Kui detail ei mahu
    toorikusse, on ``best_result`` ``None`` (UI kuvab sel juhul vea).
    Ketaste alternatiividele lisatakse põhjendused, et UI saaks neid vajadusel
    kuvada.
    """
    blade_results = [build_best_result_for_blade(blade, inp) for blade in BLADES]
    best = choose_best_result(blade_results)
    if best is None:
        return None, blade_results
    best = apply_monotonic_quote_floor(best, inp)
    add_blade_reasons(blade_results, best)
    return best, blade_results


def single_stock_capacity(inp):
    """Ühest füüsilisest toorikust valmistatavate detailide maksimum.

    Kasutatakse jäägi-režiimis, et kuvada kasutajale, mitu detaili ühest
    sisestatud jäägist saab.
    """
    return max_single_stock_capacity(inp)
