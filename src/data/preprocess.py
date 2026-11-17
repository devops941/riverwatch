"""
Preprocessing module for RiverWatch.
Handles unit normalization, duplicate resolution, censored values (<DL -> DL/2),
outlier flagging, and committing cleaned data into the SQLite database.
"""
from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from src.data.db import (
    CorrectionAudit,
    Measurement,
    Parameter,
    River,
    Sample,
    Station,
    Upload,
    ValidationIssue,
    get_db,
    get_session_factory,
    init_db,
)

CONFIG_DIR = Path(__file__).resolve().parent.parent.parent / "config"


def parse_censored_value(raw_val: Any) -> Tuple[Optional[float], int, str]:
    """
    Parse a string value. If censored like '<0.5', return (0.25, 1, '<0.5').
    If standard float, return (float_val, 0, raw_str).
    If missing or invalid, return (np.nan, 0, raw_str).
    """
    if pd.isna(raw_val) or raw_val is None:
        return None, 0, ""

    raw_str = str(raw_val).strip()
    if raw_str == "" or raw_str.lower() in ["na", "n/a", "nd", "nan", "none", "null"]:
        return None, 0, raw_str

    # Censored with '<'
    if raw_str.startswith("<"):
        m = re.search(r"<\s*([0-9]*\.?[0-9]+)", raw_str)
        if m:
            limit = float(m.group(1))
            return limit / 2.0, 1, raw_str

    # Censored with '>'
    if raw_str.startswith(">"):
        m = re.search(r">\s*([0-9]*\.?[0-9]+)", raw_str)
        if m:
            limit = float(m.group(1))
            return limit, 1, raw_str

    # Standard numeric
    try:
        val = float(raw_str)
        return val, 0, raw_str
    except ValueError:
        return None, 0, raw_str


