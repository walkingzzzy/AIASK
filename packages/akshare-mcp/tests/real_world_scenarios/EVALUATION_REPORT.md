# AKShare MCP 场景测试深度评估报告

> 评估日期: 2026-02-09
> 评估范围: 12个真实应用场景 (scenario_01 ~ scenario_12)
> 评估方法: 源码核实 + 行业调研 + 测试文档质量审查
> 评估定位: 本项目以TDX客户端为核心交互前端，TDX数据源为第一优先级。本报告评估的是**测试场景文档**的质量（流程合理性、步骤可执行性、验证条件准确性），工具开发已完成。

---

## 一、总体评估

### 12个场景可行性概览

✅ 完全可行: 4个（01、03、10、12）
⚠️ 部分可行（需改进）: 8个（02、04、05、06、07、08、09、11）
❌ 不可行: 0个

### 系统性问题（跨场景）

1. **文档与实现仍有关键字段不一致**: 如 `annual_return`（不存在）、`tdx_send_status`（应为`tdx_send_result`）、`triggered` 语义（始终False）、`recommendation` 枚举值（sell/hold/add vs 实际 sell/reduce/consider_sell/hold/strong_hold）、`analyze_portfolio_risk` 返回结构（文档写顶层字段，实际是 var/risk 子结构）
2. **部分验证条件"过强"或"不可验证"**: 如强制涨停数量完全一致、强制压力场景损失大小关系、triggered 状态检测
3. **个别能力仍是演示数据**: 恐惧贪婪指数（固定值50）、市场洞察（硬编码趋势/板块），需明确标注避免误导测试人员
4. **"全局统一数据源降级链"表述过于理想化**: 实际是工具级差异化链路，不同工具有各自的降级路径

### 优先改进方向

- **P0**: 先修正文档误导项（场景04/05/08），涉及字段名错误和验证条件与实际行为不符
- **P1**: 统一测试断言口径（场景06/07/11），避免过强断言导致测试误判
- **P2**: 补充性能与异常测试矩阵（全场景）

---

## 二、分场景详细评估

### 场景01：盘前选股与自选股同步

**可行性**: ✅ 完全可行

**调研依据**:
- https://akshare.akfamily.xyz/data/stock/stock.html
- https://www.joinquant.com/guide
- https://www.ricequant.com/doc/
- https://ta-lib.github.io/ta-doc/indicator/RSI.htm
- https://www.tradingview.com/education/macd/

**问题清单**:
1. 场景强调"盘前效率"，但未给出批量行情获取的失败重试策略
2. 条件选股后缺少流动性（成交额/换手率）与停牌过滤步骤，实盘可执行性不足——Step 4仅排除ST/停牌，未过滤低流动性标的

**改进建议**:
1. `scenario_01_morning_stock_screening.md` 增加"成交额/换手率/停牌过滤"步骤（可在Step 4扩展或新增Step）
2. 增加"TDX不可用时降级到 screener_manager/search_stocks"分支说明

---

### 场景02：多因子量化选股

**可行性**: ⚠️ 部分可行（需改进）

**调研依据**:
- https://www.ricequant.com/doc/rqfactor/manual/index-rqfactor
- https://econpapers.repec.org/article/eeejfinec/v_3a33_3ay_3a1993_3ai_3a1_3ap_3a3-56.htm (Fama-French三因子)
- https://scholarworks.wmich.edu/math_pubs/42/
- https://www.joinquant.com/guide
- https://akshare.akfamily.xyz/tutorial.html

**问题清单**:
1. **因子库描述不准确**: 文档写"8个因子"易被理解为能力上限；实际是接口暴露8个基础因子类别，底层 `factor_calculator.py` 细分因子远超此数（100+）。见 `scenario_02` Step 1、`quant.py` line 10/100
2. **IC和分组回测未强调样本外验证与多重检验**: 容易过拟合。Step 3用10只股票计算IC，统计意义不足

