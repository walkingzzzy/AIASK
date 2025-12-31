# A股智能分析系统

基于AKShare的A股智能分析系统，使用CrewAI多Agent协作进行股票数据分析与决策支持。

## 项目概述

本系统利用先进的多Agent协作框架(CrewAI)和丰富的A股市场数据(AKShare)，构建了一个全面的股票分析平台。系统通过多个专业Agent协同工作，提供从数据获取、财务分析到市场情绪研判的全流程服务，帮助投资者做出更明智的投资决策。

## 🚀 快速开始

### 启动Web界面（推荐）

```bash
# 安装依赖
pip install -e .

# 启动Streamlit应用
python run_app.py
# 或
streamlit run app/streamlit_app.py
```

访问 http://localhost:8501 即可使用Web界面。

### 运行示例代码

```bash
python examples/demo_ai_score.py
```

### 运行回测

```python
from packages.core.backtest import BacktestEngine, AIScoreStrategy

# 创建回测引擎
engine = BacktestEngine(initial_capital=100000)

# 运行AI评分策略回测
result = engine.run(
    strategy=AIScoreStrategy,
    stock_code="600519",
    start_date="20230101",
    end_date="20231231"
)

# 查看回测报告
print(result.summary())
```

## 功能特性

### 🎯 P0核心功能（已完成）

- **AI智能评分**：基于5个维度（技术面/基本面/资金面/情绪面/风险）的1-10分综合评分
- **技术指标库**：MA/EMA/MACD/RSI/KDJ/BOLL/ATR等10+核心指标
- **自然语言查询**：支持股票筛选、个股分析、数据查询三类意图
- **评分解释**：可解释AI，展示因子贡献和投资建议
- **多源数据**：AKShare主数据源 + Tushare备用数据源
- **智能缓存**：内存+SQLite两级缓存，提升响应速度

### 🚀 P1增强功能（已完成）

- **向量知识库**：SQLite向量存储 + FTS5全文搜索，支持RAG检索
- **北向资金追踪**：资金流向分析、个股持仓查询、持仓排名
- **龙虎榜分析**：每日龙虎榜、席位分析、机构/游资追踪
- **回测系统**：基于backtrader的策略回测，支持AI评分策略和动量策略
- **完整测试覆盖**：数据层、指标、评分、NLP、服务层、回测集成测试

### 原有功能

- **A股数据获取**：获取A股股票的实时行情、历史K线数据、财务指标和板块数据
- **财务分析**：深度分析公司财务报表，计算关键财务比率，识别财务趋势和风险
- **市场情绪分析**：跟踪资金流向、分析新闻情绪和技术面指标，综合评估市场情绪
- **智能计算支持**：提供安全的数学计算工具，辅助投资决策过程中的数值计算

### 工具详情

1. **A股数据获取工具**
   - 支持获取实时行情数据（最新价、涨跌幅、成交量等）
   - 提供历史日线数据（支持指定时间范围）
   - 可获取财务数据（包括财务报表主要指标）
   - 支持板块数据查询（行业分类和板块行情）

2. **财务分析工具**
   - 财务比率分析：计算盈利能力、偿债能力、运营能力等核心比率
   - 趋势分析：分析财务指标的历史变化趋势
   - 同业对比：与同行业公司进行财务指标对比分析

3. **市场情绪分析工具**
   - 资金流向分析：监控主力资金流入流出情况
   - 新闻情绪分析：抓取并分析相关新闻的情感倾向
   - 技术情绪分析：基于技术指标评估市场情绪

4. **计算器工具**
   - 支持基本数学运算（加减乘除）
   - 提供高级运算功能（指数、对数等）
   - 安全的表达式解析，防止代码注入

## 依赖环境

- Python 3.12+（最高支持3.13）
- CrewAI 0.152.0+（多Agent协作框架）
- AKShare 1.12.0+（A股数据接口库）
- Pydantic 2.0.0+（数据验证库）
- Pandas 2.0.0+（数据处理库）
- NumPy 1.24.0+（科学计算库）
- 其他依赖详见pyproject.toml

## 安装步骤

### 方法一：使用Poetry（推荐）

```bash
# 克隆仓库
git clone <repository_url>
cd crewAI-examples-main/crews/stock_analysis_a_stock/src/a_stock_analysis

# 安装poetry（如果尚未安装）
pip install poetry

# 使用poetry安装依赖
poetry install

# 配置环境变量
copy .env.example .env
# 编辑.env文件，填写必要的API密钥
```

### 方法二：使用pip

```bash
# 克隆仓库
git clone <repository_url>
cd crewAI-examples-main/crews/stock_analysis_a_stock/src/a_stock_analysis

# 使用pip安装依赖
pip install -e .

# 配置环境变量
copy .env.example .env
# 编辑.env文件，填写必要的API密钥
```

## 使用方法

### 基本使用

```bash
# 使用Python直接运行
python main.py

# 或使用poetry运行（推荐）
poetry run a_stock_analysis
```

### 使用示例

运行程序后，系统会自动执行以下流程：

1. 创建专业的A股分析师Agent
2. 分配市场分析和财务分析任务
3. Agent使用各种工具进行分析
4. 生成完整的股票分析报告

系统默认分析的是贵州茅台（600519.SH），您可以在`main.py`中修改分析目标。

## 项目结构

