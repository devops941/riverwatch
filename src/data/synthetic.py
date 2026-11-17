"""
Synthetic data generator for RiverWatch.
Generates realistic multi-indicator river monitoring data across 8 stations
over 8 years with monsoon seasonality, longitudinal degradation,
and deliberately injected errors for validation testing.
"""
from __future__ import annotations

import os
from datetime import date
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

SAMPLE_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "sample"


STATIONS_META = [
    {"station_id": "STN-01", "station_name": "Rishikesh Upstream", "river": "Ganga", "lat": 30.13, "lon": 78.32, "river_order": 1},
    {"station_id": "STN-02", "station_name": "Haridwar D/S Barrage", "river": "Ganga", "lat": 29.93, "lon": 78.14, "river_order": 2},
    {"station_id": "STN-03", "station_name": "Garhmukteshwar Ghat", "river": "Ganga", "lat": 28.78, "lon": 78.10, "river_order": 3},
    {"station_id": "STN-04", "station_name": "Kannauj Confluence", "river": "Ganga", "lat": 27.05, "lon": 79.92, "river_order": 4},
    {"station_id": "STN-05", "station_name": "Kanpur Jajmau", "river": "Ganga", "lat": 26.43, "lon": 80.40, "river_order": 5},
    {"station_id": "STN-06", "station_name": "Prayagraj Sangam", "river": "Ganga", "lat": 25.42, "lon": 81.88, "river_order": 6},
    {"station_id": "STN-07", "station_name": "Varanasi Assi Ghat", "river": "Ganga", "lat": 25.28, "lon": 83.00, "river_order": 7},
    {"station_id": "STN-08", "station_name": "Varanasi Malviya Bridge", "river": "Ganga", "lat": 25.32, "lon": 83.04, "river_order": 8},
]


