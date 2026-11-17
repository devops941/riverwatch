"""
Pydantic v2 Schemas for RiverWatch REST API.
Validates all request and response payloads.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


# ---------------- Uploads & Issues ----------------
class UploadSummary(BaseModel):
    upload_id: int
    filename: str
    uploaded_at: datetime
    status: str
    n_rows: int
    n_errors: int
    n_warnings: int


class ValidationIssueItem(BaseModel):
    issue_id: int
    upload_id: int
    row_number: Optional[int] = None
    column_name: Optional[str] = None
    value: Optional[str] = None
    severity: str
    rule: str
    message: str
    suggestion: Optional[str] = None
    status: str


class IssuePatchRequest(BaseModel):
    action: str = Field(..., description="'fix' | 'ignore' | 'exclude_row'")
    new_value: Optional[str] = None
    reason: Optional[str] = "Manual correction via UI"


class CommitRequest(BaseModel):
    duplicate_strategy: str = Field("keep_first", description="'keep_first' | 'keep_last' | 'average'")


# ---------------- Stations & Time Series ----------------
class StationItem(BaseModel):
    station_id: str
    station_name: str
    river_name: Optional[str] = "Ganga"
    lat: Optional[float] = None
    lon: Optional[float] = None
    river_order: Optional[int] = None
    latest_wqi: Optional[float] = None
    wqi_class: Optional[str] = None
    cpcb_class: Optional[str] = None
    priority_score: Optional[float] = None


class TimeSeriesPoint(BaseModel):
    sample_date: str
    value: Optional[float] = None
    is_censored: int = 0
    is_imputed: int = 0
    is_outlier: int = 0


class StationSeriesResponse(BaseModel):
    station_id: str
    param_code: str
    display_name: str
    unit: str
    standard_value: Optional[float] = None
    points: List[TimeSeriesPoint]


# ---------------- Analysis Schemas ----------------
class WQIItem(BaseModel):
    sample_id: int
    station_id: str
    sample_date: str
    wqi: Optional[float] = None
    wqi_class: Optional[str] = None
    wqi_equal_weights: Optional[float] = None
    cpcb_class: Optional[str] = None
    violating_params: Optional[str] = None
    n_params_used: int = 0


class ComplianceItem(BaseModel):
    station_id: str
    station_name: str
    pct_class_a: float
    pct_class_b: float
    pct_class_c: float
    pct_class_d: float
    pct_class_e: float
    pct_below_e: float
    dominant_violations: List[str]


class TrendItem(BaseModel):
    station_id: str
    param_code: str
    test_used: Optional[str] = None
    trend: Optional[str] = None
    interpretation: Optional[str] = None
    p_value: Optional[float] = None
    tau: Optional[float] = None
    sen_slope_per_year: Optional[float] = None
    ci_low: Optional[float] = None
    ci_high: Optional[float] = None
    pct_change_per_year: Optional[float] = None


class CorrelationItem(BaseModel):
    param_a: str
    param_b: str
    spearman_rho: float
    p_value: float
    p_adjusted: float
    n: int


class PCALoadingItem(BaseModel):
    component: str
    param_code: str
    loading: float
    explained_variance_ratio: float


class DriverItem(BaseModel):
    param_code: str
    pca_score: float
    corr_score: float
    change_contribution: float
    combined_score: float
    rank: int
    explanation: str


class PriorityItem(BaseModel):
    station_id: str
    station_name: Optional[str] = None
    mean_wqi_12m: Optional[float] = None
    wqi_slope: Optional[float] = None
    violation_rate: Optional[float] = None
    days_since_last_sample: Optional[int] = None
    gap_score: Optional[float] = None
    priority_score: Optional[float] = None
    priority_rank: Optional[int] = None
    reason: Optional[str] = None


class PriorityRecomputeRequest(BaseModel):
    weights: Dict[str, float] = Field(
        default_factory=lambda: {
            "wqi_12m": 0.30,
            "wqi_slope": 0.25,
            "violation_rate": 0.20,
            "recency": 0.15,
            "variability_gap": 0.10,
        }
    )


# ---------------- Records & Audit ----------------
class RecordMeasurement(BaseModel):
    param_code: str
    value: Optional[float] = None
    raw_value: Optional[str] = None
    is_censored: int = 0
    is_imputed: int = 0
    is_outlier: int = 0


class RecordSampleItem(BaseModel):
    sample_id: int
    station_id: str
    sample_date: str
    wqi: Optional[float] = None
    wqi_class: Optional[str] = None
    cpcb_class: Optional[str] = None
    measurements: Dict[str, Optional[float]]


class AuditItem(BaseModel):
    audit_id: int
    sample_id: int
    param_code: str
    old_value: Optional[float] = None
    new_value: Optional[float] = None
    reason: str
    changed_at: datetime


class RecordPatchRequest(BaseModel):
    new_value: float
    reason: str = Field(..., description="Audit reason for editing this measured value")


# ---------------- Direct Data Entry Schemas ----------------
class DataEntryRequest(BaseModel):
    station_id: str
    sample_date: str = Field(..., description="Sample date in YYYY-MM-DD format")
    measurements: Dict[str, float] = Field(..., description="Dictionary of parameter codes to values")
    notes: Optional[str] = "Manual field measurement"


class DataEntryResponse(BaseModel):
    sample_id: int
    station_id: str
    sample_date: str
    wqi: Optional[float] = None
    wqi_class: Optional[str] = None
    cpcb_class: Optional[str] = None
    violating_params: Optional[str] = None
    status: str = "success"
    message: str = "Data entry successfully recorded and river analytics recomputed."


class DataPreviewRequest(BaseModel):
    measurements: Dict[str, float]


class DataPreviewResponse(BaseModel):
    wqi: Optional[float] = None
    wqi_class: Optional[str] = None
    cpcb_class: Optional[str] = None
    violating_params: List[str] = []
    n_params_used: int = 0

