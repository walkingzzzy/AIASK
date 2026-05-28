# S22 · 收尾/163 工具回归

- **判定**: ⚠️ 通过 (Pass=2 / Degraded=1 / Fail=0)

| 工具 | 状态 | 关键发现 |
|---|---|---|
| `get_available_categories()` | ✅ Pass | **33 个分类与 S01 完全一致**(alerts/backtest/basic_data/compliance/data_sync/decision/execution/factor/finance/fund_flow/general/industry_chain/macro/market/news/options/paper_trading/performance/portfolio/quant/research/risk/screening/search/sector/semantic/sentiment/skills/strategy/technical/user/vector/watchlist) |
| `get_index_quote(000001)` | ⚠️ Degraded | **§4.5.1 GBK 乱码 ???? 与 S02 一致复现** — name="????" / price=null,3 个 fallback 全跪:eastmoney_index_single empty / eastmoney_index失败:未获取到指数行情 / tushare_index_daily失败:您的token不对。quality_flags=[degraded, empty_upstream, fallback] 显式 |
| `available_tools(include_contracts=false)` | ✅ Pass | **163 工具完全锚定 S01 基线**(v1 161 + valuation_consensus + decision_consensus 两个 meta-tool),quality.tool_count=163 / contract_coverage=0.0 |

## v1 → v2 Delta
- ✅ 锚点完美回归:tool_count=163 / categories=33
- ⚠️ §4.5.1 GBK 乱码 ???? 在 fallback chain 全跪场景仍间歇性复现(politics 性 — 上游 sina/eastmoney/tushare 无 token 时编码无法 detect)
