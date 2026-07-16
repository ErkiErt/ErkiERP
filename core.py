import math
from dataclasses import dataclass, replace

MAX_LENGTH_MM = 3800.0
MAX_WIDTH_MM = 3800.0
MAX_MATERIAL_THICKNESS_MM = 95.0
MAX_DETAIL_COUNT = 10_000
SAW_HOURLY_RATE_EUR = 60.0
TRIM_REMOVAL_MM = 1.0
ROTATION_PREFERRED_MAX_MM = 1000.0
MIN_STRIP_WIDTH_MM = 4.0
NARROW_STRIP_MAX_WIDTH_MM = 6.0
NARROW_STRIP_MIN_THICKNESS_MM = 2.0
NARROW_STRIP_TIME_FACTOR = 2.0
THICK_MATERIAL_TIME_FACTOR_START_MM = 80.0
THICK_MATERIAL_TIME_FACTOR = 2.0
DUST_BAG_CHANGE_SEC = 10 * 60
DUST_BAG_STANDARD_MIN_THICKNESS_MM = 20.0
DUST_BAG_FAST_MIN_THICKNESS_MM = 50.0
DUST_BAG_STANDARD_STOCK_INTERVAL = 8
DUST_BAG_FAST_STOCK_INTERVAL = 3
SMALL_PRECISION_MAX_COUNT = 10
SMALL_PRECISION_MAX_DETAIL_AREA_M2 = 0.5
SMALL_PRECISION_SURCHARGE_EUR = 20.0
QUOTE_BUFFER_RATE = 0.05
QUOTE_ROUNDING_SEC = 5 * 60

BASE_SETUP_SEC = 20 * 60
PRECISION_SETUP_SEC = 30 * 60
SMALL_BLADE_SWITCH_SEC = 5 * 60
BASE_HANDLING_PER_STOCK_SEC = 90
HANDLING_PER_DETAIL_SEC = 20
CUT_RETURN_FACTOR = 0.20

MIN_SMALL_BLADE_TIME_SAVING_SEC = 10 * 60
MIN_MATERIAL_AREA_SAVING_M2 = 0.01

LARGE_BLADE = {
    'blade': '5,6 mm', 'kerf_mm': 5.6, 'max_stack_mm': 80.0,
    'max_single_thickness_mm': 95.0, 'is_default': True,
}
SMALL_BLADE = {
    'blade': '3,1 mm', 'kerf_mm': 3.1, 'max_stack_mm': 25.0,
    'max_single_thickness_mm': 25.0, 'is_default': False,
}
BLADES = [LARGE_BLADE, SMALL_BLADE]
THICKNESS_OPTIONS_MM = list(range(1, 13)) + [15, 18, 20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70, 75, 80, 85, 90, 95]


@dataclass
class CalcInput:
    thickness_mm: float
    raw_width_mm: float
    raw_length_mm: float
    detail_width_mm: float
    detail_length_mm: float
    detail_count: int
    trim_edges: bool = True
    hourly_rate_eur: float = SAW_HOURLY_RATE_EUR  # vana ajaloo ühilduvus
    material_price_m2_eur: float = 0.0  # vana ajaloo ühilduvus
    precision_cut: bool = False
    stock_source: str | None = None
    max_stock_count: int | None = None


def area_m2(width_mm, length_mm):
    return max(0.0, width_mm) * max(0.0, length_mm) / 1_000_000.0


def get_sec_per_meter(thickness_mm):
    for upper, seconds in ((20, 6.0), (40, 7.5), (50, 10.0), (60, 12.0), (70, 18.0), (80, 24.0), (95, 36.0)):
        if thickness_mm <= upper:
            return seconds
    return None


def quality_control_seconds_per_detail(detail_width_mm, detail_length_mm):
    longest = max(detail_width_mm, detail_length_mm)
    if longest <= 1000:
        return 15
    if longest <= 2000:
        return 25
    return 35


def quality_control_check_count(ordered_detail_count, inspection_unit_count=None):
    """Return staged QC checks; the final inspection unit is always included."""
    units = max(0, int(inspection_unit_count if inspection_unit_count is not None else ordered_detail_count))
    ordered = max(0, int(ordered_detail_count))
    if units == 0:
        return 0
    first_stage = min(units, 25)
    if ordered <= 25 or units <= 25:
        return first_stage
    second_units = min(max(units - 25, 0), 75)
    second_stage = math.ceil(second_units / 10)
    if ordered <= 100 or units <= 100:
        return first_stage + second_stage
    return first_stage + second_stage + math.ceil(max(units - 100, 0) / 25)


