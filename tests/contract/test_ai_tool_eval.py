"""P0-6 AI Tool-Calling Evaluation Harness.

Validates five dimensions required by the MCP-AI optimization plan:
  1. Tool discovery correctness
  2. Parameter correctness
  3. Safe-mode selection
  4. Degraded / fallback identification
  5. Multi-step workflow chaining

Run with:  pytest tests/contract/test_ai_tool_eval.py -v
"""

from __future__ import annotations

import sys
import os
import re
import importlib
import inspect
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Bootstrap: ensure the akshare_mcp package is importable without a running
# MCP server by adding the source root to sys.path.
# ---------------------------------------------------------------------------
_SRC_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir, os.pardir, "packages", "akshare-mcp", "src")
)
if _SRC_ROOT not in sys.path:
    sys.path.insert(0, _SRC_ROOT)


# ============================================================================
# Dimension 1: Tool Discovery Correctness
# ============================================================================
class TestToolDiscovery:
    """Verify that the tool catalog provides complete, machine-parseable contracts."""

    def test_catalog_contracts_exist(self):
        """TOOL_CONTRACTS must define at least the 5 core AI workflow tools."""
        from akshare_mcp.tools.tool_catalog import TOOL_CONTRACTS

        required_tools = {
            "analyze_stock_workflow",
            "factor_candidate_workflow",
            "strategy_review_workflow",
            "prediction_diagnosis_workflow",
            "data_quality_workflow",
        }
        missing = required_tools - set(TOOL_CONTRACTS.keys())
        assert not missing, f"Missing workflow tools in catalog: {missing}"

    def test_each_contract_has_required_fields(self):
        """Every contract must carry name, description, input_schema, output_schema,
        side_effect, freshness, examples, and tags."""
        from akshare_mcp.tools.tool_catalog import TOOL_CONTRACTS

        required_keys = {
            "name", "title", "category", "description",
            "required_params", "input_schema", "output_schema",
            "side_effect", "freshness", "examples", "tags",
            "contract_version",
        }
        for tool_name, contract in TOOL_CONTRACTS.items():
            missing = required_keys - set(contract.keys())
            assert not missing, f"Tool '{tool_name}' missing contract keys: {missing}"

    def test_output_schema_has_standard_envelope_shape(self):
        """The standard output schema must define success, data, error, source, meta."""
        from akshare_mcp.tools.tool_catalog import STANDARD_ENVELOPE_OUTPUT_SCHEMA

        required_top = {"success", "data", "error", "source", "cached", "timestamp"}
        actual_top = set(STANDARD_ENVELOPE_OUTPUT_SCHEMA.get("properties", {}).keys())
        missing = required_top - actual_top
        assert not missing, f"Standard envelope schema missing properties: {missing}"

        meta_props = STANDARD_ENVELOPE_OUTPUT_SCHEMA["properties"]["meta"]["properties"]
        required_meta = {
            "trace_id", "source_chain", "quality", "side_effect",
            "idempotency_key", "degraded", "latency_ms",
        }
        missing_meta = required_meta - set(meta_props.keys())
        assert not missing_meta, f"Envelope meta schema missing: {missing_meta}"

    def test_workflow_guides_exist(self):
        """Workflow guides for stock-analysis, factor-governance, strategy-promotion."""
        from akshare_mcp.tools.tool_catalog import WORKFLOW_GUIDES

        required_guides = {"stock-analysis", "factor-governance", "strategy-promotion"}
        missing = required_guides - set(WORKFLOW_GUIDES.keys())
        assert not missing, f"Missing workflow guides: {missing}"

    def test_build_tool_meta_populates_contract(self):
        """build_tool_meta must return a non-empty dict with contract version for known tools."""
        from akshare_mcp.tools.tool_catalog import build_tool_meta

        meta = build_tool_meta("analyze_stock_workflow")
        assert meta.get("contract_version") == "ai_tool_contract_v1"
        assert meta.get("required_params") is not None
        assert meta.get("side_effect") is not None
        assert meta.get("examples") is not None

    def test_list_tool_contracts_non_empty(self):
        """list_tool_contracts returns all defined contracts."""
        from akshare_mcp.tools.tool_catalog import list_tool_contracts

        contracts = list_tool_contracts()
        assert len(contracts) >= 5, f"Expected >=5 contracts, got {len(contracts)}"

    def test_get_tool_contract_returns_copy(self):
        """get_tool_contract must return a deep copy (mutation-safe)."""
        from akshare_mcp.tools.tool_catalog import get_tool_contract

        c1 = get_tool_contract("analyze_stock_workflow")
        c2 = get_tool_contract("analyze_stock_workflow")
        assert c1 is not c2
        assert c1 == c2