def generate_synthetic_data(seed: int = 42, years: int = 8, start_year: int = 2017) -> pd.DataFrame:
    """
    Generate realistic multi-station, multi-year river water quality dataset.
    """
    np.random.seed(seed)
    rows: List[Dict] = []

    # Monthly dates from start_year for `years` years
    date_range = pd.date_range(start=f"{start_year}-01-15", periods=years * 12, freq="MS") + pd.Timedelta(days=14)

    for stn in STATIONS_META:
        order = stn["river_order"]  # 1 to 8
        downstream_factor = (order - 1) / 7.0  # 0.0 to 1.0

        for t_idx, dt in enumerate(date_range):
            month = dt.month
            year_frac = t_idx / len(date_range)  # 0.0 to 1.0 temporal drift

            # Monsoon indicator: July (7), Aug (8), Sept (9)
            is_monsoon = 1.0 if month in [7, 8, 9] else 0.0
            # Summer dry: March-June
            is_summer = 1.0 if month in [4, 5, 6] else 0.0
            # Winter: Nov-Feb
            is_winter = 1.0 if month in [11, 12, 1, 2] else 0.0

            # Seasonality variations
            temp = 24.0 + 8.0 * np.sin(2 * np.pi * (month - 4) / 12) + np.random.normal(0, 1.2)
            temp = np.clip(temp, 10.0, 38.0)

            # pH: baseline 7.6 - 8.2, slight increase downstream, slight drop in monsoon
            ph = 7.7 + 0.3 * (1 - downstream_factor) - 0.2 * is_monsoon + np.random.normal(0, 0.15)
            ph = np.clip(ph, 6.8, 8.8)

            # Dissolved Oxygen: clean upstream (8.5-9.2), heavy depletion downstream (3.2-4.5)
            # DO is higher in cold winter, slightly lower in hot summer, aerated in high-flow monsoon
            do_base = 8.8 - 4.5 * downstream_factor - 0.6 * year_frac * downstream_factor
            do_seasonal = 0.8 * is_winter - 0.6 * is_summer + 0.5 * is_monsoon
            do_mgl = do_base + do_seasonal + np.random.normal(0, 0.35)
            do_mgl = np.clip(do_mgl, 1.5, 11.0)

            # BOD: low upstream (1.0-1.8 mg/L), high downstream (7-16 mg/L)
            # Worsening trend downstream over time (+3 mg/L over 8 years at STN-05..08)
            bod_base = 1.2 + (8.5 * downstream_factor) + (2.5 * year_frac * downstream_factor)
            bod_seasonal = -1.2 * is_monsoon + 1.5 * is_summer
            bod_mgl = bod_base + bod_seasonal + np.random.normal(0, 0.6)
            bod_mgl = np.clip(bod_mgl, 0.5, 30.0)

            # COD: approximately 2.5 - 4.0x BOD
            cod_mgl = bod_mgl * (2.8 + np.random.normal(0, 0.25)) + np.random.normal(0, 1.5)
            cod_mgl = np.clip(cod_mgl, 2.0, 85.0)

            # Nitrate: agricultural runoff + domestic sewage, higher in monsoon runoff & downstream
            nitrate_base = 1.5 + 4.0 * downstream_factor + 2.5 * is_monsoon
            nitrate_mgl = nitrate_base + np.random.normal(0, 0.5)
            nitrate_mgl = np.clip(nitrate_mgl, 0.2, 25.0)

            # Ammonia: high in untreated sewage downstream
            ammonia_base = 0.1 + 2.2 * (downstream_factor ** 1.5) + (0.5 * year_frac * downstream_factor)
            ammonia_mgl = ammonia_base - 0.4 * is_monsoon + np.random.normal(0, 0.15)
            ammonia_mgl = np.clip(ammonia_mgl, 0.05, 8.0)

            # Conductivity & TDS: high dilution in monsoon, concentration in dry season
            ec_base = 300.0 + 650.0 * downstream_factor
            ec_seasonal = -180.0 * is_monsoon + 120.0 * is_summer
            conductivity_uscm = ec_base + ec_seasonal + np.random.normal(0, 35.0)
            conductivity_uscm = np.clip(conductivity_uscm, 120.0, 2800.0)

            # TDS ~ 0.62 * EC
            tds_mgl = conductivity_uscm * 0.62 + np.random.normal(0, 15.0)
            tds_mgl = np.clip(tds_mgl, 80.0, 1800.0)

            # Turbidity: huge spike during monsoon runoff
            turb_base = 6.0 + 12.0 * downstream_factor
            turb_seasonal = 85.0 * is_monsoon + 5.0 * is_summer
            turbidity_ntu = turb_base + turb_seasonal + np.random.normal(0, 4.0)
            turbidity_ntu = np.clip(turbidity_ntu, 1.0, 250.0)

            # Total & Faecal Coliform: exponential increase downstream, lower during cold winter
            # Upstream: 300 - 900 MPN/100mL; Downstream: 20,000 - 150,000 MPN/100mL
            log_tc = 2.6 + 2.4 * downstream_factor - 0.3 * is_winter + 0.4 * is_summer + np.random.normal(0, 0.2)
            total_coliform_mpn = float(int(np.power(10, log_tc)))

            # Faecal coliform ~ 30-60% of total coliform
            fc_ratio = 0.45 + np.random.normal(0, 0.05)
            faecal_coliform_mpn = float(int(total_coliform_mpn * np.clip(fc_ratio, 0.25, 0.70)))

            rows.append({
                "station_id": stn["station_id"],
                "station_name": stn["station_name"],
                "river": stn["river"],
                "lat": stn["lat"],
                "lon": stn["lon"],
                "sample_date": dt.strftime("%Y-%m-%d"),
                "ph": round(float(ph), 2),
                "do_mgl": round(float(do_mgl), 2),
                "bod_mgl": round(float(bod_mgl), 2),
                "cod_mgl": round(float(cod_mgl), 2),
                "nitrate_mgl": round(float(nitrate_mgl), 2),
                "ammonia_mgl": round(float(ammonia_mgl), 2),
                "conductivity_uscm": round(float(conductivity_uscm), 1),
                "turbidity_ntu": round(float(turbidity_ntu), 1),
                "tds_mgl": round(float(tds_mgl), 1),
                "temp_c": round(float(temp), 1),
                "total_coliform_mpn": total_coliform_mpn,
                "faecal_coliform_mpn": faecal_coliform_mpn,
            })

    df = pd.DataFrame(rows)
    return df


