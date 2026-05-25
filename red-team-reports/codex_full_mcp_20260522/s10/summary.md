# S10 · 板块轮动 + 行业资金流 + 概念热度 + 产业链 + 板块相关性 + 向量搜索

- **判定**: ✅ 通过 (32/31 工具,Pass=9 / Degraded=23 / Fail=0)
- **耗时**: 12:11:54 → 12:13:41 (约 107s)
- **覆盖模块**: sector_manager / industry_chain_manager / concept_fund_flow / sector_fund_flow / market_blocks / block_stocks / 向量搜索 / 北向资金 / factor_profile

## 🔥 本场景重大发现 — 板块/资金流/产业链整体半瘫(16 条 finding,7 条 high)

### 1. get_sector_fund_flow 不是真实资金流 — mainNetInflow == changePercent(S10-F01)

```python
get_sector_fund_flow(top_n=20)
# 输出:
{
  "name": "半导体",
  "changePercent": 3.0360838383838367,    # 涨跌幅 %
  "mainNetInflow": 3.0360838383838367,    # ← 与 changePercent 完全相同!
  "superLargeNetInflow": null,            # ← null
  "largeNetInflow": null,                 # ← null
  "mediumNetInflow": null,                # ← null
  "smallNetInflow": null,                 # ← null
  "mainInflowPercent": null,              # ← null
  "source": "db.market_blocks",
  "degraded": true                        # ← inline degraded
}
# 但顶层 success=true degraded=false  ← 不一致!
```

`db.market_blocks` 用 sector heat proxy(涨跌幅)替代真实资金流,**5 个 sub-flow 字段全 null**;AI 误以为 mainNetInflow=3.036 是亿元单位的资金流,实际是涨跌幅 %。

### 2. sector_correlation silent failure — 返回 {} 但 success=true(S10-F02)

```python
sector_manager.sector_correlation(sectors=["半导体","电池","光伏设备","酿酒","全国性银行"])
# 输出:
{
  "sectors": [...],
  "period": 60,
  "correlation_matrix": {},     # ← 空对象!
  "interpretation": {...},      # ← 解释字段在,但没数据可解释
  "success": true,
  "degraded": false,
  "fallback_used": false,
  "quality_flags": []
}
```

5 sectors 输入,correlation 完全空,**无任何错误标志**。AI 拿到空对象会做出错误的分散决策。

### 3. sector_rotation vs sector_performance 同 30d 半导体收益矛盾(S10-F03)

| 工具 | 半导体 30d 收益 | 排名 |
|---|---|---|
| `sector_rotation(30)` top 5 | **不在列表** | 不入 top 5 |
| `sector_performance(ind_半导体, 30)` | **41.08%** | 应当 top 1 |
| `sector_rotation` top 1 | 玻璃玻纤 27.82% | top 1 |

**41% 的半导体应当是 top 1 但 sector_rotation 没列出**,两工具同概念给两套排名。

### 4. search_by_kline 茅台最相似全是 ST 退市股(S10-F04)

```
search_by_kline(code="600519" 贵州茅台, days=20, top_n=5)
# 输出:
  600543  *ST莫高    similarity=0.5753   ← 退市
  000752  *ST西发    similarity=0.5197   ← 退市
  600084  *ST尼雅    similarity=0.5165   ← 退市
  600696  *ST岩石    similarity=0.4996   ← 退市
  600059  古越龙山   similarity=0.4918   ← 唯一非 ST
```

**5 个最相似 4 个是 ST**,K 线相似度算法**没过滤 ST/退市标记**,候选 scope 限制 industry=酿酒 36 个 → 4 个 ST 的低位震荡曲线"形似"茅台下跌。AI 拿到这个结果完全不能用。

### 5. get_market_blocks vs list_sectors 同概念差 136 倍(S10-F05)

```
sector_manager.list_sectors(industry):     count = 136
get_market_blocks(industry, limit=5):      count = 1   ← 只半导体!
```

两工具都标 `source=db` `block_type=industry`,但**返回 count 差 136 倍**。AI 看 `get_market_blocks` 以为全市场只 1 个 industry,看 `list_sectors` 看到 136 个。

### 6. industry_chain 颗粒度过粗 + 覆盖度 <5%(S10-F06)

```
industry_chain(半导体):
  upstream    = [硅片, 光刻胶]                          ← 缺 EDA/光刻机/化学材料
  midstream   = [芯片设计, 芯片制造]                     ← 缺 IP 授权/晶圆代工
  downstream  = [封装测试, 终端应用]                     ← 缺 测试设备
  total       = 6 stage 项

related_stocks(半导体):
  unique      = 6 个标的
  coverage    ≈ 3% (6/201)         ← 半导体行业 201 个标的中只 6 个被覆盖
  duplicates  = [688981 中芯国际 (upstream + midstream),  002371 北方华创 (midstream + downstream)]
```

**preset 产业链字典覆盖率 < 5%**,中微公司/拓荆科技/华海清科等真实标的全缺。

