import os
from pathlib import Path

MATPLOTLIB_CACHE_DIR = Path(__file__).resolve().parent / '.matplotlib-cache'
MATPLOTLIB_CACHE_DIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault('MPLCONFIGDIR', str(MATPLOTLIB_CACHE_DIR))

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
import streamlit as st

from application.quote_service import build_price_summary
from utils import dimension_text, fmt, material_need_lines, offcut_label, sec_to_minsec, work_order_steps

BLUE = '#1f6fb2'
LIGHT_BLUE = '#d7eaf8'
ORANGE = '#f2a65a'
GREEN = '#9ccc65'


def render_sales_result(result):
    st.subheader('Pakkumise kokkuvõte')
    top1, top2 = st.columns(2)
    top1.metric('Tellitud detaile', f"{result['detail_count']} tk")
    top2.metric('Arvutuslik tööaeg', sec_to_minsec(result['total_sec']))

    summary = build_price_summary(result)
    st.markdown('#### Hinna jaotus')
    price_cols = st.columns(2 if summary['has_extra_work'] else 1)
    # „Tööraha" tähendab ainult saagimistööd — pealdis ütleb selle üheselt välja,
    # et kasutajale ei jääks muljet, nagu sisaldaks summa ka materjali maksumust.
    price_cols[0].metric('Tööraha (saagimine, ei sisalda materjali)', fmt(summary['base_work_fee_eur'], 2, '€'))
    if summary['has_extra_work']:
        price_cols[1].metric('Võimalikud lisatööd (täpsuslõikus)', fmt(summary['precision_surcharge_eur'], 2, '€'))

    if summary['material_cost_known']:
        st.metric('Materjali hind', fmt(summary['material_cost_eur'], 2, '€'))
    else:
        st.metric('Materjali kogus', fmt(summary['material_area_m2'], 3, 'm²'))
        st.caption('Materjali €/m² hinda kalkulaator ei arvuta — küsi materjali maksumus eraldi hinnapakkumisega.')

    total_label = 'Hind kokku (sisaldab materjali)' if summary['total_includes_material'] else 'Hind kokku (ilma materjalita)'
    st.metric(total_label, fmt(summary['total_eur'], 2, '€'))
    st.caption('Tööraha sisaldab hinnastamisvaru ja arvestusaja ümardamist ülespoole.')

    st.markdown('#### Materjali vajadus')
    for line in material_need_lines(result):
        st.markdown(f'- **{line}**')
    if result.get('partial_sheet_count') and result.get('stock_source') != 'Jääk':
        st.caption('Enne täisplaadi lõikust kontrolli, kas sobivat jääki pole riiulis või boksides.')
    if result['precision_cut']:
        if result.get('small_precision_fixed_price'):
            st.info(
                f"Täpsuslõikus ±0,2 mm: hinnalisa {fmt(result['precision_surcharge_eur'], 2, '€')} "
                '(vähemalt 20 €). '
                f"Kvaliteedikontroll {result['quality_control_check_count']} kontrolli × "
                f"{result['quality_control_sec_per_detail']} sek sisaldub hinnalisas."
            )
        else:
            st.info(
                f"Täpsuslõikus ±0,2 mm: kvaliteedikontroll {sec_to_minsec(result['quality_control_sec'])} "
                f"({result['quality_control_check_count']} kontrolli × "
                f"{result['quality_control_sec_per_detail']} sek). Aeg sisaldub tööajas ja töörahas."
            )
    if result.get('warning'):
        st.warning(result['warning'])


