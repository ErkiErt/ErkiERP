"""Pakkimisjuhise domeeniloogika (Faas C).

Arvutab tootmistöölise jaoks SISEMISE pakkimissoovituse: kas tellimuse detailid
pakitakse lainepapikasti (väiksed/kompaktsed detailid) või ribadena kimpu/alusele
(piklikud „riba"-detailid). Loogika on puhas (ei sõltu Streamlitist ega
esitluskihist) ja tagastab struktureeritud plaani, mille sõnastab eesti keelde
esitluskiht (``utils.packing_instruction_lines``).

NB: pakkimisaega/kulu EI lisata kliendi hinnapakkumisse — see on eraldiseisev
tootmisjuhis.

Dokumenteeritud eeldused (kokku võetud ka failis ``SUMMARY_FAAS_C.md``):
  * Kasti mahutavus on hinnatud RUUMALA baasil + turvavaru, kuna täpne 3D
    ladumisalgoritm ei kuulu selle faasi ulatusse.
  * Turvavaru ladumise ebaefektiivsuse jaoks on 20% (spetsis lubatud 15–20%).
  * Alla 1000 mm ribade „lihtsa pakkimise" aeg on eeldatud sama kui kimbul
    (120 sek ots), kuna eraldi aega ei antud.
  * 1020–1200 mm ribadele rakendame lihtsuse huvides alusepakkimist (nagu
    >1200 mm), kuna vahemikule eraldi reeglit ei antud.
"""

import math
from dataclasses import dataclass
from itertools import permutations


@dataclass(frozen=True)
class Box:
    """Üks lainepapikast. Mõõdud on SISEMÕÕDUD (L×W×H mm), hind KM-ga (€)."""

    name: str
    length_mm: float
    width_mm: float
    height_mm: float
    price_eur: float

    @property
    def volume_l(self):
        return self.length_mm * self.width_mm * self.height_mm / 1_000_000.0

    @property
    def sorted_dims_mm(self):
        # Kahanevas suurusjärjestuses, et võrrelda detaili mahtumist mistahes
        # orientatsioonis (pikim detaili külg pikima kasti külje vastu jne).
        return tuple(sorted((self.length_mm, self.width_mm, self.height_mm), reverse=True))


# Lainepapikastid (sisemõõdud L×W×H mm, hind KM-ga €). Hinnad on Exceli
# "Kek +KM" veerust (kasutaja täpsustus: „kek nimelise rea hindadega"), mitte
# Tehpacki veerust. Kasti 5 (440×310×270/320) "Kek +KM" lahter oli algandmestikus
# TÜHI — arvutasime selle olemasolevast "Kek" hinnast (1.29 €), korrutades sama
# KM-teguriga, mis kehtib teistel ridadel (Kek+KM / Kek ≈ 1.22, st ~22% KM):
# 1.29 × 1.22 ≈ 1.5738 €. See on dokumenteeritud eeldus (vt SUMMARY_FAAS_C.md).
# Kasti 5 kõrgus on tegelikult 270–320 mm; mahutavuse arvutuses kasutame
# turvalisemat 270 mm, et mitte üle hinnata mahutavust.
BOX_CATALOG = (
    Box('200×150×120', 200, 150, 120, 1.22),
    Box('350×250×200', 350, 250, 200, 1.0248),
    Box('360×250×250', 360, 250, 250, 1.0248),
    Box('400×300×220', 400, 300, 220, 1.22),
    Box('440×310×270', 440, 310, 270, 1.5738),  # arvutatud (Kek 1.29 × 1.22)
    Box('590×380×250', 590, 380, 250, 1.7812),
    Box('590×380×400', 590, 380, 400, 2.1228),
)

# Aluse hinnad (KM-ga €). Täisalus = EUR-alus (riba pikkus >1020 mm → alusele);
# poolik euraalus = kolme suurima kasti soovitus.
FULL_PALLET_PRICE_EUR = 6.00
HALF_PALLET_PRICE_EUR = 4.00

# Ladumise ebaefektiivsuse turvavaru: reaalselt ei saa kasti sisemahtu 100%
# täita (õhuvahed, detailide jäik kuju). Kasutame 20% varu (spetsis lubatud
# 15–20% vahemik) — st kasutatav ruumala on 80% kasti sisemahust.
BOX_PACKING_SAFETY_MARGIN = 0.20

