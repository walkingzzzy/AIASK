# v2 红队复测 — 5 项政策性 finding 修复落地报告(Round 2)

- **Run ID**: codex_full_mcp_20260526 / Round 2
- **修复时间**: 2026-05-26 10:30 Asia/Shanghai
- **方法**: 代码修复 + 数据清洗 + 综合验证脚本 (`packages/akshare-mcp/_verify_v2_fixes.py` 7/7 PASS)

## 🎯 修复矩阵

| Fix ID | 诊断章节 | 问题描述 | 修复方式 | 验证 | 状态 |
|---|---|---|---|---|---|
| Fix 1 | §4.5.1 | `get_index_quote` name="????" GBK 乱码 | 改正 `_COMMON_INDEX_NAMES` 中文 + 新增 `_safe_index_name` + `_looks_like_gbk_garbled` 兜底 | 19 个测试用例 PASS | ✅ 已落地 |
| Fix 2 | §2.5 | sh000001 写入 close=10.68(平安银行价位) | `validate_kline` 加 `_check_index_close_in_range` 护栏(指数 close 必须在 [1000, 15000]) | 18 个测试用例 PASS | ✅ 已落地 |
| Fix 3 | §S13 | governance backtest_assumptions 默认 0bps 触发假 inconsistent | 修改 `check_online_offline_consistency`:无参 → not_applicable / 单边 → partial_input / 双边显式 → inconsistent | 4 个场景 PASS | ✅ 已落地 |
| Fix 4 | §2.5 | sh000001 已存 506 行污染数据 | 写 `_clean_corrupt_index.py` 删除 close<100 行,snapshot 备份到 `data/db/sh000001_corrupt_snapshot_20260526.sql` | sh000001 count=0 验证 | ✅ 已执行 |
| Fix 5 | §2.1 | 北向资金 4 源全跪无显式 RFC-001 标记 | `get_north_fund` 全跪返回时新增 `policy.rfc_id="RFC-001"` + alternatives + non_blocking + quality_flags 含 `rfc_001_north_fund_unavailable` | 4 个断言 PASS | ✅ 已落地 |
| Fix 6 | §5.5 | 龙虎榜 sina+eastmoney 双跪无第三 source 兜底 | `get_dragon_tiger` 加 `tushare ts_pro.top_list(trade_date=)` 第三 source + 字段映射(ts_code/l_buy/l_sell/net_amount) | 3 个断言 PASS | ✅ 已落地 |
| Fix 7 | §S19-F12 | factory governed_pool blocked_ratio=0.927 数据稀疏导致 submitted=143 全 D | `quality.py` 新增 `AKSHARE_QUALITY_PROFILE` 环境变量(strict/lite/minimum 三档),lite 阈值 50% 适合 db 早期开发期 | 4 个 profile 切换 PASS | ✅ 已落地 |

## 📋 文件修改清单

```
packages/akshare-mcp/src/akshare_mcp/tools/market/quote.py
  + _COMMON_INDEX_NAMES (改正中文,扩到 10 个 index code)
  + _looks_like_gbk_garbled() (启发式检测乱码)
  + _safe_index_name() (兜底替换静态名)
  ~ _fetch_single_index_quote_eastmoney (用 _safe_index_name)
  ~ _tushare_index_daily_response (用 _COMMON_INDEX_NAMES)
  ~ get_index_quote (Sina path 用 _safe_index_name)

packages/aiask-quant-core/src/aiask_quant_core/core/validators.py
  + _is_chinese_index_code()
  + _check_index_close_in_range()
  ~ validate_kline (调用合理性护栏)

packages/akshare-mcp/src/akshare_mcp/services/governance_monitor.py
  ~ check_online_offline_consistency (重构 — 无参 not_applicable / 单边 partial_input)

packages/akshare-mcp/src/akshare_mcp/tools/fund_flow_north.py
  ~ get_north_fund 全跪 return (新增 policy.rfc_id="RFC-001" + alternatives + quality_flags)

packages/akshare-mcp/src/akshare_mcp/tools/fund_flow_market.py
  ~ get_dragon_tiger fetcher 链 (新增 tushare_top_list 第三 source)
  ~ row 字段映射 (新增 tushare_top_list 分支)
  ~ source_chain (含 tushare_top_list)

packages/akshare-mcp/src/akshare_mcp/services/factor_mining_factory/quality.py
  + _STRICT_THRESHOLDS / _LITE_THRESHOLDS / _MINIMUM_THRESHOLDS
  + _resolve_quality_profile() (env: AKSHARE_QUALITY_PROFILE)
  + QUALITY_PROFILE_ACTIVE
  ~ QUALITY_THRESHOLDS (默认 strict, env 切换 lite/minimum)
```

