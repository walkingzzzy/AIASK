# 策略工厂 Stock-First 多策略路由改造方案

日期：2026-06-03
版本：SF-ROUTER-V1
关联文档：
- `策略工厂实际架构现状梳理-2026-06-02.md`（ARCH-MAP：漏斗原罪）
- `策略工厂倒置架构设计方案-2026-06-02.md`（observe farm：怎么观察/选择）
- `策略工厂Alpha源接线修复方案-2026-06-03.md`（alpha 接线：因子接回生成链）
- `策略工厂修复进度总览-2026-06-03.md`（已完成 commit 链）

> 产生方式：sequential-thinking MCP 深度思考（7 轮）+ 逐函数代码勘察。

---

## 0. 一句话结论

当前架构的真问题**不是"策略类型太少"或"没按周期孵化"**（这两项的基础设施其实已存在），
而是**生成驱动方向错了**：spawn 是 **market-first（自上而下从大盘宏观信号生成）**，
把全市场塞进一条狭窄通道，产出同质的少数策略族，硬套到一批股票上 ——
**个股自身的实际情况从未被当作生成的主驱动**。

解决方案：把生成倒成 **stock-first（自下而上：逐股诊断 → 该股票现在适合哪种类型/周期 →
生成匹配的多类型候选）**，全部走已建好的宽进 observe + 多频孵化，
积累"命中率 by 类型×regime×周期"知识矩阵。

---

## 1. 根因诊断（market-first 单通道，附代码证据）

### 1.1 当前 spawn 是 market-first

`domain/spawner_parts/serialization.py` 的 spawn lane：
- `_from_fear_greed` / `_from_factor_ic` / `_from_factor_pool` / `_from_volatility`
  / `_from_event_driven` / `_from_fund_flow`
- **全部以 snapshot（全市场宏观快照）为输入** → 产出"市场层面"候选 →
  再用 `_resolve_target_codes` 套一批股票。

含义：它先问"今天大盘什么状态（恐贪/波动/因子IC趋势）"，据此选一个策略族，
再找一批股票套上去。**同一时刻全市场共享同一套宏观信号**，必然倾向生成
同质的、少数几个策略族的候选 —— 这就是"狭窄通道"的代码根因。

### 1.2 个股的"实际情况"没有进入生成主驱动

用户要的：这只股票此刻是趋势中？超卖？放量突破？有新闻催化？估值低位？
→ 据此生成它**适配**的策略类型。

现状：个股状态没被用来**决定生成什么**。逐股矩阵 `StockStrategyMatrixPlanner`
虽是 stock-first 的载体，但（a）默认 OFF，（b）是"给每只股票套同一组固定 family"，
**不是诊断驱动**。

---

## 2. 已有零件盘点（避免从零造，诚实区分）

| 能力 | 现状 | 落点 |
|---|---|---|
| 多策略族注册表 | ✅ 已覆盖趋势/均值回归/突破/多因子/宏观/轮动等 | `FACTOR_STRATEGY_MAPPING` / spawner families |
| 周期分档孵化 | ✅ 已分 high/medium/low frequency 三档（min_days 20/30/45，horizon 5/10/20） | `forward_verifier.INCUBATION_PROFILES` |
| holding_period_bucket | ✅ short/medium/long 贯穿 spawn→dedup→孵化 | `domain/strategy_profile.py` |
| 逐股矩阵（stock-first 载体） | 🟡 存在但默认 OFF + 非诊断驱动 | `application/stock_strategy_matrix.py` |
| 个股诊断工具 | ✅ MCP 工具齐全 | `smart_stock_diagnosis` / `build_stock_context` / `calculate_technical_indicators` / `get_factor_profile` / 估值工具 |
| regime 标签 | ✅ P1-D 已加（trend/vol/sentiment） | `forward_verifier` + `reporting.py` |
| 宽进 observe + 严出 | ✅ 已建（P1-A / PromotionGate / 跨regime门） | 倒置架构成果 |

