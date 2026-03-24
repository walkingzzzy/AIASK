# MCP 服务预测能力增强优化方案

> 归档说明：本文已移入 `docs/plans/archive/`，仅保留历史增强规划与能力差距分析，不再作为当前开发入口。
>
> 编制日期: 2026-03-05
> 版本: v1.0
> 范围: AKShare MCP 服务全模块（因子、策略、回测、风控、数据）

> 校准说明：本文属于 2026-03-05 编制的增强方案与能力规划，主要用于记录当时对 MCP 预测能力的能力盘点、差距识别与优化方向，不应直接视为当前仓库已全部落地的现状说明。
>
> 文中关于“当前系统能力”“增强后能力”“全模块覆盖”等表述，需结合当前代码、运行时审计结果与最近测试产物重新核实；若与现状不一致，应以当前事实为准。


---

## 一、当前系统能力全景

### 1.1 架构总览

```
┌─────────────────────────────────┐
│        AI (Claude/GPT)          │  ← 大脑：推理、分析、预测、综合判断
│  · 自然语言理解与多轮对话        │
│  · 多信号融合与深度推理           │
│  · 上下文记忆与策略建议           │
└──────────┬──────────────────────┘
           │ MCP Protocol (JSON-RPC)
           ▼
┌─────────────────────────────────┐
│      MCP 工具服务层              │  ← 手脚：获取数据、执行计算、返回结构化结果
│  tools/   → 40+ MCP 工具        │
│  services/ → 30+ 业务服务        │
│  core/    → 缓存/限流/验证       │
│  storage/ → TimescaleDB          │
└─────────────────────────────────┘
```

### 1.2 已实现模块成熟度矩阵

| 层级 | 已实现模块 | 成熟度 |
|------|-----------|--------|
| **数据层** | AKShare/Tushare/Baostock/多源降级、TimescaleDB 存储、智能缓存 | 较成熟 |
| **因子层** | 技术因子(25+)、基本面因子(30+)、波动率因子(8)、量价因子(16)、情绪因子 | 中等 |
| **分析层** | IC/IR 分析、分组回测、Walk-Forward/Purged K-Fold 验证、Bootstrap CI | 较好 |
| **策略层** | MA交叉/动量/RSI/买入持有/多因子/宏观择时、策略工厂自动生成/淘汰 | 中等 |
| **回测层** | 基础回测(Numba JIT)、高级回测(止损/仓位管理)、蒙特卡洛、Walk-Forward | 中等 |
| **风控层** | VaR/CVaR、Barra风险分解、压力测试、证据链决策审计 | 基础 |
| **组合层** | 等权/风险平价/均值方差/Black-Litterman 优化 | 基础 |
| **文本层** | 关键词词典情绪分析(40词)、新闻/研报/公告抓取 | 初级 |

### 1.3 核心代码模块清单

```
akshare_mcp/
├── server.py                    # FastMCP 入口，注册 28 个工具模块
├── tools/
│   ├── market/                  # 行情：K线/盘口/涨停/指数/板块
│   ├── news/                    # 资讯：新闻/公告/研报/分析师
│   ├── semantic/                # 语义：NLP选股/产业链/诊断/日报
│   ├── formula_fallback/        # 通用公式回退与指标兼容层
│   ├── managers/                # 30+ Manager：统一编排层
│   ├── decision.py              # should_i_buy / should_i_sell
│   ├── quant.py                 # 因子计算/IC分析/分组回测
│   ├── backtest.py              # 回测引擎入口
│   ├── portfolio.py             # 组合优化
│   ├── sentiment.py             # 情绪分析
│   └── ...                      # alerts/valuation/vector/skills 等
├── services/
│   ├── backtest/                # 回测引擎(JIT+高级+并行)
│   ├── factor_calculator/       # 因子计算器(5个Mixin)
│   ├── strategy_factory.py      # 策略自动生成/淘汰
│   ├── signal_tracker.py        # 信号追踪/前瞻验证
│   ├── llm_alpha.py             # 文本信号/因子挖掘(规则版)
│   ├── multi_factor.py          # 多因子框架
│   ├── risk_model.py            # 风险模型
│   ├── validation.py            # WalkForward/PurgedKFold/Bootstrap
│   ├── evidence_chain.py        # 证据链决策审计
│   └── ...                      # 30+ 其他服务
├── core/                        # 缓存/限流/重试/向量化指标
├── data_source/                 # 多源数据管理(Tushare/AKShare/Baostock 等)
└── storage/timescaledb/         # DB 存储层
```

