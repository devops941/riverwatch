"""
Database models and connection management for RiverWatch using SQLAlchemy 2.0.
"""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Generator, Optional

from sqlalchemy import (
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Session, relationship, sessionmaker
import yaml

DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "riverwatch.db"
CONFIG_DIR = Path(__file__).resolve().parent.parent.parent / "config"


class Base(DeclarativeBase):
    pass


class River(Base):
    __tablename__ = "rivers"

    river_id = Column(Integer, primary_key=True, autoincrement=True)
    river_name = Column(String(100), unique=True, nullable=False)

    stations = relationship("Station", back_populates="river")


class Station(Base):
    __tablename__ = "stations"

    station_id = Column(String(50), primary_key=True)
    station_name = Column(String(150), nullable=True)
    river_id = Column(Integer, ForeignKey("rivers.river_id"), nullable=True)
    lat = Column(Float, nullable=True)
    lon = Column(Float, nullable=True)
    river_order = Column(Integer, nullable=True)  # 1 (upstream) to n (downstream)

    river = relationship("River", back_populates="stations")
    samples = relationship("Sample", back_populates="station")


class Parameter(Base):
    __tablename__ = "parameters"

    param_code = Column(String(50), primary_key=True)
    display_name = Column(String(100), nullable=True)
    unit = Column(String(50), nullable=True)
    standard_value = Column(Float, nullable=True)
    ideal_value = Column(Float, nullable=True)
    worse_if = Column(String(20), nullable=True)  # 'increasing' | 'decreasing' | 'both'
    valid_min = Column(Float, nullable=True)
    valid_max = Column(Float, nullable=True)


class Upload(Base):
    __tablename__ = "uploads"

    upload_id = Column(Integer, primary_key=True, autoincrement=True)
    filename = Column(String(255), nullable=False)
    uploaded_at = Column(DateTime, default=datetime.utcnow)
    status = Column(String(50), default="validated")  # 'validated', 'committed', 'rejected'
    n_rows = Column(Integer, default=0)
    n_errors = Column(Integer, default=0)
    n_warnings = Column(Integer, default=0)

    samples = relationship("Sample", back_populates="upload")
    issues = relationship("ValidationIssue", back_populates="upload")


class Sample(Base):
    __tablename__ = "samples"

    sample_id = Column(Integer, primary_key=True, autoincrement=True)
    upload_id = Column(Integer, ForeignKey("uploads.upload_id"), nullable=True)
    station_id = Column(String(50), ForeignKey("stations.station_id"), nullable=False)
    sample_date = Column(Date, nullable=False)
    is_excluded = Column(Integer, default=0)

    __table_args__ = (
        UniqueConstraint("station_id", "sample_date", name="uq_station_sample_date"),
        Index("idx_samples_stn_date", "station_id", "sample_date"),
    )

    upload = relationship("Upload", back_populates="samples")
    station = relationship("Station", back_populates="samples")
    measurements = relationship("Measurement", back_populates="sample", cascade="all, delete-orphan")
    wqi_result = relationship("WQIResult", back_populates="sample", uselist=False, cascade="all, delete-orphan")
    pca_scores = relationship("PCAScore", back_populates="sample", uselist=False, cascade="all, delete-orphan")


class Measurement(Base):
    __tablename__ = "measurements"

    sample_id = Column(Integer, ForeignKey("samples.sample_id"), primary_key=True)
    param_code = Column(String(50), ForeignKey("parameters.param_code"), primary_key=True)
    value = Column(Float, nullable=True)
    raw_value = Column(String(100), nullable=True)
    is_censored = Column(Integer, default=0)
    is_imputed = Column(Integer, default=0)
    is_outlier = Column(Integer, default=0)

    __table_args__ = (
        Index("idx_measurements_param", "param_code"),
    )

    sample = relationship("Sample", back_populates="measurements")
    parameter = relationship("Parameter")


class ValidationIssue(Base):
    __tablename__ = "validation_issues"

    issue_id = Column(Integer, primary_key=True, autoincrement=True)
    upload_id = Column(Integer, ForeignKey("uploads.upload_id"), nullable=False)
    row_number = Column(Integer, nullable=True)
    column_name = Column(String(100), nullable=True)
    value = Column(Text, nullable=True)
    severity = Column(String(20), nullable=False)  # 'error' | 'warning'
    rule = Column(String(100), nullable=False)
    message = Column(Text, nullable=False)
    suggestion = Column(Text, nullable=True)
    status = Column(String(20), default="open")  # 'open' | 'fixed' | 'ignored' | 'excluded'

    __table_args__ = (
        Index("idx_val_upload_status", "upload_id", "status"),
    )

    upload = relationship("Upload", back_populates="issues")


class CorrectionAudit(Base):
    __tablename__ = "corrections_audit"

    audit_id = Column(Integer, primary_key=True, autoincrement=True)
    sample_id = Column(Integer, nullable=True)
    param_code = Column(String(50), nullable=True)
    old_value = Column(Float, nullable=True)
    new_value = Column(Float, nullable=True)
    reason = Column(Text, nullable=True)
    changed_at = Column(DateTime, default=datetime.utcnow)


class WQIResult(Base):
    __tablename__ = "wqi_results"

    sample_id = Column(Integer, ForeignKey("samples.sample_id"), primary_key=True)
    wqi = Column(Float, nullable=True)
    wqi_class = Column(String(50), nullable=True)
    wqi_equal_weights = Column(Float, nullable=True)
    cpcb_class = Column(String(20), nullable=True)
    violating_params = Column(Text, nullable=True)
    n_params_used = Column(Integer, default=0)

    sample = relationship("Sample", back_populates="wqi_result")


class TrendResult(Base):
    __tablename__ = "trend_results"

    station_id = Column(String(50), ForeignKey("stations.station_id"), primary_key=True)
    param_code = Column(String(50), primary_key=True)
    test_used = Column(String(50), nullable=True)
    trend = Column(String(50), nullable=True)  # 'increasing' | 'decreasing' | 'no trend'
    interpretation = Column(String(50), nullable=True)  # 'worsening' | 'improving' | 'no trend'
    p_value = Column(Float, nullable=True)
    tau = Column(Float, nullable=True)
    sen_slope_per_year = Column(Float, nullable=True)
    ci_low = Column(Float, nullable=True)
    ci_high = Column(Float, nullable=True)
    pct_change_per_year = Column(Float, nullable=True)


class CorrelationResult(Base):
    __tablename__ = "correlation_results"

    param_a = Column(String(50), primary_key=True)
    param_b = Column(String(50), primary_key=True)
    spearman_rho = Column(Float, nullable=True)
    p_value = Column(Float, nullable=True)
    p_adjusted = Column(Float, nullable=True)
    n = Column(Integer, default=0)


class PCAResult(Base):
    __tablename__ = "pca_results"

    component = Column(String(20), primary_key=True)  # 'PC1', 'PC2', ...
    param_code = Column(String(50), primary_key=True)
    loading = Column(Float, nullable=True)
    explained_variance_ratio = Column(Float, nullable=True)


class PCAScore(Base):
    __tablename__ = "pca_scores"

    sample_id = Column(Integer, ForeignKey("samples.sample_id"), primary_key=True)
    pc1 = Column(Float, nullable=True)
    pc2 = Column(Float, nullable=True)
    pc3 = Column(Float, nullable=True)

    sample = relationship("Sample", back_populates="pca_scores")


class DriverRanking(Base):
    __tablename__ = "driver_ranking"

    param_code = Column(String(50), primary_key=True)
    pca_score = Column(Float, nullable=True)
    corr_score = Column(Float, nullable=True)
    change_contribution = Column(Float, nullable=True)
    combined_score = Column(Float, nullable=True)
    rank = Column(Integer, nullable=True)
    explanation = Column(Text, nullable=True)


class StationPriority(Base):
    __tablename__ = "station_priority"

    station_id = Column(String(50), ForeignKey("stations.station_id"), primary_key=True)
    mean_wqi_12m = Column(Float, nullable=True)
    wqi_slope = Column(Float, nullable=True)
    violation_rate = Column(Float, nullable=True)
    days_since_last_sample = Column(Integer, nullable=True)
    gap_score = Column(Float, nullable=True)
    priority_score = Column(Float, nullable=True)
    priority_rank = Column(Integer, nullable=True)
    reason = Column(Text, nullable=True)


class Report(Base):
    __tablename__ = "reports"

    report_id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    file_path = Column(String(255), nullable=False)
    scope_json = Column(Text, nullable=True)


_engine = None
_SessionLocal = None


def get_engine(db_path: Path | str = DB_PATH):
    global _engine
    if _engine is None:
        db_file = Path(db_path)
        db_file.parent.mkdir(parents=True, exist_ok=True)
        _engine = create_engine(
            f"sqlite:///{db_file}",
            connect_args={"check_same_thread": False},
            echo=False,
        )
    return _engine


def get_session_factory(db_path: Path | str = DB_PATH):
    global _SessionLocal
    if _SessionLocal is None:
        engine = get_engine(db_path)
        _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return _SessionLocal


def get_db(db_path: Path | str = DB_PATH) -> Generator[Session, None, None]:
    factory = get_session_factory(db_path)
    db = factory()
    try:
        yield db
    finally:
        db.close()


def init_db(db_path: Path | str = DB_PATH, seed_parameters: bool = True):
    engine = get_engine(db_path)
    Base.metadata.create_all(bind=engine)

    if seed_parameters:
        factory = get_session_factory(db_path)
        with factory() as session:
            count = session.query(Parameter).count()
            if count == 0:
                param_yaml = CONFIG_DIR / "parameters.yaml"
                if param_yaml.exists():
                    with open(param_yaml, "r", encoding="utf-8") as f:
                        data = yaml.safe_load(f)
                    params = data.get("parameters", {})
                    for code, info in params.items():
                        p = Parameter(
                            param_code=code,
                            display_name=info.get("display_name"),
                            unit=info.get("unit"),
                            standard_value=info.get("standard_value"),
                            ideal_value=info.get("ideal_value"),
                            worse_if=info.get("worse_if"),
                            valid_min=info.get("valid_min"),
                            valid_max=info.get("valid_max"),
                        )
                        session.add(p)
                    session.commit()