# Kasti kokkupaneku aeg: fikseeritud 30 sek, ÜKS KORD kasti kohta (mitte per
# toorik). Detaili sisestamise aega spetsis ei antud, seega ajahinnang katab
# ainult kastide kokkupaneku.
BOX_ASSEMBLY_SEC = 30

# Riba = piklik detail: pikim külg vähemalt 5× lühim külg (lihtne mõõdupõhine
# heuristika, ilma keeruka kujutuvastuseta).
STRIP_LENGTH_TO_WIDTH_RATIO = 5.0

# Riba pikkuse läviväärtused (mm). Alus (palett) rakendub üldiselt alates
# pikkusest ≥1000 mm ja laiusest ≥20 mm; lihtsuse huvides rakendame
# alusepakkimist alates pikkusest >1020 mm (katab ka 1020–1200 mm vahemiku).
STRIP_PALLET_MIN_LENGTH_MM = 1020.0
# Lihtne kilepakkimine: lühike ja kitsas riba väikeses koguses.
STRIP_SIMPLE_MAX_LENGTH_MM = 1000.0
STRIP_SIMPLE_MAX_WIDTH_MM = 20.0
STRIP_SIMPLE_MAX_COUNT = 20  # täpset kogusepiiri ei antud → ligikaudne ~20 tk

# Kimbu ergonoomilised piirid. 600 mm on käsitsi tõstmise MAX kõrgus: kui virn
# ületaks selle antud koguse/paksuse juures, jagame mitmeks väiksemaks kimbuks.
BUNDLE_MAX_WIDTH_MM = 500.0
BUNDLE_MAX_HEIGHT_MM = 600.0

# Ajad (sek).
STRIP_END_WRAP_SEC = 120  # 120 sek ühe otsa kohta; kimbul 2 otsa = 240 sek
STRIP_PALLET_SEC = 10  # kiire, kuna alus on juba tootmiskoha juures


def boxes_by_volume_desc():
    """Kastid ruumala järgi kahanevalt (suurim ees)."""
    return sorted(BOX_CATALOG, key=lambda box: box.volume_l, reverse=True)


def three_largest_boxes():
    """Kolm suurimat kasti ruumala järgi — nende puhul soovita poolik euraalus."""
    return boxes_by_volume_desc()[:3]


def catalog_max_box_dimension_mm():
    """Suurima kasti pikim sisemõõt kataloogis (dünaamiliselt, mitte hardcode'itud).

    Kui detaili pikim mõõt seda ületab, ei mahu detail ühtegi kasti — sel juhul
    rakendub alati riba-loogika, sõltumata pikkuse/laiuse suhtest.
    """
    return max(
        max(box.length_mm, box.width_mm, box.height_mm)
        for box in BOX_CATALOG
    )


def detail_fits_in_box(detail_w, detail_l, detail_thickness, box):
    """Kas üks detail mahub kasti (mõõdupõhine, mistahes orientatsioonis)?"""
    part = sorted((detail_w, detail_l, detail_thickness), reverse=True)
    return all(p <= b + 1e-6 for p, b in zip(part, box.sorted_dims_mm))


