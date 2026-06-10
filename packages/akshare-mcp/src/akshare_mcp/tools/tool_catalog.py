"""AI-facing MCP tool contract catalog."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from ..contracts.strategy_manager_contract import build_strategy_manager_input_schema
from ..provider_contracts import provider_tool_contracts

STANDARD_ENVELOPE_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "success": {"type": "boolean"},
        "data": {"type": ["object", "array", "string", "number", "boolean", "null"]},
        "error": {"type": ["string", "null"]},
        "error_code": {"type": ["string", "null"]},
        "source": {"type": "string"},
        "cached": {"type": "boolean"},
        "timestamp": {"type": "string"},
        "meta": {
            "type": "object",
            "properties": {
                "trace_id": {"type": "string"},
                "tool_version": {"type": "string"},
                "data_timestamp": {"type": ["string", "null"]},
                "source_chain": {"type": "array", "items": {"type": "string"}},
                "cached": {"type": "boolean"},
                "latency_ms": {"type": "number"},
                "quality": {"type": "object"},
                "provider_contract": {"type": "object"},
                "contract_meta": {"type": "object"},
                "quality_gate": {"type": "object"},
                "reconciliation": {"type": "object"},
                "provider_status": {"type": "object"},
                "side_effect": {"type": "object"},
                "lineage": {"type": "object"},
                "pit": {
                    "type": "object",
                    "description": "Point-In-Time compliance metadata: as_of, pit_passed",
                    "properties": {
                        "as_of": {"type": "string"},
                        "pit_passed": {"type": "boolean"},
                    },
                },
                "idempotency_key": {"type": ["string", "null"]},
                "degraded": {"type": "boolean"},
            },
            "additionalProperties": True,
        },
    },
    "required": ["success", "data", "error", "source", "cached", "timestamp"],
    "additionalProperties": True,
}


def _contract(
    *,
    name: str,
    title: str,
    category: str,
    description: str,
    required_params: list[str],
    input_schema: dict[str, Any],
    side_effect_level: str,
    freshness: str,
    examples: list[dict[str, Any]],
    tags: list[str],
    output_schema: dict[str, Any] | None = None,
    source_policy: dict[str, Any] | None = None,
    contract_source: str = "akshare_mcp.tool_catalog",
) -> dict[str, Any]:
    payload = {
        "name": name,
        "title": title,
        "category": category,
        "description": description,
        "required_params": required_params,
        "input_schema": input_schema,
        "output_schema": output_schema or STANDARD_ENVELOPE_OUTPUT_SCHEMA,
        "side_effect": {
            "level": side_effect_level,
            "confirmation_required": side_effect_level == "trade_risk",
        },
        "freshness": {"expectation": freshness},
        "examples": examples,
        "tags": tags,
        "contract_version": "ai_tool_contract_v1",
        "contract_source": contract_source,
    }
    if source_policy is not None:
        payload["source_policy"] = source_policy
    return payload


TOOL_CONTRACTS: dict[str, dict[str, Any]] = {
    "analyze_stock_workflow": _contract(
        name="analyze_stock_workflow",
        title="Analyze Stock Workflow",
        category="research",
        description="AI-facing narrow workflow for stock snapshot analysis with profile, kline, financial and decision context.",
        required_params=["code"],
        input_schema={
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "6-digit stock code"},
                "investment_style": {"type": "string"},
                "include_kline": {"type": "boolean"},
                "include_financials": {"type": "boolean"},
                "include_decision": {"type": "boolean"},
                "kline_limit": {"type": "integer", "minimum": 20, "maximum": 240},
                "as_of": {"type": "string", "description": "PIT cutoff date (ISO string). Omit for current time."},
            },
            "required": ["code"],
            "additionalProperties": True,
        },
        side_effect_level="read_only",
        freshness="intraday_quote_and_recent_fundamental_context",
        examples=[
            {
                "description": "Generate a read-only stock snapshot for one code",
                "arguments": {"code": "600519", "include_financials": True, "include_decision": True},
            }
        ],
        tags=["workflow", "stock-analysis", "ai-friendly"],
    ),
    "analyze_stock_product_workflow": _contract(
        name="analyze_stock_product_workflow",
        title="Analyze Stock Product Workflow",
        category="research",
        description="Unified stock deep-analysis workflow with evidence normalization, integrity gate, agent review, synthesis and report bundle artifacts.",
        required_params=["code"],
        input_schema={
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "6-digit stock code or stock name"},
                "task": {
                    "type": "string",
                    "enum": ["quick_scan", "deep_analysis", "recover_gaps", "rebuild_report", "trade_plan"],
                },
                "run_id": {"type": "string", "description": "Existing run id for rebuild_report"},
                "investment_style": {"type": "string"},
                "user_id": {"type": "string"},
                "market": {"type": "string", "description": "Market scope; cn by default for phase 1"},
                "as_of": {"type": "string", "description": "PIT cutoff date (ISO string). Omit for current time."},
            },
            "required": ["code"],
            "additionalProperties": True,
        },
        side_effect_level="stateful",
        freshness="intraday_quote_and_recent_fundamental_context",
        examples=[
            {
                "description": "Run full deep analysis for a stock",
                "arguments": {"code": "600519", "task": "deep_analysis", "investment_style": "balanced"},
            },
            {
                "description": "Rebuild an existing HTML report bundle",
                "arguments": {"code": "600519", "task": "rebuild_report", "run_id": "stock-analysis-run-600519-demo"},
            },
        ],
        tags=["workflow", "stock-analysis", "product-surface", "lineage"],
    ),
    "factor_candidate_workflow": _contract(
        name="factor_candidate_workflow",
        title="Factor Candidate Workflow",
        category="quant",
        description="AI-facing workflow for factor candidate generation, validation, registry review and scheduler checks.",
        required_params=[],
        input_schema={
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "enum": ["pipeline", "generate", "validate", "registry_review", "scheduler_check"],
                },
                "code": {"type": "string"},
                "codes": {"type": "array", "items": {"type": "string"}},
                "artifact_id": {"type": "string"},
                "candidate_index": {"type": "integer", "minimum": 0},
                "candidate_count": {"type": "integer", "minimum": 1, "maximum": 24},
                "persist_artifact": {"type": "boolean"},
                "write_memory": {"type": "boolean"},
                "run_scheduler_now": {"type": "boolean"},
                "idempotency_key": {"type": "string"},
                "as_of": {"type": "string", "description": "PIT cutoff date (ISO string). Omit for current time."},
            },
            "additionalProperties": True,
        },
        side_effect_level="stateful",
        freshness="depends_on_market_context_and_artifact_state",
        examples=[
            {
                "description": "Generate and validate candidate factors for several stocks",
                "arguments": {"task": "pipeline", "codes": ["600519", "000001"], "candidate_count": 6},
            }
        ],
        tags=["workflow", "factor-mining", "registry", "lineage"],
    ),
    "strategy_review_workflow": _contract(
        name="strategy_review_workflow",
        title="Strategy Review Workflow",
        category="strategy",
        description="AI-facing workflow for strategy review with lifecycle, runtime, promotion and optional refresh steps.",
        required_params=["strategy_id"],
        input_schema={
            "type": "object",
            "properties": {
                "strategy_id": {"type": "string"},
                "include_factory_status": {"type": "boolean"},
                "include_review_report": {"type": "boolean"},
                "include_runtime_alerts": {"type": "boolean"},
                "run_factory_once": {"type": "boolean"},
                "run_runtime_cycle": {"type": "boolean"},
                "idempotency_key": {"type": "string"},
                "as_of": {"type": "string", "description": "PIT cutoff date (ISO string). Omit for current time."},
            },
            "required": ["strategy_id"],
            "additionalProperties": True,
        },
        side_effect_level="stateful",
        freshness="runtime_and_review_state",
        examples=[
            {
                "description": "Review a strategy in read-only mode",
                "arguments": {"strategy_id": "strat_demo", "include_runtime_alerts": True},
            }
        ],
        tags=["workflow", "strategy", "promotion-review", "runtime"],
    ),
    "prediction_diagnosis_workflow": _contract(
        name="prediction_diagnosis_workflow",
        title="Prediction Diagnosis Workflow",
        category="quant",
        description="Diagnose model probabilities with calibration, uncertainty and lineage-friendly output.",
        required_params=["probabilities", "labels"],
        input_schema={
            "type": "object",
            "properties": {
                "probabilities": {"type": "array", "items": {"type": "number"}},
                "labels": {"type": "array", "items": {"type": "number"}},
                "raw_scores": {"type": "array", "items": {"type": "number"}},
                "method": {"type": "string", "enum": ["raw", "platt", "isotonic"]},
                "platt_a": {"type": "number"},
                "platt_b": {"type": "number"},
                "coverage_target": {"type": "number"},
                "dataset_id": {"type": "string"},
                "run_id": {"type": "string"},
                "persist_artifact": {"type": "boolean"},
                "output_artifact_id": {"type": "string"},
                "as_of": {"type": "string", "description": "PIT cutoff date (ISO string). Omit for current time."},
            },
            "required": ["probabilities", "labels"],
            "additionalProperties": True,
        },
        side_effect_level="stateful",
        freshness="depends_on_input_predictions_and_labels",
        examples=[
            {
                "description": "Build a calibration report from model probabilities",
                "arguments": {"probabilities": [0.2, 0.8], "labels": [0, 1], "method": "raw"},
            }
        ],
        tags=["workflow", "prediction", "calibration", "uncertainty"],
    ),
    "data_quality_workflow": _contract(
        name="data_quality_workflow",
        title="Data Quality Workflow",
        category="data_sync",
        description="Assess dataset completeness, missing fields, minimum quality gate and remediation hints.",
        required_params=[],
        input_schema={
            "type": "object",
            "properties": {
                "dataset_id": {"type": "string"},
                "records": {"type": "array", "items": {"type": "object"}},
                "required_fields": {"type": "array", "items": {"type": "string"}},
                "as_of_field": {"type": "string"},
                "as_of_value": {"type": "string"},
                "source": {"type": "string"},
                "source_chain": {"type": "array", "items": {"type": "string"}},
                "minimum_quality_threshold": {"type": "number"},
                "persist_artifact": {"type": "boolean"},
                "output_artifact_id": {"type": "string"},
                "as_of": {"type": "string", "description": "PIT cutoff date (ISO string). Omit for current time."},
            },
            "additionalProperties": True,
        },
        side_effect_level="stateful",
        freshness="depends_on_input_dataset_snapshot",
        examples=[
            {
                "description": "Validate a small record batch against required fields",
                "arguments": {
                    "dataset_id": "dataset_demo",
                    "required_fields": ["code", "date", "close"],
                    "records": [{"code": "600519", "date": "2026-04-01", "close": 1820.5}],
                },
            }
        ],
        tags=["workflow", "data-quality", "dataset", "validation"],
    ),
    "semantic_stock_search": _contract(
        name="semantic_stock_search",
        title="Semantic Stock Search",
        category="search",
        description="Resolve stock ideas from natural-language cues such as sector, style, theme, code or stock name.",
        required_params=["query"],
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Natural-language stock query in Chinese or ticker/name form."},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
        side_effect_level="read_only",
        freshness="vector_index_and_market_taxonomy_snapshot",
        examples=[
            {"description": "Search high-dividend bank stocks", "arguments": {"query": "高股息银行股", "limit": 20}},
            {"description": "Search by stock code or short name", "arguments": {"query": "600519", "limit": 10}},
        ],
        tags=["search", "semantic", "screening", "vector"],
    ),
    "search_similar_stocks": _contract(
        name="search_similar_stocks",
        title="Search Similar Stocks",
        category="search",
        description="Find similar stocks for a given target code using profile, fundamental and technical similarity signals.",
        required_params=["code"],
        input_schema={
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Target stock code."},
                "top_n": {"type": "integer", "minimum": 1, "maximum": 50},
                "similarity_type": {
                    "type": "string",
                    "enum": ["both", "profile", "fundamental", "technical"],
                },
                "search_backend": {"type": "string", "enum": ["db", "memory"]},
                "allow_fallback": {"type": "boolean"},
            },
            "required": ["code"],
            "additionalProperties": True,
        },
        side_effect_level="read_only",
        freshness="vector_index_and_recent_stock_profile_snapshot",
        examples=[
            {
                "description": "Find stocks similar to Kweichow Moutai",
                "arguments": {"code": "600519", "top_n": 10, "similarity_type": "both"},
            }
        ],
        tags=["search", "similarity", "vector", "research"],
    ),
    "search_by_kline": _contract(
        name="search_by_kline",
        title="Search By Kline Pattern",
        category="quant",
        description="Find stocks with K-line shapes similar to a target stock over a recent window.",
        required_params=["code"],
        input_schema={
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Target stock code."},
                "days": {"type": "integer", "minimum": 5, "maximum": 240},
                "top_n": {"type": "integer", "minimum": 1, "maximum": 50},
                "search_backend": {"type": "string", "enum": ["db", "memory"]},
                "allow_fallback": {"type": "boolean"},
            },
            "required": ["code"],
            "additionalProperties": True,
        },
        side_effect_level="read_only",
        freshness="recent_kline_vector_snapshot",
        examples=[
            {
                "description": "Match recent 20-day K-line patterns",
                "arguments": {"code": "600519", "days": 20, "top_n": 10},
            }
        ],
        tags=["quant", "kline", "vector", "pattern-search"],
    ),
    "available_tools": _contract(
        name="available_tools",
        title="Available Tools",
        category="search",
        description="List available tools with AI-facing contracts, side-effect level and examples when known.",
        required_params=[],
        input_schema={
            "type": "object",
            "properties": {
                "category": {"type": "string"},
                "include_contracts": {"type": "boolean"},
            },
            "additionalProperties": True,
        },
        side_effect_level="read_only",
        freshness="runtime_surface",
        examples=[{"description": "List all AI-callable tools", "arguments": {"include_contracts": True}}],
        tags=["catalog", "discovery"],
    ),
    "get_tool_contract": _contract(
        name="get_tool_contract",
        title="Get Tool Contract",
        category="search",
        description="Fetch a single AI-facing tool contract including required parameters, examples and output schema.",
        required_params=["tool_name"],
        input_schema={
            "type": "object",
            "properties": {"tool_name": {"type": "string"}},
            "required": ["tool_name"],
            "additionalProperties": False,
        },
        side_effect_level="read_only",
        freshness="runtime_surface",
        examples=[{"description": "Inspect one workflow tool", "arguments": {"tool_name": "analyze_stock_workflow"}}],
        tags=["catalog", "contract"],
    ),
    "quant_manager": _contract(
        name="quant_manager",
        title="Quant Manager",
        category="quant",
        description="High-capacity manager for quant research, factor mining, model registry and experiment replay.",
        required_params=["action"],
        input_schema={
            "type": "object",
            "properties": {
                "action": {"type": "string"},
                "params": {"type": "object"},
                "kwargs": {"type": ["object", "string"]},
                "code": {"type": "string"},
            },
            "required": ["action"],
            "additionalProperties": True,
        },
        side_effect_level="stateful",
        freshness="depends_on_action",
        examples=[{"description": "Call factor candidate generation", "arguments": {"action": "llm_factor_mining", "params": {"codes": ["600519"]}}}],
        tags=["manager", "quant", "heavy-surface"],
    ),
    "strategy_manager": _contract(
        name="strategy_manager",
        title="Strategy Manager",
        category="strategy",
        description="High-capacity manager for strategy marketplace, reviews, factory runs and runtime governance.",
        required_params=["action"],
        input_schema={
            "type": "object",
            "properties": {
                "action": {"type": "string"},
                "params": {"type": "object"},
                "kwargs": {"type": ["object", "string"]},
            },
            "required": ["action"],
            "additionalProperties": True,
        },
        side_effect_level="stateful",
        freshness="depends_on_runtime_state",
        examples=[{"description": "Read strategy review report", "arguments": {"action": "review_report", "params": {"strategy_id": "strat_demo"}}}],
        tags=["manager", "strategy", "heavy-surface"],
    ),
    "screener_manager": _contract(
        name="screener_manager",
        title="Screener Manager",
        category="screening",
        description="Manager for fundamental, technical and combined stock screening. Supports action + params/kwargs payloads.",
        required_params=["action"],
        input_schema={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "help",
                        "screen",
                        "list",
                        "list_strategies",
                        "save_strategy",
                        "run_strategy",
                        "technical_screen",
                        "list_conditions",
                        "combined_screen",
                    ],
                },
                "params": {"type": "object"},
                "kwargs": {"type": ["object", "string", "null"]},
                "criteria": {"type": "object", "description": "Fundamental criteria dict for screen action."},
                "fundamental_criteria": {"type": "object", "description": "Fundamental criteria dict for combined_screen."},
                "fundamental_conditions": {
                    "type": "array",
                    "description": "Optional parsed fundamental condition list from parse_selection_query.",
                    "items": {"type": "object"},
                },
                "conditions": {
                    "type": "array",
                    "description": "Technical condition ids or condition dicts with params.",
                    "items": {"type": ["string", "object"]},
                },
                "technical_conditions": {
                    "type": "array",
                    "items": {"type": ["string", "object"]},
                },
                "tech_conditions": {
                    "type": "array",
                    "items": {"type": ["string", "object"]},
                },
                "logic": {"type": "string", "enum": ["AND", "OR"]},
                "stock_pool": {"type": ["array", "string"]},
                "limit": {"type": "integer", "minimum": 1, "maximum": 500},
            },
            "required": ["action"],
            "additionalProperties": True,
        },
        side_effect_level="stateful",
        freshness="depends_on_screen_action_and_market_snapshot",
        examples=[
            {
                "description": "Run a combined screen using parsed semantic conditions",
                "arguments": {
                    "action": "combined_screen",
                    "fundamental_conditions": [{"field": "pe_ratio", "operator": "<", "value": 20}],
                    "technical_conditions": [{"id": "price_above_ma", "params": {"n": 20}}],
                    "logic": "AND",
                    "limit": 20,
                },
            }
        ],
        tags=["manager", "screening", "fundamental", "technical"],
    ),
    "governance_check_workflow": _contract(
        name="governance_check_workflow",
        title="Governance Check Workflow",
        category="governance",
        description="AI-facing workflow for monitoring governance across factor decay, crowding, model drift, strategy health and online/offline consistency.",
        required_params=[],
        input_schema={
            "type": "object",
            "properties": {
                "target_type": {"type": "string", "enum": ["factor", "model", "strategy", "system"], "description": "Type of target to check"},
                "target_id": {"type": "string", "description": "Identifier of the specific target (factor name, model name, strategy ID)"},
                "ic_history": {"type": "array", "items": {"type": "number"}, "description": "Chronological IC values for factor decay check"},
                "factor_expression": {"type": "string", "description": "Factor expression for crowding analysis"},
                "factor_category": {"type": "string", "description": "Factor category (momentum, value, quality, etc.)"},
                "existing_factor_pool": {"type": "array", "items": {"type": "string"}, "description": "Names of existing factors in the pool"},
                "current_metrics": {"type": "object", "description": "Current model metrics for drift detection"},
                "baseline_metrics": {"type": "object", "description": "Baseline model metrics for drift comparison"},
                "posture_level": {"type": "string", "description": "Strategy posture level (safe, guarded, critical)"},
                "control_mode": {"type": "string", "description": "Strategy control mode (active, halted, manual_stop)"},
                "open_alert_count": {"type": "integer", "description": "Number of open runtime alerts"},
                "include_factor_decay": {"type": "boolean", "default": True},
                "include_crowding": {"type": "boolean", "default": True},
                "include_model_drift": {"type": "boolean", "default": True},
                "include_strategy_health": {"type": "boolean", "default": True},
                "include_consistency": {"type": "boolean", "default": True},
                "as_of": {"type": "string", "description": "PIT cutoff date (ISO string). Omit for current time."},
            },
            "additionalProperties": True,
        },
        side_effect_level="read_only",
        freshness="real_time_governance_snapshot",
        examples=[
            {
                "description": "Check factor governance for a specific factor",
                "arguments": {"target_type": "factor", "target_id": "momentum_20d", "ic_history": [0.05, 0.04, 0.03, 0.02]},
            },
            {
                "description": "Run system-wide governance check",
                "arguments": {"target_type": "system"},
            },
        ],
        tags=["workflow", "governance", "monitoring", "ai-friendly"],
    ),
    "run_skill": _contract(
        name="run_skill",
        title="Run Skill",
        category="skills",
        description="Execute a bundled orchestrated skill for higher-level domain workflows.",
        required_params=["skill_id"],
        input_schema={
            "type": "object",
            "properties": {"skill_id": {"type": "string"}, "params": {"type": "object"}},
            "required": ["skill_id"],
            "additionalProperties": True,
        },
        side_effect_level="read_only",
        freshness="depends_on_skill_and_inputs",
        examples=[{"description": "Run factor mining skill", "arguments": {"skill_id": "akshare-factor-mining", "params": {"task": "candidate_pipeline"}}}],
        tags=["skills", "workflow"],
    ),
    # ── Key bottom-level managers ────────────────────────────────────────────
    "risk_manager": _contract(
        name="risk_manager",
        title="Risk Manager",
        category="risk",
        description="Portfolio risk analysis: VaR, stress-test, and exposure breakdown. Pass action + params/kwargs.",
        required_params=["action"],
        input_schema={
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["help", "calculate_var", "stress_test", "risk_exposure", "list"]},
                "params": {"type": "object"},
                "kwargs": {"type": ["object", "string", "null"]},
                "codes": {"type": "array", "items": {"type": "string"}},
                "weights": {"type": "array", "items": {"type": "number"}},
                "scenario": {"type": "string"},
                "confidence": {"type": "number", "minimum": 0.8, "maximum": 0.9999},
                "method": {"type": "string", "enum": ["historical", "parametric", "monte_carlo"]},
                "lookback_days": {"type": "integer"},
                "portfolio_value": {"type": "number"},
            },
            "required": ["action"],
            "additionalProperties": True,
        },
        side_effect_level="read_only",
        freshness="depends_on_kline_and_portfolio_data",
        examples=[
            {"description": "Calculate 95% VaR for a 2-stock portfolio", "arguments": {"action": "calculate_var", "codes": ["600519", "000001"], "weights": [0.6, 0.4], "confidence": 0.95}},
            {"description": "Run stress test with market_crash scenario", "arguments": {"action": "stress_test", "codes": ["600519"], "scenario": "market_crash"}},
        ],
        tags=["risk", "var", "stress-test", "exposure"],
    ),
    "quant_manager": _contract(
        name="quant_manager",
        title="Quant Manager",
        category="quant",
        description=(
            "Quant research hub: factor mining, candidate validation, registry, research memory, "
            "autoML, IC analysis, and scheduler control. Prefer factor_candidate_workflow for "
            "end-to-end pipelines; use quant_manager directly for individual steps."
        ),
        required_params=["action"],
        input_schema={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "help", "llm_factor_mining", "validate_factor_candidate",
                        "factor_candidate_registry", "factor_research_memory",
                        "factor_ic", "batch_compute_factors", "calculate_factors",
                        "automl_discovery", "champion_challenger", "model_registry",
                        "replay_experiment", "scheduler_status", "scheduler_run_now",
                    ],
                },
                "params": {"type": "object"},
                "kwargs": {"type": ["object", "string", "null"]},
                "code": {"type": "string", "description": "Single 6-digit stock code"},
                "dry_run": {"type": "boolean", "description": "If true, validate only; no artifact is persisted."},
                "as_of": {"type": "string", "description": "PIT cutoff date (ISO). Applies to validation and IC steps."},
            },
            "required": ["action"],
            "additionalProperties": True,
        },
        side_effect_level="stateful",
        freshness="depends_on_market_data_and_artifact_state",
        examples=[
            {"description": "Mine LLM factor candidates for two stocks", "arguments": {"action": "llm_factor_mining", "params": {"codes": ["600519", "000001"], "candidate_count": 4, "persist_artifact": True}}},
            {"description": "Validate a factor candidate from artifact (dry_run)", "arguments": {"action": "validate_factor_candidate", "params": {"artifact_id": "art_xxx", "dry_run": True}}},
            {"description": "Check active pool in factor registry", "arguments": {"action": "factor_candidate_registry", "params": {"op": "active_pool", "limit": 20}}},
        ],
        tags=["quant", "factor-mining", "registry", "automl"],
    ),
    "execution_manager": _contract(
        name="execution_manager",
        title="Execution Manager",
        category="execution",
        description=(
            "TWAP/VWAP execution planning with soft-gate risk warnings, compliance gate, "
            "and cost model transparency. Use dry_run=true to validate a plan without persisting it."
        ),
        required_params=["action"],
        input_schema={
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["help", "twap", "vwap", "list", "summary", "get_config", "set_config", "update"]},
                "params": {"type": "object"},
                "kwargs": {"type": ["object", "string", "null"]},
                "dry_run": {"type": "boolean", "description": "Preview plan without persisting task. Returns status=dry_run_preview."},
            },
            "required": ["action"],
            "additionalProperties": True,
        },
        side_effect_level="stateful",
        freshness="real_time_for_planning_static_for_config",
        examples=[
            {"description": "Dry-run TWAP plan to inspect cost and warnings before submitting", "arguments": {"action": "twap", "dry_run": True, "params": {"code": "600519", "total_quantity": 1000, "duration_minutes": 60}}},
            {"description": "Get current soft-gate config", "arguments": {"action": "get_config"}},
        ],
        tags=["execution", "twap", "vwap", "dry-run", "cost-model"],
    ),
    "strategy_manager": _contract(
        name="strategy_manager",
        title="Strategy Manager",
        category="strategy",
        description=(
            "Strategy marketplace lifecycle manager: create, publish, lifecycle scan, "
            "promotion review, runtime alerts, incubation, vector governance, domain projection, "
            "AI generation, and factory status. Prefer strategy_review_workflow and "
            "resource://strategy/{id}/review for read-only snapshots."
        ),
        required_params=["action"],
        input_schema=build_strategy_manager_input_schema(),
        side_effect_level="stateful",
        freshness="depends_on_strategy_lifecycle_and_factory_state",
        examples=[
            {"description": "List strategies sorted by rank", "arguments": {"action": "list", "params": {"limit": 10, "sort_by": "rank"}}},
            {"description": "Get review report for a specific strategy", "arguments": {"action": "review_report", "params": {"strategy_id": "strat_001"}}},
            {"description": "Verify execution-audit schema, migrations, and linkage coverage", "arguments": {"action": "execution_audit_verification", "params": {"strategy_id": "strat_001"}}},
            {"description": "Inspect vector index health for strategy governance", "arguments": {"action": "vector_health", "params": {"index_name": "strategy_behavior"}}},
            {"description": "Run factory once to advance lifecycle", "arguments": {"action": "factory_run_once"}},
        ],
        tags=["strategy", "lifecycle", "factory", "promotion", "runtime"],
    ),
    # ── P2-1 adapter tools ───────────────────────────────────────────────────
    "experiment_tracker": _contract(
        name="experiment_tracker",
        title="Experiment Tracker",
        category="research",
        description=(
            "Log and query experiment runs, metrics, and artifacts. "
            "Builtin by default; switches to MLflow when installed. "
            "Actions: backend, log_run, log_metric, log_artifact, get_run, list_runs."
        ),
        required_params=["action"],
        input_schema={
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["backend", "log_run", "log_metric", "log_artifact", "get_run", "list_runs"]},
                "experiment_name": {"type": "string"},
                "run_id": {"type": "string"},
                "metric_key": {"type": "string"},
                "metric_value": {"type": "number"},
                "metric_step": {"type": "integer"},
                "artifact_key": {"type": "string"},
                "artifact_data": {"type": "object"},
                "params": {"type": "object"},
                "tags": {"type": "object"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 200},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        side_effect_level="stateful",
        freshness="session_scoped_in_memory",
        examples=[
            {"description": "Start an experiment run", "arguments": {"action": "log_run", "experiment_name": "factor_ic_study", "params": {"codes": ["600519"], "horizon": 10}}},
            {"description": "List recent runs", "arguments": {"action": "list_runs", "experiment_name": "factor_ic_study", "limit": 10}},
            {"description": "Check active backend (builtin vs MLflow)", "arguments": {"action": "backend"}},
        ],
        tags=["experiment", "tracking", "mlflow", "lineage", "p2"],
    ),
    "data_validation": _contract(
        name="data_validation",
        title="Data Validation",
        category="research",
        description=(
            "Validate a dataset against expectations: required fields, missing ratios, "
            "type conformance, and minimum quality threshold. "
            "Builtin by default; switches to Great Expectations when installed. "
            "Actions: backend, validate."
        ),
        required_params=["action"],
        input_schema={
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["backend", "validate"]},
                "records": {"type": "array", "items": {"type": "object"}, "description": "List of records to validate"},
                "expectations": {"type": "object", "description": "Expectation config: required_fields, type_map, value_ranges, etc."},
                "dataset_id": {"type": "string"},
                "minimum_quality_threshold": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        side_effect_level="read_only",
        freshness="stateless_per_call",
        examples=[
            {"description": "Validate a batch of records for required fields", "arguments": {"action": "validate", "records": [{"close": 10.5, "volume": 1000}], "expectations": {"required_fields": ["close", "volume"]}, "minimum_quality_threshold": 0.95}},
            {"description": "Check active backend", "arguments": {"action": "backend"}},
        ],
        tags=["data-quality", "validation", "great-expectations", "p2"],
    ),
    "get_market_temperature_snapshot": _contract(
        name="get_market_temperature_snapshot",
        title="Market Temperature Snapshot",
        category="market",
        description=(
            "Build a read-only A-share market thermometer from local SQLite stock universe "
            "and daily K-line data. Returns market temperature, MA20 breadth, hot/cold "
            "industry rankings, and explicit data-quality metadata."
        ),
        required_params=[],
        input_schema={
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 1000,
                    "description": "Maximum stock-universe sample size loaded from SQLite.",
                },
                "top_n": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 50,
                    "description": "Number of hot/cold industry rows to return.",
                },
                "as_of": {
                    "type": ["string", "null"],
                    "description": "Optional point-in-time cutoff date, YYYY-MM-DD.",
                },
                "min_bars": {
                    "type": "integer",
                    "minimum": 2,
                    "maximum": 120,
                    "description": "Minimum daily bars requested per stock for MA20 calculation.",
                },
                "use_cache": {
                    "type": "boolean",
                    "default": True,
                    "description": "When true, serve the latest matching local snapshot cache before recomputing.",
                },
            },
            "additionalProperties": False,
        },
        side_effect_level="read_only",
        freshness="local_sqlite_daily_kline_snapshot",
        examples=[
            {
                "description": "Build a default market thermometer snapshot",
                "arguments": {"limit": 300, "top_n": 8},
            },
            {
                "description": "Build a point-in-time snapshot for a specific trade date",
                "arguments": {"as_of": "2026-06-08", "limit": 500, "top_n": 10},
            },
        ],
        tags=["market", "breadth", "industry-rotation", "temperature", "read-only"],
    ),
    "sync_market_temperature_snapshot_cache": _contract(
        name="sync_market_temperature_snapshot_cache",
        title="Sync Market Temperature Snapshot Cache",
        category="data_sync",
        description=(
            "Data-sync entrypoint for refreshing the persisted market thermometer cache "
            "from local SQLite stock and K-line data."
        ),
        required_params=[],
        input_schema={
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 1000,
                    "description": "Maximum stock-universe sample size loaded from SQLite.",
                },
                "top_n": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 50,
                    "description": "Number of hot/cold industry rows stored in the returned preview.",
                },
                "as_of": {
                    "type": ["string", "null"],
                    "description": "Optional point-in-time cutoff date, YYYY-MM-DD.",
                },
                "min_bars": {
                    "type": "integer",
                    "minimum": 2,
                    "maximum": 120,
                    "description": "Minimum daily bars requested per stock for MA20 calculation.",
                },
            },
            "additionalProperties": False,
        },
        side_effect_level="stateful",
        freshness="local_sqlite_daily_snapshot_cache_refresh",
        examples=[
            {
                "description": "Refresh the market thermometer cache from the data-sync surface",
                "arguments": {"limit": 1000, "top_n": 20},
            }
        ],
        tags=["data-sync", "market", "breadth", "temperature", "cache", "stateful"],
    ),
    "refresh_market_temperature_snapshot_cache": _contract(
        name="refresh_market_temperature_snapshot_cache",
        title="Refresh Market Temperature Snapshot Cache",
        category="market",
        description=(
            "Compute the A-share market thermometer from local SQLite stock and K-line data, "
            "then persist the snapshot into the durable local cache for fast read-only access."
        ),
        required_params=[],
        input_schema={
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 1000,
                    "description": "Maximum stock-universe sample size loaded from SQLite.",
                },
                "top_n": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 50,
                    "description": "Number of hot/cold industry rows stored in the returned preview.",
                },
                "as_of": {
                    "type": ["string", "null"],
                    "description": "Optional point-in-time cutoff date, YYYY-MM-DD.",
                },
                "min_bars": {
                    "type": "integer",
                    "minimum": 2,
                    "maximum": 120,
                    "description": "Minimum daily bars requested per stock for MA20 calculation.",
                },
            },
            "additionalProperties": False,
        },
        side_effect_level="stateful",
        freshness="local_sqlite_daily_snapshot_cache_refresh",
        examples=[
            {
                "description": "Refresh the full local market-temperature cache",
                "arguments": {"limit": 1000, "top_n": 20},
            },
            {
                "description": "Refresh a point-in-time cache entry",
                "arguments": {"as_of": "2026-06-08", "limit": 1000, "top_n": 20},
            },
        ],
        tags=["market", "breadth", "industry-rotation", "temperature", "cache", "stateful"],
    ),
    "list_market_temperature_snapshot_cache": _contract(
        name="list_market_temperature_snapshot_cache",
        title="List Market Temperature Snapshot Cache",
        category="market",
        description=(
            "List compact metadata for persisted market thermometer cache entries, "
            "including trade date, temperature, state, sample counts, quality status, and warnings."
        ),
        required_params=[],
        input_schema={
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 365,
                    "description": "Maximum number of cached trade-date snapshots to list.",
                },
                "include_snapshot": {
                    "type": "boolean",
                    "default": False,
                    "description": "When true, include each raw snapshot JSON; keep false for compact UI/history queries.",
                },
            },
            "additionalProperties": False,
        },
        side_effect_level="read_only",
        freshness="local_sqlite_market_temperature_cache_history",
        examples=[
            {
                "description": "List recent market thermometer cache entries",
                "arguments": {"limit": 30},
            }
        ],
        tags=["market", "breadth", "industry-rotation", "temperature", "cache", "history", "read-only"],
    ),
    "list_market_temperature_industry_history": _contract(
        name="list_market_temperature_industry_history",
        title="List Market Temperature Industry History",
        category="market",
        description=(
            "Read point-in-time industry temperature history from persisted market thermometer "
            "cache snapshots. Pass an industry name/code for one time series, or omit it to "
            "return the top industries per cached trade date."
        ),
        required_params=[],
        input_schema={
            "type": "object",
            "properties": {
                "industry": {
                    "type": ["string", "null"],
                    "description": "Optional industry name or code to filter, for example bank or 801780.",
                },
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 365,
                    "description": "Maximum cached trade-date snapshots to inspect.",
                },
                "top_n": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 50,
                    "description": "When industry is omitted, return at most this many industries per date.",
                },
                "match_mode": {
                    "type": "string",
                    "enum": ["exact", "contains"],
                    "default": "exact",
                    "description": "Industry match mode for the name/code filter.",
                },
                "include_source_chain": {
                    "type": "boolean",
                    "default": False,
                    "description": "Include snapshot source_chain on each row for audits.",
                },
            },
            "additionalProperties": False,
        },
        side_effect_level="read_only",
        freshness="local_sqlite_market_temperature_industry_history",
        examples=[
            {
                "description": "Read one industry's cached temperature time series",
                "arguments": {"industry": "bank", "limit": 60},
            },
            {
                "description": "Read top industry rotation rows for recent cached dates",
                "arguments": {"limit": 20, "top_n": 8},
            },
        ],
        tags=["market", "breadth", "industry-rotation", "temperature", "cache", "history", "read-only"],
    ),
    "list_market_temperature_industry_constituents": _contract(
        name="list_market_temperature_industry_constituents",
        title="List Market Temperature Industry Constituents",
        category="market",
        description=(
            "Read local stock-universe constituents for one market-temperature industry. "
            "This is the drill-down companion to industry heat/history rows and stays "
            "strictly read-only against the local SQLite stocks table."
        ),
        required_params=["industry"],
        input_schema={
            "type": "object",
            "properties": {
                "industry": {
                    "type": "string",
                    "minLength": 1,
                    "description": "Industry name to match against stock universe industry/sector fields.",
                },
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 1000,
                    "description": "Maximum constituent rows to return.",
                },
                "offset": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 10000,
                    "description": "Offset within the matched constituent list.",
                },
                "match_mode": {
                    "type": "string",
                    "enum": ["exact", "contains"],
                    "default": "contains",
                    "description": "Industry match mode for stock universe industry/sector fields.",
                },
                "include_source_chain": {
                    "type": "boolean",
                    "default": False,
                    "description": "Include source_chain on each constituent row for audits.",
                },
            },
            "required": ["industry"],
            "additionalProperties": False,
        },
        side_effect_level="read_only",
        freshness="local_sqlite_stock_universe",
        examples=[
            {
                "description": "List the largest local constituents for one industry",
                "arguments": {"industry": "bank", "limit": 50, "match_mode": "contains"},
            }
        ],
        tags=["market", "industry-rotation", "temperature", "constituents", "stocks", "read-only"],
    ),
    "get_market_temperature_forward_validation": _contract(
        name="get_market_temperature_forward_validation",
        title="Get Market Temperature Forward Validation",
        category="market",
        description=(
            "Build a read-only point-in-time validation matrix from persisted market thermometer "
            "snapshots. Buckets by market temperature state and summarizes future cached market "
            "breadth returns over configurable horizons."
        ),
        required_params=[],
        input_schema={
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "minimum": 2,
                    "maximum": 365,
                    "description": "Maximum cached snapshots to use for validation.",
                },
                "horizons": {
                    "type": ["array", "string", "integer", "null"],
                    "description": "Forward horizons in cached trade-date steps, for example [1, 3, 5] or '1,3,5'.",
                },
                "target_field": {
                    "type": "string",
                    "enum": ["weighted_pct_change", "avg_pct_change", "temperature_delta", "benchmark_return"],
                    "default": "weighted_pct_change",
                    "description": "Forward target. benchmark_return uses local benchmark/index K-line closes when available.",
                },
                "benchmark_code": {
                    "type": ["string", "null"],
                    "default": "000300",
                    "description": "Optional benchmark/index code used when target_field is benchmark_return.",
                },
                "min_samples": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 100,
                    "description": "Minimum samples for a matrix cell to be marked reliable.",
                },
                "neutral_band_pct": {
                    "type": "number",
                    "minimum": 0.0,
                    "maximum": 5.0,
                    "description": "Neutral-state hit threshold in percentage points.",
                },
                "include_samples": {
                    "type": "boolean",
                    "default": False,
                    "description": "Include compact per-date validation samples for audit/debug views.",
                },
            },
            "additionalProperties": False,
        },
        side_effect_level="read_only",
        freshness="local_sqlite_market_temperature_forward_validation",
        examples=[
            {
                "description": "Build the default market-temperature validation matrix",
                "arguments": {"limit": 180, "horizons": [1, 3, 5]},
            }
        ],
        tags=["market", "breadth", "temperature", "forward-validation", "matrix", "read-only"],
    ),
}

TOOL_CONTRACTS.update(provider_tool_contracts())


WORKFLOW_GUIDES: dict[str, dict[str, Any]] = {
    "stock-analysis": {
        "name": "stock-analysis",
        "title": "Stock Analysis Guide",
        "recommended_tools": ["analyze_stock_workflow", "resource://stock/{code}/profile", "stock-analysis"],
        "steps": [
            "Read stock profile context first.",
            "Fetch a single workflow snapshot instead of chaining many raw tools.",
            "Only fall back to manager tools when the workflow result is insufficient.",
        ],
        "guardrails": [
            "Expose evidence and confidence separately.",
            "Do not treat heuristic decision output as a production-grade forecast.",
        ],
    },
    "stock-deep-analysis": {
        "name": "stock-deep-analysis",
        "title": "Stock Deep Analysis Guide",
        "recommended_tools": [
            "analyze_stock_product_workflow",
            "run_skill(skill_id=akshare-stock-deep-analysis)",
            "resource://stock/{code}/deep-analysis",
            "resource://analysis-run/{run_id}/summary",
            "resource://analysis-run/{run_id}/report",
            "stock-analysis-deep",
        ],
        "steps": [
            "Resolve the stock target first; do not continue when name resolution is ambiguous.",
            "Use a single product workflow run to materialize evidence, gap report, review, synthesis and report artifacts.",
            "Read the persisted run summary or report resource instead of re-chaining raw tools in Web or BFF surfaces.",
        ],
        "guardrails": [
            "Block final report publication when critical fields are missing.",
            "Every qualitative section must cite evidence ids or explicit structured sources.",
            "Keep quick_scan and deep_analysis distinct in output scope and report depth.",
        ],
    },
    "factor-governance": {
        "name": "factor-governance",
        "title": "Factor Governance Guide",
        "recommended_tools": ["factor_candidate_workflow", "quant_manager", "factor-registry-review"],
        "steps": [
            "Generate candidates, then validate them, then inspect registry or research memory.",
            "Check fallback and degraded flags before promoting any candidate.",
            "Persist artifact IDs for replay and later review.",
        ],
        "guardrails": [
            "Do not interpret candidate generation as validation success.",
            "Treat scheduler runs and memory writes as stateful operations.",
        ],
    },
    "strategy-promotion": {
        "name": "strategy-promotion",
        "title": "Strategy Promotion Guide",
        "recommended_tools": ["strategy_review_workflow", "resource://strategy/{id}/review", "strategy-promotion-review"],
        "steps": [
            "Read lifecycle projection and runtime context together.",
            "Inspect latest promotion review before triggering runtime-side actions.",
            "Keep factory runs and runtime cycles explicit and auditable.",
        ],
        "guardrails": [
            "Do not infer deployability from ranking alone.",
            "Surface runtime risk and promotion blockers separately from recommendation text.",
        ],
    },
    "governance-monitoring": {
        "name": "governance-monitoring",
        "title": "Governance Monitoring Guide",
        "recommended_tools": [
            "governance_check_workflow",
            "resource://governance/system/report",
            "resource://factor/{factor_id}/profile",
            "resource://model/{model_id}/profile",
            "resource://strategy/{strategy_id}/governance",
        ],
        "steps": [
            "Start with a system-wide governance check to identify flagged dimensions.",
            "Drill into specific factors, models, or strategies using targeted checks.",
            "Review factor decay and crowding before promoting new candidates.",
            "Compare backtest vs execution assumptions to validate strategy readiness.",
        ],
        "guardrails": [
            "Do not interpret 'healthy' governance as permission to deploy.",
            "Always check online/offline consistency before trusting backtest results.",
            "Surface all governance warnings to the user for final decision.",
        ],
    },
}


def get_tool_contract(name: str) -> dict[str, Any] | None:
    item = TOOL_CONTRACTS.get(str(name or "").strip())
    return deepcopy(item) if item else None


def list_tool_contracts() -> list[dict[str, Any]]:
    return [deepcopy(TOOL_CONTRACTS[name]) for name in sorted(TOOL_CONTRACTS)]


def get_workflow_guide(name: str) -> dict[str, Any] | None:
    item = WORKFLOW_GUIDES.get(str(name or "").strip())
    return deepcopy(item) if item else None


def build_tool_meta(name: str) -> dict[str, Any]:
    contract = get_tool_contract(name)
    if not contract:
        return {"contract_version": "ai_tool_contract_v1"}
    return {
        "contract_version": contract.get("contract_version"),
        "contract_source": contract.get("contract_source"),
        "required_params": contract.get("required_params"),
        "side_effect": contract.get("side_effect"),
        "freshness": contract.get("freshness"),
        "source_policy": contract.get("source_policy"),
        "standard_model": contract.get("standard_model"),
        "provider_choices": contract.get("provider_choices"),
        "provider_status": contract.get("provider_status"),
        "quality_gate": contract.get("quality_gate"),
        "reconciliation": contract.get("reconciliation"),
        "form_schema": contract.get("form_schema"),
        "tags": contract.get("tags"),
        "examples": contract.get("examples"),
        "input_schema": contract.get("input_schema"),
        "output_schema": contract.get("output_schema"),
    }