def render_cutting_details(result):
    st.subheader('Lõikuse info')
    if result.get('stock_source') == 'Jääk':
        source_text = (
            f"Sisestatud jääk — {dimension_text(result['raw_width_mm'])} × "
            f"{dimension_text(result['raw_length_mm'])} mm"
        )
    else:
        source_text = result.get('material_name') or 'Täisplaat'
    left, right = st.columns(2)
    with left:
        st.markdown(
            f"**Lähtematerjal:** {source_text}  \n"
            f"**Paksus:** {dimension_text(result['thickness_mm'])} mm  \n"
            f"**Detail:** {dimension_text(result['original_detail_width_mm'])} × "
            f"{dimension_text(result['original_detail_length_mm'])} mm — {result['detail_count']} tk  \n"
            f"**Lõikelaius:** {result['blade']['blade']}  \n"
            f"**Tasanduslõige:** lõikelaius + {dimension_text(result['trim_removal_mm'])} mm ainult lõigataval teljel  \n"
            f"**Paigutus:** {result['across']} × {result['along']}  \n"
            f"**Detaile toorikust:** {result['pieces_per_sheet']} tk"
        )
    with right:
        orientation = 'Detaili paigutus pööratakse 90°.' if result.get('rotated') else 'Detaili paigutust ei pöörata.'
        st.markdown(
            f"**Paigutuse suund:** {orientation}  \n"
            f"**Pikilõikeid:** {result['longitudinal_cut_count']}  \n"
            f"**Ristlõikeid:** {result['cross_cut_count']}  \n"
            f"**Lõikeid kokku:** {result['total_cut_count']}"
        )
        if result.get('rotation_over_1m'):
            st.warning('Üle 1 m detail pööratakse ainult seetõttu, et see vähendab materjalivajadust.')

    if result['precision_cut']:
        st.markdown(
            f"**Täpsuslõikuse seadistus:** {sec_to_minsec(result.get('precision_setup_sec', 30 * 60))}  \n"
            f"**Kvaliteedikontroll:** {result['quality_control_check_count']} kontrollikorda  \n"
            f"**Kontrollühikuid:** {result['quality_control_unit_count']}  \n"
            f"**Lubatud plaadikihte pakis:** kuni {result['max_stack_layers']}  \n"
            "**Kontrolliplaan:** kontrolli esimesed 25 kontrollühikut; seejärel kuni 100-ni iga 10. ja üle 100 iga 25. kontrollühik. Viimane kontrollühik kontrolli alati.  \n"
            "Koos lõigatud vastavaid ribasid kontrollitakse ühe ribapakina. Mõõdu kõrvalekalde korral peata lõikus, korrigeeri seadistus ja kontrolli uus proovdetail."
        )

    st.markdown('#### Materjali väljastus')
    full_count = result['full_sheet_count']
    if result.get('stock_source') == 'Jääk':
        layout_cols = result['partial_cols'] if result.get('partial_sheet_count') else result['across']
        layout_rows = result['partial_rows'] if result.get('partial_sheet_count') else result['along']
        st.markdown(
            '**Sisestatud jääk — 1 tk**  \n'
            f"Paksus: {dimension_text(result['thickness_mm'])} mm  \n"
            f"Mõõt: {dimension_text(result['raw_width_mm'])} × {dimension_text(result['raw_length_mm'])} mm  \n"
            f"Sellest valmistada: {result['detail_count']} detaili  \n"
            f"Paigutus: {layout_cols} × {layout_rows}"
        )
    elif full_count:
        st.markdown(
            f"**Täisplaat — {full_count} tk**  \n"
            f"Materjal: {source_text}  \n"
            f"Paksus: {dimension_text(result['thickness_mm'])} mm  \n"
            f"Mõõt: {dimension_text(result['raw_width_mm'])} × {dimension_text(result['raw_length_mm'])} mm  \n"
            f"Paigutus: {result['across']} × {result['along']}  \n"
            f"Detaile toorikust: {result['pieces_per_sheet']} tk"
        )
    if result.get('partial_sheet_count') and result.get('stock_source') != 'Jääk':
        st.markdown(
            '**Lisamaterjali vajadus (eelistatavalt jääk):**  \n'
            f"Sobiva jäägi minimaalne mõõt — {dimension_text(result['partial_stock_width_mm'])} × "
            f"{dimension_text(result['partial_stock_length_mm'])} mm  \n"
            f"Sellest valmistada {result['partial_piece_count']} detaili; paigutus "
            f"{result['partial_cols']} × {result['partial_rows']}."
        )

    st.markdown('#### Tööjärjekord')
    for number, step in enumerate(work_order_steps(result), 1):
        st.markdown(f'{number}. {step}')

    st.markdown('#### Ajajaotus')
    metric_count = 3 + int(result['precision_cut']) + int(bool(result.get('dust_bag_change_sec')))
    cols = st.columns(metric_count)
    cols[0].metric('Seadistus', sec_to_minsec(result['setup_sec']))
    cols[1].metric('Lõikamine', sec_to_minsec(result['cutting_time_sec']))
    cols[2].metric('Käsitlus', sec_to_minsec(result['handling_sec']))
    metric_index = 3
    if result['precision_cut']:
        cols[metric_index].metric('Kvaliteedikontroll', sec_to_minsec(result['quality_control_sec']))
        metric_index += 1
    if result.get('dust_bag_change_sec'):
        cols[metric_index].metric('Laastukottide vahetus', sec_to_minsec(result['dust_bag_change_sec']))
    st.caption(
        'Käsitlus: 20 sek valmis detaili kohta, kuid vähemalt 90 sek kasutatud tooriku kohta. '
        'Kitsaste 4–6 mm ribade ja vähemalt 80 mm materjali kokkulepitud ajategur rakendub eraldi.'
    )
    if result.get('full_offcuts') and full_count:
        st.markdown('#### Plaadist üle jäävad tükid')
        for offcut in result['full_offcuts']:
            st.markdown(f"- {offcut_label(offcut)} — {full_count} tk")