---

## 二、架构约束分析：AI 调用 MCP 的设计本质

### 2.1 核心架构约束

本系统是 **AI 通过 MCP 协议调用工具服务**，这决定了优化方案必须遵循以下约束：

| 约束 | 含义 | 影响 |
|------|------|------|
| **AI 是推理层** | Claude/GPT 负责理解、分析、预测、综合判断 | MCP 工具不应替代 AI 做预测决策 |
| **MCP 工具是计算层** | 工具负责获取数据、执行统计计算、返回结构化 JSON | 工具应返回丰富原材料而非硬编码结论 |
| **轻量级进程** | MCP 服务作为 stdio 子进程运行，无 GPU、无持久化训练管道 | 不适合承载重型 ML 推理 |
| **同步调用模式** | AI 调一次工具拿一次结果，无流式推送 | 工具应一次返回足够丰富的数据 |
| **AI 原生 NLP 能力** | AI 本身就是最强的 NLP 引擎 | MCP 工具只需提供原始文本，无需内置 NLP 模型 |

### 2.2 当前设计问题：MCP 工具越权做决策

以 `should_i_buy` 为例，当前设计让 MCP 工具自己做判断：

```python
# 当前设计（问题）：工具内硬编码评分逻辑
if pe and 0 < pe < 15:
    score += 25        # 硬编码阈值
    reasons.append('估值偏低')
elif pe and pe >= 50:
    score -= 15        # AI 完全无法干预这个判断

# 最终返回一个打包好的结论
return {"recommendation": "buy", "score": 75}
```

**问题**：
- AI 拿到的是一个已经被硬编码规则决定的结论，失去了自主推理的空间
- PE < 15 是否算"低估"取决于行业、周期、增速，硬编码阈值无法覆盖
- AI 本身有远超 if/else 的推理能力，但被 MCP 工具的硬编码逻辑架空了

### 2.3 正确的职责分工

```
MCP 工具（提供数据 + 统计上下文）     AI（推理 + 判断）
──────────────────────────────     ─────────────────
PE = 12.3                          →  "相对行业中位数18.5偏低23%，
行业中位数 PE = 18.5                    但考虑到增速放缓，
3年PE历史分位 = 23%                     低估程度有限"
同行PE范围 = [8.2, 45.6]
营收增速 = -5.2%（放缓）

RSI = 28.5                         → "RSI进入超卖区间，
历史超卖后10日回升概率 = 72%             结合历史72%反弹概率
近30日RSI序列 = [45, 38, 32, 28.5]     和MACD即将金叉，
                                       短期反弹概率较大"
MACD柱状图 = [-0.3, -0.15, -0.02]
趋势 = 柱状图收窄，接近金叉
```

---

## 三、核心问题诊断

### 3.1 预测能力瓶颈（按严重程度排序）

| # | 问题 | 影响范围 | 严重度 |
|---|------|---------|--------|
| 1 | **因子只输出单点值，无时间序列/截面分布/历史分位** | 全部因子工具 | 致命 |
| 2 | **MCP 工具硬编码评分规则，AI 推理能力被架空** | decision/diagnosis | 严重 |
| 3 | **多因子模型 z-score 用全局数据，存在前视偏差** | multi_factor/backtest | 严重 |
| 4 | **LLM Alpha 模块是 40 词的词袋模型，无语义理解** | llm_alpha.py | 严重 |
| 5 | **因子无截面排名信息，AI 无法判断个股在全市场的相对位置** | 因子层 | 较大 |
| 6 | **缺少历史相似形态匹配** | 技术分析 | 较大 |
| 7 | **情绪分析仅基于价格波动，未利用新闻文本** | sentiment/diagnosis | 中等 |

