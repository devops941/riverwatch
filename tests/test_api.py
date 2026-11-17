"""
Integration and REST API tests for RiverWatch backend routes.
Verifies all route logic, response schemas, and database transactions.
"""
import pytest
from backend.main import health_check
from backend.routers.analysis import (
    get_compliance_summary,
    get_driver_rankings,
    get_station_priority,
    get_trends,
    get_wqi_data,
)
from backend.routers.export import (
    correct_measurement,
    export_cleaned_csv,
    export_results_excel,
    get_audit_trail,
    get_sample_records,
    preview_sample_analytics,
    submit_data_entry,
)
from backend.routers.stations import get_all_stations, get_station_time_series
from backend.routers.uploads import download_template
from backend.schemas import DataEntryRequest, DataPreviewRequest, RecordPatchRequest
from src.data.db import get_session_factory, init_db


@pytest.fixture(scope="module")
def db_session():
    init_db()
    factory = get_session_factory()
    session = factory()
    yield session
    session.close()


def test_health_check(db_session):
    res = health_check(session=db_session)
    assert res["status"] == "healthy"
    assert res["service"] == "RiverWatch Backend"
    assert res["samples_in_db"] > 0


def test_download_template():
    res = download_template()
    assert res.status_code == 200
    assert "text/csv" in res.media_type


def test_stations_endpoint(db_session):
    stations = get_all_stations(session=db_session)
    assert isinstance(stations, list)
    assert len(stations) >= 8
    first = stations[0]
    assert first.station_id == "STN-01"
    assert first.river_name == "Ganga"
    assert first.latest_wqi is not None


def test_station_series_endpoint(db_session):
    series = get_station_time_series("STN-01", param="wqi", session=db_session)
    assert series.station_id == "STN-01"
    assert len(series.points) > 0


def test_wqi_endpoint(db_session):
    wqi_list = get_wqi_data(limit=10, session=db_session)
    assert len(wqi_list) == 10
    first = wqi_list[0]
    assert first.wqi is not None
    assert first.wqi_class is not None


def test_compliance_summary_endpoint(db_session):
    comp_list = get_compliance_summary(session=db_session)
    assert len(comp_list) >= 8
    first = comp_list[0]
    assert first.pct_class_a >= 0.0


def test_trends_endpoint(db_session):
    trends = get_trends(session=db_session)
    assert len(trends) > 0
    first = trends[0]
    assert first.test_used in ["original_test", "hamed_rao"]


def test_drivers_endpoint(db_session):
    drivers = get_driver_rankings(session=db_session)
    assert len(drivers) > 0
    first = drivers[0]
    assert first.rank == 1
    assert first.combined_score > 0.0


def test_priority_endpoint(db_session):
    priorities = get_station_priority(session=db_session)
    assert len(priorities) >= 8
    first = priorities[0]
    assert first.priority_rank == 1
    assert first.priority_score is not None


def test_export_data_csv(db_session):
    res = export_cleaned_csv(session=db_session)
    assert res.status_code == 200
    assert "text/csv" in res.media_type


def test_export_results_excel(db_session):
    res = export_results_excel(session=db_session)
    assert res.status_code == 200
    assert "openxmlformats" in res.media_type


def test_records_pagination_and_audit(db_session):
    # 1. Fetch sample records
    res = get_sample_records(page=1, page_size=5, session=db_session)
    assert res["page"] == 1
    assert len(res["records"]) == 5
    sample_id = res["records"][0].sample_id

    # 2. Patch a measurement value with audit justification
    payload = RecordPatchRequest(new_value=7.42, reason="Routine sensor calibration audit")
    patch_res = correct_measurement(sample_id, "ph", payload, session=db_session)
    assert patch_res["status"] == "success"
    assert patch_res["new_value"] == 7.42

    # 3. Verify entry in audit log
    audits = get_audit_trail(session=db_session)
    assert len(audits) > 0
    matched = next((a for a in audits if a.sample_id == sample_id and a.param_code == "ph"), None)
    assert matched is not None
    assert matched.new_value == 7.42
    assert matched.reason == "Routine sensor calibration audit"


def test_data_entry_and_preview(db_session):
    # 1. Test live preview without saving
    preview_req = DataPreviewRequest(
        measurements={
            "do_mgl": 7.5,
            "ph": 7.3,
            "bod_mgl": 1.8,
            "cod_mgl": 10.0,
            "total_coliform_mpn": 45.0,
        }
    )
    prev_res = preview_sample_analytics(preview_req)
    assert prev_res.wqi is not None
    assert prev_res.wqi > 0
    assert prev_res.n_params_used == 5
    assert prev_res.cpcb_class in ["Class A", "Class B"]

    # 2. Test direct data entry and recomputation
    entry_req = DataEntryRequest(
        station_id="STN-01",
        sample_date="2026-11-17",
        measurements={
            "do_mgl": 7.5,
            "ph": 7.3,
            "bod_mgl": 1.8,
            "cod_mgl": 10.0,
            "total_coliform_mpn": 45.0,
        },
        notes="Field lab test sample",
    )
    entry_res = submit_data_entry(entry_req, session=db_session)
    assert entry_res.status == "success"
    assert entry_res.sample_id > 0
    assert entry_res.wqi is not None
    assert entry_res.station_id == "STN-01"