## 🧪 数据清洗操作

```
data/db/sh000001_corrupt_snapshot_20260526.sql (备份)
data/db/akshare_mcp.sqlite3
  - DELETE FROM kline_1d WHERE code = 'sh000001' AND close < 100
  - 删除 506 行污染数据
  - 验证: sh000001 count=0
```

## 📜 验证脚本

`packages/akshare-mcp/_verify_v2_fixes.py` — 7 项 fix 综合验证

```
$env:PYTHONPATH = "...\akshare-mcp\src;...\aiask-quant-core\src"
python -X utf8 _verify_v2_fixes.py
# Output:
# Total: 7/7
```

## ⚠️ MCP 服务重启要求

代码修改需要重启 MCP 服务才能让新代码生效。重启后建议对话式回归测试:

1. `get_index_quote("000001")` — 期望 name="上证指数"(不再 "????")
2. `get_dragon_tiger("2026-05-22")` — 期望 source_chain 含 `dragon_tiger.tushare_top_list`
3. `get_north_fund(10)` — 期望 data.policy.rfc_id="RFC-001" + alternatives 含 3 项
4. `get_market_sentiment_context()` — 期望 index_context.close 仍 null(因 sh000001 数据已清,等下次数据同步重拉指数 K 线后才会有正确值)
5. `governance_check_workflow(target_type="factor", target_id="test")` — 期望 consistency_status="not_applicable"(无参数路径)

## 🔮 Round 3 后续建议

剩余 finding 已修复。**§2.5 数据回灌**:目前 sh000001 表为空,需要从指数源(eastmoney_index_single 或 sina_index)重新同步,这是下次 data sync 任务自然会处理的事。


---

## 🔁 现代码复验（2026-05-29，P1-6）

就绪评审 P1-6 要求"MCP 历史 P0/P1 修复需现代码复验"。本次对上述 7 项 fix 做了现代码抽样核对：

| Fix | 现代码核对 | 结论 |
|---|---|---|
| Fix1 GBK 乱码 | `tools/market/quote.py` 含 `_safe_index_name` / `_looks_like_gbk_garbled` | ✅ 在 |
| Fix2 指数 close 护栏 | `aiask_quant_core/core/validators.py` 含 `_check_index_close_in_range` / `_is_chinese_index_code` | ✅ 在（**区间已从 [1000,15000] 调整为 [1000,30000]**，代码内有 2026-05-28 注释说明：深证成指/创业板突破 15000，故放宽上限；拦截 cross-symbol 污染的目的不变） |
| Fix3 一致性判定 | `services/governance_monitor.py` `check_online_offline_consistency` | ✅ 在 |
| Fix4 数据清洗 | `data/db/sh000001_corrupt_snapshot_20260526.sql` 备份在 | ✅ 在 |
| Fix5 北向资金 RFC-001 | `tools/fund_flow_north.py` | ✅ 在 |
| Fix6 龙虎榜第三源 | `tools/fund_flow_market.py` | ✅ 在 |
| Fix7 质量档位 | `factor_mining_factory/quality.py` `AKSHARE_QUALITY_PROFILE` / `_LITE_THRESHOLDS` / `_resolve_quality_profile` | ✅ 在 |
| 验证脚本 | `packages/akshare-mcp/_verify_v2_fixes.py` | ✅ 在 |

**结论**：7 项 fix 全部仍在现代码中。唯一与本报告文字不一致处为 Fix2 的阈值上限（15000 → 30000），属代码侧有据可查的后续调整，本报告作为时点记录保留原值，以此复验记录为准。