**结论：~60% 零件已在。真正缺的是"诊断 → 类型路由"这座桥。**
SF-ROUTER 不是推倒重来，是**把生成驱动倒过来 + 把已有零件接对**。

---

## 3. 核心设计：个股诊断 → 策略类型路由器

### 3.1 StockRegimeProfile（个股状态画像）

对每只候选股票，用已有指标/MCP 算出多维状态（带置信度）：
- **技术态**：趋势强度（ADX/均线斜率）、动量（动量因子/RSI）、波动率档（ATR 分位）、位置（距均线/前高前低）。
- **价量结构**：突破 / 缩量整理 / 放量、流动性（换手率）。
- **事件/新闻**：催化（公告/研报/北向异动）、情绪极性。
- **基本面/估值**：ROE/现金流/估值分位（判断是否适合中长线价值）。

### 3.2 StockStrategyRouter（类型路由表）

输入 StockRegimeProfile → 输出"适配 family 集合 + holding_bucket + 置信度 + **排除项**"。
先用透明可解释的 if/score 规则（可单测）。映射对齐用户列举的 4 大类 × 3 周期：

| 个股状态 | 路由策略类型 | 周期 |
|---|---|---|
| 强趋势 + 动量正 + 放量突破 | 趋势跟随（momentum/ma_cross/volatility_breakout/event_structure_breakout） | 波段 medium |
| 超卖 + 缩量止跌 + 无基本面恶化 | 均值回归（mean_reversion_short/rsi/gap_fill） | 短线 short |
| 估值低位 + ROE 稳 + 行业景气 | 价值/质量/成长因子（value/quality/growth_factor） | 中长线 long |
| 多因子 IC 共振 | 多因子（multi_factor） | medium/long |
| 事件催化 + 情绪发酵 | 事件驱动 / 轮动（event_structure_breakout/sector_rotation） | 短/波段 |
| 高流动性 + 微观失衡（可选） | 日内/超短（A股 T+1 仅研究观察，不实盘） | 日内 |

**关键：排除项**。震荡股显式排除趋势策略、低流动性股排除日内 ——
这正是"减少狭窄通道误杀"、让合适策略真正能进孵化的机制。

### 3.3 接入点

Router 画像直接喂逐股矩阵：`StockStrategyMatrixPlanner` 不再"套固定 family"，
而是"按 Router 画像为该股票生成它适配的 family + bucket"。
toggle `STRATEGY_FACTORY_STOCK_FIRST_ROUTER_ENABLED`（默认 OFF）。

---

## 4. 分层实施路线（每阶段灰度 toggle + 可单测 + 默认 OFF 零变化）

| 阶段 | 内容 | 性质 | 验收 |
|---|---|---|---|
| **SR-0 诊断契约** | 定义 `StockRegimeProfile` 数据契约；application 层用已有指标/MCP 算出，写进 snapshot per-stock 字段 | 新建（地基，低风险） | 样本股票产出 profile，人工抽查合理 |
| **SR-1 路由器** | `StockStrategyRouter` 规则表：profile → 适配 family+bucket+排除项 | 新建（核心，中风险） | 趋势股→趋势族、超卖股→均值回归族、低估值→价值族；震荡股不被套趋势 |
| **SR-2 多周期孵化** | 路由的多类型候选走宽进 observe + 三频孵化档（复用）；补缺：SignalTracker 采集 5/10/20/40 多 horizon 前向收益；HitRateReporter 加 holding_bucket 切片 | 复用 + 补缺 | observe farm 出现 short/medium/long 三类并行积累 skill_lcb |
| **SR-3 命中率矩阵** | 报表：命中率 by（strategy_type × holding_bucket × regime） | 新建报表 | 回答"AI 在什么股票什么状态下生成的什么类型策略，前向命中率多少" |
| **SR-4 组合层** | `optimize_portfolio`（Markowitz）消费已验证 skill 的单股策略做相关性/配比 | 后置（Layer 4） | 组合级风险/收益优化 |
| **SR-5 日内/超短** | 分钟级前向测量管道；A股 T+1 仅研究观察 | 可选扩展 | 不阻塞主线 |

