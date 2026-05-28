# S10 · 期权/可转债

- **判定**: ✅ 通过 (Pass=2 / Degraded=2 / Fail-graceful=1 / Fail=0)

| 工具 | 状态 | 关键发现 |
|---|---|---|
| `options_manager(calculate_greeks)` | ✅ Pass | delta=0.9522 / gamma=0.2843 / theta=-0.0004/天 / vega=0.0017 / rho=0.0070,T=0.25y / σ=20%,interpretation 中文解读完整 |
| `get_cb_info(123039)` | 🟡 Fail-graceful | data.cb_info={}, source=none, fallback_reason="tdx_only_mode", **tqcenter 不可用且未启用旧降级**(护栏正确生效),latency=6025ms |
| `get_stock_capital(600519)` | ✅ Pass | tqcenter 1 条:ltgb=zgb=1252270208 股(12.5 亿),Date=20260526 实时 |
| `get_option_chain(510050)` | ⚠️ Degraded | options=[] expiryMonths=[],fallback_reason="akshare options provider unavailable: option_sse_list_sina, option_sse_codes_sina, option_sse_spot_price_sina, option_sse_underlying_spot_price_sina"。**provider_contract.v1 完整暴露** + quality_gate report_only(2 warning:freshness_sla / multi_source_reconciliation) + provider_status diagnostic 4 sources 全 available=true 但实际返回空,reconciliation mismatch 显式 |
| `get_ipo_info()` | ⚠️ Degraded | 1 条 IPO(SGCode=301669, SGDate=20260529)但 code/name/SGPrice/MaxSG/PE_Issue 全空,source=tqcenter 数据完整性问题(non-blocking) |

## v1 → v2 Delta
- ✅ options_manager.calculate_greeks 5 大希腊字母 + 中文 interpretation 输出稳定
- ✅ get_cb_info **tdx_only_mode 护栏完美**(tdx_local_only=1 时正确拒绝外部 fallback)
- ⚠️ get_option_chain provider_contract.v1 / quality_gate / provider_status 三层 envelope 完整(v1 仅基础 fallback_reason),透明度大幅提升
- ⚠️ get_ipo_info tqcenter 数据本身字段缺失(non-blocking,数据源问题)
- ✅ get_stock_capital tqcenter 直连 OK
