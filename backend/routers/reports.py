"""
Reports Router for RiverWatch.
Handles on-demand generation and downloading of PDF/HTML executive reports.
"""
from __future__ import annotations

from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from backend.deps import get_db_session
from src.data.db import Report
from src.report.generate import generate_executive_report

router = APIRouter(prefix="/api", tags=["Reports"])


@router.post("/report")
def create_report(session: Session = Depends(get_db_session)):
    """
    Generate on-demand executive report (PDF and HTML) with embedded charts and tables.
    """
    try:
        res = generate_executive_report(session)
        return {
            "status": "success",
            "report_id": res["report_id"],
            "pdf_url": f"/api/report/{res['report_id']}",
            "html_path": res["html_path"],
            "metrics": res["metrics"],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate report: {str(e)}")


@router.get("/report/{report_id}")
def download_report(report_id: int, session: Session = Depends(get_db_session)):
    """
    Download generated PDF report file.
    """
    rep = session.query(Report).filter_by(report_id=report_id).first()
    if not rep or not Path(rep.file_path).exists():
        raise HTTPException(status_code=404, detail="Report file not found.")

    return FileResponse(
        path=Path(rep.file_path),
        media_type="application/pdf",
        filename=f"riverwatch_report_{report_id}.pdf",
    )


@router.get("/reports")
def list_reports(session: Session = Depends(get_db_session)):
    """
    List all generated reports.
    """
    reps = session.query(Report).order_by(Report.created_at.desc()).all()
    return [
        {
            "report_id": r.report_id,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "file_path": r.file_path,
            "pdf_url": f"/api/report/{r.report_id}",
        }
        for r in reps
    ]
