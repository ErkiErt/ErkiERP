from html import escape

from utils import dimension_text, material_need_lines, offcut_label, work_order_steps


def _positions(count, limit=80):
    """Return representative grid boundaries without creating huge HTML files."""
    if count <= limit:
        return range(1, count)
    step = count / limit
    return sorted({max(1, min(count - 1, round(index * step))) for index in range(1, limit)})


def _scheme_svg(result, *, full_stock):
    is_entered_remnant = result.get('stock_source') == 'Jääk'
    if is_entered_remnant:
        stock_w = result['raw_width_mm']
        stock_l = result['raw_length_mm']
        cols = result['partial_cols'] if result.get('partial_sheet_count') else result['across']
        rows = result['partial_rows'] if result.get('partial_sheet_count') else result['along']
        count = result['detail_count']
        title = 'Sisestatud jääk — 1 tk'
    elif full_stock:
        stock_w = result['raw_width_mm']
        stock_l = result['raw_length_mm']
        cols, rows = result['across'], result['along']
        count = result['pieces_per_sheet']
        title = f"Täisplaat — {result['full_sheet_count']} tk"
    else:
        stock_w = result['partial_stock_width_mm']
        stock_l = result['partial_stock_length_mm']
        cols, rows = result['partial_cols'], result['partial_rows']
        count = result['partial_piece_count']
        title = 'Sobiva jäägi minimaalne mõõt'

    canvas_w, canvas_h = 520.0, 310.0
    margin_x, margin_y = 56.0, 42.0
    available_w, available_h = canvas_w - 2 * margin_x, canvas_h - 2 * margin_y
    scale = min(available_w / stock_w, available_h / stock_l)
    draw_w, draw_h = stock_w * scale, stock_l * scale
    x = (canvas_w - draw_w) / 2
    y = margin_y + (available_h - draw_h) / 2
    trim_w_px = result.get('trim_width_allowance_mm', result['trim_allowance_mm']) * scale
    trim_l_px = result.get('trim_length_allowance_mm', result['trim_allowance_mm']) * scale

    lines = []
    if is_entered_remnant and count <= 500:
        piece_w = result['detail_width_mm']
        piece_l = result['detail_length_mm']
        kerf = result['blade']['kerf_mm']
        for index in range(count):
            row, col = divmod(index, cols)
            part_x = x + (result.get('trim_width_allowance_mm', 0) + col * (piece_w + kerf)) * scale
            part_bottom = result.get('trim_length_allowance_mm', 0) + row * (piece_l + kerf)
            part_y = y + draw_h - (part_bottom + piece_l) * scale
            lines.append(
                f'<rect x="{part_x:.2f}" y="{part_y:.2f}" width="{piece_w * scale:.2f}" '
                f'height="{piece_l * scale:.2f}" class="part"/>'
            )
    else:
        for col in _positions(cols):
            gx = x + draw_w * col / cols
            lines.append(f'<line x1="{gx:.2f}" y1="{y:.2f}" x2="{gx:.2f}" y2="{y + draw_h:.2f}"/>')
        for row in _positions(rows):
            gy = y + draw_h * row / rows
            lines.append(f'<line x1="{x:.2f}" y1="{gy:.2f}" x2="{x + draw_w:.2f}" y2="{gy:.2f}"/>')
    grid = ''.join(lines)
    dense_note = ' · skeemiline tihevaade' if cols > 80 or rows > 80 else ''
    return f'''
    <article class="scheme">
      <h3>{escape(title)}</h3>
      <svg viewBox="0 0 {canvas_w:.0f} {canvas_h:.0f}" role="img" aria-label="{escape(title)}">
        <rect x="{x:.2f}" y="{y:.2f}" width="{draw_w:.2f}" height="{draw_h:.2f}" class="stock{' remnant-stock' if is_entered_remnant else ''}"/>
        <g class="cut-grid">{grid}</g>
        {f'<rect x="{x:.2f}" y="{y:.2f}" width="{max(1.5, trim_w_px):.2f}" height="{draw_h:.2f}" class="trim"/>' if trim_w_px else ''}
        {f'<rect x="{x:.2f}" y="{y + draw_h - max(1.5, trim_l_px):.2f}" width="{draw_w:.2f}" height="{max(1.5, trim_l_px):.2f}" class="trim"/>' if trim_l_px else ''}
        <text x="{canvas_w / 2:.1f}" y="20" class="summary">{cols} × {rows} · {count} detaili{dense_note}</text>
        <text x="{canvas_w / 2:.1f}" y="{canvas_h - 7:.1f}" class="dimension">{dimension_text(stock_w)} mm</text>
        <text x="14" y="{canvas_h / 2:.1f}" transform="rotate(-90 14 {canvas_h / 2:.1f})" class="dimension">{dimension_text(stock_l)} mm</text>
      </svg>
    </article>'''