**改进建议**:
1. Step 1 改为"当前接口暴露8个基础因子类别（momentum/volatility/reversal/value/quality/growth/size/liquidity），每个类别下有多个细分因子"，并链接扩展说明
2. 增加"训练/验证/样本外"拆分与最小样本门槛建议（如行业中性后再算IC）
3. Step 3 补充说明"此处10只为快速验证，正式分析建议≥30只"

---

### 场景03：买入决策全流程

**可行性**: ✅ 完全可行

**调研依据**:
- https://pages.stern.nyu.edu/~adamodar/New_Home_Page/data.html (Damodaran估值数据)
- https://corporatefinanceinstitute.com/resources/valuation/dividend-discount-model/
- https://ta-lib.github.io/ta-doc/indicator/RSI.htm
- https://ta-lib.github.io/ta-doc/indicator/BBANDS.htm
- https://production.dataviz.cnn.io/index/fearandgreed/

**问题清单**:
1. DCF/DDM输入假设敏感性未结构化展示（增长率/折现率扰动），用户难以判断估值区间
2. 情绪与估值信号权重未明确披露，当信号冲突时缺少优先级规则说明

**改进建议**:
1. Step 2 DCF部分增加"敏感性网格"验证（discount_rate ±1%、growth_rate ±1%），展示估值区间而非单点值
2. Step 5 结果验证中增加"信号冲突时的优先级规则"说明（如技术面看空但估值看多时，should_i_buy如何权衡）

---

### 场景04：持仓监控与止盈止损

**可行性**: ⚠️ 部分可行（需改进）

**调研依据**:
- https://www.joinquant.com/community/post/detailMobile?postId=35378
- https://scholarworks.wmich.edu/math_pubs/42/
- https://ta-lib.github.io/ta-doc/indicator/RSI.htm
- https://www.tushare.pro/document/2?doc_id=26
- https://www.ricequant.com/doc/rqalpha-plus/tutorial/enhanced-feature

**问题清单**:
1. **`check_all_alerts` 的 `triggered` 不会动态更新**: 该工具不是实时触发引擎，`triggered` 在创建时设为 False 且无实际触发检测逻辑（不会获取实时价格与阈值比较）。见 `scenario_04` line 96、`alerts.py` line 42/73/82
2. **`should_i_sell` 的 `recommendation` 枚举值与文档不符**: 文档断言 recommendation 为 `sell/hold/add`，源码实际值为 `sell/reduce/consider_sell/hold/strong_hold`（无 `add`）。见 `scenario_04` line 36、`decision.py` line 367

**改进建议**:
1. Step 6 改为"验证告警对象存在 `triggered` 字段（当前实现默认 False，触发检测需通过外部逻辑实现）"
2. Step 1 修正 recommendation 枚举说明，给出完整映射表：`sell`(强烈卖出) / `reduce`(建议减仓) / `consider_sell`(可考虑卖出) / `hold`(继续持有) / `strong_hold`(坚定持有)

---

### 场景05：回测与TDX可视化

**可行性**: ⚠️ 部分可行（需改进）

**调研依据**:
- https://www.ricequant.com/doc/rqalpha-plus/doc/index-rqalphaplus
- https://www.ricequant.com/doc/rqalpha-plus/tutorial/enhanced-feature
- https://scholarworks.wmich.edu/math_pubs/42/
- http://gainium.io/blog/common-backtesting-problems
- https://www.joinquant.com/community/post/detailMobile?postId=35378

**问题清单**:
1. **文档验证 `annual_return`，但返回结构无该字段**: `BacktestEngine.run_backtest` 返回的 data 字段为 `total_return/max_drawdown/sharpe_ratio/trades_count/win_rate`，不包含 `annual_return`。见 `scenario_05` line 35、`backtest.py`(服务层) line 503+
2. **一键联动返回字段名错误**: 文档写 `tdx_send_status`，源码实际返回 `tdx_send_result`。见 `scenario_05` line 85、`backtest.py`(工具层) line 439

