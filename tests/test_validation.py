"""
Unit tests for data validation rules (Section 6.1).
"""
import pandas as pd
import pytest
from src.data.validate import Validator, validate_dataframe


@pytest.fixture
def base_valid_df():
    return pd.DataFrame([
        {
            "station_id": "STN-01",
            "station_name": "Test Stn",
            "sample_date": "2023-05-15",
            "ph": 7.8,
            "do_mgl": 8.0,
            "bod_mgl": 2.2,
            "cod_mgl": 8.5,
            "nitrate_mgl": 2.1,
            "ammonia_mgl": 0.2,
            "conductivity_uscm": 450.0,
            "turbidity_ntu": 8.0,
            "tds_mgl": 280.0,
            "temp_c": 22.0,
            "lat": 28.5,
            "lon": 77.2,
        }
    ])


def test_missing_mandatory_columns():
    bad_df = pd.DataFrame([{"ph": 7.5, "do_mgl": 8.0}])
    issues = validate_dataframe(bad_df)
    rules = [i["rule"] for i in issues]
    assert "missing_mandatory_column" in rules
    assert any(i["column_name"] == "station_id" for i in issues)
    assert any(i["column_name"] == "sample_date" for i in issues)


def test_unparseable_and_future_dates(base_valid_df):
    df = base_valid_df.copy()
    # Add unparseable date
    df.at[0, "sample_date"] = "invalid-date-99"
    issues = validate_dataframe(df)
    assert any(i["rule"] == "unparseable_date" for i in issues)

    # Future date
    df.at[0, "sample_date"] = "2099-01-01"
    issues_future = validate_dataframe(df)
    assert any(i["rule"] == "future_date" for i in issues_future)


def test_physically_impossible_values(base_valid_df):
    # Impossible pH (>14)
    df = base_valid_df.copy()
    df.at[0, "ph"] = 15.5
    issues = validate_dataframe(df)
    assert any(i["rule"] == "physically_impossible_value" and i["column_name"] == "ph" for i in issues)

    # Negative DO (<0)
    df = base_valid_df.copy()
    df.at[0, "do_mgl"] = -2.5
    issues = validate_dataframe(df)
    assert any(i["rule"] == "physically_impossible_value" and i["column_name"] == "do_mgl" for i in issues)

    # Temperature > 50 C
    df = base_valid_df.copy()
    df.at[0, "temp_c"] = 65.0
    issues = validate_dataframe(df)
    assert any(i["rule"] == "physically_impossible_value" and i["column_name"] == "temp_c" for i in issues)


def test_duplicate_samples(base_valid_df):
    # Two identical rows with same station and date
    df = pd.concat([base_valid_df, base_valid_df], ignore_index=True)
    issues = validate_dataframe(df)
    assert any(i["rule"] == "duplicate_sample" for i in issues)


def test_unit_consistency(base_valid_df):
    # Conductivity in mS/cm instead of uS/cm (e.g. 0.45 < 50)
    df = base_valid_df.copy()
    df.at[0, "conductivity_uscm"] = 0.45
    issues = validate_dataframe(df)
    assert any(i["rule"] == "unit_consistency" and i["column_name"] == "conductivity_uscm" for i in issues)


def test_non_numeric_values(base_valid_df):
    df = base_valid_df.copy().astype(object)
    df.at[0, "bod_mgl"] = "Not Available"
    issues = validate_dataframe(df)
    assert any(i["rule"] == "non_numeric_value" and i["column_name"] == "bod_mgl" for i in issues)


def test_invalid_coordinates(base_valid_df):
    df = base_valid_df.copy()
    df.at[0, "lat"] = 65.0  # Outside India bounding box
    issues = validate_dataframe(df)
    assert any(i["rule"] == "invalid_coordinates" for i in issues)
