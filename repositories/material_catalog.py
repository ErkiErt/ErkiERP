import csv
import re
from functools import lru_cache
from pathlib import Path


# Andmefail on projekti juurkataloogis; repository elab alampaketis, seega
# viitame ühe taseme võrra ülespoole.
CATALOG_FILE = Path(__file__).resolve().parent.parent / 'plastmaterjalid_sae_app.csv'
MAX_UNINTERRUPTED_CUT_MM = 3800.0
MAX_SUPPORTED_THICKNESS_MM = 95.0

UNSUPPORTED_NAME_PATTERNS = (
    r'\bDIBOND\b',
    r'\bACP\b',
    r'\bCEM[- ]?1\b',
    r'TEKSTOLIIT',
    r'\bDURASTONE\b',
    r'PINNAKAITSEMATT',
    r'^VÕRK$',
    r'RULLMATERJAL',
    r'\d\s*M(?:\s|$)',
    r'\b(?:PE|PTFE|PA6E)\s+KILE\b',
    r'VAHT',
    r'\bFOAM\b',
    r'VIBRAFOAM',
    r'SIMOPOR',
    r'FOREX',
    r'COPLAST',
    r'TERMOLON',
    r'KIHTPLAST',
    r'\bSTEPISOL',
    r'\bPLASTVIL\b',
    r'\bDAMTEC\b',
    r'DEFEKT',
)


def _number(value):
    try:
        return float(str(value).strip().replace(',', '.'))
    except (TypeError, ValueError):
        return None


def _number_text(value):
    value = float(value)
    if abs(value - round(value)) < 0.001:
        return str(int(round(value)))
    return f'{value:g}'.replace('.', ',')


def _dimensions_from_name(article_name):
    """Recover an unambiguous thickness x width x length triple from a name."""
    match = re.search(
        r'(?<![A-Z0-9])'
        r'(\d+(?:[.,]\d+)?)\s*(?:MM)?\s*[X×]\s*'
        r'(\d+(?:[.,]\d+)?)\s*(?:MM)?\s*[X×]\s*'
        r'(\d+(?:[.,]\d+)?)\s*(?:MM)?',
        article_name.upper(),
    )
    if not match:
        return None
    values = tuple(_number(value) for value in match.groups())
    if any(value is None or value <= 0 for value in values):
        return None
    thickness, width, length = values
    if thickness > MAX_SUPPORTED_THICKNESS_MM:
        return None
    return thickness, *sorted((width, length))


def _is_supported_article(group, article_name):
    name = article_name.upper().strip()
    if any(re.search(pattern, name) for pattern in UNSUPPORTED_NAME_PATTERNS):
        return False
    # Standard Booksi vanades nimetustes ei ole kõigil Makroloni õõneslehtedel
    # sõna "kihtplast". 2100 × 6000 mm Makroloni read on kokkulepitud
    # täisplastlehtede valikust väljas; õõnespaneelina jääb ainult Paneltim.
    if 'MAKROLON' in name and '6000' in name:
        return False
    # PE-gruppi sattunud NR-kumm, mitte PET-i Axpet NR pinnatähis.
    if group == 'PE' and re.match(r'^NR\s+\d', name):
        return False
    return True


def _canonical_group(group, article_name):
    name = article_name.upper()
    if 'PANELTIM' in name:
        return 'Õõnespaneel'
    if re.search(r'\bPMMA\b|\bPLEXIGLAS\b', name):
        return 'PMMA'
    if re.search(r'\bPETP\b|\bPET[- ]?P\b', name):
        return 'PET'
    return group


def _with_cast_modifier(base, name):
    if re.search(r'\bOIL\b|\bLFX\b', name):
        return f'{base} + Oil'
    if re.search(r'MO\s*S?2|MOS2|NYLATRON\s+GSM', name):
        return f'{base} + MoS₂'
    return base