**改进建议**:
1. Step 1 验证条件改为"包含 `total_return/max_drawdown/sharpe_ratio/win_rate/trades_count` 字段"，移除 `annual_return`
2. Step 6 字段改为 `tdx_send_result` 并补充失败分支断言（如 trades 为空时 tdx_send_result.success=False）

---

### 场景06：组合风险管理

**可行性**: ⚠️ 部分可行（需改进）

**调研依据**:
- http://doi.org/10.1111/j.1540-6261.1952.tb01525.x (Markowitz均值方差)
- https://www.bis.org/bcbs/publ/d457.htm (Basel VaR框架)
- https://www.risk.net/journal-of-risk/technical-paper/2161159/optimization-conditional-value-risk
- https://www.aqr.com/insights/research/white-papers/risk-parity-risk-management-and-the-real-world
- https://www.goldmansachs.com/our-firm/history/moments/1990-black-litterman-model

**问题清单**:
1. **`analyze_portfolio_risk` 返回结构与文档不匹配**: 文档按 `portfolio_volatility/portfolio_return/sharpe_ratio/correlation_matrix` 顶层断言，源码实际返回 `{'var': var_result, 'risk': risk_result}` 子结构。见 `scenario_06` line 34、`portfolio.py` line 265
2. **"market_crash 损失必大于 sector_rotation"并非实现保证**: `stress_test_portfolio` 的 market_crash 基于历史波动率估算，sector_rotation 基于相关性分析，两者不具有固定大小关系。见 `scenario_06` line 80、`portfolio.py` line 344+

**改进建议**:
1. Step 1 断言改为按 `data.var.*` 与 `data.risk.*` 子结构校验
2. Step 6 改为"损失为负向冲击且字段完整"，不做固定大小关系断言

---

### 场景07：涨停复盘与龙虎榜追踪

**可行性**: ⚠️ 部分可行（需改进）

**调研依据**:
- https://www.tushare.pro/document/2?doc_id=355
- https://www.sse.com.cn/lawandrules/sselawsrules/repeal/rules/c/c_20230418_5720138.shtml
- https://www.szse.cn/lawrules/rule/stock/trade/t20250207_612205.html
- https://www.sse.com.cn/market/stockdata/overview/day/
- https://www.tushare.pro/document/2?doc_id=47

**问题清单**:
1. **验证条件"列表数量与统计涨停数一致"过强**: `get_limit_up_stocks` 和 `get_limit_up_statistics` 可能使用不同数据源或不同时间点的数据，严格一致不现实。见 `scenario_07` line 47
2. 龙虎榜、资金流存在T+1与数据源差异，断言应允许偏差区间

**改进建议**:
1. Step 2 改为"基本一致（允许±N）且样本代码可交叉命中"
2. 增加"交易日/非交易日/盘后时点"三种口径测试

---

### 场景08：每日市场全景报告

**可行性**: ⚠️ 部分可行（需改进）

**调研依据**:
- https://www.stats.gov.cn/sj/zxfb/2026/202601/t20260103_1975731.html (国家统计局PMI)
- https://www.stats.gov.cn/sj/zxfb/2026/202601/t20260109_1975858.html (国家统计局CPI)
- https://www.pbc.gov.cn/zhengcehuobisi/125207/125227/125957/125989/5555790/index.html (央行货币政策)
- https://production.dataviz.cnn.io/index/fearandgreed/
- https://www.tushare.pro/document/2?doc_id=47

**问题清单**:
1. **`calculate_fear_greed_index` 当前为固定值（演示数据）**: 源码确认所有组件均返回50，index=50，level='neutral'。见 `scenario_08` line 107、`sentiment.py`(服务层) line 37
2. **`market_insight_manager` 返回预设趋势/板块**: `market_trend` 返回固定 sideways/medium/3000/3300，`sector_analysis` 返回固定热门/冷门板块。见 `market_insight_manager.py` line 24/34

