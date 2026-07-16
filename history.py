from pathlib import Path
import datetime
import uuid

import pandas as pd

from core import quality_control_check_count
from utils import opened_material_label

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / 'data'
DATA_DIR.mkdir(parents=True, exist_ok=True)
HISTORY_FILE = DATA_DIR / 'saetoo_ajalugu.csv'
QUERY_MEMORY_FILE = DATA_DIR / 'arvutusparingud.csv'

HISTORY_COLUMNS = [
    'paring_id', 'kuupaev', 'materjal_paksus_mm', 'toorik_laius_mm', 'toorik_pikkus_mm',
    'detail_laius_mm', 'detail_pikkus_mm', 'detailide_arv', 'ketas', 'detailid_pooratud',
    'taisplaatide_arv', 'lisamaterjal_laius_mm', 'lisamaterjal_pikkus_mm',
    'tapususloikus', 'kvaliteedikontrollide_arv', 'kvaliteedikontroll_aeg_sek', 'arvutuslik_aeg_sek',
    'lahtematerjal', 'materjal', 'laastukoti_vahetuste_arv', 'laastukoti_vahetus_aeg_sek',
    'paksu_materjali_ajategur', 'hinnastusaeg_sek', 'hinnastuspuhver_sek',
    'tegelik_aeg_sek', 'tooraha_eur', 'markused',
]

QUERY_MEMORY_COLUMNS = [
    'paring_id', 'kuupaev', 'materjal_paksus_mm', 'toorik_laius_mm', 'toorik_pikkus_mm',
    'detail_laius_mm', 'detail_pikkus_mm', 'detailide_arv', 'tasandusloige',
    'soovitatud_ketas', 'detailid_pooratud', 'materjali_vajadus', 'taisplaatide_arv',
    'lisamaterjal_laius_mm', 'lisamaterjal_pikkus_mm', 'tapususloikus',
    'kvaliteedikontrollide_arv', 'kvaliteedikontroll_aeg_sek', 'arvutuslik_aeg_sek', 'ml_prognoos_sek',
    'materjalikulu_m2', 'lahtematerjal', 'materjal', 'laastukoti_vahetuste_arv',
    'laastukoti_vahetus_aeg_sek', 'paksu_materjali_ajategur',
    'hinnastusaeg_sek', 'hinnastuspuhver_sek', 'tooraha_eur',
]


def _normalize(df, columns):
    # Vanad CSV-failid jäävad loetavaks: puuduvaid veerge täiendatakse.
    for column in columns:
        if column not in df.columns:
            df[column] = None
    return df[columns]


def normalize_history_df(df):
    return _normalize(df, HISTORY_COLUMNS)


def normalize_query_memory_df(df):
    return _normalize(df, QUERY_MEMORY_COLUMNS)


def load_history():
    if HISTORY_FILE.exists():
        try:
            return normalize_history_df(pd.read_csv(HISTORY_FILE))
        except Exception:
            pass
    return pd.DataFrame(columns=HISTORY_COLUMNS)


def load_query_memory():
    if QUERY_MEMORY_FILE.exists():
        try:
            return normalize_query_memory_df(pd.read_csv(QUERY_MEMORY_FILE))
        except Exception:
            pass
    return pd.DataFrame(columns=QUERY_MEMORY_COLUMNS)


def save_history_row(row):
    combined = pd.concat([load_history(), normalize_history_df(pd.DataFrame([row]))], ignore_index=True)
    combined.to_csv(HISTORY_FILE, index=False)


def save_query_memory_row(row):
    # Skeemi täienemisel kirjutatakse fail normaliseeritult uuesti. Nii ei
    # satu uute veergudega rida vana CSV-päise alla ega muuda faili loetamatuks.
    existing = load_query_memory()
    new_row = normalize_query_memory_df(pd.DataFrame([row]))
    combined = pd.concat([existing, new_row], ignore_index=True)
    combined.to_csv(QUERY_MEMORY_FILE, index=False)


