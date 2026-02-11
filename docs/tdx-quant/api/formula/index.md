# 调用通达信公式概述

> 原始URL: https://help.tdx.com.cn/quant/docs/markdown/mindoc-1h3hrvkp4sc0g/
> 抓取时间: 2026-02-03

调用通达信公式API允许您在Python中调用通达信的技术指标公式、条件选股公式和专家系统公式。

## 函数列表

| 函数名 | 说明 |
|--------|------|
| [formula_format_data](./formula_format_data.md) | 格式化K线数据 |
| [formula_set_data](./formula_set_data.md) | 向通达信公式系统设置数据 |
| [formula_set_data_info](./formula_set_data_info.md) | 向通达信公式系统设置数据信息 |
| [formula_get_data](./formula_get_data.md) | 获取公式中的设置数据 |
| [formula_zb](./formula_zb.md) | 调用通达信技术指标公式 |

## 支持的公式类型

1. **技术指标公式** - 使用 `formula_zb()` 调用，如MACD、KDJ、RSI等
2. **条件选股公式** - 使用 `formula_xg()` 调用
3. **专家系统公式** - 使用 `formula_exp()` 调用

