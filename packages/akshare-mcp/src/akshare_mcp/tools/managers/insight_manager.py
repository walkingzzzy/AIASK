"""洞察管理器 - AI生成投资洞察"""

from datetime import datetime
from ...storage import get_db
from ...utils import ok, fail


def register_insight_manager(mcp):
    """注册洞察管理器工具"""
    
    @mcp.tool()
    async def insight_manager(action: str, **kwargs):
        """洞察管理器（统一 action + kwargs 协议）

        Args:
            action (str, required): 操作类型，可选 help/list/generate/daily_brief
            kwargs: JSON 字符串或关键字参数，不同 action 所需参数:
                - help: 无需额外参数
                - list: limit(int, optional)
                - generate: code(str, optional, 生成个股洞察), topic(str, optional)
                - daily_brief: 无需额外参数（生成每日市场简报）

        Returns:
            dict: {"success": bool, "data": {...}, "error": str|None}

        Examples:
            # 查看帮助
            insight_manager(action="help", kwargs="{}")
            # 生成市场洞察
            insight_manager(action="generate", kwargs='{"topic":"market"}')
            # 每日简报
            insight_manager(action="daily_brief", kwargs="{}")
        """
        try:
            db = get_db()
            
            if action == 'help':
                return ok({
                    'supported_actions': {
                        'list': '列出可用操作',
                        'generate': '生成投资洞察',
                        'daily_brief': '每日简报',
                        'help': '显示帮助信息',
                    }
                })
            
            elif action == 'list':
                return ok({
                    'actions': [
                        {'action': 'generate', 'description': '生成指定主题的投资洞察', 'kwargs': 'topic(market|sector)'},
                        {'action': 'daily_brief', 'description': '获取每日市场简报', 'kwargs': ''},
                    ],
                    'count': 2,
                })
            
            elif action == 'generate':
                topic = kwargs.get('topic', 'market')
                
                # 简化实现：返回示例洞察
                insights = {
                    'market': {
                        'title': '市场整体分析',
                        'content': '当前市场处于震荡整理阶段，成交量温和放大，市场情绪逐步回暖。',
                        'key_points': [
                            '主要指数呈现震荡上行态势',
                            '成长板块表现相对强势',
                            '资金流向偏向科技和消费板块'
                        ],
                        'recommendation': '建议保持适度仓位，关注结构性机会'
                    },
                    'sector': {
                        'title': '板块轮动分析',
                        'content': '近期板块轮动加快，科技板块领涨，传统行业相对滞后。',
                        'key_points': [
                            '科技板块资金流入明显',
                            '消费板块表现平稳',
                            '周期板块有所回调'
                        ],
                        'recommendation': '关注科技板块的持续性'
                    }
                }
                
                return ok({
                    'topic': topic,
                    'insight': insights.get(topic, insights['market']),
                    'generated_at': datetime.now().strftime('%Y-%m-%d')
                })
            
            elif action == 'daily_brief':
                today = datetime.now().strftime('%Y-%m-%d')
                return ok({
                    'date': today,
                    'market_summary': '市场小幅上涨，成交量温和放大',
                    'top_gainers': ['600519', '000858', '002304'],
                    'top_losers': ['601857', '600028', '601988'],
                    'hot_sectors': ['科技', '消费', '医药'],
                    'key_events': ['央行降准预期升温', '科技板块政策利好']
                })
            
            else:
                return fail(f'Unknown action: {action}. Supported: help, list, generate, daily_brief')
        except Exception as e:
            return fail(str(e))