**改进建议**:
1. Step 6（恐惧贪婪指数）和 Step 9（市场洞察）显式标注"⚠️ 当前仅校验返回结构，不校验市场真实性（演示数据）"
2. 增加"宏观数据发布时间检查"断言，避免把旧值当"最新"——验证返回数据的日期字段是否为最近发布期

---

### 场景09：产业链深度研究

**可行性**: ⚠️ 部分可行（需改进）

**调研依据**:
- https://www.ricequant.com/doc/rqfactor/manual/index-rqfactor
- https://www.ricequant.com/doc/rqfactor/api/factor-test
- https://www.joinquant.com/help/data/stock?f=home&m=footer
- https://akshare.akfamily.xyz/data/stock/stock.html
- https://www.ricequant.com/doc/

**问题清单**:
1. **产业链覆盖是预置集合，广度有限**: 仅覆盖新能源/半导体/光伏/白酒/医药 5个行业。见 `scenario_09` line 39、`semantic.py` line 270
2. **相似股票/相似K线属于启发式结果，缺少稳定性说明**: 不同时间点执行可能返回不同结果

**改进建议**:
1. 增加"关键词不命中时返回全量预置链 + 提示"的显式验收条件
2. 增加"行业内基准对照"（例如同申万二级行业）防止跨行业误匹配

---

### 场景10：期权策略分析

**可行性**: ✅ 完全可行

**调研依据**:
- https://www.macroption.com/the-pricing-of-options-and-corporate-liabilities/ (Black-Scholes原始论文)
- https://www.macroption.com/put-call-parity-formula/
- https://www.cfainstitute.org/insights/professional-learning/refresher-readings/2026/option-replication-using-put-call-parity
- https://etf.sse.com.cn/fund/learning/knowledge/c/c_20250312_10775658.shtml
- https://www.sse.com.cn/assortment/options/disclo/update/c/c_20250519_10779419.shtml

**问题清单**:
1. 文档虽已修正 action/参数名（v1.1），但仍应强调"欧式假设"边界——BS闭式解仅适用于欧式期权
2. 缺少极端波动率（IV爆炸）异常路径测试

**改进建议**:
1. 增加"美式期权不适用Black-Scholes闭式解"提示（上交所ETF期权为欧式，此处仅为边界说明）
2. 增加 `volatility > 1`、`time_to_maturity ≈ 0` 的数值稳定性测试用例

---

### 场景11：新股与可转债申购

**可行性**: ⚠️ 部分可行（需改进）

**调研依据**:
- https://www.tushare.pro/document/2?doc_id=404
- https://www.tushare.pro/document/2?doc_id=188
- https://www.sse.com.cn/lawandrules/sselawsrules/bond/convertible/
- https://www.sse.com.cn/lawandrules/sselawsrules2025/bond/convertible/listing/c/c_20250516_10787557.shtml
- https://www.sse.com.cn/aboutus/mediacenter/hotandd/c/c_20220729_5706472.shtml

**问题清单**:
1. **转股溢价率公式描述易歧义**: 文档 Step 4 写"转股溢价率 = (转债价格/100*转股价 - 正股价) / 正股价"，括号和单位口径容易混淆。见 `scenario_11` line 75
2. **`check_all_alerts` 同场景04问题**: `triggered` 不会动态更新，不能代表实时触发状态。见 `scenario_11` line 100

**改进建议**:
1. 转股溢价率公式改为标准写法：`转股溢价率 = (转债现价 - 转股价值) / 转股价值`，其中 `转股价值 = 正股现价 × 100 / 转股价`，并注明"转债价格按100面值口径"
2. 增加"正股停牌/转股价变更"两条边界用例

---

### 场景12：跨周期技术共振选股

**可行性**: ✅ 完全可行

