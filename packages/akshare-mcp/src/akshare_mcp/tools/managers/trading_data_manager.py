"""交易数据管理器 - 龙虎榜、大单追踪"""

from datetime import datetime
import json
import logging
from ...storage import get_db
from ...utils import ok, fail

logger = logging.getLogger(__name__)


def _normalize_kwargs(kwargs: dict) -> dict:
    extra = kwargs.get("kwargs")
    if extra is not None:
        if isinstance(extra, str):
            try:
                extra = json.loads(extra or "{}")
            except Exception:
                extra = None
        if isinstance(extra, dict):
            kwargs = {**kwargs, **extra}
    if "code" not in kwargs or kwargs.get("code") is None:
        kwargs["code"] = kwargs.get("Code") or kwargs.get("stock_code") or kwargs.get("symbol")
    return kwargs


def register_trading_data_manager(mcp):
    """注册交易数据管理器工具"""
    
    @mcp.tool()
    async def trading_data_manager(action: str, **kwargs):
        """交易数据管理器（统一 action + kwargs 协议）

        Args:
            action (str, required): 操作类型，可选 help/dragon_tiger/block_trades/institutional_flow
            kwargs: JSON 字符串或关键字参数，不同 action 所需参数:
                - help: 无需额外参数
                - dragon_tiger: date(str, optional, "YYYY-MM-DD"), stock_code(str, optional)
                - block_trades: date(str, optional), stock_code(str, optional), limit(int, optional)
                - institutional_flow: code(str, optional)

        Returns:
            dict: {"success": bool, "data": {...}, "error": str|None}

        Examples:
            # 查看帮助
            trading_data_manager(action="help", kwargs="{}")
            # 查询龙虎榜
            trading_data_manager(action="dragon_tiger", kwargs='{"date":"2025-01-15"}')
            # 查询大宗交易
            trading_data_manager(action="block_trades", kwargs='{"stock_code":"600519","limit":10}')
            # 机构资金流向
            trading_data_manager(action="institutional_flow", kwargs="{}")
        """
        try:
            db = get_db()
            kwargs = _normalize_kwargs(kwargs)
            
            if action == 'help':
                return ok({
                    'supported_actions': {
                        'dragon_tiger': '龙虎榜查询（可选 date, stock_code）',
                        'block_trades': '大宗交易查询（可选 date, stock_code）',
                        'institutional_flow': '机构资金流向（可选 date）',
                        'help': '显示帮助信息',
                    }
                })
            
            elif action == 'dragon_tiger':
                date_raw = kwargs.get('date', datetime.now().strftime('%Y-%m-%d'))
                limit = kwargs.get('limit', 50)
                
                if hasattr(date_raw, 'toordinal'):
                    date_val = date_raw
                else:
                    date_val = datetime.strptime(str(date_raw)[:10], '%Y-%m-%d').date()
                
                async with db.acquire() as conn:
                    try:
                        rows = await conn.fetch(
                            """SELECT code, trade_date, reason, buy_amount, sell_amount, 
                                      (COALESCE(buy_amount,0) - COALESCE(sell_amount,0)) AS net_buy, buyer_type 
                               FROM dragon_tiger 
                               WHERE trade_date = $1::date 
                               ORDER BY (COALESCE(buy_amount,0) - COALESCE(sell_amount,0)) DESC NULLS LAST 
                               LIMIT $2""",
                            date_val, limit
                        )
                        data = [dict(row) for row in rows]
                    except Exception:
                        rows = await conn.fetch(
                            """SELECT stock_code AS code, trade_date, reason, 
                                      net_amount AS net_buy, NULL::double precision AS buy_amount, 
                                      NULL::double precision AS sell_amount, NULL AS buyer_type 
                               FROM dragon_tiger_list 
                               WHERE trade_date = $1::date 
                               ORDER BY COALESCE(net_amount, 0) DESC NULLS LAST 
                               LIMIT $2""",
                            date_val, limit
                        )
                        data = [dict(row) for row in rows]
                
                # 如果当日无数据，尝试获取最近的龙虎榜数据
                if not data:
                    logger.info(f"[TradingData] {date_val} 无龙虎榜数据，查询最近数据")
                    async with db.acquire() as conn:
                        try:
                            rows = await conn.fetch(
                                """SELECT code, trade_date, reason, buy_amount, sell_amount, 
                                          (COALESCE(buy_amount,0) - COALESCE(sell_amount,0)) AS net_buy, buyer_type 
                                   FROM dragon_tiger 
                                   WHERE trade_date <= $1::date 
                                   ORDER BY trade_date DESC, (COALESCE(buy_amount,0) - COALESCE(sell_amount,0)) DESC NULLS LAST 
                                   LIMIT $2""",
                                date_val, limit
                            )
                            data = [dict(row) for row in rows]
                            if data:
                                date_val = data[0]['trade_date']
                        except Exception:
                            rows = await conn.fetch(
                                """SELECT stock_code AS code, trade_date, reason, 
                                          net_amount AS net_buy, NULL::double precision AS buy_amount, 
                                          NULL::double precision AS sell_amount, NULL AS buyer_type 
                                   FROM dragon_tiger_list 
                                   WHERE trade_date <= $1::date 
                                   ORDER BY trade_date DESC, COALESCE(net_amount, 0) DESC NULLS LAST 
                                   LIMIT $2""",
                                date_val, limit
                            )
                            data = [dict(row) for row in rows]
                            if data:
                                date_val = data[0]['trade_date']
                
                if data:
                    total_buy = sum(row.get('buy_amount', 0) or 0 for row in data)
                    total_sell = sum(row.get('sell_amount', 0) or 0 for row in data)
                    net_buy = total_buy - total_sell

                    analysis = {
                        'totalBuy': float(total_buy),
                        'totalSell': float(total_sell),
                        'netBuy': float(net_buy),
                        'marketSentiment': 'bullish' if net_buy > 0 else 'bearish',
                        'activeStocks': len(data)
                    }
                else:
                    # DB 全部无数据，Tushare 降级
                    logger.info(f"[TradingData] DB无龙虎榜数据，尝试Tushare")
                    try:
                        from ..fund_flow import get_dragon_tiger
                        date_str = str(date_val).replace('-', '')
                        dt_res = get_dragon_tiger(date=date_str)
                        if dt_res.get('success') and dt_res.get('data'):
                            dt_data = dt_res['data']
                            if isinstance(dt_data, list):
                                for item in dt_data:
                                    buy_amt = float(item.get('buyAmount', 0) or 0)
                                    sell_amt = float(item.get('sellAmount', 0) or 0)
                                    net_amt = float(item.get('netAmount', 0) or 0) or (buy_amt - sell_amt)
                                    data.append({
                                        'code': item.get('code', ''),
                                        'tradeDate': str(date_val),
                                        'reason': item.get('reason', ''),
                                        'buyAmount': buy_amt,
                                        'sellAmount': sell_amt,
                                        'netBuy': net_amt,
                                        'buyerType': None,
                                    })
                    except Exception as e:
                        logger.warning(f"[TradingData] Tushare龙虎榜也失败: {e}")

                    if data:
                        total_buy = sum(row.get('buyAmount') or row.get('buy_amount') or 0 for row in data)
                        total_sell = sum(row.get('sellAmount') or row.get('sell_amount') or 0 for row in data)
                        net_buy = total_buy - total_sell
                        analysis = {
                            'totalBuy': float(total_buy),
                            'totalSell': float(total_sell),
                            'netBuy': float(net_buy),
                            'marketSentiment': 'bullish' if net_buy > 0 else 'bearish',
                            'activeStocks': len(data)
                        }
                    else:
                        analysis = {
                            'totalBuy': 0,
                            'totalSell': 0,
                            'netBuy': 0,
                            'marketSentiment': 'neutral',
                            'activeStocks': 0
                        }
                
                return ok({
                    'date': str(date_val),
                    'data': data,
                    'analysis': analysis,
                    'message': '返回最近龙虎榜数据' if not data or str(date_val) != str(kwargs.get('date', datetime.now().strftime('%Y-%m-%d'))[:10]) else None
                })
            
            elif action == 'block_trades':
                code = kwargs.get('code')
                days = kwargs.get('days', 5)
                
                if not code:
                    return fail('需要提供股票代码')
                
                async with db.acquire() as conn:
                    rows = await conn.fetch(
                        """SELECT * FROM block_trades 
                           WHERE code = $1 AND trade_date >= CURRENT_DATE - ($2::integer * INTERVAL '1 day')
                           ORDER BY trade_date DESC, trade_amount DESC""",
                        code, int(days)
                    )
                    trades = [dict(row) for row in rows]
                
                if trades:
                    total_amount = sum(t.get('trade_amount', 0) for t in trades)
                    avg_price = sum(t.get('trade_price', 0) for t in trades) / len(trades)

                    klines = await db.get_klines(code, limit=1)
                    current_price = klines[0]['close'] if klines else 0

                    premium = (avg_price - current_price) / current_price if current_price > 0 else 0

                    analysis = {
                        'totalTrades': len(trades),
                        'totalAmount': float(total_amount),
                        'avgPrice': float(avg_price),
                        'currentPrice': float(current_price),
                        'premium': f"{premium*100:.2f}%",
                        'signal': 'positive' if premium > 0 else ('negative' if premium < -0.05 else 'neutral')
                    }
                else:
                    analysis = {
                        'totalTrades': 0,
                        'totalAmount': 0,
                        'signal': 'no_data'
                    }
                
                return ok({
                    'code': code,
                    'days': days,
                    'trades': trades,
                    'analysis': analysis
                })
            
            elif action == 'institutional_flow':
                code = kwargs.get('code')
                period = kwargs.get('period', 20)
                
                if not code:
                    return fail('需要提供股票代码')
                
                async with db.acquire() as conn:
                    try:
                        rows = await conn.fetch(
                            """SELECT code, trade_date, reason, buy_amount, sell_amount, 
                                      (COALESCE(buy_amount,0) - COALESCE(sell_amount,0)) AS net_buy, buyer_type 
                               FROM dragon_tiger 
                               WHERE code = $1 
                               AND trade_date >= CURRENT_DATE - ($2::integer * INTERVAL '1 day')
                               AND (buyer_type = 'institution' OR buyer_type IS NULL)
                               ORDER BY trade_date DESC""",
                            code, period
                        )
                    except Exception:
                        rows = await conn.fetch(
                            """SELECT stock_code AS code, trade_date, reason, 
                                      NULL::double precision AS buy_amount, NULL::double precision AS sell_amount,
                                      net_amount AS net_buy, NULL AS buyer_type 
                               FROM dragon_tiger_list 
                               WHERE stock_code = $1 
                               AND trade_date >= CURRENT_DATE - ($2::integer * INTERVAL '1 day')
                               ORDER BY trade_date DESC""",
                            code, period
                        )
                    institutional_trades = [dict(row) for row in rows]
                
                if institutional_trades:
                    total_buy = sum(t.get('buy_amount', 0) for t in institutional_trades)
                    total_sell = sum(t.get('sell_amount', 0) for t in institutional_trades)
                    net_flow = total_buy - total_sell

                    flow_analysis = {
                        'totalBuy': float(total_buy),
                        'totalSell': float(total_sell),
                        'netFlow': float(net_flow),
                        'flowDirection': 'inflow' if net_flow > 0 else 'outflow',
                        'strength': 'strong' if abs(net_flow) > total_buy * 0.3 else 'weak',
                        'tradeCount': len(institutional_trades)
                    }
                else:
                    flow_analysis = {
                        'totalBuy': 0,
                        'totalSell': 0,
                        'netFlow': 0,
                        'flowDirection': 'neutral',
                        'strength': 'none',
                        'tradeCount': 0
                    }

                return ok({
                    'code': code,
                    'period': period,
                    'institutionalFlow': flow_analysis,
                    'trades': institutional_trades[:10]
                })
            
            else:
                return fail(f'Unknown action: {action}. Supported: help, dragon_tiger, block_trades, institutional_flow')
        except Exception as e:
            return fail(str(e))
