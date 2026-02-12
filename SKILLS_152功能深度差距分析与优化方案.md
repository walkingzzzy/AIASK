# SKILLS 能力与 152 功能深度差距分析（含 TDX 交互）+ 优化方案

> 生成时间：2026-02-12  
> 分析范围：`/.codex/skills`（16 个 skills） vs 运行时工具（152 个）  
> 重点方向：顶级基金经理流程、量化研究深度、TDX 交互能力  
> 证据文件：`skill_tool_coverage_runtime.json`、`skill_tool_gap_list.txt`

---

## 1. 执行摘要

当前 Skills 体系与项目真实能力之间存在结构性断层：

- `152` 个运行时工具中，skills 仅覆盖 `68` 个，覆盖率 `44.74%`
- 未覆盖工具 `84` 个
- `TDX` 工具 `36` 个，skills 覆盖 `0` 个（核心短板）
- `Manager` 工具 `30` 个，skills 仅覆盖 `5` 个（`alerts/backtest/performance/portfolio/risk`）

这意味着：项目“工具层”已经很强，但“能力编排层（skills）”没有把现有能力组织成基金经理级、量化研究级、TDX 实盘协同级的工作流。

---

## 2. 量化现状（本地实测）

基于运行时注册工具（`akshare_mcp.server`）和 skills 文档自动比对：

| 指标 | 数值 |
|---|---:|
| 运行时工具总数 | 152 |
| Skills 数量 | 16 |
| Skills 联合覆盖工具数 | 68 |
| 联合覆盖率 | 44.74% |
| 未覆盖工具数 | 84 |
| TDX 工具总数 | 36 |
| TDX 被 Skills 覆盖数 | 0 |
| Manager 工具总数 | 30 |
| Manager 被 Skills 覆盖数 | 5 |

关键一致性问题：

- `akshare-asset-allocation`、`akshare-portfolio-manager-core` 引用了不存在的独立工具 `add_holding`（该能力实际在 `portfolio_manager` 的 `action=add_holding` 中）
- 多个 skills 仍是“单工具清单”，不是“多阶段决策流程”

---

## 3. 关键短板拆解

## 3.1 顶级基金经理能力短板

现有 `akshare-portfolio-manager-core` 只覆盖目标-构建-风险-复盘的最简链路，缺少：

- 合规闸门：`compliance_manager` 未进入流程
- 执行层：`execution_manager`（TWAP/VWAP）未纳入
- 研究与事件：`research_manager`、`event_manager` 未纳入
- 监控联动：`live_trading_manager`、`watchlist_manager` 未纳入
- 运营闭环：`user_manager`、`data_sync_manager`、`get_sync_status` 未纳入

结果：只能“给分析”，难形成“策略-执行-风控-复盘”的闭环生产流。

## 3.2 量化研究深度短板

虽然有 `akshare-quant`、`akshare-quant-research-process`，但缺少：

- 交易成本与冲击建模的标准入口（与回测默认参数解耦不清）
- Walk-forward / OOS 验证规范化流程（仅“建议”，非强制节点）
- 模型治理与文档留痕（版本、参数、数据快照、实验可复现）
- manager 化入口弱：`quant_manager`、`technical_analysis_manager`、`vector_search_manager` 未纳入技能流程

## 3.3 TDX 交互短板（最严重）

代码层已实现大量 TDX 工具，但 skills 层零覆盖，导致用户很难“自然调用”：

- 已实现工具族：行情订阅/刷新、公式计算、条件选股、交易数据、板块管理、文件推送、回测可视化推送
- 技术限制已在代码层考虑（能力降级、fallback、env_diag），但 skills 不会主动引导
- 运行日志显示 TDX 初始化失败会重试并降级（`tdx.py` 中有 retry + fallback），但无 skill 指导用户做“环境预检-能力探测-降级分流”

简言之：有武器库，没有作战手册。

---

## 4. 外部基线（深度联网检索结论）

本次检索使用了 TDX 官方、SEC、GIPS、IOSCO、QuantConnect、Backtrader、vn.py 等一手资料（见文末链接）。

关键基线：