**调研依据**:
- https://ta-lib.github.io/ta-doc/indicator/MACD.htm
- https://ta-lib.github.io/ta-doc/indicator/RSI.htm
- https://ta-lib.github.io/ta-doc/indicator/STOCH.htm
- https://www.tradingview.com/script/WqzrfL2Q-Multi-Timeframe-MACD-Strategy-ver-1-0/
- https://www.tradingview.com/script/Epqb0L8C-RSI-MACD-Multi-Timeframe-Strategy/

**问题清单**:
1. 多周期逐标的调用在实盘高并发下耗时会明显上升（每只7次TDX调用，10只=70次），文档缺少耗时基准
2. 文档对"共振→胜率提升"缺少分组回测证据链

**改进建议**:
1. 增加缓存/批处理提示及耗时基准分层（10只/50只/200只）
2. 增加"共振信号 vs 非共振信号"样本外对照回测建议

---

## 三、文档修改清单

### P0（字段名错误/验证条件与实际行为不符）

- [x] `scenario_04_position_monitor_stoploss.md` line 36: `recommendation` 枚举改为源码实际值 `sell/reduce/consider_sell/hold/strong_hold`（非 sell/hold/add）
- [x] `scenario_04_position_monitor_stoploss.md` line 96: `triggered` 验证语义改为"字段存在 + 当前默认 False（无实际触发检测）"
- [x] `scenario_05_backtest_tdx_visualization.md` line 35: 移除 `annual_return` 断言，改为 `total_return/max_drawdown/sharpe_ratio/win_rate/trades_count`
- [x] `scenario_05_backtest_tdx_visualization.md` line 85: `tdx_send_status` 改为 `tdx_send_result`，补充失败分支断言
- [x] `scenario_08_daily_market_report.md` line 107: 标注恐惧贪婪指数当前为演示值（固定50），Step 仅校验返回结构
- [x] `scenario_08_daily_market_report.md`: market_insight_manager 相关步骤标注为演示数据，仅校验返回结构

### P1（断言过强/描述不准确）

- [x] `scenario_06_portfolio_risk_management.md` line 34: 按 `var/risk` 子结构改写断言（非顶层 portfolio_volatility）
- [x] `scenario_06_portfolio_risk_management.md` line 80: 删除固定损失大小比较，改为"损失为负向冲击且字段完整"
- [x] `scenario_07_limit_up_dragon_tiger.md` line 47: 改为"允许偏差的一致性（±5%或样本交叉命中）"
- [x] `scenario_11_ipo_convertible_bond.md` line 75: 转股溢价率公式重写为标准写法并注明单位口径
- [x] `scenario_02_multi_factor_screening.md` Step 1: "8个因子"改为"8个因子类别，底层细分因子100+"
- [x] `README.md`: "统一降级链"改为"按工具链路定义的差异化降级路径"

### P2（补充完善）

- [x] `scenario_01_morning_stock_screening.md`: 增加流动性过滤步骤和TDX不可用降级分支
- [x] `scenario_03_buy_decision_workflow.md`: 增加DCF敏感性网格和信号冲突优先级规则
- [x] `scenario_10_option_strategy_analysis.md`: 增加极端参数（volatility>1, T≈0）数值稳定性测试
- [x] `scenario_11_ipo_convertible_bond.md`: 增加"正股停牌/转股价变更"边界用例
- [x] `scenario_12_multi_timeframe_resonance.md`: 增加耗时基准分层和共振信号对照回测
- [x] `README.md` 性能基准表: 增加"多周期共振分析"和"每日报告生成"目标耗时

---

## 四、代码改进建议

> 以下代码改进已全部实施。