def preprocess_dataframe(
    df: pd.DataFrame,
    duplicate_strategy: str = "keep_first",  # 'keep_first', 'keep_last', 'average'
    excluded_rows: Optional[List[int]] = None,
    value_overrides: Optional[Dict[Tuple[int, str], Any]] = None,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Clean and structure incoming DataFrame into samples_df and measurements_df.
    """
    df_clean = df.copy()
    excluded_rows = excluded_rows or []
    value_overrides = value_overrides or {}

    # Apply manual overrides if any
    for (row_idx, col_name), new_val in value_overrides.items():
        if 0 <= row_idx < len(df_clean) and col_name in df_clean.columns:
            df_clean.at[row_idx, col_name] = new_val

    # Filter out excluded rows
    valid_indices = [i for i in df_clean.index if (i + 1) not in excluded_rows]
    df_clean = df_clean.loc[valid_indices].copy()

    # Parse sample_date
    df_clean["parsed_date"] = pd.to_datetime(df_clean["sample_date"], errors="coerce").dt.date
    # Drop rows with unparseable dates
    df_clean = df_clean[df_clean["parsed_date"].notna()].copy()

    # Handle duplicates
    dup_cols = ["station_id", "parsed_date"]
    if duplicate_strategy == "keep_first":
        df_clean = df_clean.drop_duplicates(subset=dup_cols, keep="first")
    elif duplicate_strategy == "keep_last":
        df_clean = df_clean.drop_duplicates(subset=dup_cols, keep="last")
    elif duplicate_strategy == "average":
        # Average numeric columns for duplicates
        numeric_cols = [c for c in df_clean.columns if c not in ["station_id", "station_name", "river", "lat", "lon", "sample_date", "parsed_date"]]
        for c in numeric_cols:
            df_clean[c] = pd.to_numeric(df_clean[c], errors="coerce")
        agg_funcs = {c: "mean" for c in numeric_cols}
        first_cols = [c for c in ["station_name", "river", "lat", "lon"] if c in df_clean.columns]
        for c in first_cols:
            agg_funcs[c] = "first"
        df_clean = df_clean.groupby(dup_cols, as_index=False).agg(agg_funcs)

    return df_clean


def commit_upload_to_db(
    df: pd.DataFrame,
    upload_id: int,
    session: Session,
    duplicate_strategy: str = "keep_first",
    excluded_rows: Optional[List[int]] = None,
    value_overrides: Optional[Dict[Tuple[int, str], Any]] = None,
) -> Dict[str, int]:
    """
    Preprocess and commit data into SQLite database:
    stations, samples, and measurements.
    """
    df_clean = preprocess_dataframe(df, duplicate_strategy, excluded_rows, value_overrides)

    # 1. Ensure River exists
    default_river_name = "Ganga"
    if "river" in df_clean.columns and df_clean["river"].notna().any():
        detected_river = df_clean["river"].dropna().iloc[0]
        if str(detected_river).strip():
            default_river_name = str(detected_river).strip()

    river = session.query(River).filter_by(river_name=default_river_name).first()
    if not river:
        river = River(river_name=default_river_name)
        session.add(river)
        session.flush()

    # 2. Upsert Stations
    unique_stations = df_clean[["station_id"]].drop_duplicates()
    station_meta_map: Dict[str, Dict] = {}

    for _, row in df_clean.iterrows():
        stn_id = str(row["station_id"]).strip()
        if stn_id not in station_meta_map:
            station_meta_map[stn_id] = {
                "station_name": row.get("station_name", stn_id),
                "lat": float(row["lat"]) if pd.notna(row.get("lat")) else None,
                "lon": float(row["lon"]) if pd.notna(row.get("lon")) else None,
                "river_order": int(row["river_order"]) if pd.notna(row.get("river_order")) else None,
            }

    for idx, (stn_id, meta) in enumerate(sorted(station_meta_map.items())):
        stn = session.query(Station).filter_by(station_id=stn_id).first()
        if not stn:
            stn = Station(
                station_id=stn_id,
                station_name=meta["station_name"] or stn_id,
                river_id=river.river_id,
                lat=meta["lat"],
                lon=meta["lon"],
                river_order=meta["river_order"] if meta["river_order"] is not None else (idx + 1),
            )
            session.add(stn)
        else:
            if meta["lat"] is not None:
                stn.lat = meta["lat"]
            if meta["lon"] is not None:
                stn.lon = meta["lon"]
            if meta["station_name"]:
                stn.station_name = meta["station_name"]
    session.flush()

    # 3. Known parameter list
    param_records = session.query(Parameter).all()
    known_param_codes = {p.param_code for p in param_records}

    # 4. Insert Samples & Measurements
    samples_created = 0
    measurements_created = 0

    for _, row in df_clean.iterrows():
        stn_id = str(row["station_id"]).strip()
        sample_dt = row["parsed_date"]

        # Check existing sample
        existing_sample = (
            session.query(Sample)
            .filter_by(station_id=stn_id, sample_date=sample_dt)
            .first()
        )

        if existing_sample:
            sample_obj = existing_sample
            sample_obj.upload_id = upload_id
            sample_obj.is_excluded = 0
        else:
            sample_obj = Sample(
                upload_id=upload_id,
                station_id=stn_id,
                sample_date=sample_dt,
                is_excluded=0,
            )
            session.add(sample_obj)
            session.flush()
            samples_created += 1

        # Insert measurements for all matching parameters in row
        for col in df_clean.columns:
            if col in known_param_codes:
                raw_cell = row[col]
                num_val, is_cens, raw_text = parse_censored_value(raw_cell)

                # Unit conversion check for conductivity (mS/cm -> uS/cm if < 10)
                if col == "conductivity_uscm" and num_val is not None:
                    if 0.0 < num_val < 10.0:
                        num_val = num_val * 1000.0

                # Existing measurement check
                existing_m = (
                    session.query(Measurement)
                    .filter_by(sample_id=sample_obj.sample_id, param_code=col)
                    .first()
                )
                if existing_m:
                    existing_m.value = num_val
                    existing_m.raw_value = raw_text
                    existing_m.is_censored = is_cens
                else:
                    m = Measurement(
                        sample_id=sample_obj.sample_id,
                        param_code=col,
                        value=num_val,
                        raw_value=raw_text,
                        is_censored=is_cens,
                        is_imputed=0,
                        is_outlier=0,
                    )
                    session.add(m)
                    measurements_created += 1

    # Update Upload status
    up = session.query(Upload).filter_by(upload_id=upload_id).first()
    if up:
        up.status = "committed"
        up.n_rows = len(df_clean)

    session.commit()

    return {
        "samples_committed": samples_created,
        "measurements_committed": measurements_created,
    }
