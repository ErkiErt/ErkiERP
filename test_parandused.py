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
            app.selectbox[0].select('Kulumiskindel plast').run(timeout=30)
            app.selectbox[1].select('PE500 (PE-HMW)').run(timeout=30)
            app.selectbox[2].select(20.0).run(timeout=30)
            app.selectbox[3].select('1000|2000').run(timeout=30)
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
            app.selectbox[0].select('Konstruktsioonplast').run(timeout=30)
            app.selectbox[1].select('PE300 (PE-HD)').run(timeout=30)
            app.selectbox[2].select(10.0).run(timeout=30)
            app.selectbox[3].select('1500|3000').run(timeout=30)
            app.text_input[0].input('55').run(timeout=30)
            app.text_input[1].input('2740').run(timeout=30)
            app.number_input[0].set_value(500).run(timeout=30)
            next(button for button in app.button if button.label == 'Arvuta pakkumine').click().run(timeout=30)

            self.assertFalse(app.exception)
            result = app.session_state['best_result']
            self.assertEqual(app.title[0].value, 'Erki Saagimise kalkulaator')
            self.assertEqual(result['handling_sec'], 500 * 20)
            self.assertLess(result['handling_sec'], result['cutting_time_sec'])
            # Detail (2740 mm) on lühem kui plaat (3000 mm), seega valitakse
            # jäägisäästlik cross-first strateegia: enne lõigatakse detail
            # pikkusesse (üks täislaiune ristlõige, mis jätab kasutatava
            # 1500×253 mm otsajäägi) ja alles siis ribastatakse. See lühendab
            # pikilõike teekonda ja alandab töötasu 410 → 390 minutit.
            self.assertEqual(result['cut_strategy'], 'cross')
            self.assertEqual(result['billable_sec'], 390 * 60)
            self.assertEqual(result['work_fee_eur'], 390.0)
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
                app.selectbox[0].select('Kulumiskindel plast').run(timeout=30)
                app.selectbox[1].select('PE500 (PE-HMW)').run(timeout=30)
                app.selectbox[2].select(20.0).run(timeout=30)
                app.selectbox[3].select('1000|2000').run(timeout=30)
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


