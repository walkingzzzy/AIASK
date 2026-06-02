# N13 · 因子库与单因子计算

- 调用次数: 31 | 判定: pass_with_high_finding
- 覆盖工具: get_factor_library、list_factors、calculate_factor、get_factor_profile

## 关键发现

- **F-N13-1 (high)**: `calculate_factor` 别名解析三层命名断裂。`alias_canonical_map` 声明 `pb_ratio→pb_ttm`，但 `calculate_factor(pb_ratio)` 报 "Unsupported factor"；且映射目标 `pb_ttm` 本身也不在 `supported_factors`（实际是 `pb_mrq`）。`rsi_24` 同理（在 alias_map 但 supported 无）。与 naming_note 宣称的"All 4 actions accept any name in aliases"矛盾。对比 `rsi→rsi_14` 别名成功。
- **F-N13-2 (medium)**: 5 个 alternative 因子（sentiment_score/capital_flow/north_flow/institutional_flow/event_intensity）库声明 `always_available`，但 calculate_factor 全部失败。元数据与运行时能力不符。
- **F-N13-3 (medium)**: `roe_ttm` 值疑似偏低（茅台 10.06、格力 4.0，实际应为 30%+/20%+），疑似单季 vs TTM 口径问题。net_margin=50.53(茅台) 则合理。
- **F-N13-4 (low)**: `get_factor_profile` 的 percentile_1y 与 percentile_3y 恒等（db 仅约 1 年数据，3y 回退未标注）。

## 正向能力

- 因子库结构清晰：50 因子 / 5 分类 / 85 别名，含 alias_canonical_map / sub_factors / data_dependency / requires_financials / availability_hint。
- `get_factor_profile` 高质量画像：30 日序列 + 1y/3y 分位 + trend + rolling_zscore + industry_rank + market_percentile + historical_oversold_recovery（含 reliable 标志）。茅台 RSI oversold 10d hit_rate 0.92。
- calculate_factor 失败错误信息优秀：value/growth 显式列出期望财务字段名。
- 技术/量价因子计算稳定合理；rsi/atr/kdj_k 别名解析成功。

## 因子库快照

50 因子：technical(动量/趋势/反转/RSI/MACD/威廉/CCI/MFI/KDJ/ROC)、risk(波动率/ATR/布林/下行)、volume(量比/OBV/VWAP/换手)、fundamental(PE/PB/PS/ROE/ROA/毛利/净利/负债/成长/股息)、alternative(情绪/资金流/北向/机构/事件)。
