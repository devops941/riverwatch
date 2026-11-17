"""
Export and Record Audit Router for RiverWatch.
Provides CSV/Excel data exports, sample records exploration, and value correction
workflows with an immutable audit trail.
"""
from __future__ import annotations

import io
from datetime import datetime
from typing import Any, Dict, List, Optional

import openpyxl
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response, StreamingResponse
from sqlalchemy.orm import Session

from backend.deps import get_db_session
from backend.schemas import (
    AuditItem,
    DataEntryRequest,
    DataEntryResponse,
    DataPreviewRequest,
    DataPreviewResponse,
    RecordPatchRequest,
    RecordSampleItem,
)
from src.analysis.compliance import compute_all_compliance, evaluate_sample_cpcb
from src.analysis.drivers import compute_all_drivers
from src.analysis.priority import compute_priority_scores
from src.analysis.wqi import compute_all_wqi, compute_sample_wqi, load_wqi_configs
from src.data.mongo_db import sync_records_to_mongo
from src.data.db import (
    CorrectionAudit,
    CorrelationResult,
    DriverRanking,
    Measurement,
    Parameter,
    Sample,
    Station,
    StationPriority,
    TrendResult,
    WQIResult,
)

router = APIRouter(prefix="/api", tags=["Export & Records"])


@router.get("/export/data.csv")
def export_cleaned_csv(session: Session = Depends(get_db_session)):
    """
    Download complete cleaned wide dataset as CSV.
    """
    q = (
        session.query(
            Sample.station_id,
            Station.station_name,
            Station.river_order,
            Station.lat,
            Station.lon,
            Sample.sample_date,
            Measurement.param_code,
            Measurement.value,
        )
        .join(Station, Sample.station_id == Station.station_id)
        .join(Measurement, Sample.sample_id == Measurement.sample_id)
        .filter(Sample.is_excluded == 0)
        .all()
    )

    if not q:
        raise HTTPException(status_code=404, detail="No data available to export.")

    df_long = pd.DataFrame(
        q,
        columns=["station_id", "station_name", "river_order", "lat", "lon", "sample_date", "param_code", "value"],
    )
    df_wide = df_long.pivot_table(
        index=["station_id", "station_name", "river_order", "lat", "lon", "sample_date"],
        columns="param_code",
        values="value",
    ).reset_index()

    stream = io.StringIO()
    df_wide.to_csv(stream, index=False)
    stream.seek(0)

    return Response(
        content=stream.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=riverwatch_cleaned_data.csv"},
    )


@router.get("/export/results.xlsx")
def export_results_excel(session: Session = Depends(get_db_session)):
    """
    Download multi-sheet comprehensive Excel workbook with all analytical tables.
    """
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        # Sheet 1: Stations & Priority
        q_pri = session.query(StationPriority).all()
        if q_pri:
            df_pri = pd.DataFrame([
                {
                    "Rank": p.priority_rank,
                    "Station ID": p.station_id,
                    "Priority Score": p.priority_score,
                    "Mean WQI (12m)": p.mean_wqi_12m,
                    "Sen Slope": p.wqi_slope,
                    "Violation Rate": p.violation_rate,
                    "Days Since Sample": p.days_since_last_sample,
                    "Recommendation": p.reason,
                }
                for p in q_pri
            ])
            df_pri.to_excel(writer, sheet_name="Sampling Priority", index=False)

        # Sheet 2: Drivers
        q_drv = session.query(DriverRanking).order_by(DriverRanking.rank.asc()).all()
        if q_drv:
            df_drv = pd.DataFrame([
                {
                    "Rank": d.rank,
                    "Parameter": d.param_code,
                    "Combined Score": d.combined_score,
                    "PCA Score": d.pca_score,
                    "Correlation Score": d.corr_score,
                    "Change Contribution": d.change_contribution,
                    "Explanation": d.explanation,
                }
                for d in q_drv
            ])
            df_drv.to_excel(writer, sheet_name="Pollution Drivers", index=False)

        # Sheet 3: Trends
        q_tr = session.query(TrendResult).all()
        if q_tr:
            df_tr = pd.DataFrame([
                {
                    "Station ID": t.station_id,
                    "Parameter": t.param_code,
                    "Test": t.test_used,
                    "Trend": t.trend,
                    "Interpretation": t.interpretation,
                    "Sen Slope / Year": t.sen_slope_per_year,
                    "p-Value": t.p_value,
                    "Kendall Tau": t.tau,
                    "% Change / Year": t.pct_change_per_year,
                }
                for t in q_tr
            ])
            df_tr.to_excel(writer, sheet_name="Trends (Mann-Kendall)", index=False)

        # Sheet 4: Correlations
        q_corr = session.query(CorrelationResult).all()
        if q_corr:
            df_corr = pd.DataFrame([
                {
                    "Param A": c.param_a,
                    "Param B": c.param_b,
                    "Spearman Rho": c.spearman_rho,
                    "p-Value": c.p_value,
                    "p-Adjusted (FDR)": c.p_adjusted,
                    "Sample Size (N)": c.n,
                }
                for c in q_corr
            ])
            df_corr.to_excel(writer, sheet_name="Correlation Matrix", index=False)

    output.seek(0)
    return Response(
        content=output.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=riverwatch_analytics_results.xlsx"},
    )