# ============================================================================
# Dimension 2: Parameter Correctness
# ============================================================================
class TestParameterCorrectness:
    """Verify that tool contracts' required_params match the registered functions."""

    def test_workflow_tool_signatures_match_contracts(self):
        """For each workflow tool, verify required_params align with function signatures."""
        from akshare_mcp.tools.tool_catalog import TOOL_CONTRACTS

        # Read the ai_workflows source directly to avoid heavy import chains
        # (strategy_factory etc. may not be installed in test environments).
        ai_workflows_path = os.path.join(
            _SRC_ROOT, "akshare_mcp", "tools", "ai_workflows.py"
        )
        with open(ai_workflows_path, encoding="utf-8") as f:
            module_source = f.read()

        for tool_name in (
            "analyze_stock_workflow",
            "factor_candidate_workflow",
            "strategy_review_workflow",
            "prediction_diagnosis_workflow",
            "data_quality_workflow",
        ):
            contract = TOOL_CONTRACTS.get(tool_name)
            assert contract is not None, f"Contract missing for {tool_name}"
            required = contract.get("required_params", [])

            # Check the function signature is defined in source
            assert f"async def {tool_name}(" in module_source, \
                f"Function {tool_name} not found in ai_workflows.py source"

            # Extract the function's argument names from source via regex
            pattern = rf"async def {tool_name}\((.*?)\)"
            match = re.search(pattern, module_source, re.DOTALL)
            assert match, f"Could not parse signature for {tool_name}"
            sig_text = match.group(1)
            param_names = [
                p.strip().split(":")[0].strip().split("=")[0].strip()
                for p in sig_text.split(",")
                if p.strip() and p.strip() != "self"
            ]

            for req_param in required:
                assert req_param in param_names, \
                    f"Required param '{req_param}' not in {tool_name} signature: {param_names}"

    def test_input_schema_required_fields_are_consistent(self):
        """input_schema.required must be a subset of input_schema.properties."""
        from akshare_mcp.tools.tool_catalog import TOOL_CONTRACTS

        for tool_name, contract in TOOL_CONTRACTS.items():
            schema = contract.get("input_schema", {})
            properties = set(schema.get("properties", {}).keys())
            required = set(schema.get("required", []))
            extra = required - properties
            assert not extra, \
                f"Tool '{tool_name}' has required fields not in properties: {extra}"

    def test_contract_examples_have_arguments(self):
        """Every contract example must have a non-empty arguments dict."""
        from akshare_mcp.tools.tool_catalog import TOOL_CONTRACTS

        for tool_name, contract in TOOL_CONTRACTS.items():
            examples = contract.get("examples", [])
            assert len(examples) > 0, f"Tool '{tool_name}' has no examples"
            for idx, example in enumerate(examples):
                assert "arguments" in example, \
                    f"Tool '{tool_name}' example[{idx}] missing 'arguments'"
                assert isinstance(example["arguments"], dict), \
                    f"Tool '{tool_name}' example[{idx}].arguments is not a dict"


