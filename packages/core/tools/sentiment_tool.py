"""
情绪分析工具
提供新闻情绪分析、事件检测等功能的CrewAI工具
"""
from typing import Dict, Any, List, Optional
import logging

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

from ..sentiment.news_crawler import NewsCrawler, NewsArticle
from ..sentiment.sentiment_analyzer import SentimentAnalyzer, SentimentResult
from ..sentiment.event_detector import EventDetector, StockEvent

logger = logging.getLogger(__name__)


# ==================== 输入模型 ====================

class StockSentimentInput(BaseModel):
    """股票情绪分析输入"""
    stock_code: str = Field(description="股票代码，如600519")
    stock_name: str = Field(default="", description="股票名称（可选）")


class MarketSentimentInput(BaseModel):
    """市场情绪分析输入"""
    limit: int = Field(default=20, description="获取新闻数量")


class StockNewsInput(BaseModel):
    """股票新闻查询输入"""
    stock_code: str = Field(description="股票代码")
    days: int = Field(default=7, description="获取最近几天的新闻")
    limit: int = Field(default=10, description="返回数量")


class EventDetectionInput(BaseModel):
    """事件检测输入"""
    stock_code: str = Field(description="股票代码")
    stock_name: str = Field(default="", description="股票名称")


# ==================== CrewAI工具 ====================

class StockSentimentTool(BaseTool):
    """
    股票情绪分析工具
    
    分析个股的新闻情绪、公告情绪、研报情绪，
    生成综合情绪评分和关键事件。
    """
    name: str = "stock_sentiment_analysis"
    description: str = """分析个股的市场情绪。
    输入股票代码，返回：
    - 综合情绪评分（-1到1，正为看多）
    - 情绪级别（极度看多/偏多/中性/偏空/极度看空）
    - 新闻情绪分析
    - 公告情绪分析
    - 研报情绪分析
    - 关键事件列表
    - 情绪变化趋势
    """
    args_schema: type[BaseModel] = StockSentimentInput
    
    def _run(self, stock_code: str, stock_name: str = "") -> str:
        """执行情绪分析"""
        try:
            analyzer = SentimentAnalyzer()
            result = analyzer.analyze_stock(stock_code, stock_name)
            
            # 格式化输出
            output = f"""
📊 {stock_name or stock_code} 情绪分析报告

【综合情绪】
- 情绪评分：{result.overall_score}（-1到1，正为看多）
- 情绪级别：{result.sentiment_level}
- 置信度：{result.confidence}

【新闻情绪】
- 情绪分数：{result.news_sentiment.get('score', 0)}
- 新闻数量：{result.news_sentiment.get('count', 0)}
- 正面/负面/中性：{result.news_sentiment.get('positive', 0)}/{result.news_sentiment.get('negative', 0)}/{result.news_sentiment.get('neutral', 0)}

【公告情绪】
- 情绪分数：{result.announcement_sentiment.get('score', 0)}
- 公告数量：{result.announcement_sentiment.get('count', 0)}
- 重要公告：{result.announcement_sentiment.get('important_count', 0)}条

【研报情绪】
- 情绪分数：{result.research_sentiment.get('score', 0)}
- 研报数量：{result.research_sentiment.get('count', 0)}
- 上调/下调/维持：{result.research_sentiment.get('upgrades', 0)}/{result.research_sentiment.get('downgrades', 0)}/{result.research_sentiment.get('maintains', 0)}

【情绪趋势】
- 变化方向：{result.trend.get('direction', '未知')}
- 变化幅度：{result.trend.get('change', 0)}

【关键事件】
"""
            for i, event in enumerate(result.key_events[:5], 1):
                impact_emoji = "🟢" if event['impact'] == 'positive' else ("🔴" if event['impact'] == 'negative' else "⚪")
                output += f"{i}. {impact_emoji} {event['event'][:50]}... ({event['source']})\n"
            
            output += f"\n更新时间：{result.updated_at}"
            
            return output
            
        except Exception as e:
            logger.error(f"情绪分析失败: {e}")
            return f"情绪分析失败: {str(e)}"


class MarketSentimentTool(BaseTool):
    """
    市场整体情绪分析工具
    
    分析市场热点新闻，判断整体市场情绪。
    """
    name: str = "market_sentiment_analysis"
    description: str = """分析市场整体情绪。
    获取市场热点新闻，分析整体市场情绪倾向。
    返回市场情绪评分和热点事件。
    """
    args_schema: type[BaseModel] = MarketSentimentInput
    
    def _run(self, limit: int = 20) -> str:
        """执行市场情绪分析"""
        try:
            crawler = NewsCrawler()
            analyzer = SentimentAnalyzer()
            
            # 获取市场新闻
            news_list = crawler.get_market_news(limit)
            
            # 分析情绪
            positive = 0
            negative = 0
            neutral = 0
            total_score = 0.0
            
            for news in news_list:
                score, _ = analyzer.analyze_text(news.title + news.content)
                total_score += score
                
                if score > 0.1:
                    positive += 1
                elif score < -0.1:
                    negative += 1
                else:
                    neutral += 1
            
            avg_score = total_score / len(news_list) if news_list else 0
            
            # 判断市场情绪
            if avg_score > 0.3:
                market_mood = "乐观"
            elif avg_score > 0.1:
                market_mood = "偏乐观"
            elif avg_score > -0.1:
                market_mood = "中性"
            elif avg_score > -0.3:
                market_mood = "偏悲观"
            else:
                market_mood = "悲观"
            
            output = f"""
📈 市场情绪分析报告

【整体情绪】
- 情绪评分：{avg_score:.2f}（-1到1）
- 市场情绪：{market_mood}
- 分析新闻数：{len(news_list)}

【情绪分布】
- 正面新闻：{positive}条 ({positive/len(news_list)*100:.1f}%)
- 负面新闻：{negative}条 ({negative/len(news_list)*100:.1f}%)
- 中性新闻：{neutral}条 ({neutral/len(news_list)*100:.1f}%)

【热点新闻】
"""
            for i, news in enumerate(news_list[:5], 1):
                score, _ = analyzer.analyze_text(news.title)
                emoji = "🟢" if score > 0.1 else ("🔴" if score < -0.1 else "⚪")
                output += f"{i}. {emoji} {news.title[:40]}...\n"
            
            return output
            
        except Exception as e:
            logger.error(f"市场情绪分析失败: {e}")
            return f"市场情绪分析失败: {str(e)}"