class SelectionStateTests(unittest.TestCase):
    """Regressioonitestid plaadi/jäägi valiku session_state ahelale.

    Kaetud on viis valikujärjestust ning nõue, et iga eelneva sammu muutmine
    teeb varem arvutatud pakkumise kehtetuks (vana tulemus ei jää ripakile).
    """

    def _select_full_sheet(self, app):
        next(button for button in app.button if button.key == 'choose_stock_Täisplaat').click().run(timeout=30)
        app.selectbox[0].select('Kulumiskindel plast').run(timeout=30)
        app.selectbox[1].select('PE500 (PE-HMW)').run(timeout=30)
        app.selectbox[2].select(20.0).run(timeout=30)
        app.selectbox[3].select('1000|2000').run(timeout=30)
        return app

    def _calculate(self, app):
        next(button for button in app.button if button.label == 'Arvuta pakkumine').click().run(timeout=30)
        return app

    def test_sequence_1_material_thickness_plate_normal(self):
        # 1. materjal → paksus → plaat (normaaljuhtum): tulemus arvutub õigesti.
        app = AppTest.from_file('app.py').run(timeout=30)
        self._select_full_sheet(app)
        app.text_input[0].input('100').run(timeout=30)
        app.text_input[1].input('200').run(timeout=30)
        app.number_input[0].set_value(10).run(timeout=30)
        self._calculate(app)
        self.assertFalse(app.exception)
        result = app.session_state['best_result']
        self.assertIsNotNone(result)
        self.assertEqual(result['stock_source'], 'Täisplaat')
        self.assertEqual(result['thickness_mm'], 20.0)
        self.assertEqual(result['material_name'], 'PE500 (PE-HMW)')
        self.assertEqual(result['detail_count'], 10)

    def test_sequence_2_material_then_remnant(self):
        # 2. materjal → jääk: kasutaja valib olemasoleva jäägi laost.
        app = AppTest.from_file('app.py').run(timeout=30)
        next(button for button in app.button if button.key == 'choose_stock_Jääk').click().run(timeout=30)
        for widget, value in zip(app.text_input, ('5', '2000', '3000', '100', '200')):
            widget.input(value).run(timeout=30)
        app.number_input[0].set_value(10).run(timeout=30)
        self._calculate(app)
        self.assertFalse(app.exception)
        result = app.session_state['best_result']
        self.assertIsNotNone(result)
        self.assertEqual(result['stock_source'], 'Jääk')
        self.assertEqual(result['thickness_mm'], 5.0)
        self.assertEqual(result['raw_width_mm'], 2000.0)
        self.assertEqual(result['raw_length_mm'], 3000.0)

    def test_sequence_3_remnant_back_to_plate_clears_result(self):
        # 3. jääk → tagasi plaadile: jäägist loobumine kustutab vana tulemuse
        # ja tühjendab jäägi mõõdud, et miski ei jääks ripakile.
        app = AppTest.from_file('app.py').run(timeout=30)
        next(button for button in app.button if button.key == 'choose_stock_Jääk').click().run(timeout=30)
        for widget, value in zip(app.text_input, ('5', '2000', '3000', '100', '200')):
            widget.input(value).run(timeout=30)
        app.number_input[0].set_value(10).run(timeout=30)
        self._calculate(app)
        self.assertIsNotNone(app.session_state['best_result'])

        next(button for button in app.button if button.key == 'choose_stock_Täisplaat').click().run(timeout=30)
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state['stock_source'], 'Täisplaat')
        self.assertIsNone(app.session_state['best_result'])
        self.assertEqual(app.session_state['raw_width_mm'], '')
        self.assertEqual(app.session_state['raw_length_mm'], '')
        self.assertIsNone(app.session_state['material_group'])

    def test_sequence_4_changing_quantity_recomputes(self):
        # 4. koguse muutmine PÄRAST valikut peab ümber arvutama, mitte hoidma
        # vana tulemust.
        app = AppTest.from_file('app.py').run(timeout=30)
        self._select_full_sheet(app)
        app.text_input[0].input('100').run(timeout=30)
        app.text_input[1].input('200').run(timeout=30)
        app.number_input[0].set_value(10).run(timeout=30)
        self._calculate(app)
        first = app.session_state['best_result']
        self.assertEqual(first['detail_count'], 10)
        first_fee = first['work_fee_eur']

        app.number_input[0].set_value(50).run(timeout=30)
        self._calculate(app)
        second = app.session_state['best_result']
        self.assertEqual(second['detail_count'], 50)
        self.assertGreaterEqual(second['work_fee_eur'], first_fee)

    def test_sequence_5_changing_dimensions_recomputes(self):
        # 5. mõõtude muutmine PÄRAST valikut — vana tulemus ei tohi rippuda.
        app = AppTest.from_file('app.py').run(timeout=30)
        self._select_full_sheet(app)
        app.text_input[0].input('100').run(timeout=30)
        app.text_input[1].input('200').run(timeout=30)
        app.number_input[0].set_value(10).run(timeout=30)
        self._calculate(app)
        first = app.session_state['best_result']
        self.assertEqual(first['original_detail_width_mm'], 100.0)
        self.assertEqual(first['original_detail_length_mm'], 200.0)

        app.text_input[0].input('250').run(timeout=30)
        app.text_input[1].input('400').run(timeout=30)
        self._calculate(app)
        second = app.session_state['best_result']
        self.assertEqual(second['original_detail_width_mm'], 250.0)
        self.assertEqual(second['original_detail_length_mm'], 400.0)

    def test_upstream_change_invalidates_stale_result(self):
        # Iga eelneva valikusammu muutmine teeb arvutatud tulemuse kehtetuks.
        for change in ('group', 'material', 'thickness', 'format'):
            with self.subTest(change=change):
                app = AppTest.from_file('app.py').run(timeout=30)
                self._select_full_sheet(app)
                app.text_input[0].input('100').run(timeout=30)
                app.text_input[1].input('200').run(timeout=30)
                app.number_input[0].set_value(10).run(timeout=30)
                self._calculate(app)
                self.assertIsNotNone(app.session_state['best_result'])
                if change == 'group':
                    app.selectbox[0].select('Konstruktsioonplast').run(timeout=30)
                elif change == 'material':
                    app.selectbox[1].select('PE1000 (PE-UHMW)').run(timeout=30)
                elif change == 'thickness':
                    app.selectbox[2].select(30.0).run(timeout=30)
                else:
                    app.selectbox[3].select('1000|3000').run(timeout=30)
                self.assertIsNone(app.session_state['best_result'], change)


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