def quote_billable_seconds(work_seconds):
    """Apply the agreed 5% reserve and round the final time upward to 5 minutes."""
    work_seconds = max(0.0, float(work_seconds))
    reserve = work_seconds * QUOTE_BUFFER_RATE
    return math.ceil((work_seconds + reserve) / QUOTE_ROUNDING_SEC) * QUOTE_ROUNDING_SEC


def max_pieces_in_length(total_len, piece_len, kerf):
    if total_len <= 0 or piece_len <= 0:
        return 0
    return max(0, math.floor((total_len + kerf) / (piece_len + kerf)))


def used_size_mm(piece_count, piece_size, kerf):
    if piece_count <= 0:
        return 0.0
    return piece_count * piece_size + max(0, piece_count - 1) * kerf


def validate_input_values(inp):
    errors = []
    if not 0 < inp.thickness_mm <= MAX_MATERIAL_THICKNESS_MM:
        errors.append(f'Materjali paksus peab olema vahemikus 0–{int(MAX_MATERIAL_THICKNESS_MM)} mm.')
    if not 0 < inp.raw_width_mm <= MAX_WIDTH_MM:
        errors.append(f'Tooriku laius peab olema vahemikus 1–{int(MAX_WIDTH_MM)} mm.')
    if not 0 < inp.raw_length_mm <= MAX_LENGTH_MM:
        errors.append(f'Tooriku pikkus peab olema vahemikus 1–{int(MAX_LENGTH_MM)} mm.')
    if inp.detail_width_mm <= 0 or inp.detail_length_mm <= 0:
        errors.append('Detaili mõõdud peavad olema suuremad kui 0 mm.')
    elif min(inp.detail_width_mm, inp.detail_length_mm) < MIN_STRIP_WIDTH_MM:
        errors.append(
            f'Minimaalne saega lõigatav riba on {MIN_STRIP_WIDTH_MM:g} mm. '
            'Alla 4 mm riba soovitame tellida freesist.'
        )
    elif (
        min(inp.detail_width_mm, inp.detail_length_mm) <= NARROW_STRIP_MAX_WIDTH_MM
        and inp.thickness_mm < NARROW_STRIP_MIN_THICKNESS_MM
    ):
        errors.append(
            f'{MIN_STRIP_WIDTH_MM:g}–{NARROW_STRIP_MAX_WIDTH_MM:g} mm riba saab lõigata '
            f'alates {NARROW_STRIP_MIN_THICKNESS_MM:g} mm materjalipaksusest.'
        )
    if inp.detail_count < 1:
        errors.append('Detailide arv peab olema vähemalt 1.')
    elif inp.detail_count > MAX_DETAIL_COUNT:
        errors.append(
            'Ühes päringus saab arvutada kuni 10 000 detaili. '
            'Suurema seeria jaoks koosta eraldi pakkumine.'
        )
    return errors


def _axis_cut_count(piece_count, separates_remainder, trim=True):
    if piece_count <= 0:
        return 0
    return max(0, piece_count - 1) + int(bool(separates_remainder)) + int(bool(trim))


def _partial_layout(count, max_cols, max_rows, piece_w, piece_l, kerf, trim_width, trim_length):
    options = []
    for cols in range(1, min(max_cols, count) + 1):
        rows = math.ceil(count / cols)
        if rows > max_rows:
            continue
        width = trim_width + used_size_mm(cols, piece_w, kerf)
        length = trim_length + used_size_mm(rows, piece_l, kerf)
        options.append({
            'cols': cols,
            'rows': rows,
            'width_mm': width,
            'length_mm': length,
            'area_m2': area_m2(width, length),
            'empty_positions': cols * rows - count,
        })
    if not options:
        return None
    return min(options, key=lambda x: (round(x['area_m2'], 9), x['empty_positions'], x['rows'] + x['cols']))


def _simple_offcuts(raw_w, raw_l, used_w, used_l):
    offcuts = []
    side = max(0.0, raw_w - used_w)
    end = max(0.0, raw_l - used_l)
    if side > 0.01:
        offcuts.append({'name': 'Küljeriba', 'width_mm': side, 'length_mm': raw_l, 'area_m2': area_m2(side, raw_l)})
    if end > 0.01 and used_w > 0:
        offcuts.append({'name': 'Otsajääk', 'width_mm': used_w, 'length_mm': end, 'area_m2': area_m2(used_w, end)})
    return offcuts


