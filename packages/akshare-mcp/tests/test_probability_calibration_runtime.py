from __future__ import annotations

from akshare_mcp.services.probability_calibration import (
    build_calibration_quality_report,
    calibrate_probability_series,
)


def test_calibrate_probability_series_exposes_backend_and_fallback_state():
    probabilities = [0.12, 0.18, 0.22, 0.31, 0.44, 0.51, 0.63, 0.71, 0.83, 0.91]
    labels = [0, 0, 0, 0, 0, 1, 1, 1, 1, 1]

    result = calibrate_probability_series(
        probabilities,
        labels,
        method="sigmoid",
    )

    assert len(result.probabilities) == len(probabilities)
    assert result.backend_requested == "sklearn_calibrated_classifier_cv"
    assert result.method == "sigmoid"
    if result.backend_used == "sklearn_calibrated_classifier_cv":
        assert result.fallback_used is False
        assert result.cv_folds is not None
    else:
        assert result.backend_used == "builtin_lightweight"
        assert result.fallback_used is True
        assert result.fallback_reason

    report = build_calibration_quality_report(
        result.probabilities,
        labels,
        calibration_method=result.method,
        calibration_version="test_v1",
        calibration_backend=result.backend_used,
        backend_requested=result.backend_requested,
        backend_used=result.backend_used,
        fallback_used=result.fallback_used,
        fallback_reason=result.fallback_reason,
        cv_folds=result.cv_folds,
    ).to_dict()

    assert report["backend_requested"] == "sklearn_calibrated_classifier_cv"
    assert report["backend_used"] in {"sklearn_calibrated_classifier_cv", "builtin_lightweight"}
    assert isinstance(report["fallback_used"], bool)
