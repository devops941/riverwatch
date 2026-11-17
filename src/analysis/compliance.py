"""
CPCB Water Quality Standards Compliance Module for RiverWatch.
Evaluates Designated Best Use Criteria (Classes A through E),
determines best satisfied class, and flags violating parameters.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import yaml

from src.data.db import Sample, WQIResult

CONFIG_DIR = Path(__file__).resolve().parent.parent.parent / "config"


def load_cpcb_criteria() -> Dict[str, Any]:
    analysis_path = CONFIG_DIR / "analysis.yaml"
    with open(analysis_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("cpcb_classes", {})


def evaluate_sample_cpcb(
    measurements: Dict[str, float], cpcb_criteria: Optional[Dict[str, Any]] = None
) -> Tuple[str, List[str]]:
    """
    Evaluate a sample's measurements against CPCB criteria (Classes A, B, C, D, E).
    Returns (best_class_name, list_of_violating_rules_for_higher_classes).
    """
    if cpcb_criteria is None:
        cpcb_criteria = load_cpcb_criteria()

    do = measurements.get("do_mgl")
    bod = measurements.get("bod_mgl")
    ph = measurements.get("ph")
    tc = measurements.get("total_coliform_mpn")
    nh3 = measurements.get("ammonia_mgl")
    ec = measurements.get("conductivity_uscm")

    violations_for_a = []
    # Check Class A
    if do is not None and do < 6.0:
        violations_for_a.append(f"DO {do} < 6.0 mg/L")
    if bod is not None and bod > 2.0:
        violations_for_a.append(f"BOD {bod} > 2.0 mg/L")
    if ph is not None and (ph < 6.5 or ph > 8.5):
        violations_for_a.append(f"pH {ph} outside [6.5, 8.5]")
    if tc is not None and tc > 50.0:
        violations_for_a.append(f"Total Coliform {tc} > 50 MPN/100mL")

    if not violations_for_a:
        return "Class A", []

    # Check Class B
    violations_for_b = []
    if do is not None and do < 5.0:
        violations_for_b.append(f"DO {do} < 5.0 mg/L")
    if bod is not None and bod > 3.0:
        violations_for_b.append(f"BOD {bod} > 3.0 mg/L")
    if ph is not None and (ph < 6.5 or ph > 8.5):
        violations_for_b.append(f"pH {ph} outside [6.5, 8.5]")
    if tc is not None and tc > 500.0:
        violations_for_b.append(f"Total Coliform {tc} > 500 MPN/100mL")

    if not violations_for_b:
        return "Class B", violations_for_a

    # Check Class C
    violations_for_c = []
    if do is not None and do < 4.0:
        violations_for_c.append(f"DO {do} < 4.0 mg/L")
    if bod is not None and bod > 3.0:
        violations_for_c.append(f"BOD {bod} > 3.0 mg/L")
    if ph is not None and (ph < 6.0 or ph > 9.0):
        violations_for_c.append(f"pH {ph} outside [6.0, 9.0]")
    if tc is not None and tc > 5000.0:
        violations_for_c.append(f"Total Coliform {tc} > 5000 MPN/100mL")

    if not violations_for_c:
        return "Class C", violations_for_b

    # Check Class D (Fisheries)
    violations_for_d = []
    if do is not None and do < 4.0:
        violations_for_d.append(f"DO {do} < 4.0 mg/L")
    if ph is not None and (ph < 6.5 or ph > 8.5):
        violations_for_d.append(f"pH {ph} outside [6.5, 8.5]")
    if nh3 is not None and nh3 > 1.2:
        violations_for_d.append(f"Free Ammonia {nh3} > 1.2 mg/L")

    if not violations_for_d:
        return "Class D", violations_for_c

    # Check Class E (Irrigation/Cooling)
    violations_for_e = []
    if ph is not None and (ph < 6.0 or ph > 8.5):
        violations_for_e.append(f"pH {ph} outside [6.0, 8.5]")
    if ec is not None and ec > 2250.0:
        violations_for_e.append(f"Conductivity {ec} > 2250 µS/cm")

    if not violations_for_e:
        return "Class E", violations_for_d

    return "Below Class E", violations_for_e


def compute_all_compliance(session) -> int:
    """
    Evaluate compliance for all samples and update wqi_results table.
    """
    cpcb_criteria = load_cpcb_criteria()
    samples = session.query(Sample).filter(Sample.is_excluded == 0).all()
    count = 0

    for s in samples:
        meas_dict = {m.param_code: m.value for m in s.measurements if m.value is not None}
        cpcb_cls, viol = evaluate_sample_cpcb(meas_dict, cpcb_criteria)

        viol_str = "; ".join(viol[:4]) if viol else "None"

        wqi_res = session.query(WQIResult).filter_by(sample_id=s.sample_id).first()
        if wqi_res:
            wqi_res.cpcb_class = cpcb_cls
            wqi_res.violating_params = viol_str
        else:
            wqi_res = WQIResult(
                sample_id=s.sample_id,
                cpcb_class=cpcb_cls,
                violating_params=viol_str,
            )
            session.add(wqi_res)
        count += 1

    session.commit()
    return count