### 7. concept_fund_flow 单源依赖 vs 同类 4-6 source(S10-F07)

| 工具 | source 数量 | 跪了能 fallback? |
|---|---|---|
| `get_concept_fund_flow` | **1** (eastmoney.push2.concept) | ❌ 单源 |
| `get_sector_fund_flow` | **5** (memory_cache/cache/db/eastmoney/tushare) | ✅ |
| `get_north_fund` | **4** (north_fund_flow/tushare/hkex/eastmoney) | ✅(全跪但有降级) |
| `get_market_blocks` | **5** | ✅ |
| `get_block_stocks` | **6** | ✅ |

**concept_fund_flow 单源依赖**,proxy 跪一次工具完全不可用。



### 8. freshness_sla 在 null 时 "passed=true" — 整个 SLA bypass(S10-F08)

S09-F12 模式确认:本场景至少 6 个工具的 freshness_sla 在 `data_timestamp=null` 时返回 `passed=true`(本应 'unknown' 或 'warning'):

| 工具 | data_timestamp | age_seconds | freshness_sla.passed |
|---|---|---|---|
| `get_concept_fund_flow` | null | null | **true** ← 实际 proxy 全跪 |
| `get_sector_fund_flow` | null | null | **true** ← 实际 sector heat proxy |
| `get_market_blocks` | null | null | **true** ← 实际 cache stale |
| `get_block_stocks` | null | null | **true** ← 实际 prices 全 0 |
| `get_north_fund` | null | null | **true** ← 实际 4 sources 全跪 |
| `get_north_fund_top` | null | null | **true** ← 实际 53 天前 |

**整个 freshness SLA 实质失效**,AI 看 quality_gate.passed=true 以为数据新,实际可能 53 天前 stale。

## ✅ Positive evidence(4 条)

### S10-F13:get_factor_profile 是工具集**最丰富的因子分析** ✅

```
get_factor_profile(600519, factors="momentum,rsi,macd", lookback_days=120)
# 单个工具替代 5+ 个分析:
  momentum:
    current=-0.0863  series_30d=[30 daily]  percentile_1y=5.2%  percentile_3y=5.2%
    trend="stable"  rolling_zscore=-1.4169  market_percentile=100.0
  rsi:
    current=22.5864  percentile_1y=2.5%  rolling_zscore=-2.3869
    historical_oversold_recovery:
      sample_count=23  reliable=true
      5d:  hit_rate=69.2%  avg_return=1.72%
      10d: hit_rate=83.3%  avg_return=3.83%
  macd:
    current=-31.7084  rolling_zscore=-2.1444  trend="weakening"
```

✅ **一个工具替代 5+ 个分析**:current + 30d series + 1y/3y percentile + zscore + market_percentile + historical_oversold_recovery 全套。茅台 RSI percentile_1y=2.5% 极度超卖;但因子模式工具同样有 industry_total=1 bug(F11)。

### S10-F14:search_similar_stocks(fundamental) 同行业匹配合理 ✅

```
search_similar_stocks(600519 茅台, type=fundamental):
  泸州老窖    similarity=0.7857   ROE=7.19  PE=13.64
  迎驾贡酒    similarity=0.7855   ROE=7.28  PE=14.17
  山西汾酒    similarity=0.7792   ROE=11.96 PE=14.60
  洋河股份    similarity=0.7397   ROE=4.97  PE=66.53  ← 异常 PE 不警告
  会稽山      similarity=0.7300   ROE=3.09  PE=31.63
```

✅ 5 个全是酿酒同行 + features 完整;db_empty fallback python 内存暴力搜索;**fundamental 模式 robust**(对比 search_by_kline F04 跑偏)。

### S10-F15:get_north_fund_top(10) 完整 ratio + market_cap ✅

```
top_10:
  300750  宁德时代  ratio=17.27%  shares=761.3M  marketCap=305.8B
  600519  贵州茅台  ratio=4.69%   shares=58.7M   marketCap=85.2B
  000333  美的集团  ratio=14.0%   shares=973.4M  marketCap=74.3B
  600036  招商银行  ratio=5.8%    shares=1198M   marketCap=47.1B
  300308  中际旭创  ratio=6.97%   shares=77.5M   marketCap=44.1B
  ...
```

✅ 完整 10 record + 5 字段;**ratio 17.27% 宁德时代外资持股最高 — 数据合理 ✅**。

### S10-F16:data_validation(GE) 持续 100% ✅

S07/S08/S09/S10 **四场景累计 4/4 验证 stable** — `data_validation` GE backend 是工具集**最稳定的层**。

## 🚨 工具间数据不一致(本场景新增 16 条 finding,其中 high 7 条)

### 7 条 high

