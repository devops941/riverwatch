"""
Uploads and Ingestion Router for RiverWatch.
Handles CSV/Excel upload, validation issue queries, inline issue resolution,
and database committing.
"""
from __future__ import annotations

import io
from pathlib import Path
from typing import List, Optional

import pandas as pd
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session

from backend.deps import get_db_session
from backend.schemas import IssuePatchRequest, UploadSummary, ValidationIssueItem
from src.analysis.compliance import compute_all_compliance
from src.analysis.correlation import compute_all_correlations
from src.analysis.drivers import compute_all_drivers
from src.analysis.pca import compute_all_pca
from src.analysis.priority import compute_priority_scores
from src.analysis.trend import compute_all_trends
from src.analysis.wqi import compute_all_wqi
from src.data.db import CorrectionAudit, Upload, ValidationIssue
from src.data.ingest import ingest_file
from src.data.preprocess import commit_upload_to_db
from src.data.synthetic import SAMPLE_DIR, save_sample_datasets
from src.data.validate import validate_dataframe

router = APIRouter(prefix="/api", tags=["Uploads & Ingestion"])
UPLOADS_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "uploads"


@router.get("/template")
def download_template():
    """
    Download empty CSV template for RiverWatch monitoring uploads.
    """
    SAMPLE_DIR.mkdir(parents=True, exist_ok=True)
    template_path = SAMPLE_DIR / "riverwatch_template.csv"
    if not template_path.exists():
        save_sample_datasets()
    return FileResponse(
        path=template_path,
        media_type="text/csv",
        filename="riverwatch_template.csv",
    )


@router.post("/uploads", response_model=UploadSummary)
async def upload_file(
    file: UploadFile = File(...),
    session: Session = Depends(get_db_session),
):
    """
    Upload CSV or Excel file, validate schema and values, and record issues.
    """
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    content = await file.read()
    filename = file.filename or "upload.csv"

    # Save to disk
    save_path = UPLOADS_DIR / filename
    with open(save_path, "wb") as f:
        f.write(content)

    try:
        df_mapped, meta = ingest_file(content, filename)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to read or parse file: {str(e)}",
        )

    # Validate
    issues = validate_dataframe(df_mapped)
    n_errors = sum(1 for i in issues if i["severity"] == "error")
    n_warnings = sum(1 for i in issues if i["severity"] == "warning")

    upload_rec = Upload(
        filename=filename,
        status="validated",
        n_rows=len(df_mapped),
        n_errors=n_errors,
        n_warnings=n_warnings,
    )
    session.add(upload_rec)
    session.flush()

    for iss in issues:
        v_rec = ValidationIssue(
            upload_id=upload_rec.upload_id,
            row_number=iss.get("row_number"),
            column_name=iss.get("column_name"),
            value=str(iss.get("value", "")),
            severity=iss.get("severity", "warning"),
            rule=iss.get("rule", "general"),
            message=iss.get("message", ""),
            suggestion=iss.get("suggestion", ""),
            status="open",
        )
        session.add(v_rec)

    session.commit()

    return UploadSummary(
        upload_id=upload_rec.upload_id,
        filename=upload_rec.filename,
        uploaded_at=upload_rec.uploaded_at,
        status=upload_rec.status,
        n_rows=upload_rec.n_rows,
        n_errors=upload_rec.n_errors,
        n_warnings=upload_rec.n_warnings,
    )


@router.get("/uploads/{upload_id}/issues", response_model=List[ValidationIssueItem])
def get_upload_issues(
    upload_id: int,
    severity: Optional[str] = Query(None, description="'error' | 'warning'"),
    status: Optional[str] = Query(None, description="'open' | 'fixed' | 'ignored' | 'excluded'"),
    session: Session = Depends(get_db_session),
):
    """
    List validation issues for a given upload with optional severity/status filters.
    """
    q = session.query(ValidationIssue).filter(ValidationIssue.upload_id == upload_id)
    if severity:
        q = q.filter(ValidationIssue.severity == severity.lower())
    if status:
        q = q.filter(ValidationIssue.status == status.lower())

    records = q.order_by(ValidationIssue.row_number.asc()).all()
    return [
        ValidationIssueItem(
            issue_id=r.issue_id,
            upload_id=r.upload_id,
            row_number=r.row_number,
            column_name=r.column_name,
            value=r.value,
            severity=r.severity,
            rule=r.rule,
            message=r.message,
            suggestion=r.suggestion,
            status=r.status,
        )
        for r in records
    ]


