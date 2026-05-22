# 金融系统级 Agent 优化方案

> 编制日期：2026-05-16
> 基线版本：AIASK Agent + Hermes v0.14.0 能力对等
> 目标：从当前"金融专业 Agent"升级为完整的"金融系统级 Agent"

---

## 一、系统级 Agent 定义与行业标准

### 1.1 什么是系统级 AI Agent

系统级 AI（System-Level AI）是 Salesforce AI Research 于 2025 年提出的概念，
标志着 AI 从"模型级"向"系统级"的范式转变。核心区别：

| 维度 | 模型级 AI | 系统级 AI |
|------|-----------|-----------|
| 架构 | 单一 LLM + Prompt | 多组件协调系统 |
| 记忆 | 无状态/短上下文 | 短期 + 长期 + 工作记忆 |
| 推理 | System 1（快速反应） | System 2（深度规划 + 反思） |
| 执行 | 单步工具调用 | 多步工作流编排 |
| 学习 | 静态权重 | 持续反馈闭环 |
| 协作 | 单体 | 多 Agent 协调 |
| 治理 | 无 | 权限/审计/人类监督 |

系统级 Agent 的五大支柱（综合 Salesforce、MIT Sloan、Google Cloud 定义）：

1. **记忆架构**：支持连续性的多层记忆系统
2. **推理模块**：处理复杂逻辑的深度推理引擎
3. **仿真环境**：持续改进性能的模拟与反馈
4. **多模态能力**：理解文本、图像、视频和空间推理
5. **编排层**：协调所有组件的统一调度


### 1.2 金融行业系统级 Agent 的定义

金融系统级 Agent 是能够**自主执行多步骤金融工作流**的 AI 系统，
在明确的目标和约束下与内部数据库、外部数据源和功能性 API 交互，
做出决策并执行操作。

**监管视角（FINRA 2026 年度监管报告）：**

FINRA 明确区分了传统 GenAI 工具（搜索/摘要/起草）和"能够发起并完成
多步骤操作任务的新型系统"。对金融 Agent 的核心要求：

- 所有自主决策必须有人类可审计的完整记录
- Agent 不能执行本应由注册人员监督、记录或验证的步骤
- 必须有文档化的风险管理程序
- 监督程序（WSP）必须覆盖 AI Agent 的全部行为

**行业实践视角（McKinsey、Google Cloud、CFA Institute）：**

金融系统级 Agent 的典型应用场景：

| 场景 | 能力要求 | 价值 |
|------|----------|------|
| 量化策略全生命周期 | 因子挖掘→回测→风控→孵化→实盘 | 研究效率提升 10x |
| KYC/AML 合规 | 自主查询、交叉比对、风险评分、SAR 生成 | 处理时间从天到分钟 |
| 组合风险管理 | 实时监控、压力测试、VaR、自动对冲 | 风险响应从小时到秒 |
| 多 Agent 交易 | 分析师+交易员+风控经理协作决策 | 收益提升 3-15% |
| 智能客服 | 个性化投资建议、合规沟通 | 服务成本降低 20-40% |

### 1.3 金融系统级 Agent 的六层架构模型

```
┌─────────────────────────────────────────────────────────────────┐
│  L6：监管合规与治理（Governance & Compliance）                   │
│  审计追踪 · 可解释性 · 人类监督 · 监管合规                      │
├─────────────────────────────────────────────────────────────────┤
│  L5：多 Agent 协作与编排（Multi-Agent Orchestration）            │
│  专业化角色 · 辩论机制 · 共识决策 · 任务分解                    │
├─────────────────────────────────────────────────────────────────┤
│  L4：自主决策与执行（Autonomous Decision & Execution）            │
│  策略生成 · 回测优化 · 风控执行 · 交易执行 · 意图确认           │
├─────────────────────────────────────────────────────────────────┤
│  L3：金融推理引擎（Financial Reasoning Engine）                  │
│  因子分析 · 基本面/技术面/情绪面 · 风险评估 · 归因分析          │
├─────────────────────────────────────────────────────────────────┤
│  L2：数据感知与记忆（Data Perception & Memory）                  │
│  实时行情 · 财报 · 新闻 · 研报 · 长期策略记忆 · 学习闭环       │
├─────────────────────────────────────────────────────────────────┤
│  L1：基础设施（Infrastructure）                                  │
│  LLM 路由 · 工具调用 · 安全沙箱 · 消息网关 · MCP/ACP           │
└─────────────────────────────────────────────────────────────────┘
```


---

## 二、当前项目能力现状评估

### 2.1 已实现能力全景

基于代码审计，AIASK 金融系统级 Agent 当前已实现的能力：

#### L1 基础设施层 — ✅ 完整（100%）

| 能力 | 实现模块 | 工具名 |
|------|----------|--------|
| LLM 多模型路由与回退 | `model_providers.py` | `agent_model_manage` |
| 凭证池轮换 | `model_providers.ProviderUsageStore` | — |
| MCP 协议聚合 | `mcp_client.py` (MCPAggregator) | `agent_mcp_manage` |
| ACP 客户端适配 | `acp.py` (ACPManager) | `agent_acp_manage` |
| 安全扫描/脱敏 | `security.py` (SecurityScanner) | `agent_security_scan` |
| 终端/进程管理 | `terminal_backends.py`, `process_registry.py` | `agent_terminal`, `agent_process` |
| 浏览器自动化（11 工具） | `native_capabilities.py` | `agent_browser_*` |
| 消息网关（19 平台） | `gateway.py` (GatewayRuntime) | `agent_gateway_*` |
| Webhook/Cron 调度 | `webhooks.py`, `scheduler.py` | `agent_webhook`, `agent_cronjob` |
| 插件系统 | `plugin_runtime.py` | `agent_plugin_manage` |
| 技能包管理 | `skill_packs.py` | `agent_skill_pack_manage` |

#### L2 数据感知与记忆层 — ✅ 完整（100%）

| 能力 | 实现模块 | 工具名 |
|------|----------|--------|
| Web 搜索 | `native_capabilities.py` | `agent_web_search` |
| Web 内容提取 | `native_capabilities.py` | `agent_web_extract` |
| 文件系统操作 | `native_capabilities.py` | `agent_file_read/write/patch/search` |
| 长期记忆（SQLite + 可插拔） | `memory.py`, `memory_providers.py` | `agent_memory` |
| 会话搜索 | `session_store.py` | `agent_session_search` |
| 视觉分析 | `native_capabilities.py` | `agent_vision_analyze` |
| 图像生成 | `native_capabilities.py` | `agent_image_generate` |
| 语音合成 | `native_capabilities.py` | `agent_text_to_speech` |
| 语音识别 | `native_capabilities.py` | `agent_transcribe_audio` |
| 学习闭环 | `learning_loop.py` | `agent_learning_*` |
| 技能反思 | `learning_loop.py` | `agent_skill_reflect` |

#### L3 金融推理引擎层 — ✅ 深度实现（95%）

| 能力 | 实现模块 | 工具名 |
|------|----------|--------|
| 股票分析工作流 | `native_capabilities.py` | `agent_analyze_stock` |
| 因子验证（IC/回测/OOS/鲁棒性） | `factor_research.py` | `agent_factor_validation` |
| 回测套件 | `backtest_filter.py` | `agent_backtest_suite` |
| 组合风险/压力测试 | `native_capabilities.py` | `agent_portfolio_risk` |
| 量化研究管线 | `quant_research.py` | `agent_quant_research_run` |
| 数据验证 | `native_capabilities.py` | `agent_data_validation` |
| 数据就绪门禁 | `native_capabilities.py` | `agent_quant_data_gate` |
| 治理检查 | `native_capabilities.py` | `agent_governance_check` |
| 市场证据收集 | `market_evidence.py` | — |
| 主题图谱/暴露分析 | `theme_graph.py`, `theme_exposure_builder.py` | — |
| 因子有效性评估 | `factor_effectiveness.py` | — |
| 策略新颖性检测 | `strategy_novelty.py` | — |

#### L4 自主决策与执行层 — ✅ 深度实现（90%）

| 能力 | 实现模块 | 状态 |
|------|----------|------|
| 策略工厂调度器 | `factory_scheduler.py` | ✅ 含断路器/EMA |
| 策略生成（Spawner） | `research/spawner.py` | ✅ |
| 质量门禁（多维） | `quality_gates.py` | ✅ |
| 孵化预算管理 | `incubation_budgeter.py` | ✅ |
| 模拟盘桥接 | `paper_trading_bridge.py` | ✅ |
| 模拟盘调度 | `paper_trading_scheduler.py` | ✅ |
| 策略提交/晋升 | `submitter.py`, `submission_gate/` | ✅ |
| 向量去重 | `deduplicator.py` | ✅ |
| 持久化意图确认 | `intents.py` | ✅ |
| 事件引擎 | `event_engine.py` | ✅ |
| Walk-Forward 验证 | `research/walk_forward.py` | ✅ |
| 任务委派 | `native_capabilities.py` | ✅ `agent_delegate_task` |
| 期货日历研究 | `futures_calendar_research.py` | ✅ |
| 机会发现 | `opportunity.py` | ✅ |
| 淘汰机制 | `elimination.py` | ✅ |
| 任务看板 | `factory_task_board.py` | ✅ |

