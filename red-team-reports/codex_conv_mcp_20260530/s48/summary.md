# N48 · 全工具回归收尾 + 跨场景一致性复测（000001 双重语义污染根因闭环）

- **执行时间**: 2026-05-30T20:05:40+08:00
- **真实工具调用**: 35 次
- **判定**: Pass 23 / Degraded 3 / Fail-graceful 5 / **Fail-schema 4**
- **verdict**: `fail_schema_000001_cross_symbol_contamination_root_cause_isolated_to_db_stock_quotes_direct_readers_but_baselines_stable_and_get_kline_is_correct_reference_pattern`

## 一句话结论

收尾场景把 v3 全程最高频、跨 N34/N36/N38/N39/N46/N47 反复出现的「000001 上证指数混淆」**根因彻底锁定并闭环**：问题不在分析工具，而在**入库校验层**——`sqlite.save_klines` 校验器把深市个股 000001（平安银行，股价约 11 元）误当上证指数（`sh000001`），套用指数价格区间 `[1000,30000]` 将真实股价 11 元判为 `index_close_out_of_range ... possible cross-symbol contamination` 而**拒绝入库**，使 `db.stock_quotes` 表的 000001 快照被上证指数（4068 点）占据。凡**直读 `db.stock_quotes`** 的工具继承污染。

## 三大基线锚点（首尾复测稳定）

| 锚点 | N01 | N48 | 结论 |
|---|---|---|---|
| 工具数 | 163 | 163 | ✓ 无漂移 |
| 分类数 | 33 | 33 | ✓ |
| 因子/分类/别名 | 50/5/85 | 50/5/85 | ✓ |

## 根因闭环证据链（F-N48-1，HIGH）

1. **`get_dead_letters()`** → 5 条 `validation_rejection`：`code='000001' close=11.0~11.49 expected [1000,30000]; possible cross-symbol contamination`，最终 `all kline rows rejected for 000001`。
2. **污染路径（直读 db.stock_quotes）**：
   - `get_batch_quotes([...,000001,...])` → 000001 = **4068.57 / name="上证指数"**
   - `get_key_levels(000001)` → current_price=4068.57 / `price_calibration.factor=377.4184`（把 10.78 的平安银行K线 ×377 拉到指数点位）
3. **正确路径（走实时源 / data_source / K线源）**：
   - `get_realtime_quote(000001)` = **10.93**（平安银行，pe4.8/pb0.46 银行特征）
   - `get_stock_info(000001)` = 平安银行 / 全国性银行 / 1991 上市
   - `get_kline(000001)` = 10.68~10.93 **且显式提示**「000001 同时存在个股和指数语义，默认按个股；如需指数用 sh000001 / get_index_kline」← **全系统正确范本**
   - `calculate_factor(000001 momentum)` 走 K线源，无污染

**修正 N47 结论**：此前以为「污染仅 get_key_levels 残留」，N48 证明污染面 = **所有直读 db.stock_quotes 快照的代码路径**（至少含 get_batch_quotes + get_key_levels）。

## 本场景 4 个 Fail-schema

| ID | 级别 | 问题 |
|---|---|---|
| **F-N48-1** | HIGH | 入库校验器误判 000001 个股为指数→拒绝入库→db.stock_quotes 被指数污染（根因） |
| **F-N48-2** | HIGH | get_key_levels(000001) factor=377 校准到 4068 指数点位（F-N48-1 的具体表现，N46 复现） |
| **F-N48-3** | MED | search_stocks 中文行业词「白酒」=0 匹配（仅代码/名称），与 semantic_stock_search 能力割裂（同 N45 中文失效） |
| **F-N48-4** | LOW | calculate_factor 财务因子(pe→pe_ttm)缺数据时 error 颗粒度不足（未区分数据缺失 vs 计算异常） |

## 关键正向

- **get_kline 的双重语义处理是修复模板**：默认个股 + 显式 fallback_reason 提示，应推广到 get_batch_quotes / get_key_levels。
- **取数分层清晰可诊断**：污染严格限于直读 db.stock_quotes 的路径，边界精确，便于定点修复。
- **别名契约零偏差**：`rsi` 与 `rsi_14` 返回完全相同值（41.042543481567876）。
- **search 层非法码处理正确**：`search_stocks(999999)=not_found`，反衬分析层非法码坐标化是局部缺陷。
- 错误/降级普遍 graceful（macro cpi/gdp 源不可用、深市指数 token 失效、pe 因子缺数据均显式降级非裸抛）。