def dust_bag_change_count(thickness_mm, stock_count, full_length_ripping):
    """Return required chip-bag changes for long full-length ripping jobs."""
    stock_count = max(0, int(stock_count))
    if not full_length_ripping or thickness_mm < DUST_BAG_STANDARD_MIN_THICKNESS_MM:
        return 0
    if thickness_mm >= DUST_BAG_FAST_MIN_THICKNESS_MM:
        return stock_count // DUST_BAG_FAST_STOCK_INTERVAL
    # 1–8 stocks need no pause; the first change is needed before stock 9.
    return max(0, (stock_count - 1) // DUST_BAG_STANDARD_STOCK_INTERVAL)


def build_orientation_result(blade, inp, detail_w, detail_l):
    if inp.thickness_mm > blade.get('max_single_thickness_mm', blade['max_stack_mm']):
        return None
    narrowest_detail_side = min(inp.detail_width_mm, inp.detail_length_mm)
    if narrowest_detail_side < MIN_STRIP_WIDTH_MM:
        return None
    narrow_strip = narrowest_detail_side <= NARROW_STRIP_MAX_WIDTH_MM
    if narrow_strip and (
        inp.thickness_mm < NARROW_STRIP_MIN_THICKNESS_MM
        or abs(detail_w - narrowest_detail_side) > 0.001
        or detail_l <= NARROW_STRIP_MAX_WIDTH_MM
    ):
        # Kitsas mõõt peab jääma pikisuunas lõigatava riba laiuseks.
        return None
    kerf = blade['kerf_mm']
    base_trim_allowance = kerf + TRIM_REMOVAL_MM
    # Tasandusvaru on vaja ainult suunal, kus detail lõigatakse tooriku
    # mõõdust väiksemaks. Täispikka või täislaiuses detaili sellel teljel ei
    # lõigata ning plaadi olemasolev mõõt jääb puutumata.
    trim_width = base_trim_allowance if detail_w < inp.raw_width_mm - 0.001 else 0.0
    trim_length = base_trim_allowance if detail_l < inp.raw_length_mm - 0.001 else 0.0
    available_w = inp.raw_width_mm - trim_width
    available_l = inp.raw_length_mm - trim_length
    cols = max_pieces_in_length(available_w, detail_w, kerf)
    rows = max_pieces_in_length(available_l, detail_l, kerf)
    capacity = cols * rows
    if capacity <= 0:
        return None

    full_count, remainder_count = divmod(inp.detail_count, capacity)
    extra_count = int(remainder_count > 0)
    stock_count = full_count + extra_count
    if inp.max_stock_count is not None and stock_count > inp.max_stock_count:
        return None

    full_used_w = trim_width + used_size_mm(cols, detail_w, kerf)
    full_used_l = trim_length + used_size_mm(rows, detail_l, kerf)
    partial = _partial_layout(
        remainder_count, cols, rows, detail_w, detail_l, kerf, trim_width, trim_length
    ) if remainder_count else None
    partial_w = partial['width_mm'] if partial else 0.0
    partial_l = partial['length_mm'] if partial else 0.0
    partial_cols = partial['cols'] if partial else 0
    partial_rows = partial['rows'] if partial else 0

    full_long = _axis_cut_count(cols, full_used_w < inp.raw_width_mm - 0.001, trim_width > 0)
    full_cross = _axis_cut_count(rows, full_used_l < inp.raw_length_mm - 0.001, trim_length > 0)
    partial_long = _axis_cut_count(partial_cols, False, trim_width > 0) if partial else 0
    partial_cross = _axis_cut_count(partial_rows, False, trim_length > 0) if partial else 0
    long_total = full_count * full_long + extra_count * partial_long
    cross_total = full_count * full_cross + extra_count * partial_cross

    full_area = area_m2(inp.raw_width_mm, inp.raw_length_mm)
    required_area = full_count * full_area + area_m2(partial_w, partial_l)
    net_area = inp.detail_count * area_m2(detail_w, detail_l)
    calculated_kerf = (
        full_count * (full_long * inp.raw_length_mm * kerf + full_cross * full_used_w * kerf)
        + extra_count * (partial_long * partial_l * kerf + partial_cross * partial_w * kerf)
    ) / 1_000_000.0
    kerf_area = min(max(0.0, required_area - net_area), calculated_kerf)
    losses_area = max(0.0, required_area - net_area)

    spm = get_sec_per_meter(inp.thickness_mm)
    rip_forward_sec = (
        full_count * full_long * inp.raw_length_mm
        + extra_count * partial_long * partial_l
    ) / 1000.0 * spm
    cross_forward_sec = (
        full_count * full_cross * full_used_w
        + extra_count * partial_cross * partial_w
    ) / 1000.0 * spm
    narrow_strip_time_factor = NARROW_STRIP_TIME_FACTOR if narrow_strip else 1.0
    thick_material_time_factor = (
        THICK_MATERIAL_TIME_FACTOR
        if inp.thickness_mm >= THICK_MATERIAL_TIME_FACTOR_START_MM
        else 1.0
    )
    cutting_sec = (
        (rip_forward_sec * narrow_strip_time_factor + cross_forward_sec)
        * (1 + CUT_RETURN_FACTOR)
        * thick_material_time_factor
    )
    base_setup_sec = BASE_SETUP_SEC + (0 if blade['is_default'] else SMALL_BLADE_SWITCH_SEC)
    precision_setup_sec = (
        (PRECISION_SETUP_SEC if inp.precision_cut else 0)
        * narrow_strip_time_factor
        * thick_material_time_factor
    )
    setup_sec = base_setup_sec * narrow_strip_time_factor * thick_material_time_factor + precision_setup_sec
    # Käsitlus on valmis detailide tõstmine otse sae kõrval olevale alusele.
    # 20 s detaili kohta väldib eeldust, et operaator kõnnib iga ribaga eraldi;
    # vähemalt 90 s tooriku kohta jätab alles realistliku plaadi peale-/mahalaadimise.
    handling_base_sec = max(
        stock_count * BASE_HANDLING_PER_STOCK_SEC,
        inp.detail_count * HANDLING_PER_DETAIL_SEC,
    )
    handling_sec = handling_base_sec * narrow_strip_time_factor * thick_material_time_factor
    full_length_ripping = bool(
        long_total > 0
        and cross_total == 0
        and inp.raw_length_mm >= 2000.0
        and abs(detail_l - inp.raw_length_mm) <= 0.001
    )
    bag_change_count = dust_bag_change_count(inp.thickness_mm, stock_count, full_length_ripping)
    bag_change_sec = bag_change_count * DUST_BAG_CHANGE_SEC
    qc_per_detail = quality_control_seconds_per_detail(detail_w, detail_l) if inp.precision_cut else 0
    max_stack_layers = max(1, math.floor(blade['max_stack_mm'] / inp.thickness_mm))
    full_stack_batches = math.ceil(full_count / max_stack_layers) if full_count else 0
    # Sama asukohaga ribad lõigatakse plaadipakis koos ja moodustavad ühe
    # kontrollühiku. Eraldi lisajäägi detailid on üksikud kontrollühikud.
    inspection_units = full_stack_batches * capacity + remainder_count
    qc_check_count = quality_control_check_count(inp.detail_count, inspection_units) if inp.precision_cut else 0
    qc_sec = qc_per_detail * qc_check_count
    total_sec = setup_sec + cutting_sec + handling_sec + bag_change_sec + qc_sec
    normal_work_sec = total_sec - precision_setup_sec - qc_sec
    small_precision_fixed_price = bool(
        inp.precision_cut
        and inp.detail_count <= SMALL_PRECISION_MAX_COUNT
        and area_m2(inp.detail_width_mm, inp.detail_length_mm) < SMALL_PRECISION_MAX_DETAIL_AREA_M2
    )
    normal_billable_sec = quote_billable_seconds(normal_work_sec)
    total_billable_sec = quote_billable_seconds(total_sec)
    normal_quote_fee = normal_billable_sec / 3600.0 * SAW_HOURLY_RATE_EUR
    work_fee = total_billable_sec / 3600.0 * SAW_HOURLY_RATE_EUR
    if small_precision_fixed_price:
        # 20 € on miinimumlisatasu, mitte hinnalagi: täppisseadistus ja kontroll
        # ei tohi muuta müüdud tööd kahjumlikuks.
        work_fee = max(work_fee, normal_quote_fee + SMALL_PRECISION_SURCHARGE_EUR)
        total_billable_sec = work_fee / SAW_HOURLY_RATE_EUR * 3600.0
    precision_surcharge_eur = max(0.0, work_fee - normal_quote_fee) if inp.precision_cut else 0.0

    full_offcuts = _simple_offcuts(inp.raw_width_mm, inp.raw_length_mm, full_used_w, full_used_l)
    usable_offcut_area = sum(o['area_m2'] for o in full_offcuts) * full_count
    rotation_over_1m = bool(max(inp.detail_width_mm, inp.detail_length_mm) > ROTATION_PREFERRED_MAX_MM and detail_w != inp.detail_width_mm)
    return {
        'blade': blade,
        'thickness_mm': inp.thickness_mm,
        'trim_edges': True,
        'trim_allowance_mm': base_trim_allowance,
        'trim_width_allowance_mm': trim_width,
        'trim_length_allowance_mm': trim_length,
        'trim_removal_mm': TRIM_REMOVAL_MM,
        'precision_cut': inp.precision_cut,
        'stock_source': inp.stock_source,
        'raw_width_mm': inp.raw_width_mm,
        'raw_length_mm': inp.raw_length_mm,
        'original_detail_width_mm': inp.detail_width_mm,
        'original_detail_length_mm': inp.detail_length_mm,
        'detail_width_mm': detail_w,
        'detail_length_mm': detail_l,
        'detail_count': inp.detail_count,
        'across': cols,
        'along': rows,
        'pieces_per_sheet': capacity,
        'full_sheet_count': full_count,
        'partial_sheet_count': extra_count,
        'partial_piece_count': remainder_count,
        'partial_cols': partial_cols,
        'partial_rows': partial_rows,
        'partial_stock_width_mm': partial_w,
        'partial_stock_length_mm': partial_l,
        'opened_sheet_count': stock_count,
        'opened_material_area_m2': required_area,
        'opened_sheet_area_m2': required_area,
        'material_needed_area_m2': required_area,
        'net_detail_area_m2': net_area,
        'kerf_area_m2': kerf_area,
        'loss_area_m2': losses_area,
        'consumed_area_m2': required_area,
        'material_billable_area_m2': required_area,
        'usable_offcut_area_m2': usable_offcut_area,
        'non_usable_offcut_area_m2': max(0.0, losses_area - usable_offcut_area),
        'full_offcuts': full_offcuts,
        'partial_offcuts': [],
        'largest_usable_offcut': max(full_offcuts, key=lambda o: o['area_m2']) if full_offcuts and full_count else None,
        'largest_any_offcut': max(full_offcuts, key=lambda o: o['area_m2']) if full_offcuts and full_count else None,
        'longitudinal_cut_count': long_total,
        'cross_cut_count': cross_total,
        'total_cut_count': long_total + cross_total,
        'cutting_time_sec': cutting_sec,
        'setup_sec': setup_sec,
        'precision_setup_sec': precision_setup_sec,
        'handling_sec': handling_sec,
        'handling_base_sec': handling_base_sec,
        'handling_sec_per_detail': HANDLING_PER_DETAIL_SEC,
        'narrow_strip_time_factor': narrow_strip_time_factor,
        'thick_material_time_factor': thick_material_time_factor,
        'full_length_ripping': full_length_ripping,
        'dust_bag_change_count': bag_change_count,
        'dust_bag_change_sec': bag_change_sec,
        'quality_control_sec_per_detail': qc_per_detail,
        'quality_control_check_count': qc_check_count,
        'quality_control_unit_count': inspection_units,
        'max_stack_layers': max_stack_layers,
        'full_stack_batch_count': full_stack_batches,
        'quality_control_sec': qc_sec,
        'small_precision_fixed_price': small_precision_fixed_price,
        'precision_surcharge_eur': precision_surcharge_eur,
        'total_sec': total_sec,
        'billable_sec': total_billable_sec,
        'quote_buffer_sec': max(0.0, total_billable_sec - total_sec),
        'quote_buffer_rate': QUOTE_BUFFER_RATE,
        'quote_rounding_sec': QUOTE_ROUNDING_SEC,
        'hourly_rate_eur': SAW_HOURLY_RATE_EUR,
        'estimated_work_cost_eur': work_fee,
        'work_fee_eur': work_fee,
        'material_price_m2_eur': 0.0,
        'material_cost_eur': 0.0,
        'total_estimated_cost_eur': work_fee,
        'rotation_over_1m': rotation_over_1m,
        'warning': ' '.join(filter(None, (
            '4–6 mm pikisuunalise riba korral on seadistus, ribastamine ja detailide käsitlus arvestatud 2× ajaga.'
            if narrow_strip else None,
            'Alates 80 mm materjalipaksusest on seadistus, lõikamine ja käsitlus arvestatud 2× ajaga.'
            if thick_material_time_factor > 1 else None,
            f'Lisatud {bag_change_count} laastukottide vahetust, kokku {round(bag_change_sec / 60)} minutit.'
            if bag_change_count else None,
        ))) or None,
        'ml_predicted_actual_time_sec': None,
    }


def result_sort_key(result):
    return (
        round(result['material_needed_area_m2'], 6),
        result['full_sheet_count'],
        int(result.get('rotation_over_1m', False)),
        result['total_sec'],
        result['total_cut_count'],
        0 if result['blade']['is_default'] else 1,
    )


def result_sort_key_ml(result):
    predicted = result.get('ml_predicted_actual_time_sec') or result['total_sec']
    return (
        round(result['material_needed_area_m2'], 6),
        result['full_sheet_count'],
        int(result.get('rotation_over_1m', False)),
        predicted,
        result['total_cut_count'],
    )


def choose_best_orientation_result(results):
    valid = [r for r in results if r is not None]
    return min(valid, key=result_sort_key) if valid else None


def choose_best_result(results):
    valid = [r for r in results if r is not None]
    if not valid:
        return None
    large = next((r for r in valid if r['blade']['is_default']), None)
    small = next((r for r in valid if not r['blade']['is_default']), None)
    if large is None:
        return small
    if small is None:
        return large
    area_save = large['material_needed_area_m2'] - small['material_needed_area_m2']
    if area_save >= MIN_MATERIAL_AREA_SAVING_M2:
        return small
    if area_save <= -MIN_MATERIAL_AREA_SAVING_M2:
        return large
    return small if large['total_sec'] - small['total_sec'] >= MIN_SMALL_BLADE_TIME_SAVING_SEC else large


def choose_best_result_ml(results):
    valid = [r for r in results if r is not None]
    return min(valid, key=result_sort_key_ml) if valid else None


def build_best_result_for_blade(blade, inp):
    normal = build_orientation_result(blade, inp, inp.detail_width_mm, inp.detail_length_mm)
    rotated = build_orientation_result(blade, inp, inp.detail_length_mm, inp.detail_width_mm)
    if normal:
        normal['rotated'] = False
    if rotated:
        rotated['rotated'] = True
    return choose_best_orientation_result([normal, rotated])


def build_best_result(inp):
    return choose_best_result([
        build_best_result_for_blade(blade, inp)
        for blade in BLADES
    ])


def apply_monotonic_quote_floor(result, inp):
    """Ensure a larger quantity cannot receive a lower total sales price."""
    if result is None:
        return None
    highest_operational_sec = result['total_sec']
    for detail_count in range(1, inp.detail_count):
        candidate = build_best_result(replace(inp, detail_count=detail_count))
        if candidate is not None:
            highest_operational_sec = max(highest_operational_sec, candidate['total_sec'])
    floor_billable_sec = quote_billable_seconds(highest_operational_sec)
    result['billable_sec'] = max(result['billable_sec'], floor_billable_sec)
    result['work_fee_eur'] = result['billable_sec'] / 3600.0 * SAW_HOURLY_RATE_EUR
    result['estimated_work_cost_eur'] = result['work_fee_eur']
    result['total_estimated_cost_eur'] = result['work_fee_eur']
    result['quote_buffer_sec'] = max(0.0, result['billable_sec'] - result['total_sec'])
    result['quote_floor_basis_sec'] = highest_operational_sec
    return result


def max_single_stock_capacity(inp):
    """Return the best capacity of one physical stock across blades and orientations."""
    probe = replace(inp, detail_count=1, max_stock_count=1)
    results = []
    for blade in BLADES:
        results.append(build_orientation_result(blade, probe, probe.detail_width_mm, probe.detail_length_mm))
        results.append(build_orientation_result(blade, probe, probe.detail_length_mm, probe.detail_width_mm))
    return max((result['pieces_per_sheet'] for result in results if result), default=0)


def add_blade_reasons(results, best):
    for result in results:
        if result is None:
            continue
        result['blade_reason'] = (
            ('Soovitatud' if result is best else 'Alternatiiv')
            + f": lõikelaius {result['blade']['blade']}, materjalikulu {result['material_needed_area_m2']:.3f} m², "
            + f"tööaeg {round(result['total_sec'] / 60)} min."
        )