class SalesSummaryUiTests(unittest.TestCase):
    """UI-testid pakkumise kokkuvõtte selguse ja materjalivaliku kompaktsuse kohta."""

    def _full_sheet_quote(self):
        query_file = Path('data/arvutusparingud.csv')
        self._original_queries = query_file.read_bytes() if query_file.exists() else None
        self._query_file = query_file
        app = AppTest.from_file('app.py').run(timeout=30)
        next(button for button in app.button if button.key == 'choose_stock_Täisplaat').click().run(timeout=30)
        app.selectbox[0].select('Kulumiskindel plast').run(timeout=30)
        app.selectbox[1].select('PE500 (PE-HMW)').run(timeout=30)
        app.selectbox[2].select(20.0).run(timeout=30)
        app.selectbox[3].select('1000|2000').run(timeout=30)
        return app

    def _restore(self):
        original = getattr(self, '_original_queries', None)
        query_file = getattr(self, '_query_file', None)
        if query_file is None:
            return
        if original is None:
            query_file.unlink(missing_ok=True)
        else:
            query_file.write_bytes(original)

    def test_summary_shows_separate_work_material_and_total(self):
        try:
            app = self._full_sheet_quote()
            app.text_input[0].input('100').run(timeout=30)
            app.text_input[1].input('200').run(timeout=30)
            app.number_input[0].set_value(10).run(timeout=30)
            next(button for button in app.button if button.label == 'Arvuta pakkumine').click().run(timeout=30)
            self.assertFalse(app.exception)
            metric_labels = [item.label for item in app.metric]
            self.assertIn('Tööraha (saagimine, ei sisalda materjali)', metric_labels)
            self.assertIn('Materjali kogus', metric_labels)
            self.assertIn('Hind kokku (ilma materjalita)', metric_labels)
            captions = '\n'.join(item.value for item in app.caption)
            self.assertIn('materjali €/m² hinda kalkulaator ei arvuta', captions.lower())
        finally:
            self._restore()

    def test_material_description_hidden_until_material_selected(self):
        try:
            app = AppTest.from_file('app.py').run(timeout=30)
            next(button for button in app.button if button.key == 'choose_stock_Täisplaat').click().run(timeout=30)
            # Enne materjali/paksuse valikut ei tohi kirjelduse infosektsiooni olla.
            self.assertFalse(any(exp.label == 'Materjali kirjeldus ja artiklid' for exp in app.expander))
            app.selectbox[0].select('Kulumiskindel plast').run(timeout=30)
            app.selectbox[1].select('PE500 (PE-HMW)').run(timeout=30)
            app.selectbox[2].select(20.0).run(timeout=30)
            # Materjal ja paksus valitud → kirjelduse infosektsioon on olemas.
            self.assertTrue(any(exp.label == 'Materjali kirjeldus ja artiklid' for exp in app.expander))
        finally:
            self._restore()


