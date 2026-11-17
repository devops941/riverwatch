"""
Report Generation Module for RiverWatch.
Generates comprehensive executive water quality reports in HTML and PDF formats,
integrating analytical KPIs, compliance metrics, station priority ranks, and charts.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import jinja2
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pymupdf  # PyMuPDF 2.0
from sqlalchemy.orm import Session

from src.data.db import (
    DriverRanking,
    Report,
    Sample,
    Station,
    StationPriority,
    TrendResult,
    WQIResult,
    get_session_factory,
)

OUTPUTS_DIR = Path(__file__).resolve().parent.parent.parent / "outputs"
TEMPLATE_PATH = Path(__file__).resolve().parent / "template.html.j2"


def generate_longitudinal_chart(session: Session, output_path: Path) -> Optional[Path]:
    """
    Generate an upstream-to-downstream river profile chart with matplotlib.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Query station order and mean WQI
    q = (
        session.query(
            Station.river_order,
            Station.station_name,
            WQIResult.wqi,
        )
        .join(Sample, Station.station_id == Sample.station_id)
        .join(WQIResult, Sample.sample_id == WQIResult.sample_id)
        .filter(Sample.is_excluded == 0, WQIResult.wqi.isnot(None))
        .all()
    )

    if not q:
        return None

    df = pd.DataFrame(q, columns=["order", "name", "wqi"])
    grouped = df.groupby(["order", "name"])["wqi"].agg(["mean", "std"]).reset_index()
    grouped = grouped.sort_values("order")

    plt.figure(figsize=(9, 4.5), dpi=150)
    plt.style.use("seaborn-v0_8-whitegrid" if "seaborn-v0_8-whitegrid" in plt.style.available else "default")

    x = np.arange(len(grouped))
    plt.plot(x, grouped["mean"], marker="o", color="#0284c7", linewidth=2.5, markersize=7, label="Mean WQI")
    plt.fill_between(
        x,
        grouped["mean"] - grouped["std"].fillna(0),
        grouped["mean"] + grouped["std"].fillna(0),
        alpha=0.15,
        color="#0284c7",
        label="± 1 Std Dev",
    )

    # Threshold horizontal lines
    plt.axhline(25, color="#10b981", linestyle="--", alpha=0.7, label="Excellent (<=25)")
    plt.axhline(50, color="#06b6d4", linestyle="--", alpha=0.7, label="Good (<=50)")
    plt.axhline(75, color="#f59e0b", linestyle="--", alpha=0.7, label="Poor (<=75)")
    plt.axhline(100, color="#ef4444", linestyle="--", alpha=0.7, label="Very Poor (<=100)")

    plt.xticks(x, [n[:18] for n in grouped["name"]], rotation=25, ha="right", fontsize=9)
    plt.ylabel("Water Quality Index (WQI)", fontsize=10, fontweight="bold")
    plt.title("Upstream to Downstream River Degradation Profile", fontsize=12, fontweight="bold", pad=12)
    plt.legend(loc="upper left", framealpha=0.9, fontsize=8)
    plt.tight_layout()

    plt.savefig(output_path)
    plt.close()
    return output_path


