"""
Analysis Router for RiverWatch.
Serves WQI, CPCB compliance, trends, correlation matrix, PCA,
pollution driver rankings, and station sampling priority.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.deps import get_db_session
from backend.schemas import (
    ComplianceItem,
    CorrelationItem,
    DriverItem,
    PCALoadingItem,
    PriorityItem,
    PriorityRecomputeRequest,
    TrendItem,
    WQIItem,
)
from src.analysis.compliance import compute_all_compliance
from src.analysis.correlation import compute_all_correlations
from src.analysis.drivers import compute_all_drivers
from src.analysis.pca import compute_all_pca
from src.analysis.priority import compute_priority_scores
from src.analysis.trend import compute_all_trends
from src.analysis.wqi import compute_all_wqi
from src.data.db import (
    CorrelationResult,
    DriverRanking,
    PCAResult,
    PCAScore,
    Sample,
    Station,
    StationPriority,
    TrendResult,
    WQIResult,
)

router = APIRouter(prefix="/api", tags=["Analysis Engine"])


@router.post("/analysis/run")
def trigger_analysis(session: Session = Depends(get_db_session)):
    """
    Run the entire analytical pipeline across all committed samples.
    """
    n_wqi = compute_all_wqi(session)
    n_comp = compute_all_compliance(session)
    n_trends = compute_all_trends(session)
    n_corr = compute_all_correlations(session)
    pca_res = compute_all_pca(session)
    drivers = compute_all_drivers(session)
    priorities = compute_priority_scores(session)

    return {
        "status": "success",
        "wqi_samples": n_wqi,
        "compliance_samples": n_comp,
        "trends_calculated": n_trends,
        "correlation_pairs": n_corr,
        "pca_variance": pca_res.get("variance_ratio", []),
        "top_driver": drivers[0]["param_code"] if drivers else None,
        "top_priority_station": priorities[0]["station_id"] if priorities else None,
    }


@router.get("/wqi", response_model=List[WQIItem])
def get_wqi_data(
    station_id: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    limit: int = 500,
    session: Session = Depends(get_db_session),
):
    """
    Retrieve WQI values and CPCB class ratings.
    """
    q = (
        session.query(
            Sample.sample_id,
            Sample.station_id,
            Sample.sample_date,
            WQIResult.wqi,
            WQIResult.wqi_class,
            WQIResult.wqi_equal_weights,
            WQIResult.cpcb_class,
            WQIResult.violating_params,
            WQIResult.n_params_used,
        )
        .join(WQIResult, Sample.sample_id == WQIResult.sample_id)
        .filter(Sample.is_excluded == 0, WQIResult.wqi.isnot(None))
    )

    if station_id and isinstance(station_id, str):
        q = q.filter(Sample.station_id == station_id)
    if start and isinstance(start, str):
        q = q.filter(Sample.sample_date >= start)
    if end and isinstance(end, str):
        q = q.filter(Sample.sample_date <= end)

    records = q.order_by(Sample.sample_date.asc()).limit(limit).all()

    return [
        WQIItem(
            sample_id=r.sample_id,
            station_id=r.station_id,
            sample_date=str(r.sample_date),
            wqi=r.wqi,
            wqi_class=r.wqi_class,
            wqi_equal_weights=r.wqi_equal_weights,
            cpcb_class=r.cpcb_class,
            violating_params=r.violating_params,
            n_params_used=r.n_params_used or 0,
        )
        for r in records
    ]


@router.get("/compliance", response_model=List[ComplianceItem])
def get_compliance_summary(
    station_id: Optional[str] = None,
    session: Session = Depends(get_db_session),
):
    """
    Retrieve station-level CPCB Designated Best Use compliance percentages.
    """
    stns = session.query(Station).order_by(Station.river_order.asc())
    if station_id and isinstance(station_id, str):
        stns = stns.filter(Station.station_id == station_id)
    stns_list = stns.all()

    results = []
    for s in stns_list:
        classes_q = (
            session.query(WQIResult.cpcb_class, WQIResult.violating_params)
            .join(Sample, WQIResult.sample_id == Sample.sample_id)
            .filter(Sample.station_id == s.station_id, Sample.is_excluded == 0)
            .all()
        )

        n = len(classes_q)
        if n == 0:
            continue

        counts = {"Class A": 0, "Class B": 0, "Class C": 0, "Class D": 0, "Class E": 0, "Below Class E": 0}
        all_violations = []

        for row in classes_q:
            cls = row[0] or "Below Class E"
            counts[cls] = counts.get(cls, 0) + 1
            if row[1] and row[1] != "None":
                all_violations.extend([v.strip() for v in row[1].split(";")])

        # Top 3 violations
        from collections import Counter
        top_v = [item[0] for item in Counter(all_violations).most_common(3)]

        results.append(
            ComplianceItem(
                station_id=s.station_id,
                station_name=s.station_name or s.station_id,
                pct_class_a=round(counts.get("Class A", 0) / n * 100.0, 1),
                pct_class_b=round(counts.get("Class B", 0) / n * 100.0, 1),
                pct_class_c=round(counts.get("Class C", 0) / n * 100.0, 1),
                pct_class_d=round(counts.get("Class D", 0) / n * 100.0, 1),
                pct_class_e=round(counts.get("Class E", 0) / n * 100.0, 1),
                pct_below_e=round(counts.get("Below Class E", 0) / n * 100.0, 1),
                dominant_violations=top_v,
            )
        )

    return results


@router.get("/trends", response_model=List[TrendItem])
def get_trends(
    station_id: Optional[str] = None,
    param: Optional[str] = None,
    session: Session = Depends(get_db_session),
):
    """
    Retrieve Mann-Kendall and Sen's slope trend test results.
    """
    q = session.query(TrendResult)
    if station_id and isinstance(station_id, str):
        q = q.filter(TrendResult.station_id == station_id)
    if param and isinstance(param, str):
        q = q.filter(TrendResult.param_code == param)

    records = q.order_by(TrendResult.p_value.asc()).all()
    return [
        TrendItem(
            station_id=r.station_id,
            param_code=r.param_code,
            test_used=r.test_used,
            trend=r.trend,
            interpretation=r.interpretation,
            p_value=r.p_value,
            tau=r.tau,
            sen_slope_per_year=r.sen_slope_per_year,
            ci_low=r.ci_low,
            ci_high=r.ci_high,
            pct_change_per_year=r.pct_change_per_year,
        )
        for r in records
    ]


@router.get("/correlation", response_model=List[CorrelationItem])
def get_correlation_matrix(session: Session = Depends(get_db_session)):
    """
    Retrieve pairwise Spearman correlation with FDR adjustment.
    """
    records = session.query(CorrelationResult).order_by(CorrelationResult.param_a.asc(), CorrelationResult.param_b.asc()).all()
    return [
        CorrelationItem(
            param_a=r.param_a,
            param_b=r.param_b,
            spearman_rho=r.spearman_rho,
            p_value=r.p_value,
            p_adjusted=r.p_adjusted,
            n=r.n,
        )
        for r in records
    ]


@router.get("/pca")
def get_pca_data(session: Session = Depends(get_db_session)):
    """
    Retrieve PCA loadings, explained variance ratio, and sample scores.
    """
    loadings = session.query(PCAResult).all()
    scores = (
        session.query(
            PCAScore.sample_id,
            Sample.station_id,
            Sample.sample_date,
            PCAScore.pc1,
            PCAScore.pc2,
            PCAScore.pc3,
        )
        .join(Sample, PCAScore.sample_id == Sample.sample_id)
        .all()
    )

    evr_map = {}
    loadings_by_comp: Dict[str, Dict[str, float]] = {}
    for r in loadings:
        evr_map[r.component] = r.explained_variance_ratio
        if r.component not in loadings_by_comp:
            loadings_by_comp[r.component] = {}
        loadings_by_comp[r.component][r.param_code] = r.loading

    scores_list = [
        {
            "sample_id": s.sample_id,
            "station_id": s.station_id,
            "sample_date": str(s.sample_date),
            "pc1": s.pc1,
            "pc2": s.pc2,
            "pc3": s.pc3,
        }
        for s in scores
    ]

    return {
        "explained_variance": evr_map,
        "loadings": loadings_by_comp,
        "scores": scores_list,
    }


@router.get("/drivers", response_model=List[DriverItem])
def get_driver_rankings(session: Session = Depends(get_db_session)):
    """
    Retrieve ranked pollution drivers with composite scores and explanations.
    """
    records = session.query(DriverRanking).order_by(DriverRanking.rank.asc()).all()
    return [
        DriverItem(
            param_code=r.param_code,
            pca_score=r.pca_score,
            corr_score=r.corr_score,
            change_contribution=r.change_contribution,
            combined_score=r.combined_score,
            rank=r.rank,
            explanation=r.explanation,
        )
        for r in records
    ]


@router.get("/priority", response_model=List[PriorityItem])
def get_station_priority(session: Session = Depends(get_db_session)):
    """
    Retrieve sampling priority ranking for all monitoring stations.
    """
    records = (
        session.query(
            StationPriority.station_id,
            Station.station_name,
            StationPriority.mean_wqi_12m,
            StationPriority.wqi_slope,
            StationPriority.violation_rate,
            StationPriority.days_since_last_sample,
            StationPriority.gap_score,
            StationPriority.priority_score,
            StationPriority.priority_rank,
            StationPriority.reason,
        )
        .join(Station, StationPriority.station_id == Station.station_id)
        .order_by(StationPriority.priority_rank.asc())
        .all()
    )

    return [
        PriorityItem(
            station_id=r.station_id,
            station_name=r.station_name,
            mean_wqi_12m=r.mean_wqi_12m,
            wqi_slope=r.wqi_slope,
            violation_rate=r.violation_rate,
            days_since_last_sample=r.days_since_last_sample,
            gap_score=r.gap_score,
            priority_score=r.priority_score,
            priority_rank=r.priority_rank,
            reason=r.reason,
        )
        for r in records
    ]


@router.post("/priority/recompute", response_model=List[PriorityItem])
def recompute_priority(
    payload: PriorityRecomputeRequest,
    session: Session = Depends(get_db_session),
):
    """
    Dynamically recalculate station priority ranking using custom user weights.
    """
    compute_priority_scores(session, custom_weights=payload.weights)
    return get_station_priority(session=session)
