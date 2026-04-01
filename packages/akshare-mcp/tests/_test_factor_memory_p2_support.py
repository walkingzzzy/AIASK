from datetime import date, timedelta
from types import SimpleNamespace

import pytest


class _DummyMCP:
    def tool(self):
        def _decorator(fn):
            setattr(self, fn.__name__, fn)
            return fn

        return _decorator


class _DisabledEmbeddingService:
    config = SimpleNamespace(provider="disabled", model="")

    def is_enabled(self):
        return False

    async def embed_text(self, text):
        raise RuntimeError("embedding disabled")


class _PromptDB:
    async def get_klines(self, code, limit=180):
        return [
            {"date": "2026-03-17", "open": 10.0, "high": 10.5, "low": 9.9, "close": 10.2, "volume": 1000, "amount": 2000.0},
            {"date": "2026-03-18", "open": 10.2, "high": 10.6, "low": 10.0, "close": 10.4, "volume": 1100, "amount": 2100.0},
            {"date": "2026-03-19", "open": 10.4, "high": 10.8, "low": 10.3, "close": 10.7, "volume": 1400, "amount": 2600.0},
            {"date": "2026-03-20", "open": 10.7, "high": 11.0, "low": 10.6, "close": 10.9, "volume": 1500, "amount": 2800.0},
            {"date": "2026-03-21", "open": 10.9, "high": 11.2, "low": 10.8, "close": 11.1, "volume": 1700, "amount": 3000.0},
        ] * 30

    async def get_financials(self, code, limit=4):
        return [
            {
                "roe": 18.2,
                "roa": 9.1,
                "gross_margin": 42.0,
                "debt_ratio": 0.31,
                "revenue_growth": 12.5,
                "profit_growth": 15.6,
            }
        ]


class _ValidationDB:
    async def get_klines(self, code, limit=220):
        rows = []
        close = 10.0
        start = date(2025, 1, 1)
        for idx in range(max(240, int(limit))):
            close *= 1.002 + (int(str(code)[-1]) * 0.0001)
            volume = 100000 + idx * 1000
            rows.append(
                {
                    "date": str(start + timedelta(days=idx)),
                    "open": round(close * 0.998, 6),
                    "high": round(close * 1.01, 6),
                    "low": round(close * 0.99, 6),
                    "close": round(close, 6),
                    "volume": volume,
                    "amount": round(close * volume, 2),
                }
            )
        return rows[-int(limit):]


class _FeedbackDB(_ValidationDB):
    async def get_strategy(self, strategy_id):
        if strategy_id != "sid_feedback_case":
            return None
        return {
            "id": "sid_feedback_case",
            "name": "FeedbackStrategy",
            "status": "incubating",
            "params": {
                "candidate_provenance": {
                    "source_candidate_artifact_id": "factor_validation_registry_feedback_champion",
                    "candidate_family": "momentum",
                    "candidate_name": "feedback_champion",
                    "expected_regime": ["trend"],
                }
            },
        }

    async def list_strategy_incubation_metrics(self, strategy_id, limit=1, start_date=None, end_date=None):
        del limit, start_date, end_date
        if strategy_id != "sid_feedback_case":
            return []
        return [
            {
                "metric_date": "2026-03-22",
                "nav": 0.94,
                "daily_return": -0.031,
                "sharpe_ratio": -0.42,
                "alpha_decay": 0.21,
                "drift_score": 0.67,
                "turnover_rate": 0.72,
                "exposure_rate": 0.86,
                "hit_rate_5d": 0.41,
                "forward_ic_5d": -0.06,
                "forward_sharpe_5d": -0.19,
                "total_signals": 14,
                "risk_flags": ["regime_shift_warning", "crowding_watch"],
                "blockers": ["review_required"],
                "decision": "review",
            }
        ]

    async def get_signal_stats(self, strategy_id):
        if strategy_id != "sid_feedback_case":
            return {"hit_rate": {}, "forward_ic": {}, "forward_sharpe": {}, "total_signals": 0}
        return {
            "hit_rate": {5: 0.41},
            "forward_ic": {5: -0.06},
            "forward_sharpe": {5: -0.19},
            "total_signals": 14,
        }

    async def list_strategy_runtime_risk_events(self, strategy_id=None, account_id=None, status=None, severity=None, limit=20):
        del account_id, status, severity, limit
        if strategy_id != "sid_feedback_case":
            return []
        return [
            {"id": 1, "severity": "critical", "event_type": "drawdown_breach", "status": "open"},
        ]

    async def list_strategy_runtime_alerts(self, strategy_id=None, category=None, severity=None, status=None, limit=20):
        del category, severity, status, limit
        if strategy_id != "sid_feedback_case":
            return []
        return [
            {"alert_id": 11, "severity": "warning", "status": "open", "category": "risk"},
        ]

    async def get_latest_strategy_incubation_pipeline_snapshot(self, strategy_id):
        if strategy_id != "sid_feedback_case":
            return None
        return {
            "pipeline_status": "review",
            "next_action": "review",
            "risk_flags": ["drift_alert"],
            "blockers": ["manual_review_required"],
        }