def _exact_material_name(group, material, article_name):
    """Return a canonical, user-facing material grade without guessing unknowns."""
    name = article_name.upper().strip()
    source = material.upper().strip()

    if group == 'Õõnespaneel':
        if re.search(r'\bPE\s+PRIME\b', name):
            return 'Paneltim PE'
        if re.search(r'\bPP[- ]?C\b', name):
            return 'Paneltim PP-C'
        return 'Paneltim PP'

    if group == 'PE':
        if 'PE1000' in name or source == 'PE1000':
            return 'PE1000 (PE-UHMW)'
        if re.search(r'\bPE500\b', name) or source == 'PE500':
            return 'PE500 (PE-HMW)'
        if re.search(r'\bPE300\b', name) or source == 'PE300':
            return 'PE300 (PE-HD)'
        if re.search(r'\bPE100\b', name):
            return 'PE100 (PE-HD)'
        if 'LDPE' in name or re.search(r'\bPE[- ]L\b', name):
            return 'PE-L / PE-LD'
        if re.search(r'PE\s+VAHT', name):
            return 'PE vaht'
        return 'PE'

    if group == 'PA':
        if re.search(r'\bPA\s*6[.]6\b|\bPA\s*66\b', name) or source in {'PA6.6', 'PA66'}:
            return 'PA66'
        is_cast = bool(re.search(
            r'\bPA\s*6G\b|\bCAST\b|ZELLAMI{1,2}D\s*1100|ERTALON\s*(?:6\s*PLA|LFX)|NYLATRON\s*GSM',
            name,
        ))
        if is_cast:
            return _with_cast_modifier('PA6-C / PA6-G', name)
        is_extruded = bool(re.search(r'\bPA\s*6E\b|\bEXT\b|ERTALON\s*6\s*SA', name))
        if is_extruded:
            base = 'PA6-E'
            return f'{base} + MoS₂' if re.search(r'MO\s*S?2|MOS2', name) else base
        if re.search(r'\bPA\s*6\b', name) or source == 'PA6':
            suffix = ' + MoS₂' if re.search(r'MO\s*S?2|MOS2', name) else ''
            return f'PA6{suffix}'
        return 'PA'

    if group == 'POM':
        if re.search(r'\bPOM[- ]?H\b', name):
            return 'POM-H'
        if 'POM-ELS' in name or re.search(r'\bPOM\s+ELS\b', name):
            return 'POM-C ELS'
        if re.search(r'\bPOM[- ]?ESD\b', name):
            return 'POM-ESD'
        if re.search(r'\bPOM[- ]?C\b', name):
            return 'POM-C'
        if re.search(r'\bPOM\s+LF\b', name):
            return 'POM-LF'
        return 'POM'

    if group == 'PET':
        if re.search(r'\bPET[- ]?G\b|\bPETG\b', name):
            return 'PET-G'
        if re.search(r'\bPET[- ]?P\b|\bPETP\b', name):
            return 'PET (PET-P)'
        return 'PET'

    if group == 'PP':
        if re.search(r'\bPP[- ]?H\b|400PPH', name):
            return 'PP-H'
        if re.search(r'\bPP[- ]?C\b', name):
            return 'PP-C'
        if re.search(r'\bPP[- ]?S\b', name):
            return 'PP-S'
        return 'PP'

    if group == 'PVC':
        if re.search(r'\bPVC[- ]?U\b', name):
            return 'PVC-U'
        if re.search(r'VAHT|FOAM|FOREX', name):
            return 'PVC vaht'
        return 'PVC'

    if group == 'PMMA':
        if re.search(r'\bXT\b', name):
            return 'PMMA-XT'
        if re.search(r'\bGS\b', name):
            return 'PMMA-GS'
        return 'PMMA'

    if group == 'PC':
        return 'PC (tehniline polükarbonaat)'

    return material


def _display_group(canonical_group, exact_material):
    """Group distinct polymers by the practical product categories used in the UI."""
    if canonical_group == 'Õõnespaneel':
        return canonical_group
    if canonical_group in {'PA', 'POM', 'PU'}:
        return 'Kulumiskindel plast'
    if exact_material.startswith(('PE500 ', 'PE1000 ')) or exact_material == 'PET (PET-P)':
        return 'Kulumiskindel plast'
    if canonical_group in {'ABS', 'PE', 'PP', 'PVC'}:
        return 'Konstruktsioonplast'
    if canonical_group in {'PTFE', 'PVDF'}:
        return 'Fluoroplast'
    if canonical_group in {'PC', 'PMMA', 'PS'} or exact_material in {'PET-G', 'PET'}:
        return 'Läbipaistev plast'
    if canonical_group == 'PEEK':
        return 'Eriotstarbelised plastid'
    return 'Eriotstarbelised plastid'


