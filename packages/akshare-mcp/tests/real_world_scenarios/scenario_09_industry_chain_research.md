# 场景09：产业链深度研究

## 用户故事

**As a** 行业研究员
**I want** 从产业链视角分析某个行业的上中下游公司，结合研报和相似股票发现投资机会
**So that** 我可以构建基于产业链逻辑的投资组合，并同步到通达信监控

## 业务流程

```
产业链查询 → 上中下游公司 → 个股研报 → 相似股票搜索 → 基本面对比 → 创建自选股板块
```

## 涉及 MCP 工具

| 步骤 | 工具 | 用途 |
|------|------|------|
| 1 | `get_industry_chain` | 获取产业链信息（上中下游） |
| 2 | `get_stock_research` | 获取个股研究报告 |
| 3 | `search_research` | 搜索行业研报 |
| 4 | `get_profit_forecast` | 获取盈利预测和目标价 |
| 5 | `search_similar_stocks` | 搜索相似股票 |
| 6 | `search_by_kline` | K线形态相似搜索 |
| 7 | `get_financials` | 获取财务指标对比 |
| 8 | `get_stock_info` | 获取公司基本信息 |
| 9 | `create_watchlist` | 创建产业链自选股板块 |
| 10 | `research_manager` | 研究管理器 |

## 测试步骤

### Step 1: 产业链查询

```
调用: get_industry_chain
参数: keyword="新能源汽车"
预期: 返回新能源汽车产业链的上中下游环节
验证: 返回 chains 列表，每条包含 id/name/upstream/midstream/downstream 字段
      预置产业链包含: 新能源/半导体/光伏/白酒/医药
      如关键词无精确匹配，返回全部预置产业链并附 message 提示

关键词不命中验证:
调用: get_industry_chain
参数: keyword="航空航天"（非预置产业链）
预期: 返回全部预置产业链列表 + message 提示"未找到精确匹配，返回全部可用产业链"
验证: chains 列表非空（包含所有预置链），message 字段包含提示信息

调用: get_industry_chain
参数: keyword="半导体"
预期: 返回半导体产业链信息
验证: 包含设计/制造/封测等环节
注意: get_industry_chain 是独立工具（在 semantic.py 中注册），
      industry_chain_manager 是管理器工具（在 industry_chain_manager.py 中注册），
      两者功能有重叠但实现不同。独立工具使用预置数据，管理器支持 get_chain/related_stocks action。
```

### Step 2: 个股研报

```
调用: get_stock_research
参数: stock_code="300750", limit=5
预期: 返回宁德时代最近5篇研究报告
验证: 返回 reports 列表，每篇研报包含 title/author/org_name/date/rating 字段
      降级链: Tushare report_rc → 东财 datacenter → AkShare

调用: get_profit_forecast
参数: symbol="300750"
预期: 返回机构盈利预测
验证: 返回 items 列表，每条包含 date/institution/researcher/rating/eps_forecast/income_forecast/netprofit_forecast 字段
      降级链: 东财 datacenter → Tushare forecast → AkShare
```

### Step 3: 行业研报搜索

```
调用: search_research
参数: keyword="新能源汽车", days=30
预期: 返回最近30天的新能源汽车相关研报
验证: 研报数量 > 0，按日期降序排列
```

### Step 4: 相似股票搜索

```
调用: search_similar_stocks
参数: code="300750", top_n=10, similarity_type="fundamental"
预期: 返回基本面相似的10只股票
验证: 返回 similar_stocks 列表，每只包含 code/name/similarity(0-1)/features 字段
      similarity_type 支持: fundamental/technical/both
      相似度基于欧氏距离计算（PE/PB/ROE/动量/波动率等特征）
      如无相似结果，回退到同行业股票（relationship='same_industry'）

调用: search_by_kline
参数: code="300750", days=20, top_n=5
预期: 返回K线走势相似的5只股票
验证: 返回 results 列表，每只包含 code/name/similarity(0-1)/correlation(-1~1) 字段
      使用皮尔逊相关系数计算价格序列相似度
      如无相似结果，回退到同行业股票
```

### Step 5: 基本面对比

```
调用: get_financials
参数: stock_code="300750"
预期: 返回宁德时代财务指标
验证: 包含营收/净利润/ROE/毛利率等核心指标

调用: get_financials
参数: stock_code="002594"
预期: 返回比亚迪财务指标
验证: 可与宁德时代进行横向对比

行业基准对照说明:
  横向对比时应确保两只股票属于同一申万二级行业或产业链同一环节，
  避免跨行业误匹配（如将电池制造商与整车厂直接对比ROE）。
  search_similar_stocks 的回退机制（relationship='same_industry'）可辅助验证行业归属。
```

### Step 6: 创建产业链自选股

```
调用: create_watchlist
参数: block_code="MCP_NEV_CHAIN", block_name="新能源车产业链", stock_codes=["300750","002594","601012","300274","002049"]
预期: success=true
验证: 通达信客户端出现"新能源车产业链"板块
```

## TDX 前端交互

- 通达信自选股面板出现产业链板块
- 板块内按上中下游分组展示（通过板块命名区分）
- 用户可在通达信中直接对比产业链公司的K线和财务数据

## 边界条件

| 条件 | 处理方式 |
|------|---------|
| 产业链关键词无匹配 | 返回全部预置产业链 + 提示信息（非空结果） |
| 研报数据为空 | 降级到公告/新闻数据 |
| 相似股票搜索超时 | 减少搜索范围或降低top_n |
| 财务数据缺失（新股） | 返回可用字段，缺失字段标注null |
| 产业链公司已退市 | 自动过滤退市股票 |
| 自选股板块已存在 | 覆盖更新板块内容 |

## 已知限制

- `get_industry_chain` 依赖预置的产业链数据库，覆盖范围有限
- 研报数据来源: Tushare report_rc → 东财 datacenter → AkShare，字段映射已修正
- `search_similar_stocks` 基于有限的特征维度，相似度仅供参考
- `search_by_kline` 使用价格序列相关性，不考虑成交量等因素
- 产业链分析需要人工判断上下游关系，工具仅提供数据支持