#### L5 多 Agent 协作层 — ⚠️ 部分实现（40%）

| 能力 | 实现模块 | 状态 |
|------|----------|------|
| 子 Agent 委派 | `agent_delegate_task` | ✅ |
| Mixture of Agents | `moa.py` | ✅ |
| RL 训练（Atropos） | `rl_atropos.py` | ✅ |
| 多角色辩论/共识 | — | ❌ 未实现 |
| 专业化 Agent 团队 | — | ❌ 未实现 |
| Agent 间通信协议 | — | ❌ 未实现 |
| 动态角色分配 | — | ❌ 未实现 |

#### L6 监管合规与治理层 — ✅ 基本完整（85%）

| 能力 | 实现模块 | 状态 |
|------|----------|------|
| 工具风险分级 | `tool_risk.py` | ✅ |
| 工具护栏 | `tool_guardrails.py` | ✅ |
| 工具策略控制 | `tools/policy.py` | ✅ |
| 审批流程 | `approvals.py` | ✅ |
| 安全扫描 | `security.py` | ✅ |
| 治理平面合约 | `governance_plane_contract.py` | ✅ |
| 金融就绪度检查 | `financial_readiness.py` | ✅ |
| 双运行模式隔离 | `finance_safe` / `hermes_full` | ✅ |
| 意图确认机制 | `intents.py` | ✅ |
| 决策可解释性报告 | — | ⚠️ 部分（有质量报告，缺自然语言解释链） |
| 完整审计追踪 | — | ⚠️ 部分（有运行记录，缺决策链路追踪） |


### 2.2 能力成熟度雷达图（文本表示）

```
                    L1 基础设施
                       ★★★★★ (100%)
                      /         \
        L6 治理合规  /           \  L2 数据记忆
          ★★★★☆   /             \   ★★★★★
          (85%)   /               \   (100%)
                 /                 \
                /                   \
   L5 多Agent /                     \ L3 金融推理
     ★★☆☆☆  /                       \  ★★★★★
     (40%) /                         \  (95%)
            \                       /
             \                     /
              \     L4 自主执行    /
               \    ★★★★★      /
                \   (90%)      /
                 \            /
                  \          /
                   ----------
```

### 2.3 与行业标杆对比

| 对比维度 | AIASK（本项目） | TradingAgents | QuantAgent | Bloomberg Agent |
|----------|----------------|---------------|------------|-----------------|
| 策略全生命周期 | ★★★★★ | ★★☆ | ★★☆ | ★★★ |
| 多 Agent 协作 | ★★☆ | ★★★★★ | ★★★★ | ★★★ |
| 实时流处理 | ★★☆ | ★★★ | ★★★★★ | ★★★★ |
| 监管合规 | ★★★★ | ★☆ | ★☆ | ★★★★★ |
| 平台集成广度 | ★★★★★ | ★☆ | ★☆ | ★★★ |
| 自主学习闭环 | ★★★ | ★★ | ★★★ | ★★ |
| 可解释性 | ★★★ | ★★ | ★★ | ★★★★ |

**结论**：AIASK 在策略全生命周期和平台集成广度上领先，
但在多 Agent 协作深度和实时流处理上存在明显短板。


---

## 三、优化方案总览

### 3.1 优化路线图

```
Phase 1（P0，4 周）        Phase 2（P1，6 周）        Phase 3（P2，8 周）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
│ 多Agent辩论框架   │  │ 实时事件驱动引擎  │  │ 自适应学习闭环    │
│ 决策可解释性      │  │ 流式数据管线      │  │ RL在线策略优化    │
│ 调度器核心优化    │  │ 中国市场特化      │  │ 跨组织Agent协作   │
│ 审计追踪增强     │  │ 高频信号处理      │  │ 监管报告自动化    │
└──────────────────┘  └──────────────────┘  └──────────────────┘
```

### 3.2 优化方案索引

| 编号 | 方案名称 | 层级 | 优先级 | 预估工期 |
|------|----------|------|--------|----------|
| OPT-01 | 多 Agent 辩论与共识框架 | L5 | 🔴 P0 | 2 周 |
| OPT-02 | 决策链路可解释性引擎 | L6 | 🔴 P0 | 1.5 周 |
| OPT-03 | 调度器核心优化（节假日/断路器/EMA） | L4 | 🔴 P0 | 1 周 |
| OPT-04 | 完整审计追踪系统 | L6 | 🔴 P0 | 1 周 |
| OPT-05 | 实时事件驱动引擎 | L4 | 🟡 P1 | 2 周 |
| OPT-06 | 流式市场数据管线 | L2 | 🟡 P1 | 2 周 |
| OPT-07 | 中国 A 股市场特化 | L3/L4 | 🟡 P1 | 1.5 周 |
| OPT-08 | 高频信号处理框架 | L3 | 🟡 P1 | 2 周 |
| OPT-09 | RL 在线策略优化闭环 | L5 | 🟢 P2 | 3 周 |
| OPT-10 | 跨组织 Agent 协作协议 | L5 | 🟢 P2 | 2 周 |
| OPT-11 | 监管报告自动生成 | L6 | 🟢 P2 | 2 周 |
| OPT-12 | 自适应资源调度 | L4 | 🟢 P2 | 1.5 周 |


---

## 四、Phase 1 详细方案（P0 优先级）

### OPT-01：多 Agent 辩论与共识框架

**问题诊断**：
当前系统的策略决策由单一推理路径完成（Spawner → 质量门禁 → 提交），
缺乏多视角交叉验证。学术研究（TradingAgents, FinDebate, P1GPT）表明，
多角色辩论机制可显著提升决策质量和鲁棒性。

> **关键研究发现**（arxiv 2511.13614）：最优通信设计取决于市场特征——
> 竞争性对话在高波动科技股中表现更优，协作性对话在稳定蓝筹股中占优，
> 而金融板块对所有通信干预都有抵抗性。因此辩论模式应根据标的市场特征
> 动态切换（competitive / collaborative / minimal）。

**目标**：
在策略工厂的关键决策节点引入**市场状态自适应**的多 Agent 辩论机制，
模拟专业投研团队的协作模式，并根据市场波动率动态选择辩论策略。

**架构设计**：

参考 FinDebate（arxiv 2509.17395）五专业 Agent 并行架构和
TradingAgents 的 Bull/Bear 研究员辩论机制：

```
┌─────────────────────────────────────────────────────────┐
│                  DebateOrchestrator                       │
│  (管理辩论流程、收集观点、判定共识)                        │
│  ┌────────────────────────────────────────────────┐     │
│  │  MarketRegimeDetector（市场状态检测）            │     │
│  │  → volatile: competitive debate                 │     │
│  │  → stable: collaborative debate                 │     │
│  │  → uncertain: full multi-round debate           │     │
│  └────────────────────────────────────────────────┘     │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  │
│  │基本面分析 │  │技术面分析 │  │情绪面分析 │  │估值分析   │  │
│  │  Agent   │  │  Agent   │  │  Agent   │  │  Agent   │  │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘  │
│       │              │              │              │       │
│       ▼              ▼              ▼              ▼       │
│  ┌──────────────────────────────────────┐               │
│  │         ArgumentPool（论点池）        │               │
│  │  每个 Agent 提交：观点 + 证据 + 置信度 │               │
│  └──────────────────┬───────────────────┘               │
│                     │                                    │
│                     ▼                                    │
│  ┌──────────────────────────────────────┐               │
│  │       RiskManagerAgent（风控裁判）     │               │
│  │  评估分歧度、识别盲点、做出最终裁定    │               │
│  └──────────────────┬───────────────────┘               │
│                     │                                    │
│                     ▼                                    │
│  ┌──────────────────────────────────────┐               │
│  │     ConsensusRecord（共识记录）        │               │
│  │  最终决策 + 各方论点 + 分歧说明        │               │
│  └──────────────────────────────────────┘               │
└─────────────────────────────────────────────────────────┘
```

**实现要点**：

