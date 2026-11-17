"""
Driver Ranking Module for RiverWatch.
Synthesizes PCA loadings, Spearman correlations with WQI, and early-vs-late change
contributions into a composite driver score identifying the variables most responsible
for water quality deterioration.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
import yaml
from sqlalchemy.orm import Session

from src.analysis.correlation import analyze_early_vs_late_change
from src.data.db import DriverRanking, Measurement, Parameter, PCAResult, Sample, WQIResult

CONFIG_DIR = Path(__file__).resolve().parent.parent.parent / "config"


def load_driver_weights() -> Dict[str, float]:
    analysis_path = CONFIG_DIR / "analysis.yaml"
    with open(analysis_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("driver_weights", {
        "pca_loading": 0.35,
        "correlation": 0.35,
        "change_contribution": 0.30,
    })


def min_max_normalize(series: pd.Series) -> pd.Series:
    s_min = series.min()
    s_max = series.max()
    if pd.isna(s_min) or pd.isna(s_max) or abs(s_max - s_min) < 1e-9:
        return pd.Series(0.5, index=series.index)
    return (series - s_min) / (s_max - s_min)


def generate_driver_explanation(
    param_code: str, rank: int, combined_score: float, top_component: str
) -> str:
    descriptions = {
        "bod_mgl": "Organic sewage and untreated effluent; depletes oxygen critical for aquatic biodiversity.",
        "do_mgl": "Oxygen saturation vital for river ecosystem; severe deficit indicates excessive organic loading.",
        "faecal_coliform_mpn": "Direct indicator of human/animal fecal contamination and waterborne pathogen risk.",
        "total_coliform_mpn": "General bacterial contamination from surface runoff and domestic sewage.",
        "ammonia_mgl": "Toxic byproduct of domestic wastewater decomposition and agricultural discharges.",
        "nitrate_mgl": "Nutrient pollution causing eutrophication from fertilizers and municipal runoff.",
        "turbidity_ntu": "Suspended sediment from soil erosion and industrial/construction runoff.",
        "conductivity_uscm": "Dissolved ionic mineral content and industrial effluent discharge.",
        "tds_mgl": "Total dissolved solids affecting salinity and industrial water usability.",
        "cod_mgl": "Chemical oxidizable pollutants indicating non-biodegradable industrial waste.",
        "ph": "Acid-base imbalance indicating chemical effluent or extreme algal blooms.",
        "temp_c": "Thermal pollution altering biochemical reaction rates and dissolved gas solubility.",
    }
    base_desc = descriptions.get(
        param_code, "Contributes meaningfully to river water quality variability."
    )
    if rank == 1:
        return f"Primary Driver (#{rank}): {base_desc} (Impact score: {round(combined_score, 2)})."
    elif rank <= 3:
        return f"Major Co-Factor (#{rank}): {base_desc} (Impact score: {round(combined_score, 2)})."
    else:
        return f"Secondary Factor (#{rank}): {base_desc}."


def compute_all_drivers(session: Session) -> List[Dict[str, Any]]:
    """
    Calculate composite driver scores and persist to driver_ranking table.
    """
    weights = load_driver_weights()

    # 1. Fetch PCA loadings
    pca_rows = session.query(PCAResult).all()
    pca_scores_dict: Dict[str, float] = {}

    for row in pca_rows:
        p = row.param_code
        evr = row.explained_variance_ratio or 0.0
        loading = abs(row.loading or 0.0)
        pca_scores_dict[p] = pca_scores_dict.get(p, 0.0) + (loading * evr)

    # 2. Fetch wide data with WQI to compute correlation with WQI
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
        return []

    df_long = pd.DataFrame(data, columns=["sample_id", "station_id", "sample_date", "param_code", "value"])
    df_wide = df_long.pivot_table(index=["sample_id", "station_id", "sample_date"], columns="param_code", values="value").reset_index()

    # Get WQI for sample_id
    wqi_rows = session.query(WQIResult.sample_id, WQIResult.wqi).filter(WQIResult.wqi.isnot(None)).all()
    wqi_df = pd.DataFrame(wqi_rows, columns=["sample_id", "wqi"])
    df_wide = pd.merge(df_wide, wqi_df, on="sample_id", how="left")

    corr_dict: Dict[str, float] = {}
    if "wqi" in df_wide.columns:
        wqi_s = df_wide["wqi"]
        for col in df_wide.columns:
            if col not in ["sample_id", "station_id", "sample_date", "wqi"]:
                sub = df_wide[[col, "wqi"]].dropna()
                if len(sub) >= 8:
                    from scipy.stats import spearmanr
                    r, _ = spearmanr(sub[col], sub["wqi"])
                    corr_dict[col] = abs(float(r)) if not np.isnan(r) else 0.0
                else:
                    corr_dict[col] = 0.0

    # 3. Early vs Late Change Analysis
    change_res = analyze_early_vs_late_change(df_wide, date_col="sample_date")
    change_dict: Dict[str, float] = {}
    for p, stats in change_res.items():
        change_dict[p] = abs(stats.get("rank_biserial", 0.0))

    # 4. Combine signals
    all_params = sorted(list(set(pca_scores_dict.keys()).union(set(corr_dict.keys()))))
    if not all_params:
        return []

    s_pca = pd.Series([pca_scores_dict.get(p, 0.0) for p in all_params], index=all_params)
    s_corr = pd.Series([corr_dict.get(p, 0.0) for p in all_params], index=all_params)
    s_change = pd.Series([change_dict.get(p, 0.0) for p in all_params], index=all_params)

    norm_pca = min_max_normalize(s_pca)
    norm_corr = min_max_normalize(s_corr)
    norm_change = min_max_normalize(s_change)

    w_pca = weights.get("pca_loading", 0.35)
    w_corr = weights.get("correlation", 0.35)
    w_change = weights.get("change_contribution", 0.30)

    combined = (w_pca * norm_pca) + (w_corr * norm_corr) + (w_change * norm_change)
    ranked = combined.sort_values(ascending=False)

    session.query(DriverRanking).delete()
    result_list = []

    for rank_idx, (p_code, c_score) in enumerate(ranked.items(), start=1):
        expl = generate_driver_explanation(p_code, rank_idx, float(c_score), "PC1")
        row = DriverRanking(
            param_code=p_code,
            pca_score=round(float(norm_pca[p_code]), 3),
            corr_score=round(float(norm_corr[p_code]), 3),
            change_contribution=round(float(norm_change[p_code]), 3),
            combined_score=round(float(c_score), 3),
            rank=rank_idx,
            explanation=expl,
        )
        session.add(row)
        result_list.append({
            "param_code": p_code,
            "pca_score": round(float(norm_pca[p_code]), 3),
            "corr_score": round(float(norm_corr[p_code]), 3),
            "change_contribution": round(float(norm_change[p_code]), 3),
            "combined_score": round(float(c_score), 3),
            "rank": rank_idx,
            "explanation": expl,
        })

    session.commit()
    return result_list
