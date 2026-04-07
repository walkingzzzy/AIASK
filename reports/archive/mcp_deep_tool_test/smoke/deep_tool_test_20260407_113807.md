# AKShare MCP 155 Tools Deep Conversational Functional Test

- Executed at: `2026-04-07T11:38:19+08:00`
- Runtime tool count: **8**
- Tools passed: **6**
- Tools failed: **2**
- Total cases: **24**
- Case pass rate: **91.67%**
- Average latency: **263.8 ms**

## Input Audit

- `packages/akshare-mcp/TOOL_DOC_AUDIT_RAW.json`: missing
- Runtime registry fallback: `/Users/mac/Desktop/股票/reports/tool_registry/latest.json`
- Legacy results baseline: `/Users/mac/Desktop/股票/.mcp_full_test_results.json`

## Historical Comparison

- Fixed vs legacy: **2**
- Persistent failures: **0**
- Regressions: **2**

## Workflow Results

| Workflow | Status | Total Latency |
|----------|--------|---------------|
| `market_to_decision` | PASS | 2653 ms |
| `finance_to_comprehensive` | PASS | 11 ms |
| `text_to_unified_decision` | PASS | 2025 ms |

## Defects

| Severity | Tool | Case | Observed | Historical |
|----------|------|------|----------|------------|
| P1 | `analyze_portfolio_risk` | `variant` | weights 数量必须与 codes 一致 | `ok` |
| P2 | `alerts_manager` | `create_indicator` | quality_meta_not_observed; source_chain_not_observed | `ok` |
| P2 | `alerts_manager` | `list_active` | quality_meta_not_observed; source_chain_not_observed | `ok` |
| P2 | `analyze_portfolio_risk_barra` | `missing_required` | Error executing tool analyze_portfolio_risk_barra: 1 validation error for analyze_portfolio_risk_barraArguments
holdings | `ok` |
| P2 | `analyze_research_report` | `missing_required` | unexpected_behavior | `ok` |
| P2 | `analyze_research_report` | `primary` | quality_meta_not_observed; source_chain_not_observed | `ok` |
| P2 | `analyze_research_report` | `variant` | quality_meta_not_observed; source_chain_not_observed | `ok` |
| P2 | `analyze_stock_workflow` | `missing_code` | Error executing tool analyze_stock_workflow: 1 validation error for analyze_stock_workflowArguments
code
  Field require | `failed` |

## Tool Matrix

| Tool | Category | Status | Quality Meta | Source Chain | Avg Latency | Historical |
|------|----------|--------|--------------|--------------|-------------|------------|
| `ai_workflow_artifact` | `general` | `passed` | yes | yes | 0 ms | `failed` |
| `alerts_manager` | `alerts` | `passed` | no | no | 1 ms | `ok` |
| `analyze_portfolio_risk` | `portfolio` | `failed` | yes | yes | 36 ms | `ok` |
| `analyze_portfolio_risk_barra` | `portfolio` | `passed` | yes | yes | 14 ms | `ok` |
| `analyze_research_report` | `general` | `failed` | no | no | 1 ms | `ok` |
| `analyze_stock_sentiment` | `sentiment` | `passed` | yes | no | 16 ms | `ok` |
| `analyze_stock_workflow` | `general` | `passed` | yes | yes | 2034 ms | `failed` |
| `available_tools` | `search` | `passed` | yes | yes | 7 ms | `ok` |

## Detailed Defects

### P1 `analyze_portfolio_risk` / `variant`

- Category: `portfolio`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/portfolio.py`
- Repro payload: `{"codes": ["300750", "688981", "002415"], "weights": [1.0]}`
- Observed: `weights 数量必须与 codes 一致`

### P2 `alerts_manager` / `create_indicator`

- Category: `alerts`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/managers/alerts_manager.py`
- Repro payload: `{"action": "create", "code": "600519", "condition": ">", "indicator": "rsi", "user_id": "deep_user_20260407_113807", "value": 70}`
- Observed: `quality_meta_not_observed; source_chain_not_observed`

### P2 `alerts_manager` / `list_active`

- Category: `alerts`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/managers/alerts_manager.py`
- Repro payload: `{"action": "list", "status": "active", "user_id": "deep_user_20260407_113807"}`
- Observed: `quality_meta_not_observed; source_chain_not_observed`

### P2 `analyze_portfolio_risk_barra` / `missing_required`

- Category: `portfolio`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/portfolio.py`
- Repro payload: `{}`
- Observed: `Error executing tool analyze_portfolio_risk_barra: 1 validation error for analyze_portfolio_risk_barraArguments
holdings
  Field required [type=missing, input_value={}, input_type=dict]
    For further information visit https://errors.pydantic.dev/2.12/v/missing`

### P2 `analyze_research_report` / `missing_required`

- Category: `general`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/research.py`
- Repro payload: `{"code": ""}`
- Observed: `unexpected_behavior`

### P2 `analyze_research_report` / `primary`

- Category: `general`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/research.py`
- Repro payload: `{"code": "600519"}`
- Observed: `quality_meta_not_observed; source_chain_not_observed`

### P2 `analyze_research_report` / `variant`

- Category: `general`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/research.py`
- Repro payload: `{"code": "000001"}`
- Observed: `quality_meta_not_observed; source_chain_not_observed`

### P2 `analyze_stock_workflow` / `missing_code`

- Category: `general`
- Historical status: `failed`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/ai_workflows.py`
- Repro payload: `{}`
- Observed: `Error executing tool analyze_stock_workflow: 1 validation error for analyze_stock_workflowArguments
code
  Field required [type=missing, input_value={}, input_type=dict]
    For further information visit https://errors.pydantic.dev/2.12/v/missing`

## Improvement Suggestions

1. Fix wrapper signature mismatches and missing helpers first. `unexpected keyword argument 'args'` and `NameError` issues are P0 because they block core read-only flows.
2. Unify alias normalization against runtime schema. Several legacy smoke failures came from `codes` vs `code`, `query` vs `keyword`, and missing default date arguments.
3. Standardize quality metadata across market, finance, technical, valuation, decision, and backtest tools. At minimum expose `source_chain` and quality/degraded state in one consistent location.
4. Expand workflow-safe stateful test fixtures. Tools such as `ai_workflow_artifact`, `performance_manager`, and strategy-related actions benefit from reusable setup artifacts instead of hard-coded nonexistent IDs.
5. Restore the missing audit artifact. The requested `TOOL_DOC_AUDIT_RAW.json` is absent, so runtime registry export is currently the only reliable source of truth.