```python
# packages/agent/src/aiask_agent/debate.py

@dataclass
class DebateArgument:
    """单个 Agent 的辩论论点"""
    agent_role: str              # "fundamental" | "technical" | "sentiment"
    position: str               # "bullish" | "bearish" | "neutral"
    confidence: float           # 0.0 - 1.0
    evidence: list[str]         # 支撑证据列表
    risk_factors: list[str]     # 识别的风险因素
    suggested_action: str       # 建议操作
    reasoning_chain: list[str]  # 推理链路（用于可解释性）

@dataclass
class ConsensusRecord:
    """辩论共识记录"""
    debate_id: str
    topic: str                  # 辩论主题（如 "是否提交策略 X"）
    arguments: list[DebateArgument]
    consensus_reached: bool
    final_decision: str
    dissent_summary: str        # 少数派意见摘要
    confidence_weighted_score: float
    risk_manager_override: bool
    timestamp: datetime

class DebateOrchestrator:
    """多 Agent 辩论编排器"""

    def __init__(self, model_client, config: DebateConfig):
        self.agents = {
            "fundamental": FundamentalAnalystAgent(model_client),
            "technical": TechnicalAnalystAgent(model_client),
            "sentiment": SentimentAnalystAgent(model_client),
            "valuation": ValuationAnalystAgent(model_client),
            "risk_manager": RiskManagerAgent(model_client),
        }
        self.config = config
        self.regime_detector = MarketRegimeDetector()

    async def run_debate(self, topic: str, context: dict) -> ConsensusRecord:
        """执行一轮完整辩论"""
        # 0. 检测市场状态，选择辩论模式
        regime = await self.regime_detector.detect(context)
        debate_mode = self._select_debate_mode(regime)
        # competitive: 各 Agent 独立提交，不共享中间结果
        # collaborative: Agent 可看到彼此的初步结论并修正
        # minimal: 仅收集独立观点，跳过交叉质询（低波动稳定期）

        # 1. 各分析师独立分析（并行执行）
        arguments = await asyncio.gather(*[
            agent.analyze(topic, context)
            for role, agent in self.agents.items()
            if role != "risk_manager"
        ])

        # 2. 如果分歧度超过阈值，进入第二轮交叉质询
        divergence = self._compute_divergence(arguments)
        if divergence > self.config.cross_examine_threshold:
            arguments = await self._cross_examine(arguments, context)

        # 3. 风控经理做最终裁定
        consensus = await self.agents["risk_manager"].adjudicate(
            arguments, context
        )

        # 4. 记录完整辩论过程（审计追踪）
        record = ConsensusRecord(
            debate_id=f"debate_{uuid4().hex[:12]}",
            topic=topic,
            arguments=arguments,
            consensus_reached=consensus.is_unanimous,
            final_decision=consensus.decision,
            dissent_summary=consensus.dissent,
            confidence_weighted_score=consensus.weighted_score,
            risk_manager_override=consensus.was_override,
            timestamp=datetime.now(),
        )
        await self._persist_record(record)
        return record
```

**集成点**：

1. **策略提交前**：在 `submission_gate/runner.py` 中，策略通过质量门禁后、
   正式提交前触发辩论，多角色评估策略的可行性
2. **机会发现后**：在 `opportunity.py` 发现新机会时，
   多角色评估机会的真实性和时效性
3. **风险事件响应**：当组合风险指标触发阈值时，
   多角色辩论应对策略

**预期收益**：
- 策略提交质量提升（减少过拟合策略进入孵化）
- 决策过程完全可追溯（满足 FINRA 审计要求）
- 识别单一视角的盲点

**已知风险与缓解**：
- **延迟增加**：4-5 个 Agent 并行调用 LLM 会增加 10-30s 延迟。
  缓解：并行执行 + 设置辩论超时（30s）+ 非关键路径异步执行
- **成本增加**：每次辩论消耗 4-5x 的 token。
  缓解：仅在高价值决策点触发（策略提交、风险事件），日常扫描不辩论
- **共识陷阱**：Agent 可能趋同（groupthink）。
  缓解：引入 Devil's Advocate 机制，强制一个 Agent 持反对立场


---

### OPT-02：决策链路可解释性引擎

**问题诊断**：
当前系统有质量报告和运行记录，但缺乏从"输入数据"到"最终决策"的
完整自然语言推理链路。FINRA 2026 明确要求所有自主决策必须可审计，
且能向非技术监管人员解释。

> **监管要求汇总**：
> - FINRA 2026：所有自主决策必须有人类可审计的完整记录
> - EU AI Act（高风险 AI 合规期限延至 2027.12）：要求决策可追溯性、
>   训练/审查数据文档化、每个警报/驳回/升级的可审计性
> - FCA（英国）：任何实质性影响客户的决策必须可解释，
>   如果合规官无法清晰阐述决策原因，该决策不应成立
> - 中国证监会：AI 辅助投资决策需保留完整决策依据
>
> **行业共识**（Zartis 2025）：审计追踪不是事后补丁，而是 AI 系统的
> 架构级约束，必须从第一天就嵌入设计。

**目标**：
为每个关键决策生成结构化的可解释性报告，
包含推理链路、证据引用、置信度和替代方案分析。

**架构设计**：

```
决策触发
    │
    ▼
┌─────────────────────────────────────┐
│     ExplainabilityTracer            │
│  (嵌入决策流程，记录每步推理)         │
├─────────────────────────────────────┤
│  trace_start(decision_type, input)  │
│  trace_step(reasoning, evidence)    │
│  trace_branch(alternatives)         │
│  trace_conclusion(decision, conf)   │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│     ExplanationRenderer             │
│  (将追踪数据渲染为可读报告)           │
├─────────────────────────────────────┤
│  render_technical(trace) → JSON     │
│  render_narrative(trace) → 中文文本  │
│  render_regulatory(trace) → 合规格式 │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│     ExplanationStore                │
│  (持久化，支持回溯查询)              │
└─────────────────────────────────────┘
```

**实现要点**：

```python
# packages/agent/src/aiask_agent/explainability.py

@dataclass
class ReasoningStep:
    """单步推理记录"""
    step_id: str
    action: str                 # "evaluate", "compare", "decide", "reject"
    input_summary: str          # 输入数据摘要
    reasoning: str              # 推理逻辑（自然语言）
    evidence: list[dict]        # 支撑证据 [{source, value, weight}]
    output: str                 # 本步输出
    confidence: float           # 置信度
    alternatives_considered: list[str]  # 考虑过的替代方案
    timestamp: datetime

@dataclass
class DecisionTrace:
    """完整决策追踪"""
    trace_id: str
    decision_type: str          # "strategy_submit", "risk_alert", "opportunity_select"
    trigger: str                # 触发原因
    steps: list[ReasoningStep]
    final_decision: str
    final_confidence: float
    risk_assessment: str
    human_readable_summary: str  # 一段话总结
    regulatory_classification: str  # "autonomous", "assisted", "informational"

class ExplainabilityTracer:
    """决策可解释性追踪器（上下文管理器模式）"""

    def __init__(self, decision_type: str, trigger: str):
        self.trace = DecisionTrace(
            trace_id=f"trace_{uuid4().hex[:12]}",
            decision_type=decision_type,
            trigger=trigger,
            steps=[],
            final_decision="",
            final_confidence=0.0,
            risk_assessment="",
            human_readable_summary="",
            regulatory_classification="autonomous",
        )

    def step(self, action: str, reasoning: str, **kwargs) -> ReasoningStep:
        """记录一步推理"""
        s = ReasoningStep(
            step_id=f"step_{len(self.trace.steps):03d}",
            action=action,
            reasoning=reasoning,
            input_summary=kwargs.get("input_summary", ""),
            evidence=kwargs.get("evidence", []),
            output=kwargs.get("output", ""),
            confidence=kwargs.get("confidence", 0.0),
            alternatives_considered=kwargs.get("alternatives", []),
            timestamp=datetime.now(),
        )
        self.trace.steps.append(s)
        return s

    def conclude(self, decision: str, confidence: float, summary: str):
        """记录最终决策"""
        self.trace.final_decision = decision
        self.trace.final_confidence = confidence
        self.trace.human_readable_summary = summary

    async def persist(self, store: ExplanationStore):
        """持久化追踪记录"""
        await store.save_trace(self.trace)
```

**使用示例（集成到策略提交流程）**：

```python
async def evaluate_strategy_for_submission(self, strategy, context):
    tracer = ExplainabilityTracer(
        decision_type="strategy_submit",
        trigger=f"策略 {strategy.name} 通过质量门禁"
    )

    # 步骤 1：评估回测表现
    tracer.step(
        action="evaluate",
        reasoning="检查策略回测指标是否满足最低要求",
        input_summary=f"Sharpe={strategy.sharpe:.2f}, MaxDD={strategy.max_dd:.1%}",
        evidence=[
            {"source": "backtest", "value": f"Sharpe {strategy.sharpe:.2f}", "weight": 0.4},
            {"source": "backtest", "value": f"MaxDD {strategy.max_dd:.1%}", "weight": 0.3},
        ],
        output="回测指标达标" if strategy.sharpe > 1.0 else "回测指标不达标",
        confidence=0.85,
        alternatives=["降低 Sharpe 阈值至 0.8", "增加样本外验证期"],
    )

    # 步骤 2：检查与现有策略的相关性
    tracer.step(
        action="compare",
        reasoning="检查新策略与现有组合的相关性，避免过度集中",
        ...
    )

    # 最终决策
    tracer.conclude(
        decision="approve_for_incubation",
        confidence=0.82,
        summary=f"策略 {strategy.name} 基于动量因子，Sharpe 1.3，"
                f"与现有组合相关性 0.25（低），建议进入孵化阶段。"
                f"主要风险：回撤控制依赖止损线，极端行情下可能失效。"
    )

    await tracer.persist(self.explanation_store)
    return tracer.trace
```

**输出格式（监管友好）**：