### 3.2 策略引擎缺陷

| # | 问题 | 文件 |
|---|------|------|
| 8 | 策略生成全靠 if/else 硬编码规则 | strategy_factory.py |
| 9 | 回测仅满仓操作，Kelly/波动率仓位管理只是线性缩放 | advanced.py |
| 10 | MACD/TRIX 计算 O(n^2)，嵌套 EMA 重复从头计算 | technical.py |
| 11 | RSI 使用 SMA 而非标准 Wilder EMA | technical.py / strategies.py |
| 12 | 蒙特卡洛假设正态分布，忽略 A 股尖峰厚尾 | engine.py |
| 13 | Sharpe 未扣除无风险利率 | engine.py |

### 3.3 架构层问题

| # | 问题 | 影响 |
|---|------|------|
| 14 | factor_analysis 与 multi_factor 重复实现 IC 计算 | 维护负担 |
| 15 | validation.py 的 FactorValidationPipeline 未接入策略生命周期 | 验证缺位 |
| 16 | risk_model 与 strategy_factory 未集成 | 淘汰检查不完整 |
| 17 | 证据链内存缓存无上限（_CHAINS dict） | 内存泄漏 |
| 18 | 信号追踪串行遍历所有策略×所有股票 | 性能瓶颈 |

---

## 四、优化方案（六大方向）

### 方向一：重构因子输出——给 AI 提供"完整画像"而非"单个数字"

**优先级: P0 | 工作量: 2-3 周**

#### 4.1.1 问题本质

当前因子计算器的所有方法只返回一个 `float`：

```python
# 现在：AI 拿到一个孤立的数字，缺乏上下文
def calculate_momentum(self, closes, period=20):
    return (closes[-1] - closes[-period]) / closes[-period]  # → 0.083
```

AI 拿到 `momentum = 0.083` 后无法判断：这算高还是低？在行业中什么位置？历史上什么分位？趋势是增强还是减弱？

#### 4.1.2 优化设计

每个因子增加 `profile` 模式，一次性返回因子的完整画像：

```python
@mcp.tool()
async def get_factor_profile(
    code: str,
    factors: list[str],          # ["momentum", "rsi", "pe", "roe"]
    lookback: int = 60,          # 历史序列长度
    cross_section: bool = True,  # 是否计算截面排名
):
    """获取股票的因子完整画像

    Returns:
        {
            "momentum_20d": {
                "current": 0.083,
                "series_30d": [0.02, 0.04, ..., 0.083],  # 近30日时间序列
                "percentile_1y": 0.72,                    # 1年历史分位
                "percentile_3y": 0.65,                    # 3年历史分位
                "industry_rank": 15,                      # 行业排名
                "industry_total": 89,                     # 行业总数
                "market_percentile": 0.81,                # 全市场分位
                "trend": "strengthening",                 # 趋势方向
                "z_score_rolling": 1.23,                  # 滚动z-score
            },
            "rsi_14": {
                "current": 28.5,
                "series_30d": [52, 45, 38, 32, 28.5],
                "signal": "oversold",
                "historical_oversold_recovery": {
                    "count": 12,                          # 历史超卖次数
                    "avg_10d_return": 0.068,              # 超卖后10日平均收益
                    "recovery_rate": 0.72,                # 回升概率
                },
            },
            ...
        }
    """
```

#### 4.1.3 关键改造点

| 改造项 | 说明 |
|--------|------|
| 因子计算器增加序列输出 | 所有方法增加 `as_series=True` 参数，返回 ndarray |
| 新增截面排名服务 | 按行业/全市场计算因子分位，需预计算或缓存 |
| 新增历史分位服务 | 计算因子值在自身历史中的分位数 |
| 新增条件统计服务 | "当 RSI < 30 时，未来 N 日收益分布"的历史统计 |
| 因子注册装饰器 | 自动收集因子元数据（名称、类别、输入参数、值域） |

#### 4.1.4 对 AI 的增强效果

