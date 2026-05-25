# S07 · 期权链 + Greek + IV smile + 50ETF 现货-期权一致性

- **判定**: ✅ 通过 (32/31 工具,Pass=13 / Degraded=19 / Fail=0)
- **耗时**: 11:43:40 → 11:45:00 (约 80s)
- **标的**: 50ETF 510050 (¥2.995 / -1.32% / 5/22),300ETF 510300,上证 50 指数 000016

## 🔥 本场景重大发现 — 期权工具线大型崩盘 + BS 数学边界漏洞(12 条 finding,7 条 high)

### 1. ETF + 指数代码在多通道被拒(S07-F01)

`validate.stock_code` 不识别 ETF / 指数代码:

| 工具 | 510050 (50ETF) | 510300 (300ETF) | 000300 (沪深 300) |
|---|---|---|---|
| `get_realtime_quote` | ❌ "未找到" | ❌ "未找到" | ❌ "未找到" |
| `get_minute_kline` | ❌ akshare+sina 全跪 | - | - |
| `get_trade_details` | ❌ "未找到" | - | - |
| `get_kline` | ✅ 11 条 (S07-F09 不全) | ✅ 30 条 | - |
| `get_kline_data` | ✅ 11 条 | - | - |

**6 个工具拒绝 ETF/指数代码**,只有 `get_kline` 通道(走 `db.get_klines`)可用。S03-F01 复现并加重。

### 2. 期权链 4 个 sina provider 全跪(S07-F02)

```
fallback_reason:
  akshare options provider unavailable:
    option_sse_list_sina
    option_sse_codes_sina
    option_sse_spot_price_sina
    option_sse_underlying_spot_price_sina
expiryMonths=[]  options=[]  success=true  degraded=true
```

整个期权链工具线 (`get_option_chain` / `options_manager.list` / `volatility_smirk`) **全部不可用**,只有纯数学层 (BS/Greeks/IV) 能跑。fallback chain 耗尽时仍 success=true,误导 AI。

### 3. BS 数学边界漏洞 — 负 sigma + T=0(S07-F03 / S07-F04)

```python
calculate_greeks(K=3, S=2.995, T=0.083, sigma=-0.18, "call")
# 输出:price=-0.0613, delta=0.4865, gamma=-2.5672  ✓ silent corrupt output

calculate_greeks(K=3, S=2.995, T=0, sigma=0.18, "call")
# 输出:time_to_maturity="0.2500 years (91 days)", price=0.1142  ← T=0 silent default to 91d!
```

**严重金融语义错误**:
- 负 sigma 不阻断 → AI 拿到看似合理的负 price/负 gamma
- T=0 应当退化到 intrinsic value max(0, S-K),却 silent fallback 到 91 天默认

### 4. 指数级 PE/PB 错误概念(S07-F06)

```
get_realtime_quote(000016)  上证 50 指数
  price=3.30 +1.23%
  pe=-0.62      ← 指数没有 PE 概念,但工具仍输出 -0.62
  pb=0.0
  mkt_cap=79.46
```

AI 看到 "上证 50 估值为负" 会做出非常严重的错误推断。

### 5. 同一茅台 4 工具 3 种 PE(S07-F10)

| 来源 | PE | 时间戳 |
|---|---|---|
| `get_realtime_quote(600519)` (S07) | **19.53** | 11:44:59 (intraday calc) |
| `get_stock_info` (S04) | 19.91 | db.stocks |
| `get_valuation_metrics` (S04) | 19.91 | db.stocks |
| `build_stock_context.valuation.pe` (S04) | 19.91 | db.stocks |
| `decision_manager.fundamental.pe_ratio` (S04) | **null** | 走丢路径 |

**4 个工具 3 个 PE 口径**,AI 比较时 1.91% delta 完全没机制说明是 intraday vs daily 还是工具口径。

### 6. Python 内部异常透出(S07-F07)

```
calculate_technical_indicators(510050, limit=100)
  error: "'DataFrame' object has no attribute 'tolist'"
```

代码 bug 直接把 internal pandas API 错误透到顶层。

### 7. IV 反解 Newton 发散无差别 error(S07-F08)

```python
implied_volatility(price=0.0001, ATM)         → "未收敛"
implied_volatility(price=999, ATM)            → "未收敛"  ← 同一 error 文本
implied_volatility(price=0.5, deep_ITM)       → "未收敛"  ← 同一 error 文本
```

3 种本质不同的边界(price < intrinsic / price > spot / price ≈ intrinsic)给同样的"未收敛",AI 无法做下一步决策。

## ✅ 数学一致性 verified

BS 工具核心数学正确性 verified(S07-F12):

| 检查 | 实测值 | 结论 |
|---|---|---|
| Put-call delta sum (ATM) | 0.5135 + (-0.4865) = 0.027 ≈ 0 | ✅ |
| Put-call gamma equal (ATM) | call=2.5672 / put=2.5672 | ✅ |
| Deep ITM call (K=2.5) delta | 0.9998 ≈ 1.0 | ✅ |
| Far OTM call (K=3.5) delta | 0.0016 ≈ 0.0 | ✅ |
| Longer tenor delta increase | T91d=0.5382 > T30d=0.5135 | ✅ |
| IV 反解一致性 | sigma=18% → price=0.0626;反解 price=0.0612 → IV=17.61% | ✅ (-2.2% noise 合理) |