**建议起点**：SR-0 + SR-1（诊断契约 + 路由器）。这是补"缺的那座桥"，杠杆最高。

---

## 5. 算力/成本现实性（防止纸面方案落地崩盘）

5000+ 股**不能每轮全量逐股诊断**（全套 MCP 诊断单只数秒~数十秒，全市场=数小时且网络密集）。落地必须：

1. **分层 universe**：每轮只诊断"今日值得诊断"的滚动子集（几十~几百只）——
   按流动性/活跃度/事件触发筛，复用已有 universe 筛选 + 事件驱动。
2. **分级诊断**：轻量诊断（纯本地 K线技术指标，快）先跑全子集 → Router 初筛类型 →
   只对初筛通过的少数股票做重诊断（新闻/基本面/回测）。
3. **缓存 + 增量**：诊断结果按股票+日期缓存（复用 `.mcp_cache`）；regime 不日日突变，可隔日复用。
4. **数据新鲜度前置**：依赖 P-C（K线/因子IC 同步），否则诊断基于过期数据 = 错误路由。

**命中率统计现实性**：5000股×多类型×多周期 = 单元极多，样本会稀释。
→ 命中率必须**聚合到"类型×regime×周期"层级**看（而非逐股），个股层只作信号来源。

---

## 6. 与已完成工作的衔接（前面没白做）

倒置架构（observe farm）解决"**怎么观察和选择**"；SF-ROUTER 解决"**生成什么、给谁**"。两者正交互补：

```
SF-ROUTER（本方案·上游）            倒置架构（已完成·下游）
逐股诊断 → 类型路由 → 多类型候选  →  宽进 observe → ForwardVerifier(分regime/分周期)
                                      → ObservationLifecyclePolicy(skill_lcb)
                                      → PromotionGate(前向DSR) → 严出
```

- alpha 接线（gp/rl 因子）、PromotionGate、ObservationLifecyclePolicy、跨regime门 ——
  全部仍有效，正是 SF-ROUTER 的下游。**SF-ROUTER 是在已完成工作的上游补一个"诊断驱动的多类型生成器"。**

---

## 7. 诚实边界

- **是方向性增量改造，不是推倒重来**：~60% 零件已在（逐股矩阵/holding_bucket/三频孵化档/regime标签/个股诊断MCP/PromotionGate）。
- **真正新建**：SR-0 诊断契约 + SR-1 路由器。
- **真正约束（非代码能即时解决）**：
  - 多 horizon（5/10/20/40）前向收益采集 —— 现仅 3D 有数据，长线策略目前算不出命中率。
  - 5000 股逐股诊断的算力/调用成本 —— 必须分层子集 + 分级诊断 + 缓存。
  - 日内/超短在 A股 T+1 下仅能"研究观察"，需分钟级前向管道（SR-5 可选）。
- **不承诺赚钱**：承诺的是"让多类型策略按个股实际情况流动起来，并诚实测出各类型命中率"——
  这正是用户的核心诉求（先确认 AI 生成策略的命中率）。
- **组合优化（第4类）是 portfolio 级**，性质不同于单股生成，后置为 Layer 4，不与单股生成混在一起。

---

## 8. 待用户拍板的决策点

1. **是否从 SR-0 + SR-1 开工**（诊断契约 + 路由器，默认 OFF，可单测）。
2. **诊断子集策略**：每轮诊断多少只、按什么触发（流动性 top-N / 事件驱动 / 自选股）。
3. **路由规则表**：先用透明 if/score 规则（本方案默认），还是后续接 LLM 路由（成本更高）。
4. **多 horizon 采集**：是否同步扩 SignalTracker 到 5/10/20/40（长线策略命中率的前提）。