# ============================================================================
# Dimension 3: Safe-Mode Selection (side_effect inference)
# ============================================================================
class TestSafeModeSelection:
    """Verify that the side-effect inference logic correctly classifies actions."""

    def test_read_only_actions(self):
        """Read-only tools should infer side_effect.level = read_only."""
        from akshare_mcp.tools.manager_protocol import _infer_side_effect_level

        read_actions = [
            ("get_kline", "get"),
            ("quant_manager", "help"),
            ("search", "query"),
            ("valuation", "analyze"),
        ]
        for tool, action in read_actions:
            level = _infer_side_effect_level(tool, action)
            assert level == "read_only", \
                f"Expected read_only for {tool}:{action}, got {level}"

    def test_stateful_actions(self):
        """Stateful write actions should infer side_effect.level = stateful."""
        from akshare_mcp.tools.manager_protocol import _infer_side_effect_level

        write_actions = [
            ("quant_manager", "create"),
            ("strategy_manager", "update_metrics"),
            ("quant_manager", "register"),
            ("alerts_manager", "warmup"),
        ]
        for tool, action in write_actions:
            level = _infer_side_effect_level(tool, action)
            assert level == "stateful", \
                f"Expected stateful for {tool}:{action}, got {level}"

    def test_external_write_actions(self):
        """External write actions should infer side_effect.level = external_write."""
        from akshare_mcp.tools.manager_protocol import _infer_side_effect_level

        external_actions = [
            ("strategy_manager", "submit"),
            ("strategy_manager", "publish"),
            ("data_sync_manager", "sync"),
            ("quant_manager", "rebuild"),
        ]
        for tool, action in external_actions:
            level = _infer_side_effect_level(tool, action)
            assert level == "external_write", \
                f"Expected external_write for {tool}:{action}, got {level}"

    def test_trade_risk_actions(self):
        """Trade-risk actions should infer side_effect.level = trade_risk."""
        from akshare_mcp.tools.manager_protocol import _infer_side_effect_level

        risk_actions = [
            ("live_trading_manager", "submit_order"),
            ("live_trading_manager", "cancel_order"),
            ("trading", "place_order"),
        ]
        for tool, action in risk_actions:
            level = _infer_side_effect_level(tool, action)
            assert level == "trade_risk", \
                f"Expected trade_risk for {tool}:{action}, got {level}"

    def test_side_effect_meta_has_confirmation_policy(self):
        """build_side_effect_meta must include confirmation_policy and dry_run."""
        from akshare_mcp.tools.manager_protocol import build_side_effect_meta

        meta = build_side_effect_meta(tool_name="test_tool", action="create")
        assert "confirmation_policy" in meta, "Missing confirmation_policy"
        assert "dry_run" in meta, "Missing dry_run"
        assert "level" in meta
        assert "target" in meta
        assert "idempotent" in meta
        assert "confirmation_required" in meta

    def test_trade_risk_requires_explicit_confirmation(self):
        """trade_risk level must set confirmation_required=True, confirmation_policy=explicit_token_required."""
        from akshare_mcp.tools.manager_protocol import build_side_effect_meta

        meta = build_side_effect_meta(tool_name="live_trading", action="submit_order")
        assert meta["level"] == "trade_risk"
        assert meta["confirmation_required"] is True
        assert meta["confirmation_policy"] == "explicit_token_required"

    def test_read_only_is_idempotent(self):
        """read_only level must be idempotent."""
        from akshare_mcp.tools.manager_protocol import build_side_effect_meta

        meta = build_side_effect_meta(tool_name="search", action="query")
        assert meta["level"] == "read_only"
        assert meta["idempotent"] is True
        assert meta["confirmation_required"] is False

    def test_contracts_declare_correct_side_effect_levels(self):
        """Verify that workflow contracts declare consistent side-effect levels."""
        from akshare_mcp.tools.tool_catalog import TOOL_CONTRACTS

        level_choices = {"read_only", "stateful", "external_write", "trade_risk"}
        for tool_name, contract in TOOL_CONTRACTS.items():
            level = contract.get("side_effect", {}).get("level")
            assert level in level_choices, \
                f"Tool '{tool_name}' has invalid side_effect.level: {level}"


# ============================================================================
# Dimension 4: Degraded / Fallback Identification
# ============================================================================
class TestDegradedFallbackIdentification:
    """Verify that the unified envelope correctly surfaces degraded/fallback signals."""

    def test_ok_with_meta_includes_degraded_field(self):
        """ok_with_meta must always include meta.degraded."""
        import time
        from akshare_mcp.tools.manager_protocol import ok_with_meta

        result = ok_with_meta(
            {"test": True},
            tool_name="test_tool",
            action="read",
            started_at=time.perf_counter(),
        )
        assert result["success"] is True
        meta = result.get("meta", {})
        assert "degraded" in meta
        assert meta["degraded"] is False

    def test_ok_with_meta_degraded_true(self):
        """ok_with_meta with degraded=True must be reflected in meta."""
        import time
        from akshare_mcp.tools.manager_protocol import ok_with_meta

        result = ok_with_meta(
            {"test": True},
            tool_name="test_tool",
            action="read",
            started_at=time.perf_counter(),
            extra_meta={"degraded": True},
        )
        assert result["meta"]["degraded"] is True

    def test_fail_with_meta_includes_degraded_field(self):
        """fail_with_meta must always include meta.degraded."""
        import time
        from akshare_mcp.tools.manager_protocol import fail_with_meta

        result = fail_with_meta(
            "something failed",
            tool_name="test_tool",
            action="read",
            started_at=time.perf_counter(),
            error_code="INTERNAL_ERROR",
            extra_meta={"degraded": True},
        )
        assert result["success"] is False
        assert result["meta"]["degraded"] is True
        assert result.get("error_code") == "INTERNAL_ERROR"

    def test_envelope_quality_status_field(self):
        """ok_with_meta quality must default to status=not_provided when no quality extra given."""
        import time
        from akshare_mcp.tools.manager_protocol import ok_with_meta

        result = ok_with_meta(
            {},
            tool_name="test_tool",
            action="read",
            started_at=time.perf_counter(),
        )
        quality = result["meta"].get("quality", {})
        assert "status" in quality

    def test_envelope_quality_custom_status(self):
        """Passing custom quality status must override the default."""
        import time
        from akshare_mcp.tools.manager_protocol import ok_with_meta

        result = ok_with_meta(
            {},
            tool_name="test_tool",
            action="read",
            started_at=time.perf_counter(),
            extra_meta={"quality": {"status": "partial_failed", "brier_score": 0.12}},
        )
        quality = result["meta"]["quality"]
        assert quality["status"] == "partial_failed"
        assert quality["brier_score"] == 0.12

    def test_audit_event_id_present_in_envelope(self):
        """Every unified meta envelope must contain an audit_event_id."""
        import time
        from akshare_mcp.tools.manager_protocol import ok_with_meta

        result = ok_with_meta(
            {},
            tool_name="test_tool",
            action="create",
            started_at=time.perf_counter(),
        )
        meta = result["meta"]
        assert "audit_event_id" in meta
        assert meta["audit_event_id"].startswith("audit:")