```
═══════════════════════════════════════════════════════
决策追踪报告 trace_a1b2c3d4e5f6
═══════════════════════════════════════════════════════
类型：策略提交决策
触发：策略 MomentumAlpha_v3 通过质量门禁
时间：2026-05-16 14:30:22 CST
分类：自主决策（需人类确认）

【决策摘要】
策略 MomentumAlpha_v3 基于动量因子，回测 Sharpe 1.3，
与现有组合相关性 0.25（低），建议进入孵化阶段。
主要风险：回撤控制依赖止损线，极端行情下可能失效。

【推理链路】
Step 001 [评估] 检查回测指标 → 达标（置信度 85%）
  证据：Sharpe 1.3 (权重 40%), MaxDD -8.2% (权重 30%)
  替代方案：降低阈值至 0.8 / 增加 OOS 验证期

Step 002 [比较] 检查组合相关性 → 低相关（置信度 90%）
  证据：与现有 12 策略最大相关系数 0.25

Step 003 [决策] 综合评估 → 批准进入孵化（置信度 82%）

【风险评估】
- 极端行情风险：中等
- 过拟合风险：低（OOS 验证通过）
- 流动性风险：低（标的日均成交额 > 5000 万）
═══════════════════════════════════════════════════════
```


---

### OPT-03：调度器核心优化

**问题诊断**：
策略工厂调度器文档已识别多个改进点，此处整合为统一优化方案。

**优化 3.1：中国交易日历集成**

> **可用库**：`a-trade-calendar`（PyPI）专为 A 股设计；
> 或使用 `akshare` 的 `tool_trade_date_hist_sina()` 接口获取历史交易日。
> 建议本地缓存 + 年度更新，避免运行时网络依赖。

```python
# packages/strategy-factory/src/strategy_factory/infrastructure/trading_calendar.py

class ChinaTradingCalendar:
    """A 股交易日历，支持节假日和调休"""

    def __init__(self, data_source: str = "local"):
        self._holidays: set[date] = set()
        self._extra_workdays: set[date] = set()  # 调休工作日
        self._load_calendar(data_source)

    def is_trading_day(self, d: date) -> bool:
        """判断是否为交易日"""
        if d in self._holidays:
            return False
        if d in self._extra_workdays:
            return True
        return d.weekday() < 5  # 非节假日的工作日

    def next_trading_day(self, d: date) -> date:
        """获取下一个交易日"""
        candidate = d + timedelta(days=1)
        while not self.is_trading_day(candidate):
            candidate += timedelta(days=1)
        return candidate

    def trading_days_between(self, start: date, end: date) -> list[date]:
        """获取区间内所有交易日"""
        return [d for d in self._date_range(start, end) if self.is_trading_day(d)]

    def _load_calendar(self, source: str):
        """加载日历数据（支持本地 JSON 或远程 API）"""
        # 优先从本地 JSON 加载（年度更新）
        # 回退到 akshare 的 tool_trade_date_hist_sina()
        ...
```

**优化 3.2：断路器 Half-Open + 指数退避**

> **最佳实践参考**：AWS Builder's Library 推荐使用"full jitter"模式
> （`random(0, min(cap, base * 2^attempt))`）而非固定百分比抖动，
> 以更有效地分散重试请求。Microsoft Azure 也推荐断路器与指数退避组合使用。

```python
# 增强 factory_scheduler.py 中的断路器状态机

class CircuitBreakerState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

class EnhancedCircuitBreaker:
    def __init__(self, max_failures: int = 5, base_backoff: float = 1800):
        self.state = CircuitBreakerState.CLOSED
        self.consecutive_failures = 0
        self.max_failures = max_failures
        self.base_backoff = base_backoff
        self.current_backoff = base_backoff
        self.open_until: datetime | None = None

    def record_failure(self, now: datetime):
        self.consecutive_failures += 1
        if self.consecutive_failures >= self.max_failures:
            self.state = CircuitBreakerState.OPEN
            # 指数退避：1800s → 3600s → 7200s（上限）
            self.current_backoff = min(self.current_backoff * 2, 7200)
            # Full Jitter（AWS 推荐）：random(0, backoff)
            # 比固定百分比抖动更有效地分散重试
            jittered = random.uniform(0, self.current_backoff)
            self.open_until = now + timedelta(seconds=max(self.base_backoff * 0.5, jittered))

    def record_success(self):
        self.state = CircuitBreakerState.CLOSED
        self.consecutive_failures = 0
        self.current_backoff = self.base_backoff

    def should_attempt(self, now: datetime) -> bool:
        if self.state == CircuitBreakerState.CLOSED:
            return True
        if self.state == CircuitBreakerState.OPEN:
            if now >= self.open_until:
                self.state = CircuitBreakerState.HALF_OPEN
                return True  # 允许一次探测
            return False
        if self.state == CircuitBreakerState.HALF_OPEN:
            return True  # 探测中
        return False

    def record_probe_result(self, success: bool, now: datetime):
        """Half-Open 探测结果"""
        if success:
            self.record_success()
        else:
            self.state = CircuitBreakerState.OPEN
            self.current_backoff = min(self.current_backoff * 2, 7200)
            self.open_until = now + timedelta(seconds=self.current_backoff)
```

**优化 3.3：EMA 饥饿保护 + 持久化**

```python
# 增强 family gate feedback

EMA_FLOOR = 0.15           # EMA 下限，防止永久边缘化
EXPLORATION_CYCLE = 20     # 每 20 轮强制探索一次
EXPLORATION_RESET = 0.5    # 探索重置值

def update_family_gate_feedback(self, family_counts: dict, cycle_count: int):
    """更新 family EMA 反馈，含饥饿保护"""
    for family, count in family_counts.items():
        prev = self._family_gate_feedback.get(family, {}).get("ema_submit_count", 0.0)
        new_ema = 0.3 * count + 0.7 * prev
        self._family_gate_feedback[family] = {
            "ema_submit_count": round(new_ema, 4),
            "last_seen_cycle": cycle_count,
        }

    # 衰减未出现的 family（带下限保护）
    for family, data in self._family_gate_feedback.items():
        if family not in family_counts:
            prev = data.get("ema_submit_count", 0.0)
            data["ema_submit_count"] = max(EMA_FLOOR, round(prev * 0.7, 4))

    # 周期性探索重置
    if cycle_count > 0 and cycle_count % EXPLORATION_CYCLE == 0:
        for family, data in self._family_gate_feedback.items():
            if data.get("ema_submit_count", 0) < 0.2:
                data["ema_submit_count"] = EXPLORATION_RESET

async def persist_scheduler_state(self, db):
    """持久化调度器状态（含 EMA 反馈）"""
    await db.save_json("scheduler_state", {
        "family_gate_feedback": self._family_gate_feedback,
        "cycle_count": self._cycle_count,
        "circuit_breaker": {
            "state": self._circuit_breaker.state.value,
            "consecutive_failures": self._circuit_breaker.consecutive_failures,
            "current_backoff": self._circuit_breaker.current_backoff,
        },
    })

async def restore_scheduler_state(self, db):
    """启动时恢复状态"""
    state = await db.load_json("scheduler_state")
    if state:
        self._family_gate_feedback = state.get("family_gate_feedback", {})
        self._cycle_count = state.get("cycle_count", 0)
```


---

### OPT-04：完整审计追踪系统

**问题诊断**：
当前有运行记录和 TaskBoard，但缺乏从"用户请求/系统触发"到"最终执行"
的端到端审计链。金融监管要求每个自主操作都能回溯到触发源。

**架构设计**：

```
┌─────────────────────────────────────────────────────────┐
│                    AuditTrail                             │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  AuditEvent                                              │
│  ├── event_id (全局唯一)                                 │
│  ├── trace_id (关联同一决策链的所有事件)                   │
│  ├── parent_event_id (因果链)                            │
│  ├── actor (user | agent | system | scheduler)           │
│  ├── action (tool_call | decision | state_change | ...)  │
│  ├── target (策略ID | 工具名 | 资源路径)                  │
│  ├── input_hash (输入数据指纹，不存明文敏感数据)           │
│  ├── output_summary (输出摘要)                           │
│  ├── risk_level (low | medium | high | critical)         │
│  ├── approval_status (auto | pending | approved | denied)│
│  ├── timestamp                                           │
│  └── metadata (扩展字段)                                 │
│                                                          │
│  AuditQuery                                              │
│  ├── by_trace_id → 完整决策链                            │
│  ├── by_time_range → 时间段内所有事件                     │
│  ├── by_risk_level → 高风险操作筛选                       │
│  ├── by_actor → 特定角色的操作历史                        │
│  └── by_target → 特定资源的变更历史                       │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

**实现要点**：

```python
# packages/agent/src/aiask_agent/audit.py

@dataclass
class AuditEvent:
    event_id: str
    trace_id: str
    parent_event_id: str | None
    actor: str              # "user", "agent", "scheduler", "system"
    action: str             # "tool_call", "decision", "state_change", "approval"
    target: str             # 操作目标
    input_hash: str         # SHA256 of input (不存原文)
    output_summary: str     # 输出摘要（脱敏）
    risk_level: str         # "low", "medium", "high", "critical"
    approval_status: str    # "auto_approved", "pending", "approved", "denied"
    duration_ms: int        # 执行耗时
    timestamp: datetime
    metadata: dict