class OffcutStrategyTests(unittest.TestCase):
    """Regressioonitestid jäägisäästliku lõikestrateegia jaoks."""

    def test_short_detail_uses_cross_first_and_leaves_full_width_remnant(self):
        # Detail on plaadist selgelt lühem → tuleks enne pikkusesse lõigata,
        # et suur täislaiune otsajääk eralduks tervikuna.
        from core import choose_offcut_strategy, is_usable_offcut
        result = build_orientation_result(
            LARGE_BLADE, CalcInput(10, 1500, 3000, 55, 2000, 24), 55, 2000
        )
        self.assertIsNotNone(result)
        self.assertEqual(result['cut_strategy'], 'cross')
        offcuts = result['full_offcuts']
        end = next((o for o in offcuts if o['name'] == 'Otsajääk'), None)
        self.assertIsNotNone(end)
        # Otsajääk on täislaiune (kogu plaadi laius), mitte kitsas riba.
        self.assertAlmostEqual(end['width_mm'], 1500, delta=1.0)
        self.assertTrue(is_usable_offcut(end))
        # Suurim taaskasutatav jääk on määratud ja kasutatav.
        self.assertIsNotNone(result['largest_usable_offcut'])
        self.assertTrue(is_usable_offcut(result['largest_usable_offcut']))

    def test_area_is_invariant_between_strategies(self):
        # Mõlema strateegia jäägi kogupindala peab olema identne — muutub
        # ainult kuju, mitte materjalikulu.
        from core import _strategy_offcuts
        cross = _strategy_offcuts(1500, 3000, 1455, 2747, 'cross')
        rip = _strategy_offcuts(1500, 3000, 1455, 2747, 'rip')
        self.assertAlmostEqual(
            sum(o['area_m2'] for o in cross),
            sum(o['area_m2'] for o in rip),
            places=6,
        )

    def test_full_length_detail_has_no_end_remnant_and_time_unchanged(self):
        # Täispikk detail (detail_l == raw_l): otsajääki pole, strateegia ei tohi
        # lõikeaega muuta võrreldes vana rip-first käitumisega.
        below = build_best_result_for_blade(LARGE_BLADE, CalcInput(79.9, 100, 2000, 50, 2000, 1))
        doubled = build_best_result_for_blade(LARGE_BLADE, CalcInput(80, 100, 2000, 50, 2000, 1))
        self.assertAlmostEqual(doubled['cutting_time_sec'], below['cutting_time_sec'] * 2)
        # Terve otsariba puudub, seega yksik jääk on ainult küljeriba.
        self.assertTrue(all(o['name'] != 'Otsajääk' for o in below['full_offcuts']))

    def test_sliver_offcut_is_not_counted_as_usable(self):
        from core import is_usable_offcut
        sliver = {'name': 'Küljeriba', 'width_mm': 20.0, 'length_mm': 3000.0,
                  'area_m2': 20.0 * 3000.0 / 1_000_000.0}
        self.assertFalse(is_usable_offcut(sliver))
        good = {'name': 'Otsajääk', 'width_mm': 1500.0, 'length_mm': 300.0,
                'area_m2': 1500.0 * 300.0 / 1_000_000.0}
        self.assertTrue(is_usable_offcut(good))

    def test_remnant_stock_produces_partial_offcuts(self):
        # Jäägist (stock_source='Jääk') lõigates peab süsteem samuti arvutama,
        # milline osa jäägist jääb taaskasutatavaks.
        result = build_best_result_for_blade(
            LARGE_BLADE,
            CalcInput(12, 1000, 2000, 200, 300, 4, stock_source='Jääk', max_stock_count=1),
        )
        self.assertIsNotNone(result)
        self.assertEqual(result['stock_source'], 'Jääk')
        self.assertIn('cut_strategy', result)

    def test_work_order_reflects_cross_first_strategy(self):
        from utils import work_order_steps
        result = build_orientation_result(
            LARGE_BLADE, CalcInput(10, 1500, 3000, 55, 2000, 24), 55, 2000
        )
        steps = ' '.join(work_order_steps(result))
        self.assertEqual(result['cut_strategy'], 'cross')
        self.assertIn('esmalt pikkusesse', steps)

    def test_sort_prefers_larger_usable_offcut_on_area_tie(self):
        # Sama materjalikulu ja plaadiarvu korral eelistatakse suuremat
        # taaskasutatavat jääki.
        from core import result_sort_key
        base = build_best_result_for_blade(LARGE_BLADE, inp())
        a = dict(base)
        b = dict(base)
        a['largest_usable_offcut'] = {'name': 'Otsajääk', 'width_mm': 1500, 'length_mm': 500, 'area_m2': 0.75}
        b['largest_usable_offcut'] = {'name': 'Otsajääk', 'width_mm': 1500, 'length_mm': 200, 'area_m2': 0.30}
        self.assertLess(result_sort_key(a), result_sort_key(b))


