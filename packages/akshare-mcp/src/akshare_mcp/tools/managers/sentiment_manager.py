"""情绪分析管理器（增强版）"""

from ...utils import ok, fail, normalize_code
from ...storage import get_db
from ...data_source import data_source
import logging
import json

logger = logging.getLogger(__name__)

def _normalize_kwargs(kwargs: dict) -> dict:
    raw = kwargs.get("kwargs")
    if isinstance(raw, dict):
        kwargs = {**kwargs, **raw}
    elif isinstance(raw, str):
        try:
            extra = json.loads(raw or "{}")
            if isinstance(extra, dict):
                kwargs = {**kwargs, **extra}
        except Exception:
            pass
    if "code" not in kwargs:
        kwargs["code"] = kwargs.get("Code") or kwargs.get("stock_code") or kwargs.get("symbol")
    if "sector" not in kwargs:
        kwargs["sector"] = kwargs.get("Sector") or kwargs.get("industry") or kwargs.get("industry_name")
    return kwargs


def register_sentiment_manager(mcp):
    """注册情绪分析管理器工具"""
    
    @mcp.tool()
    async def sentiment_manager(action: str, **kwargs):
        """情绪分析管理器（统一 action + kwargs 协议）

        Args:
            action (str, required): 操作类型，可选 help/market_sentiment/stock_sentiment/sector_sentiment
            kwargs: JSON 字符串或关键字参数，不同 action 所需参数:
                - help: 无需额外参数
                - market_sentiment: 无需额外参数（返回市场整体情绪指标）
                - stock_sentiment: code(str, 股票代码)
                - sector_sentiment: sector(str, 板块名称, optional)

        Returns:
            dict: {"success": bool, "data": {...}, "error": str|None}

        Examples:
            # 查看帮助
            sentiment_manager(action="help", kwargs="{}")
            # 市场整体情绪
            sentiment_manager(action="market_sentiment", kwargs="{}")
            # 个股情绪分析
            sentiment_manager(action="stock_sentiment", kwargs='{"code":"600519"}')
            # 板块情绪分析
            sentiment_manager(action="sector_sentiment", kwargs='{"sector":"白酒"}')
        """
        try:
            db = get_db()
            kwargs = _normalize_kwargs(kwargs)
            
            if action == 'help':
                return ok({
                    'supported_actions': {
                        'market_sentiment': '市场整体情绪分析',
                        'stock_sentiment': '个股情绪分析（需要 code）',
                        'sector_sentiment': '板块情绪分析（需要 sector）',
                        'help': '显示帮助信息',
                    }
                })
            
            elif action == 'market_sentiment':
                # 计算市场整体情绪
                # 数据源优先级: DB → TDX → Tushare → AkShare
                async with db.acquire() as conn:
                    # 取每只股票最新一条行情
                    up_count = await conn.fetchval(
                        """
                        WITH latest AS (
                            SELECT DISTINCT ON (code) code, change_pct
                            FROM stock_quotes
                            ORDER BY code, time DESC
                        )
                        SELECT COUNT(*) FROM latest WHERE change_pct > 0
                        """
                    ) or 0
                    down_count = await conn.fetchval(
                        """
                        WITH latest AS (
                            SELECT DISTINCT ON (code) code, change_pct
                            FROM stock_quotes
                            ORDER BY code, time DESC
                        )
                        SELECT COUNT(*) FROM latest WHERE change_pct < 0
                        """
                    ) or 0
                    total_count = int(up_count) + int(down_count)
                
                data_source_info = '数据库'
                
                # 方案2: 如果数据库为空，从数据源获取（优先级: AkShare批量 → 逐只K线）
                if total_count == 0:
                    logger.info("[Sentiment] 数据库无数据，从数据源获取市场情绪")
                    
                    # 优先尝试 Tushare daily 获取全市场涨跌
                    try:
                        ts_pro = data_source.get_tushare_pro()
                        if ts_pro:
                            import datetime as _dt_sent
                            base = _dt_sent.datetime.now()
                            for days_back in range(7):
                                check_date = (base - _dt_sent.timedelta(days=days_back)).strftime('%Y%m%d')
                                try:
                                    df = ts_pro.daily(trade_date=check_date, fields='ts_code,pct_chg')
                                    if df is not None and not df.empty and len(df) > 100:
                                        up_count = int((df['pct_chg'] > 0).sum())
                                        down_count = int((df['pct_chg'] < 0).sum())
                                        total_count = up_count + down_count
                                        data_source_info = f'Tushare daily ({check_date})'
                                        logger.info(f"[Sentiment] Tushare: 涨{up_count} 跌{down_count}")
                                        break
                                except Exception:
                                    continue
                    except Exception as e:
                        logger.warning(f"[Sentiment] Tushare批量行情失败: {e}")
                    
                    # 降级: AkShare 批量行情
                    if total_count == 0:
                        try:
                            import akshare as ak
                            df = ak.stock_zh_a_spot_em()
                            if df is not None and not df.empty:
                                chg_col = '涨跌幅'
                                if chg_col in df.columns:
                                    up_count = int(len(df[df[chg_col] > 0]))
                                    down_count = int(len(df[df[chg_col] < 0]))
                                    total_count = up_count + down_count
                                    data_source_info = 'AkShare实时行情'
                                    logger.info(f"[Sentiment] AkShare批量行情: 涨{up_count} 跌{down_count}")
                        except Exception as e:
                            logger.warning(f"[Sentiment] AkShare批量行情失败: {e}")
                
                # 方案3: AkShare批量也失败，逐只K线兜底
                if total_count == 0:
                    sample_stocks = ['600519', '000001', '600036', '601318', '000858', 
                                   '601166', '600887', '601288', '600030', '601398']
                    
                    up_count = 0
                    down_count = 0
                    
                    for code in sample_stocks:
                        try:
                            quote_data = data_source.get_kline(code, 'daily', 1)
                            if quote_data and len(quote_data) > 0:
                                latest = quote_data[-1]
                                change_pct = latest.get('change_pct', 0)
                                if change_pct > 0:
                                    up_count += 1
                                elif change_pct < 0:
                                    down_count += 1
                        except Exception as e:
                            logger.warning(f"[Sentiment] 获取 {code} 行情失败: {e}")
                            continue
                    
                    total_count = up_count + down_count
                    data_source_info = '实时数据源(样本)'
                
                # 计算情绪指标
                if total_count > 0:
                    up_ratio = up_count / total_count
                    sentiment_score = up_ratio * 100
                    
                    if sentiment_score >= 70:
                        sentiment = 'bullish'
                        description = '市场情绪乐观'
                    elif sentiment_score >= 55:
                        sentiment = 'slightly_bullish'
                        description = '市场情绪偏乐观'
                    elif sentiment_score >= 45:
                        sentiment = 'neutral'
                        description = '市场情绪中性'
                    elif sentiment_score >= 30:
                        sentiment = 'slightly_bearish'
                        description = '市场情绪偏悲观'
                    else:
                        sentiment = 'bearish'
                        description = '市场情绪悲观'
                else:
                    # 方案3: 完全无数据时，返回中性
                    sentiment_score = 50
                    sentiment = 'neutral'
                    description = '数据不足，返回中性情绪'
                    data_source_info = '默认值'
                    up_count = 0
                    down_count = 0
                    up_ratio = 0.5
                
                return ok({
                    'sentiment': sentiment,
                    'score': float(sentiment_score),
                    'description': description,
                    'indicators': {
                        'up_count': up_count,
                        'down_count': down_count,
                        'up_ratio': f"{up_ratio*100:.2f}%" if total_count > 0 else "50.00%",
                        'sample_size': total_count,
                        'data_source': data_source_info
                    }
                })
            
            elif action == 'stock_sentiment':
                code = kwargs.get('code')
                if not code:
                    return fail('需要提供股票代码')
                
                code = normalize_code(code)
                
                # 获取K线数据分析情绪
                klines = await db.get_klines(code, limit=20)
                if not klines:
                    klines = data_source.get_kline(code, 'daily', 20)
                
                if not klines or len(klines) < 5:
                    return ok({
                        'code': code,
                        'sentiment': 'neutral',
                        'score': 50,
                        'description': '数据不足'
                    })
                
                # 计算涨跌天数
                up_days = sum(1 for k in klines if k.get('close', 0) > k.get('open', 0))
                down_days = len(klines) - up_days
                
                # 计算成交量变化
                volumes = [k.get('volume', 0) for k in klines]
                avg_volume = sum(volumes) / len(volumes) if volumes else 0
                recent_volume = sum(volumes[-5:]) / 5 if len(volumes) >= 5 else 0
                volume_ratio = recent_volume / avg_volume if avg_volume > 0 else 1
                
                # 情绪评分
                sentiment_score = (up_days / len(klines)) * 60 + (min(volume_ratio, 2) / 2) * 40
                
                if sentiment_score >= 70:
                    sentiment = 'bullish'
                    description = '个股情绪乐观'
                elif sentiment_score >= 55:
                    sentiment = 'slightly_bullish'
                    description = '个股情绪偏乐观'
                elif sentiment_score >= 45:
                    sentiment = 'neutral'
                    description = '个股情绪中性'
                elif sentiment_score >= 30:
                    sentiment = 'slightly_bearish'
                    description = '个股情绪偏悲观'
                else:
                    sentiment = 'bearish'
                    description = '个股情绪悲观'
                
                return ok({
                    'code': code,
                    'sentiment': sentiment,
                    'score': float(sentiment_score),
                    'description': description,
                    'indicators': {
                        'up_days': up_days,
                        'down_days': down_days,
                        'volume_ratio': float(volume_ratio),
                        'volume_status': 'active' if volume_ratio > 1.2 else ('weak' if volume_ratio < 0.8 else 'normal')
                    }
                })
            
            elif action == 'sector_sentiment':
                sector = kwargs.get('sector')
                if not sector:
                    return fail('需要提供板块名称')
                
                # 获取板块内股票的情绪
                async with db.acquire() as conn:
                    stocks = await conn.fetch(
                        "SELECT code FROM stocks WHERE industry = $1 LIMIT 20",
                        sector
                    )
                
                if not stocks:
                    return fail(f'未找到板块 {sector} 的股票')
                
                sentiment_scores = []
                for stock in stocks:
                    result = await sentiment_manager('stock_sentiment', code=stock['code'])
                    if result.get('success'):
                        sentiment_scores.append(result['data']['score'])
                
                if sentiment_scores:
                    avg_score = sum(sentiment_scores) / len(sentiment_scores)
                    
                    if avg_score >= 70:
                        sentiment = 'bullish'
                    elif avg_score >= 55:
                        sentiment = 'slightly_bullish'
                    elif avg_score >= 45:
                        sentiment = 'neutral'
                    elif avg_score >= 30:
                        sentiment = 'slightly_bearish'
                    else:
                        sentiment = 'bearish'
                else:
                    avg_score = 50
                    sentiment = 'neutral'
                
                return ok({
                    'sector': sector,
                    'sentiment': sentiment,
                    'score': float(avg_score),
                    'stock_count': len(stocks)
                })
            
            else:
                return fail(f'Unknown action: {action}. Supported: help, market_sentiment, stock_sentiment, sector_sentiment')
        except Exception as e:
            logger.error(f"[SentimentManager] Error: {e}")
            return fail(str(e))
