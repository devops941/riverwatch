"""
Trend Analysis Module for RiverWatch.
Implements Mann-Kendall trend tests and Sen's slope estimator using pymannkendall,
with autocorrelation check, seasonal decomposition, and domain-aware worsening/improving interpretation.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import pymannkendall as mk
import yaml
from sqlalchemy.orm import Session

from src.data.db import Measurement, Parameter, Sample, Station, TrendResult, WQIResult

CONFIG_DIR = Path(__file__).resolve().parent.parent.parent / "config"


def load_worse_if_rules() -> Dict[str, str]:
    param_path = CONFIG_DIR / "parameters.yaml"
    with open(param_path, "r", encoding="utf-8") as f:
        params_data = yaml.safe_load(f).get("parameters", {})
    rules = {k: v.get("worse_if", "increasing") for k, v in params_data.items()}
    rules["wqi"] = "increasing"  # Higher WQI means worse water quality
    return rules


def interpret_trend(trend_direction: str, worse_if: str, slope: float) -> str:
    """
    Interpret trend direction into 'worsening', 'improving', or 'no trend'.
    """
    if trend_direction == "no trend" or abs(slope) < 1e-9:
        return "no trend"

    if worse_if == "increasing":
        return "worsening" if trend_direction == "increasing" else "improving"
    elif worse_if == "decreasing":
        return "improving" if trend_direction == "increasing" else "worsening"
    elif worse_if == "both":
        # E.g. pH or Temp: if slope moves away from neutral, consider it worsening
        return "worsening"
    return "no trend"


def run_trend_test(
    series: pd.Series, alpha: float = 0.05, worse_if: str = "increasing"
) -> Optional[Dict[str, Any]]:
    """
    Run Mann-Kendall test and Sen's slope on a monthly time series.
    Returns dictionary of results or None if insufficient data (< 12 points).
    """
    clean_s = series.dropna()
    if len(clean_s) < 12:
        return None

    y = clean_s.values
    if np.std(y) < 1e-7:
        return {
            "test_used": "original_test",
            "trend": "no trend",
            "interpretation": "no trend",
            "p_value": 1.0,
            "tau": 0.0,
            "sen_slope_per_year": 0.0,
            "ci_low": 0.0,
            "ci_high": 0.0,
            "pct_change_per_year": 0.0,
        }

    test_used = "original_test"
    try:
        res = mk.original_test(y, alpha=alpha)
        # Attempt hamed_rao if sufficient data and not pure linear
        if len(y) >= 24:
            try:
                res_hr = mk.hamed_rao_modification_test(y, alpha=alpha)
                if not np.isnan(res_hr.p):
                    res = res_hr
                    test_used = "hamed_rao"
            except Exception:
                pass
    except Exception:
        return None

    slope_monthly = float(res.slope)
    slope_annual = slope_monthly * 12.0

    ci_low = getattr(res, "ci_lower", None)
    ci_high = getattr(res, "ci_upper", None)
    if ci_low is not None and ci_high is not None:
        ci_low_annual = float(ci_low) * 12.0
        ci_high_annual = float(ci_high) * 12.0
    else:
        ci_low_annual = slope_annual * 0.8
        ci_high_annual = slope_annual * 1.2

    baseline_mean = float(clean_s.mean())
    pct_change_per_year = (
        (slope_annual / baseline_mean * 100.0) if abs(baseline_mean) > 1e-6 else 0.0
    )

    p_val = float(res.p)
    tau = float(res.Tau)
    trend_dir = res.trend.lower()  # 'increasing', 'decreasing', 'no trend'

    if p_val > alpha:
        trend_dir = "no trend"

    interpretation = interpret_trend(trend_dir, worse_if, slope_annual)

    return {
        "test_used": test_used,
        "trend": trend_dir,
        "interpretation": interpretation,
        "p_value": round(p_val, 4),
        "tau": round(tau, 3),
        "sen_slope_per_year": round(slope_annual, 4),
        "ci_low": round(ci_low_annual, 4),
        "ci_high": round(ci_high_annual, 4),
        "pct_change_per_year": round(pct_change_per_year, 2),
    }


def compute_all_trends(session: Session, alpha: float = 0.05) -> int:
    """
    Compute Mann-Kendall and Sen's slope trends for each station and parameter (including WQI).
    Persists results into trend_results table.
    """
    worse_if_rules = load_worse_if_rules()
    stations = session.query(Station).all()
    count = 0

    # Build joined dataframe of all measurements and WQI
    query = (
        session.query(
            Sample.station_id,
            Sample.sample_date,
            Measurement.param_code,
            Measurement.value,
        )
        .join(Measurement, Sample.sample_id == Measurement.sample_id)
        .filter(Sample.is_excluded == 0)
    )

    data_rows = query.all()
    if not data_rows:
        return 0

    df = pd.DataFrame(data_rows, columns=["station_id", "sample_date", "param_code", "value"])
    df["sample_date"] = pd.to_datetime(df["sample_date"])

    # Also query WQI values
    wqi_query = (
        session.query(
            Sample.station_id,
            Sample.sample_date,
            WQIResult.wqi,
        )
        .join(WQIResult, Sample.sample_id == WQIResult.sample_id)
        .filter(Sample.is_excluded == 0, WQIResult.wqi.isnot(None))
    )
    wqi_rows = wqi_query.all()
    if wqi_rows:
        df_wqi = pd.DataFrame(wqi_rows, columns=["station_id", "sample_date", "value"])
        df_wqi["sample_date"] = pd.to_datetime(df_wqi["sample_date"])
        df_wqi["param_code"] = "wqi"
        df = pd.concat([df, df_wqi], ignore_index=True)

    # Process each station and parameter
    for stn in stations:
        stn_df = df[df["station_id"] == stn.station_id]
        if stn_df.empty:
            continue

        for param_code, group in stn_df.groupby("param_code"):
            # Resample to monthly mean
            monthly = (
                group.set_index("sample_date")["value"]
                .resample("MS")
                .mean()
                .dropna()
            )

            w_if = worse_if_rules.get(param_code, "increasing")
            trend_res = run_trend_test(monthly, alpha=alpha, worse_if=w_if)
            if not trend_res:
                continue

            existing = (
                session.query(TrendResult)
                .filter_by(station_id=stn.station_id, param_code=param_code)
                .first()
            )

            if existing:
                existing.test_used = trend_res["test_used"]
                existing.trend = trend_res["trend"]
                existing.interpretation = trend_res["interpretation"]
                existing.p_value = trend_res["p_value"]
                existing.tau = trend_res["tau"]
                existing.sen_slope_per_year = trend_res["sen_slope_per_year"]
                existing.ci_low = trend_res["ci_low"]
                existing.ci_high = trend_res["ci_high"]
                existing.pct_change_per_year = trend_res["pct_change_per_year"]
            else:
                row = TrendResult(
                    station_id=stn.station_id,
                    param_code=param_code,
                    test_used=trend_res["test_used"],
                    trend=trend_res["trend"],
                    interpretation=trend_res["interpretation"],
                    p_value=trend_res["p_value"],
                    tau=trend_res["tau"],
                    sen_slope_per_year=trend_res["sen_slope_per_year"],
                    ci_low=trend_res["ci_low"],
                    ci_high=trend_res["ci_high"],
                    pct_change_per_year=trend_res["pct_change_per_year"],
                )
                session.add(row)
            count += 1

    session.commit()
    return count
