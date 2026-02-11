#!/usr/bin/env python3
"""
通达信量化平台文档抓取脚本
抓取 https://help.tdx.com.cn/quant/ 的所有文档并保存为Markdown格式
"""

import os
import re
import time
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urljoin

BASE_URL = "https://help.tdx.com.cn"
DOCS_DIR = os.path.dirname(os.path.abspath(__file__))

# 所有需要抓取的页面
PAGES = [
    # 概述部分
    ("/quant/", "overview/index.md", "TdxQuant简介"),
    ("/quant/docs/markdown/mindoc-1cfsjkbf8f3is/TdxQuantVersion.html", "overview/version.md", "版本更新说明"),
    ("/quant/docs/markdown/mindoc-1cfsjkbf8f3is/mindoc-1d00970eq1rtc.html", "overview/install-python.md", "安装Python及开发环境"),
    ("/quant/docs/markdown/mindoc-1cfsjkbf8f3is/mindoc-1d00kk3jsibbc.html", "overview/install-tdx.md", "安装通达信终端并获取数据"),
    ("/quant/docs/markdown/mindoc-1cfsjkbf8f3is/mindoc-1cv7o3nje2gu8.html", "overview/quick-start.md", "快速开始第一个策略"),
    
    # 通用函数
    ("/quant/docs/markdown/ctx.stock.md/", "api/common/index.md", "通用函数概述"),
    ("/quant/docs/markdown/ctx.stock.md/mindoc-1cv85e8u9nb0c.html", "api/common/initialize.md", "初始化initialize"),
    ("/quant/docs/markdown/ctx.stock.md/mindoc-1h1104d65vr68.html", "api/common/subscribe_hq.md", "订阅行情subscribe_hq"),
    ("/quant/docs/markdown/ctx.stock.md/mindoc-1h112vh7jtsms.html", "api/common/unsubscribe_hq.md", "取消订阅unsubscribe_hq"),
    ("/quant/docs/markdown/ctx.stock.md/mindoc-1h1137r4k2mas.html", "api/common/get_subscribe_hq_stock_list.md", "获得订阅列表"),
    ("/quant/docs/markdown/ctx.stock.md/mindoc-1h10f9145us1g.html", "api/common/refresh_cache.md", "刷新行情缓存refresh_cache"),
    ("/quant/docs/markdown/ctx.stock.md/mindoc-1h10fh9m6recg.html", "api/common/refresh_kline.md", "缓存历史K线refresh_kline"),
    ("/quant/docs/markdown/ctx.stock.md/mindoc-1h10rkbndkb0k.html", "api/common/send_message.md", "发送消息send_message"),
    ("/quant/docs/markdown/ctx.stock.md/mindoc-1h10u5k9qjh8o.html", "api/common/send_warn.md", "发送预警信号send_warn"),
    ("/quant/docs/markdown/ctx.stock.md/mindoc-1h10u17ue9464.html", "api/common/send_file.md", "发送文件send_file"),
    ("/quant/docs/markdown/ctx.stock.md/mindoc-1h10vc2pot87c.html", "api/common/send_bt_data.md", "发送回测数据send_bt_data"),
    ("/quant/docs/markdown/ctx.stock.md/mindoc-1h10pqrdlj71o.html", "api/common/download_file.md", "下载数据文件download_file"),
    ("/quant/docs/markdown/ctx.stock.md/mindoc-1h10q7i3702rk.html", "api/common/get_trading_dates.md", "获取交易日列表"),
    
    # 行情类信息
    ("/quant/docs/markdown/mindoc-1ctuhthaq5qmg/", "api/market/index.md", "行情类信息概述"),
    ("/quant/docs/markdown/mindoc-1ctuhthaq5qmg/mindoc-1h10g60jt68sc.html", "api/market/get_market_data.md", "获取K线数据get_market_data"),
    ("/quant/docs/markdown/mindoc-1ctuhthaq5qmg/mindoc-1h10iig4pb6e0.html", "api/market/get_market_snapshot.md", "获取快照数据get_market_snapshot"),
    ("/quant/docs/markdown/mindoc-1ctuhthaq5qmg/mindoc-1h10jj7r7jol4.html", "api/market/get_stock_info.md", "获取证券基本信息get_stock_info"),
    ("/quant/docs/markdown/mindoc-1ctuhthaq5qmg/mindoc-1h10hsiat36k4.html", "api/market/get_divid_factors.md", "获取分红配送数据"),
    ("/quant/docs/markdown/mindoc-1ctuhthaq5qmg/mindoc-1h137jr3khrqo.html", "api/market/get_ipo_info.md", "获取新股申购信息get_ipo_info"),
    ("/quant/docs/markdown/mindoc-1ctuhthaq5qmg/mindoc-1h3rtq1hij0ac.html", "api/market/get_more_info.md", "获取股票更多信息get_more_info"),
    ("/quant/docs/markdown/mindoc-1ctuhthaq5qmg/mindoc-1h3ru0b1tssrc.html", "api/market/get_gb_info.md", "获取每天的股本数据get_gb_info"),
    
    # 财务类数据
    ("/quant/docs/markdown/TdxQuant.md/", "api/finance/index.md", "财务类数据概述"),
    ("/quant/docs/markdown/TdxQuant.md/mindoc-1h10m001ic888.html", "api/finance/get_financial_data.md", "获取专业财务数据"),
    ("/quant/docs/markdown/TdxQuant.md/mindoc-1h10mdt617qss.html", "api/finance/get_financial_data_by_date.md", "获取指定日期财务数据"),
    ("/quant/docs/markdown/TdxQuant.md/mindoc-1h10muc82r55k.html", "api/finance/get_gpjy_value.md", "获取股票交易数据"),
    ("/quant/docs/markdown/TdxQuant.md/mindoc-1h2pci5gh6h7k.html", "api/finance/get_gpjy_value_by_date.md", "获取指定日期股票交易数据"),
    ("/quant/docs/markdown/TdxQuant.md/mindoc-1h10p0ncmp5mc.html", "api/finance/get_bkjy_value.md", "获取板块交易数据"),
    ("/quant/docs/markdown/TdxQuant.md/mindoc-1h10p3d31736g.html", "api/finance/get_bkjy_value_by_date.md", "获取指定日期板块交易数据"),
    ("/quant/docs/markdown/TdxQuant.md/mindoc-1h10p8op6ia9g.html", "api/finance/get_scjy_value.md", "获取市场交易数据"),
    ("/quant/docs/markdown/TdxQuant.md/mindoc-1h10pe678ta04.html", "api/finance/get_scjy_value_by_date.md", "获取指定日期市场交易数据"),
    ("/quant/docs/markdown/TdxQuant.md/mindoc-1h10pk3rsg044.html", "api/finance/get_gp_one_data.md", "获取股票的单个数据"),
]