@router.get("/records")
def get_sample_records(
    station_id: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
    session: Session = Depends(get_db_session),
):
    """
    List processed sample records with measurements and WQI status.
    """
    q = (
        session.query(
            Sample.sample_id,
            Sample.station_id,
            Sample.sample_date,
            WQIResult.wqi,
            WQIResult.wqi_class,
            WQIResult.cpcb_class,
        )
        .outerjoin(WQIResult, Sample.sample_id == WQIResult.sample_id)
        .filter(Sample.is_excluded == 0)
    )
    if station_id and isinstance(station_id, str):
        q = q.filter(Sample.station_id == station_id)

    page_num = page if isinstance(page, int) else 1
    size_num = page_size if isinstance(page_size, int) else 50

    total_records = q.count()
    offset = (page_num - 1) * size_num
    records = q.order_by(Sample.sample_date.desc()).offset(offset).limit(size_num).all()

    # Load measurements for these samples
    sample_ids = [r[0] for r in records]
    meas_q = (
        session.query(
            Measurement.sample_id,
            Measurement.param_code,
            Measurement.value,
        )
        .filter(Measurement.sample_id.in_(sample_ids))
        .all()
    )

    meas_map: Dict[int, Dict[str, Optional[float]]] = {}
    for m in meas_q:
        if m[0] not in meas_map:
            meas_map[m[0]] = {}
        meas_map[m[0]][m[1]] = m[2]

    results = []
    for r in records:
        results.append(
            RecordSampleItem(
                sample_id=r[0],
                station_id=r[1],
                sample_date=str(r[2]),
                wqi=r[3],
                wqi_class=r[4],
                cpcb_class=r[5],
                measurements=meas_map.get(r[0], {}),
            )
        )

    return {
        "page": page,
        "page_size": page_size,
        "total_records": total_records,
        "total_pages": (total_records + page_size - 1) // page_size,
        "records": results,
    }


@router.patch("/records/{sample_id}/{param_code}")
def correct_measurement(
    sample_id: int,
    param_code: str,
    payload: RecordPatchRequest,
    session: Session = Depends(get_db_session),
):
    """
    Edit a measured value, logging the change in corrections_audit and updating WQI.
    """
    meas = (
        session.query(Measurement)
        .filter_by(sample_id=sample_id, param_code=param_code)
        .first()
    )
    if not meas:
        raise HTTPException(status_code=404, detail="Measurement record not found.")

    old_val = meas.value
    meas.value = payload.new_value
    meas.raw_value = str(payload.new_value)

    # Log audit entry
    audit = CorrectionAudit(
        sample_id=sample_id,
        param_code=param_code,
        old_value=old_val,
        new_value=payload.new_value,
        reason=payload.reason,
        changed_at=datetime.utcnow(),
    )
    session.add(audit)
    session.commit()

    # Recompute WQI & Compliance for this sample
    compute_all_wqi(session)
    compute_all_compliance(session)

    return {
        "status": "success",
        "sample_id": sample_id,
        "param_code": param_code,
        "old_value": old_val,
        "new_value": payload.new_value,
        "audit_id": audit.audit_id,
    }