# ============================================================================
# Dimension 5: Multi-Step Workflow Chaining
# ============================================================================
class TestMultiStepWorkflowChaining:
    """Verify that workflow tools produce chainable step/lineage structures."""

    def test_workflow_contracts_have_workflow_tag(self):
        """All 5 workflow tools must be tagged as 'workflow'."""
        from akshare_mcp.tools.tool_catalog import TOOL_CONTRACTS

        workflow_tools = [
            "analyze_stock_workflow",
            "factor_candidate_workflow",
            "strategy_review_workflow",
            "prediction_diagnosis_workflow",
            "data_quality_workflow",
        ]
        for name in workflow_tools:
            contract = TOOL_CONTRACTS.get(name)
            assert contract is not None, f"Contract missing for {name}"
            assert "workflow" in contract.get("tags", []), \
                f"Tool '{name}' missing 'workflow' tag"

    def test_envelope_has_lineage_structure(self):
        """ok_with_meta with lineage extra must produce meta.lineage dict."""
        import time
        from akshare_mcp.tools.manager_protocol import ok_with_meta

        result = ok_with_meta(
            {},
            tool_name="test_tool",
            action="run",
            started_at=time.perf_counter(),
            extra_meta={
                "lineage": {
                    "dataset_id": "ds_001",
                    "run_id": "run_001",
                    "artifact_id": "art_001",
                },
            },
        )
        lineage = result["meta"].get("lineage", {})
        assert lineage.get("dataset_id") == "ds_001"
        assert lineage.get("run_id") == "run_001"
        assert lineage.get("artifact_id") == "art_001"

    def test_envelope_source_chain_propagation(self):
        """Source chain must be preserved and accessible for multi-step tracing."""
        import time
        from akshare_mcp.tools.manager_protocol import ok_with_meta

        chain = ["workflow.factor_candidate", "manager.quant_manager", "service.llm"]
        result = ok_with_meta(
            {},
            tool_name="test_tool",
            action="run",
            started_at=time.perf_counter(),
            source_chain=chain,
        )
        assert result["meta"]["source_chain"] == chain

    def test_envelope_idempotency_key_propagation(self):
        """idempotency_key must be passed through correctly."""
        import time
        from akshare_mcp.tools.manager_protocol import ok_with_meta

        result = ok_with_meta(
            {},
            tool_name="test_tool",
            action="run",
            started_at=time.perf_counter(),
            extra_meta={"idempotency_key": "key_123"},
        )
        assert result["meta"]["idempotency_key"] == "key_123"

    def test_envelope_latency_ms_is_numeric(self):
        """latency_ms must be a non-negative number."""
        import time
        from akshare_mcp.tools.manager_protocol import ok_with_meta

        started = time.perf_counter()
        result = ok_with_meta(
            {},
            tool_name="test_tool",
            action="run",
            started_at=started,
        )
        latency = result["meta"]["latency_ms"]
        assert isinstance(latency, (int, float))
        assert latency >= 0

    def test_lineage_reference_keys_defined(self):
        """LINEAGE_REFERENCE_KEYS must include dataset, run, artifact, model, strategy, review IDs."""
        from akshare_mcp.tools.manager_protocol import LINEAGE_REFERENCE_KEYS

        required_keys = {
            "artifact_id", "dataset_id", "run_id",
            "model_id", "strategy_id", "review_id",
        }
        actual_keys = set(LINEAGE_REFERENCE_KEYS)
        missing = required_keys - actual_keys
        assert not missing, f"LINEAGE_REFERENCE_KEYS missing: {missing}"

    def test_lineage_auto_extraction_from_extra(self):
        """build_lineage_meta must auto-extract known reference keys from extra payload."""
        from akshare_mcp.tools.manager_protocol import build_lineage_meta

        extra = {
            "artifact_id": "art_x",
            "dataset_id": "ds_x",
            "run_id": "run_x",
            "strategy_id": "strat_x",
            "model_id": "mod_x",
        }
        lineage = build_lineage_meta(extra)
        assert lineage["artifact_id"] == "art_x"
        assert lineage["dataset_id"] == "ds_x"
        assert lineage["run_id"] == "run_x"
        assert lineage["strategy_id"] == "strat_x"
        assert lineage["model_id"] == "mod_x"