def inject_synthetic_errors(df: pd.DataFrame, seed: int = 42) -> Tuple[pd.DataFrame, Dict]:
    """
    Inject deliberate errors matching Section 6.1 of specification:
    1. Unparseable and future dates
    2. Non-numeric values in numeric columns ("N/A", "ND")
    3. Censored values ("<0.5", "<1.0")
    4. Physically impossible values (pH 15.0, negative DO/BOD, temp 65)
    5. Extreme outliers beyond median +/- 5 MAD
    6. Duplicates (same station_id & sample_date)
    7. Unit inconsistency (conductivity in mS/cm instead of uS/cm)
    8. Out-of-bounds coordinates
    """
    df_raw = df.astype(object).copy()
    np.random.seed(seed)

    injected: Dict[str, List] = {
        "future_date": [],
        "unparseable_date": [],
        "non_numeric": [],
        "censored": [],
        "impossible_ph": [],
        "negative_concentration": [],
        "impossible_temp": [],
        "impossible_do": [],
        "outliers": [],
        "duplicates": [],
        "unit_mismatch": [],
        "invalid_coords": [],
    }

    # 1. Date errors (rows 12 and 25)
    df_raw.at[12, "sample_date"] = "2035-11-20"  # Future date
    injected["future_date"].append({"row": 12, "col": "sample_date", "val": "2035-11-20"})

    df_raw.at[25, "sample_date"] = "2021-99-99"  # Unparseable date
    injected["unparseable_date"].append({"row": 25, "col": "sample_date", "val": "2021-99-99"})

    # 2. Non-numeric values in numeric columns (rows 35, 45, 60)
    df_raw.at[35, "bod_mgl"] = "ND"
    injected["non_numeric"].append({"row": 35, "col": "bod_mgl", "val": "ND"})

    df_raw.at[45, "nitrate_mgl"] = "Not Detected"
    injected["non_numeric"].append({"row": 45, "col": "nitrate_mgl", "val": "Not Detected"})

    df_raw.at[60, "ph"] = "invalid_ph"
    injected["non_numeric"].append({"row": 60, "col": "ph", "val": "invalid_ph"})

    # 3. Censored values (rows 75, 85)
    df_raw.at[75, "ammonia_mgl"] = "<0.5"
    injected["censored"].append({"row": 75, "col": "ammonia_mgl", "val": "<0.5"})

    df_raw.at[85, "bod_mgl"] = "<1.0"
    injected["censored"].append({"row": 85, "col": "bod_mgl", "val": "<1.0"})

    # 4. Physically impossible values
    # pH = 15.0 (row 105)
    df_raw.at[105, "ph"] = 15.0
    injected["impossible_ph"].append({"row": 105, "col": "ph", "val": 15.0})

    # pH = -1.2 (row 115)
    df_raw.at[115, "ph"] = -1.2
    injected["impossible_ph"].append({"row": 115, "col": "ph", "val": -1.2})

    # Negative BOD (row 130)
    df_raw.at[130, "bod_mgl"] = -4.5
    injected["negative_concentration"].append({"row": 130, "col": "bod_mgl", "val": -4.5})

    # Negative DO (row 140)
    df_raw.at[140, "do_mgl"] = -1.8
    injected["impossible_do"].append({"row": 140, "col": "do_mgl", "val": -1.8})

    # Impossible high DO > 20 (row 150)
    df_raw.at[150, "do_mgl"] = 24.8
    injected["impossible_do"].append({"row": 150, "col": "do_mgl", "val": 24.8})

    # Impossible water temperature > 50 C (row 165)
    df_raw.at[165, "temp_c"] = 68.5
    injected["impossible_temp"].append({"row": 165, "col": "temp_c", "val": 68.5})

    # 5. Outliers (row 180: turbidity extreme spike)
    df_raw.at[180, "turbidity_ntu"] = 980.0
    injected["outliers"].append({"row": 180, "col": "turbidity_ntu", "val": 980.0})

    # 6. Duplicates: duplicate row 200 at row 201
    dup_row = df_raw.iloc[200].to_dict()
    df_raw = pd.concat([df_raw.iloc[:201], pd.DataFrame([dup_row]), df_raw.iloc[201:]]).reset_index(drop=True)
    injected["duplicates"].append({"station_id": dup_row["station_id"], "sample_date": dup_row["sample_date"]})

    # 7. Unit mismatch: Conductivity in mS/cm instead of uS/cm (e.g. 0.45 instead of 450)
    df_raw.at[220, "conductivity_uscm"] = 0.42
    injected["unit_mismatch"].append({"row": 220, "col": "conductivity_uscm", "val": 0.42})

    # 8. Coordinate out of range
    df_raw.at[240, "lat"] = 65.4  # Outside India bounding box
    injected["invalid_coords"].append({"row": 240, "col": "lat", "val": 65.4})

    return df_raw, injected


def create_template_dataframe() -> pd.DataFrame:
    """
    Standard empty wide template with 1 example row.
    """
    example = {
        "station_id": "STN-01",
        "station_name": "Example Station",
        "river": "Ganga",
        "lat": 30.13,
        "lon": 78.32,
        "sample_date": "2024-01-15",
        "ph": 7.8,
        "do_mgl": 8.5,
        "bod_mgl": 2.1,
        "cod_mgl": 8.0,
        "nitrate_mgl": 2.5,
        "ammonia_mgl": 0.2,
        "conductivity_uscm": 450.0,
        "turbidity_ntu": 8.5,
        "tds_mgl": 280.0,
        "temp_c": 22.0,
        "total_coliform_mpn": 800,
        "faecal_coliform_mpn": 320,
    }
    return pd.DataFrame([example])


def save_sample_datasets():
    SAMPLE_DIR.mkdir(parents=True, exist_ok=True)
    clean_df = generate_synthetic_data()
    raw_df, _ = inject_synthetic_errors(clean_df)
    template_df = create_template_dataframe()

    clean_path = SAMPLE_DIR / "riverwatch_synthetic_clean.csv"
    raw_path = SAMPLE_DIR / "riverwatch_synthetic_raw.csv"
    template_path = SAMPLE_DIR / "riverwatch_template.csv"

    clean_df.to_csv(clean_path, index=False)
    raw_df.to_csv(raw_path, index=False)
    template_df.to_csv(template_path, index=False)

    return clean_path, raw_path, template_path


if __name__ == "__main__":
    c, r, t = save_sample_datasets()
    print(f"Generated clean dataset: {c}")
    print(f"Generated raw error dataset: {r}")
    print(f"Generated template: {t}")
