def parse_float_text(text, default=0.0):
    try:
        return float(str(text).strip().replace(',', '.'))
    except (ValueError, TypeError):
        return default


def parse_positive_optional_float_text(text, field_name):
    normalized = str(text).strip().replace(',', '.') if text is not None else ''
    if not normalized:
        return None
    try:
        value = float(normalized)
    except (ValueError, TypeError) as exc:
        raise ValueError(f'{field_name} peab olema number.') from exc
    if value <= 0:
        raise ValueError(f'{field_name} peab olema suurem kui 0.')
    return value


def parse_nonnegative_optional_float_text(text, field_name):
    normalized = str(text).strip().replace(',', '.') if text is not None else ''
    if not normalized:
        return None
    try:
        value = float(normalized)
    except (ValueError, TypeError) as exc:
        raise ValueError(f'{field_name} peab olema number.') from exc
    if value < 0:
        raise ValueError(f'{field_name} ei tohi olla negatiivne.')
    return value


def sec_to_minsec(seconds):
    if seconds is None:
        return '—'
    total = int(round(seconds))
    minutes, sec = divmod(abs(total), 60)
    return f"{'-' if total < 0 else ''}{minutes} min {sec:02d} sek"


def fmt(value, decimals=2, unit=''):
    if value is None:
        return '—'
    text = f'{value:,.{decimals}f}'.replace(',', ' ').replace('.', ',')
    return f'{text} {unit}'.strip()


def dimension_text(value):
    value = float(value or 0)
    return str(int(round(value))) if abs(value - round(value)) < 0.01 else f'{value:.1f}'.replace('.', ',')


def material_need_lines(result):
    if result.get('stock_source') == 'Jääk':
        return [
            'Sisestatud jääk — '
            f"{dimension_text(result['raw_width_mm'])} × {dimension_text(result['raw_length_mm'])} mm"
        ]
    lines = []
    count = int(result.get('full_sheet_count', 0))
    if count:
        lines.append(f"{count} täisplaat — {dimension_text(result['raw_width_mm'])} × {dimension_text(result['raw_length_mm'])} mm")
    if result.get('partial_sheet_count'):
        lines.append(
            'Sobiva jäägi minimaalne mõõt — '
            f"{dimension_text(result['partial_stock_width_mm'])} × {dimension_text(result['partial_stock_length_mm'])} mm"
        )
    return lines or ['Materjal ei ole määratud']


def opened_material_label(result):
    return ' + '.join(material_need_lines(result))


def offcut_label(offcut):
    if not offcut:
        return '—'
    return f"{offcut['name']}: {dimension_text(offcut['width_mm'])} × {dimension_text(offcut['length_mm'])} mm"


def work_order_steps(result):
    """Build the same operator sequence for the screen and printable cut sheet.

    Lõikejärjekord sõltub valitud strateegiast:
      - 'cross' (jäägisäästlik, kui detail on plaadist lühem): esmalt lõigatakse
        detail pikkusesse (täislaiune ristlõige, mis jätab kasutatava otsajäägi),
        alles siis ribastatakse. Nii kulub materjali kokkuhoidlikult ja alles
        jääv otsajääk on terve, taaskasutatav tükk.
      - 'rip' (kui detail on täispikk või ribastamine jätab suurema jäägi):
        esmalt pikilõiked, seejärel ristlõiked mõõtu.
    """
    strategy = result.get('cut_strategy', 'rip')
    has_cross = result.get('cross_cut_count', 0) > 0
    steps = ['Tee tasanduslõige ainult skeemil näidatud lõikesuunal.']
    if result.get('rotated'):
        steps.append('Kasuta skeemil näidatud 90° pööratud detailipaigutust.')
    if strategy == 'cross' and has_cross:
        steps.append(
            'Lõika detail esmalt pikkusesse: tee üks täislaiune ristlõige, et suur '
            'otsajääk eralduks tervikuna ja jääks taaskasutatavaks.'
        )
        steps.append('Ribasta seejärel lõigatud plaadiosa pikisuunas mõõtu.')
    else:
        steps.append('Lõika esmalt pikisuunalised ribad.')
        if has_cross:
            steps.append('Pööra ribad 90° ja tee ristlõiked mõõtu.')
    steps.append(
        'Too alus või käru sae juurde, sea see sobivale töökõrgusele ja tõsta valmis detailid otse alusele.'
    )
    if result.get('partial_sheet_count') and result.get('stock_source') != 'Jääk':
        steps.append('Enne täisplaadi lõikust kontrolli, kas sobivat jääki pole riiulis või boksides.')
    if result.get('dust_bag_change_count'):
        steps.append(
            f"Vaheta täispikal ribastamisel laastukotte {result['dust_bag_change_count']} korda; "
            'arvestuslikult 10 minutit vahetuse kohta.'
        )
    return steps
