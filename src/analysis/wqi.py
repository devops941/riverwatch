"""
Water Quality Index (WQI) computation module for RiverWatch.
Implements the weighted-arithmetic index method (Brown et al., 1970) with
renormalized weights for missing parameters and equal-weights sensitivity check.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import yaml

from src.data.db import Parameter, Sample, Measurement, WQIResult

CONFIG_DIR = Path(__file__).resolve().parent.parent.parent / "config"


def load_wqi_configs() -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    param_path = CONFIG_DIR / "parameters.yaml"
    analysis_path = CONFIG_DIR / "analysis.yaml"

    with open(param_path, "r", encoding="utf-8") as f:
        params_data = yaml.safe_load(f).get("parameters", {})

    with open(analysis_path, "r", encoding="utf-8") as f:
        analysis_data = yaml.safe_load(f)

    wqi_classes = analysis_data.get("wqi", {}).get("classes", [
        {"max": 25.0, "label": "Excellent"},
        {"max": 50.0, "label": "Good"},
        {"max": 75.0, "label": "Poor"},
        {"max": 100.0, "label": "Very Poor"},
        {"max": 9999.0, "label": "Unsuitable"},
    ])

    return params_data, wqi_classes


def get_wqi_class(wqi_val: Optional[float], classes: List[Dict[str, Any]]) -> str:
    if wqi_val is None or np.isnan(wqi_val):
        return "Insufficient Data"
    for cls in classes:
        if wqi_val <= cls["max"]:
            return cls["label"]
    return "Unsuitable"


def compute_sample_wqi(
    measurements: Dict[str, float],
    params_config: Dict[str, Any],
    classes_config: List[Dict[str, Any]],
    min_params: int = 4,
) -> Dict[str, Any]:
    """
    Compute Weighted Arithmetic WQI for a single sample dictionary of {param_code: value}.
    Returns:
      {
        "wqi": float or None,
        "wqi_class": str,
        "wqi_equal_weights": float or None,
        "n_params_used": int,
        "q_values": dict,
        "weights": dict
      }
    """
    # Filter to available parameters that have standard_value and not NaN
    avail_params = {}
    for p_code, val in measurements.items():
        if val is not None and not np.isnan(val) and p_code in params_config:
            std = params_config[p_code].get("standard_value")
            if std and std > 0:
                avail_params[p_code] = float(val)

    # Condition: Minimum 4 parameters, must include either DO or BOD
    has_do_or_bod = ("do_mgl" in avail_params) or ("bod_mgl" in avail_params)
    n_params = len(avail_params)

    if n_params < min_params or not has_do_or_bod:
        return {
            "wqi": None,
            "wqi_class": "Insufficient Data",
            "wqi_equal_weights": None,
            "n_params_used": n_params,
            "q_values": {},
            "weights": {},
        }

    # Calculate proportionality constant K = 1 / sum(1 / S_i)
    inv_std_sum = sum(1.0 / params_config[p]["standard_value"] for p in avail_params)
    K = 1.0 / inv_std_sum

    # Calculate unit weights W_i = K / S_i (sums to 1.0)
    weights = {p: K / params_config[p]["standard_value"] for p in avail_params}

    # Calculate quality ratings q_i
    q_values = {}
    for p, val in avail_params.items():
        std = params_config[p]["standard_value"]
        ideal = params_config[p].get("ideal_value", 0.0)

        if p == "do_mgl":
            # DO inverse: 100 * (14.6 - V) / (14.6 - 5.0)
            ideal_do = 14.6
            std_do = std  # 5.0
            q_i = 100.0 * (ideal_do - val) / (ideal_do - std_do)
        elif p == "ph":
            # pH deviation from 7.0
            if val >= 7.0:
                q_i = 100.0 * (val - 7.0) / (std - 7.0)  # std is 8.5
            else:
                q_i = 100.0 * (7.0 - val) / (7.0 - 6.5)
        else:
            # Standard parameters: 100 * (val - 0) / (std - 0)
            q_i = 100.0 * (val - ideal) / (std - ideal)

        q_values[p] = max(0.0, q_i)

    # WQI = sum(q_i * W_i)
    weighted_wqi = sum(q_values[p] * weights[p] for p in avail_params)
    equal_weights_wqi = sum(q_values[p] for p in avail_params) / n_params

    wqi_class = get_wqi_class(weighted_wqi, classes_config)

    return {
        "wqi": round(weighted_wqi, 2),
        "wqi_class": wqi_class,
        "wqi_equal_weights": round(equal_weights_wqi, 2),
        "n_params_used": n_params,
        "q_values": q_values,
        "weights": weights,
    }


def compute_all_wqi(session) -> int:
    """
    Calculate and persist WQI for all samples in database.
    """
    params_config, classes_config = load_wqi_configs()

    samples = session.query(Sample).filter(Sample.is_excluded == 0).all()
    count = 0

    for s in samples:
        meas_dict = {m.param_code: m.value for m in s.measurements}
        wqi_res = compute_sample_wqi(meas_dict, params_config, classes_config)

        existing = session.query(WQIResult).filter_by(sample_id=s.sample_id).first()
        if existing:
            existing.wqi = wqi_res["wqi"]
            existing.wqi_class = wqi_res["wqi_class"]
            existing.wqi_equal_weights = wqi_res["wqi_equal_weights"]
            existing.n_params_used = wqi_res["n_params_used"]
        else:
            row = WQIResult(
                sample_id=s.sample_id,
                wqi=wqi_res["wqi"],
                wqi_class=wqi_res["wqi_class"],
                wqi_equal_weights=wqi_res["wqi_equal_weights"],
                n_params_used=wqi_res["n_params_used"],
            )
            session.add(row)
        count += 1

    session.commit()
    return count
