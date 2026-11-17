"""
Sampling Priority Scoring Module for RiverWatch.
Calculates multi-criteria priority index for river monitoring stations,
incorporating recent quality deterioration, Sen's slope, violation frequency,
sampling recency, and data completeness, with live weight recomputation.
"""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
import yaml
from sqlalchemy.orm import Session

from src.data.db import Sample, Station, StationPriority, TrendResult, WQIResult

CONFIG_DIR = Path(__file__).resolve().parent.parent.parent / "config"


def load_priority_weights() -> Dict[str, float]:
    analysis_path = CONFIG_DIR / "analysis.yaml"
    with open(analysis_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("priority_weights", {
        "wqi_12m": 0.30,
        "wqi_slope": 0.25,
        "violation_rate": 0.20,
        "recency": 0.15,
        "variability_gap": 0.10,
    })


def min_max_norm(val: float, min_val: float, max_val: float) -> float:
    if abs(max_val - min_val) < 1e-9:
        return 0.5
    return float(np.clip((val - min_val) / (max_val - min_val), 0.0, 1.0))


def compute_priority_scores(
    session: Session, custom_weights: Optional[Dict[str, float]] = None
) -> List[Dict[str, Any]]:
    """
    Compute priority scores for all stations and save to station_priority table.
    """
    weights = custom_weights or load_priority_weights()
    w_wqi = weights.get("wqi_12m", 0.30)
    w_slope = weights.get("wqi_slope", 0.25)
    w_viol = weights.get("violation_rate", 0.20)
    w_rec = weights.get("recency", 0.15)
    w_gap = weights.get("variability_gap", 0.10)

    stations = session.query(Station).all()
    if not stations:
        return []

    # Get today or max sample date in dataset to evaluate recency
    max_date_row = session.query(Sample.sample_date).order_by(Sample.sample_date.desc()).first()
    ref_date = max_date_row[0] if max_date_row else date.today()

    station_metrics = []

    for stn in stations:
        # Fetch samples and WQI for this station
        q = (
            session.query(Sample.sample_date, WQIResult.wqi, WQIResult.cpcb_class)
            .outerjoin(WQIResult, Sample.sample_id == WQIResult.sample_id)
            .filter(Sample.station_id == stn.station_id, Sample.is_excluded == 0)
            .order_by(Sample.sample_date.asc())
            .all()
        )

        if not q:
            continue

        dates = [row[0] for row in q]
        wqis = [row[1] for row in q if row[1] is not None]
        cpcb_classes = [row[2] for row in q if row[2] is not None]

        # 1. Mean WQI of last 12 months (or last 12 available samples)
        last_12_wqi = wqis[-12:] if len(wqis) >= 12 else wqis
        mean_wqi_12m = float(np.mean(last_12_wqi)) if last_12_wqi else 50.0

        # 2. WQI slope from TrendResult
        t_row = (
            session.query(TrendResult)
            .filter_by(station_id=stn.station_id, param_code="wqi")
            .first()
        )
        # Positive slope means worsening WQI
        wqi_slope = float(t_row.sen_slope_per_year) if (t_row and t_row.sen_slope_per_year) else 0.0
        # If trend is decreasing (improving), keep slope at 0 or negative
        wqi_slope = max(0.0, wqi_slope)

        # 3. Violation rate (% of samples failing Class B or designated criteria)
        n_total = len(cpcb_classes)
        # Non-compliant: not Class A and not Class B
        n_viol = sum(1 for c in cpcb_classes if c not in ["Class A", "Class B"])
        violation_rate = (n_viol / n_total) if n_total > 0 else 0.0

        # 4. Days since last sample
        last_date = dates[-1]
        days_since = max(0, (ref_date - last_date).days)

        # 5. Gap score / coefficient of variation
        wqi_cv = (float(np.std(wqis) / np.mean(wqis))) if (wqis and np.mean(wqis) > 0) else 0.1

        station_metrics.append({
            "station_id": stn.station_id,
            "station_name": stn.station_name,
            "mean_wqi_12m": mean_wqi_12m,
            "wqi_slope": wqi_slope,
            "violation_rate": violation_rate,
            "days_since_last_sample": days_since,
            "gap_score": wqi_cv,
        })

    if not station_metrics:
        return []

    df_m = pd.DataFrame(station_metrics)

    # Normalize each column
    min_wqi, max_wqi = df_m["mean_wqi_12m"].min(), df_m["mean_wqi_12m"].max()
    min_slp, max_slp = df_m["wqi_slope"].min(), df_m["wqi_slope"].max()
    min_vio, max_vio = df_m["violation_rate"].min(), df_m["violation_rate"].max()
    min_day, max_day = df_m["days_since_last_sample"].min(), df_m["days_since_last_sample"].max()
    min_gap, max_gap = df_m["gap_score"].min(), df_m["gap_score"].max()

    results = []
    for _, row in df_m.iterrows():
        n_wqi = min_max_norm(row["mean_wqi_12m"], min_wqi, max_wqi)
        n_slp = min_max_norm(row["wqi_slope"], min_slp, max_slp)
        n_vio = min_max_norm(row["violation_rate"], min_vio, max_vio)
        n_day = min_max_norm(row["days_since_last_sample"], min_day, max_day)
        n_gap = min_max_norm(row["gap_score"], min_gap, max_gap)

        score = (w_wqi * n_wqi) + (w_slope * n_slp) + (w_viol * n_vio) + (w_rec * n_day) + (w_gap * n_gap)

        # Reason text
        reasons = []
        if row["mean_wqi_12m"] > 60:
            reasons.append(f"Elevated WQI ({round(row['mean_wqi_12m'], 1)})")
        if row["wqi_slope"] > 0.5:
            reasons.append(f"Worsening quality trend (+{round(row['wqi_slope'], 2)}/yr)")
        if row["violation_rate"] > 0.4:
            reasons.append(f"{round(row['violation_rate'] * 100)}% CPCB violation rate")
        if row["days_since_last_sample"] > 60:
            reasons.append(f"No sampling for {row['days_since_last_sample']} days")

        reason_str = "; ".join(reasons) if reasons else "Routine monitoring schedule adequate."

        results.append({
            "station_id": row["station_id"],
            "station_name": row["station_name"],
            "mean_wqi_12m": round(row["mean_wqi_12m"], 2),
            "wqi_slope": round(row["wqi_slope"], 3),
            "violation_rate": round(row["violation_rate"], 3),
            "days_since_last_sample": int(row["days_since_last_sample"]),
            "gap_score": round(row["gap_score"], 3),
            "priority_score": round(float(score), 4),
            "reason": reason_str,
        })

    # Sort descending by priority score
    results.sort(key=lambda x: x["priority_score"], reverse=True)

    # Save to database
    session.query(StationPriority).delete()
    for rank_idx, r in enumerate(results, start=1):
        r["priority_rank"] = rank_idx
        row_obj = StationPriority(
            station_id=r["station_id"],
            mean_wqi_12m=r["mean_wqi_12m"],
            wqi_slope=r["wqi_slope"],
            violation_rate=r["violation_rate"],
            days_since_last_sample=r["days_since_last_sample"],
            gap_score=r["gap_score"],
            priority_score=r["priority_score"],
            priority_rank=rank_idx,
            reason=r["reason"],
        )
        session.add(row_obj)

    session.commit()
    return results
