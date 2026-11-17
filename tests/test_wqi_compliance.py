"""
Unit tests for WQI calculation and CPCB Designated Best Use compliance (Section 6.2 & 6.3).
"""
import pytest
from src.analysis.compliance import evaluate_sample_cpcb
from src.analysis.wqi import compute_sample_wqi, load_wqi_configs


@pytest.fixture
def configs():
    return load_wqi_configs()


def test_wqi_standard_limits_equal_100(configs):
    params_cfg, classes_cfg = configs

    # When all parameters are set exactly to their standard permissible limits:
    # DO = 5.0 (standard limit -> q_DO = 100)
    # BOD = 3.0 (standard limit -> q_BOD = 100)
    # Nitrate = 20.0 (standard limit -> q_NO3 = 100)
    # pH = 8.5 (standard limit -> q_pH = 100)
    # Since all q_i = 100, WQI = sum(100 * W_i) = 100.0 exactly!
    measurements = {
        "do_mgl": 5.0,
        "bod_mgl": 3.0,
        "nitrate_mgl": 20.0,
        "ph": 8.5,
    }

    res = compute_sample_wqi(measurements, params_cfg, classes_cfg, min_params=4)
    assert res["wqi"] is not None
    assert pytest.approx(res["wqi"], 0.1) == 100.0
    assert pytest.approx(res["wqi_equal_weights"], 0.1) == 100.0


def test_wqi_pristine_values_equal_zero(configs):
    params_cfg, classes_cfg = configs

    # When all parameters are set to their ideal pristine values:
    # DO = 14.6 mg/L (ideal -> q_DO = 0)
    # BOD = 0.0 (ideal -> q_BOD = 0)
    # pH = 7.0 (ideal -> q_pH = 0)
    # Nitrate = 0.0 (ideal -> q_NO3 = 0)
    measurements = {
        "do_mgl": 14.6,
        "bod_mgl": 0.0,
        "ph": 7.0,
        "nitrate_mgl": 0.0,
    }

    res = compute_sample_wqi(measurements, params_cfg, classes_cfg, min_params=4)
    assert res["wqi"] is not None
    assert pytest.approx(res["wqi"], 0.01) == 0.0
    assert res["wqi_class"] == "Excellent"


def test_wqi_insufficient_parameters(configs):
    params_cfg, classes_cfg = configs

    # Only 2 parameters provided (minimum 4 required)
    meas = {"ph": 7.5, "do_mgl": 8.0}
    res = compute_sample_wqi(meas, params_cfg, classes_cfg, min_params=4)
    assert res["wqi"] is None
    assert res["wqi_class"] == "Insufficient Data"

    # 4 parameters but neither DO nor BOD provided
    meas_no_core = {"ph": 7.5, "turbidity_ntu": 5.0, "tds_mgl": 300.0, "conductivity_uscm": 500.0}
    res_no_core = compute_sample_wqi(meas_no_core, params_cfg, classes_cfg, min_params=4)
    assert res_no_core["wqi"] is None


def test_cpcb_class_a():
    # Meets all Class A requirements: DO >= 6, BOD <= 2, pH 6.5-8.5, Coliform <= 50
    meas = {
        "do_mgl": 7.5,
        "bod_mgl": 1.2,
        "ph": 7.6,
        "total_coliform_mpn": 35.0,
    }
    c_cls, viol = evaluate_sample_cpcb(meas)
    assert c_cls == "Class A"
    assert len(viol) == 0


def test_cpcb_class_b_and_violations():
    # Satisfies Class B (DO >= 5, BOD <= 3, coliform <= 500), but fails Class A on Coliform > 50
    meas = {
        "do_mgl": 6.5,
        "bod_mgl": 1.8,
        "ph": 7.4,
        "total_coliform_mpn": 320.0,
    }
    c_cls, viol = evaluate_sample_cpcb(meas)
    assert c_cls == "Class B"
    assert any("Total Coliform" in v for v in viol)


def test_cpcb_below_class_e():
    # Severe pollution: low DO, high BOD, high coliform
    meas = {
        "do_mgl": 2.1,
        "bod_mgl": 18.0,
        "ph": 5.2,
        "total_coliform_mpn": 85000.0,
        "ammonia_mgl": 3.8,
        "conductivity_uscm": 3500.0,
    }
    c_cls, viol = evaluate_sample_cpcb(meas)
    assert c_cls == "Below Class E"
    assert len(viol) > 0
