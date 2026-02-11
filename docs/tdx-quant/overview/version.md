# TdxQuant版本及更新说明

> 原始URL: https://help.tdx.com.cn/quant/docs/markdown/mindoc-1cfsjkbf8f3is/TdxQuantVersion.html
> 抓取时间: 2026-02-03

## 📋 更新日志

### 📅 2026-01-31 更新说明

**新增功能：**
- 支持调用通达信公式进行计算

**新增函数：**
- `formula_format_data` - 格式化K线数据
- `formula_set_data` - 向通达信公式系统设置数据
- `formula_set_data_info` - 向通达信公式系统设置数据信息
- `formula_get_data` - 获取公式中的设置数据
- `formula_zb` - 调用通达信技术指标公式
- `formula_xg` - 调用通达信条件选股公式
- `formula_exp` - 调用通达信专家系统公式
- `get_more_info` - 获取股票更多信息
- `get_gb_info` - 获取每天的股本数据

**更新函数：**
- `refresh_cache` - 刷新行情缓存，新增参数force和market，可指定强制刷新或指定市场刷新

**其他更新：**
- 新增中证指数（.CSI），中金所期货（.CFF），宏观数据（.HG）等市场后缀识别和数据获取
- 获取非指定日期的股票交易数据，板块交易数据等数据时增加了对应日期返回

**问题修复：**
- 修复了部分市场数据返回时小数位数不对导致的精度问题
- 修复了获取Python3.9以及之前版本依赖库错误问题

### 📅 2026-01-17 正式发布

TdxQuant 正式发布首个版本。

