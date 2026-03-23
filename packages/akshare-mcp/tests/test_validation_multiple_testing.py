import numpy as np

from akshare_mcp.services.validation import (
    FactorValidationPipeline,
    deflated_sharpe_ratio,
    hansen_spa_test,
    probability_of_backtest_overfitting,
    white_reality_check,
)


def test_deflated_sharpe_ratio_becomes_more_conservative_with_more_trials():
    rng = np.random.default_rng(7)
    returns = rng.normal(0.0006, 0.01, size=252)

    low_trials = deflated_sharpe_ratio(returns, n_trials=5, periods_per_year=252.0)
    high_trials = deflated_sharpe_ratio(returns, n_trials=50, periods_per_year=252.0)

    assert low_trials["available"] is True
    assert high_trials["available"] is True
    assert high_trials["reference_sharpe"] > low_trials["reference_sharpe"]
    assert high_trials["dsr"] < low_trials["dsr"]


def test_probability_of_backtest_overfitting_detects_specialist_family():
    rng = np.random.default_rng(11)
    stable_family = rng.normal(0.0008, 0.01, size=(160, 8))

    overfit_family = rng.normal(-0.0005, 0.004, size=(160, 8))
    block_size = 20
    for model_idx in range(8):
        start = model_idx * block_size
        end = start + block_size
        overfit_family[start:end, model_idx] += 0.045

    stable = probability_of_backtest_overfitting(stable_family, n_splits=8, seed=19)
    overfit = probability_of_backtest_overfitting(overfit_family, n_splits=8, seed=19)

    assert stable["available"] is True
    assert overfit["available"] is True
    assert overfit["pbo"] > stable["pbo"]


def test_white_reality_check_and_hansen_spa_discriminate_null_vs_signal():
    rng = np.random.default_rng(23)
    null_family = rng.normal(0.0, 0.01, size=(240, 6))
    signal_family = rng.normal(0.0, 0.01, size=(240, 6))
    signal_family[:, 0] += 0.004

    null_rc = white_reality_check(null_family, n_bootstrap=300, seed=23)
    signal_rc = white_reality_check(signal_family, n_bootstrap=300, seed=23)
    null_spa = hansen_spa_test(null_family, n_bootstrap=300, seed=23, center="consistent")
    signal_spa = hansen_spa_test(signal_family, n_bootstrap=300, seed=23, center="consistent")

    assert null_rc["available"] is True
    assert signal_rc["available"] is True
    assert null_spa["available"] is True
    assert signal_spa["available"] is True
    assert signal_rc["p_value"] < null_rc["p_value"]
    assert signal_spa["p_value"] < null_spa["p_value"]
    assert signal_spa["p_value"] < 0.2


def test_factor_validation_pipeline_emits_multiple_testing_report():
    rng = np.random.default_rng(31)
    factor_panel = rng.normal(0.0, 1.0, size=(90, 6))
    return_panel = 0.02 * factor_panel + rng.normal(0.0, 0.05, size=(90, 6))
    family_returns = rng.normal(0.0, 0.01, size=(90, 4))
    family_returns[:, 0] += 0.003

    pipeline = FactorValidationPipeline(validation_parallel=False, bootstrap_n=200)
    report = pipeline.run(
        factor_panel,
        return_panel,
        validation_parallel=False,
        family_returns=family_returns,
        multiple_testing_config={
            "n_bootstrap": 200,
            "pbo_n_splits": 4,
            "seed": 31,
        },
    )

    assert report["multiple_testing"]["available"] is True
    assert "deflated_sharpe" in report["multiple_testing"]
    assert "pbo" in report["multiple_testing"]
    assert "white_reality_check" in report["multiple_testing"]
    assert "hansen_spa" in report["multiple_testing"]