```
src/a_stock_analysis/
├── .env                # 环境变量配置文件
├── .env.example        # 环境变量模板文件
├── __init__.py         # 包初始化文件
├── crew.py             # CrewAI配置和Agent定义
├── main.py             # 主入口文件
├── run_app.py          # Streamlit应用启动脚本
├── config/             # 配置文件目录
│   ├── agents.yaml     # Agent配置
│   └── tasks.yaml      # Task配置
├── app/                # Web应用（P0新增）
│   └── streamlit_app.py  # Streamlit MVP界面
├── data_layer/         # 数据层（P0新增）
│   ├── sources/        # 数据源适配器
│   │   ├── base_adapter.py      # 基础适配器
│   │   ├── akshare_adapter.py   # AKShare适配器
│   │   ├── tushare_adapter.py   # Tushare备用适配器
│   │   └── source_aggregator.py # 多源聚合器
│   ├── cache/          # 缓存层
│   │   └── cache_manager.py     # 两级缓存管理
│   └── quality/        # 数据质量
│       └── validator.py         # 数据验证器
├── indicators/         # 技术指标库（P0新增）
│   ├── trend.py        # 趋势指标（MA/EMA/MACD/DMI）
│   ├── momentum.py     # 动量指标（RSI/KDJ/CCI）
│   ├── volatility.py   # 波动率指标（BOLL/ATR）
│   └── volume.py       # 成交量指标（OBV/VWAP）
├── scoring/            # AI评分系统（P0新增）
│   ├── ai_score/       # 评分计算
│   │   ├── score_components.py  # 5维度评分组件
│   │   └── score_calculator.py  # 综合评分计算器
│   └── explainer/      # 评分解释
│       └── score_explainer.py   # 可解释AI
├── nlp_query/          # 自然语言查询（P0新增）
│   ├── intent_parser.py    # 意图解析器
│   └── query_executor.py   # 查询执行器
├── services/           # 服务层（P0新增）
│   └── stock_data_service.py  # 统一数据服务
├── tools/              # CrewAI工具集合
│   ├── a_stock_data_tool.py       # A股数据获取工具
│   ├── financial_tool.py          # 财务分析工具
│   ├── market_sentiment_tool.py   # 市场情绪分析工具
│   ├── calculator_tool.py         # 计算器工具
│   ├── ai_score_tool.py           # AI评分工具（P0新增）
│   ├── technical_indicator_tool.py # 技术指标工具（P0新增）
│   ├── nlp_query_tool.py          # NLP查询工具（P0新增）
│   ├── north_fund_tool.py         # 北向资金工具（P1新增）
│   └── dragon_tiger_tool.py       # 龙虎榜工具（P1新增）
├── vector_store/       # 向量知识库（P1新增）
│   ├── embeddings/     # 向量化模型
│   │   └── embedding_models.py    # OpenAI/本地模型
│   ├── storage/        # 向量存储
│   │   └── sqlite_vector_store.py # SQLite向量存储
│   └── retrieval/      # 检索器
│       └── retriever.py           # 混合检索+RAG
├── backtest/           # 回测系统（P1新增）
│   ├── data_feed.py    # AKShare数据源适配器
│   ├── strategies.py   # 策略类（BaseStrategy/AIScoreStrategy/MomentumStrategy）
│   └── engine.py       # 回测引擎（BacktestEngine/BacktestResult）
├── tests/              # 测试模块（P1新增）
│   ├── test_data_layer.py         # 数据层测试
│   ├── test_indicators.py         # 指标测试
│   ├── test_scoring.py            # 评分测试
│   ├── test_nlp_query.py          # NLP查询测试
│   ├── test_services.py           # 服务测试
│   ├── test_vector_store.py       # 向量库测试
│   └── test_backtest.py           # 回测系统测试
└── examples/           # 示例代码（P0新增）
    └── demo_ai_score.py  # AI评分演示
```

## 配置说明

### 环境变量配置

在`.env`文件中，您需要配置以下环境变量：

- `OPENAI_API_KEY`：OpenAI API密钥（用于LLM服务）
- 其他可能需要的API密钥（根据实际使用的服务）

### 配置文件

- `config/agents.yaml`：定义系统中使用的Agent及其角色、目标和背景
- `config/tasks.yaml`：定义Agent需要执行的任务

## 数据来源

本系统主要使用AKShare库获取A股市场数据：

- 实时行情数据：来自各大交易所的实时行情
- 历史数据：包含A股市场多年的交易数据
- 财务数据：上市公司公开披露的财务报表数据
- 板块数据：市场分类和板块行情信息

## 常见问题解答(FAQ)

### 1. 运行时出现`ImportError: cannot import name 'BaseTool'`错误怎么办？

这是因为crewAI版本更新导致API变更。请确保：
- 所有工具文件中使用`from crewai.tools import BaseTool`而非`from crewai import BaseTool`
- 使用正确版本的pydantic（v2.x）

### 2. 数据获取失败怎么办？

- 检查网络连接是否正常
- 确认AKShare库已正确安装且版本不低于1.12.0
- 验证股票代码格式是否正确（如：000001.SZ或600519.SH）

### 3. 如何修改分析的股票？

编辑`main.py`文件，修改`run()`函数中的股票代码参数。

### 4. 如何扩展系统功能？

- 在`tools`目录下创建新的工具文件
- 在`crew.py`中定义新的Agent或任务
- 在`config`目录下更新相关配置

## 贡献指南

我们欢迎社区贡献，如果您有任何想法或发现问题，请通过以下方式参与：

1. 提交Issue报告问题或提出新功能建议
2. 提交Pull Request贡献代码
3. 完善文档和示例

## 许可证

本项目采用MIT许可证，详情请参阅LICENSE文件。

## 免责声明

本系统仅提供数据分析服务，不构成任何投资建议。投资有风险，入市需谨慎。请在做出投资决策前进行充分的研究和分析。

## 致谢

- 感谢CrewAI团队提供强大的多Agent协作框架
- 感谢AKShare团队提供全面的A股市场数据接口
- 感谢所有为开源社区做出贡献的开发者