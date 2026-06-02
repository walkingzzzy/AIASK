# N36 · 合规检查

**工具**: compliance_manager(help/check_order/get_restrictions/check/check_trade/rules)
**调用**: 30 次 · **结论**: pass_with_high_finding

## 覆盖
- rules / get_restrictions(600519/000001/300750/ZZZ999)
- check_order：正常/非整百/超数量/超金额/超涨停/低跌停/负数量/零数量/卖出/创业板20%/科创板/非法码/000001/sz000001
- check/check_trade 别名 + 非法 action

## 关键发现
| ID | 级别 | 摘要 |
|---|---|---|
| F-N36-1 | **high** | 000001 被误当上证指数(sh000001)，涨跌停用 4000 点级基准，11.5 买单被拒(N34 F-N34-1 同源根因)，sz000001 前缀亦未消歧 |
| F-N36-2 | **high** | check_order 非法代码 ZZZ999→000999 静默坐标化(对照 N34 paper_trading 拒绝) |
| F-N36-3 | medium | 非交易时段盘口量 0 被当违规 blocked(过度阻断，应同 trading_hours 仅 warning) |
| F-N36-4 | low | get_restrictions 仅返回通用静态限制，不含标的特定信息(涨跌停/ST/创业板20%)且不校验代码 |

## 正向能力
- **★★ 合规规则覆盖全面**：8 条规则 + 实时盘口校验。
- **★★ 涨跌停基准正确(除 000001)**：茅台/五粮液/比亚迪/平安/洋河主板 10%，创业板 300750 正确识别 20%。
- **★★ 数量/金额/价格校验精确**：非整百/超数量/超金额/超涨停/低跌停/负数量 全部正确拦截。
- **★ buy 查卖量/sell 查买量** 方向逻辑正确。
- check/check_trade 别名一致；realtime 字段透明(数据来源+涨跌停)。

## standing caveat
周末非交易：所有 check_order 因 trading_hours=false(warning)+盘口量 0(violation)被 blocked；涨跌停/lot_size/数量/金额等静态规则可正常验证；N21 已覆盖部分合规阻断。