class AuditTrailStore:
    """审计追踪存储（追加写入，不可修改）"""

    def __init__(self, db_path: Path):
        self._db = sqlite3.connect(str(db_path))
        self._ensure_schema()

    async def record(self, event: AuditEvent):
        """记录审计事件（追加写入）"""
        ...

    async def query_trace(self, trace_id: str) -> list[AuditEvent]:
        """查询完整决策链"""
        ...

    async def query_high_risk(self, since: datetime) -> list[AuditEvent]:
        """查询高风险操作"""
        ...

    async def generate_compliance_report(
        self, start: datetime, end: datetime
    ) -> ComplianceReport:
        """生成合规报告"""
        events = await self.query_time_range(start, end)
        return ComplianceReport(
            total_decisions=len([e for e in events if e.action == "decision"]),
            autonomous_decisions=len([e for e in events
                if e.action == "decision" and e.actor == "agent"]),
            human_overrides=len([e for e in events
                if e.approval_status == "denied"]),
            high_risk_actions=len([e for e in events
                if e.risk_level in ("high", "critical")]),
            average_confidence=...,
            ...
        )
```

**集成方式**：
通过装饰器或中间件模式，自动为所有工具调用和决策点生成审计事件：

```python
def audited(risk_level: str = "low"):
    """审计装饰器"""
    def decorator(func):
        @wraps(func)
        async def wrapper(self, *args, **kwargs):
            event = AuditEvent(
                event_id=f"evt_{uuid4().hex[:12]}",
                trace_id=get_current_trace_id(),
                actor="agent",
                action="tool_call",
                target=func.__name__,
                risk_level=risk_level,
                ...
            )
            try:
                result = await func(self, *args, **kwargs)
                event.output_summary = summarize(result)
                event.approval_status = "auto_approved"
                return result
            except Exception as exc:
                event.output_summary = f"ERROR: {type(exc).__name__}"
                raise
            finally:
                await audit_store.record(event)
        return wrapper
    return decorator
```


---

## 五、Phase 2 详细方案（P1 优先级）

### OPT-05：实时事件驱动引擎

**问题诊断**：
当前策略工厂以固定间隔（盘中 720s / 盘后 3600s）批次调度，
无法对突发市场事件（涨跌停、重大公告、异常成交量）做出即时响应。

> **行业实践**：事件驱动架构（EDA）已成为机构级交易系统的标准设计模式。
> Python 生态中 `asyncio` + 事件总线模式被广泛用于算法交易
>（参考 PyQuantNews、MarketClutch 的 EDA 教程和 `aat` 异步交易框架）。
> 关键设计原则：事件驱动不替代批次调度，而是补充——
> 批次负责系统性扫描，事件负责即时响应。

**目标**：
在保留批次调度的基础上，增加事件驱动的即时响应通道。

**架构设计**：

```
┌─────────────────────────────────────────────────────────────┐
│                    EventDrivenEngine                          │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐   │
│  │ MarketEvent  │    │ NewsEvent    │    │ SystemEvent  │   │
│  │ Source       │    │ Source       │    │ Source       │   │
│  └──────┬───────┘    └──────┬───────┘    └──────┬───────┘   │
│         │                   │                   │            │
│         ▼                   ▼                   ▼            │
│  ┌──────────────────────────────────────────────────────┐   │
│  │              EventBus（事件总线）                      │   │
│  │  - 事件分类与优先级排序                               │   │
│  │  - 去重与节流（防止事件风暴）                          │   │
│  │  - 持久化（确保不丢失）                               │   │
│  └──────────────────────┬───────────────────────────────┘   │
│                         │                                    │
│                         ▼                                    │
│  ┌──────────────────────────────────────────────────────┐   │
│  │           EventRouter（事件路由器）                    │   │
│  │  - 规则匹配（哪些事件触发哪些处理器）                  │   │
│  │  - 优先级调度（critical > high > normal）             │   │
│  │  - 并发控制（限制同时处理的事件数）                    │   │
│  └──────────────────────┬───────────────────────────────┘   │
│                         │                                    │
│         ┌───────────────┼───────────────┐                   │
│         ▼               ▼               ▼                   │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐            │
│  │ 策略紧急   │  │ 风险响应   │  │ 机会捕获   │            │
│  │ 评估处理器 │  │ 处理器     │  │ 处理器     │            │
│  └────────────┘  └────────────┘  └────────────┘            │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

**事件类型定义**：

```python
class MarketEventType(Enum):
    LIMIT_UP = "limit_up"           # 涨停
    LIMIT_DOWN = "limit_down"       # 跌停
    VOLUME_SPIKE = "volume_spike"   # 成交量异常放大
    PRICE_GAP = "price_gap"         # 跳空缺口
    INDEX_CRASH = "index_crash"     # 指数急跌（>2%/5min）
    SECTOR_ROTATION = "sector_rotation"  # 板块轮动信号

class NewsEventType(Enum):
    POLICY_CHANGE = "policy_change"     # 政策变化
    EARNINGS_SURPRISE = "earnings"      # 业绩超预期/不及预期
    ANALYST_UPGRADE = "analyst_upgrade" # 分析师评级变化
    INSIDER_TRADE = "insider_trade"     # 内部人交易

class SystemEventType(Enum):
    STRATEGY_BREACH = "strategy_breach"     # 策略触发止损/止盈
    RISK_THRESHOLD = "risk_threshold"       # 风险指标越限
    DATA_ANOMALY = "data_anomaly"           # 数据异常
    MODEL_DRIFT = "model_drift"            # 模型漂移检测
```

**与现有调度器的协作**：

```python
class HybridScheduler:
    """混合调度器：批次 + 事件驱动"""

    def __init__(self, factory_scheduler, event_engine):
        self.batch_scheduler = factory_scheduler  # 现有调度器
        self.event_engine = event_engine          # 新增事件引擎

    async def start(self):
        # 并行运行两个调度通道
        await asyncio.gather(
            self.batch_scheduler.start(),    # 定时批次
            self.event_engine.start(),       # 事件驱动
        )

    # 事件驱动不替代批次调度，而是补充：
    # - 批次调度：全面扫描、系统性研究、定期报告
    # - 事件驱动：即时响应、紧急风控、机会捕获
```

---

### OPT-06：流式市场数据管线

**问题诊断**：
当前数据获取依赖 akshare-mcp 的请求-响应模式，
无法支持实时行情推送和流式处理。

**目标**：
建立流式数据管线，支持实时行情订阅和增量处理。

**架构设计**：

```python
# packages/agent/src/aiask_agent/streaming.py

class MarketDataStream:
    """流式市场数据管线"""

    def __init__(self, config: StreamConfig):
        self._subscribers: dict[str, list[Callable]] = {}
        self._buffer = AsyncBuffer(max_size=10000)
        self._processors: list[StreamProcessor] = []

    async def subscribe(self, symbols: list[str], callback: Callable):
        """订阅标的实时数据"""
        for symbol in symbols:
            self._subscribers.setdefault(symbol, []).append(callback)

    async def add_processor(self, processor: StreamProcessor):
        """添加流处理器（如异常检测、信号计算）"""
        self._processors.append(processor)

    async def _process_tick(self, tick: MarketTick):
        """处理单个 tick"""
        # 1. 通过所有处理器
        signals = []
        for processor in self._processors:
            signal = await processor.process(tick)
            if signal:
                signals.append(signal)

        # 2. 如果产生信号，发布到事件总线
        for signal in signals:
            await self.event_bus.publish(signal)

        # 3. 通知订阅者
        for callback in self._subscribers.get(tick.symbol, []):
            await callback(tick)


class VolumeAnomalyDetector(StreamProcessor):
    """成交量异常检测处理器"""

    def __init__(self, lookback: int = 20, threshold: float = 3.0):
        self._history: dict[str, deque] = {}
        self.lookback = lookback
        self.threshold = threshold

    async def process(self, tick: MarketTick) -> MarketEvent | None:
        history = self._history.setdefault(tick.symbol, deque(maxlen=self.lookback))
        history.append(tick.volume)

        if len(history) < self.lookback:
            return None

        mean_vol = sum(history) / len(history)
        if tick.volume > mean_vol * self.threshold:
            return MarketEvent(
                type=MarketEventType.VOLUME_SPIKE,
                symbol=tick.symbol,
                value=tick.volume / mean_vol,
                timestamp=tick.timestamp,
            )
        return None
```

---

### OPT-07：中国 A 股市场特化

**问题诊断**：
调度器文档已识别交易日历问题。除此之外，A 股还有多个特殊规则
需要在系统级别支持。

**特化内容**：

| 规则 | 影响模块 | 实现方式 |
|------|----------|----------|
| T+1 交易制度 | 策略执行、回测 | 持仓锁定期检查 |

> **T+1 规则的深层影响**（ResearchGate/SSRN 研究）：
> T+1 制度不仅是简单的"当日不能卖"，它还导致：
> - 开盘价系统性折价（overnight return puzzle）
> - 日内动量策略失效（无法当日止损）
> - 对算法交易的定价效率影响（需多日换手策略）
> 策略工厂的回测引擎必须正确模拟 T+1 约束，否则回测结果会严重高估。
| 涨跌停板（±10%/±20%） | 风控、信号生成 | 价格边界检测 |
| 集合竞价（9:15-9:25, 14:57-15:00） | 调度器、信号 | 时间窗口感知 |
| 交易日历（节假日+调休） | 调度器 | OPT-03 已覆盖 |
| 北向资金流向 | 情绪分析 | 数据源集成 |
| 融资融券余额 | 风险评估 | 数据源集成 |
| 板块轮动特征 | 策略生成 | 行业分类体系 |
| 注册制/退市规则 | 标的筛选 | 风险标记 |

