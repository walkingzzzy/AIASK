# 通用函数概述

> 原始URL: https://help.tdx.com.cn/quant/docs/markdown/ctx.stock.md/
> 抓取时间: 2026-02-03

通用函数可以获取如下数据：

- **股票数据**：我们拥有所有A股上市公司2005年以来的股票行情数据、财务数据、上市公司基本信息、融资融券信息等。为了避免幸存者偏差，我们包括了已经退市的股票数据。其中volume（成交量）字段单位是股。

- **基金数据**：我们目前提供了多种在交易所上市的基金的行情、净值等数据，包含ETF、LOF、分级A/B基金以及货币基金的完整的行情、净值数据等，请点击基金数据查看。

- **股票指数**：我们支持指数数据，包括指数的行情数据以及成分股数据。为了避免未来函数，我们支持获取历史任意时刻的指数成分股信息，具体见get_index_stocks。

- **行业板块/概念板块**：我们支持按行业、按概念板块获取成分股，具体见获取A股板块代码列表get_sector_list及获取板块成份股get_stock_list_in_sector。

- **宏观数据**：我们提供全方位的宏观数据，为投资者决策提供有力数据支持。

- **金融期货数据**：我们提供中金所推出的所有金融期货产品的行情数据，并包含历史产品的数据。

- **商品期货**：我们支持从2005年以来上海国际能源交易中心、上期所、郑商所、大商所的行情数据，并包含历史产品的数据。

## 函数列表

| 函数名 | 说明 |
|--------|------|
| [initialize](./initialize.md) | 初始化，所有策略必须调用 |
| [subscribe_hq](./subscribe_hq.md) | 订阅行情实时更新 |
| [unsubscribe_hq](./unsubscribe_hq.md) | 取消订阅更新 |
| [get_subscribe_hq_stock_list](./get_subscribe_hq_stock_list.md) | 获得订阅列表 |
| [refresh_cache](./refresh_cache.md) | 刷新行情缓存 |
| [refresh_kline](./refresh_kline.md) | 缓存历史K线 |
| [send_message](./send_message.md) | 发送消息到TQ策略界面 |
| [send_warn](./send_warn.md) | 发送预警信号到客户端 |
| [send_file](./send_file.md) | 发送文件到客户端 |
| [send_bt_data](./send_bt_data.md) | 发送回测数据 |
| [download_file](./download_file.md) | 下载特定数据文件 |
| [get_trading_dates](./get_trading_dates.md) | 获取交易日列表 |