def build_printable_cut_sheet(result):
    precision_setup_minutes = round(result.get('precision_setup_sec', 30 * 60) / 60)
    precision = (
        '<p><strong>Täpsus:</strong> ±0,2 mm</p>'
        f'<p><strong>Täppislõikuse seadistus:</strong> {precision_setup_minutes} minutit. Seadista mõõt ja kinnita see proovdetailiga enne seeria alustamist.</p>'
        f"<p><strong>Kvaliteedikontroll:</strong> {result['quality_control_check_count']} kontrollikorda; "
        f"{result['quality_control_unit_count']} kontrollühikut.</p>"
        '<ul><li>Kontrolli esimesed 25 kontrollühikut.</li>'
        '<li>Kontrollühikud 26–100: kontrolli iga 10. järel.</li>'
        '<li>Üle 100 kontrollühiku: kontrolli iga 25. järel.</li>'
        '<li>Kontrolli alati viimane kontrollühik.</li>'
        '<li>Koos lõigatud vastavaid ribasid kontrolli ühe ribapakina.</li>'
        '<li>Kõrvalekalde korral peata lõikus, korrigeeri seadistus ja kontrolli uus proovdetail.</li></ul>'
        if result['precision_cut'] else ''
    )
    rotation = 'Pööra detaili paigutus 90°.' if result.get('rotated') else 'Detaili paigutust ei pöörata.'
    materials = ''.join(f'<li>{escape(line)}</li>' for line in material_need_lines(result))
    stock_check = ''
    if result['partial_sheet_count'] and result.get('stock_source') != 'Jääk':
        stock_check = '<p class="notice"><strong>Enne täisplaadi lõikust kontrolli, kas sobivat jääki pole riiulis või boksides.</strong></p>'
    steps = work_order_steps(result)
    step_html = ''.join(f'<li>{escape(step)}</li>' for step in steps)
    schemes = []
    layout_rows = []
    if result.get('stock_source') == 'Jääk':
        schemes.append(_scheme_svg(result, full_stock=False))
        layout_cols = result['partial_cols'] if result.get('partial_sheet_count') else result['across']
        layout_rows_count = result['partial_rows'] if result.get('partial_sheet_count') else result['along']
        layout_rows.append(
            f"<p><strong>Sisestatud jääk:</strong> {layout_cols} × {layout_rows_count} = "
            f"{result['detail_count']} detaili</p>"
        )
    elif result['full_sheet_count']:
        schemes.append(_scheme_svg(result, full_stock=True))
        layout_rows.append(
            f"<p><strong>Täisplaat:</strong> {result['across']} × {result['along']} = "
            f"{result['pieces_per_sheet']} detaili</p>"
        )
    if result['partial_sheet_count'] and result.get('stock_source') != 'Jääk':
        schemes.append(_scheme_svg(result, full_stock=False))
        layout_rows.append(
            f"<p><strong>Sobiv jääk:</strong> {result['partial_cols']} × {result['partial_rows']} = "
            f"{result['partial_piece_count']} detaili</p>"
        )
    scheme_html = ''.join(schemes)
    layout_html = ''.join(layout_rows)
    source_label = 'Jääk' if result.get('stock_source') == 'Jääk' else (result.get('material_name') or 'Täisplaat')
    largest_usable = result.get('largest_usable_offcut')
    if largest_usable:
        offcut_html = (
            '<p><strong>Suurim taaskasutatav jääk:</strong> '
            f'{escape(offcut_label(largest_usable))} — märgista ja pane riiulisse.</p>'
        )
    else:
        offcut_html = (
            '<p><strong>Taaskasutatav jääk:</strong> ei teki (allesjääv materjal on '
            'liiga väike kasutamiseks).</p>'
        )
    return f'''<!doctype html>
<html lang="et"><head><meta charset="utf-8"><title>Lõikeleht</title>
<style>
@page {{ size: A4 landscape; margin: 10mm; }}
body {{ font-family: Arial, sans-serif; color: #111; font-size: 10.5pt; }}
h1 {{ margin: 0 0 5mm; }} h2 {{ margin: 4mm 0 2mm; }} h3 {{ margin: 0 0 1mm; text-align:center; font-size:11pt; }}
.grid, .schemes {{ display:grid; grid-template-columns:1fr 1fr; gap:5mm; margin-bottom:4mm; }}
.box, .scheme {{ border:1px solid #555; border-radius:5px; padding:3.5mm; break-inside:avoid; }}
.scheme svg {{ width:100%; height:65mm; display:block; }}
  .stock {{ fill:#d7eaf8; stroke:#222; stroke-width:1.4; }}
  .remnant-stock {{ fill:#f4f5f6; }} .part {{ fill:#d7eaf8; stroke:#1f6fb2; stroke-width:.45; }}
  .cut-grid {{ stroke:#1f6fb2; stroke-width:.45; }} .trim {{ fill:#f2a65a; }}
.summary {{ text-anchor:middle; font-size:12px; font-weight:bold; }}
.dimension {{ text-anchor:middle; font-size:11px; }}
.notice {{ background:#fff4cc; border-left:4px solid #d39b00; padding:2.5mm; }}
li {{ margin:1.2mm 0; }} .no-print {{ margin-bottom:4mm; }}
@media print {{ .no-print {{ display:none; }} }}
</style></head><body>
<button class="no-print" onclick="window.print()">Prindi lõikeleht</button>
<h1>Lõikeleht</h1><div class="grid"><section class="box">
<h2>Materjali väljastus</h2><ul>{materials}</ul>{stock_check}
    <p><strong>Lähtematerjal:</strong> {escape(source_label)}, {dimension_text(result['thickness_mm'])} mm</p>
</section><section class="box"><h2>Detailid</h2>
<p><strong>Mõõt:</strong> {dimension_text(result['original_detail_width_mm'])} × {dimension_text(result['original_detail_length_mm'])} mm</p>
<p><strong>Kogus:</strong> {result['detail_count']} tk</p>{precision}
<p><strong>Lõikelaius:</strong> {escape(result['blade']['blade'])}</p>
<p><strong>Tasanduslõige:</strong> lõikelaius + {dimension_text(result['trim_removal_mm'])} mm ainult lõigataval teljel</p>
</section></div>
<div class="grid"><section class="box"><h2>Paigutus</h2>
{layout_html}
<p><strong>Suund:</strong> {rotation}</p>
<p><strong>Lõiked:</strong> {result['longitudinal_cut_count']} piki + {result['cross_cut_count']} risti</p>
{offcut_html}
</section><section class="box"><h2>Tööjärjekord</h2><ol>{step_html}</ol></section></div>
<h2>Lõikeskeem</h2><div class="schemes">{scheme_html}</div>
</body></html>'''