def dimensional_capacity(detail_w, detail_l, detail_thickness, box):
    """Mitu detaili mahub kasti puhtalt telgjoondatud ladumisel (parim orientatsioon).

    Proovib kõik detaili 6 orientatsiooni kasti mõõtude vastu ja tagastab suurima
    ruudustiku-mahutavuse (mm-täpne). See on ülempiir, mida ruumala-hinnang ei
    tohi ületada (nt paks detail, mida ei saa lõputult virnastada).
    """
    dims = (float(detail_w), float(detail_l), float(detail_thickness))
    box_dims = (box.length_mm, box.width_mm, box.height_mm)
    best = 0
    for perm in set(permutations(dims)):
        if all(p <= b + 1e-6 for p, b in zip(perm, box_dims)) and all(p > 0 for p in perm):
            count = 1
            for p, b in zip(perm, box_dims):
                count *= int((b + 1e-6) // p)
            best = max(best, count)
    return best


def box_capacity(detail_w, detail_l, detail_thickness, box):
    """Detailide arv ühes kastis: ruumala + turvavaru, piiratud mõõdupõhise mahuga.

    Ruumala-hinnang (80% sisemahust) annab tiheda pakkimise ligikaudse arvu;
    mõõdupõhine ``dimensional_capacity`` on füüsiline ülempiir. Võtame nende
    miinimumi, et arvutus jääks matemaatiliselt korrektseks (ei ületa reaalset
    mahtu). Kui detail mahub kasti mõõtmeliselt, on mahutavus vähemalt 1.
    """
    if not detail_fits_in_box(detail_w, detail_l, detail_thickness, box):
        return 0
    detail_vol_l = detail_w * detail_l * detail_thickness / 1_000_000.0
    if detail_vol_l <= 0:
        return 0
    usable = box.volume_l * (1 - BOX_PACKING_SAFETY_MARGIN)
    volume_based = int(usable // detail_vol_l)
    dimensional = dimensional_capacity(detail_w, detail_l, detail_thickness, box)
    return max(1, min(volume_based, dimensional))


def _box_plan(box, box_count, capacity, count):
    # Poolik euraalus soovitatakse, kui valitud kast on üks kolmest suurimast.
    recommend_pallet = box in three_largest_boxes()
    box_line_total = round(box.price_eur * box_count, 4)
    pallet_price = HALF_PALLET_PRICE_EUR if recommend_pallet else 0.0
    return {
        'method': 'box',
        'box': box,
        'box_name': box.name,
        'box_count': box_count,
        'capacity_per_box': capacity,
        'recommend_pallet': recommend_pallet,
        'assembly_sec': BOX_ASSEMBLY_SEC * box_count,
        'estimated_sec': BOX_ASSEMBLY_SEC * box_count,
        'detail_count': count,
        # Hinnad (SISEMINE tootmisjuhis, EI lähe kliendi hinnapakkumisse).
        'packaging_label': f'Kast {box.name} mm',
        'packaging_unit_price_eur': box.price_eur,
        'packaging_count': box_count,
        'packaging_line_total_eur': box_line_total,
        'pallet_kind': 'half' if recommend_pallet else None,
        'pallet_price_eur': pallet_price,
        'packaging_total_eur': round(box_line_total + pallet_price, 4),
    }


def select_box(detail_w, detail_l, detail_thickness, count):
    """Vali väikseim kast, kuhu kogu tellimus mahub; muidu suurim + mitu kasti.

    Tagastab plaani-sõnastiku või ``None``, kui detail ei mahu ühtegi kasti
    (sel juhul kasutab kutsuja riba/aluse loogikat).
    """
    count = max(1, int(count))
    fitting = [
        box for box in BOX_CATALOG
        if detail_fits_in_box(detail_w, detail_l, detail_thickness, box)
    ]
    if not fitting:
        return None
    # 1) väikseim kast, kuhu kogu kogus mahub ühte kasti.
    for box in sorted(fitting, key=lambda b: b.volume_l):
        capacity = box_capacity(detail_w, detail_l, detail_thickness, box)
        if capacity >= count:
            return _box_plan(box, 1, capacity, count)
    # 2) ei mahu ühte kasti → kasuta suurimat sobivat kasti ja arvuta kastide
    #    arv ülespoole ümardatult.
    largest = max(fitting, key=lambda b: b.volume_l)
    capacity = box_capacity(detail_w, detail_l, detail_thickness, largest)
    box_count = math.ceil(count / capacity)
    return _box_plan(largest, box_count, capacity, count)


def is_strip(detail_w, detail_l):
    """Kas detail on „riba" (piklik) — pikim külg ≥ 5× lühim külg."""
    longest = max(detail_w, detail_l)
    shortest = min(detail_w, detail_l)
    if shortest <= 0:
        return False
    return longest >= STRIP_LENGTH_TO_WIDTH_RATIO * shortest


def bundle_count(strip_width_mm, thickness_mm, count):
    """Mitu kimpu, arvestades kimbu max laiust 500 mm ja max kõrgust 600 mm.

    Ridades laotud ribade arv = (500 / riba laius) × (600 / paksus). Kui kogus
    ületab ühe kimbu mahu, tekib mitu kimpu (600 mm kõrguse piirang jaotab virna).
    """
    strips_per_row = max(1, int(BUNDLE_MAX_WIDTH_MM // strip_width_mm)) if strip_width_mm > 0 else 1
    rows = max(1, int(BUNDLE_MAX_HEIGHT_MM // thickness_mm)) if thickness_mm > 0 else 1
    per_bundle = max(1, strips_per_row * rows)
    return math.ceil(max(1, int(count)) / per_bundle)


def select_strip_packing(detail_w, detail_l, detail_thickness, count):
    """Vali riba-pakkimise meetod ja aeg detaili PIKKUSE järgi."""
    length = max(detail_w, detail_l)
    width = min(detail_w, detail_l)
    count = max(1, int(count))

    # Reeglid 3 & 5: pikkus > 1020 mm → alusepakkimine (alus on juba käepärast).
    if length > STRIP_PALLET_MIN_LENGTH_MM:
        return {
            'method': 'pallet',
            'length_mm': length,
            'width_mm': width,
            'estimated_sec': STRIP_PALLET_SEC,
            'recommend_pallet': True,
            'detail_count': count,
            # Hinnad (SISEMINE tootmisjuhis).
            'packaging_label': 'Pakkekile alusel',
            'packaging_unit_price_eur': 0.0,  # pakkekile hinda andmestikus ei ole
            'packaging_count': 1,
            'packaging_line_total_eur': 0.0,
            'pallet_kind': 'full',
            'pallet_price_eur': FULL_PALLET_PRICE_EUR,
            'packaging_total_eur': round(FULL_PALLET_PRICE_EUR, 4),
        }

    # Reegel 1: pikkus < 1000 mm JA laius < 20 mm JA väike kogus → lihtne
    # kilepakkimine (alust ei kasutata). Aeg käsitletakse sama loogikaga kui
    # kimbul (120 sek ots), kuna eraldi aega ei antud.
    if (
        length < STRIP_SIMPLE_MAX_LENGTH_MM
        and width < STRIP_SIMPLE_MAX_WIDTH_MM
        and count <= STRIP_SIMPLE_MAX_COUNT
    ):
        return {
            'method': 'simple_wrap',
            'length_mm': length,
            'width_mm': width,
            'bundle_count': 1,
            'estimated_sec': 2 * STRIP_END_WRAP_SEC,  # 2 otsa
            'recommend_pallet': False,
            'detail_count': count,
            # Hinnad (SISEMINE tootmisjuhis).
            'packaging_label': 'Pakkekile',
            'packaging_unit_price_eur': 0.0,  # pakkekile hinda andmestikus ei ole
            'packaging_count': 1,
            'packaging_line_total_eur': 0.0,
            'pallet_kind': None,
            'pallet_price_eur': 0.0,
            'packaging_total_eur': 0.0,
        }

    # Reegel 2: pikkus ≤ 1020 mm → kimpu, otsad kilega. 120 sek ots (240 sek
    # kimbu kohta); jaga mitmeks kimbuks, kui virn ületaks 600 mm.
    bundles = bundle_count(width, detail_thickness, count)
    return {
        'method': 'bundle',
        'length_mm': length,
        'width_mm': width,
        'bundle_count': bundles,
        'estimated_sec': bundles * 2 * STRIP_END_WRAP_SEC,
        'recommend_pallet': False,
        'detail_count': count,
        # Hinnad (SISEMINE tootmisjuhis).
        'packaging_label': 'Pakkekile (kimp)',
        'packaging_unit_price_eur': 0.0,  # pakkekile hinda andmestikus ei ole
        'packaging_count': bundles,
        'packaging_line_total_eur': 0.0,
        'pallet_kind': None,
        'pallet_price_eur': 0.0,
        'packaging_total_eur': 0.0,
    }


def build_packing_plan(detail_w, detail_l, detail_thickness, count):
    """Peamine sisenemispunkt: vali detaili mõõtude põhjal pakkimismeetod.

    Riba-tüüpi detailid pakitakse riba-loogikaga, ülejäänud kasti-loogikaga.
    Kui detail ei mahu ühtegi kasti, langetakse tagasi riba/aluse loogikale.
    """
    detail_w = float(detail_w or 0)
    detail_l = float(detail_l or 0)
    detail_thickness = float(detail_thickness or 0)
    count = max(1, int(count or 1))

    # Kui detaili pikim mõõt ületab kataloogi suurima kasti pikima sisemõõdu, ei
    # mahu detail ühtegi kasti → kasuta ALATI riba-loogikat (pikkuse-põhised
    # reeglid), sõltumata pikkuse/laiuse suhtest (ratio-heuristikast).
    longest_side = max(detail_w, detail_l, detail_thickness)
    too_long_for_any_box = longest_side > catalog_max_box_dimension_mm()

    if is_strip(detail_w, detail_l) or too_long_for_any_box:
        return select_strip_packing(detail_w, detail_l, detail_thickness, count)
    plan = select_box(detail_w, detail_l, detail_thickness, count)
    if plan is None:
        return select_strip_packing(detail_w, detail_l, detail_thickness, count)
    return plan
