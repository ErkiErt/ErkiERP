import math
import os
import random
import unittest
from pathlib import Path
from unittest.mock import patch

import matplotlib.pyplot as plt
from streamlit.testing.v1 import AppTest

from core import (
    BASE_HANDLING_PER_STOCK_SEC, BASE_SETUP_SEC, BLADES, CalcInput, DUST_BAG_CHANGE_SEC,
    HANDLING_PER_DETAIL_SEC, LARGE_BLADE, MAX_DETAIL_COUNT, MAX_MATERIAL_THICKNESS_MM,
    PRECISION_SETUP_SEC, SAW_HOURLY_RATE_EUR, THICK_MATERIAL_TIME_FACTOR, TRIM_REMOVAL_MM,
    SMALL_BLADE,
    apply_monotonic_quote_floor, build_best_result, build_best_result_for_blade, build_orientation_result,
    choose_best_result, dust_bag_change_count, max_single_stock_capacity, quality_control_check_count,
    quality_control_seconds_per_detail, validate_input_values,
)
from history import build_pending_save_row, build_query_memory_row, normalize_history_df
from print_sheet import build_printable_cut_sheet
from ui import build_scheme_figure, build_scheme_figures
from utils import material_need_lines
from materials import (
    formats_for_selection,
    groups,
    load_sheet_catalog,
    materials_for_group,
    sheet_compatibility,
    thicknesses_for_material,
)


def inp(raw_w=1000, raw_l=3000, detail_w=25, detail_l=25, count=592, precision=False):
    return CalcInput(18, raw_w, raw_l, detail_w, detail_l, count, precision_cut=precision)


class CalculationTests(unittest.TestCase):
    def test_material_catalog_selection_chain(self):
        self.assertIn('Kulumiskindel plast', groups())
        self.assertIn('PE500 (PE-HMW)', materials_for_group('Kulumiskindel plast'))
        self.assertIn('PE100 (PE-HD)', materials_for_group('Konstruktsioonplast'))
        self.assertIn('PE-L / PE-LD', materials_for_group('Konstruktsioonplast'))
        self.assertIn(20.0, thicknesses_for_material('Kulumiskindel plast', 'PE500 (PE-HMW)'))
        formats = formats_for_selection('Kulumiskindel plast', 'PE500 (PE-HMW)', 20.0)
        self.assertTrue(any(item['width_mm'] == 1000 and item['length_mm'] == 2000 for item in formats))
        pe100_formats = formats_for_selection('Konstruktsioonplast', 'PE100 (PE-HD)', 20.0)
        self.assertTrue(any(item['width_mm'] == 1000 and item['length_mm'] == 2000 for item in pe100_formats))
        self.assertFalse(any(row['thickness_mm'] > 95 for row in load_sheet_catalog()))
        self.assertNotIn(1000.0, thicknesses_for_material('Konstruktsioonplast', 'PE'))
        for group in groups(require_format=True):
            for material in materials_for_group(group, require_format=True):
                for thickness in thicknesses_for_material(group, material, require_format=True):
                    formats = formats_for_selection(group, material, thickness)
                    self.assertTrue(formats)
                    self.assertTrue(all(item['status'] == 'direct' for item in formats))
        self.assertNotIn('PE-L / PE-LD', materials_for_group('Konstruktsioonplast', require_format=True))
        self.assertIn('PE-L / PE-LD', materials_for_group('Konstruktsioonplast', require_format=False))

    def test_material_taxonomy_and_catalog_cleaning(self):
        pa = materials_for_group('Kulumiskindel plast', require_format=True)
        self.assertIn('PA6-C / PA6-G', pa)
        self.assertIn('PA6-E', pa)
        self.assertIn('PA66', pa)
        self.assertIn('POM-C', materials_for_group('Kulumiskindel plast', require_format=True))
        self.assertIn('POM-H', materials_for_group('Kulumiskindel plast', require_format=True))
        self.assertIn('POM-C ELS', materials_for_group('Kulumiskindel plast', require_format=True))
        self.assertIn('PET (PET-P)', materials_for_group('Kulumiskindel plast', require_format=True))
        self.assertNotIn('PC (tehniline polükarbonaat)', materials_for_group('Kulumiskindel plast', require_format=True))
        self.assertIn('PC (tehniline polükarbonaat)', materials_for_group('Läbipaistev plast', require_format=True))
        self.assertIn('PMMA-XT', materials_for_group('Läbipaistev plast', require_format=True))
        self.assertIn('PMMA', materials_for_group('Läbipaistev plast', require_format=True))
        self.assertIn('PET', materials_for_group('Läbipaistev plast', require_format=True))
        self.assertFalse(any('täpsustamata' in material.lower() for material in materials_for_group('Läbipaistev plast', require_format=True)))
        self.assertNotIn('PMMA-XT', materials_for_group('Kulumiskindel plast', require_format=True))
        self.assertIn('PP-H', materials_for_group('Konstruktsioonplast', require_format=True))
        self.assertIn('PP-C', materials_for_group('Konstruktsioonplast', require_format=True))
        self.assertIn('PP', materials_for_group('Konstruktsioonplast', require_format=True))
        self.assertNotIn('PP – täpsustamata', materials_for_group('Konstruktsioonplast', require_format=True))
        self.assertIn('PVC-U', materials_for_group('Konstruktsioonplast', require_format=True))
        names = [row['article_name'].upper() for row in load_sheet_catalog()]
        self.assertFalse(any('DIBOND' in name or 'TEKSTOLIIT' in name for name in names))
        self.assertFalse(any('JÄÄG' in name for name in names))
        self.assertFalse(any(name.endswith('1140M') for name in names))
        self.assertFalse(any('VAHT' in name or 'FOAM' in name or 'SIMOPOR' in name or 'TERMOLON' in name for name in names))
        self.assertFalse(any('STEPISOL' in name or 'PLASTVIL' in name or 'DAMTEC' in name for name in names))
        self.assertFalse(any('KIHTPLAST' in name for name in names))
        self.assertFalse(any('MAKROLON' in name and '6000' in name for name in names))
        self.assertFalse(any('DEFEKT' in name for name in names))
        self.assertFalse(any(row['material'] == 'PE vaht' for row in load_sheet_catalog()))
        self.assertTrue(all(row['material'] == 'PA6-C / PA6-G + Oil' for row in load_sheet_catalog() if 'ZELLAMIID 1100 OIL' in row['article_name'].upper()))
        hollow_rows = [row for row in load_sheet_catalog() if row['group'] == 'Õõnespaneel']
        self.assertTrue(hollow_rows)
        self.assertTrue(all('PANELTIM' in row['article_name'].upper() for row in hollow_rows))
        self.assertEqual(
            set(materials_for_group('Õõnespaneel', require_format=True)),
            {'Paneltim PE', 'Paneltim PP', 'Paneltim PP-C'},
        )
        self.assertEqual(set(groups(require_format=True)), {
            'Kulumiskindel plast', 'Konstruktsioonplast', 'Fluoroplast',
            'Läbipaistev plast', 'Eriotstarbelised plastid', 'Õõnespaneel',
        })
        self.assertEqual(set(materials_for_group('Fluoroplast', require_format=True)), {'PTFE', 'PVDF'})
        self.assertEqual(set(materials_for_group('Eriotstarbelised plastid', require_format=True)), {'PEEK'})
        self.assertIn('PU', materials_for_group('Kulumiskindel plast', require_format=True))
        self.assertFalse(any(
            'täpsustamata' in row['material'].lower()
            for row in load_sheet_catalog()
        ))

    def test_machine_format_classification(self):
        self.assertEqual(sheet_compatibility(1000, 2000), 'direct')
        self.assertEqual(sheet_compatibility(2000, 4000), 'precut')
        self.assertEqual(sheet_compatibility(2000, 6000), 'precut')
        self.assertEqual(sheet_compatibility(5100, 7100), 'incompatible')


