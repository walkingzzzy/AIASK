# 通达信量化平台 TdxQuant 文档

> 本地离线文档库 - 抓取自 https://help.tdx.com.cn/quant/
> 
> 抓取时间: 2026-02-03

## 📚 文档目录

### 概述
- [TdxQuant简介](./overview/index.md)
- [版本更新说明](./overview/version.md)
- [安装Python及开发环境](./overview/install-python.md)
- [安装通达信终端并获取数据](./overview/install-tdx.md)
- [快速开始第一个策略](./overview/quick-start.md)

### API参考

#### 通用函数
- [通用函数概述](./api/common/index.md)
- [初始化 initialize](./api/common/initialize.md)
- [订阅行情 subscribe_hq](./api/common/subscribe_hq.md)
- [取消订阅 unsubscribe_hq](./api/common/unsubscribe_hq.md)
- [获得订阅列表 get_subscribe_hq_stock_list](./api/common/get_subscribe_hq_stock_list.md)
- [刷新行情缓存 refresh_cache](./api/common/refresh_cache.md)
- [缓存历史K线 refresh_kline](./api/common/refresh_kline.md)
- [发送消息 send_message](./api/common/send_message.md)
- [发送预警信号 send_warn](./api/common/send_warn.md)
- [发送文件 send_file](./api/common/send_file.md)
- [发送回测数据 send_bt_data](./api/common/send_bt_data.md)
- [下载数据文件 download_file](./api/common/download_file.md)
- [获取交易日列表 get_trading_dates](./api/common/get_trading_dates.md)

#### 行情类信息
- [行情类信息概述](./api/market/index.md)
- [获取K线数据 get_market_data](./api/market/get_market_data.md)
- [获取快照数据 get_market_snapshot](./api/market/get_market_snapshot.md)
- [获取证券基本信息 get_stock_info](./api/market/get_stock_info.md)
- [获取分红配送数据 get_divid_factors](./api/market/get_divid_factors.md)
- [获取新股申购信息 get_ipo_info](./api/market/get_ipo_info.md)
- [获取股票更多信息 get_more_info](./api/market/get_more_info.md)
- [获取每天的股本数据 get_gb_info](./api/market/get_gb_info.md)

#### 财务类数据
- [财务类数据概述](./api/finance/index.md)
- [获取专业财务数据 get_financial_data](./api/finance/get_financial_data.md)
- [获取指定日期财务数据 get_financial_data_by_date](./api/finance/get_financial_data_by_date.md)
- [获取股票交易数据 get_gpjy_value](./api/finance/get_gpjy_value.md)
- [获取指定日期股票交易数据 get_gpjy_value_by_date](./api/finance/get_gpjy_value_by_date.md)
- [获取板块交易数据 get_bkjy_value](./api/finance/get_bkjy_value.md)
- [获取指定日期板块交易数据 get_bkjy_value_by_date](./api/finance/get_bkjy_value_by_date.md)
- [获取市场交易数据 get_scjy_value](./api/finance/get_scjy_value.md)
- [获取指定日期市场交易数据 get_scjy_value_by_date](./api/finance/get_scjy_value_by_date.md)
- [获取股票的单个数据 get_gp_one_data](./api/finance/get_gp_one_data.md)

#### 分类/板块成份股
- [分类板块成份股概述](./api/sector/index.md)
- [获取A股板块代码列表 get_sector_list](./api/sector/get_sector_list.md)
- [获取系统成份股 get_stock_list](./api/sector/get_stock_list.md)
- [获取板块成份股 get_stock_list_in_sector](./api/sector/get_stock_list_in_sector.md)

#### 自选股/自定义板块
- [自选股自定义板块概述](./api/custom-sector/index.md)
- [获取自定义板块列表 get_user_sector](./api/custom-sector/get_user_sector.md)
- [创建自定义板块 create_sector](./api/custom-sector/create_sector.md)
- [删除自定义板块 delete_sector](./api/custom-sector/delete_sector.md)
- [重命名自定义板块 rename_sector](./api/custom-sector/rename_sector.md)
- [添加自定义板块成份股 send_user_block](./api/custom-sector/send_user_block.md)
- [清空自定义板块成份股 clear_sector](./api/custom-sector/clear_sector.md)

#### 债券和期货数据
- [债券和期货数据概述](./api/bond-futures/index.md)
- [可转债基础信息 get_cb_info](./api/bond-futures/get_cb_info.md)
- 期货品种基本信息 product_basic（暂未开放）
- 合约详细信息 future_basic（暂未开放）

#### 调用通达信公式
- [调用通达信公式概述](./api/formula/index.md)
- [格式化K线数据 formula_format_data](./api/formula/formula_format_data.md)
- [设置数据 formula_set_data](./api/formula/formula_set_data.md)
- [设置数据信息 formula_set_data_info](./api/formula/formula_set_data_info.md)
- [获取公式中的设置数据 formula_get_data](./api/formula/formula_get_data.md)
- [调用通达信公式进行计算 formula_zb](./api/formula/formula_zb.md)

### 常量枚举
- [常量枚举](./api/constants.md)

### 示例
- [回测及模拟交易](./examples/backtest.md)
- [场景化示例概述](./examples/index.md)
- [执行选股入板块](./examples/select-stock.md)
- [订阅行情涨幅突破实时预警](./examples/realtime-alert.md)
- [计算调仓信号并快速买卖](./examples/trade-signal.md)
- [公众号文章例子](./examples/wechat-articles.md)

### 常见问题
- [常见问题FAQ](./faq.md)

---

## 🔗 官方资源

- 官方文档: https://help.tdx.com.cn/quant/
- 通达信官网: https://www.tdx.com.cn/