def render_html_report(context: Dict[str, Any], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
        template_str = f.read()

    template = jinja2.Template(template_str)
    rendered = template.render(context)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(rendered)
    return output_path


def convert_html_or_build_pdf(context: Dict[str, Any], chart_img: Optional[Path], pdf_path: Path) -> Path:
    """
    Build clean executive multi-page PDF using PyMuPDF.
    """
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open()

    # Page 1: Cover & Executive Dashboard
    page1 = doc.new_page(width=595, height=842)  # A4 size in points
    rect_head = pymupdf.Rect(40, 40, 555, 90)
    page1.draw_rect(rect_head, color=(0.01, 0.52, 0.78), fill=(0.01, 0.52, 0.78))
    page1.insert_text(pymupdf.Point(55, 65), "RiverWatch: Water Quality & Pollution Intelligence", fontsize=16, color=(1, 1, 1), fontname="helv")
    page1.insert_text(pymupdf.Point(55, 82), f"River: {context['river_name']} | Generated: {context['generated_at']} | Stations: {context['n_stations']}", fontsize=10, color=(0.9, 0.9, 0.9))

    # KPI summary boxes
    kpis = [
        ("TOTAL SAMPLES", str(context["n_samples"])),
        ("MEAN WQI", str(context["mean_wqi"])),
        ("CLASS B COMPLIANCE", f"{context['pct_class_b']}%"),
        ("TOP DRIVER", str(context["top_driver"])),
    ]
    for idx, (label, val) in enumerate(kpis):
        x0 = 40 + (idx * 130)
        box = pymupdf.Rect(x0, 110, x0 + 120, 160)
        page1.draw_rect(box, color=(0.88, 0.91, 0.94), fill=(0.96, 0.98, 1.0))
        page1.insert_text(pymupdf.Point(x0 + 10, 132), val, fontsize=15, color=(0.01, 0.45, 0.72))
        page1.insert_text(pymupdf.Point(x0 + 10, 150), label, fontsize=7, color=(0.4, 0.45, 0.5))

    # Insert Chart if available
    if chart_img and chart_img.exists():
        page1.insert_image(pymupdf.Rect(40, 180, 555, 420), filename=str(chart_img))

    # Section 1: Sampling Priority Table
    page1.insert_text(pymupdf.Point(40, 450), "1. Station Health & Sampling Priority Ranking", fontsize=12, color=(0.06, 0.09, 0.16))
    y = 475
    # Table headers
    page1.draw_rect(pymupdf.Rect(40, y - 12, 555, y + 4), color=(0.85, 0.88, 0.92), fill=(0.92, 0.94, 0.97))
    page1.insert_text(pymupdf.Point(45, y), "Rank", fontsize=8, color=(0.1, 0.1, 0.1))
    page1.insert_text(pymupdf.Point(75, y), "Station Name", fontsize=8, color=(0.1, 0.1, 0.1))
    page1.insert_text(pymupdf.Point(230, y), "Latest WQI", fontsize=8, color=(0.1, 0.1, 0.1))
    page1.insert_text(pymupdf.Point(290, y), "WQI Class", fontsize=8, color=(0.1, 0.1, 0.1))
    page1.insert_text(pymupdf.Point(360, y), "Priority Score", fontsize=8, color=(0.1, 0.1, 0.1))
    page1.insert_text(pymupdf.Point(430, y), "Recommended Action", fontsize=8, color=(0.1, 0.1, 0.1))

    y += 18
    for idx, stn in enumerate(context["stations"][:8]):
        page1.insert_text(pymupdf.Point(45, y), f"#{idx+1}", fontsize=8)
        page1.insert_text(pymupdf.Point(75, y), str(stn["station_name"])[:26], fontsize=8)
        page1.insert_text(pymupdf.Point(230, y), str(stn.get("latest_wqi", "N/A")), fontsize=8)
        page1.insert_text(pymupdf.Point(290, y), str(stn.get("wqi_class", "N/A")), fontsize=8)
        page1.insert_text(pymupdf.Point(360, y), str(stn.get("priority_score", "0.0")), fontsize=8)
        page1.insert_text(pymupdf.Point(430, y), str(stn.get("priority_reason", ""))[:28], fontsize=8)
        page1.draw_line(pymupdf.Point(40, y + 4), pymupdf.Point(555, y + 4), color=(0.9, 0.9, 0.9))
        y += 18

    # Section 2: Top Drivers
    y += 20
    page1.insert_text(pymupdf.Point(40, y), "2. Identified Key Drivers of Water Quality Decline", fontsize=12, color=(0.06, 0.09, 0.16))
    y += 20
    for d in context["drivers"][:5]:
        line = f"• Rank #{d['rank']}: {d['param_code']} (Impact Score: {d['combined_score']}) - {d['explanation'][:80]}"
        page1.insert_text(pymupdf.Point(45, y), line, fontsize=8, color=(0.2, 0.2, 0.2))
        y += 16

    # Footer
    page1.insert_text(pymupdf.Point(40, 815), "Generated by RiverWatch • CPCB Designated Best Use Assessment • Confidential Environmental Audit", fontsize=7, color=(0.5, 0.5, 0.5))

    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


def generate_executive_report(session: Session, file_name_prefix: str = "riverwatch_report") -> Dict[str, Any]:
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    # 1. Total samples & mean WQI
    wqi_rows = session.query(WQIResult.wqi, WQIResult.cpcb_class).filter(WQIResult.wqi.isnot(None)).all()
    n_samples = len(wqi_rows)
    all_wqis = [r[0] for r in wqi_rows]
    mean_wqi = round(float(np.mean(all_wqis)), 2) if all_wqis else 0.0

    # Class B compliance
    n_class_b = sum(1 for r in wqi_rows if r[1] in ["Class A", "Class B"])
    pct_class_b = round((n_class_b / n_samples * 100.0), 1) if n_samples > 0 else 0.0

    # 2. Stations & priority
    stns = session.query(Station).order_by(Station.river_order.asc()).all()
    stations_data = []

    for s in stns:
        # Latest WQI
        latest_wqi_obj = (
            session.query(WQIResult.wqi, WQIResult.wqi_class)
            .join(Sample, WQIResult.sample_id == Sample.sample_id)
            .filter(Sample.station_id == s.station_id)
            .order_by(Sample.sample_date.desc())
            .first()
        )
        # Priority
        pri_obj = session.query(StationPriority).filter_by(station_id=s.station_id).first()

        wqi_val = latest_wqi_obj[0] if latest_wqi_obj else None
        wqi_cls = latest_wqi_obj[1] if latest_wqi_obj else "Unknown"

        slug = str(wqi_cls).lower().replace(" ", "-")

        stations_data.append({
            "station_id": s.station_id,
            "station_name": s.station_name,
            "river_order": s.river_order,
            "latest_wqi": wqi_val,
            "wqi_class": wqi_cls,
            "wqi_class_slug": slug,
            "priority_score": pri_obj.priority_score if pri_obj else 0.0,
            "priority_reason": pri_obj.reason if pri_obj else "Routine schedule",
        })

    # Sort stations by priority score
    stations_data.sort(key=lambda x: x["priority_score"], reverse=True)

    # 3. Drivers
    drv_rows = session.query(DriverRanking).order_by(DriverRanking.rank.asc()).all()
    drivers_data = [
        {
            "rank": d.rank,
            "param_code": d.param_code,
            "combined_score": d.combined_score,
            "pca_score": d.pca_score,
            "corr_score": d.corr_score,
            "change_contribution": d.change_contribution,
            "explanation": d.explanation,
        }
        for d in drv_rows
    ]
    top_driver = drivers_data[0]["param_code"] if drivers_data else "None"

    # 4. Trends
    trend_rows = session.query(TrendResult).order_by(TrendResult.p_value.asc()).all()
    trends_data = [
        {
            "station_id": t.station_id,
            "param_code": t.param_code,
            "test_used": t.test_used,
            "trend": t.trend,
            "interpretation": t.interpretation,
            "sen_slope_per_year": t.sen_slope_per_year,
            "p_value": t.p_value,
        }
        for t in trend_rows
    ]

    # 5. Generate Matplotlib chart
    chart_path = OUTPUTS_DIR / f"{file_name_prefix}_chart.png"
    generate_longitudinal_chart(session, chart_path)

    context = {
        "generated_at": timestamp,
        "river_name": "Ganga Basin",
        "n_stations": len(stns),
        "n_samples": n_samples,
        "mean_wqi": mean_wqi,
        "pct_class_b": pct_class_b,
        "top_driver": top_driver,
        "stations": stations_data,
        "drivers": drivers_data,
        "trends": trends_data,
        "chart_image_path": str(chart_path.name),
    }

    # Render HTML and PDF
    html_path = OUTPUTS_DIR / f"{file_name_prefix}.html"
    pdf_path = OUTPUTS_DIR / f"{file_name_prefix}.pdf"

    render_html_report(context, html_path)
    convert_html_or_build_pdf(context, chart_path, pdf_path)

    # Save to Report table
    rep = Report(
        file_path=str(pdf_path),
        scope_json=json.dumps({"n_samples": n_samples, "mean_wqi": mean_wqi, "top_driver": top_driver}),
    )
    session.add(rep)
    session.commit()

    return {
        "report_id": rep.report_id,
        "html_path": str(html_path),
        "pdf_path": str(pdf_path),
        "metrics": {"n_samples": n_samples, "mean_wqi": mean_wqi, "pct_class_b": pct_class_b},
    }
