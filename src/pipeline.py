"""
End-to-End Execution Pipeline CLI for RiverWatch.
Executes data ingestion, validation, database commit, WQI calculation,
CPCB compliance, trends, PCA, driver ranking, and priority scoring.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src.analysis.compliance import compute_all_compliance
from src.analysis.correlation import compute_all_correlations
from src.analysis.drivers import compute_all_drivers
from src.analysis.pca import compute_all_pca
from src.analysis.priority import compute_priority_scores
from src.analysis.trend import compute_all_trends
from src.analysis.wqi import compute_all_wqi
from src.data.db import Upload, ValidationIssue, get_session_factory, init_db
from src.data.ingest import ingest_file
from src.data.preprocess import commit_upload_to_db
from src.data.synthetic import SAMPLE_DIR, save_sample_datasets
from src.data.validate import validate_dataframe


def run_pipeline(source: str = "synthetic", file_path: str | None = None, db_path: str | None = None):
    print("=" * 70)
    print("🌊 RiverWatch: River Health Intelligence Pipeline")
    print("=" * 70)

    # 1. Initialize database schema
    print("\n[1/8] Initializing SQLite database schema...")
    if db_path:
        init_db(db_path=db_path)
        session_factory = get_session_factory(db_path=db_path)
    else:
        init_db()
        session_factory = get_session_factory()

    # 2. Source resolution
    if source == "synthetic":
        print("\n[2/8] Generating synthetic dataset (8 stations, 8 years)...")
        clean_p, _, _ = save_sample_datasets()
        target_file = clean_p
        filename = "riverwatch_synthetic_clean.csv"
    else:
        if not file_path or not Path(file_path).exists():
            print(f"Error: Provided file '{file_path}' does not exist.")
            sys.exit(1)
        target_file = Path(file_path)
        filename = target_file.name

    print(f"\n[3/8] Ingesting and mapping headers from: {target_file}")
    with open(target_file, "rb") as f:
        file_bytes = f.read()

    df_mapped, meta = ingest_file(file_bytes, filename)
    print(f"   -> Rows: {meta['n_rows']}, Columns: {meta['n_columns']}")
    print(f"   -> Mandatory fields: station_id={meta['has_mandatory_station_id']}, sample_date={meta['has_mandatory_sample_date']}")

    # 3. Validation
    print("\n[4/8] Running multi-rule validation checks...")
    issues = validate_dataframe(df_mapped)
    errors = [i for i in issues if i["severity"] == "error"]
    warnings = [i for i in issues if i["severity"] == "warning"]
    print(f"   -> Validation complete: {len(errors)} errors, {len(warnings)} warnings found.")

    # 4. Commit to database
    print("\n[5/8] Preprocessing and committing records to database...")
    with session_factory() as session:
        up = Upload(
            filename=filename,
            status="committed" if len(errors) == 0 else "validated",
            n_rows=len(df_mapped),
            n_errors=len(errors),
            n_warnings=len(warnings),
        )
        session.add(up)
        session.flush()

        # Record validation issues
        for iss in issues:
            vi = ValidationIssue(
                upload_id=up.upload_id,
                row_number=iss.get("row_number"),
                column_name=iss.get("column_name"),
                value=str(iss.get("value", "")),
                severity=iss.get("severity", "warning"),
                rule=iss.get("rule", "general"),
                message=iss.get("message", ""),
                suggestion=iss.get("suggestion", ""),
                status="open",
            )
            session.add(vi)
        session.commit()

        commit_res = commit_upload_to_db(df_mapped, upload_id=up.upload_id, session=session)
        print(f"   -> Committed: {commit_res['samples_committed']} samples, {commit_res['measurements_committed']} measurements.")

    # 5. Core Analytical Engine
    print("\n[6/8] Executing analytical modules:")
    with session_factory() as session:
        # A. WQI
        n_wqi = compute_all_wqi(session)
        print(f"   -> Weighted-Arithmetic WQI calculated for {n_wqi} samples.")

        # B. CPCB Compliance
        n_comp = compute_all_compliance(session)
        print(f"   -> CPCB Designated Best Use compliance evaluated for {n_comp} samples.")

        # C. Trends
        n_trends = compute_all_trends(session)
        print(f"   -> Mann-Kendall & Sen's slope trend tests computed ({n_trends} series).")

        # D. Correlation
        n_corr = compute_all_correlations(session)
        print(f"   -> Spearman correlation matrix & FDR correction computed ({n_corr} pairs).")

        # E. PCA
        pca_out = compute_all_pca(session)
        evr = pca_out.get("variance_ratio", [])
        evr_str = ", ".join([f"{round(v * 100, 1)}%" for v in evr])
        print(f"   -> PCA completed (Explained variance: {evr_str}).")

        # F. Driver Ranking
        drivers = compute_all_drivers(session)
        top_driver = drivers[0]["param_code"] if drivers else "None"
        print(f"   -> Driver ranking completed. Top pollution driver: '{top_driver}'.")

        # G. Priority Scoring
        priority_res = compute_priority_scores(session)
        top_stn = priority_res[0]["station_name"] if priority_res else "None"
        print(f"   -> Station sampling priority calculated. Highest priority station: '{top_stn}'.")

    print("\n" + "=" * 70)
    print("✅ Pipeline run successfully completed! All tables populated.")
    print("=" * 70 + "\n")


def main():
    parser = argparse.ArgumentParser(description="RiverWatch Analytical Pipeline CLI")
    parser.add_argument(
        "--source",
        choices=["synthetic", "file"],
        default="synthetic",
        help="Data source: 'synthetic' or 'file'",
    )
    parser.add_argument(
        "--path",
        type=str,
        default=None,
        help="Path to CSV/Excel file when --source=file",
    )
    args = parser.parse_args()
    run_pipeline(source=args.source, file_path=args.path)


if __name__ == "__main__":
    main()
