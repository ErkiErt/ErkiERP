import importlib
import os

import streamlit as st
import utils as utils_module
import core as core_module
import materials as materials_module

# Streamliti kuumlaadimine võib hoida vana moodulit mälus. Kohalik ajalugu
# laaditakse teadlikult uuesti, et app.py ja history.py skeem oleks alati sama.
utils_module = importlib.reload(utils_module)
core_module = importlib.reload(core_module)
materials_module = importlib.reload(materials_module)

# Core peab olema taastatud enne mooduleid, mis impordivad sealt uusi sümboleid.
import history as history_module
import print_sheet as print_sheet_module
import ui as ui_module

history_module = importlib.reload(history_module)
print_sheet_module = importlib.reload(print_sheet_module)
ui_module = importlib.reload(ui_module)

from core import MAX_DETAIL_COUNT, CalcInput, validate_input_values
from application.quote_service import compute_quote, single_stock_capacity
from history import build_pending_save_row, build_query_memory_row, load_history, load_query_memory, save_history_row, save_query_memory_row
from materials import articles_for_selection, formats_for_selection, groups, materials_for_group, thickness_label, thicknesses_for_material
from print_sheet import build_printable_cut_sheet
from ui import draw_scheme, render_cutting_details, render_sales_result
from utils import parse_float_text, parse_nonnegative_optional_float_text, parse_positive_optional_float_text

st.set_page_config(page_title='Erki Saagimise kalkulaator', page_icon='▦', layout='wide')

RESULT_SCHEMA_VERSION = 20
INTERNAL_MODE = os.getenv('ERKI_INTERNAL_MODE') == '1'
previous_result_schema = st.session_state.get('result_schema_version')

GROUP_CARD_CONTENT = {
    'Kulumiskindel plast': {
        'materials': 'PA · POM · PET-P · PE500 · PE1000 · PU',
        'description': 'Kulumis-, surve- ja löögikindlad plastid liikuvatele ning koormatud detailidele.',
    },
    'Konstruktsioonplast': {
        'materials': 'PP · PE100 · PE300 · PVC · ABS',
        'description': 'Universaalsed lehtmaterjalid mahutitele, katetele ja keevitatavatele konstruktsioonidele.',
    },
    'Fluoroplast': {
        'materials': 'PTFE · PVDF',
        'description': 'Hea kemikaali- ja temperatuuritaluvusega materjalid nõudlikku töökeskkonda.',
    },
    'Läbipaistev plast': {
        'materials': 'PMMA · PC · PET-G · PET · PS',
        'description': 'Optiliste, kaitsvate ja läbipaistvust vajavate detailide lehtmaterjalid.',
    },
    'Eriotstarbelised plastid': {
        'materials': 'PEEK',
        'description': 'Kõrgema temperatuuri ja mehaanilise koormuse jaoks mõeldud erimaterjalid.',
    },
    'Õõnespaneel': {
        'materials': 'Paneltim PE · Paneltim PP · Paneltim PP-C',
        'description': 'Kerged jäigad paneelid; selles grupis kuvatakse ainult Paneltimi täislehed.',
    },
}

DEFAULTS = {
    'thickness_mm': None,
    'stock_source': None,
    'material_group': None,
    'material_name': None,
    'catalog_thickness_mm': None,
    'sheet_format_key': None,
    'raw_thickness_mm': '',
    'raw_width_mm': '',
    'raw_length_mm': '',
    'detail_width_mm': '',
    'detail_length_mm': '',
    'detail_count': None,
    'precision_cut': False,
    'best_result': None,
    'last_query_id': None,
    'notes': '',
    'result_schema_version': RESULT_SCHEMA_VERSION,
}
for key, value in DEFAULTS.items():
    st.session_state.setdefault(key, value)
if previous_result_schema != RESULT_SCHEMA_VERSION:
    for key in ('thickness_mm', 'stock_source', 'material_group', 'material_name', 'catalog_thickness_mm', 'sheet_format_key', 'raw_thickness_mm', 'raw_width_mm', 'raw_length_mm', 'detail_width_mm', 'detail_length_mm', 'detail_count'):
        st.session_state[key] = DEFAULTS[key]
    st.session_state.precision_cut = False
    st.session_state.best_result = None
    st.session_state.last_query_id = None
    st.session_state.result_schema_version = RESULT_SCHEMA_VERSION


def clear_query():
    for key in ('thickness_mm', 'stock_source', 'material_group', 'material_name', 'catalog_thickness_mm', 'sheet_format_key', 'raw_thickness_mm', 'raw_width_mm', 'raw_length_mm', 'detail_width_mm', 'detail_length_mm', 'detail_count'):
        st.session_state[key] = DEFAULTS[key]
    st.session_state.precision_cut = False
    st.session_state.best_result = None
    st.session_state.last_query_id = None


