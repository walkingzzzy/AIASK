"""
集合竞价分析工具
供CrewAI Agent调用
"""
from crewai.tools import BaseTool
from pydantic import BaseModel, Field
from typing import Type, Any
from ..call_auction.auction_analyzer import CallAuctionAnalyzer


class CallAuctionInput(BaseModel):
    """竞价分析输入"""
    stock_code: str = Field(default="", description="股票代码，为空则返回市场概况")
    analysis_type: str = Field(
        default="overview",
        description="分析类型: overview(市场概况)/ranking(排行榜)/detail(个股详情)"
    )


class CallAuctionTool(BaseTool):
    name: str = "集合竞价分析工具"
    description: str = """
    分析集合竞价数据，识别异动股票。

    功能：
    1. 获取竞价市场概况
    2. 获取竞价排行榜（涨幅榜、成交量榜、量比榜）
    3. 分析个股竞价情况

    使用场景：
    - 盘前分析，寻找当日热点
    - 识别竞价异动股票
    - 预测开盘走势
    """
    args_schema: Type[BaseModel] = CallAuctionInput

    def _run(self, stock_code: str = "", analysis_type: str = "overview") -> str:
        analyzer = CallAuctionAnalyzer()

        try:
            if analysis_type == "overview":
                # 市场概况
                ranking = analyzer.get_auction_ranking(top_n=10)
                result = f"竞价市场概况:\n"
                result += f"异动股票数量: {len(ranking['abnormal_stocks'])}\n\n"
                result += "竞价涨幅前10:\n"
                for i, stock in enumerate(ranking['change_ranking'][:10], 1):
                    result += f"{i}. {stock.stock_name}({stock.stock_code}) "
                    result += f"涨幅{stock.auction_change:.2f}% "
                    result += f"量比{stock.volume_ratio:.2f}\n"
                return result

            elif analysis_type == "ranking":
                # 排行榜
                ranking = analyzer.get_auction_ranking(top_n=20)
                result = "竞价排行榜:\n\n"

                result += "【涨幅榜】\n"
                for i, stock in enumerate(ranking['change_ranking'][:10], 1):
                    result += f"{i}. {stock.stock_name} {stock.auction_change:.2f}%\n"

                result += "\n【异动榜】\n"
                for i, stock in enumerate(ranking['abnormal_stocks'][:10], 1):
                    reasons = ", ".join(stock.abnormal_reason)
                    result += f"{i}. {stock.stock_name} - {reasons}\n"

                return result

            elif analysis_type == "detail" and stock_code:
                # 个股详情
                analysis = analyzer.analyze_auction_stock(stock_code)
                if 'error' in analysis:
                    return analysis['error']

                result = f"【{analysis['stock_info']['name']}】竞价分析\n\n"
                result += f"竞价价格: {analysis['stock_info']['auction_price']:.2f}\n"
                result += f"竞价涨幅: {analysis['stock_info']['auction_change']:.2f}%\n"
                result += f"量比: {analysis['auction_metrics']['volume_ratio']:.2f}\n"
                result += f"净流入: {analysis['auction_metrics']['net_inflow']/10000:.0f}万\n\n"

                if analysis['is_abnormal']:
                    result += f"⚠️ 异动原因: {', '.join(analysis['abnormal_reasons'])}\n\n"

                result += f"开盘预测: {analysis['open_prediction']}\n"
                result += f"操作建议: {analysis['operation_advice']}\n"

                return result

            else:
                return "参数错误，请指定正确的分析类型"

        except Exception as e:
            return f"分析失败: {str(e)}"