- **TDX 官方**强调初始化、客户端登录、`PYPlugins/user` 路径、数据下载前置；并明确公式系统与实时订阅接口边界。
- **QuantConnect**采用 `Universe -> Alpha -> Portfolio -> Risk -> Execution` 的模块化流水线，并强调组件职责隔离（SoC）。
- **Backtrader**把滑点、佣金、信用利息作为显式可配置模型，便于回测一致性与敏感性分析。
- **SEC 206(4)-7**要求书面政策、年度审查、CCO 责任；合规流程必须制度化。
- **GIPS**强调公平披露和可比绩效展示（初始 5 年并逐年扩至 10 年）。
- **IOSCO 2025 流动性管理建议**强调基金设计、日常流动性、压力测试、治理与披露的完整框架。

推论：Skills 需要从“工具调用提示”升级为“可审计、可复盘、可执行、可降级”的标准流程。

---

## 5. 优化总方案（先方案）

## Phase 0（1 周）：建立能力治理底座

目标：让 skills 与工具注册清单自动对齐。

交付：

1. 新增 `scripts/skill_coverage_audit.py`  
   自动输出：
   - skills 覆盖率
   - 未覆盖工具清单
   - TDX 覆盖率
   - manager 覆盖率
2. 新增 `/.codex/skills/_meta/coverage_baseline.json`
3. 在 CI 增加阈值校验（例如覆盖率低于阈值则告警）

验收指标：

- 覆盖率报告自动生成
- skill 引用不存在工具时报错（如 `add_holding`）

---

## Phase 1（1-2 周）：先补最关键缺口（TDX + Manager）

目标：把“0 覆盖 TDX”先拉起来，并补齐基金经理主链缺失环节。

### 1) 新增 3 个 TDX 专项 Skills

- `akshare-tdx-runtime-ops`
  - 预检：`tdx_refresh_data` / `tdx_manage_subscription` / 环境诊断
  - 结果：可用能力矩阵（supported / degraded / unavailable）
- `akshare-tdx-formula-research`
  - `tdx_calculate_indicator` + `tdx_screen_stocks` + `tdx_get_expert_signals` + fallback 分流
- `akshare-tdx-front-sync`
  - `push_message` / `push_warn` / `send_backtest_result` / `send_backtest_trades` / `tdx_send_file`

### 2) 升级基金经理核心 Skill

升级 `akshare-portfolio-manager-core`：

- 增加前置合规：`compliance_manager`
- 增加执行层：`execution_manager`
- 增加事件与研究：`event_manager` + `research_manager`
- 增加监控：`live_trading_manager` + `watchlist_manager`

验收指标：

- TDX 覆盖率从 0 提升到至少 50%
- Manager 覆盖率从 5/30 提升到至少 12/30

---

## Phase 2（2-4 周）：量化研究深水区升级

目标：把量化技能从“指标查询”升级到“研究工厂”。

升级 `akshare-quant-research-process`：

1. 强制阶段化：
   - 数据质量门禁（缺失、异常、样本长度）
   - 因子有效性（IC + 稳定性）
   - 组合构建（约束 + 风险预算）
   - 回测（含成本参数）
   - OOS / 滚动验证
   - 压测与归因
2. 引入 manager 统一入口：
   - `quant_manager`、`technical_analysis_manager`、`vector_search_manager`
3. 引入“研究留痕”：
   - 参数、数据窗口、版本、结论统一输出模板

验收指标：

- 量化相关技能覆盖工具数提升 30%+
- 同一策略可输出可复现实验记录

---

## Phase 3（4-8 周）：基金经理闭环能力成型

目标：形成 “投研-组合-执行-风控-复盘-报告” 的标准作业流。

新增 `akshare-fund-manager-pro`（建议）：

- 资产配置（IPS 约束）
- 标的筛选（基本面/技术/资金流/事件）
- 组合构建（优化 + 风险预算）
- 执行（TWAP/VWAP）
- 合规检查
- TDX 前端联动（预警、可视化、文件报告）
- 绩效归因与再平衡建议

验收指标：

- 单 skill 完成端到端闭环
- 报告字段可满足审阅/复盘（策略、风险、执行、绩效、异常）

---

## 6. 重点 TDX 优化专项（建议并行）

除 Skills 之外，建议做 4 个专项增强：

1. **TDX 能力握手协议**
   - 每次调用前缓存 capability（init 状态、formula API、订阅 API）
   - 向上游 skill 输出标准能力描述，自动决定主路径或 fallback
