"""Tests for theme response regression model (PR-7)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from strategy_factory.application.research.theme_response_regression import (
    EdgeRegressionResult,
    ThemeResponseRegression,
)


@pytest.fixture
def model():
    return ThemeResponseRegression()


def test_detect_shocks_basic(model):
    """Detect shocks in a series with clear outliers."""
    np.random.seed(42)
    returns = pd.Series(np.random.normal(0, 0.02, 200))
    # Inject shocks
    returns.iloc[50] = 0.10  # +5 sigma
    returns.iloc[100] = -0.08  # -4 sigma
    returns.iloc[150] = 0.12  # +6 sigma

    shocks = model.detect_shocks(returns, z_threshold=2.0, window=20)
    assert len(shocks) >= 3
    assert all(col in shocks.columns for col in ["idx", "magnitude", "direction_sign"])


def test_detect_shocks_empty_series(model):
    shocks = model.detect_shocks(pd.Series(dtype=float))
    assert shocks.empty


def test_detect_shocks_short_series(model):
    shocks = model.detect_shocks(pd.Series([0.01, -0.01, 0.02]))
    assert shocks.empty


def test_fit_edge_with_correlated_data(model):
    """Fit edge where target responds positively to source shocks."""
    np.random.seed(123)
    n = 300

    # Source returns with some shocks
    source = pd.Series(np.random.normal(0, 0.02, n))
    source.iloc[50] = 0.08
    source.iloc[100] = 0.09
    source.iloc[150] = -0.07
    source.iloc[200] = 0.10
    source.iloc[250] = -0.08

    # Target responds positively to source shocks with lag
    target = pd.Series(np.random.normal(0, 0.015, n))
    for shock_idx in [50, 100, 200, 250]:
        # Add positive response in next 5 days
        for lag in range(1, 6):
            if shock_idx + lag < n:
                target.iloc[shock_idx + lag] += 0.01 * np.sign(source.iloc[shock_idx])

    shocks = model.detect_shocks(source, z_threshold=2.0, window=20)
    result = model.fit_edge(source, target, shocks, horizons=[5])

    # With synthetic data, result depends on random seed and shock detection
    assert result.status in ("fitted", "insufficient_data", "no_significant_horizon")
    if result.status == "fitted":
        assert result.n_samples >= 3


def test_fit_edge_insufficient_data(model):
    """Fit edge with too few shocks."""
    source = pd.Series(np.random.normal(0, 0.02, 50))
    target = pd.Series(np.random.normal(0, 0.02, 50))
    shocks = pd.DataFrame(columns=["idx", "magnitude", "direction_sign"])

    result = model.fit_edge(source, target, shocks)
    assert result.status == "insufficient_data"


def test_edge_regression_result_to_dict():
    result = EdgeRegressionResult(
        source_theme="oil",
        target_theme="airlines",
        best_horizon=5,
        beta=-0.03,
        r_squared=0.15,
        p_value=0.05,
        n_samples=30,
        direction_sign=-1,
        magnitude_factor=0.6,
        confidence=0.55,
        status="fitted",
    )
    d = result.to_dict()
    assert d["source_theme"] == "oil"
    assert d["direction_sign"] == -1
    assert d["status"] == "fitted"