# ============================================================================
# Cross-cutting: Unified Envelope Contract
# ============================================================================
class TestUnifiedEnvelopeContract:
    """Verify the overall unified envelope contract shape."""

    def test_ok_envelope_shape(self):
        """ok_with_meta must return the exact envelope shape required by P0-3."""
        import time
        from akshare_mcp.tools.manager_protocol import ok_with_meta

        result = ok_with_meta(
            {"test": 1},
            tool_name="test_tool",
            action="read",
            started_at=time.perf_counter(),
            source_chain=["test"],
        )
        # Top-level keys
        assert result["success"] is True
        assert result["data"] == {"test": 1}
        assert result["error"] is None
        assert "source" in result
        assert "cached" in result
        assert "timestamp" in result

        # Meta keys
        meta = result["meta"]
        required_meta_keys = {
            "trace_id", "audit_event_id", "tool_version",
            "data_timestamp", "source_chain", "cached",
            "latency_ms", "quality", "side_effect",
            "lineage", "idempotency_key", "degraded",
        }
        missing = required_meta_keys - set(meta.keys())
        assert not missing, f"Envelope meta missing keys: {missing}"

    def test_fail_envelope_shape(self):
        """fail_with_meta must return the correct failure envelope."""
        import time
        from akshare_mcp.tools.manager_protocol import fail_with_meta

        result = fail_with_meta(
            "test error",
            tool_name="test_tool",
            action="write",
            started_at=time.perf_counter(),
            error_code="TEST_ERROR",
        )
        assert result["success"] is False
        assert result["data"] is None
        assert "test error" in result["error"]
        assert result["error_code"] == "TEST_ERROR"

        meta = result["meta"]
        assert "audit_event_id" in meta
        assert "side_effect" in meta
        assert meta["side_effect"]["level"] in {"read_only", "stateful", "external_write", "trade_risk"}

    def test_generate_audit_event_id_uniqueness(self):
        """generate_audit_event_id must produce unique IDs."""
        from akshare_mcp.tools.manager_protocol import generate_audit_event_id

        ids = {generate_audit_event_id("tool", "action") for _ in range(100)}
        assert len(ids) == 100, "audit_event_id collisions detected"

    def test_generate_audit_event_id_format(self):
        """audit_event_id must follow the pattern 'audit:{tool}:{action}:{ts}:{hex}'."""
        from akshare_mcp.tools.manager_protocol import generate_audit_event_id

        event_id = generate_audit_event_id("my_tool", "my_action")
        parts = event_id.split(":")
        assert parts[0] == "audit"
        assert parts[1] == "my_tool"
        assert parts[2] == "my_action"
        assert parts[3].isdigit()  # timestamp
        assert len(parts[4]) == 8  # hex suffix


# ============================================================================
# P1 Dimension 1: PIT Default (P1-1)
# ============================================================================
class TestPITDefault:
    """Verify PIT middleware and workflow as_of parameter integration."""

    def test_pit_middleware_create_context_none(self):
        """create_pit_context(None) must return a valid context without truncation."""
        from akshare_mcp.tools.pit_middleware import create_pit_context

        ctx = create_pit_context(None)
        assert ctx is not None
        assert ctx.as_of_datetime is not None

    def test_pit_middleware_create_context_date(self):
        """create_pit_context with a date string must parse correctly."""
        from akshare_mcp.tools.pit_middleware import create_pit_context

        ctx = create_pit_context("2025-12-31")
        assert "2025-12-31" in ctx.as_of_datetime.isoformat()

    def test_pit_middleware_build_meta_simple(self):
        """build_pit_meta_simple must produce standard PIT meta dict."""
        from akshare_mcp.tools.pit_middleware import build_pit_meta_simple

        meta = build_pit_meta_simple(None)
        assert "as_of" in meta
        assert "pit_passed" in meta
        assert meta["pit_passed"] is True

    def test_pit_middleware_build_meta_with_date(self):
        """build_pit_meta_simple with as_of date must include that date."""
        from akshare_mcp.tools.pit_middleware import build_pit_meta_simple

        meta = build_pit_meta_simple("2025-06-15")
        assert "2025-06-15" in meta["as_of"]

    def test_workflows_accept_as_of_parameter(self):
        """All 5 workflow functions must accept an as_of parameter."""
        ai_workflows_path = os.path.join(
            _SRC_ROOT, "akshare_mcp", "tools", "ai_workflows.py"
        )
        with open(ai_workflows_path, encoding="utf-8") as f:
            source = f.read()

        for workflow in (
            "analyze_stock_workflow",
            "factor_candidate_workflow",
            "strategy_review_workflow",
            "prediction_diagnosis_workflow",
            "data_quality_workflow",
        ):
            pattern = rf"async def {workflow}\("
            match = re.search(pattern, source)
            assert match, f"{workflow} not found"
            # Find the full signature
            brace_start = match.end()
            brace_end = source.find(") ->", brace_start)
            sig = source[brace_start:brace_end]
            assert "as_of" in sig, \
                f"Workflow '{workflow}' missing as_of parameter"

    def test_tool_catalog_as_of_in_schemas(self):
        """All 5 workflow tool contracts must declare as_of in input_schema."""
        from akshare_mcp.tools.tool_catalog import TOOL_CONTRACTS

        for name in (
            "analyze_stock_workflow",
            "factor_candidate_workflow",
            "strategy_review_workflow",
            "prediction_diagnosis_workflow",
            "data_quality_workflow",
        ):
            contract = TOOL_CONTRACTS.get(name)
            assert contract is not None, f"Contract missing: {name}"
            props = contract.get("input_schema", {}).get("properties", {})
            assert "as_of" in props, \
                f"Tool '{name}' input_schema missing as_of property"

    def test_envelope_pit_meta_schema(self):
        """Standard envelope output schema must include pit in meta properties."""
        from akshare_mcp.tools.tool_catalog import STANDARD_ENVELOPE_OUTPUT_SCHEMA

        meta_props = STANDARD_ENVELOPE_OUTPUT_SCHEMA["properties"]["meta"]["properties"]
        assert "pit" in meta_props, "Envelope meta schema missing 'pit' property"


