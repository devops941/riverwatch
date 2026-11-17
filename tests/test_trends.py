"""
Unit tests for Mann-Kendall trend tests and Sen's slope estimator (Section 6.4).
"""
import numpy as np
import pandas as pd
import pytest
from src.analysis.trend import interpret_trend, run_trend_test


def test_monotonic_increasing_trend():
    # Perfectly increasing series of 24 monthly steps
    y = pd.Series([10.0 + 0.5 * i for i in range(24)])
    res = run_trend_test(y, alpha=0.05, worse_if="increasing")
    assert res is not None
    assert res["trend"] == "increasing"
    assert res["interpretation"] == "worsening"
    assert res["p_value"] < 0.05
    assert res["sen_slope_per_year"] > 0


def test_monotonic_decreasing_trend_for_do():
    # Decreasing DO series: rising DO is improving, falling DO is worsening
    y = pd.Series([9.0 - 0.2 * i for i in range(24)])
    res = run_trend_test(y, alpha=0.05, worse_if="decreasing")
    assert res is not None
    assert res["trend"] == "decreasing"
    assert res["interpretation"] == "worsening"  # lower DO is worse
    assert res["p_value"] < 0.05
    assert res["sen_slope_per_year"] < 0


def test_no_trend_noise():
    # Alternating seasonal series without monotonic trend
    y = pd.Series([50.0, 52.0, 48.0, 51.0, 49.0, 50.0, 52.0, 48.0, 51.0, 49.0, 50.0, 50.0, 51.0, 49.0])
    res = run_trend_test(y, alpha=0.05, worse_if="increasing")
    assert res is not None
    assert res["trend"] == "no trend"
    assert res["interpretation"] == "no trend"
    assert res["p_value"] > 0.05


def test_trend_interpretation_logic():
    assert interpret_trend("increasing", "increasing", 1.5) == "worsening"
    assert interpret_trend("decreasing", "increasing", -1.5) == "improving"
    assert interpret_trend("increasing", "decreasing", 1.5) == "improving"
    assert interpret_trend("decreasing", "decreasing", -1.5) == "worsening"
    assert interpret_trend("no trend", "increasing", 0.0) == "no trend"