```python
# packages/strategy-factory/src/strategy_factory/domain/china_market_rules.py

class ChinaMarketRules:
    """A 股市场规则引擎"""

    MAIN_BOARD_LIMIT = 0.10      # 主板涨跌停 ±10%
    GEM_BOARD_LIMIT = 0.20       # 创业板/科创板 ±20%
    ST_LIMIT = 0.05              # ST 股 ±5%

    @staticmethod
    def get_price_limit(symbol: str) -> float:
        """获取标的涨跌停幅度"""
        if symbol.startswith(("300", "301", "688", "689")):
            return ChinaMarketRules.GEM_BOARD_LIMIT
        # ST 判断需要查询标的状态
        return ChinaMarketRules.MAIN_BOARD_LIMIT

    @staticmethod
    def is_auction_period(t: time) -> bool:
        """是否处于集合竞价时段"""
        morning_auction = time(9, 15) <= t < time(9, 25)
        closing_auction = time(14, 57) <= t <= time(15, 0)
        return morning_auction or closing_auction

    @staticmethod
    def can_sell_today(buy_date: date, current_date: date) -> bool:
        """T+1 规则：当日买入次日才能卖出"""
        return current_date > buy_date

    @staticmethod
    def is_st_stock(symbol: str, name: str) -> bool:
        """判断是否为 ST 股"""
        return "ST" in name.upper() or "*ST" in name.upper()
```

---

### OPT-08：高频信号处理框架

**问题诊断**：
当前系统以日频/小时频为主，缺乏分钟级信号处理能力。
学术研究（QuantAgent）表明 1h/4h 级别的多 Agent 信号融合
可显著提升短期预测准确率。

**架构设计**：

```python
# packages/strategy-factory/src/strategy_factory/application/hf_signals.py

class SignalTimeframe(Enum):
    M1 = "1min"
    M5 = "5min"
    M15 = "15min"
    H1 = "1hour"
    H4 = "4hour"
    D1 = "daily"

@dataclass
class TradingSignal:
    symbol: str
    timeframe: SignalTimeframe
    direction: str          # "long", "short", "neutral"
    strength: float         # -1.0 to 1.0
    source: str             # "indicator", "pattern", "trend", "sentiment"
    confidence: float       # 0.0 to 1.0
    metadata: dict
    timestamp: datetime

class MultiTimeframeSignalAggregator:
    """多时间框架信号聚合器"""

    def __init__(self, timeframes: list[SignalTimeframe]):
        self.timeframes = timeframes
        self._signals: dict[str, dict[SignalTimeframe, list[TradingSignal]]] = {}

    async def aggregate(self, symbol: str) -> AggregatedSignal:
        """聚合多时间框架信号"""
        signals = self._signals.get(symbol, {})

        # 时间框架权重：高频信号权重低，低频信号权重高
        weights = {
            SignalTimeframe.M5: 0.05,
            SignalTimeframe.M15: 0.10,
            SignalTimeframe.H1: 0.25,
            SignalTimeframe.H4: 0.30,
            SignalTimeframe.D1: 0.30,
        }

        weighted_direction = 0.0
        total_confidence = 0.0

        for tf, tf_signals in signals.items():
            if not tf_signals:
                continue
            latest = tf_signals[-1]
            w = weights.get(tf, 0.1)
            weighted_direction += latest.strength * w * latest.confidence
            total_confidence += latest.confidence * w

        return AggregatedSignal(
            symbol=symbol,
            direction="long" if weighted_direction > 0.1 else
                     "short" if weighted_direction < -0.1 else "neutral",
            strength=abs(weighted_direction),
            confidence=total_confidence / sum(weights.values()),
            contributing_timeframes=list(signals.keys()),
        )
```


---

## 六、Phase 3 详细方案（P2 优先级）

### OPT-09：RL 在线策略优化闭环

**问题诊断**：
当前 RL Atropos 模块偏向离线训练侧，未与策略工厂的选择/淘汰决策
形成在线闭环。策略在孵化期的表现反馈未被用于动态调整策略参数。

> **最新研究支撑**：
> - Regime-Aware RL（arxiv 2509.14385）：Agent 根据宏观经济状态转换动态重新分配资本
> - Graph Attention Multi-Agent DRL（Nature 2025）：三个异构 Agent（风险评估、收益预测、
>   市场环境感知）通过图注意力网络建模资产相关性，自适应调整参数
> - Unified Agentic Framework（Springer 2026）：LLM 信号 + RL 执行 + 约束弹性的统一架构
>
> 这些研究验证了"在线自适应 + 市场状态感知"的可行性和有效性。

**目标**：
将 RL 反馈接入策略工厂的全生命周期，实现：
- 孵化期策略参数的在线微调（regime-aware）
- 基于实际表现的策略权重动态调整
- 从失败策略中提取经验用于新策略生成

**架构设计**：

```
┌─────────────────────────────────────────────────────────────┐
│                 RL Online Optimization Loop                   │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  策略工厂                    RL 优化器                        │
│  ┌──────────┐               ┌──────────────┐               │
│  │ Spawner  │──生成策略──→  │ 参数空间定义  │               │
│  └──────────┘               └──────┬───────┘               │
│       ↑                            │                        │
│       │                            ▼                        │
│  ┌──────────┐               ┌──────────────┐               │
│  │ 经验库   │←──提取经验──  │ 在线微调     │               │
│  └──────────┘               └──────┬───────┘               │
│       ↑                            │                        │
│       │                            ▼                        │
│  ┌──────────┐               ┌──────────────┐               │
│  │ 淘汰器   │←──表现反馈──  │ 模拟盘评估   │               │
│  └──────────┘               └──────┬───────┘               │
│                                    │                        │
│                                    ▼                        │
│                             ┌──────────────┐               │
│                             │ 奖励信号计算  │               │
│                             │ Sharpe变化率  │               │
│                             │ 回撤控制效果  │               │
│                             │ 风险调整收益  │               │
│                             └──────────────┘               │
└─────────────────────────────────────────────────────────────┘
```

**实现要点**：

```python
class OnlineStrategyOptimizer:
    """在线策略优化器"""

    def __init__(self, rl_manager: RLAtroposManager, config: OptConfig):
        self.rl_manager = rl_manager
        self.config = config
        self._reward_history: dict[str, list[float]] = {}

    async def compute_reward(self, strategy_id: str, period_result: dict) -> float:
        """计算策略的 RL 奖励信号"""
        sharpe_delta = period_result["sharpe"] - period_result.get("prev_sharpe", 0)
        drawdown_penalty = max(0, period_result["max_drawdown"] - self.config.dd_threshold)
        turnover_cost = period_result["turnover"] * self.config.turnover_penalty

        reward = (
            sharpe_delta * self.config.sharpe_weight
            - drawdown_penalty * self.config.dd_weight
            - turnover_cost
        )
        self._reward_history.setdefault(strategy_id, []).append(reward)
        return reward

    async def suggest_parameter_adjustment(
        self, strategy_id: str, current_params: dict
    ) -> dict:
        """基于累积奖励建议参数调整"""
        rewards = self._reward_history.get(strategy_id, [])
        if len(rewards) < self.config.min_observations:
            return current_params  # 观察期不足，不调整

        # 使用 bandit 算法选择参数方向
        trend = sum(rewards[-5:]) / 5 - sum(rewards[-10:-5]) / 5
        adjustments = {}

        if trend < -0.1:  # 表现恶化
            # 收紧风控参数
            adjustments["stop_loss"] = current_params["stop_loss"] * 0.9
            adjustments["position_size"] = current_params["position_size"] * 0.8
        elif trend > 0.1:  # 表现改善
            # 适度放宽（但不超过初始值的 120%）
            adjustments["position_size"] = min(
                current_params["position_size"] * 1.1,
                current_params.get("initial_position_size", 1.0) * 1.2
            )

        return {**current_params, **adjustments}

    async def extract_failure_experience(self, strategy: dict) -> dict:
        """从失败策略中提取经验"""
        return {
            "strategy_family": strategy["family"],
            "failure_mode": self._classify_failure(strategy),
            "market_regime": strategy.get("market_regime_at_failure"),
            "lesson": self._generate_lesson(strategy),
            "avoid_patterns": self._extract_avoid_patterns(strategy),
        }
```

---

### OPT-10：跨组织 Agent 协作协议

**问题诊断**：
当前系统是单体 Agent 架构，未来需要支持：
- 与外部数据提供商 Agent 的协作
- 与合规审计 Agent 的交互
- 与客户端 Agent 的安全通信

> **行业进展**：2025-2026 年已出现多个 Agent 间通信协议标准：
> - ACP（Agent Communication Protocol, arxiv 2602.15055）：联邦编排 + 零信任
> - Google A2A（Agent-to-Agent）：跨平台 Agent 发现与协作
> - Coral Protocol：去中心化 Agent 协作基础设施
> - Agent Trust Protocol (ATP)：加密身份验证标准
>
> **安全警告**（CSA 2025）：79% 的组织已使用 AI Agent，但 86% 未经安全审批部署。
> 跨组织通信必须采用零信任架构，防范 Logic-layer Prompt Control Injection (LPCI) 攻击。

