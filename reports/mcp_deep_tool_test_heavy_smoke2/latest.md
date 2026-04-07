# AKShare MCP 155 Tools Deep Conversational Functional Test

- Executed at: `2026-04-07T11:53:58+08:00`
- Runtime tool count: **9**
- Tools passed: **7**
- Tools failed: **2**
- Total cases: **27**
- Case pass rate: **85.19%**
- Average latency: **1121.0 ms**

## Input Audit

- `packages/akshare-mcp/TOOL_DOC_AUDIT_RAW.json`: missing
- Runtime registry fallback: `/Users/mac/Desktop/股票/reports/tool_registry/latest.json`
- Legacy results baseline: `/Users/mac/Desktop/股票/.mcp_full_test_results.json`

## Historical Comparison

- Fixed vs legacy: **0**
- Persistent failures: **1**
- Regressions: **1**

## Workflow Results

| Workflow | Status | Total Latency |
|----------|--------|---------------|
| `market_to_decision` | PASS | 2599 ms |
| `finance_to_comprehensive` | PASS | 36 ms |
| `text_to_unified_decision` | PASS | 2053 ms |

## Defects

| Severity | Tool | Case | Observed | Historical |
|----------|------|------|----------|------------|
| P1 | `get_market_news` | `primary` | quality_meta_not_observed; source_chain_not_observed; slow_response>10000ms | `ok` |
| P1 | `get_minute_kline` | `primary` | missing_envelope_keys:timestamp | `ok` |
| P1 | `get_minute_kline` | `variant` | missing_envelope_keys:timestamp | `ok` |
| P1 | `get_realtime_quote` | `bank_variant` | missing_envelope_keys:timestamp | `error` |
| P1 | `get_realtime_quote` | `primary` | missing_envelope_keys:timestamp | `error` |
| P2 | `analyze_research_report` | `primary` | quality_meta_not_observed; source_chain_not_observed | `ok` |
| P2 | `analyze_research_report` | `variant` | quality_meta_not_observed; source_chain_not_observed | `ok` |
| P2 | `get_market_news` | `variant` | quality_meta_not_observed; source_chain_not_observed | `ok` |
| P2 | `get_research_reports` | `primary` | quality_meta_not_observed; source_chain_not_observed | `ok` |
| P2 | `get_research_reports` | `variant` | quality_meta_not_observed; source_chain_not_observed | `ok` |
| P2 | `get_stock_news` | `primary` | quality_meta_not_observed; source_chain_not_observed | `ok` |
| P2 | `get_stock_news` | `variant` | quality_meta_not_observed; source_chain_not_observed | `ok` |
| P2 | `get_stock_research` | `primary` | quality_meta_not_observed; source_chain_not_observed | `ok` |
| P2 | `get_stock_research` | `variant` | quality_meta_not_observed; source_chain_not_observed | `ok` |
| P2 | `search_research` | `primary` | quality_meta_not_observed; source_chain_not_observed | `ok` |
| P2 | `search_research` | `variant` | quality_meta_not_observed; source_chain_not_observed | `ok` |
| P2 | `search_research_db` | `primary` | quality_meta_not_observed; source_chain_not_observed | `ok` |
| P2 | `search_research_db` | `variant` | quality_meta_not_observed; source_chain_not_observed | `ok` |

## Tool Matrix

| Tool | Category | Status | Quality Meta | Source Chain | Avg Latency | Historical |
|------|----------|--------|--------------|--------------|-------------|------------|
| `analyze_research_report` | `general` | `passed` | no | no | 0 ms | `ok` |
| `get_market_news` | `news` | `passed` | no | no | 6992 ms | `ok` |
| `get_minute_kline` | `market` | `failed` | yes | yes | 1780 ms | `ok` |
| `get_realtime_quote` | `market` | `failed` | yes | yes | 411 ms | `error` |
| `get_research_reports` | `news` | `passed` | no | no | 225 ms | `ok` |
| `get_stock_news` | `news` | `passed` | no | no | 158 ms | `ok` |
| `get_stock_research` | `news` | `passed` | no | no | 184 ms | `ok` |
| `search_research` | `news` | `passed` | no | no | 324 ms | `ok` |
| `search_research_db` | `general` | `passed` | no | no | 10 ms | `ok` |

## Detailed Defects

### P1 `get_market_news` / `primary`