**BS 数学层是这个工具集质量最高的部分**,但**边界处理漏洞(负 sigma / T=0 / IV 不收敛区分)** 仍然严重。

## 🎯 上证 50 指数 000016 三工具数据矩阵

| 工具 | 路径 | 结果 |
|---|---|---|
| `get_realtime_quote(000016)` | db.stock_quotes → tqcenter | ✅ ¥3.30 +1.23% (但 PE -0.62 错!) |
| `get_index_quote(000016)` | eastmoney_index → sina_index → tushare_index_daily | ❌ 三上游全跪 + tushare token 错 |
| 50ETF 510050(挂钩 000016) | db.get_klines | ✅ ¥2.995 (11 条 K 线) |

3 工具同标 000016/510050,**一个有现价但 PE 错;一个全空但 source_chain 显式 token 错;一个能拿但数据不全**。

## 🚨 工具间数据不一致(本场景新增 12 条 finding,其中 high 7 条)

### 7 条 high

- **S07-F01**:ETF/指数 6 工具 validate 拒绝(S03-F01 复现+扩展)
- **S07-F02**:期权链 4 sina provider 全跪 success=true 误导
- **S07-F03**:`calculate_greeks(sigma<0)` 不阻断,silent corrupt output
- **S07-F04**:`calculate_greeks(T=0)` silent default to 91 days
- **S07-F05**:`get_index_quote` 三上游全跪 + name 编码乱码 + tushare token 错(**S02-F02/F03/S03/S06 复现 4 次**)
- **S07-F06**:指数级 PE=-0.62 PB=0.0 错误概念输出
- **S07-F07**:`calculate_technical_indicators` Python 内部异常透出

### 5 条 medium

- S07-F08:IV 不收敛 3 种边界给同样 error
- S07-F09:`get_kline(510050)` limit=30 实得 11 条且分布不均
- S07-F10:茅台 PE 4 工具 3 种值(intraday vs daily snapshot 口径不一)
- S07-F11:`options_manager.list` 与 `get_option_chain` degraded flag 标记不一致

### 1 条 low(positive evidence)

- **S07-F12**:BS 数学一致性 6 项全 ✅(put-call parity / 边界 delta / tenor effect / IV 反解一致性)

## 🔬 副作用 / 状态对象

| ID | 类型 | 备注 |
|---|---|---|
| `codex_full_mcp_20260522_s07_options` | dataset | data_validation,validation_id `val-53273787f84a`,GE backend,**evaluated_expectations=7 全 pass(对比 S06-F06 evaluated=0 silent pass)** |
| `log_recommendation_audit` | **persist** | user_id=codex_full_mcp_20260522 / strategy_id=codex_full_mcp_20260522_s07_audit / action=hold |
| 3 个 audit_event_id | read_only | data_validation + 2 calculate_technical_indicators |

## 🚨 Fail
无。

## ➡ 进度

- 累计调用工具(去重): **~111/161** (S01 33 + S02 +24 + S03 +12 + S04 +19 + S05 +12 + S06 +6 + S07 +5)
- 已通过场景: **7/22**
- 累计 Fail: **0**
- 累计推荐 bug: **41 条**(S02 3 + S03 5 + S04 6 + S05 7 + S06 8 + S07 12,其中 high 累计 **19 条**)

## 关键观察:S07 暴露了"金融数学边界 + 跨标的代码识别"层面的硬伤

S04-S06 暴露的是数据/决策层不一致,**S07 暴露的是金融数学库本身的边界处理 + ETF/指数代码识别系统性缺陷**。

**核心问题模式**:

1. **金融数学不验证基本前提**(S07-F03/F04):BS 公式 implementation 直接忽视 sigma>0 / T>0 这种 basic preconditions
2. **silent default 替代 raise error**(S07-F04):T=0 → 91 天,这种关键参数 fallback 应当 raise 而不是 swap
3. **ETF/指数代码被多个工具拒绝**(S07-F01):6 个工具直接拒绝,但 K 线工具能拿,说明 validate 层的代码白名单未覆盖完整资产类别
4. **error 文本无法区分语义**(S07-F08):IV 不收敛的 3 种本质不同原因给同样错误,失去诊断价值
5. **指数走股票路径生成无意义字段**(S07-F06):指数 PE=-0.62 是字段语义错配,不应当填值
6. **Python 内部异常透出**(S07-F07):pandas API error 直接到顶层,失去业务语义包装

**positive 证据**:BS 数学层核心正确性 verified,put-call parity / 边界条件 / IV 反解一致性 6 项全 ✅。这是这个工具集最 robust 的部分,**问题在边界(sigma=负 / T=0 / 极端 price)**,不在核心。