# ============================================================================
# P1 Dimension 2: Unified Lineage (P1-2)
# ============================================================================
class TestUnifiedLineage:
    """Verify LineageContext and automatic lineage tracking in workflows."""

    def test_lineage_context_create(self):
        """LineageContext.create must generate a valid context with run_id."""
        from akshare_mcp.services.lineage_tracker import LineageContext

        ctx = LineageContext.create("test_workflow")
        assert ctx.run_id.startswith("test_workflow:")
        assert ctx.workflow == "test_workflow"
        assert ctx.parent_run_id is None

    def test_lineage_context_child(self):
        """child() must create a child context with parent linkage."""
        from akshare_mcp.services.lineage_tracker import LineageContext

        ctx = LineageContext.create("parent_workflow")
        child = ctx.child("step_one")
        assert child.parent_run_id == ctx.run_id
        assert child.workflow == "parent_workflow.step_one"
        assert child in ctx.children

    def test_lineage_context_to_meta(self):
        """to_meta() must serialize all non-None fields."""
        from akshare_mcp.services.lineage_tracker import LineageContext

        ctx = LineageContext.create("wf", dataset_id="ds_001", model_id="m_001")
        meta = ctx.to_meta()
        assert meta["run_id"] == ctx.run_id
        assert meta["workflow"] == "wf"
        assert meta["dataset_id"] == "ds_001"
        assert meta["model_id"] == "m_001"

    def test_lineage_context_child_runs_in_meta(self):
        """to_meta() must include child_runs when children exist."""
        from akshare_mcp.services.lineage_tracker import LineageContext

        ctx = LineageContext.create("wf")
        ctx.child("step_a")
        ctx.child("step_b")
        meta = ctx.to_meta()
        assert "child_runs" in meta
        assert len(meta["child_runs"]) == 2

    def test_lineage_set_artifact(self):
        """set_artifact must update artifact_id and reflect in to_meta."""
        from akshare_mcp.services.lineage_tracker import LineageContext

        ctx = LineageContext.create("wf")
        ctx.set_artifact("art_123")
        assert ctx.artifact_id == "art_123"
        assert ctx.to_meta()["artifact_id"] == "art_123"

    def test_lineage_reference_keys_include_p1_keys(self):
        """LINEAGE_REFERENCE_KEYS must include factor_candidate_id and promotion_review_id."""
        from akshare_mcp.tools.manager_protocol import LINEAGE_REFERENCE_KEYS

        assert "factor_candidate_id" in LINEAGE_REFERENCE_KEYS
        assert "promotion_review_id" in LINEAGE_REFERENCE_KEYS