def invalidate_result():
    # Iga eelneva sammu muutmine teeb varem arvutatud pakkumise kehtetuks, et
    # vana tulemus ei jääks uue sisendi taustal ripakile.
    st.session_state.best_result = None
    st.session_state.last_query_id = None


def on_material_group_change():
    # Grupi vahetus lähtestab allavoolu valikud (materjal, paksus, formaat), et
    # vana valik ei jääks uue grupi taustale kehtima ega arvutus ripakile.
    st.session_state.material_name = None
    st.session_state.catalog_thickness_mm = None
    st.session_state.sheet_format_key = None
    invalidate_result()


def choose_stock_source(source):
    if st.session_state.stock_source != source:
        for key in ('material_group', 'material_name', 'catalog_thickness_mm', 'sheet_format_key'):
            st.session_state[key] = None
        st.session_state.raw_width_mm = ''
        st.session_state.raw_length_mm = ''
        st.session_state.raw_thickness_mm = ''
        st.session_state.best_result = None
        st.session_state.last_query_id = None
    st.session_state.stock_source = source

st.title('Erki Saagimise kalkulaator')
st.caption('Versioon 1 · kiire müügipakkumine ja eraldi tehniline lõikeleht.')

st.markdown(
    """
    <style>
    [class*="st-key-stock_card_"] { border-top: .3rem solid #0f7894 !important; }
    </style>
    """,
    unsafe_allow_html=True,
)

sales_tab, cutting_tab, log_tab = st.tabs([
    'Müügivaade',
    'Lõikeleht',
    'Töölogi' if INTERNAL_MODE else 'Töölogi (sisemine)',
])

