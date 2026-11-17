"""
Unit tests for station sampling priority scoring (Section 6.8).
"""
import pytest
from src.analysis.priority import min_max_norm


def test_min_max_norm():
    assert min_max_norm(50.0, 0.0, 100.0) == 0.5
    assert min_max_norm(0.0, 0.0, 100.0) == 0.0
    assert min_max_norm(100.0, 0.0, 100.0) == 1.0
    # Clamping
    assert min_max_norm(150.0, 0.0, 100.0) == 1.0
    assert min_max_norm(-10.0, 0.0, 100.0) == 0.0
    # Division by zero safeguard
    assert min_max_norm(5.0, 5.0, 5.0) == 0.5