def _draw_dimension(ax, start, end, y, text):
    ax.annotate('', xy=(start, y), xytext=(end, y), arrowprops={'arrowstyle': '<->', 'color': '#333', 'lw': 0.8})
    ax.text((start + end) / 2, y, text, ha='center', va='bottom', fontsize=8)


def _draw_layout(result, stock_w, stock_l, cols, rows, piece_count, title, full_stock):
    aspect = max(0.35, min(2.5, stock_w / stock_l))
    fig, ax = plt.subplots(figsize=(min(7, 4.6 * aspect + 1.8), 4.6))
    pad_w = stock_w * 0.10
    pad_l = stock_l * 0.10
    ax.set_xlim(-pad_w, stock_w + pad_w)
    ax.set_ylim(-pad_l, stock_l + pad_l)
    ax.set_aspect('equal')
    ax.axis('off')
    ax.set_title(title, fontsize=11, weight='bold', pad=8)
    ax.add_patch(Rectangle((0, 0), stock_w, stock_l, edgecolor='#333', facecolor='#f4f5f6', lw=1.3))

    trim_w = result.get('trim_width_allowance_mm', result['trim_allowance_mm'])
    trim_l = result.get('trim_length_allowance_mm', result['trim_allowance_mm'])
    if trim_w:
        ax.add_patch(Rectangle((0, 0), trim_w, stock_l, edgecolor='none', facecolor=ORANGE, alpha=0.85))
    if trim_l:
        ax.add_patch(Rectangle((0, 0), stock_w, trim_l, edgecolor='none', facecolor=ORANGE, alpha=0.85))
    piece_w = result['detail_width_mm']
    piece_l = result['detail_length_mm']
    kerf = result['kerf_mm'] if 'kerf_mm' in result else result['blade']['kerf_mm']
    dense = piece_count > 250
    drawn = 0
    for row in range(rows):
        for col in range(cols):
            if drawn >= piece_count:
                break
            x = trim_w + col * (piece_w + kerf)
            y = trim_l + row * (piece_l + kerf)
            ax.add_patch(Rectangle((x, y), piece_w, piece_l, edgecolor=BLUE, facecolor=LIGHT_BLUE, lw=0.18 if dense else 0.55))
            drawn += 1

    _draw_dimension(ax, 0, stock_w, -pad_l * 0.55, f'{dimension_text(stock_w)} mm')
    ax.annotate('', xy=(-pad_w * 0.55, 0), xytext=(-pad_w * 0.55, stock_l), arrowprops={'arrowstyle': '<->', 'color': '#333', 'lw': 0.8})
    ax.text(-pad_w * 0.62, stock_l / 2, f'{dimension_text(stock_l)} mm', rotation=90, ha='right', va='center', fontsize=8)
    summary = f'{cols} × {rows} paigutus · {piece_count} detaili'
    ax.text(stock_w / 2, stock_l + pad_l * 0.3, summary, ha='center', va='bottom', fontsize=9, color='#333')
    if dense:
        ax.text(stock_w / 2, stock_l / 2, f'{piece_count} detaili', ha='center', va='center', fontsize=12, weight='bold', color='#174a73', bbox={'facecolor': 'white', 'alpha': 0.86, 'edgecolor': 'none', 'pad': 4})
    fig.tight_layout(pad=0.4)
    return fig