with sales_tab:
    st.subheader('Sisend')
    st.markdown('#### 1. Vali lähtematerjal')
    full_stock_col, remnant_col = st.columns(2, gap='medium')
    source_cards = (
        (full_stock_col, 'Täisplaat', 'Vali materjal, paksus ja laos kasutatav standardne plaadiformaat.', 'stock_card_full'),
        (remnant_col, 'Jääk', 'Sisesta jäägi paksus ja tegelikud mõõdud.', 'stock_card_remnant'),
    )
    for column, source, description, card_key in source_cards:
        with column:
            with st.container(border=True, height=145, key=card_key):
                st.markdown(f'**{source}**')
                st.caption(description)
                selected_source = st.session_state.stock_source == source
                st.button(
                    'Valitud ✓' if selected_source else f'Vali {source.lower()} ›',
                    key=f'choose_stock_{source}',
                    type='primary' if selected_source else 'secondary',
                    width='stretch',
                    on_click=choose_stock_source,
                    args=(source,),
                )

    source_selected = bool(st.session_state.stock_source)
    full_sheet_selected = st.session_state.stock_source == 'Täisplaat'
    # Kataloogipõhine materjalivalik kuulub ainult täisplaadi harusse.
    require_catalog_format = True
    group_options = groups(require_format=require_catalog_format) if full_sheet_selected else []
    if st.session_state.material_group not in group_options:
        st.session_state.material_group = None

    material_options = (
        materials_for_group(st.session_state.material_group, require_format=require_catalog_format)
        if st.session_state.material_group else []
    )
    if st.session_state.material_name not in material_options:
        st.session_state.material_name = None

    thickness_options = (
        thicknesses_for_material(
            st.session_state.material_group,
            st.session_state.material_name,
            require_format=require_catalog_format,
        )
        if st.session_state.material_group and st.session_state.material_name else []
    )
    if st.session_state.catalog_thickness_mm not in thickness_options:
        st.session_state.catalog_thickness_mm = None

    format_options = (
        formats_for_selection(st.session_state.material_group, st.session_state.material_name, st.session_state.catalog_thickness_mm)
        if st.session_state.catalog_thickness_mm is not None else []
    )
    format_by_key = {item['key']: item for item in format_options}
    if st.session_state.sheet_format_key not in format_by_key:
        st.session_state.sheet_format_key = None

    if not source_selected:
        st.caption('Vali esmalt lähtematerjal: täisplaat või jääk.')
    elif full_sheet_selected:
        # Kompaktne mitmetasemeline valik: grupp → materjal → paksus → formaat.
        # Iga järgnev selectbox filtreerub eelmise põhjal ja on enne valikut
        # keelatud, nii et kogu materjalivalik mahub kahte tihedasse ritta.
        st.markdown('#### 2. Vali materjal')
        with st.container(border=True):
            group_col, material_col, thickness_col = st.columns(3)
            with group_col:
                st.selectbox('Materjaligrupp', group_options, index=None, placeholder='Vali grupp', key='material_group', on_change=on_material_group_change)
            with material_col:
                st.selectbox('Täpne materjal', material_options, index=None, placeholder='Vali materjal', key='material_name', disabled=not material_options, on_change=invalidate_result)
            with thickness_col:
                st.selectbox('Paksus', thickness_options, index=None, format_func=thickness_label, placeholder='Vali paksus', key='catalog_thickness_mm', disabled=not thickness_options, on_change=invalidate_result)
            st.selectbox(
                'Plaadiformaat',
                list(format_by_key),
                index=None,
                format_func=lambda key: format_by_key[key]['label'],
                placeholder='Vali plaadiformaat',
                key='sheet_format_key',
                disabled=not format_options,
                on_change=invalidate_result,
            )
    elif st.session_state.stock_source == 'Jääk':
        st.markdown('#### 2. Sisesta jäägi ja detaili mõõdud')

    chosen_format = format_by_key.get(st.session_state.sheet_format_key) if st.session_state.stock_source == 'Täisplaat' else None
    matches = []
    if chosen_format and st.session_state.catalog_thickness_mm is not None:
        matches = articles_for_selection(
            st.session_state.material_group,
            st.session_state.material_name,
            st.session_state.catalog_thickness_mm,
            chosen_format['width_mm'],
            chosen_format['length_mm'],
        )

    # Materjali kirjeldused (omadused, kasutusalad, artiklid) ei ole enam kogu aeg
    # nähtaval, vaid kuvatakse eraldi infosektsioonis alles siis, kui materjal ja
    # paksus on valitud — nii püsib valikuosa kompaktne.
    if full_sheet_selected and st.session_state.material_name and st.session_state.catalog_thickness_mm is not None:
        group_content = GROUP_CARD_CONTENT.get(st.session_state.material_group, {})
        with st.expander('Materjali kirjeldus ja artiklid', expanded=False):
            if group_content.get('description'):
                st.markdown(f"**{st.session_state.material_group}** — {group_content['description']}")
            if group_content.get('materials'):
                st.caption(f"Grupi materjalid: {group_content['materials']}")
            if chosen_format:
                descriptions = sorted({
                    ' / '.join(part for part in (row['color'], row['variant']) if part)
                    for row in matches
                    if row['color'] or row['variant']
                })
                extra = f" | {', '.join(descriptions[:3])}" if descriptions else ''
                st.caption(f"Leitud {len(matches)} artiklit{extra}. See on artiklivalik, mitte laoseis.")
            else:
                st.caption('Vali plaadiformaat, et näha sobivaid artikleid.')

    with st.form('calculation_form'):
        a, b, c = st.columns(3)
        with a:
            if st.session_state.stock_source == 'Jääk':
                st.text_input('Jäägi paksus (mm)', placeholder='Sisesta paksus', key='raw_thickness_mm')
                st.text_input('Jäägi laius (mm)', placeholder='Sisesta laius', key='raw_width_mm')
                st.text_input('Jäägi pikkus (mm)', placeholder='Sisesta pikkus', key='raw_length_mm')
            elif chosen_format:
                st.markdown(
                    f"**Valitud plaat:** {chosen_format['label']}  \n"
                    f"**Materjal:** {st.session_state.material_name}, {thickness_label(st.session_state.catalog_thickness_mm)}"
                )
            else:
                st.caption('Vali ülal materjal ja plaadiformaat.')
        with b:
            st.text_input('Detaili laius (mm)', placeholder='Sisesta laius', key='detail_width_mm')
            st.text_input('Detaili pikkus (mm)', placeholder='Sisesta pikkus', key='detail_length_mm')
            st.number_input(
                'Detailide arv', min_value=1, max_value=MAX_DETAIL_COUNT, step=1,
                value=None, placeholder='Sisesta kogus', key='detail_count',
            )
        with c:
            st.checkbox('Täpsuslõikus ±0,2 mm', key='precision_cut')
            st.info('Tasanduslõige arvestatakse ainult lõigataval teljel: lõikelaius + 1 mm.')
        submitted = st.form_submit_button('Arvuta pakkumine', type='primary', width='stretch')

    st.button('Uus päring', key='new_query', on_click=clear_query)

    if submitted:
        selection_errors = []
        if not st.session_state.stock_source:
            selection_errors.append('Vali lähtematerjal: täisplaat või jääk.')
        if st.session_state.stock_source == 'Täisplaat' and (
            not st.session_state.material_group
            or not st.session_state.material_name
            or st.session_state.catalog_thickness_mm is None
        ):
            selection_errors.append('Vali materjaligrupp, täpne materjal ja paksus.')
        if st.session_state.stock_source == 'Täisplaat' and not chosen_format:
            selection_errors.append('Vali plaadiformaat.')
        raw_width = chosen_format['width_mm'] if chosen_format else parse_float_text(st.session_state.raw_width_mm)
        raw_length = chosen_format['length_mm'] if chosen_format else parse_float_text(st.session_state.raw_length_mm)
        selected_thickness = (
            st.session_state.catalog_thickness_mm
            if st.session_state.stock_source == 'Täisplaat'
            else parse_float_text(st.session_state.raw_thickness_mm)
        )
        inp = CalcInput(
            thickness_mm=float(selected_thickness or 0),
            raw_width_mm=raw_width,
            raw_length_mm=raw_length,
            detail_width_mm=parse_float_text(st.session_state.detail_width_mm),
            detail_length_mm=parse_float_text(st.session_state.detail_length_mm),
            detail_count=int(st.session_state.detail_count or 0),
            precision_cut=bool(st.session_state.precision_cut),
            stock_source=st.session_state.stock_source,
            max_stock_count=1 if st.session_state.stock_source == 'Jääk' else None,
        )
        errors = selection_errors + validate_input_values(inp)
        if errors:
            for error in errors:
                st.error(error)
            st.session_state.best_result = None
        else:
            best, _blade_results = compute_quote(inp)
            if best is None:
                capacity = single_stock_capacity(inp) if st.session_state.stock_source == 'Jääk' else 0
                if capacity and inp.detail_count > capacity:
                    st.error(
                        f'Ühest sisestatud jäägist saab valmistada kuni {capacity} detaili. '
                        'Vähenda kogust või sisesta suurem jääk.'
                    )
                else:
                    st.error('Detail ei mahu antud toorikusse või materjalipaksus ei sobi valitud lõikelaiusega.')
                st.session_state.best_result = None
            else:
                best['material_group'] = st.session_state.material_group
                best['material_name'] = st.session_state.material_name
                best['selected_format_label'] = chosen_format['label'] if chosen_format else None
                best['article_codes'] = sorted({row['article_code'] for row in matches if row['article_code']}) if chosen_format else []
                st.session_state.best_result = best
                if INTERNAL_MODE:
                    query_id, row = build_query_memory_row(best)
                    save_query_memory_row(row)
                    st.session_state.last_query_id = query_id

    if st.session_state.best_result:
        render_sales_result(st.session_state.best_result)