class StockNewsTool(BaseTool):
    """
    股票新闻查询工具
    
    获取个股相关新闻列表。
    """
    name: str = "stock_news_query"
    description: str = """查询个股相关新闻。
    输入股票代码，返回最近的相关新闻列表，
    包括新闻标题、来源、发布时间等信息。
    """
    args_schema: type[BaseModel] = StockNewsInput
    
    def _run(self, stock_code: str, days: int = 7, limit: int = 10) -> str:
        """查询股票新闻"""
        try:
            crawler = NewsCrawler()
            news_list = crawler.get_stock_news(stock_code, days, limit)
            
            if not news_list:
                return f"未找到{stock_code}的相关新闻"
            
            output = f"📰 {stock_code} 相关新闻（近{days}天）\n\n"
            
            for i, news in enumerate(news_list, 1):
                importance_star = "⭐" * int(news.importance * 5)
                output += f"{i}. 【{news.source}】{news.title}\n"
                output += f"   时间：{news.publish_time} | 重要性：{importance_star}\n"
                if news.content:
                    output += f"   摘要：{news.content[:80]}...\n"
                output += "\n"
            
            return output
            
        except Exception as e:
            logger.error(f"新闻查询失败: {e}")
            return f"新闻查询失败: {str(e)}"


class EventDetectionTool(BaseTool):
    """
    事件检测工具
    
    从新闻中检测重大事件。
    """
    name: str = "event_detection"
    description: str = """检测个股相关的重大事件。
    分析新闻和公告，识别业绩、并购、增减持、
    监管处罚等重大事件，评估事件影响。
    """
    args_schema: type[BaseModel] = EventDetectionInput
    
    def _run(self, stock_code: str, stock_name: str = "") -> str:
        """检测事件"""
        try:
            crawler = NewsCrawler()
            detector = EventDetector()
            
            # 获取新闻和公告
            news_list = crawler.get_stock_news(stock_code, days=7, limit=20)
            announcements = crawler.get_stock_announcements(stock_code, limit=10)
            
            # 检测事件
            all_articles = news_list + announcements
            events = detector.detect_events(all_articles, stock_code, stock_name)
            
            # 生成摘要
            summary = detector.get_event_summary(events)
            
            output = f"""
🎯 {stock_name or stock_code} 事件检测报告

【事件统计】
- 检测到事件：{summary['total_events']}个
- 正面事件：{summary['positive_events']}个
- 负面事件：{summary['negative_events']}个
- 中性事件：{summary['neutral_events']}个
- 整体影响：{summary['overall_impact']}

【重大事件列表】
"""
            for i, event in enumerate(events[:8], 1):
                impact_emoji = "🟢" if event.impact_score > 0.1 else ("🔴" if event.impact_score < -0.1 else "⚪")
                output += f"{i}. {impact_emoji} 【{event.event_type}】{event.event_title[:40]}...\n"
                output += f"   影响：{event.impact}（{event.impact_score:+.2f}）| 来源：{event.source}\n"
            
            if not events:
                output += "暂未检测到重大事件\n"
            
            return output
            
        except Exception as e:
            logger.error(f"事件检测失败: {e}")
            return f"事件检测失败: {str(e)}"


class ResearchReportTool(BaseTool):
    """
    研报查询工具
    
    获取个股相关研报信息。
    """
    name: str = "research_report_query"
    description: str = """查询个股相关研报。
    返回券商研报列表，包括评级、目标价等信息。
    """
    args_schema: type[BaseModel] = StockSentimentInput
    
    def _run(self, stock_code: str, stock_name: str = "") -> str:
        """查询研报"""
        try:
            crawler = NewsCrawler()
            reports = crawler.get_research_reports(stock_code, limit=10)
            
            if not reports:
                return f"未找到{stock_code}的相关研报"
            
            output = f"📋 {stock_name or stock_code} 研报列表\n\n"
            
            for i, report in enumerate(reports, 1):
                output += f"{i}. {report.title}\n"
                output += f"   {report.content}\n"
                output += f"   发布时间：{report.publish_time}\n\n"
            
            return output
            
        except Exception as e:
            logger.error(f"研报查询失败: {e}")
            return f"研报查询失败: {str(e)}"


# ==================== 便捷函数 ====================

def get_sentiment_tools() -> List[BaseTool]:
    """获取所有情绪分析工具"""
    return [
        StockSentimentTool(),
        MarketSentimentTool(),
        StockNewsTool(),
        EventDetectionTool(),
        ResearchReportTool()
    ]
