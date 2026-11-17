"""
Data validation module for RiverWatch.
Implements Section 6.1 validation rules, producing detailed actionable issue reports
with row number, column, observed value, rule violated, and suggested fix.
"""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import yaml

CONFIG_DIR = Path(__file__).resolve().parent.parent.parent / "config"


def load_parameter_config(config_path: Optional[Path] = None) -> Dict[str, Any]:
    path = config_path or (CONFIG_DIR / "parameters.yaml")
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("parameters", {})


class Validator:
    def __init__(self, param_config: Optional[Dict[str, Any]] = None):
        self.param_config = param_config or load_parameter_config()

    def validate(self, df: pd.DataFrame) -> List[Dict[str, Any]]:
        """
        Run all validation checks on the mapped DataFrame.
        Returns a list of issue dictionaries.
        """
        issues: List[Dict[str, Any]] = []

        # 1. Missing mandatory columns check (Dataset-level)
        mandatory_cols = ["station_id", "sample_date"]
        for col in mandatory_cols:
            if col not in df.columns:
                issues.append({
                    "row_number": None,
                    "column_name": col,
                    "value": "MISSING",
                    "severity": "error",
                    "rule": "missing_mandatory_column",
                    "message": f"Mandatory column '{col}' is missing from the dataset.",
                    "suggestion": f"Map or add '{col}' column in the uploaded file.",
                })

        # If mandatory columns are missing, we cannot perform row-level station/date checks reliably
        if "station_id" not in df.columns or "sample_date" not in df.columns:
            return issues

        # 2. Date checks (unparseable / future dates)
        today = date.today()
        parsed_dates = []

        for idx, val in df["sample_date"].items():
            row_num = idx + 1
            if pd.isna(val) or str(val).strip() == "":
                issues.append({
                    "row_number": row_num,
                    "column_name": "sample_date",
                    "value": str(val),
                    "severity": "error",
                    "rule": "missing_date",
                    "message": "Sample date is blank or missing.",
                    "suggestion": "Provide a valid sampling date in YYYY-MM-DD format.",
                })
                parsed_dates.append(None)
                continue

            dt_str = str(val).strip()
            parsed_dt = None
            try:
                parsed_dt = pd.to_datetime(dt_str, errors="raise").date()
                parsed_dates.append(parsed_dt)
            except Exception:
                issues.append({
                    "row_number": row_num,
                    "column_name": "sample_date",
                    "value": dt_str,
                    "severity": "error",
                    "rule": "unparseable_date",
                    "message": f"Cannot parse date '{dt_str}'.",
                    "suggestion": "Format date as YYYY-MM-DD or DD-MM-YYYY.",
                })
                parsed_dates.append(None)
                continue

            if parsed_dt > today:
                issues.append({
                    "row_number": row_num,
                    "column_name": "sample_date",
                    "value": dt_str,
                    "severity": "error",
                    "rule": "future_date",
                    "message": f"Sample date '{dt_str}' is in the future.",
                    "suggestion": "Verify sampling year and date; river monitoring dates must be past or present.",
                })

        # 3. Duplicate (station_id, sample_date)
        # Identify duplicates where neither station_id nor sample_date is null
        valid_date_series = pd.Series(parsed_dates, index=df.index)
        temp_dup_df = pd.DataFrame({
            "station_id": df["station_id"].astype(str).str.strip(),
            "sample_date": valid_date_series,
        })
        # Mask out rows where sample_date is None
        temp_dup_df_valid = temp_dup_df[temp_dup_df["sample_date"].notna()]
        dup_mask = temp_dup_df_valid.duplicated(subset=["station_id", "sample_date"], keep=False)

        for idx in temp_dup_df_valid[dup_mask].index:
            row_num = idx + 1
            stn = df.at[idx, "station_id"]
            d_val = df.at[idx, "sample_date"]
            issues.append({
                "row_number": row_num,
                "column_name": "station_id, sample_date",
                "value": f"{stn} @ {d_val}",
                "severity": "warning",
                "rule": "duplicate_sample",
                "message": f"Duplicate sample record for station '{stn}' on date '{d_val}'.",
                "suggestion": "Keep first, keep last, average readings, or exclude duplicate entry.",
            })

        # 4. Coordinates check (lat / lon bounding box for India: approx 6.0-38.0 N, 68.0-98.0 E)
        if "lat" in df.columns:
            for idx, val in df["lat"].items():
                if pd.notna(val):
                    try:
                        lat_val = float(val)
                        if lat_val < 6.0 or lat_val > 38.0:
                            issues.append({
                                "row_number": idx + 1,
                                "column_name": "lat",
                                "value": str(val),
                                "severity": "warning",
                                "rule": "invalid_coordinates",
                                "message": f"Latitude {lat_val} is outside expected India bounding range (6.0 - 38.0 N).",
                                "suggestion": "Verify coordinate units or decimal precision.",
                            })
                    except (ValueError, TypeError):
                        pass

        if "lon" in df.columns:
            for idx, val in df["lon"].items():
                if pd.notna(val):
                    try:
                        lon_val = float(val)
                        if lon_val < 68.0 or lon_val > 98.0:
                            issues.append({
                                "row_number": idx + 1,
                                "column_name": "lon",
                                "value": str(val),
                                "severity": "warning",
                                "rule": "invalid_coordinates",
                                "message": f"Longitude {lon_val} is outside expected India bounding range (68.0 - 98.0 E).",
                                "suggestion": "Verify coordinate units or decimal precision.",
                            })
                    except (ValueError, TypeError):
                        pass

        # 5. Parameter value checks: non-numeric, impossible, negative, unit consistency, MAD outliers
        numeric_series_dict: Dict[str, pd.Series] = {}

        for param_code, pmeta in self.param_config.items():
            if param_code not in df.columns:
                continue

            series = df[param_code]
            num_values = []

            for idx, val in series.items():
                row_num = idx + 1
                if pd.isna(val) or str(val).strip() == "":
                    num_values.append(np.nan)
                    continue

                val_str = str(val).strip()

                # Check censored notation (e.g., "<0.5", "<1.0") -> valid, flagged for preprocessing
                if val_str.startswith("<") or val_str.startswith(">"):
                    try:
                        clean_num = float(val_str[1:].strip())
                        num_values.append(clean_num)  # temporary float representation
                        continue
                    except ValueError:
                        pass

                # Try numeric conversion
                try:
                    num_val = float(val_str)
                    num_values.append(num_val)
                except ValueError:
                    num_values.append(np.nan)
                    issues.append({
                        "row_number": row_num,
                        "column_name": param_code,
                        "value": val_str,
                        "severity": "warning",
                        "rule": "non_numeric_value",
                        "message": f"Non-numeric text '{val_str}' found in numeric column '{param_code}'.",
                        "suggestion": "Value will be treated as NaN or needs manual numeric correction.",
                    })
                    continue

                # Impossible / Out-of-bounds checks
                valid_min = pmeta.get("valid_min")
                valid_max = pmeta.get("valid_max")

                # Physical impossibilities
                if valid_min is not None and num_val < valid_min:
                    issues.append({
                        "row_number": row_num,
                        "column_name": param_code,
                        "value": str(val),
                        "severity": "error",
                        "rule": "physically_impossible_value",
                        "message": f"Value {num_val} in '{param_code}' is below minimum physical limit ({valid_min} {pmeta.get('unit')}).",
                        "suggestion": f"Check for negative concentration or sensor error. Must be >= {valid_min}.",
                    })

                if valid_max is not None and num_val > valid_max:
                    issues.append({
                        "row_number": row_num,
                        "column_name": param_code,
                        "value": str(val),
                        "severity": "error",
                        "rule": "physically_impossible_value",
                        "message": f"Value {num_val} in '{param_code}' exceeds maximum physical limit ({valid_max} {pmeta.get('unit')}).",
                        "suggestion": f"Check measurement scale/units. Must be <= {valid_max}.",
                    })

                # Expected unit consistency check
                exp_min = pmeta.get("expected_range_min")
                exp_max = pmeta.get("expected_range_max")
                if exp_min is not None and 0.0 < num_val < exp_min and (valid_min is None or num_val >= valid_min):
                    if param_code == "conductivity_uscm":
                        issues.append({
                            "row_number": row_num,
                            "column_name": param_code,
                            "value": str(val),
                            "severity": "warning",
                            "rule": "unit_consistency",
                            "message": f"Value {num_val} in '{param_code}' is suspiciously low ({num_val} < {exp_min}).",
                            "suggestion": "Check if conductivity was recorded in mS/cm instead of µS/cm (multiply by 1000).",
                        })

            numeric_series_dict[param_code] = pd.Series(num_values, index=df.index)

        # 6. Station-level checks: Missingness (>40%) & Suspicious Outliers (Median +/- 5 MAD)
        if "station_id" in df.columns:
            for stn_id, stn_df in df.groupby("station_id"):
                n_stn_rows = len(stn_df)
                if n_stn_rows == 0:
                    continue

                for param_code, num_s in numeric_series_dict.items():
                    sub_s = num_s.loc[stn_df.index].dropna()
                    n_valid = len(sub_s)
                    missing_rate = (n_stn_rows - n_valid) / n_stn_rows

                    # Missingness > 40%
                    if missing_rate > 0.40 and n_stn_rows >= 5:
                        issues.append({
                            "row_number": None,
                            "column_name": param_code,
                            "value": f"{round(missing_rate * 100, 1)}% missing",
                            "severity": "warning",
                            "rule": "high_missingness",
                            "message": f"Station '{stn_id}' is missing {round(missing_rate * 100, 1)}% of values for '{param_code}'.",
                            "suggestion": "Parameter will be omitted from WQI calculation for this station.",
                        })

                    # Outlier check using Median +/- 5 MAD (minimum 8 valid samples)
                    if n_valid >= 8:
                        med = sub_s.median()
                        mad = (sub_s - med).abs().median()
                        if mad > 1e-6:
                            upper_thresh = med + 5.0 * mad
                            lower_thresh = med - 5.0 * mad

                            outlier_indices = sub_s[(sub_s > upper_thresh) | (sub_s < lower_thresh)].index
                            for out_idx in outlier_indices:
                                out_val = df.at[out_idx, param_code]
                                issues.append({
                                    "row_number": out_idx + 1,
                                    "column_name": param_code,
                                    "value": str(out_val),
                                    "severity": "warning",
                                    "rule": "suspicious_outlier",
                                    "message": f"Value {out_val} in '{param_code}' at station '{stn_id}' is beyond 5 MAD (range [{round(lower_thresh, 2)}, {round(upper_thresh, 2)}]).",
                                    "suggestion": "Flagged as outlier; inspect for extreme contamination event or lab typo.",
                                })

        return issues


def validate_dataframe(df: pd.DataFrame) -> List[Dict[str, Any]]:
    validator = Validator()
    return validator.validate(df)