with cutting_tab:
    result = st.session_state.best_result
    if not result:
        st.info('Sisesta müügivaates töö andmed ja vajuta „Arvuta pakkumine“.')
    else:
        render_cutting_details(result)
        draw_scheme(result)
        printable_html = build_printable_cut_sheet(result)
        st.download_button(
            'Laadi / prindi lõikeleht',
            data=printable_html.encode('utf-8'),
            file_name='loikeleht.html',
            mime='text/html',
            help='Ava fail brauseris ja vajuta „Prindi lõikeleht“. Leht on A4 rõhtpaigutuses.',
        )

with log_tab:
    if not INTERNAL_MODE:
        st.info('Töölogi ja salvestatud päringud on avalikus testversioonis privaatsuse kaitseks välja lülitatud.')
        st.stop()
    st.subheader('Praeguse seansi töölogi')
    result = st.session_state.best_result
    if not result:
        st.info('Arvuta esmalt töö.')
    else:
        st.markdown(
            f"**Lõikelaius:** {result['blade']['blade']}  \n"
            f"**Detaile toorikust:** {result['pieces_per_sheet']}  \n"
            f"**Lõikeid kokku:** {result['total_cut_count']}  \n"
            f"**Arvutuslik aeg:** {round(result['total_sec'])} sek  \n"
            f"**Tööraha:** {result['work_fee_eur']:.2f} €"
        )
        st.text_area('Märkused', key='notes')
        c1, c2 = st.columns(2)
        with c1:
            actual_time = st.text_input('Tegelik tööaeg (min)', placeholder='nt 24,5')
        with c2:
            rework_time = st.text_input('Ümbertöötluse aeg (min)', placeholder='valikuline')
        if st.button('Salvesta lõpetatud töö'):
            try:
                actual_min = parse_positive_optional_float_text(actual_time, 'Tegelik tööaeg')
                rework_min = parse_nonnegative_optional_float_text(rework_time, 'Ümbertöötluse aeg')
                if actual_min is None:
                    raise ValueError('Tegelik tööaeg on salvestamiseks vajalik.')
                row = build_pending_save_row(
                    st.session_state,
                    result,
                    result['blade']['blade'],
                    result.get('rotated', False),
                    actual_min * 60,
                    (rework_min or 0) * 60,
                )
                save_history_row(row)
                st.success('Töö salvestatud.')
            except ValueError as exc:
                st.error(str(exc))

    with st.expander('Varasemad lõpetatud tööd'):
        history = load_history()
        st.dataframe(history, width='stretch', hide_index=True)
    with st.expander('Salvestatud päringud'):
        memory = load_query_memory()
        st.dataframe(memory.tail(100).iloc[::-1], width='stretch', hide_index=True)
