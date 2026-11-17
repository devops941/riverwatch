"""
Stations Router for RiverWatch.
Provides station metadata, geographical coordinates, latest environmental status,
and parameterized time-series trajectories.
"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.deps import get_db_session
from backend.schemas import StationItem, StationSeriesResponse, TimeSeriesPoint
from src.data.db import Measurement, Parameter, River, Sample, Station, StationPriority, WQIResult

router = APIRouter(prefix="/api/stations", tags=["Stations"])


@router.get("", response_model=List[StationItem])
def get_all_stations(session: Session = Depends(get_db_session)):
    """
    List all monitoring stations with latest WQI, WQI class, and sampling priority.
    """
    stations = session.query(Station).order_by(Station.river_order.asc()).all()
    results = []

    for s in stations:
        # Latest sample and WQI
        latest_wqi_obj = (
            session.query(WQIResult.wqi, WQIResult.wqi_class, WQIResult.cpcb_class)
            .join(Sample, WQIResult.sample_id == Sample.sample_id)
            .filter(Sample.station_id == s.station_id, Sample.is_excluded == 0)
            .order_by(Sample.sample_date.desc())
            .first()
        )
        pri = session.query(StationPriority).filter_by(station_id=s.station_id).first()
        river_name = s.river.river_name if s.river else "Ganga"

        results.append(
            StationItem(
                station_id=s.station_id,
                station_name=s.station_name or s.station_id,
                river_name=river_name,
                lat=s.lat,
                lon=s.lon,
                river_order=s.river_order,
                latest_wqi=latest_wqi_obj[0] if latest_wqi_obj else None,
                wqi_class=latest_wqi_obj[1] if latest_wqi_obj else None,
                cpcb_class=latest_wqi_obj[2] if latest_wqi_obj else None,
                priority_score=pri.priority_score if pri else None,
            )
        )

    return results


@router.get("/{station_id}/series", response_model=StationSeriesResponse)
def get_station_time_series(
    station_id: str,
    param: str = "wqi",
    start: Optional[str] = None,
    end: Optional[str] = None,
    session: Session = Depends(get_db_session),
):
    """
    Retrieve historical time series data for a specific station and parameter.
    """
    stn = session.query(Station).filter_by(station_id=station_id).first()
    if not stn:
        raise HTTPException(status_code=404, detail=f"Station '{station_id}' not found.")

    param_val = param if isinstance(param, str) else "wqi"

    if param_val == "wqi":
        display_name = "Water Quality Index (WQI)"
        unit = "Index Units"
        standard_val = 50.0  # Clean water boundary

        q = (
            session.query(
                Sample.sample_date,
                WQIResult.wqi,
            )
            .join(WQIResult, Sample.sample_id == WQIResult.sample_id)
            .filter(Sample.station_id == station_id, Sample.is_excluded == 0)
        )
        if start and isinstance(start, str):
            q = q.filter(Sample.sample_date >= start)
        if end and isinstance(end, str):
            q = q.filter(Sample.sample_date <= end)

        records = q.order_by(Sample.sample_date.asc()).all()
        points = [
            TimeSeriesPoint(
                sample_date=str(r[0]),
                value=r[1],
                is_censored=0,
                is_imputed=0,
                is_outlier=0,
            )
            for r in records
        ]
    else:
        p_obj = session.query(Parameter).filter_by(param_code=param_val).first()
        display_name = p_obj.display_name if p_obj else param_val
        unit = p_obj.unit if p_obj else ""
        standard_val = p_obj.standard_value if p_obj else None

        q = (
            session.query(
                Sample.sample_date,
                Measurement.value,
                Measurement.is_censored,
                Measurement.is_imputed,
                Measurement.is_outlier,
            )
            .join(Measurement, Sample.sample_id == Measurement.sample_id)
            .filter(
                Sample.station_id == station_id,
                Measurement.param_code == param_val,
                Sample.is_excluded == 0,
            )
        )
        if start and isinstance(start, str):
            q = q.filter(Sample.sample_date >= start)
        if end and isinstance(end, str):
            q = q.filter(Sample.sample_date <= end)

        records = q.order_by(Sample.sample_date.asc()).all()
        points = [
            TimeSeriesPoint(
                sample_date=str(r[0]),
                value=r[1],
                is_censored=r[2] or 0,
                is_imputed=r[3] or 0,
                is_outlier=r[4] or 0,
            )
            for r in records
        ]

    return StationSeriesResponse(
        station_id=station_id,
        param_code=param,
        display_name=display_name,
        unit=unit,
        standard_value=standard_val,
        points=points,
    )