AI 拿到完整因子画像后，可以做出远超硬编码规则的判断：
- "该股 PE 为 12.3，在行业中排名第 8/89（前 9%），处于自身 3 年历史 23% 分位，营收增速 -5.2% 正在放缓 → 低估可能是增速下滑的合理定价而非机会"
- "RSI 28.5 进入超卖区，历史 12 次超卖中有 72% 在 10 日内回升，平均回升幅度 6.8%，当前 MACD 柱状图正在收窄 → 短期反弹概率较大"

---

### 方向二：新增历史形态匹配与条件概率工具

**优先级: P0 | 工作量: 2 周**

#### 4.2.1 设计理念

这是最适合 MCP 架构的"预测增强"方式——不让 MCP 工具自己预测，而是提供**历史统计证据**让 AI 做概率推理。

#### 4.2.2 新增工具

```python
@mcp.tool()
async def get_conditional_returns(
    code: str,
    conditions: dict,
    forward_days: list[int] = [5, 10, 20],
):
    """条件收益率统计：当满足指定条件时，历史上未来N日的收益分布

    Args:
        code: 股票代码
        conditions: 条件字典，如：
            {"rsi_14": "<30", "macd_histogram": ">0", "volume_ratio": ">1.5"}
        forward_days: 计算未来几日的收益

    Returns:
        {
            "condition_matches": 18,          # 历史满足条件次数
            "forward_returns": {
                "5d":  {"mean": 0.032, "median": 0.028, "win_rate": 0.72,
                        "std": 0.045, "worst": -0.08, "best": 0.12},
                "10d": {"mean": 0.048, "median": 0.041, "win_rate": 0.67, ...},
                "20d": {"mean": 0.061, "median": 0.055, "win_rate": 0.61, ...},
            },
            "recent_matches": [               # 最近3次匹配的实际结果
                {"date": "2025-11-20", "5d_return": 0.035, "10d_return": 0.052},
                ...
            ]
        }
    """

@mcp.tool()
async def find_similar_patterns(
    code: str,
    lookback: int = 20,
    top_k: int = 5,
    method: str = "dtw",
):
    """K线形态相似度搜索：找到历史上与当前形态最相似的时期

    Returns:
        {
            "similar_periods": [
                {
                    "start_date": "2024-03-15",
                    "similarity": 0.92,
                    "subsequent_5d_return": 0.045,
                    "subsequent_10d_return": 0.067,
                    "subsequent_20d_return": 0.031,
                    "market_regime": "震荡上行",
                },
                ...
            ],
            "aggregate_prediction": {
                "avg_10d_return": 0.041,
                "win_rate": 0.80,
                "confidence": "medium",
            }
        }
    """

@mcp.tool()
async def get_signal_hit_rate(
    signal_type: str,
    lookback_years: int = 3,
    universe: str = "all",
):
    """信号历史命中率统计：某类技术信号在历史上的实际表现

    Args:
        signal_type: "macd_golden_cross" | "rsi_oversold" | "ma_bullish_alignment" | ...

    Returns:
        {
            "signal": "macd_golden_cross",
            "total_occurrences": 1523,
            "5d_win_rate": 0.58,
            "10d_win_rate": 0.62,
            "20d_win_rate": 0.55,
            "avg_10d_return": 0.023,
            "by_market_regime": {
                "bull": {"count": 480, "10d_win_rate": 0.72},
                "bear": {"count": 390, "10d_win_rate": 0.48},
                "sideways": {"count": 653, "10d_win_rate": 0.61},
            }
        }
    """
```

#### 4.2.3 对 AI 的增强效果

AI 可以做**基于证据的概率推理**：
- "MACD 金叉信号在震荡市中历史命中率 61%，当前市场为震荡格局"
- "当前形态与 2024-03-15 相似度 92%，当时后 10 日上涨 6.7%"
- "满足 RSI<30 且量比>1.5 的条件在历史上出现过 18 次，10 日胜率 67%"

---

### 方向三：NLP 文本数据增强——让 AI 发挥原生 NLP 能力

**优先级: P1 | 工作量: 1-2 周**

#### 4.3.1 架构适配分析