def build_scheme_figures(result):
    figures = []
    if result.get('stock_source') == 'Jääk':
        cols = result['partial_cols'] if result.get('partial_sheet_count') else result['across']
        rows = result['partial_rows'] if result.get('partial_sheet_count') else result['along']
        figures.append(_draw_layout(
            result, result['raw_width_mm'], result['raw_length_mm'], cols, rows,
            result['detail_count'], 'Sisestatud jääk — 1 tk', False,
        ))
        return figures
    if result['full_sheet_count']:
        figures.append(_draw_layout(
            result, result['raw_width_mm'], result['raw_length_mm'], result['across'], result['along'],
            result['pieces_per_sheet'], f"Täisplaat — {result['full_sheet_count']} tk", True,
        ))
    if result['partial_sheet_count']:
        figures.append(_draw_layout(
            result, result['partial_stock_width_mm'], result['partial_stock_length_mm'], result['partial_cols'],
            result['partial_rows'], result['partial_piece_count'], 'Sobiva jäägi minimaalne mõõt', False,
        ))
    return figures


def build_scheme_figure(result, title='Lõikeskeem'):
    """Tagasiühilduvuse abifunktsioon testidele: koondab paigutused ühte joonisesse."""
    layouts = []
    if result.get('stock_source') == 'Jääk':
        cols = result['partial_cols'] if result.get('partial_sheet_count') else result['across']
        rows = result['partial_rows'] if result.get('partial_sheet_count') else result['along']
        layouts.append((result['raw_width_mm'], result['raw_length_mm'], cols, rows, result['detail_count'], 'Sisestatud jääk — 1 tk'))
    elif result['full_sheet_count']:
        layouts.append((result['raw_width_mm'], result['raw_length_mm'], result['across'], result['along'], result['pieces_per_sheet'], f"Täisplaat — {result['full_sheet_count']} tk"))
    if result['partial_sheet_count'] and result.get('stock_source') != 'Jääk':
        layouts.append((result['partial_stock_width_mm'], result['partial_stock_length_mm'], result['partial_cols'], result['partial_rows'], result['partial_piece_count'], 'Sobiva jäägi minimaalne mõõt'))
    fig, axes = plt.subplots(1, max(1, len(layouts)), figsize=(5 * max(1, len(layouts)), 4), squeeze=False)
    for ax in axes[0]:
        ax.axis('off')
    for ax, layout in zip(axes[0], layouts):
        stock_w, stock_l, cols, rows, count, subtitle = layout
        ax.set_xlim(0, stock_w); ax.set_ylim(0, stock_l); ax.set_aspect('equal'); ax.set_title(subtitle, fontsize=10)
        ax.add_patch(Rectangle((0, 0), stock_w, stock_l, edgecolor='#333', facecolor='#f4f5f6'))
        trim_w = result.get('trim_width_allowance_mm', result['trim_allowance_mm'])
        trim_l = result.get('trim_length_allowance_mm', result['trim_allowance_mm'])
        kerf = result['blade']['kerf_mm']; drawn = 0
        for row in range(rows):
            for col in range(cols):
                if drawn >= count: break
                ax.add_patch(Rectangle((trim_w + col * (result['detail_width_mm'] + kerf), trim_l + row * (result['detail_length_mm'] + kerf)), result['detail_width_mm'], result['detail_length_mm'], edgecolor=BLUE, facecolor=LIGHT_BLUE, lw=.3))
                drawn += 1
    fig.suptitle(title)
    fig.tight_layout()
    return fig


def draw_scheme(result):
    st.subheader('Lõikeskeem')
    figures = build_scheme_figures(result)
    for figure in figures:
        st.pyplot(figure, width='content')
        plt.close(figure)
    st.caption('Sinine: detail · oranž: tasanduslõike varu. Mõõdud on millimeetrites; telgede numbriridu ei kuvata.')


def comparison_table(results):
    # Alles jäetud vana impordi ühilduvuseks; müügivaates alternatiive ei näidata.
    return None