**目标**：
基于 ACP 协议思想，定义标准化的 Agent 间通信协议，支持跨组织边界的安全协作。

**协议设计**：

```python
# Agent Communication Protocol (ACP) Extension

@dataclass
class AgentMessage:
    """Agent 间通信消息"""
    message_id: str
    sender: AgentIdentity       # 发送方身份
    receiver: AgentIdentity     # 接收方身份
    intent: str                 # "request", "response", "notify", "negotiate"
    capability_required: str    # 需要的能力
    payload: dict               # 消息内容
    constraints: dict           # 约束条件（超时、权限、数据范围）
    signature: str              # 数字签名（验证身份）
    timestamp: datetime
    ttl_seconds: int            # 消息有效期

@dataclass
class AgentIdentity:
    """Agent 身份标识"""
    agent_id: str
    organization: str
    role: str                   # "data_provider", "analyst", "executor", "auditor"
    capabilities: list[str]     # 声明的能力列表
    trust_level: str            # "internal", "partner", "external"
    public_key: str             # 用于验证签名

class CrossOrgAgentGateway:
    """跨组织 Agent 网关"""

    def __init__(self, identity: AgentIdentity, policy: SecurityPolicy):
        self.identity = identity
        self.policy = policy
        self._trusted_peers: dict[str, AgentIdentity] = {}

    async def send_request(self, peer_id: str, capability: str, payload: dict) -> dict:
        """向外部 Agent 发送请求"""
        peer = self._trusted_peers.get(peer_id)
        if not peer:
            raise UntrustedPeerError(f"Peer {peer_id} not in trusted list")

        # 检查数据外发策略
        sanitized = self.policy.sanitize_outbound(payload)

        message = AgentMessage(
            message_id=f"msg_{uuid4().hex[:12]}",
            sender=self.identity,
            receiver=peer,
            intent="request",
            capability_required=capability,
            payload=sanitized,
            constraints={"timeout": 30, "data_scope": "public_only"},
            signature=self._sign(sanitized),
            timestamp=datetime.now(),
            ttl_seconds=60,
        )

        response = await self._transport.send(message)
        # 验证响应签名
        if not self._verify_signature(response, peer):
            raise SignatureVerificationError()
        return response.payload
```

---

### OPT-11：监管报告自动生成

**问题诊断**：
金融机构需要定期向监管机构提交 AI 系统使用报告。
当前缺乏自动化的报告生成能力。

**目标**：
基于审计追踪数据，自动生成符合监管要求的报告。

**报告类型**：

| 报告 | 频率 | 内容 | 对应监管 |
|------|------|------|----------|
| AI 决策审计报告 | 日报 | 所有自主决策的摘要和统计 | FINRA/证监会 |
| 风险事件报告 | 实时 | 高风险操作和异常事件 | 内部风控 |
| 模型表现报告 | 周报 | 策略表现、模型漂移、准确率 | 模型风险管理 |
| 合规状态报告 | 月报 | 系统合规状态、人类监督统计 | 合规部门 |

```python
class RegulatoryReportGenerator:
    """监管报告自动生成器"""

    async def generate_daily_decision_report(self, date: date) -> Report:
        """日度决策审计报告"""
        events = await self.audit_store.query_time_range(
            datetime.combine(date, time.min),
            datetime.combine(date, time.max),
        )

        return Report(
            title=f"AI 决策审计日报 - {date.isoformat()}",
            sections=[
                self._summary_section(events),
                self._autonomous_decisions_section(events),
                self._human_overrides_section(events),
                self._high_risk_actions_section(events),
                self._strategy_lifecycle_section(events),
                self._anomaly_section(events),
            ],
            metadata={
                "generated_at": datetime.now().isoformat(),
                "system_version": SYSTEM_VERSION,
                "report_type": "daily_decision_audit",
                "regulatory_framework": "FINRA_2026 / 证监会AI监管指引",
            },
        )
```

---

### OPT-12：自适应资源调度

**问题诊断**：
当前调度间隔固定，不根据市场活跃度、系统负载或策略产出效率动态调整。

**目标**：
实现基于多维信号的自适应调度，在高价值时段加密运行，低价值时段节省资源。

```python
class AdaptiveScheduler:
    """自适应资源调度器"""

    def __init__(self, base_interval: float, config: AdaptiveConfig):
        self.base_interval = base_interval
        self.config = config
        self._market_activity_score = 0.5   # 0-1
        self._system_load_score = 0.5       # 0-1
        self._productivity_score = 0.5      # 0-1

    def compute_adaptive_interval(self) -> float:
        """计算自适应间隔"""
        # 市场活跃度高 → 缩短间隔
        market_factor = 1.0 - (self._market_activity_score - 0.5) * 0.6

        # 系统负载高 → 延长间隔
        load_factor = 1.0 + max(0, self._system_load_score - 0.7) * 2.0

        # 产出效率低 → 适度延长
        productivity_factor = 1.0 + max(0, 0.3 - self._productivity_score) * 1.5

        adjusted = self.base_interval * market_factor * load_factor * productivity_factor

        # 限制在合理范围内
        return max(self.config.min_interval, min(self.config.max_interval, adjusted))

    async def update_signals(self):
        """更新自适应信号"""
        self._market_activity_score = await self._compute_market_activity()
        self._system_load_score = await self._compute_system_load()
        self._productivity_score = await self._compute_productivity()
```


---

## 七、实施计划与里程碑

### 7.1 Phase 1 实施计划（4 周）

```
Week 1                    Week 2                    Week 3                    Week 4
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│ OPT-03 调度器   │  │ OPT-01 辩论框架 │  │ OPT-01 辩论框架 │  │ OPT-04 审计追踪 │
│ - 交易日历      │  │ - Agent 角色定义 │  │ - 集成到提交流程│  │ - 存储层实现    │
│ - 断路器增强    │  │ - 辩论编排器    │  │ - 测试验证      │  │ - 装饰器集成    │
│ - EMA 持久化    │  │ - 共识记录      │  │                 │  │ - 查询 API      │
├─────────────────┤  ├─────────────────┤  ├─────────────────┤  ├─────────────────┤
│ OPT-02 可解释性 │  │ OPT-02 可解释性 │  │                 │  │                 │
│ - Tracer 核心   │  │ - Renderer 实现 │  │                 │  │                 │
│ - 数据模型      │  │ - 集成到决策点  │  │                 │  │                 │
└─────────────────┘  └─────────────────┘  └─────────────────┘  └─────────────────┘
```

**Phase 1 交付物**：
- [ ] `ChinaTradingCalendar` 类 + 2026 年日历数据
- [ ] `EnhancedCircuitBreaker` 含 Half-Open + 指数退避
- [ ] EMA 饥饿保护 + 状态持久化
- [ ] `DebateOrchestrator` + 3 个分析师 Agent + 风控裁判
- [ ] `ExplainabilityTracer` + `ExplanationRenderer`
- [ ] `AuditTrailStore` + 审计装饰器
- [ ] 单元测试覆盖率 > 80%
- [ ] 集成测试：完整策略提交流程含辩论 + 可解释性 + 审计

### 7.2 Phase 2 实施计划（6 周）

**Phase 2 交付物**：
- [ ] `EventDrivenEngine` + `EventBus` + 3 类事件源
- [ ] `MarketDataStream` + 流处理器框架
- [ ] `ChinaMarketRules` 完整规则引擎
- [ ] `MultiTimeframeSignalAggregator`
- [ ] `HybridScheduler`（批次 + 事件混合调度）
- [ ] 性能基准：事件响应延迟 < 500ms

### 7.3 Phase 3 实施计划（8 周）

**Phase 3 交付物**：
- [ ] `OnlineStrategyOptimizer` + 奖励信号计算
- [ ] `CrossOrgAgentGateway` + 安全通信协议
- [ ] `RegulatoryReportGenerator` + 4 类报告模板
- [ ] `AdaptiveScheduler` + 多维信号融合
- [ ] 端到端集成测试
- [ ] 性能与安全审计

### 7.4 成功指标

| 指标 | 当前基线 | Phase 1 目标 | Phase 3 目标 |
|------|----------|-------------|-------------|
| 策略提交质量（孵化存活率） | ~60% | 75% | 85% |
| 决策可追溯率 | ~40% | 95% | 100% |
| 事件响应延迟 | N/A（批次） | — | < 500ms |
| 系统级 Agent 成熟度 | L3.5 | L4.5 | L5.5 |
| FINRA 合规就绪度 | 部分 | 基本就绪 | 完全就绪 |
| 多 Agent 协作深度 | 委派级 | 辩论级 | 协商级 |


---

## 八、技术风险与缓解措施