def build_query_memory_row(result):
    query_id = uuid.uuid4().hex
    qc_checks = result.get('quality_control_check_count')
    if qc_checks is None:
        qc_checks = quality_control_check_count(result.get('detail_count', 0)) if result.get('precision_cut') else 0
    return query_id, {
        'paring_id': query_id,
        'kuupaev': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'materjal_paksus_mm': result['thickness_mm'],
        'toorik_laius_mm': result['raw_width_mm'],
        'toorik_pikkus_mm': result['raw_length_mm'],
        'detail_laius_mm': result['original_detail_width_mm'],
        'detail_pikkus_mm': result['original_detail_length_mm'],
        'detailide_arv': result['detail_count'],
        'tasandusloige': 'Jah',
        'soovitatud_ketas': result['blade']['blade'],
        'detailid_pooratud': 'Jah' if result.get('rotated') else 'Ei',
        'materjali_vajadus': opened_material_label(result),
        'taisplaatide_arv': result['full_sheet_count'],
        'lisamaterjal_laius_mm': result['partial_stock_width_mm'] or None,
        'lisamaterjal_pikkus_mm': result['partial_stock_length_mm'] or None,
        'tapususloikus': 'Jah' if result['precision_cut'] else 'Ei',
        'kvaliteedikontrollide_arv': qc_checks,
        'kvaliteedikontroll_aeg_sek': round(result['quality_control_sec']),
        'arvutuslik_aeg_sek': round(result['total_sec']),
        'ml_prognoos_sek': round(result['ml_predicted_actual_time_sec']) if result.get('ml_predicted_actual_time_sec') else None,
        'materjalikulu_m2': round(result['material_needed_area_m2'], 4),
        'lahtematerjal': result.get('stock_source'),
        'materjal': result.get('material_name'),
        'laastukoti_vahetuste_arv': result.get('dust_bag_change_count', 0),
        'laastukoti_vahetus_aeg_sek': round(result.get('dust_bag_change_sec', 0)),
        'paksu_materjali_ajategur': result.get('thick_material_time_factor', 1.0),
        'hinnastusaeg_sek': round(result.get('billable_sec', result['total_sec'])),
        'hinnastuspuhver_sek': round(result.get('quote_buffer_sec', 0)),
        'tooraha_eur': round(result['work_fee_eur'], 2),
    }


def build_pending_save_row(state, result, actual_blade, actual_rotated, actual_time_sec, rework_time_sec):
    actual_total = actual_time_sec
    if actual_total is not None and rework_time_sec:
        actual_total += rework_time_sec
    qc_checks = result.get('quality_control_check_count')
    if qc_checks is None:
        qc_checks = quality_control_check_count(result.get('detail_count', 0)) if result.get('precision_cut') else 0
    return {
        'paring_id': state.get('last_query_id'),
        'kuupaev': datetime.datetime.now().strftime('%Y-%m-%d %H:%M'),
        'materjal_paksus_mm': result['thickness_mm'],
        'toorik_laius_mm': result['raw_width_mm'],
        'toorik_pikkus_mm': result['raw_length_mm'],
        'detail_laius_mm': result['original_detail_width_mm'],
        'detail_pikkus_mm': result['original_detail_length_mm'],
        'detailide_arv': result['detail_count'],
        'ketas': actual_blade,
        'detailid_pooratud': 'Jah' if actual_rotated else 'Ei',
        'taisplaatide_arv': result['full_sheet_count'],
        'lisamaterjal_laius_mm': result['partial_stock_width_mm'] or None,
        'lisamaterjal_pikkus_mm': result['partial_stock_length_mm'] or None,
        'tapususloikus': 'Jah' if result['precision_cut'] else 'Ei',
        'kvaliteedikontrollide_arv': qc_checks,
        'kvaliteedikontroll_aeg_sek': round(result['quality_control_sec']),
        'arvutuslik_aeg_sek': round(result['total_sec']),
        'lahtematerjal': result.get('stock_source'),
        'materjal': result.get('material_name'),
        'laastukoti_vahetuste_arv': result.get('dust_bag_change_count', 0),
        'laastukoti_vahetus_aeg_sek': round(result.get('dust_bag_change_sec', 0)),
        'paksu_materjali_ajategur': result.get('thick_material_time_factor', 1.0),
        'hinnastusaeg_sek': round(result.get('billable_sec', result['total_sec'])),
        'hinnastuspuhver_sek': round(result.get('quote_buffer_sec', 0)),
        'tegelik_aeg_sek': round(actual_total) if actual_total is not None else None,
        'tooraha_eur': round(result['work_fee_eur'], 2),
        'markused': state.get('notes', ''),
    }