# ============================================================================
# P1 Dimension 3: Uncertainty Contract (P1-3)
# ============================================================================
class TestUncertaintyContract:
    """Verify UncertaintyReport and build_uncertainty_report."""

    def test_uncertainty_report_creation(self):
        """build_uncertainty_report must return a valid UncertaintyReport."""
        from akshare_mcp.services.uncertainty_contract import build_uncertainty_report

        report = build_uncertainty_report(
            raw_probability=0.72,
            calibrated_probability=0.65,
            calibration_method="platt",
            sample_size=200,
        )
        assert report.raw_probability == 0.72
        assert report.calibrated_probability == 0.65
        assert report.calibration_method == "platt"
        assert report.calibration_sample_size == 200

    def test_uncertainty_report_to_dict(self):
        """to_dict must produce a serializable dict with required keys."""
        from akshare_mcp.services.uncertainty_contract import build_uncertainty_report

        report = build_uncertainty_report(
            raw_probability=0.5,
            calibration_method="raw",
            sample_size=50,
        )
        d = report.to_dict()
        assert "raw_probability" in d
        assert "calibration_method" in d
        assert "quality_band" in d
        assert "reliability_summary" in d

    def test_uncertainty_quality_band_unknown_when_no_metrics(self):
        """quality_band must be 'unknown' when no brier/ece provided."""
        from akshare_mcp.services.uncertainty_contract import build_uncertainty_report

        report = build_uncertainty_report(
            raw_probability=0.5,
            calibration_method="none",
            sample_size=0,
        )
        assert report.quality_band == "unknown"

    def test_uncertainty_warnings_for_uncalibrated(self):
        """Warnings must flag uncalibrated probabilities."""
        from akshare_mcp.services.uncertainty_contract import build_uncertainty_report

        report = build_uncertainty_report(
            raw_probability=0.5,
            calibration_method="none",
            sample_size=10,
        )
        warning_texts = " ".join(report.warnings)
        assert "未经校准" in warning_texts
        assert "样本量" in warning_texts

    def test_uncertainty_good_quality_band(self):
        """Good brier+ece+sample should produce quality_band=good."""
        from akshare_mcp.services.uncertainty_contract import build_uncertainty_report

        report = build_uncertainty_report(
            raw_probability=0.7,
            calibrated_probability=0.68,
            calibration_method="platt",
            sample_size=500,
            brier_score=0.03,
            ece=0.02,
        )
        assert report.quality_band == "good"


# ============================================================================
# P1 Dimension 4: Factor Enrichment (P1-4)
# ============================================================================
class TestFactorEnrichment:
    """Verify factor_enrichment.py enrichment scoring."""

    def test_factor_enrichment_report_creation(self):
        """build_factor_enrichment must produce a FactorEnrichmentReport."""
        from akshare_mcp.services.factor_enrichment import build_factor_enrichment

        report = build_factor_enrichment(
            expression="close / sma(close, 20) - 1",
            hypothesis="均线偏离度因子",
        )
        assert report.originality is not None
        assert report.complexity is not None
        assert report.crowding_proxy is not None
        assert report.hypothesis_alignment is not None

    def test_factor_enrichment_to_dict(self):
        """to_dict must include all enrichment dimensions."""
        from akshare_mcp.services.factor_enrichment import build_factor_enrichment

        report = build_factor_enrichment(
            expression="rank(ts_delta(close, 5))",
        )
        d = report.to_dict()
        assert "originality" in d
        assert "complexity" in d
        assert "crowding_proxy" in d
        assert "hypothesis_alignment" in d
        assert "validation_summary" in d
        assert "registry_status" in d
        assert "decay_monitor_status" in d

    def test_factor_complexity_scoring(self):
        """Complex expressions should score higher than simple ones."""
        from akshare_mcp.services.factor_enrichment import build_factor_enrichment

        simple = build_factor_enrichment(expression="close")
        complex_ = build_factor_enrichment(expression="rank(ts_delta(close, 5)) / std(close, 20) + sma(volume, 10)")
        assert complex_.complexity["score"] > simple.complexity["score"]

    def test_factor_originality_with_pool(self):
        """Factor similar to existing pool should have lower originality."""
        from akshare_mcp.services.factor_enrichment import build_factor_enrichment

        novel = build_factor_enrichment(
            expression="exotic_signal(x, y, z)",
            existing_pool=["sma_ratio_20", "momentum_10d"],
        )
        duplicate = build_factor_enrichment(
            expression="sma_ratio_20",
            existing_pool=["sma_ratio_20", "momentum_10d"],
        )
        assert novel.originality["score"] > duplicate.originality["score"]

    def test_factor_crowding_momentum_high(self):
        """Momentum-related factors should have high crowding proxy."""
        from akshare_mcp.services.factor_enrichment import build_factor_enrichment

        report = build_factor_enrichment(expression="pct_change(close, 20)")
        assert report.crowding_proxy["band"] in ("high", "medium")


