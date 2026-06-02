# N03 · 多股批量行情对比 + 全市场扫描

- **判定**: ⚠ 通过（含 1 项 schema 发现）(Pass=18 / Degraded=13 / Fail-graceful=0 / Fail-schema=1)
- **真实工具调用数**: 33

## 核心成果

1. **批量行情**：2/3/5/8 只批量均成功，`found/missing/rejected_count` 计数自洽；>5 只走全市场快照路径。
2. **股本数据**：9 只标的 `get_stock_capital` 全部成功（tqcenter），数值合理（平安银行总股本 194 亿 / 比亚迪 91 亿 / 格力 56 亿）。
3. **全市场分页**：`get_stock_list` total=5532，offset 0/100/3000/5000/5530 分页正确，越界 offset=99999 优雅返回空。
4. **中文搜索强**：单字「茅」命中茅台，行业词「银行/证券/医药」返回市值 TOP 排序，代码「600036」精确命中，无结果「ZZZZNOTEXIST」正确 not_found。

## ⚠ 关键发现

- **F-N03-1 [MEDIUM / 唯一 schema 级]**：`get_batch_quotes(stock_codes=[])` 空数组**抛 pydantic 校验异常**（`Field required`），而非文档承诺的 `success=false`。空数组被当成缺失字段。这是本次首个 Fail-schema。
- **F-N03-2 [MEDIUM]**：`get_batch_quotes` 把非法代码 999999 当成上证指数返回 price=4068.57，而 `get_realtime_quote(999999)` 正确报"未找到"。**batch 与单查的代码校验不一致**。
- **F-N03-3 [LOW]**：`get_stock_list` 恒 `fallback_used=true` + `reason='未获取到A股股票列表'`，但实际从 db.stocks 正确返回（total=5532）。**文案误导**（像失败，实为正常 db 兜底）。

## 亮点

股本/搜索/分页核心数据质量高；envelope 的 found/missing/rejected/truncated 边界标志完整。
