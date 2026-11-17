"""
Principal Component Analysis (PCA) Module for RiverWatch.
Performs log-transformation on skewed variables, z-score standardization,
PCA decomposition using scikit-learn, scree variance calculation, biplot coordinate extraction,
and plain-language component interpretation.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler
from sqlalchemy.orm import Session

from src.data.db import Measurement, PCAResult, PCAScore, Sample

SKEWED_PARAMS = ["total_coliform_mpn", "faecal_coliform_mpn", "turbidity_ntu"]


def prepare_pca_matrix(df_wide: pd.DataFrame) -> Tuple[np.ndarray, List[str], List[int]]:
    """
    Log-transform skewed variables, impute missing with column median, and z-score standardize.
    Returns (scaled_matrix, feature_names, sample_ids).
    """
    feature_cols = [
        c for c in df_wide.columns
        if c not in ["sample_id", "station_id", "sample_date"] and df_wide[c].notna().sum() >= 10
    ]

    sample_ids = df_wide["sample_id"].tolist()
    sub_df = df_wide[feature_cols].copy()

    # Log-transform skewed parameters
    for col in feature_cols:
        if col in SKEWED_PARAMS:
            sub_df[col] = np.log10(np.clip(pd.to_numeric(sub_df[col], errors="coerce"), 0, None) + 1.0)
        else:
            sub_df[col] = pd.to_numeric(sub_df[col], errors="coerce")

    # Impute missing values with column median
    sub_df = sub_df.fillna(sub_df.median())

    scaler = StandardScaler()
    scaled_data = scaler.fit_transform(sub_df.values)

    return scaled_data, feature_cols, sample_ids


def interpret_component(component_name: str, loadings_dict: Dict[str, float]) -> str:
    """
    Generate plain-language interpretation based on top positive and negative loadings.
    """
    sorted_items = sorted(loadings_dict.items(), key=lambda x: abs(x[1]), reverse=True)
    top_3 = sorted_items[:3]
    top_str = ", ".join([f"{k} ({'+' if v > 0 else ''}{round(v, 2)})" for k, v in top_3])

    organic_markers = {"bod_mgl", "cod_mgl", "ammonia_mgl", "total_coliform_mpn", "faecal_coliform_mpn"}
    mineral_markers = {"conductivity_uscm", "tds_mgl"}

    top_keys = {k for k, _ in top_3}
    if len(top_keys.intersection(organic_markers)) >= 2:
        return f"{component_name} represents Organic & Sewage Pollution: strongly driven by {top_str}."
    elif len(top_keys.intersection(mineral_markers)) >= 1:
        return f"{component_name} represents Mineralization & Salinity: driven by {top_str}."
    else:
        return f"{component_name} represents Hydrochemical Variance: driven by {top_str}."


def run_pca_analysis(df_wide: pd.DataFrame, n_components: int = 3) -> Dict[str, Any]:
    """
    Run PCA on the wide data matrix.
    """
    if len(df_wide) < 8:
        return {"loadings": {}, "variance_ratio": [], "scores": [], "interpretations": {}}

    scaled_data, feature_cols, sample_ids = prepare_pca_matrix(df_wide)
    n_comp = min(n_components, len(feature_cols), len(scaled_data))

    pca = PCA(n_components=n_comp)
    scores = pca.fit_transform(scaled_data)

    loadings = {}
    interpretations = {}

    for comp_idx in range(n_comp):
        comp_name = f"PC{comp_idx + 1}"
        comp_loadings = {
            feature_cols[f_idx]: float(pca.components_[comp_idx, f_idx])
            for f_idx in range(len(feature_cols))
        }
        loadings[comp_name] = comp_loadings
        interpretations[comp_name] = interpret_component(comp_name, comp_loadings)

    variance_ratios = [float(v) for v in pca.explained_variance_ratio_]

    scores_list = []
    for row_idx, s_id in enumerate(sample_ids):
        score_dict = {"sample_id": s_id}
        for comp_idx in range(n_comp):
            score_dict[f"pc{comp_idx + 1}"] = float(scores[row_idx, comp_idx])
        scores_list.append(score_dict)

    return {
        "features": feature_cols,
        "loadings": loadings,
        "variance_ratio": variance_ratios,
        "interpretations": interpretations,
        "scores": scores_list,
    }


def compute_all_pca(session: Session) -> Dict[str, Any]:
    """
    Execute PCA over entire monitoring dataset and persist to pca_results and pca_scores.
    """
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
        return {}

    df_long = pd.DataFrame(data, columns=["sample_id", "station_id", "sample_date", "param_code", "value"])
    df_wide = df_long.pivot_table(index=["sample_id", "station_id", "sample_date"], columns="param_code", values="value").reset_index()

    pca_output = run_pca_analysis(df_wide, n_components=3)
    if not pca_output.get("loadings"):
        return {}

    # Clear previous PCA results
    session.query(PCAResult).delete()
    session.query(PCAScore).delete()

    loadings_dict = pca_output["loadings"]
    variance_ratios = pca_output["variance_ratio"]

    for comp_idx, (comp_name, p_loadings) in enumerate(loadings_dict.items()):
        evr = variance_ratios[comp_idx] if comp_idx < len(variance_ratios) else 0.0
        for p_code, val in p_loadings.items():
            row = PCAResult(
                component=comp_name,
                param_code=p_code,
                loading=round(val, 4),
                explained_variance_ratio=round(evr, 4),
            )
            session.add(row)

    for item in pca_output["scores"]:
        score_row = PCAScore(
            sample_id=item["sample_id"],
            pc1=round(item.get("pc1", 0.0), 3),
            pc2=round(item.get("pc2", 0.0), 3),
            pc3=round(item.get("pc3", 0.0), 3),
        )
        session.add(score_row)

    session.commit()
    return pca_output