- **S10-F01**:`get_sector_fund_flow` mainNetInflow == changePercent(用 sector heat proxy 替代真实资金流)
- **S10-F02**:`sector_correlation` silent failure(返回 {} 但 success=true)
- **S10-F03**:`sector_rotation` vs `sector_performance` 同 30d 半导体 41% 矛盾
- **S10-F04**:`search_by_kline(600519)` 5 个最相似 4 个 ST 退市股
- **S10-F05**:`get_market_blocks` vs `list_sectors` 同概念差 136 倍
- **S10-F06**:`industry_chain` 颗粒度过粗 + related_stocks 覆盖度 <5%
- **S10-F07**:`get_concept_fund_flow` 单源依赖 proxy 跪即全跪
- **S10-F08**:`freshness_sla` 在 data_timestamp=null 时 "passed=true"(SLA bypass)

### 4 条 medium

- S10-F09:`block_code` 双命名空间(ind_* 127 个 + new_* 9 个混用)
- S10-F10:`calculate_factor` momentum_20d 输入但返回 factor='momentum'(alias 未传播)
- S10-F11:`get_factor_profile.industry_total=1` 但酿酒行业实际 36 个
- S10-F12:`get_industry_chain(does_not_exist)` 返回空数组无 not_found 错误

### 4 条 low(positive evidence)

- **S10-F13** ✅:`get_factor_profile` 工具集最丰富因子分析(替代 5+ 工具)
- **S10-F14** ✅:`search_similar_stocks(fundamental)` 同行业匹配合理(对比 search_by_kline 跑偏)
- **S10-F15** ✅:`get_north_fund_top` 北向持股 ratio + market_cap 完整
- **S10-F16** ✅:`data_validation(GE)` S07-S10 四场景累计 4/4 stable

## 🔬 副作用 / 状态对象

| ID | 类型 | 备注 |
|---|---|---|
| `val-0fa79bf3ba13` | dataset_id | data_validation,GE backend,3/3 pass |
| `log_recommendation_audit` | **persist** | strategy_id=codex_full_mcp_20260522_s10_audit action=hold |
| ~24 个 audit_event_id | read_only | sector × 5 / industry_chain × 4 / fund_flow × 5 / search × 4 / north_fund × 2 / factor × 2 / macro / data_validation |

## 🚨 Fail
无。

## ➡ 进度

- 累计调用工具(去重): **~148/161**(S01 33 + S02 +24 + S03 +12 + S04 +19 + S05 +12 + S06 +6 + S07 +5 + S08 +14 + S09 +12 + S10 +11)
- 已通过场景: **9/22**
- 累计 Fail: **0**
- 累计推荐 bug: **85 条**(S02 3 + S03 5 + S04 6 + S05 7 + S06 8 + S07 12 + S08 12 + S09 16 + S10 16,其中 high 累计 **41 条**)

## 关键观察:S10 暴露了"板块/资金流/产业链层"的系统性 silent fallback

**S07** 是金融数学;**S08** 是量化数学;**S09** 是组合优化数学;**S10** 暴露的是**板块层 + 资金流层 + 产业链层的 silent fallback 模式集中爆发**。

**核心问题模式**:

1. **sector heat proxy 替代真实资金流**(S10-F01):mainNetInflow == changePercent 完全语义错配,但顶层 degraded=false 不警告
2. **silent failure 不报错**(S10-F02):sector_correlation={} 但 success=true 没 degraded 标志
3. **同概念两工具两套结果**(S10-F03/F05):sector_rotation vs sector_performance 同 30d 半导体收益不一;list_sectors vs market_blocks 同 industry 数量差 136 倍
4. **算法跑偏**(S10-F04):search_by_kline 茅台最相似全 ST 退市股,候选范围过窄 + 没过滤 trade_status
5. **preset 字典覆盖率低**(S10-F06):industry_chain 9 stocks 给 201 标的的半导体行业(<5% 覆盖)
6. **单源依赖**(S10-F07):concept_fund_flow only 1 source vs 同类工具 4-6 sources;无任何降级路径
7. **freshness SLA bypass**(S10-F08):至少 6 个工具的 quality_gate.freshness_sla 在 data_timestamp=null 时仍 passed=true,**整个 freshness 校验实质失效**
8. **命名空间混乱**(S10-F09):ind_* / new_* 双前缀,9 个 new_* 拼音简写不规范
9. **alias 未传播**(S10-F10):momentum_20d 输入返回 'momentum' family,子型丢失
10. **industry_total=1 bug**(S10-F11):factor_profile 把酿酒 36 个标的当 1 个

**positive 证据**(4 条):

- `get_factor_profile` 是工具集最丰富的因子分析(单工具替代 5+ 个)
- `search_similar_stocks(fundamental)` 同行业 features 完整(对比 K 线模式跑偏)
- `get_north_fund_top` 北向持股 ratio + market_cap 完整 ✅
- `data_validation(GE)` S07-S10 四场景累计 4/4 stable

**关键洞察**:**state management + factor profile + fundamental search 是 robust 的;板块/资金流/概念热度/产业链/向量 K 线搜索是系统性失效**。这不是单个工具的 bug 而是**整个'板块+资金流+产业链层'缺乏多源 + silent fallback**。