| 方案 | 是否适合 MCP | 原因 |
|------|-------------|------|
| 在 MCP 内运行 FinBERT 模型 | 不适合 | 需 GPU，400MB 模型文件，推理延迟高 |
| MCP 返回原始文本，AI 自己做 NLP | **最适合** | AI (Claude) 本身就是顶级 NLP 引擎 |
| MCP 做关键词统计 + AI 做语义理解 | 适合 | 轻量计算 + AI 深度分析 |

#### 4.3.2 优化设计

```python
@mcp.tool()
async def get_stock_text_signals(
    code: str,
    days: int = 7,
    include_full_text: bool = True,
):
    """获取股票相关的新闻/公告/研报文本，供 AI 分析

    设计理念：MCP 负责数据采集与结构化，AI 负责语义理解与判断

    Returns:
        {
            "news": [
                {"date": "2026-03-05", "title": "...", "source": "...",
                 "text": "...",                           # AI 直接分析原文
                 "keyword_hits": ["增持", "业绩预增"]},    # 简单关键词辅助
                ...
            ],
            "notices": [
                {"date": "...", "title": "...", "type": "业绩预告",
                 "text": "..."}
            ],
            "research_reports": [
                {"date": "...", "title": "...", "institution": "...",
                 "rating": "买入", "target_price": 45.0,
                 "summary": "..."}
            ],
            "text_statistics": {
                "news_count_7d": 15,
                "news_count_30d": 42,
                "volume_trend": "increasing",              # 舆情量趋势
                "positive_keyword_ratio": 0.65,            # 正面关键词比例
                "negative_keyword_ratio": 0.12,
                "event_types_detected": ["高管增持", "业绩预增"],
            }
        }
    """

@mcp.tool()
async def get_market_sentiment_context(
    scope: str = "market",
):
    """获取市场级别情绪上下文数据

    Returns:
        {
            "fear_greed_index": 35,
            "northbound_flow_5d": -52.3,    # 亿元
            "margin_balance_change_5d": -1.2,
            "limit_up_count_today": 45,
            "limit_down_count_today": 12,
            "turnover_ratio_vs_20d_avg": 0.85,
            "sector_rotation_signal": {
                "inflow_sectors": ["新能源", "半导体"],
                "outflow_sectors": ["房地产", "白酒"],
            },
            "recent_market_headlines": [     # 供 AI 分析的市场要闻
                {"date": "...", "title": "...", "text": "..."},
                ...
            ]
        }
    """
```

#### 4.3.3 对 AI 的增强效果

- AI 直接阅读原始新闻文本，用自身的语义理解能力分析（远超 40 个关键词的词袋模型）
- AI 可以理解"不利好"≠"利好"、"否认收购"≠"收购"等复杂语义
- AI 可以综合多条新闻做事件推理："高管连续增持 + 业绩预增 + 行业政策利好 → 多维度正面信号"

---

### 方向四：因子计算与回测引擎修复

**优先级: P0 | 工作量: 2-3 周**

#### 4.4.1 因子计算修复

| 修复项 | 当前问题 | 修复方案 |
|--------|---------|---------|
| RSI 标准 | 使用 SMA 而非 Wilder EMA | 改用 Wilder 指数平滑 |
| MACD 性能 | O(n^2) 嵌套 EMA | 改为单次遍历 O(n) 增量 EMA |
| TRIX 性能 | 同上 | 同上 |
| z-score 前视偏差 | 全局数据标准化 | 改为 expanding/rolling 窗口 |
| ADOSC | fast/slow EMA 实际用 SMA | 改用真正 EMA |
| ATR | SMA 平均 | 增加 Wilder EMA 版本 |

#### 4.4.2 新增因子

| 因子 | 类别 | 说明 |
|------|------|------|
| Parkinson 波动率 | 波动率 | 基于 High/Low 的波动率估计，比 close-close 更准 |
| Garman-Klass 波动率 | 波动率 | 综合 OHLC 的波动率估计 |
| 波动率比率 | 波动率 | VOL_5D/VOL_60D，捕捉波动率变化 |
| Piotroski F-Score | 基本面 | 9 维财务健康度评分 |
| Altman Z-Score | 基本面 | 破产风险评分 |
| DuPont 分解 | 基本面 | ROE = 净利率 × 周转率 × 杠杆 |
| OBV 变化量 | 量价 | N 日 OBV 变化（替代全历史累积） |
| 相对 PE/ROE | 基本面 | 相对行业中位数的因子 |