class ArchitectureLayerTests(unittest.TestCase):
    """Testid kihilise arhitektuuri jaoks: äriloogikat saab kontrollida
    Streamlitit käivitamata ning sõltuvussuund ui → application → domain püsib.
    """

    def test_domain_calculations_do_not_import_streamlit(self):
        import subprocess
        import sys
        # Eraldi protsessis: domeenikihi import ei tohi Streamlitit kaasa tuua.
        result = subprocess.run(
            [sys.executable, '-c',
             'import sys, domain.calculations; '
             'assert "streamlit" not in sys.modules, "domeen ei tohi Streamlitit importida"'],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_domain_and_compat_core_expose_same_engine(self):
        import domain.calculations as calculations
        import core
        # Compat-kiht re-ekspordib domeeni sama funktsiooni, mitte koopiat.
        self.assertIs(core.build_best_result, calculations.build_best_result)
        self.assertIs(core.CalcInput, calculations.CalcInput)

    def test_repositories_back_the_compat_material_module(self):
        import repositories.material_catalog as catalog
        import materials
        self.assertIs(materials.load_sheet_catalog, catalog.load_sheet_catalog)
        self.assertTrue(catalog.load_sheet_catalog())

    def test_quote_service_computes_best_result_without_ui(self):
        from application.quote_service import compute_quote, single_stock_capacity
        best, blade_results = compute_quote(inp(count=10))
        self.assertIsNotNone(best)
        self.assertEqual(best['detail_count'], 10)
        # Ketaste alternatiividele on lisatud põhjendused.
        self.assertTrue(any(r and 'blade_reason' in r for r in blade_results))
        # Hinnastuse alammäär on rakendatud (hinnastusaeg ei alane tööajast).
        self.assertGreaterEqual(best['billable_sec'], best['total_sec'] * 1.05)

    def test_quote_service_returns_none_when_detail_does_not_fit(self):
        from application.quote_service import compute_quote
        too_big = CalcInput(5, 100, 100, 500, 500, 1, stock_source='Jääk', max_stock_count=1)
        best, _ = compute_quote(too_big)
        self.assertIsNone(best)

    def test_quote_service_single_stock_capacity_matches_domain(self):
        from application.quote_service import single_stock_capacity
        remnant = CalcInput(5, 2000, 3000, 100, 2000, 100, stock_source='Jääk', max_stock_count=1)
        self.assertEqual(single_stock_capacity(remnant), max_single_stock_capacity(remnant))

    def test_price_summary_separates_work_material_and_total(self):
        from application.quote_service import build_price_summary, compute_quote
        best, _ = compute_quote(inp(count=10))
        summary = build_price_summary(best)
        # Tavatöös pole täpsuslõikuse lisatasu: tööraha == põhitööraha == kokku.
        self.assertFalse(summary['has_extra_work'])
        self.assertEqual(summary['precision_surcharge_eur'], 0.0)
        self.assertAlmostEqual(summary['base_work_fee_eur'], best['work_fee_eur'], places=6)
        self.assertAlmostEqual(summary['total_eur'], best['total_estimated_cost_eur'], places=6)
        # Materjali €/m² hinda andmestikus pole, seega kuvatakse pindala ja
        # märgitakse, et hind kokku ei sisalda materjali maksumust.
        self.assertFalse(summary['material_cost_known'])
        self.assertFalse(summary['total_includes_material'])
        self.assertEqual(summary['material_area_m2'], best['material_needed_area_m2'])

    def test_price_summary_shows_precision_extra_work_separately(self):
        from application.quote_service import build_price_summary, compute_quote
        best, _ = compute_quote(inp(count=10, precision=True))
        summary = build_price_summary(best)
        # Täpsuslõikus lisab omaette „võimalikud lisatööd" rea, mis on positiivne
        # ja mille võrra põhitööraha jääb kogu töörahast väiksemaks.
        self.assertTrue(summary['has_extra_work'])
        self.assertGreater(summary['precision_surcharge_eur'], 0.0)
        self.assertAlmostEqual(
            summary['base_work_fee_eur'] + summary['precision_surcharge_eur'],
            best['work_fee_eur'],
            places=6,
        )


class PackingTests(unittest.TestCase):
    """Faas C: pakkimisjuhise loogika (kastid, ribad, poolik euraalus)."""

    def test_box_catalog_and_three_largest(self):
        from domain.packing import BOX_CATALOG, three_largest_boxes
        self.assertEqual(len(BOX_CATALOG), 7)
        names = {box.name for box in three_largest_boxes()}
        # Kolm suurimat ruumala järgi.
        self.assertEqual(names, {'590×380×400', '590×380×250', '440×310×270'})

    def test_detail_fits_in_box_uses_all_three_dimensions(self):
        from domain.packing import BOX_CATALOG, detail_fits_in_box
        small_box = BOX_CATALOG[0]  # 200×150×120
        # 190×140×10 mahub mistahes orientatsioonis.
        self.assertTrue(detail_fits_in_box(140, 190, 10, small_box))
        # 210 mm külg ei mahu ühtegi 200 mm mõõtu.
        self.assertFalse(detail_fits_in_box(210, 140, 10, small_box))

    def test_select_box_picks_smallest_fitting_box(self):
        from domain.packing import select_box
        plan = select_box(120, 90, 5, 10)
        self.assertEqual(plan['method'], 'box')
        self.assertEqual(plan['box_name'], '200×150×120')
        self.assertEqual(plan['box_count'], 1)
        self.assertFalse(plan['recommend_pallet'])

    def test_select_box_recommends_pallet_for_three_largest(self):
        from domain.packing import select_box
        # Suur lapik detail mahub ainult kolme suurima kasti hulka.
        plan = select_box(370, 550, 20, 5)
        self.assertEqual(plan['method'], 'box')
        self.assertIn(plan['box_name'], {'590×380×400', '590×380×250', '440×310×270'})
        self.assertTrue(plan['recommend_pallet'])

    def test_select_box_uses_multiple_boxes_when_order_too_big(self):
        from domain.packing import select_box
        # Väike detail, kuid tohutu kogus → ei mahu ühte kasti.
        plan = select_box(120, 90, 20, 100000)
        self.assertEqual(plan['method'], 'box')
        self.assertGreater(plan['box_count'], 1)
        self.assertEqual(plan['assembly_sec'], 30 * plan['box_count'])

    def test_is_strip_ratio(self):
        from domain.packing import is_strip
        self.assertTrue(is_strip(15, 900))   # 60× → riba
        self.assertFalse(is_strip(200, 300))  # 1,5× → mitte riba

    def test_catalog_max_box_dimension_is_dynamic(self):
        from domain.packing import catalog_max_box_dimension_mm
        # Praeguses kataloogis on suurima kasti pikim sisemõõt 590 mm, kuid
        # väärtus arvutatakse dünaamiliselt (mitte hardcode'itud).
        self.assertEqual(catalog_max_box_dimension_mm(), 590)

    def test_detail_longer_than_any_box_always_uses_strip(self):
        from domain.packing import (
            build_packing_plan, catalog_max_box_dimension_mm, is_strip,
        )
        # Detail 650 mm pikk × 300 mm lai: suhe (650/300 ≈ 2,17) on alla 5, seega
        # ratio-heuristika üksi EI klassifitseeriks seda ribaks. Kuid 650 mm
        # ületab suurima kasti pikima sisemõõdu (590 mm) → detail ei mahu ühtegi
        # kasti ja peab ikkagi saama riba-pakkimise soovituse, mitte kasti.
        self.assertFalse(is_strip(300, 650))
        self.assertGreater(650, catalog_max_box_dimension_mm())
        plan = build_packing_plan(300, 650, 20, 10)
        self.assertNotEqual(plan['method'], 'box')
        self.assertIn(plan['method'], ('pallet', 'bundle', 'simple_wrap'))

    def test_strip_pallet_over_1020mm(self):
        from domain.packing import select_strip_packing
        plan = select_strip_packing(30, 1500, 10, 50)
        self.assertEqual(plan['method'], 'pallet')
        self.assertEqual(plan['estimated_sec'], 10)
        self.assertTrue(plan['recommend_pallet'])

    def test_strip_1020_1200_range_uses_pallet(self):
        from domain.packing import select_strip_packing
        # 1020–1200 mm vahemik → alusepakkimine (dokumenteeritud eeldus).
        plan = select_strip_packing(30, 1100, 10, 50)
        self.assertEqual(plan['method'], 'pallet')

    def test_strip_simple_wrap_short_and_narrow_small_qty(self):
        from domain.packing import select_strip_packing
        plan = select_strip_packing(15, 800, 8, 10)
        self.assertEqual(plan['method'], 'simple_wrap')
        # 120 sek × 2 otsa.
        self.assertEqual(plan['estimated_sec'], 240)
        self.assertFalse(plan['recommend_pallet'])

    def test_strip_bundle_up_to_1020mm(self):
        from domain.packing import select_strip_packing
        plan = select_strip_packing(40, 1000, 10, 30)
        self.assertEqual(plan['method'], 'bundle')
        # 120 sek ots × 2 otsa × kimpude arv.
        self.assertEqual(plan['estimated_sec'], plan['bundle_count'] * 240)

    def test_strip_bundle_splits_when_stack_exceeds_600mm(self):
        from domain.packing import bundle_count
        # Paks materjal + suur kogus ühes reas → virn ületab 600 mm, mitu kimpu.
        one_row = bundle_count(600, 100, 100)  # riba laius 600 > 500 → 1 tk/reas
        self.assertGreater(one_row, 1)

    def test_packing_instruction_lines_box_contains_markers(self):
        from utils import packing_instruction_lines
        result = build_best_result_for_blade(LARGE_BLADE, inp(detail_w=120, detail_l=90, count=10))
        lines = packing_instruction_lines(result)
        joined = ' '.join(lines)
        self.assertIn('Paki kasti', joined)
        self.assertIn('Markeeri kleepsud', joined)

    def test_packing_instruction_lines_reports_offcut(self):
        from utils import packing_instruction_lines
        result = build_best_result_for_blade(LARGE_BLADE, inp(detail_w=120, detail_l=90, count=10))
        result['largest_usable_offcut'] = {
            'name': 'Otsajääk', 'width_mm': 500, 'length_mm': 1500, 'area_m2': 0.75,
        }
        lines = packing_instruction_lines(result)
        self.assertTrue(any(line.startswith('Jääk:') and 'märgi jäägile mõõt' in line for line in lines))

    def test_packing_instruction_lines_strip_uses_pallet(self):
        from utils import packing_instruction_lines
        result = build_best_result_for_blade(LARGE_BLADE, inp(raw_w=1000, raw_l=3000, detail_w=30, detail_l=1500, count=20))
        lines = packing_instruction_lines(result)
        self.assertTrue(any('alusele' in line for line in lines))

    def test_print_sheet_contains_paki_toodang_section(self):
        result = build_best_result_for_blade(LARGE_BLADE, inp(detail_w=120, detail_l=90, count=10))
        html = build_printable_cut_sheet(result)
        self.assertIn('Paki toodang', html)
        self.assertIn('Markeeri kleepsud', html)

    def test_packing_service_matches_domain_plan(self):
        from application.packing_service import build_packing_plan_for_result
        from domain.packing import build_packing_plan
        result = build_best_result_for_blade(LARGE_BLADE, inp(detail_w=120, detail_l=90, count=10))
        service_plan = build_packing_plan_for_result(result)
        domain_plan = build_packing_plan(120, 90, result['thickness_mm'], 10)
        self.assertEqual(service_plan['method'], domain_plan['method'])
        self.assertEqual(service_plan.get('box_name'), domain_plan.get('box_name'))

    def test_box_prices_use_kek_km_column(self):
        from domain.packing import BOX_CATALOG
        prices = {box.name: box.price_eur for box in BOX_CATALOG}
        self.assertAlmostEqual(prices['200×150×120'], 1.22, places=4)
        self.assertAlmostEqual(prices['350×250×200'], 1.0248, places=4)
        self.assertAlmostEqual(prices['360×250×250'], 1.0248, places=4)
        self.assertAlmostEqual(prices['400×300×220'], 1.22, places=4)
        self.assertAlmostEqual(prices['590×380×250'], 1.7812, places=4)
        self.assertAlmostEqual(prices['590×380×400'], 2.1228, places=4)

    def test_box5_price_is_calculated_from_kek(self):
        from domain.packing import BOX_CATALOG
        prices = {box.name: box.price_eur for box in BOX_CATALOG}
        # 440×310×270 "Kek +KM" oli tühi → arvutatud Kek 1.29 × 1.22 ≈ 1.5738.
        self.assertAlmostEqual(prices['440×310×270'], 1.5738, places=4)

    def test_pallet_price_constants(self):
        from domain.packing import FULL_PALLET_PRICE_EUR, HALF_PALLET_PRICE_EUR
        self.assertEqual(FULL_PALLET_PRICE_EUR, 6.00)
        self.assertEqual(HALF_PALLET_PRICE_EUR, 4.00)

    def test_box_plan_packaging_price(self):
        from domain.packing import select_box
        # Väike detail → väikseim kast (200×150×120, 1.22 €), 1 kast, ei soovita alust.
        plan = select_box(120, 90, 5, 10)
        self.assertEqual(plan['box_name'], '200×150×120')
        self.assertEqual(plan['box_count'], 1)
        self.assertAlmostEqual(plan['packaging_line_total_eur'], 1.22, places=4)
        self.assertEqual(plan['pallet_price_eur'], 0.0)
        self.assertAlmostEqual(plan['packaging_total_eur'], 1.22, places=4)

    def test_box_plan_adds_half_pallet_for_three_largest(self):
        from domain.packing import select_box
        plan = select_box(370, 550, 20, 5)  # mahub ainult 3 suurima hulka
        self.assertTrue(plan['recommend_pallet'])
        self.assertEqual(plan['pallet_kind'], 'half')
        self.assertEqual(plan['pallet_price_eur'], 4.00)
        # Kokku = kastid + poolik euraalus.
        self.assertAlmostEqual(
            plan['packaging_total_eur'],
            plan['packaging_line_total_eur'] + 4.00,
            places=4,
        )

    def test_box_plan_multi_box_multiplies_price(self):
        from domain.packing import select_box
        plan = select_box(120, 90, 20, 100000)
        self.assertGreater(plan['box_count'], 1)
        self.assertAlmostEqual(
            plan['packaging_line_total_eur'],
            round(plan['box'].price_eur * plan['box_count'], 4),
            places=4,
        )

    def test_pallet_plan_uses_full_pallet_price(self):
        from domain.packing import select_strip_packing
        plan = select_strip_packing(30, 1500, 10, 50)
        self.assertEqual(plan['method'], 'pallet')
        self.assertEqual(plan['pallet_kind'], 'full')
        self.assertEqual(plan['pallet_price_eur'], 6.00)
        self.assertAlmostEqual(plan['packaging_total_eur'], 6.00, places=4)

    def test_bundle_and_wrap_have_no_priced_packaging(self):
        from domain.packing import select_strip_packing
        bundle = select_strip_packing(40, 1000, 10, 30)
        wrap = select_strip_packing(15, 800, 8, 10)
        self.assertEqual(bundle['packaging_total_eur'], 0.0)
        self.assertEqual(wrap['packaging_total_eur'], 0.0)

    def test_box_capacity_concrete_volume_limited(self):
        from domain.packing import BOX_CATALOG, box_capacity
        box4 = next(b for b in BOX_CATALOG if b.name == '400×300×220')  # 26.4 l
        # 100×100×50 mm detail: kasutatav maht 26.4×0.8=21.12 l, detail 0.5 l →
        # ruumala 42 tk; mõõdupõhine mahutavus 48 → min = 42.
        self.assertEqual(box_capacity(100, 100, 50, box4), 42)

    def test_box_capacity_concrete_dimension_limited(self):
        from domain.packing import BOX_CATALOG, box_capacity, dimensional_capacity
        box4 = next(b for b in BOX_CATALOG if b.name == '400×300×220')
        # 150×150×100 mm detail: ruumala annaks 9, kuid mõõdupõhiselt mahub 8 →
        # min = 8 (arvutus ei ületa reaalset mahtu).
        self.assertEqual(dimensional_capacity(150, 150, 100, box4), 8)
        self.assertEqual(box_capacity(150, 150, 100, box4), 8)

    def test_packing_instruction_lines_show_packaging_price(self):
        from utils import packing_instruction_lines
        result = build_best_result_for_blade(LARGE_BLADE, inp(detail_w=120, detail_l=90, count=10))
        joined = ' '.join(packing_instruction_lines(result))
        self.assertIn('Kastid:', joined)
        self.assertIn('Pakendi hind kokku:', joined)

    def test_print_sheet_shows_packaging_price(self):
        result = build_best_result_for_blade(LARGE_BLADE, inp(detail_w=120, detail_l=90, count=10))
        html = build_printable_cut_sheet(result)
        self.assertIn('Pakendi hind kokku', html)

    def test_packing_domain_does_not_import_streamlit(self):
        import subprocess
        import sys
        result = subprocess.run(
            [sys.executable, '-c',
             'import sys, domain.packing; '
             'assert "streamlit" not in sys.modules, "domeen ei tohi Streamlitit importida"'],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
