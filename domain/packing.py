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


# Tehpacki lainepapikastid (sisemõõdud L×W×H mm, hind KM-ga). Kasti 5 kõrgus on
# tegelikult 270–320 mm; mahutavuse arvutuses kasutame turvalisemat 270 mm, et
# mitte üle hinnata mahutavust.
BOX_CATALOG = (
    Box('200×150×120', 200, 150, 120, 0.17),
    Box('350×250×200', 350, 250, 200, 0.57),
    Box('360×250×250', 360, 250, 250, 0.60),
    Box('400×300×220', 400, 300, 220, 0.66),
    Box('440×310×270', 440, 310, 270, 0.83),
    Box('590×380×250', 590, 380, 250, 1.04),
    Box('590×380×400', 590, 380, 400, 1.00),
)

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


def detail_fits_in_box(detail_w, detail_l, detail_thickness, box):
    """Kas üks detail mahub kasti (mõõdupõhine, mistahes orientatsioonis)?"""
    part = sorted((detail_w, detail_l, detail_thickness), reverse=True)
    return all(p <= b + 1e-6 for p, b in zip(part, box.sorted_dims_mm))


def box_capacity(detail_w, detail_l, detail_thickness, box):
    """Ligikaudne detailide arv ühes kastis ruumala + turvavaru baasil.

    Kui detail mahub kasti mõõtmeliselt, on mahutavus vähemalt 1, isegi kui
    ruumala + turvavaru annaks 0 (nt üksik paks detail).
    """
    if not detail_fits_in_box(detail_w, detail_l, detail_thickness, box):
        return 0
    detail_vol_l = detail_w * detail_l * detail_thickness / 1_000_000.0
    if detail_vol_l <= 0:
        return 0
    usable = box.volume_l * (1 - BOX_PACKING_SAFETY_MARGIN)
    return max(1, int(usable // detail_vol_l))


def _box_plan(box, box_count, capacity, count):
    return {
        'method': 'box',
        'box': box,
        'box_name': box.name,
        'box_count': box_count,
        'capacity_per_box': capacity,
        # Poolik euraalus soovitatakse, kui valitud kast on üks kolmest suurimast.
        'recommend_pallet': box in three_largest_boxes(),
        'assembly_sec': BOX_ASSEMBLY_SEC * box_count,
        'estimated_sec': BOX_ASSEMBLY_SEC * box_count,
        'detail_count': count,
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

    if is_strip(detail_w, detail_l):
        return select_strip_packing(detail_w, detail_l, detail_thickness, count)
    plan = select_box(detail_w, detail_l, detail_thickness, count)
    if plan is None:
        return select_strip_packing(detail_w, detail_l, detail_thickness, count)
    return plan