#### 4.4.3 回测引擎增强

| 增强项 | 说明 |
|--------|------|
| **真正的仓位管理** | Kelly 参数从实际交易记录提取，在仿真循环中动态调整下单股数 |
| **Block Bootstrap** | 保留 A 股序列自相关和尖峰厚尾特征，替代正态分布假设 |
| **基准对比** | 回测结果增加沪深300基准的超额收益和信息比率 |
| **更多绩效指标** | Sortino Ratio、Calmar Ratio、Omega Ratio、最大连续亏损天数 |
| **Sharpe 修正** | 扣除无风险利率（1年期国债收益率） |
| **换手率成本** | 计算策略换手率并扣除交易成本对净值的影响 |

---

### 方向五：风险模型与决策系统升级

**优先级: P1 | 工作量: 2 周**

#### 4.5.1 风险模型增强

| 增强项 | 说明 |
|--------|------|
| 参数法 VaR | 增加正态分布/t 分布/Cornish-Fisher 修正 |
| 蒙特卡洛 VaR | 基于 EWMA 波动率模型的模拟 |
| Barra 自动化 | 与 FactorCalculator 集成，自动计算因子暴露 |
| 历史情景重现 | 2015 股灾 / 2020 疫情 / 2024 量化踩踏 |
| 集成到策略淘汰 | strategy_factory 的 EliminationChecker 使用风险指标 |

#### 4.5.2 决策工具重构

**核心思路**：`should_i_buy` / `smart_stock_diagnosis` 从"硬编码评分"改为"数据汇聚"模式。

```python
# 重构后：返回丰富数据，让 AI 自己判断
@mcp.tool()
async def get_investment_analysis(code: str):
    """获取股票的综合投资分析数据（供 AI 推理使用）

    Returns:
        {
            "basic_info": { ... },
            "price_context": {
                "current": 45.2,
                "change_1d": -0.012,
                "change_5d": 0.035,
                "change_20d": 0.082,
                "52w_high": 58.3,
                "52w_low": 32.1,
                "position_in_52w": 0.50,      # 当前价在52周范围中的位置
            },
            "valuation": {
                "pe": 12.3, "pe_industry_median": 18.5, "pe_percentile_3y": 0.23,
                "pb": 1.8,  "pb_industry_median": 2.5,
                "ps": 3.2,
                "dividend_yield": 0.032,
            },
            "fundamentals": {
                "roe": 0.185, "roe_trend": [0.17, 0.18, 0.185],
                "debt_ratio": 0.42,
                "revenue_growth": -0.052,
                "profit_growth": 0.12,
                "dupont": {"net_margin": 0.15, "turnover": 0.8, "leverage": 1.54},
            },
            "technical": {
                "rsi_14": 28.5,
                "macd": {"dif": -0.3, "dea": -0.45, "histogram": 0.15, "signal": "approaching_golden_cross"},
                "ma_alignment": "bearish",     # bullish/bearish/neutral
                "volume_ratio_5_20": 1.35,
                "support_levels": [42.0, 39.5],
                "resistance_levels": [48.0, 52.0],
            },
            "momentum_factors": {
                "momentum_20d": {"value": 0.083, "industry_percentile": 0.72},
                "momentum_60d": {"value": -0.12, "industry_percentile": 0.35},
                "reversal_5d": {"value": 0.025, "industry_percentile": 0.58},
            },
            "risk_metrics": {
                "volatility_20d": 0.032,
                "beta": 1.15,
                "var_95": -0.045,
                "max_drawdown_60d": -0.15,
            },
            "flow_signals": {
                "northbound_5d": 2.3,          # 亿元
                "margin_balance_change_5d": 0.5,
                "block_trade_recent": [],
            },
            "historical_patterns": {
                "rsi_oversold_10d_win_rate": 0.72,
                "similar_pattern_avg_return": 0.041,
            }
        }
    """
```