@router.get("/records/audit", response_model=List[AuditItem])
def get_audit_trail(session: Session = Depends(get_db_session)):
    """
    Retrieve all audit records of user corrections.
    """
    audits = (
        session.query(CorrectionAudit)
        .order_by(CorrectionAudit.changed_at.desc())
        .limit(100)
        .all()
    )
    return [
        AuditItem(
            audit_id=a.audit_id,
            sample_id=a.sample_id or 0,
            param_code=a.param_code or "Unknown",
            old_value=a.old_value,
            new_value=a.new_value,
            reason=a.reason or "",
            changed_at=a.changed_at,
        )
        for a in audits
    ]


@router.post("/records/preview", response_model=DataPreviewResponse)
def preview_sample_analytics(payload: DataPreviewRequest):
    """
    Live calculation of WQI and CPCB class for a set of parameter values without saving to database.
    """
    params_config, wqi_classes = load_wqi_configs()
    wqi_res = compute_sample_wqi(payload.measurements, params_config, wqi_classes, min_params=1)
    cpcb_class, violations = evaluate_sample_cpcb(payload.measurements)
    return DataPreviewResponse(
        wqi=wqi_res.get("wqi"),
        wqi_class=wqi_res.get("wqi_class"),
        cpcb_class=cpcb_class,
        violating_params=violations,
        n_params_used=wqi_res.get("n_params_used", 0),
    )


@router.post("/records/entry", response_model=DataEntryResponse)
def submit_data_entry(
    payload: DataEntryRequest,
    session: Session = Depends(get_db_session),
):
    """
    Directly insert a new water monitoring sample with its parameter measurements,
    recompute basin WQI, CPCB compliance, drivers, and priority ranking, and sync to MongoDB.
    """
    stn = session.query(Station).filter_by(station_id=payload.station_id).first()
    if not stn:
        raise HTTPException(status_code=404, detail=f"Station '{payload.station_id}' not found.")

    try:
        sample_date = datetime.strptime(payload.sample_date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid sample_date format. Must be YYYY-MM-DD.")

    # Check if sample exists for this station and date
    sample = (
        session.query(Sample)
        .filter_by(station_id=payload.station_id, sample_date=sample_date)
        .first()
    )
    if not sample:
        sample = Sample(
            station_id=payload.station_id,
            sample_date=sample_date,
            is_excluded=0,
        )
        session.add(sample)
        session.flush()

    # Insert or update measurements
    for param_code, val in payload.measurements.items():
        if val is not None and not (isinstance(val, float) and pd.isna(val)):
            meas = (
                session.query(Measurement)
                .filter_by(sample_id=sample.sample_id, param_code=param_code)
                .first()
            )
            if meas:
                meas.value = float(val)
                meas.raw_value = str(val)
            else:
                meas = Measurement(
                    sample_id=sample.sample_id,
                    param_code=param_code,
                    value=float(val),
                    raw_value=str(val),
                    is_censored=0,
                    is_imputed=0,
                    is_outlier=0,
                )
                session.add(meas)

    session.commit()

    # Recompute analytics based on updated data
    compute_all_wqi(session)
    compute_all_compliance(session)
    compute_all_drivers(session)
    compute_priority_scores(session)

    # Fetch updated WQIResult for this sample
    wqi_row = session.query(WQIResult).filter_by(sample_id=sample.sample_id).first()

    # Sync to MongoDB if active
    sync_records_to_mongo(
        "samples",
        [{
            "_id": f"{payload.station_id}_{payload.sample_date}",
            "sample_id": sample.sample_id,
            "station_id": payload.station_id,
            "sample_date": str(sample_date),
            "measurements": payload.measurements,
            "wqi": wqi_row.wqi if wqi_row else None,
            "wqi_class": wqi_row.wqi_class if wqi_row else None,
            "cpcb_class": wqi_row.cpcb_class if wqi_row else None,
            "updated_at": datetime.utcnow().isoformat(),
        }],
        key_field="_id",
    )

    return DataEntryResponse(
        sample_id=sample.sample_id,
        station_id=payload.station_id,
        sample_date=str(sample_date),
        wqi=wqi_row.wqi if wqi_row else None,
        wqi_class=wqi_row.wqi_class if wqi_row else None,
        cpcb_class=wqi_row.cpcb_class if wqi_row else None,
        violating_params=wqi_row.violating_params if wqi_row else None,
        status="success",
        message=f"Sample recorded successfully! Computed WQI is {wqi_row.wqi if wqi_row else 'N/A'}.",
    )