def _build_candidate(expression="momentum_20d", name="trend_factor_v2"):
    return {
        "name": name,
        "hypothesis": "更强的中期动量对应更高的未来收益。",
        "family": "momentum",
        "inputs": ["close"],
        "expression_dsl": expression,
        "expected_holding_period": 10,
        "expected_regime": ["trend"],
        "complexity_hint": "low",
        "novelty_rationale": "P2 memory integration test candidate.",
    }


def _register_validation_artifact(
    artifact_id: str,
    codes: list[str],
    *,
    name: str,
    recommendation: str,
    total_score: float,
    lookahead_risk: str = "low",
    multiple_testing_risk: str = "low",
    source_generation_artifact_id: str | None = None,
    wf_stability: float = 0.72,
    kf_stability: float = 0.68,
    wf_degradation: float = 0.03,
    kf_degradation: float = 0.04,
    lookback_bars: int = 180,
    horizon_days: int = 5,
    max_dates: int = 40,
):
    from akshare_mcp.services import register_artifact

    register_artifact(
        {
            "artifact_id": artifact_id,
            "strategy": "quant_factor_candidate_validation",
            "strategy_version": "p2.v1",
            "code": ",".join(codes),
            "payload": {
                "artifact_id": artifact_id,
                "action": "validate_factor_candidate",
                "codes": list(codes),
                "candidate": _build_candidate("momentum_20d", name=name),
                "metrics": {"rank_ic_mean": 0.11, "rank_ic_ir": 0.72, "sample_dates": 36},
                "candidate_resolution": {
                    "artifact_id": source_generation_artifact_id,
                },
                "factor_validation_report": {
                    "oos": {
                        "available": True,
                        "walk_forward": {
                            "stability_ratio": wf_stability,
                            "degradation": wf_degradation,
                            "oos_rank_ic_mean": 0.08,
                            "oos_rank_ic_ir": 0.61,
                        },
                        "purged_kfold": {
                            "stability_ratio": kf_stability,
                            "degradation": kf_degradation,
                            "oos_rank_ic_mean": 0.07,
                            "oos_rank_ic_ir": 0.55,
                        },
                    }
                },
                "rating": {
                    "grade": "A" if recommendation == "promote" else "B",
                    "recommendation": recommendation,
                    "total_score": total_score,
                },
                "lookahead_audit": {
                    "available": True,
                    "risk_level": lookahead_risk,
                },
                "multiple_testing": {
                    "available": True,
                    "risk_level": multiple_testing_risk,
                },
                "warnings": [
                    *(["lookahead_audit_failed"] if lookahead_risk == "high" else []),
                    *(["multiple_testing_failed"] if multiple_testing_risk == "high" else []),
                ],
                "params": {
                    "lookback_bars": lookback_bars,
                    "horizon_days": horizon_days,
                    "max_dates": max_dates,
                },
                "stage": "validated",
            },
        }
    )

__all__ = [name for name in globals() if name not in {"__builtins__", "__all__"}]
