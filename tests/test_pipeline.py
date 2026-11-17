"""
End-to-end tests for the complete pipeline, synthetic data generator,
and executive report generator.
"""
from pathlib import Path
import pytest
from src.data.db import get_session_factory, init_db
from src.data.ingest import ingest_file, load_aliases, map_columns
from src.data.synthetic import generate_synthetic_data, inject_synthetic_errors
from src.pipeline import run_pipeline
from src.report.generate import generate_executive_report


def test_synthetic_data_generation_and_errors():
    clean_df = generate_synthetic_data(years=8)
    assert len(clean_df) == 8 * 12 * 8  # 768 samples
    assert "station_id" in clean_df.columns
    assert "do_mgl" in clean_df.columns

    raw_df, injected = inject_synthetic_errors(clean_df)
    assert len(injected["impossible_ph"]) > 0
    assert len(injected["future_date"]) > 0
    assert len(injected["censored"]) > 0


def test_alias_mapping():
    aliases = load_aliases()
    assert "do_mgl" in aliases
    assert "bod_mgl" in aliases


def test_end_to_end_pipeline_and_report(tmp_path):
    test_db = tmp_path / "test_riverwatch.db"
    # Run the full pipeline on synthetic data targeting temporary test database
    run_pipeline(source="synthetic", db_path=str(test_db))

    # Verify tables and report generation
    session_factory = get_session_factory(str(test_db))
    with session_factory() as session:
        res = generate_executive_report(session, file_name_prefix="test_report")
        assert res["report_id"] is not None
        assert Path(res["html_path"]).exists()
        assert Path(res["pdf_path"]).exists()
