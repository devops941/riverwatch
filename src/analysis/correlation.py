"""
Correlation and Quality Change Analysis Module for RiverWatch.
Computes Spearman correlation matrix with Benjamini-Hochberg FDR p-value adjustment,
independent subset WQI associations, and Early vs Late period Mann-Whitney U change analysis.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy import stats
from sqlalchemy.orm import Session

from src.data.db import CorrelationResult, Measurement, Parameter, Sample, WQIResult


def benjamini_hochberg_adjust(p_values: List[float]) -> List[float]:
    """
    Apply Benjamini-Hochberg False Discovery Rate (FDR) correction to p-values.
    """
    m = len(p_values)
    if m == 0:
        return []

    # Pair with original indices
    indexed = sorted(enumerate(p_values), key=lambda x: x[1])
    adjusted = [0.0] * m

    cum_min = 1.0
    # Walk backward from largest p-value
    for k in range(m - 1, -1, -1):
        orig_idx, p = indexed[k]
        rank = k + 1
        adj_p = min(1.0, (p * m) / rank)
        cum_min = min(cum_min, adj_p)
        adjusted[orig_idx] = cum_min

    return [round(p, 4) for p in adjusted]


def compute_spearman_matrix(df_wide: pd.DataFrame) -> List[Dict[str, Any]]:
    """
    Compute pairwise Spearman rank correlation between numeric columns,
    including sample size n, raw p-value, and Benjamini-Hochberg adjusted p-value.
    """
    numeric_cols = [c for c in df_wide.columns if c not in ["sample_id", "station_id", "sample_date"]]
    pairs = []
    raw_p_values = []

    for i in range(len(numeric_cols)):
        for j in range(i, len(numeric_cols)):
            col_a = numeric_cols[i]
            col_b = numeric_cols[j]

            valid = df_wide[[col_a, col_b]].dropna()
            n = len(valid)

            if n < 5:
                continue

            if col_a == col_b:
                rho = 1.0
                p_val = 0.0
            else:
                rho_res, p_val_res = stats.spearmanr(valid[col_a], valid[col_b])
                rho = float(rho_res) if not np.isnan(rho_res) else 0.0
                p_val = float(p_val_res) if not np.isnan(p_val_res) else 1.0

            pairs.append({
                "param_a": col_a,
                "param_b": col_b,
                "spearman_rho": round(rho, 4),
                "p_value": round(p_val, 6),
                "n": n,
            })
            raw_p_values.append(p_val)

    adj_p_values = benjamini_hochberg_adjust(raw_p_values)
    for idx, item in enumerate(pairs):
        item["p_adjusted"] = adj_p_values[idx]

    return pairs


def analyze_early_vs_late_change(
    df_wide: pd.DataFrame, date_col: str = "sample_date"
) -> Dict[str, Dict[str, Any]]:
    """
    Split time series into early half and late half; run Mann-Whitney U test,
    calculate rank-biserial effect size and direction of change.
    """
    df = df_wide.copy()
    df[date_col] = pd.to_datetime(df[date_col])
    df = df.sort_values(date_col)

    n_total = len(df)
    if n_total < 10:
        return {}

    mid_idx = n_total // 2
    early_df = df.iloc[:mid_idx]
    late_df = df.iloc[mid_idx:]

    numeric_cols = [c for c in df.columns if c not in ["sample_id", "station_id", date_col]]
    change_summary = {}

    for col in numeric_cols:
        s_early = early_df[col].dropna()
        s_late = late_df[col].dropna()

        if len(s_early) < 4 or len(s_late) < 4:
            continue

        try:
            u_stat, p_val = stats.mannwhitneyu(s_early, s_late, alternative="two-sided")
            n1, n2 = len(s_early), len(s_late)
            # Rank-biserial correlation: r = 1 - 2*U / (n1*n2)
            # positive r means early > late; negative r means late > early
            r_biserial = 1.0 - (2.0 * u_stat / (n1 * n2))

            mean_early = float(s_early.mean())
            mean_late = float(s_late.mean())
            pct_change = ((mean_late - mean_early) / mean_early * 100.0) if abs(mean_early) > 1e-6 else 0.0

            change_summary[col] = {
                "u_stat": float(u_stat),
                "p_value": round(float(p_val), 4),
                "rank_biserial": round(float(r_biserial), 3),
                "mean_early": round(mean_early, 2),
                "mean_late": round(mean_late, 2),
                "pct_change": round(pct_change, 2),
            }
        except Exception:
            continue

    return change_summary


def compute_all_correlations(session: Session) -> int:
    """
    Compute pairwise correlation across all parameters in dataset
    and save into correlation_results table.
    """
    # Fetch wide matrix of all measurements
    query = (
        session.query(
            Sample.sample_id,
            Sample.station_id,
            Sample.sample_date,
            Measurement.param_code,
            Measurement.value,
        )
        .join(Measurement, Sample.sample_id == Measurement.sample_id)
        .filter(Sample.is_excluded == 0, Measurement.value.isnot(None))
    )

    data = query.all()
    if not data:
        return 0

    df_long = pd.DataFrame(data, columns=["sample_id", "station_id", "sample_date", "param_code", "value"])
    df_wide = df_long.pivot_table(index=["sample_id", "station_id", "sample_date"], columns="param_code", values="value").reset_index()

    pairs = compute_spearman_matrix(df_wide)

    # Clear and insert
    session.query(CorrelationResult).delete()

    for item in pairs:
        row = CorrelationResult(
            param_a=item["param_a"],
            param_b=item["param_b"],
            spearman_rho=item["spearman_rho"],
            p_value=item["p_value"],
            p_adjusted=item["p_adjusted"],
            n=item["n"],
        )
        session.add(row)

    session.commit()
    return len(pairs)