| 文件 | 位置 | 改进内容 | 优先级 | 状态 |
|------|------|------|--------|------|
| `sentiment.py`(服务层) | line 35 | `calculate_fear_greed_index` 改为真实多因子聚合（动量/波动率/成交量/市场宽度） | P0 | ✅ 已完成 |
| `sentiment.py`(工具层) | calculate_fear_greed_index | 接入上证指数K线和涨跌停统计数据作为输入 | P0 | ✅ 已完成 |
| `market_insight_manager.py` | line 22 | `market_trend` 接入真实指数行情+K线MA趋势判断；`sector_analysis` 接入真实板块资金流向 | P0 | ✅ 已完成 |
| `alerts.py` | line 82 | `check_all_alerts` 增加即时触发检查逻辑（price类型获取实时行情与阈值比较），返回 `triggered_count` | P1 | ✅ 已完成 |
| `backtest.py`(工具层) | line 439 | `run_backtest_and_send_to_tdx` 同时返回 `tdx_send_result` 和 `tdx_send_status`（兼容别名） | P2 | ✅ 已完成 |
| `portfolio.py` | line 344 | 压力测试结果增加 `portfolio_loss_numeric` / `avg_correlation_numeric` 数值字段便于自动断言 | P2 | ✅ 已完成 |
| `portfolio.py` | stress_test | 修复 `db` 未定义和 `get_kline` 导入路径错误的预存bug | bugfix | ✅ 已完成 |
| `quant.py` | line 100 | `get_factor_library` 每个因子增加 `sub_factors`（细分因子列表）和 `aliases`（别名映射）字段 | P2 | ✅ 已完成 |

---

## 五、技术指标参数验证

| 指标 | 场景使用参数 | 行业标准 | 评估 |
|------|------------|---------|------|
| MACD | 12/26/9 | 12/26/9 | ✅ 标准 |
| KDJ | 9/3/3 | 9/3/3 | ✅ 标准 |
| RSI | 6/12/24 | 6/12/14或24 | ✅ 合理 |
| BOLL | 20/2 | 20/2 | ✅ 标准 |
| DMI | 14/6 | 14/6 | ✅ 标准 |
| EXPMA | 12/50 | 12/50 | ✅ 标准 |

所有技术指标参数均符合行业标准。

---

## 六、数据源降级链评估

> 注意：降级链是**工具级差异化**的，非全局统一。

| 工具类别 | 实际降级链 | 评估 |
|---------|-----------|------|
| K线/行情 | TDX → Tushare → 东财 → AkShare → Baostock | ✅ 合理 |
| 龙虎榜 | Tushare → AkShare(stock_lhb_detail_em) → Sina | ✅ 合理 |
| 研报 | Tushare report_rc → 东财 datacenter → AkShare | ✅ 合理 |
| 期权链 | 新浪直连 → AkShare | ⚠️ 仅两级 |
| 涨停板 | stk_limit + daily 组合判断 | ✅ 合理 |
| 宏观数据 | Tushare Pro → AkShare | ✅ 合理 |
| IPO/可转债 | TdxQuant | ⚠️ 单一数据源 |
| 公式计算 | TdxQuant（有fallback实现） | ✅ 合理 |

---

## 七、总结

### 核心发现

12个测试场景文档整体质量较高，源码核实彻底（v1.1修正记录详细），但仍存在以下需要修正的问题：

1. **P0（6处）**: `annual_return` 字段不存在、`tdx_send_status` 应为 `tdx_send_result`、`recommendation` 枚举值不匹配、`triggered` 验证条件误导、恐惧贪婪指数/市场洞察为演示数据未标注
2. **P1（6处）**: `analyze_portfolio_risk` 返回结构不匹配、压力测试损失大小断言过强、涨停数量一致性断言过强、转股溢价率公式歧义、因子库描述不准确、降级链表述过于理想化
3. **P2（6处）**: 流动性过滤、DCF敏感性、极端参数测试、边界用例补充、耗时基准、性能基准表

### 修改工作量预估

- P0: 6处文档修正，约 1 小时
- P1: 6处文档调整，约 1 小时
- P2: 6处补充完善，约 1.5 小时