class ApplicationTests(unittest.TestCase):
    def test_catalog_example_can_be_calculated(self):
        query_file = Path('data/arvutusparingud.csv')
        original_queries = query_file.read_bytes() if query_file.exists() else None
        try:
            app = AppTest.from_file('app.py').run(timeout=30)
            self.assertFalse(app.exception)
            next(button for button in app.button if button.key == 'choose_stock_Täisplaat').click().run(timeout=30)
            next(button for button in app.button if button.key == 'choose_group_Kulumiskindel plast').click().run(timeout=30)
            app.selectbox[0].select('PE500 (PE-HMW)').run(timeout=30)
            app.selectbox[1].select(20.0).run(timeout=30)
            app.selectbox[2].select('1000|2000').run(timeout=30)
            app.text_input[0].input('100').run(timeout=30)
            app.text_input[1].input('2000').run(timeout=30)
            app.number_input[0].set_value(10).run(timeout=30)
            next(button for button in app.button if button.label == 'Arvuta pakkumine').click().run(timeout=30)
            self.assertFalse(app.exception)
            self.assertIsNotNone(app.session_state['best_result'])
        finally:
            if original_queries is None:
                query_file.unlink(missing_ok=True)
            else:
                query_file.write_bytes(original_queries)

    def test_large_series_user_flow_shows_release_information_and_clears(self):
        query_file = Path('data/arvutusparingud.csv')
        original_queries = query_file.read_bytes() if query_file.exists() else None
        try:
            app = AppTest.from_file('app.py').run(timeout=30)
            next(button for button in app.button if button.key == 'choose_stock_Täisplaat').click().run(timeout=30)
            next(button for button in app.button if button.key == 'choose_group_Konstruktsioonplast').click().run(timeout=30)
            app.selectbox[0].select('PE300 (PE-HD)').run(timeout=30)
            app.selectbox[1].select(10.0).run(timeout=30)
            app.selectbox[2].select('1500|3000').run(timeout=30)
            app.text_input[0].input('55').run(timeout=30)
            app.text_input[1].input('2740').run(timeout=30)
            app.number_input[0].set_value(500).run(timeout=30)
            next(button for button in app.button if button.label == 'Arvuta pakkumine').click().run(timeout=30)

            self.assertFalse(app.exception)
            result = app.session_state['best_result']
            self.assertEqual(app.title[0].value, 'Erki Saagimise kalkulaator')
            self.assertEqual(result['handling_sec'], 500 * 20)
            self.assertLess(result['handling_sec'], result['cutting_time_sec'])
            self.assertEqual(result['billable_sec'], 410 * 60)
            self.assertEqual(result['work_fee_eur'], 410.0)
            page_text = '\n'.join(item.value for item in app.markdown)
            self.assertIn('**Lähtematerjal:** PE300 (PE-HD)', page_text)
            self.assertIn('**Paksus:** 10 mm', page_text)
            self.assertIn('Too alus või käru sae juurde', page_text)
            self.assertTrue(any(item.label == 'Käsitlus' and item.value == '166 min 40 sek' for item in app.metric))
            self.assertTrue(any(
                'avalikus testversioonis privaatsuse kaitseks välja lülitatud' in item.value
                for item in app.info
            ))

            next(button for button in app.button if button.key == 'new_query').click().run(timeout=30)
            self.assertIsNone(app.session_state['stock_source'])
            self.assertIsNone(app.session_state['best_result'])
            self.assertEqual(app.session_state['detail_width_mm'], '')
            self.assertIsNone(app.session_state['material_group'])
        finally:
            if original_queries is None:
                query_file.unlink(missing_ok=True)
            else:
                query_file.write_bytes(original_queries)

    def test_internal_launcher_mode_keeps_private_work_log(self):
        query_file = Path('data/arvutusparingud.csv')
        original_queries = query_file.read_bytes() if query_file.exists() else None
        try:
            with patch.dict(os.environ, {'ERKI_INTERNAL_MODE': '1'}):
                app = AppTest.from_file('app.py').run(timeout=30)
                next(button for button in app.button if button.key == 'choose_stock_Täisplaat').click().run(timeout=30)
                next(button for button in app.button if button.key == 'choose_group_Kulumiskindel plast').click().run(timeout=30)
                app.selectbox[0].select('PE500 (PE-HMW)').run(timeout=30)
                app.selectbox[1].select(20.0).run(timeout=30)
                app.selectbox[2].select('1000|2000').run(timeout=30)
                app.text_input[0].input('100').run(timeout=30)
                app.text_input[1].input('2000').run(timeout=30)
                app.number_input[0].set_value(10).run(timeout=30)
                next(button for button in app.button if button.label == 'Arvuta pakkumine').click().run(timeout=30)
                self.assertFalse(app.exception)
                self.assertFalse(any('avalikus testversioonis' in item.value for item in app.info))
                self.assertTrue(query_file.exists())
                self.assertNotEqual(query_file.read_bytes(), original_queries)
        finally:
            if original_queries is None:
                query_file.unlink(missing_ok=True)
            else:
                query_file.write_bytes(original_queries)

    def test_every_visible_material_thickness_and_format_calculates(self):
        checked = 0
        for group in groups(require_format=True):
            for material in materials_for_group(group, require_format=True):
                for thickness in thicknesses_for_material(group, material, require_format=True):
                    for sheet_format in formats_for_selection(group, material, thickness):
                        raw_width = sheet_format['width_mm']
                        raw_length = sheet_format['length_mm']
                        detail_width = max(10.0, min(raw_width / 4.0, 250.0))
                        detail_length = max(10.0, min(raw_length / 4.0, 500.0))
                        for detail_count in (1, 10, 100):
                            calculation_input = CalcInput(
                                thickness,
                                raw_width,
                                raw_length,
                                detail_width,
                                detail_length,
                                detail_count,
                                stock_source='Täisplaat',
                            )
                            self.assertFalse(validate_input_values(calculation_input))
                            result = choose_best_result([
                                build_best_result_for_blade(blade, calculation_input)
                                for blade in BLADES
                            ])
                            self.assertIsNotNone(
                                result,
                                (group, material, thickness, raw_width, raw_length, detail_count),
                            )
                            for field in (
                                'total_sec', 'work_fee_eur', 'material_needed_area_m2',
                                'net_detail_area_m2', 'total_cut_count',
                            ):
                                self.assertTrue(math.isfinite(result[field]))
                                self.assertGreaterEqual(result[field], 0)
                            self.assertGreaterEqual(
                                result['material_needed_area_m2'] + 1e-9,
                                result['net_detail_area_m2'],
                            )
                            self.assertGreaterEqual(result['billable_sec'], result['total_sec'] * 1.05)
                            self.assertEqual(result['billable_sec'] % (5 * 60), 0)
                            if thickness > 25:
                                self.assertTrue(result['blade']['is_default'])
                            checked += 1
        self.assertEqual(checked, 656 * 3)

    def test_leftover_keeps_material_and_manual_dimensions(self):
        app = AppTest.from_file('app.py').run(timeout=30)
        self.assertFalse(app.exception)
        next(button for button in app.button if button.key == 'choose_stock_Jääk').click().run(timeout=30)
        self.assertEqual(len(app.selectbox), 0)
        self.assertEqual(len(app.text_input), 5)
        self.assertEqual(app.text_input[0].label, 'Jäägi paksus (mm)')
        self.assertEqual(app.text_input[1].label, 'Jäägi laius (mm)')
        self.assertEqual(app.text_input[2].label, 'Jäägi pikkus (mm)')

    def test_one_leftover_cannot_be_repeated_as_multiple_stocks(self):
        remnant = CalcInput(5, 2000, 3000, 100, 2000, 100, stock_source='Jääk', max_stock_count=1)
        self.assertGreater(max_single_stock_capacity(remnant), 0)
        self.assertIsNone(build_best_result_for_blade(LARGE_BLADE, remnant))

    def test_leftover_result_and_scheme_use_entered_piece(self):
        remnant = CalcInput(5, 2000, 3000, 100, 2000, 10, stock_source='Jääk', max_stock_count=1)
        result = build_best_result_for_blade(LARGE_BLADE, remnant)
        self.assertIsNotNone(result)
        self.assertEqual(result['stock_source'], 'Jääk')
        self.assertEqual(material_need_lines(result), ['Sisestatud jääk — 2000 × 3000 mm'])
        figures = build_scheme_figures(result)
        self.assertEqual(len(figures), 1)
        self.assertIn('Sisestatud jääk', figures[0].axes[0].get_title())
        plt.close(figures[0])
        html = build_printable_cut_sheet(result)
        self.assertIn('Sisestatud jääk', html)
        self.assertIn('<strong>Lähtematerjal:</strong> Jääk, 5 mm', html)

    def test_leftover_ui_reports_insufficient_quantity(self):
        app = AppTest.from_file('app.py').run(timeout=30)
        next(button for button in app.button if button.key == 'choose_stock_Jääk').click().run(timeout=30)
        for widget, value in zip(app.text_input, ('5', '2000', '3000', '100', '2000')):
            widget.input(value).run(timeout=30)
        app.number_input[0].set_value(100).run(timeout=30)
        next(button for button in app.button if button.label == 'Arvuta pakkumine').click().run(timeout=30)
        self.assertIsNone(app.session_state['best_result'])
        self.assertTrue(any('Ühest sisestatud jäägist' in error.value for error in app.error))


    def test_trim_allowance_is_kerf_plus_one_mm(self):
        result = build_orientation_result(LARGE_BLADE, inp(200, 200, 100, 100, 1), 100, 100)
        self.assertAlmostEqual(result['trim_allowance_mm'], LARGE_BLADE['kerf_mm'] + TRIM_REMOVAL_MM)

    def test_detail_must_fit_after_trim(self):
        # Terve toorik ühe detailina ei vaja kummalgi teljel lõikamist.
        whole = build_orientation_result(LARGE_BLADE, inp(100, 100, 100, 100, 1), 100, 100)
        self.assertIsNotNone(whole)
        self.assertEqual(whole['total_cut_count'], 0)
        # Kui pikkust on vaja mõõtu lõigata, peab sellel teljel trimmi varu olema.
        self.assertIsNone(build_orientation_result(LARGE_BLADE, inp(100, 105, 100, 100, 1), 100, 100))
        needed_length = 100 + LARGE_BLADE['kerf_mm'] + TRIM_REMOVAL_MM
        self.assertIsNotNone(build_orientation_result(LARGE_BLADE, inp(100, needed_length, 100, 100, 1), 100, 100))

    def test_full_length_strips_do_not_trim_the_untouched_length(self):
        result = build_orientation_result(
            LARGE_BLADE,
            CalcInput(5, 1000, 2000, 100, 2000, 100),
            100,
            2000,
        )
        self.assertIsNotNone(result)
        self.assertEqual(result['trim_length_allowance_mm'], 0)
        self.assertEqual(result['cross_cut_count'], 0)
        self.assertEqual(result['partial_stock_length_mm'], 2000)

    def test_material_need_full_sheet_plus_smallest_piece(self):
        size = 2 * 100 + LARGE_BLADE['kerf_mm'] + LARGE_BLADE['kerf_mm'] + TRIM_REMOVAL_MM
        result = build_orientation_result(LARGE_BLADE, inp(size, size, 100, 100, 5), 100, 100)
        self.assertEqual(result['full_sheet_count'], 1)
        self.assertEqual(result['partial_piece_count'], 1)
        lines = material_need_lines(result)
        self.assertIn('1 täisplaat', lines[0])
        self.assertIn('Sobiva jäägi minimaalne mõõt', lines[1])

    def test_less_than_capacity_uses_only_minimum_piece(self):
        result = build_orientation_result(LARGE_BLADE, inp(1000, 3000, 100, 100, 5), 100, 100)
        self.assertEqual(result['full_sheet_count'], 0)
        self.assertEqual(result['partial_sheet_count'], 1)
        self.assertLess(result['material_needed_area_m2'], 3.0)

    def test_exact_capacity_uses_one_full_sheet(self):
        result = build_orientation_result(LARGE_BLADE, inp(1000, 3000, 100, 100, 1), 100, 100)
        exact = build_orientation_result(LARGE_BLADE, inp(1000, 3000, 100, 100, result['pieces_per_sheet']), 100, 100)
        self.assertEqual(exact['full_sheet_count'], 1)
        self.assertEqual(exact['partial_sheet_count'], 0)

    def test_precision_boundaries_and_total_time(self):
        self.assertEqual(quality_control_seconds_per_detail(200, 1000), 15)
        self.assertEqual(quality_control_seconds_per_detail(200, 1000.1), 25)
        self.assertEqual(quality_control_seconds_per_detail(200, 2000), 25)
        self.assertEqual(quality_control_seconds_per_detail(200, 2000.1), 35)
        normal = build_best_result_for_blade(LARGE_BLADE, inp(count=10, precision=False))
        precise = build_best_result_for_blade(LARGE_BLADE, inp(count=10, precision=True))
        self.assertEqual(precise['quality_control_sec'], 150)
        self.assertEqual(precise['precision_setup_sec'], 30 * 60)
        self.assertAlmostEqual(precise['total_sec'] - normal['total_sec'], PRECISION_SETUP_SEC + 150)
        self.assertGreaterEqual(precise['work_fee_eur'] - normal['work_fee_eur'], 20.0)
        self.assertGreaterEqual(precise['billable_sec'], precise['total_sec'] * 1.05)
        self.assertTrue(precise['small_precision_fixed_price'])

    def test_narrow_strip_machine_rules_and_time_factor(self):
        below_minimum = CalcInput(2, 100, 1000, 3.9, 1000, 1)
        below_minimum_errors = validate_input_values(below_minimum)
        self.assertTrue(any('Minimaalne saega lõigatav riba' in error for error in below_minimum_errors))
        self.assertTrue(any('soovitame tellida freesist' in error for error in below_minimum_errors))
        too_thin = CalcInput(1, 100, 1000, 4, 1000, 1)
        self.assertTrue(any('alates 2 mm materjalipaksusest' in error for error in validate_input_values(too_thin)))

        narrow = build_best_result_for_blade(LARGE_BLADE, CalcInput(2, 100, 1000, 4, 1000, 5))
        self.assertIsNotNone(narrow)
        self.assertEqual(narrow['detail_width_mm'], 4)
        self.assertEqual(narrow['narrow_strip_time_factor'], 2.0)
        self.assertEqual(narrow['setup_sec'], BASE_SETUP_SEC * 2)

        normal = build_best_result_for_blade(LARGE_BLADE, CalcInput(2, 100, 1000, 6.1, 1000, 5))
        self.assertIsNotNone(normal)
        self.assertEqual(normal['narrow_strip_time_factor'], 1.0)
        self.assertEqual(normal['setup_sec'], BASE_SETUP_SEC)

        narrow_precise = build_best_result_for_blade(LARGE_BLADE, CalcInput(2, 100, 1000, 4, 1000, 5, precision_cut=True))
        self.assertEqual(narrow_precise['precision_setup_sec'], PRECISION_SETUP_SEC * 2)

    def test_95_mm_is_supported_and_80_mm_doubles_base_work(self):
        at_95 = build_best_result_for_blade(LARGE_BLADE, CalcInput(95, 1000, 2000, 100, 100, 1))
        self.assertIsNotNone(at_95)
        self.assertEqual(MAX_MATERIAL_THICKNESS_MM, 95)
        self.assertEqual(at_95['thick_material_time_factor'], THICK_MATERIAL_TIME_FACTOR)
        self.assertTrue(any('0–95 mm' in error for error in validate_input_values(CalcInput(95.1, 1000, 2000, 100, 100, 1))))

        below = build_best_result_for_blade(LARGE_BLADE, CalcInput(79.9, 100, 2000, 50, 2000, 1))
        doubled = build_best_result_for_blade(LARGE_BLADE, CalcInput(80, 100, 2000, 50, 2000, 1))
        self.assertAlmostEqual(doubled['setup_sec'], below['setup_sec'] * 2)
        self.assertAlmostEqual(doubled['cutting_time_sec'], below['cutting_time_sec'] * 2)
        self.assertAlmostEqual(doubled['handling_sec'], below['handling_sec'] * 2)

    def test_dust_bag_time_only_for_full_length_ripping(self):
        self.assertEqual(dust_bag_change_count(15, 20, True), 0)
        self.assertEqual(dust_bag_change_count(30, 8, True), 0)
        self.assertEqual(dust_bag_change_count(30, 12, True), 1)
        self.assertEqual(dust_bag_change_count(60, 5, True), 1)
        self.assertEqual(dust_bag_change_count(60, 6, True), 2)
        self.assertEqual(dust_bag_change_count(60, 20, False), 0)

        standard = build_best_result_for_blade(LARGE_BLADE, CalcInput(30, 100, 2000, 50, 2000, 12))
        self.assertTrue(standard['full_length_ripping'])
        self.assertEqual(standard['dust_bag_change_count'], 1)
        self.assertEqual(standard['dust_bag_change_sec'], DUST_BAG_CHANGE_SEC)

        thick = build_best_result_for_blade(LARGE_BLADE, CalcInput(60, 100, 2000, 50, 2000, 5))
        self.assertEqual(thick['dust_bag_change_count'], 1)
        cross_cut = build_best_result_for_blade(LARGE_BLADE, CalcInput(60, 100, 2000, 50, 1000, 20))
        self.assertFalse(cross_cut['full_length_ripping'])
        self.assertEqual(cross_cut['dust_bag_change_count'], 0)

    def test_dust_bag_boundaries_for_every_catalog_thickness(self):
        thicknesses = sorted({row['thickness_mm'] for row in load_sheet_catalog()})
        checked = 0
        for thickness in thicknesses:
            for stock_count in range(1, 41):
                if thickness < 20:
                    expected = 0
                elif thickness < 50:
                    expected = max(0, (stock_count - 1) // 8)
                else:
                    expected = stock_count // 3
                self.assertEqual(
                    dust_bag_change_count(thickness, stock_count, True),
                    expected,
                    (thickness, stock_count),
                )
                self.assertEqual(dust_bag_change_count(thickness, stock_count, False), 0)
                checked += 1
        self.assertGreater(checked, 1000)

    def test_every_long_catalog_format_applies_exact_dust_bag_rule(self):
        checked = 0
        seen = set()
        for row in load_sheet_catalog():
            if (
                row['width_mm'] is None
                or row['length_mm'] < 2000
                or sheet_compatibility(row['width_mm'], row['length_mm']) != 'direct'
            ):
                continue
            key = (
                row['group'], row['material'], row['thickness_mm'],
                row['width_mm'], row['length_mm'],
            )
            if key in seen:
                continue
            seen.add(key)
            strip_width = max(10.0, min(50.0, row['width_mm'] / 4.0))
            one_stock = build_orientation_result(
                LARGE_BLADE,
                CalcInput(
                    row['thickness_mm'], row['width_mm'], row['length_mm'],
                    strip_width, row['length_mm'], 1,
                ),
                strip_width,
                row['length_mm'],
            )
            self.assertIsNotNone(one_stock, key)
            capacity = one_stock['pieces_per_sheet']
            for stock_count in (1, 3, 8, 9, 12, 17):
                result = build_orientation_result(
                    LARGE_BLADE,
                    CalcInput(
                        row['thickness_mm'], row['width_mm'], row['length_mm'],
                        strip_width, row['length_mm'], capacity * stock_count,
                    ),
                    strip_width,
                    row['length_mm'],
                )
                self.assertTrue(result['full_length_ripping'], key)
                self.assertEqual(result['opened_sheet_count'], stock_count, key)
                self.assertEqual(
                    result['dust_bag_change_count'],
                    dust_bag_change_count(row['thickness_mm'], stock_count, True),
                    key,
                )
                self.assertEqual(
                    result['dust_bag_change_sec'],
                    result['dust_bag_change_count'] * DUST_BAG_CHANGE_SEC,
                    key,
                )
                checked += 1
        self.assertGreater(checked, 3000)

    def test_small_blade_is_limited_to_25_mm_material(self):
        self.assertEqual(SMALL_BLADE['max_stack_mm'], 25.0)
        self.assertEqual(SMALL_BLADE['max_single_thickness_mm'], 25.0)
        at_limit = build_best_result_for_blade(
            SMALL_BLADE, CalcInput(25, 1000, 2000, 100, 100, 10)
        )
        above_limit = build_best_result_for_blade(
            SMALL_BLADE, CalcInput(25.1, 1000, 2000, 100, 100, 10)
        )
        self.assertIsNotNone(at_limit)
        self.assertIsNone(above_limit)
        stacked = build_best_result_for_blade(
            SMALL_BLADE, CalcInput(6, 1000, 2000, 100, 100, 100, precision_cut=True)
        )
        self.assertEqual(stacked['max_stack_layers'], 4)

    def test_precision_sampling_is_smooth_at_99_and_101_details(self):
        self.assertEqual(quality_control_check_count(99), 33)
        self.assertEqual(quality_control_check_count(101), 34)
        self.assertEqual(quality_control_check_count(99) * 15, 8 * 60 + 15)
        self.assertEqual(quality_control_check_count(101) * 15, 8 * 60 + 30)

    def test_stacked_sheets_share_one_inspection_unit_per_cut_position(self):
        size = 40 + LARGE_BLADE['kerf_mm'] + TRIM_REMOVAL_MM
        result = build_orientation_result(
            LARGE_BLADE,
            inp(size, size, 40, 40, 4, precision=True),
            40,
            40,
        )
        self.assertEqual(result['pieces_per_sheet'], 1)
        self.assertEqual(result['full_sheet_count'], 4)
        self.assertEqual(result['max_stack_layers'], 4)
        self.assertEqual(result['quality_control_unit_count'], 1)
        self.assertEqual(result['quality_control_check_count'], 1)
        self.assertEqual(result['quality_control_sec'], 15)

    def test_work_fee_is_fixed_60_eur_per_hour(self):
        result = build_best_result_for_blade(LARGE_BLADE, inp())
        self.assertEqual(result['hourly_rate_eur'], SAW_HOURLY_RATE_EUR)
        self.assertAlmostEqual(result['work_fee_eur'], result['billable_sec'] / 60.0, places=6)
        self.assertGreaterEqual(result['billable_sec'], result['total_sec'] * 1.05)
        self.assertLess(result['billable_sec'], result['total_sec'] * 1.05 + 5 * 60)
        self.assertEqual(result['billable_sec'] % (5 * 60), 0)

    def test_public_quantity_limit_and_monotonic_total_price(self):
        too_many = CalcInput(10, 1200, 1600, 250, 400, MAX_DETAIL_COUNT + 1)
        self.assertTrue(any('10 000 detaili' in error for error in validate_input_values(too_many)))

        previous_fee = 0.0
        for count in range(1, 121):
            calculation_input = CalcInput(10, 1200, 1600, 250, 400, count)
            result = apply_monotonic_quote_floor(
                build_best_result(calculation_input), calculation_input
            )
            self.assertGreaterEqual(result['work_fee_eur'], previous_fee)
            previous_fee = result['work_fee_eur']

    def test_handling_is_20_seconds_per_detail_with_stock_minimum(self):
        large_series = build_best_result_for_blade(
            SMALL_BLADE, CalcInput(10, 1500, 3000, 55, 2740, 500)
        )
        self.assertEqual(HANDLING_PER_DETAIL_SEC, 20)
        self.assertEqual(large_series['handling_base_sec'], 500 * HANDLING_PER_DETAIL_SEC)
        self.assertEqual(large_series['handling_sec'], 500 * HANDLING_PER_DETAIL_SEC)
        self.assertLess(large_series['handling_sec'], large_series['cutting_time_sec'])

        one_large_detail = build_best_result_for_blade(
            LARGE_BLADE, CalcInput(10, 1500, 3000, 1400, 2900, 1)
        )
        self.assertEqual(one_large_detail['handling_sec'], BASE_HANDLING_PER_STOCK_SEC)

    def test_handling_keeps_narrow_and_thick_time_factors(self):
        normal = build_best_result_for_blade(
            LARGE_BLADE, CalcInput(10, 1000, 2000, 10, 2000, 10)
        )
        narrow = build_best_result_for_blade(
            LARGE_BLADE, CalcInput(10, 1000, 2000, 4, 2000, 10)
        )
        thick = build_best_result_for_blade(
            LARGE_BLADE, CalcInput(80, 1000, 2000, 10, 2000, 10)
        )
        self.assertEqual(narrow['handling_sec'], normal['handling_sec'] * 2)
        self.assertEqual(thick['handling_sec'], normal['handling_sec'] * 2)

    def test_rotation_is_avoided_for_long_detail_when_material_equal(self):
        # Ruudukujulisel toorikul on mõlemad suunad sama materjalikuluga.
        result = build_best_result_for_blade(LARGE_BLADE, inp(1400, 1400, 200, 1200, 2))
        self.assertFalse(result.get('rotated'))

    def test_area_invariants_on_random_inputs(self):
        rng = random.Random(42)
        checked = 0
        for _ in range(1500):
            raw_w = rng.uniform(200, 2050)
            raw_l = rng.uniform(200, 3050)
            dw = rng.uniform(10, raw_w)
            dl = rng.uniform(10, raw_l)
            result = build_orientation_result(LARGE_BLADE, inp(raw_w, raw_l, dw, dl, rng.randint(1, 500)), dw, dl)
            if result is None:
                continue
            checked += 1
            self.assertGreaterEqual(result['material_needed_area_m2'] + 1e-9, result['net_detail_area_m2'])
            self.assertGreaterEqual(result['work_fee_eur'], 0)
            self.assertGreaterEqual(result['total_cut_count'], 0)
        self.assertGreater(checked, 500)


class PresentationAndHistoryTests(unittest.TestCase):
    def setUp(self):
        self.result = build_best_result_for_blade(LARGE_BLADE, inp())

    def test_scheme_has_no_axis_ticks(self):
        figures = build_scheme_figures(self.result)
        self.assertTrue(figures)
        for figure in figures:
            for axis in figure.axes:
                self.assertFalse(axis.axison)
            plt.close(figure)

    def test_compatibility_scheme_separates_materials(self):
        figure = build_scheme_figure(self.result)
        expected = int(bool(self.result['full_sheet_count'])) + int(bool(self.result['partial_sheet_count']))
        self.assertEqual(len(figure.axes), expected)
        plt.close(figure)

    def test_print_sheet_has_operator_info_but_no_price(self):
        html = build_printable_cut_sheet(self.result)
        self.assertIn('Prindi lõikeleht', html)
        self.assertIn('Materjali väljastus', html)
        self.assertIn('Tööjärjekord', html)
        self.assertIn('Lõikeskeem', html)
        self.assertIn('<svg', html)
        self.assertIn('Enne täisplaadi lõikust kontrolli, kas sobivat jääki pole riiulis või boksides.', html)
        self.assertNotIn('ära ava', html)
        self.assertNotIn('Tööraha', html)
        self.assertNotIn('60 €/h', html)
        self.assertIn('Too alus või käru sae juurde', html)

    def test_print_sheet_does_not_claim_full_sheet_when_only_offcut_is_needed(self):
        html = build_printable_cut_sheet(self.result)
        self.assertEqual(self.result['full_sheet_count'], 0)
        self.assertIn('<strong>Sobiv jääk:</strong>', html)
        self.assertNotIn('<strong>Täisplaat:</strong>', html)

    def test_precision_work_order_contains_setup_and_control_plan(self):
        precise = build_best_result_for_blade(LARGE_BLADE, inp(count=101, precision=True))
        html = build_printable_cut_sheet(precise)
        self.assertIn('Täppislõikuse seadistus:</strong> 30 minutit', html)
        self.assertIn('Kontrolli esimesed 25 kontrollühikut', html)
        self.assertIn('kontrolli iga 10. järel', html)
        self.assertIn('kontrolli iga 25. järel', html)
        self.assertIn('Kontrolli alati viimane kontrollühik', html)
        self.assertIn('kontrolli ühe ribapakina', html)

    def test_work_order_contains_dust_bag_changes(self):
        result = build_best_result_for_blade(LARGE_BLADE, CalcInput(60, 100, 2000, 50, 2000, 5))
        html = build_printable_cut_sheet(result)
        self.assertIn('laastukotte 1 korda', html)
        self.assertIn('10 minutit vahetuse kohta', html)

    def test_work_order_contains_material_and_thickness(self):
        full_sheet = self.result.copy()
        full_sheet['material_name'] = 'POM-C'
        html = build_printable_cut_sheet(full_sheet)
        self.assertIn('<strong>Lähtematerjal:</strong> POM-C, 18 mm', html)

        remnant = build_best_result_for_blade(
            LARGE_BLADE,
            CalcInput(12, 1000, 2000, 100, 100, 10, stock_source='Jääk', max_stock_count=1),
        )
        remnant_html = build_printable_cut_sheet(remnant)
        self.assertIn('<strong>Lähtematerjal:</strong> Jääk, 12 mm', remnant_html)

    def test_query_memory_includes_new_fields(self):
        query_id, row = build_query_memory_row(self.result)
        self.assertEqual(row['paring_id'], query_id)
        self.assertIn('materjali_vajadus', row)
        self.assertIn('kvaliteedikontroll_aeg_sek', row)
        self.assertIn('tooraha_eur', row)
        self.assertIn('laastukoti_vahetuste_arv', row)
        self.assertIn('paksu_materjali_ajategur', row)
        self.assertIn('hinnastusaeg_sek', row)
        self.assertIn('hinnastuspuhver_sek', row)

    def test_old_session_result_without_qc_count_remains_saveable(self):
        old_result = self.result.copy()
        old_result.pop('quality_control_check_count', None)
        query_id, row = build_query_memory_row(old_result)
        self.assertEqual(row['paring_id'], query_id)
        self.assertEqual(row['kvaliteedikontrollide_arv'], 0)

    def test_old_history_is_normalized(self):
        import pandas as pd
        normalized = normalize_history_df(pd.DataFrame([{'kuupaev': '2026-01-01', 'avatud_plaadid': 2}]))
        self.assertIn('tooraha_eur', normalized.columns)
        self.assertEqual(len(normalized), 1)

    def test_blank_actual_time_remains_blank(self):
        row = build_pending_save_row({}, self.result, self.result['blade']['blade'], False, None, None)
        self.assertIsNone(row['tegelik_aeg_sek'])


if __name__ == '__main__':
    unittest.main()