| 风险 | 影响 | 概率 | 缓解措施 |
|------|------|------|----------|
| 多 Agent 辩论增加延迟 | 策略提交周期变长 | 高 | 设置辩论超时（30s）；非关键路径异步执行；并行调用 |
| 事件风暴导致系统过载 | 服务降级 | 中 | 事件节流 + 优先级队列 + 背压机制 + 降级到批次模式 |
| RL 在线优化过拟合 | 策略参数漂移 | 中 | 参数变化幅度限制 + 定期重置基线 + regime-aware 约束 |
| 审计数据量增长过快 | 存储成本 | 中 | 分层存储（热/温/冷）+ 自动归档 + 摘要压缩 |
| 跨组织通信安全 | 数据泄露/LPCI 攻击 | 低 | 零信任架构 + 数据脱敏 + 签名验证 + 持久记忆隔离 |
| 流式数据源不稳定 | 信号中断 | 中 | 多源冗余 + 降级到批次模式 + 数据质量检测 |
| 辩论 Agent 共识陷阱 | 决策质量下降 | 中 | Devil's Advocate 机制 + 市场状态自适应辩论模式 |
| EU AI Act 合规时间线 | 合规风险 | 低 | 高风险 AI 期限已延至 2027.12，但应提前准备 |

---

## 九、与 Hermes 能力基线的关系

本优化方案的所有新增能力均遵循 `docs/architecture/hermes-boundary.md` 的边界决策：

1. **不引入 Hermes 运行时依赖**：所有新模块在 `packages/agent` 或 `packages/strategy-factory` 下原生实现
2. **扩展 agent_* 工具表面**：新增工具遵循 `agent_` 前缀命名规范
3. **更新能力对等矩阵**：新能力超越 Hermes 基线的部分标记为 `aiask_extension`
4. **保持 finance_safe 默认模式**：高风险新能力（如 RL 在线优化）需要显式启用

**新增工具注册建议**：

```python
# 新增到 FINANCE_SAFE_TOOL_CATALOG
{
    "name": "agent_debate_run",
    "capability": "multi_agent_debate",
    "category": "financial_decision",
    "side_effect": "read_only",
    "description": "Run a multi-agent debate on a financial decision topic.",
},
{
    "name": "agent_explain_decision",
    "capability": "decision_explainability",
    "category": "financial_read",
    "side_effect": "read_only",
    "description": "Retrieve the explainability trace for a past decision.",
},
{
    "name": "agent_audit_query",
    "capability": "audit_trail_query",
    "category": "compliance",
    "side_effect": "read_only",
    "description": "Query the audit trail for compliance and review purposes.",
},
{
    "name": "agent_event_subscribe",
    "capability": "event_subscription",
    "category": "financial_stateful",
    "side_effect": "stateful",
    "description": "Subscribe to real-time market or system events.",
},
{
    "name": "agent_signal_aggregate",
    "capability": "signal_aggregation",
    "category": "financial_read",
    "side_effect": "read_only",
    "description": "Aggregate multi-timeframe trading signals for a symbol.",
},
```

---

## 十、总结

本优化方案将 AIASK 金融系统级 Agent 从当前的 **L3.5 成熟度**
（强金融推理 + 强自主执行，但多 Agent 协作和实时性不足）
提升至 **L5.5 成熟度**（完整的系统级 Agent），具体体现为：

1. **从单体决策到多角色辩论**（OPT-01）：引入专业化 Agent 团队
2. **从黑盒到全链路可解释**（OPT-02）：满足监管审计要求
3. **从固定调度到事件驱动**（OPT-05/06）：实时市场响应能力
4. **从离线训练到在线优化**（OPT-09）：持续自我改进
5. **从单组织到跨组织协作**（OPT-10）：开放生态能力
6. **从人工报告到自动合规**（OPT-11）：降低合规成本

这些优化使系统完全符合 Salesforce 定义的"系统级 AI"五大支柱，
同时满足 FINRA 2026 对金融 AI Agent 的监管要求。

---

## 参考来源

- [Salesforce AI Research: System-Level AI](https://www.salesforce.com/ap/blog/system-level-ai/) — 系统级 AI 定义
- [FINRA 2026 Annual Regulatory Oversight Report](https://www.finra.org/rules-guidance/guidance/reports/2026-finra-annual-regulatory-oversight-report/gen-ai) — 金融 AI 监管要求
- [EU AI Act High-Risk Obligations](https://fintech.global/2026/05/07/eu-ai-act-three-obligations-reshaping-comms-surveillance/) — 可追溯性、文档化、可审计性三大义务（高风险 AI 合规期限已延至 2027 年 12 月）
- [McKinsey: Agentic AI in Banking](https://www.mckinsey.com/capabilities/risk-and-resilience/our-insights/how-agentic-ai-can-change-the-way-banks-fight-financial-crime) — KYC/AML Agent 实践
- [TradingAgents: Multi-Agent LLM Trading](https://tradingagents-ai.github.io/) — 多 Agent 交易框架（Bull/Bear 辩论机制）
- [FinDebate: Multi-Agent Collaborative Intelligence](https://arxiv.org/html/2509.17395) — 五专业 Agent 并行辩论 + RAG 架构
- [Market-Dependent Communication](https://arxiv.org/html/2511.13614v1) — 竞争/协作通信模式与市场状态的关系
- [QuantAgent: Multi-Agent HFT](https://arxiv.org/html/2509.09995v3) — 高频多 Agent 架构（Indicator/Pattern/Trend/Risk 四 Agent）
- [Regime-Aware RL for Portfolio](https://arxiv.org/html/2509.14385v1) — 市场状态感知的 RL 组合优化
- [Graph Attention Multi-Agent DRL](https://www.nature.com/articles/s41598-025-32408-w) — 图注意力异构多 Agent 自适应组合优化
- [ACP: Unified Agent Communication Protocol](https://arxiv.org/abs/2602.15055) — 跨组织 Agent 安全通信协议（零信任）
- [CSA: Zero Trust for AI Agents](https://cloudsecurityalliance.org/blog/2025/09/12/fortifying-the-agentic-web-a-unified-zero-trust-architecture-against-logic-layer-threats) — Agent 零信任安全架构
- [Forbes: Agentic AI in Financial Industry](https://forbes.com/sites/zennonkapron/2025/04/23/agentic-ai-the-rise-of-autonomous-decisions-in-the-financial-industry) — 金融 Agent 趋势
- [Google Cloud: AI Agents in Financial Services](https://cloud.google.com/transform/new-research-shows-how-ai-agents-are-driving-value-for-financial-services) — 金融 Agent 价值
- [AWS: Preparing for Agentic AI in Financial Services](https://aws.amazon.com/blogs/security/preparing-for-agentic-ai-a-financial-services-approach/) — 安全控制框架
- [AWS: Timeouts, Retries and Backoff with Jitter](https://aws.amazon.com/builders-library/timeouts-retries-and-backoff-with-jitter/) — 指数退避 + 抖动最佳实践
- [CFA Institute: Agentic AI for Finance](https://rpc.cfainstitute.org/research/the-automation-ahead-content-series/agentic-ai-for-finance) — 投资领域 Agent 应用
- [Zartis: AI in Banking Audit Trails](https://www.zartis.com/ai-in-banking-why-audit-trails-are-architecture-not-afterthought/) — 审计追踪是架构而非事后补丁
- [a-trade-calendar (PyPI)](https://pypi.org/project/a-trade-calendar/) — A 股交易日历 Python 库
- [akshare (PyPI)](https://pypi.org/project/akshare/) — A 股数据接口（含交易日历 API）

> 内容基于上述来源重新组织和表述，以符合内容合规要求。

---

## 附录：验证清单

本方案经过以下维度的深度验证：

| 验证维度 | 结论 | 备注 |
|----------|------|------|
| 断路器 Half-Open 模式 | ✅ 符合行业标准 | Closed→Open→Half-Open 三态是标准模式（Cisco、Azure、AWS 均推荐） |
| 指数退避 + 抖动 | ✅ 已修正为 Full Jitter | AWS Builder's Library 推荐 `random(0, min(cap, base*2^n))` |
| 多 Agent 辩论架构 | ✅ 有学术支撑 | FinDebate（5 Agent）、TradingAgents（Bull/Bear 辩论）均已验证有效 |
| 辩论模式需市场自适应 | ⚠️ 已补充 | arxiv 2511.13614 证明竞争/协作模式效果取决于市场波动率 |
| 可解释性/审计追踪 | ✅ 监管硬性要求 | FINRA 2026 + EU AI Act + FCA 均明确要求 |
| EU AI Act 时间线 | ⚠️ 已修正 | 高风险 AI 合规期限从 2026.08 延至 2027.12（2026.05 修正案） |
| A 股交易日历 | ✅ 有现成库 | `a-trade-calendar`（PyPI）或 akshare 内置 API |
| T+1 规则影响 | ⚠️ 已补充深层影响 | 不仅是"不能卖"，还影响开盘定价和日内策略有效性 |
| 跨组织 Agent 协议 | ✅ 有标准化进展 | ACP（arxiv 2602.15055）+ A2A + Coral Protocol |
| Agent 零信任安全 | ✅ 行业共识 | CSA 2025 报告 + Agent Trust Protocol (ATP) |
| RL 在线组合优化 | ✅ 有最新研究支撑 | Nature 2025 + Springer 2026 均验证 regime-aware 方法有效 |
| 事件驱动架构 | ✅ 成熟模式 | Python asyncio + EDA 是机构级交易系统标准 |