# 继续添加更多页面...
PAGES_PART2 = [
    # 分类/板块成份股
    ("/quant/docs/markdown/mindoc-1ctuhttn72svo/", "api/sector/index.md", "分类板块成份股概述"),
    ("/quant/docs/markdown/mindoc-1ctuhttn72svo/mindoc-1h10r5907noko.html", "api/sector/get_sector_list.md", "获取A股板块代码列表"),
    ("/quant/docs/markdown/mindoc-1ctuhttn72svo/mindoc-1h10qo3uj48fg.html", "api/sector/get_stock_list.md", "获取系统成份股"),
    ("/quant/docs/markdown/mindoc-1ctuhttn72svo/mindoc-1h10r92mchgug.html", "api/sector/get_stock_list_in_sector.md", "获取板块成份股"),
    
    # 自选股/自定义板块
    ("/quant/docs/markdown/mindoc-1h139a4ckchkk/", "api/custom-sector/index.md", "自选股自定义板块概述"),
    ("/quant/docs/markdown/mindoc-1h139a4ckchkk/mindoc-1h1hauh9inaac.html", "api/custom-sector/get_user_sector.md", "获取自定义板块列表"),
    ("/quant/docs/markdown/mindoc-1h139a4ckchkk/mindoc-1h10rrkuj1drs.html", "api/custom-sector/create_sector.md", "创建自定义板块"),
    ("/quant/docs/markdown/mindoc-1h139a4ckchkk/mindoc-1h10s391lng6s.html", "api/custom-sector/delete_sector.md", "删除自定义板块"),
    ("/quant/docs/markdown/mindoc-1h139a4ckchkk/mindoc-1h10s7n863d50.html", "api/custom-sector/rename_sector.md", "重命名自定义板块"),
    ("/quant/docs/markdown/mindoc-1h139a4ckchkk/mindoc-1h10sec960u0c.html", "api/custom-sector/send_user_block.md", "添加自定义板块成份股"),
    ("/quant/docs/markdown/mindoc-1h139a4ckchkk/mindoc-1h10sbcnl1c94.html", "api/custom-sector/clear_sector.md", "清空自定义板块成份股"),
    
    # 债券和期货数据
    ("/quant/docs/markdown/mindoc-1h13a594nhvb4/", "api/bond-futures/index.md", "债券和期货数据概述"),
    ("/quant/docs/markdown/mindoc-1h13a594nhvb4/mindoc-1h137euvcjn98.html", "api/bond-futures/get_cb_info.md", "可转债基础信息get_cb_info"),
    ("/quant/docs/markdown/mindoc-1h13a594nhvb4/mindoc-1cu7okhdr4f8g.html", "api/bond-futures/product_basic.md", "期货品种基本信息"),
    ("/quant/docs/markdown/mindoc-1h13a594nhvb4/mindoc-1cu7omi7t4lp8.html", "api/bond-futures/future_basic.md", "合约详细信息"),
    
    # 调用通达信公式
    ("/quant/docs/markdown/mindoc-1h3hrvkp4sc0g/", "api/formula/index.md", "调用通达信公式概述"),
    ("/quant/docs/markdown/mindoc-1h3hrvkp4sc0g/mindoc-1h3hte6obagc0.html", "api/formula/formula_format_data.md", "格式化K线数据"),
    ("/quant/docs/markdown/mindoc-1h3hrvkp4sc0g/mindoc-1h3hsvcct5sdc.html", "api/formula/formula_set_data.md", "设置数据formula_set_data"),
    ("/quant/docs/markdown/mindoc-1h3hrvkp4sc0g/mindoc-1h3hs08rn02uc.html", "api/formula/formula_set_data_info.md", "设置数据信息"),
    ("/quant/docs/markdown/mindoc-1h3hrvkp4sc0g/mindoc-1h3httgemshno.html", "api/formula/formula_get_data.md", "获取公式中的设置数据"),
    ("/quant/docs/markdown/mindoc-1h3hrvkp4sc0g/mindoc-1h3huq37005ro.html", "api/formula/formula_zb.md", "调用通达信公式进行计算"),
    
    # 其他
    ("/quant/docs/markdown/Dict.html", "api/constants.md", "常量枚举"),
    ("/quant/docs/markdown/mindoc-1h12t4q6fg29o.html", "examples/backtest.md", "回测及模拟交易"),
    ("/quant/docs/markdown/mindoc-1h1525ci3mnkc/", "examples/index.md", "场景化示例概述"),
    ("/quant/docs/markdown/mindoc-1h1525ci3mnkc/mindoc-1h15262vnafcc.html", "examples/select-stock.md", "执行选股入板块"),
    ("/quant/docs/markdown/mindoc-1h1525ci3mnkc/mindoc-1h1526nmnk5n4.html", "examples/realtime-alert.md", "订阅行情涨幅突破实时预警"),
    ("/quant/docs/markdown/mindoc-1h1525ci3mnkc/mindoc-1h1ep1rl20jv8.html", "examples/trade-signal.md", "计算调仓信号并快速买卖"),
    ("/quant/docs/markdown/gzh0122inweixinwenz.html", "examples/wechat-articles.md", "公众号文章例子"),
    ("/quant/docs/markdown/mindoc-tdxpy.html", "faq.md", "常见问题"),
]

ALL_PAGES = PAGES + PAGES_PART2

if __name__ == "__main__":
    print(f"共需抓取 {len(ALL_PAGES)} 个页面")

