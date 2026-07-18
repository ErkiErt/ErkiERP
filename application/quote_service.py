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


def build_price_summary(result):
    """Koosta pakkumise hinna jaotus selgeteks eraldi ridadeks.

    UI kuvab need eraldi väljadena, et kasutajale oleks üheselt selge, millest
    hind koosneb. Domeeni ``work_fee_eur`` on ainult saagimise (töö) tasu — see
    EI sisalda materjali maksumust. Kui detail vajab täpsuslõikust, on selle
    lisatasu ``precision_surcharge_eur`` juba ``work_fee_eur`` sees; siin eraldame
    selle omaette reaks „võimalikud lisatööd", et põhitööraha jääks võrreldavaks.

    Materjali €/m² hinda praegu andmestikus (``plastmaterjalid_sae_app.csv``) ei
    ole, seega ``material_cost_eur`` on 0 ja ``material_cost_known`` on ``False``.
    Sel juhul kuvab UI materjali PINDALA (m²) ja märgib, et hind kokku ei sisalda
    materjali maksumust.
    """
    work_fee = float(result.get('work_fee_eur', 0.0))
    surcharge = (
        float(result.get('precision_surcharge_eur', 0.0))
        if result.get('precision_cut') else 0.0
    )
    # Põhitööraha = kogu tööraha miinus täpsuslõikuse lisatasu (kui see on).
    base_work_fee = max(0.0, work_fee - surcharge)
    material_cost = float(result.get('material_cost_eur', 0.0))
    material_cost_known = material_cost > 0.0
    total = float(result.get('total_estimated_cost_eur', work_fee))
    return {
        'base_work_fee_eur': base_work_fee,
        'precision_surcharge_eur': surcharge,
        'has_extra_work': surcharge > 0.0,
        'material_cost_eur': material_cost,
        'material_area_m2': float(result.get('material_needed_area_m2', 0.0)),
        'material_cost_known': material_cost_known,
        'total_eur': total,
        'total_includes_material': material_cost_known,
    }
