"""
Data ingestion and column alias mapping for RiverWatch.
Handles CSV and Excel uploads, standardizes headers against config/aliases.yaml,
and produces standardized DataFrames for validation and preprocessing.
"""
from __future__ import annotations

import io
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import pandas as pd
import yaml

CONFIG_DIR = Path(__file__).resolve().parent.parent.parent / "config"


def load_aliases(config_path: Optional[Path] = None) -> Dict[str, List[str]]:
    path = config_path or (CONFIG_DIR / "aliases.yaml")
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("aliases", {})


def normalize_header(header: str) -> str:
    """Normalize a header string for matching: lowercase, strip, condense spaces."""
    h = str(header).strip().lower()
    h = h.replace("\n", " ").replace("\r", " ")
    h = " ".join(h.split())
    return h


def build_alias_lookup(aliases: Dict[str, List[str]]) -> Dict[str, str]:
    """
    Invert aliases dictionary so: normalized_variant -> canonical_name
    """
    lookup: Dict[str, str] = {}
    for canonical, variants in aliases.items():
        lookup[normalize_header(canonical)] = canonical
        for var in variants:
            lookup[normalize_header(var)] = canonical
    return lookup


def map_columns(
    df: pd.DataFrame, alias_lookup: Optional[Dict[str, str]] = None
) -> Tuple[pd.DataFrame, Dict[str, Optional[str]], List[str]]:
    """
    Map DataFrame column names to canonical names using the alias lookup.
    Returns:
      (mapped_df, mapping_dict {original: canonical}, unmapped_columns)
    """
    if alias_lookup is None:
        aliases = load_aliases()
        alias_lookup = build_alias_lookup(aliases)

    mapping: Dict[str, Optional[str]] = {}
    unmapped: List[str] = []
    rename_dict: Dict[str, str] = {}

    for col in df.columns:
        norm = normalize_header(col)
        canonical = alias_lookup.get(norm)
        if canonical:
            mapping[col] = canonical
            rename_dict[col] = canonical
        else:
            # Check for close matches like removing punctuation or brackets
            cleaned = norm.replace("(", "").replace(")", "").replace("/", "").replace("_", " ")
            cleaned = " ".join(cleaned.split())
            canonical_clean = alias_lookup.get(cleaned)
            if canonical_clean:
                mapping[col] = canonical_clean
                rename_dict[col] = canonical_clean
            else:
                mapping[col] = None
                unmapped.append(col)

    mapped_df = df.rename(columns=rename_dict)
    return mapped_df, mapping, unmapped


def read_uploaded_file(file_content: Union[bytes, str, Path], filename: str) -> pd.DataFrame:
    """
    Read CSV or Excel uploaded file content into a pandas DataFrame.
    """
    fname = filename.lower()
    if isinstance(file_content, (str, Path)):
        file_path = Path(file_content)
        if fname.endswith(".csv") or file_path.suffix == ".csv":
            return pd.read_csv(file_path, dtype=object)
        elif fname.endswith((".xlsx", ".xls")) or file_path.suffix in [".xlsx", ".xls"]:
            return pd.read_excel(file_path, dtype=object)
        else:
            raise ValueError(f"Unsupported file format for {filename}. Please upload .csv or .xlsx")
    else:
        # Bytes / buffer
        buffer = io.BytesIO(file_content)
        if fname.endswith(".csv"):
            return pd.read_csv(buffer, dtype=object)
        elif fname.endswith((".xlsx", ".xls")):
            return pd.read_excel(buffer, dtype=object)
        else:
            raise ValueError(f"Unsupported file format for {filename}. Please upload .csv or .xlsx")


def ingest_file(
    file_content: Union[bytes, str, Path], filename: str
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Read file, normalize headers, and return (DataFrame, metadata)
    """
    raw_df = read_uploaded_file(file_content, filename)
    mapped_df, mapping, unmapped = map_columns(raw_df)

    metadata = {
        "filename": filename,
        "n_rows": len(raw_df),
        "n_columns": len(raw_df.columns),
        "mapping": mapping,
        "unmapped_columns": unmapped,
        "has_mandatory_station_id": "station_id" in mapped_df.columns,
        "has_mandatory_sample_date": "sample_date" in mapped_df.columns,
    }

    return mapped_df, metadata
