from typing import List
from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task

# 原有工具
from tools.a_stock_data_tool import AStockDataTool
from tools.financial_tool import FinancialAnalysisTool
from tools.market_sentiment_tool import MarketSentimentTool
from tools.calculator_tool import CalculatorTool

# P0/P1 新增工具
from tools.ai_score_tool import AIScoreTool
from tools.technical_indicator_tool import TechnicalIndicatorTool
from tools.nlp_query_tool import NLPQueryTool
from tools.north_fund_tool import NorthFundFlowTool, NorthFundHoldingTool
from tools.dragon_tiger_tool import DragonTigerDailyTool, DragonTigerStockTool
from tools.sector_rotation_tool import SectorRotationTool, SectorFundFlowTool, SectorStocksTool

# P2/P3 新增工具
from tools.sentiment_tool import NewsStockTool, NewsSentimentTool, EventDetectionTool
from tools.limit_up_tool import LimitUpDailyTool, LimitUpStockTool, LimitUpConceptTool
from tools.margin_tool import MarginMarketTool, MarginStockTool, MarginTrendTool
from tools.block_trade_tool import BlockTradeMarketTool, BlockTradeStockTool, BlockTradeAnomalyTool
from tools.call_auction_tool import CallAuctionTool

# 知识库检索工具
from tools.knowledge_search_tool import KnowledgeSearchTool, SimilarStocksTool, RAGContextTool

import os
from dotenv import load_dotenv
load_dotenv()

# 从环境变量读取模型配置
model_name = os.getenv("OPENAI_MODEL_NAME", "gpt-4o")
api_key = os.getenv("OPENAI_API_KEY")
base_url = os.getenv("OPENAI_BASE_URL")
temperature = float(os.getenv("TEMPERATURE", "0.8"))
max_tokens = int(os.getenv("MAX_TOKENS", "14000"))

from crewai import LLM
llm = LLM(
    model=f"openai/{model_name}",
    api_key=api_key,
    base_url=base_url,
    temperature=temperature,
    max_tokens=max_tokens,
    top_p=0.9,
    frequency_penalty=0.1,
    presence_penalty=0.1,
    stop=["END"],
    seed=42
)

