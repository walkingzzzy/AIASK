# N04 · 技术分析全指标 + K线形态 + 因子画像

- **判定**: ⚠ 通过（含 1 项 HIGH 级逻辑缺陷）(Pass=26 / Degraded=5 / Fail-schema=1)
- **真实工具调用数**: 32

## 核心成果

1. **全指标**：600519 一次性算出 MA/EMA/RSI/MACD/KDJ/BOLL/ATR 全 7 指标（limit=250），MACD warmup=33 正确标注。
2. **形态库**：8 种形态（doji/hammer/engulfing/morning_star/three_white_soldiers...）含 bullish/reliability 标签；多标的多周期检测均 success（近期无形态，patterns=[]）。
3. **决策摘要（亮点）**：`technical_analysis_manager.calculate` 自带 `summary`——600519 输出 trend=down / suggestion=sell / signals=[MA20下方/RSI正常/MACD负]，对 AI 极友好。
4. **因子画像（亮点）**：`get_factor_profile` 返回 percentile_1y/3y + trend + rolling_zscore + industry_rank + **历史超卖恢复命中率**（600519 RSI 超卖后 10 日 hit_rate=0.9231 reliable=true），是高质量条件概率证据。

## ⚠ 关键发现

- **F-N04-1 [HIGH / 唯一 schema-逻辑级]**：`calculate_technical_indicators(600519, ['RSI'], limit=10)` 在 K 线数不足 RSI 所需 14 根时，**返回 RSI=0 + signal='buy' + oversold=true**，无 warmup 不足告警。AI 用小 limit 会收到**虚假超卖买入信号**，可直接误导交易。指标计算缺最小样本保护。
- **F-N04-2 [LOW]**：RSI 随 limit 变化（250→45.22 / 20→39.91 / 10→0）。250 与 20 属正常窗口差异，10 触发上面的缺陷。建议 AI 用默认 limit=250。

## 评价

技术分析能力整体很强（决策摘要 + 因子画像质量高），但 `calculate_technical_indicators` 的小样本保护缺失是真实可复现的逻辑缺陷，建议增加 `min_periods` 校验，数据不足时返回 `value=null` + 告警而非 0。
