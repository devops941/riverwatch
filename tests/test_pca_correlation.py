"""
Unit tests for correlation matrix, Benjamini-Hochberg FDR, and PCA (Section 6.5 & 6.6).
"""
import numpy as np
import pandas as pd
import pytest
from src.analysis.correlation import benjamini_hochberg_adjust, compute_spearman_matrix
from src.analysis.pca import run_pca_analysis


def test_benjamini_hochberg_fdr():
    raw_p = [0.001, 0.015, 0.045, 0.20, 0.85]
    adj_p = benjamini_hochberg_adjust(raw_p)

    assert len(adj_p) == len(raw_p)
    # Check monotonicity / adjusted >= raw
    for raw, adj in zip(raw_p, adj_p):
        assert adj >= raw
        assert adj <= 1.0


def test_spearman_correlation_matrix():
    np.random.seed(42)
    x = np.linspace(1, 20, 20)
    # y perfectly correlated with x, z uncorrelated
    y = 2.5 * x + 3.0
    z = np.random.normal(0, 1, 20)

    df = pd.DataFrame({"param_x": x, "param_y": y, "param_z": z})
    pairs = compute_spearman_matrix(df)

    xy_pair = next(p for p in pairs if (p["param_a"] == "param_x" and p["param_b"] == "param_y"))
    assert pytest.approx(xy_pair["spearman_rho"], 0.01) == 1.0
    assert xy_pair["p_value"] < 0.001


def test_pca_variance_and_loadings():
    np.random.seed(42)
    # Generate 50 samples where x, y, z share a single dominant latent factor
    latent = np.random.normal(0, 5, 50)
    x = latent + np.random.normal(0, 0.2, 50)
    y = 2 * latent + np.random.normal(0, 0.2, 50)
    z = -1.5 * latent + np.random.normal(0, 0.2, 50)

    df = pd.DataFrame({
        "sample_id": list(range(1, 51)),
        "param_x": x,
        "param_y": y,
        "param_z": z,
    })

    pca_out = run_pca_analysis(df, n_components=2)
    assert len(pca_out["variance_ratio"]) >= 1
    # First component should capture > 85% of variance
    assert pca_out["variance_ratio"][0] > 0.85
    assert len(pca_out["scores"]) == 50