- Category: `news`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/news/news_feed.py`
- Repro payload: `{"limit": 5}`
- Observed: `quality_meta_not_observed; source_chain_not_observed; slow_response>10000ms`

### P1 `get_minute_kline` / `primary`

- Category: `market`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/market/kline.py`
- Repro payload: `{"limit": 60, "period": "5m", "stock_code": "600519"}`
- Observed: `missing_envelope_keys:timestamp`

### P1 `get_minute_kline` / `variant`

- Category: `market`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/market/kline.py`
- Repro payload: `{"limit": 40, "period": "15m", "stock_code": "000001"}`
- Observed: `missing_envelope_keys:timestamp`

### P1 `get_realtime_quote` / `bank_variant`

- Category: `market`
- Historical status: `error`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/market/quote.py`
- Repro payload: `{"stock_code": "000001"}`
- Observed: `missing_envelope_keys:timestamp`

### P1 `get_realtime_quote` / `primary`

- Category: `market`
- Historical status: `error`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/market/quote.py`
- Repro payload: `{"stock_code": "600519"}`
- Observed: `missing_envelope_keys:timestamp`

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

### P2 `get_market_news` / `variant`

- Category: `news`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/news/news_feed.py`
- Repro payload: `{"limit": 8}`
- Observed: `quality_meta_not_observed; source_chain_not_observed`

### P2 `get_research_reports` / `primary`

- Category: `news`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/news/research.py`
- Repro payload: `{"limit": 3, "prefer_db": true, "stock_code": "600519"}`
- Observed: `quality_meta_not_observed; source_chain_not_observed`

### P2 `get_research_reports` / `variant`

- Category: `news`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/news/research.py`
- Repro payload: `{"limit": 2, "prefer_db": false, "symbol": "000001"}`
- Observed: `quality_meta_not_observed; source_chain_not_observed`

### P2 `get_stock_news` / `primary`

- Category: `news`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/news/news_feed.py`
- Repro payload: `{"limit": 5, "prefer_db": true, "stock_code": "600519"}`
- Observed: `quality_meta_not_observed; source_chain_not_observed`

### P2 `get_stock_news` / `variant`

- Category: `news`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/news/news_feed.py`
- Repro payload: `{"limit": 3, "prefer_db": false, "stock_code": "000001"}`
- Observed: `quality_meta_not_observed; source_chain_not_observed`

### P2 `get_stock_research` / `primary`

- Category: `news`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/news/research.py`
- Repro payload: `{"limit": 3, "stock_code": "600519"}`
- Observed: `quality_meta_not_observed; source_chain_not_observed`

### P2 `get_stock_research` / `variant`

- Category: `news`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/news/research.py`
- Repro payload: `{"limit": 2, "stock_code": "000001"}`
- Observed: `quality_meta_not_observed; source_chain_not_observed`

### P2 `search_research` / `primary`

- Category: `news`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/news/research.py`
- Repro payload: `{"days": 30, "stock_code": "600519"}`
- Observed: `quality_meta_not_observed; source_chain_not_observed`

### P2 `search_research` / `variant`

- Category: `news`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/news/research.py`
- Repro payload: `{"days": 15, "keyword": "白酒", "stock_code": "000858"}`
- Observed: `quality_meta_not_observed; source_chain_not_observed`

### P2 `search_research_db` / `primary`

- Category: `general`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/research.py`
- Repro payload: `{"days": 30, "stock_code": "600519"}`
- Observed: `quality_meta_not_observed; source_chain_not_observed`

### P2 `search_research_db` / `variant`

- Category: `general`
- Historical status: `ok`
- Implementation: `/Users/mac/Desktop/股票/packages/akshare-mcp/src/akshare_mcp/tools/research.py`
- Repro payload: `{"days": 15, "keyword": "白酒"}`
- Observed: `quality_meta_not_observed; source_chain_not_observed`

## Improvement Suggestions

1. Fix wrapper signature mismatches and missing helpers first. `unexpected keyword argument 'args'` and `NameError` issues are P0 because they block core read-only flows.
2. Unify alias normalization against runtime schema. Several legacy smoke failures came from `codes` vs `code`, `query` vs `keyword`, and missing default date arguments.
3. Standardize quality metadata across market, finance, technical, valuation, decision, and backtest tools. At minimum expose `source_chain` and quality/degraded state in one consistent location.
4. Expand workflow-safe stateful test fixtures. Tools such as `ai_workflow_artifact`, `performance_manager`, and strategy-related actions benefit from reusable setup artifacts instead of hard-coded nonexistent IDs.
5. Restore the missing audit artifact. The requested `TOOL_DOC_AUDIT_RAW.json` is absent, so runtime registry export is currently the only reliable source of truth.