@lru_cache(maxsize=1)
def load_sheet_catalog():
    rows = []
    with CATALOG_FILE.open('r', encoding='utf-8-sig', newline='') as handle:
        for source in csv.DictReader(handle):
            if source.get('form', '').strip().lower() != 'leht':
                continue
            if source.get('is_remnant', '').strip().lower() == 'jah':
                continue
            group = source.get('group', '').strip()
            material = source.get('material', '').strip()
            article_name = source.get('article_name', '').strip()
            if not _is_supported_article(group, article_name):
                continue
            group = _canonical_group(group, article_name)
            material = _exact_material_name(group, material, article_name)
            group = _display_group(group, material)
            thickness = _number(source.get('thickness_mm'))
            width = _number(source.get('width_mm'))
            length = _number(source.get('length_mm'))
            recovered = _dimensions_from_name(article_name)
            if recovered and (
                thickness is None
                or not 0 < thickness <= MAX_SUPPORTED_THICKNESS_MM
                or width is None
                or length is None
            ):
                thickness, width, length = recovered
            # Standard Booksi ekspordis on osal vigastel ridadel plaadi laius
            # (nt 1000/1250/2050 mm) paksuse veergu nihkunud. Kalkulaatori
            # töövahemik on kuni 90 mm, seega ei tohi neid paksusena kuvada.
            if (
                not group
                or not material
                or thickness is None
                or not 0 < thickness <= MAX_SUPPORTED_THICKNESS_MM
            ):
                continue
            if width and length and width > 0 and length > 0:
                width, length = sorted((width, length))
            else:
                width = length = None
            rows.append({
                'article_code': source.get('article_code', '').strip(),
                'group': group,
                'material': material,
                'thickness_mm': thickness,
                'width_mm': width,
                'length_mm': length,
                'color': source.get('color', '').strip(),
                'variant': source.get('variant', '').strip(),
                'article_name': article_name,
            })
    return tuple(rows)


def _has_usable_sheet_format(row):
    return (
        row['width_mm'] is not None
        and sheet_compatibility(row['width_mm'], row['length_mm']) == 'direct'
    )


def groups(require_format=False):
    return sorted({
        row['group'] for row in load_sheet_catalog()
        if not require_format or _has_usable_sheet_format(row)
    }, key=str.casefold)


def materials_for_group(group, require_format=False):
    return sorted(
        {
            row['material'] for row in load_sheet_catalog()
            if row['group'] == group and (not require_format or _has_usable_sheet_format(row))
        },
        key=str.casefold,
    )


def thicknesses_for_material(group, material, require_format=False):
    return sorted({
        row['thickness_mm'] for row in load_sheet_catalog()
        if (
            row['group'] == group
            and row['material'] == material
            and (not require_format or _has_usable_sheet_format(row))
        )
    })


def sheet_compatibility(width_mm, length_mm):
    short, long = sorted((float(width_mm), float(length_mm)))
    if short > MAX_UNINTERRUPTED_CUT_MM:
        return 'incompatible'
    if long > MAX_UNINTERRUPTED_CUT_MM:
        return 'precut'
    return 'direct'


def formats_for_selection(group, material, thickness_mm):
    formats = {}
    for row in load_sheet_catalog():
        if row['group'] != group or row['material'] != material:
            continue
        if row['thickness_mm'] != thickness_mm or row['width_mm'] is None:
            continue
        width, length = row['width_mm'], row['length_mm']
        status = sheet_compatibility(width, length)
        if status != 'direct':
            continue
        key = f'{width:g}|{length:g}'
        formats[key] = {
            'key': key,
            'width_mm': width,
            'length_mm': length,
            'status': status,
            'label': (
                f'{_number_text(width)} × {_number_text(length)} mm — '
                + ('otse lõigatav' if status == 'direct' else 'vajab eellõiget')
            ),
        }
    return sorted(formats.values(), key=lambda item: (item['width_mm'] * item['length_mm'], item['width_mm'], item['length_mm']))


def articles_for_selection(group, material, thickness_mm, width_mm=None, length_mm=None):
    matches = []
    wanted_size = None if width_mm is None else tuple(sorted((float(width_mm), float(length_mm))))
    for row in load_sheet_catalog():
        if row['group'] != group or row['material'] != material or row['thickness_mm'] != thickness_mm:
            continue
        if wanted_size and (row['width_mm'], row['length_mm']) != wanted_size:
            continue
        matches.append(row)
    return matches


def thickness_label(value):
    return f'{_number_text(value)} mm'
