## 方案条目到实现映射
生成时间：2026-03-06
来源：`docs/plans/MCP服务预测能力增强优化方案.md`

### 1. 映射范围
本表聚焦本轮“方案缺失补齐”和随后完成的 skill 覆盖修复，覆盖：
- Phase 2：因子画像工具
- Phase 3：条件概率/条件收益工具
- Phase 4：决策工具重构为数据汇聚模式
- Phase 5：文本数据增强与市场情绪上下文
- Phase 6：回测高级指标扩展
- skill/tool 覆盖审计门禁修复

### 2. 实现映射表
| 方案条目 | 方案依据 | 实现文件 | 测试文件 | 本地验证 | 状态 |
|---|---|---|---|---|---|
| 因子画像工具 `get_factor_profile` | Phase 2；方案 4.1、5.1 | `packages/akshare-mcp/src/akshare_mcp/tools/factor_profile.py` | `packages/akshare-mcp/tests/test_prediction_enhancement.py` | `pytest -o addopts='' packages/akshare-mcp/tests/test_prediction_enhancement.py -q` | 已存在并纳入验收 |
| 条件收益/条件概率工具 `get_conditional_returns` | 方案 4.2；“历史统计 > 硬编码规则” | `packages/akshare-mcp/src/akshare_mcp/tools/quant.py`；`packages/akshare-mcp/src/akshare_mcp/services/conditional_returns.py` | `packages/akshare-mcp/tests/test_prediction_enhancement.py` | 同上，`41 passed` | 本轮新增并完成 |
| 投资分析数据汇聚 `get_investment_analysis` | 方案 4.5.2；决策工具从硬编码评分转为数据汇聚 | `packages/akshare-mcp/src/akshare_mcp/tools/decision.py` | `packages/akshare-mcp/tests/test_prediction_enhancement.py` | 同上，`41 passed` | 本轮补齐并暴露为 MCP 工具 |
| `should_i_buy / should_i_sell` context-first 化 | 问题 #2；方案 4.5.2 | `packages/akshare-mcp/src/akshare_mcp/tools/decision.py` | `packages/akshare-mcp/tests/test_prediction_enhancement.py`；`packages/akshare-mcp/tests/test_p0_regressions.py` | `41 passed`；`2 passed` | 本轮完成；输出含 `analysis_context`、`score_breakdown`、`signal_breakdown` |
| 文本增强 `get_stock_text_signals` | 方案 4.3；“原始文本 > 词袋模型” | `packages/akshare-mcp/src/akshare_mcp/tools/sentiment.py` | `packages/akshare-mcp/tests/test_prediction_enhancement.py` | `41 passed` | 本轮新增并完成 |
| 市场情绪上下文 `get_market_sentiment_context` | 方案 4.3；市场级情绪上下文聚合 | `packages/akshare-mcp/src/akshare_mcp/tools/sentiment.py` | `packages/akshare-mcp/tests/test_prediction_enhancement.py` | `41 passed` | 本轮新增并完成 |
| 回测高级指标与基准对比 | 方案 4.4.3；更多绩效指标、基准对比、Sharpe 修正方向 | `packages/akshare-mcp/src/akshare_mcp/services/backtest/engine.py`；`packages/akshare-mcp/docs/metrics-contract.md` | `packages/akshare-mcp/tests/test_backtest_baselines.py` | `pytest -o addopts='' packages/akshare-mcp/tests/test_backtest_baselines.py -q` → `19 passed` | 本轮完成 |
| Barra 风险分解工具纳入 skill 审计 | 方案 4.5.1；Barra 自动化 | `packages/akshare-mcp/src/akshare_mcp/tools/portfolio.py`；`.codex/skills/akshare-portfolio/SKILL.md`；`.codex/skills/akshare-portfolio-manager-core/SKILL.md` | 以 skill 审计为主 | `python scripts/skill_coverage_audit.py --check-thresholds` | 既有工具已纳入门禁 |
| 用户画像 / 推荐审计工具纳入 skill 审计 | 审计门禁补齐 | `packages/akshare-mcp/src/akshare_mcp/tools/sentiment.py`；`.codex/skills/akshare-portfolio-manager-core/SKILL.md`；`.codex/skills/akshare-investor-protection/SKILL.md` | 以 skill 审计为主 | 同上 | 本轮纳入门禁 |
| `strategy_manager` 纳入 skill 审计 | 方案 4.6.3；策略生命周期治理 | `packages/akshare-mcp/src/akshare_mcp/tools/managers/strategy_manager.py`；`.codex/skills/akshare-fund-manager-pro/SKILL.md` | 以 skill 审计为主 | 同上 | 本轮纳入门禁 |
| `managers` 模块命名冲突清理 | 仓库级审计收尾 | 删除 `packages/akshare-mcp/src/akshare_mcp/tools/managers.py`，保留 `packages/akshare-mcp/src/akshare_mcp/tools/managers/` | `packages/akshare-mcp/tests/test_tool_contract_check.py`；导入校验；skill 审计 | `8 passed`；`server_import_ok True`；`collisions=0` | 本轮完成 |

### 3. 关键验证结果
- `pytest -o addopts='' packages/akshare-mcp/tests/test_prediction_enhancement.py -q` → `41 passed`
- `pytest -o addopts='' packages/akshare-mcp/tests/test_backtest_baselines.py -q` → `19 passed`
- `pytest -o addopts='' packages/akshare-mcp/tests/test_tool_contract_check.py -q` → `8 passed`
- `pytest -o addopts='' packages/akshare-mcp/tests/test_p0_regressions.py -q -k 'should_i_buy_industry_median_pe_path or should_i_buy_pe_expansion_fallback_when_peers_insufficient'` → `2 passed`
- `python scripts/skill_coverage_audit.py --check-thresholds` → `coverage=100.0%`, `missing=0`, `tdx=36/36`, `manager=32/32`

### 4. 当前残余事项
1. `should_i_buy / should_i_sell` 仍保留少量启发式阈值，但已不再是纯黑盒评分。
2. 方案中的更大范围事项（如离线预计算仓库、重型风险模型增强、完整历史形态匹配）不在本轮补齐范围内。

### 5. 结论
对“方案缺失部分”的补齐与验收留痕已完成：
- 功能缺口已补齐
- 测试与文档已同步
- skill/tool 覆盖审计已恢复到 100%
- 当前可进入后续优化阶段，而非缺口修补阶段