---

### 方向六：架构层优化

**优先级: P2 | 工作量: 2-3 周**

#### 4.6.1 代码重构

| 项目 | 说明 |
|------|------|
| **统一 IC 计算** | factor_analysis 和 multi_factor 的 IC 实现合并为单一模块 |
| **验证管道接入策略生命周期** | FactorValidationPipeline 在策略提交时自动运行 |
| **因子注册器** | 装饰器自动收集元数据，支持 `list_factors()` 工具 |
| **证据链 LRU 淘汰** | _CHAINS 增加 maxsize 限制，防止内存泄漏 |
| **信号追踪异步并发** | asyncio.gather 并行处理多策略 |

#### 4.6.2 数据管道增强

```
新增: services/data_pipeline/
├── factor_store.py     # 因子预计算仓库：行业排名/分位/趋势的增量更新
├── cross_section.py    # 截面数据管理：同一时点全市场因子矩阵
└── condition_stats.py  # 条件统计预计算：信号命中率、条件收益率
```

#### 4.6.3 策略工厂增强

| 项目 | 说明 |
|------|------|
| 代表性股票动态抽样 | 从固定 10 只改为按行业分层随机抽样 |
| 策略去重增加行为相关性 | 跨类型策略信号相关性检测 |
| 尾部风险指标 | 淘汰检查增加 CVaR、最大连续亏损天数 |
| REGIME_MAP 补全 | 补充 ma_cross/quality_factor/growth_factor 等缺失映射 |

---

## 五、实施路线图

### 5.1 分阶段计划

| 阶段 | 内容 | 核心收益 | 工作量 |
|------|------|---------|--------|
| **Phase 1** | 因子计算修复（RSI/MACD/前视偏差） | 消除系统性错误 | 1 周 |
| **Phase 2** | 因子画像工具 `get_factor_profile` | AI 获得因子完整上下文 | 2 周 |
| **Phase 3** | 历史形态匹配与条件概率工具 | AI 获得统计预测证据 | 2 周 |
| **Phase 4** | 决策工具重构为"数据汇聚"模式 | AI 推理能力释放 | 1 周 |
| **Phase 5** | 文本数据增强（原始文本 + 统计） | AI NLP 能力释放 | 1-2 周 |
| **Phase 6** | 回测引擎增强 | 回测可信度提升 | 2 周 |
| **Phase 7** | 风险模型增强与集成 | 风控专业度提升 | 1-2 周 |
| **Phase 8** | 架构重构与数据管道 | 系统可维护性 | 2-3 周 |

### 5.2 优先级矩阵

```
紧急 + 重要（立即做）           重要但不紧急（规划做）
┌─────────────────────┐    ┌─────────────────────┐
│ Phase 1: 因子计算修复  │    │ Phase 6: 回测增强     │
│ Phase 2: 因子画像工具  │    │ Phase 7: 风险模型     │
│ Phase 4: 决策工具重构  │    │ Phase 8: 架构重构     │
└─────────────────────┘    └─────────────────────┘

紧急但次要（尽快做）           不紧急不重要（有空做）
┌─────────────────────┐    ┌─────────────────────┐
│ Phase 3: 历史形态匹配  │    │ 因子注册装饰器        │
│ Phase 5: 文本数据增强  │    │ 证据链LRU淘汰         │
└─────────────────────┘    └─────────────────────┘
```

---

## 六、2025-2026 前沿技术参考

### 6.1 因子挖掘前沿

