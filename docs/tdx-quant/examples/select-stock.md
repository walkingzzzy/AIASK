# 执行选股入板块

> 原始URL: https://help.tdx.com.cn/quant/docs/markdown/mindoc-1h1525ci3mnkc/mindoc-1h15262vnafcc.html
> 抓取时间: 2026-02-03

## 功能说明

本示例演示如何执行选股策略并将筛选结果加入客户端自定义板块。

## 核心步骤

### 第一步：执行选股策略

1. **基础配置**：设置目标板块、数据起始日期、连续上涨天数阈值、自定义板块信息
2. **获取数据**：使用 `get_market_data` 获取收盘价数据
3. **计算连续上涨天数**：通过pandas计算每只股票的连续上涨天数
4. **筛选符合条件的股票**：筛选连续上涨≥N天的股票

### 第二步：操作自定义板块

1. 使用 `create_sector` 创建自定义板块
2. 使用 `send_user_block` 将筛选结果添加到板块
3. 使用 `send_message` 发送提示消息到TQ策略管理器

## 关键API

| API | 说明 |
|-----|------|
| `get_stock_list_in_sector()` | 获取板块成份股 |
| `get_market_data()` | 获取K线数据 |
| `price_df()` | 转换为价格DataFrame |
| `create_sector()` | 创建自定义板块 |
| `send_user_block()` | 添加股票到自定义板块 |
| `send_message()` | 发送消息到客户端 |

## 运行效果

- VSCode端：输出符合条件的股票列表及连续上涨天数
- 通达信终端：自定义板块中显示筛选出的股票