@router.patch("/uploads/{upload_id}/issues/{issue_id}")
def update_issue_status(
    upload_id: int,
    issue_id: int,
    payload: IssuePatchRequest,
    session: Session = Depends(get_db_session),
):
    """
    Fix value, ignore issue, or exclude row, logging to audit trail.
    """
    iss = session.query(ValidationIssue).filter_by(issue_id=issue_id, upload_id=upload_id).first()
    if not iss:
        raise HTTPException(status_code=404, detail="Validation issue not found.")

    if payload.action == "ignore":
        iss.status = "ignored"
    elif payload.action == "exclude_row":
        iss.status = "excluded"
    elif payload.action == "fix":
        iss.status = "fixed"
        audit = CorrectionAudit(
            sample_id=None,
            param_code=iss.column_name,
            old_value=float(iss.value) if (iss.value and iss.value.replace(".", "", 1).isdigit()) else None,
            new_value=float(payload.new_value) if payload.new_value else None,
            reason=payload.reason or "Fixed in validation review",
        )
        session.add(audit)
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported action '{payload.action}'.")

    session.commit()
    return {"status": "success", "issue_id": issue_id, "new_status": iss.status}


@router.post("/uploads/{upload_id}/commit")
def commit_upload(
    upload_id: int,
    duplicate_strategy: str = Query("keep_first"),
    session: Session = Depends(get_db_session),
):
    """
    Preprocess and commit upload data into database tables.
    """
    up = session.query(Upload).filter_by(upload_id=upload_id).first()
    if not up:
        raise HTTPException(status_code=404, detail="Upload not found.")

    file_path = UPLOADS_DIR / up.filename
    if not file_path.exists():
        raise HTTPException(status_code=400, detail="Original upload file missing on server.")

    with open(file_path, "rb") as f:
        content = f.read()

    df_mapped, _ = ingest_file(content, up.filename)

    # Check for excluded rows in issues
    excluded_issues = (
        session.query(ValidationIssue)
        .filter_by(upload_id=upload_id, status="excluded")
        .all()
    )
    excluded_rows = [i.row_number for i in excluded_issues if i.row_number is not None]

    res = commit_upload_to_db(
        df_mapped,
        upload_id=upload_id,
        session=session,
        duplicate_strategy=duplicate_strategy,
        excluded_rows=excluded_rows,
    )

    # Automatically run analysis
    compute_all_wqi(session)
    compute_all_compliance(session)
    compute_all_trends(session)
    compute_all_correlations(session)
    compute_all_pca(session)
    compute_all_drivers(session)
    compute_priority_scores(session)

    return {
        "status": "committed",
        "upload_id": upload_id,
        "samples_committed": res["samples_committed"],
        "measurements_committed": res["measurements_committed"],
    }


@router.post("/datasets/sample")
def load_sample_dataset(session: Session = Depends(get_db_session)):
    """
    Generate synthetic clean data, ingest, commit, and run complete analysis.
    """
    clean_p, _, _ = save_sample_datasets()
    with open(clean_p, "rb") as f:
        content = f.read()

    df_mapped, _ = ingest_file(content, "riverwatch_synthetic_clean.csv")

    up = Upload(
        filename="riverwatch_synthetic_clean.csv",
        status="committed",
        n_rows=len(df_mapped),
        n_errors=0,
        n_warnings=0,
    )
    session.add(up)
    session.flush()

    res = commit_upload_to_db(df_mapped, upload_id=up.upload_id, session=session)

    # Run analytical engine
    compute_all_wqi(session)
    compute_all_compliance(session)
    compute_all_trends(session)
    compute_all_correlations(session)
    compute_all_pca(session)
    compute_all_drivers(session)
    compute_priority_scores(session)

    return {
        "status": "sample_dataset_loaded",
        "upload_id": up.upload_id,
        "n_samples": res["samples_committed"],
        "n_measurements": res["measurements_committed"],
    }