# ============================================================================
# P1 Dimension 5: Execution Reality (P1-5)
# ============================================================================
class TestExecutionReality:
    """Verify execution_reality.py execution reality contract."""

    def test_execution_reality_report_backtest(self):
        """Backtest mode must produce appropriate warnings."""
        from akshare_mcp.services.execution_reality import build_execution_reality_report

        report = build_execution_reality_report(mode="backtest")
        assert report.cost_model_mode == "backtest"
        assert any("回测" in w for w in report.warnings)

    def test_execution_reality_report_to_dict(self):
        """to_dict must include all reality assumption fields."""
        from akshare_mcp.services.execution_reality import build_execution_reality_report

        report = build_execution_reality_report(mode="backtest")
        d = report.to_dict()
        assert "fill_model" in d
        assert "slippage_assumption" in d
        assert "market_impact_assumption" in d
        assert "commission_assumption" in d
        assert "liquidity_gate" in d
        assert "promotion_gate" in d
        assert "cost_model_mode" in d
        assert "total_cost_bps" in d

    def test_execution_reality_close_price_warning(self):
        """Close price fill model must trigger a warning."""
        from akshare_mcp.services.execution_reality import build_execution_reality_report

        report = build_execution_reality_report(mode="backtest", fill_model="close_price")
        assert any("收盘价" in w for w in report.warnings)

    def test_execution_reality_total_cost_non_negative(self):
        """total_cost_bps must be non-negative."""
        from akshare_mcp.services.execution_reality import build_execution_reality_report

        report = build_execution_reality_report(mode="execution")
        assert report.total_cost_bps >= 0

    def test_execution_reality_promotion_gate_defaults(self):
        """Default promotion gate must include min_sharpe_ratio."""
        from akshare_mcp.services.execution_reality import build_execution_reality_report

        report = build_execution_reality_report(mode="backtest")
        gate = report.promotion_gate
        assert "min_sharpe_ratio" in gate
        assert gate["min_sharpe_ratio"] > 0


# ============================================================================
# P2 Dimension 1: Governance Monitor Service (P2-2)
# ============================================================================
class TestGovernanceMonitor:
    """Verify governance_monitor.py logic."""

    def test_factor_decay_check(self):
        from akshare_mcp.services.governance_monitor import check_factor_decay

        # Need enough points so that recent mean (last 8) is worse than all-time mean
        # by more than the threshold (0.015).
        history = [0.1] * 20 + [0.01] * 8
        res = check_factor_decay("test_factor", history)
        assert res["decay_status"] in ("decaying", "decayed")
        assert res["rolling_ic_trend"] == "decaying"

    def test_crowding_check(self):
        from akshare_mcp.services.governance_monitor import check_crowding

        res = check_crowding("test_factor", expression="sma(volume_ratio)")
        assert res["crowding_score"] > 0

    def test_model_drift_check(self):
        from akshare_mcp.services.governance_monitor import check_model_drift

        res = check_model_drift(
            "test_model",
            {"brier_score": 0.15, "rank_ic_mean": 0.02},
            {"brier_score": 0.10, "rank_ic_mean": 0.05},
        )
        assert res["drift_status"] in ("degraded", "warning")
        assert "brier_score" in res["degraded_dimensions"]
        assert "rank_ic_mean" in res["degraded_dimensions"]

    def test_strategy_health_check(self):
        from akshare_mcp.services.governance_monitor import check_strategy_health

        res = check_strategy_health("test_strat", control_mode="halted", open_alert_count=2)
        assert res["health_status"] == "critical"

    def test_online_offline_consistency(self):
        from akshare_mcp.services.governance_monitor import check_online_offline_consistency

        res = check_online_offline_consistency(
            {"slippage_bps": 0.0}, {"slippage_bps": 5.0}
        )
        assert res["consistency_status"] in ("gap_detected", "inconsistent")

    def test_full_governance_check(self):
        from akshare_mcp.services.governance_monitor import default_governance_monitor
        
        report = default_governance_monitor.run_full_check(target_type="system")
        assert report.overall_status in ("healthy", "warning", "critical")
        assert isinstance(report.to_dict(), dict)


# ============================================================================
# P2 Dimension 2: Research Object Resources (P2-3)
# ============================================================================
class TestResearchObjectResources:
    """Verify resource templates for P2."""

    @pytest.mark.asyncio
    async def test_system_governance_report(self):
        from akshare_mcp.resources.research_objects import build_system_governance_payload
        
        res = await build_system_governance_payload()
        assert res["found"] is True
        assert "governance_report" in res


# ============================================================================
# P2 Dimension 3: Adapters (P2-1)
# ============================================================================
class TestAdapters:
    """Verify adapter fallbacks."""

    def test_conformal_adapter(self):
        from akshare_mcp.services.adapters.mapie_adapter import get_conformal_adapter
        adapter = get_conformal_adapter(prefer_mapie=False)
        res = adapter.predict_set([0.2, 0.8], [0, 1], [0.5])
        assert len(res.prediction_sets) == 1

    def test_experiment_tracker_adapter(self):
        from akshare_mcp.services.adapters.experiment_tracker_adapter import get_experiment_tracker
        tracker = get_experiment_tracker(prefer_mlflow=False)
        run_id = tracker.log_run("test_exp")
        assert run_id
        tracker.log_metric(run_id, "acc", 0.95)
        run = tracker.get_run(run_id)
        assert run["metrics"]["acc"] == 0.95

    def test_data_validation_adapter(self):
        from akshare_mcp.services.adapters.data_validation_adapter import get_data_validation_adapter
        adapter = get_data_validation_adapter(prefer_gx=False)
        res = adapter.validate_dataset(
            [{"a": 1}, {"a": 2}],
            {"min_record_count": 1}
        )
        assert res.passed is True