| 方法 | 来源 | 核心思想 | 与本系统的关系 |
|------|------|---------|--------------|
| **AlphaForge** | AAAI 2025 | 梯度下降因子挖掘，IC均值13.85%，年化超额14.28% | 因子发现可作为离线工具，挖掘的因子导入 MCP 因子库 |
| **FactorMiner** | 2026 arXiv | 自进化 Agent 因子发现，技能模块+经验记忆 | 架构思路可参考，用 AI Agent 编排 MCP 工具链做因子研究 |
| **QuantFactor REINFORCE** | 2025 arXiv | 方差有界 REINFORCE，信息比率奖励塑造 | 理论参考，离线因子挖掘 |
| **LLM辅助因子生成** | 中科院计算所 2025 | LLM 生成因子表达式 + RL 反馈，IC 0.0515（提升75%） | **直接适用**：AI 调用 MCP 工具验证自己生成的因子公式 |
| **多模型集成** | 广发金工 2025 | MLP+GBDT+GRU+AGRU ICIR加权，RankIC 11.9% | 模型训练为离线任务，预测结果可通过 MCP 工具暴露 |

### 6.2 预测模型前沿

| 方法 | 来源 | 核心思想 | 与本系统的关系 |
|------|------|---------|--------------|
| **TFT-GNN 混合** | MDPI 2025 | 时间融合Transformer + 图神经网络 | 过重，不适合 MCP 内运行 |
| **FinMamba** | 2025 arXiv | GNN + Mamba，动态股票关系 | 同上，但关系建模思路可简化后用于 MCP |
| **时序超图注意力** | IJCAI 2025 | 行业级高阶关系 + 多尺度周期 | 理论参考 |

### 6.3 NLP/情绪前沿

| 方法 | 来源 | 核心思想 | 与本系统的关系 |
|------|------|---------|--------------|
| **事件感知情绪因子** | 2025 arXiv | LLM 增强的推文情绪 + 事件分类，IC > 0.05 | **直接适用**：MCP 提供文本 + 事件标签，AI 做语义分析 |
| **实时异常检测** | ReviewSignal 2026 | Isolation Forest 检测舆情异常 | 轻量算法，适合 MCP 内运行 |
| **多源情绪融合** | 多篇 2025 | Reddit/Twitter/财报电话会融合 | MCP 采集多源数据，AI 融合判断 |

### 6.4 适合 MCP 架构的落地路径

```
离线层（定期运行，结果存入 DB）          MCP 工具层（实时提供）           AI 推理层（实时判断）
┌──────────────────────┐         ┌────────────────────┐      ┌─────────────────┐
│ · AlphaForge 因子挖掘   │  ──→   │ · 因子画像工具        │  ──→  │ · 综合推理判断    │
│ · LightGBM 模型训练     │  ──→   │ · 条件概率统计工具     │  ──→  │ · 概率估计        │
│ · 截面排名预计算        │  ──→   │ · 历史形态匹配工具     │  ──→  │ · 风险评估        │
│ · 信号命中率统计        │  ──→   │ · 文本数据采集工具     │  ──→  │ · NLP 文本分析    │
│ · 因子分位数计算        │  ──→   │ · 风险指标计算工具     │  ──→  │ · 策略建议        │
└──────────────────────┘         └────────────────────┘      └─────────────────┘
```

---

## 七、核心结论

### 7.1 设计原则

1. **MCP 工具提供原材料，AI 做厨师** — 工具返回丰富的数据和统计证据，AI 负责推理和判断
2. **因子画像 > 单点值** — 每个因子附带历史分位、行业排名、趋势方向、条件概率
3. **历史统计 > 硬编码规则** — 用"RSI<30 后 10 日有 72% 概率上涨"替代"RSI<30 加 20 分"
4. **原始文本 > 词袋模型** — AI (Claude/GPT) 的 NLP 能力远超任何内置模型
5. **重型 ML 模型离线训练** — 预测结果存入 DB，MCP 工具只负责查询和暴露

### 7.2 预期效果

| 维度 | 当前 | 优化后 |
|------|------|--------|
| AI 可获取的因子上下文 | 单个 float 值 | 时间序列 + 分位 + 排名 + 趋势 |
| AI 预测推理依据 | 硬编码评分结论 | 历史条件概率 + 形态匹配证据 |
| NLP 分析能力 | 40 词关键词匹配 | AI 直接分析原始文本 |
| 回测可信度 | 存在前视偏差 | 修复偏差 + Block Bootstrap |
| 风控深度 | 仅历史 VaR | 多方法 VaR + Barra + 历史情景 |