@CrewBase
class AStockAnalysisCrew:
    agents_config = 'config/agents.yaml'
    tasks_config = 'config/tasks.yaml'

    # ===== 原有 Agents =====
    
    @agent
    def a_stock_analyst(self) -> Agent:
        return Agent(
            config=self.agents_config['a_stock_analyst'],
            verbose=True,
            llm=llm,
            tools=[
                AStockDataTool(),
                FinancialAnalysisTool(),
                CalculatorTool(),
                TechnicalIndicatorTool(),  # 新增：技术指标工具
                SectorRotationTool(),      # 新增：板块轮动工具
                CallAuctionTool(),         # 新增：集合竞价分析工具
            ]
        )

    @task
    def market_analysis(self) -> Task:
        return Task(
            config=self.tasks_config['market_analysis'],
            agent=self.a_stock_analyst(),
        )

    @agent
    def financial_analyst(self) -> Agent:
        return Agent(
            config=self.agents_config['financial_analyst'],
            verbose=True,
            llm=llm,
            tools=[
                AStockDataTool(),
                FinancialAnalysisTool(),
                CalculatorTool(),
                AIScoreTool(),  # 新增：AI评分工具
            ]
        )

    @task
    def financial_analysis(self) -> Task:
        return Task(
            config=self.tasks_config['financial_analysis'],
            agent=self.financial_analyst(),
        )

    @agent
    def market_sentiment_agent(self) -> Agent:
        return Agent(
            config=self.agents_config['market_sentiment_analyst'],
            verbose=True,
            llm=llm,
            tools=[
                AStockDataTool(),
                MarketSentimentTool(),
                NorthFundFlowTool(),    # 新增：北向资金流向
                NorthFundHoldingTool(), # 新增：北向资金持仓
                SectorFundFlowTool(),   # 新增：板块资金流向
            ]
        )

    @task
    def sentiment_analysis(self) -> Task:
        return Task(
            config=self.tasks_config['sentiment_analysis'],
            agent=self.market_sentiment_agent(),
        )

    @agent
    def investment_advisor(self) -> Agent:
        return Agent(
            config=self.agents_config['investment_advisor'],
            verbose=True,
            llm=llm,
            tools=[
                CalculatorTool(),
                NLPQueryTool(),           # 自然语言查询
                KnowledgeSearchTool(),    # 新增：知识库检索
                SimilarStocksTool(),      # 新增：相似股票查询
                RAGContextTool(),         # 新增：RAG上下文
            ]
        )

    @task
    def investment_recommendation(self) -> Task:
        return Task(
            config=self.tasks_config['investment_recommendation'],
            agent=self.investment_advisor(),
        )

    # ===== P1 新增 Agents =====
    
    @agent
    def quant_analyst(self) -> Agent:
        """量化分析师 - 数据驱动的量化分析"""
        return Agent(
            config=self.agents_config['quant_analyst'],
            verbose=True,
            llm=llm,
            tools=[
                AStockDataTool(),
                AIScoreTool(),              # AI综合评分
                TechnicalIndicatorTool(),   # 技术指标分析
                SectorRotationTool(),       # 板块轮动
                SectorStocksTool(),         # 板块成分股
                CalculatorTool(),
                KnowledgeSearchTool(),      # 新增：知识库检索
                RAGContextTool(),           # 新增：RAG上下文
            ]
        )

    @task
    def quant_analysis(self) -> Task:
        return Task(
            config=self.tasks_config['quant_analysis'],
            agent=self.quant_analyst(),
        )

    @agent
    def risk_manager(self) -> Agent:
        """风险管理师 - 风险识别与控制"""
        return Agent(
            config=self.agents_config['risk_manager'],
            verbose=True,
            llm=llm,
            tools=[
                AStockDataTool(),
                NorthFundFlowTool(),        # 北向资金流向
                NorthFundHoldingTool(),     # 北向资金持仓
                DragonTigerDailyTool(),     # 龙虎榜每日数据
                DragonTigerStockTool(),     # 个股龙虎榜
                TechnicalIndicatorTool(),   # 技术指标（风险评估）
                CalculatorTool(),
            ]
        )

    @task
    def risk_assessment(self) -> Task:
        return Task(
            config=self.tasks_config['risk_assessment'],
            agent=self.risk_manager(),
        )

    # ===== P2 新增 Agents =====

    @agent
    def sentiment_analyst(self) -> Agent:
        """新闻情绪分析师 - 新闻舆情与事件分析"""
        return Agent(
            config=self.agents_config['sentiment_analyst'],
            verbose=True,
            llm=llm,
            tools=[
                AStockDataTool(),
                NewsStockTool(),          # 个股新闻获取
                NewsSentimentTool(),      # 新闻情绪分析
                EventDetectionTool(),     # 重大事件检测
            ]
        )

    @task
    def news_sentiment_analysis(self) -> Task:
        return Task(
            config=self.tasks_config['news_sentiment_analysis'],
            agent=self.sentiment_analyst(),
        )

    @agent
    def limit_up_analyst(self) -> Agent:
        """涨停板分析师 - 涨停原因与连板预测"""
        return Agent(
            config=self.agents_config['limit_up_analyst'],
            verbose=True,
            llm=llm,
            tools=[
                AStockDataTool(),
                LimitUpDailyTool(),       # 每日涨停数据
                LimitUpStockTool(),       # 个股涨停历史
                LimitUpConceptTool(),     # 涨停概念分析
            ]
        )

    @task
    def limit_up_analysis(self) -> Task:
        return Task(
            config=self.tasks_config['limit_up_analysis'],
            agent=self.limit_up_analyst(),
        )

    # ===== P3 新增 Agents (可选) =====

    @agent
    def margin_analyst(self) -> Agent:
        """融资融券分析师 - 两融数据分析"""
        return Agent(
            config=self.agents_config.get('margin_analyst', self.agents_config['financial_analyst']),
            verbose=True,
            llm=llm,
            tools=[
                AStockDataTool(),
                MarginMarketTool(),       # 市场两融数据
                MarginStockTool(),        # 个股两融数据
                MarginTrendTool(),        # 两融趋势分析
            ]
        )

    @task
    def margin_analysis(self) -> Task:
        return Task(
            config=self.tasks_config.get('margin_analysis', self.tasks_config['financial_analysis']),
            agent=self.margin_analyst(),
        )

    @agent
    def block_trade_analyst(self) -> Agent:
        """大宗交易分析师 - 大宗交易监控"""
        return Agent(
            config=self.agents_config.get('block_trade_analyst', self.agents_config['market_sentiment_analyst']),
            verbose=True,
            llm=llm,
            tools=[
                AStockDataTool(),
                BlockTradeMarketTool(),   # 市场大宗交易
                BlockTradeStockTool(),    # 个股大宗交易
                BlockTradeAnomalyTool(),  # 异常交易检测
            ]
        )

    @task
    def block_trade_analysis(self) -> Task:
        return Task(
            config=self.tasks_config.get('block_trade_analysis', self.tasks_config['sentiment_analysis']),
            agent=self.block_trade_analyst(),
        )

    @crew
    def crew(self) -> Crew:
        """创建A股分析团队"""
        return Crew(
            agents=self.agents,
            tasks=self.tasks,
            process=Process.sequential,
            verbose=True,
        )