2. **订阅桥接规范**
   - 由于 MCP 非长连接推流，统一采用“订阅 + 轮询快照 + 事件摘要”
3. **错误语义标准化**
   - 所有 TDX 工具统一 `capability`/`env_diag`/`guidance` 字段
4. **前端交互回归集**
   - 把 `TDX_FRONTEND_INTERACTIVE_TEST_PLAN.md` 转成可自动执行子集（至少 smoke）

---

## 7. 目标指标（建议）

| 指标 | 当前 | 目标（8 周） |
|---|---:|---:|
| Skills 联合覆盖率 | 44.74% | ≥ 80% |
| TDX 覆盖率 | 0/36 | ≥ 25/36 |
| Manager 覆盖率 | 5/30 | ≥ 20/30 |
| 不存在工具引用 | 2 处已发现 | 0 |
| TDX 主流程成功率（预检后） | 未统一统计 | ≥ 95% |

---

## 8. 优先级任务清单（可直接执行）

P0（立即）：

1. 修复 skills 中 `add_holding` 的错误引用（改为 `portfolio_manager(action=add_holding)` 语义）
2. 新增 TDX 三个专项 skills 骨架
3. 上线覆盖率审计脚本并纳入 CI

P1（两周内）：

1. 重写 `akshare-portfolio-manager-core` 为闭环流程
2. 重写 `akshare-quant-research-process` 为强制阶段流程
3. 给每个 skill 增加“失败分流策略”（fallback 与替代工具）

P2（一月内）：

1. 新增 `akshare-fund-manager-pro`（已完成，见 `/.codex/skills/akshare-fund-manager-pro/SKILL.md`）
2. 打通 TDX 前端联动场景模板（已完成，见 `/.codex/skills/akshare-tdx-front-sync/references/scenario_templates.md`）
3. 形成“日报/周报/月报”标准输出模板（已完成，见 `/.codex/skills/akshare-fund-manager-pro/assets/templates/`）

---

## 9. 主要参考来源（联网与本地）

### TDX 官方

- https://help.tdx.com.cn/quant/docs/markdown/mindoc-1cfsjkbf8f3is
- https://help.tdx.com.cn/quant/docs/markdown/README.html
- https://help.tdx.com.cn/quant/docs/markdown/mindoc-tdxpy.html
- https://help.tdx.com.cn/gspt/
- https://help.tdx.com.cn/gspt/docs/markdown/tdxgs-1d1r6mi4ue3q4/tdxgs-1d956se1r87eo.html

### 量化架构与执行仿真

- https://www.quantconnect.com/docs/v2/writing-algorithms/algorithm-framework/overview
- https://www.backtrader.com/docu/commission-schemes/commission-schemes/
- https://www.backtrader.com/docu/slippage/slippage/
- https://github.com/vnpy/vnpy

### 合规与治理基线

- https://www.sec.gov/file/rel-no-ia-2204
- https://www.sec.gov/files/rules/final/ia-2204.htm
- https://www.sec.gov/investment/private-fund-advisers
- https://www.gipsstandards.org/standards/gips-standards-for-firms/
- https://www.gipsstandards.org/standards/gips-standards-for-firms/gips-standards-handbook-for-firms/
- https://www.iosco.org/library/pubdocs/pdf/IOSCOPD798.pdf
- https://www.iosco.org/library/pubdocs/pdf/IOSCOPD799.pdf
- https://www.iosco.org/news/pdf/IOSCONEWS771.pdf

### 本地证据

- `skill_tool_coverage_runtime.json`
- `skill_tool_gap_list.txt`
- `packages/akshare-mcp/src/akshare_mcp/data_source/tdx.py`
- `packages/akshare-mcp/src/akshare_mcp/tools/tdx_realtime.py`
- `packages/akshare-mcp/src/akshare_mcp/tools/tdx_formula.py`
- `packages/akshare-mcp/src/akshare_mcp/tools/tdx_integration.py`

---

## 10. 结论

当前不是“功能不足”，而是“能力组织不足”。  
优先级应从“继续加工具”转为“重构 skills 编排层”，尤其是 TDX 交互与基金经理闭环流程。  
按本方案推进，可在不大改工具层代码的前提下，显著提升实际可用性、专业度与可复盘性。
