"""
股票数据路由
包含行情、K线、指标、盘口、成交明细等接口
"""
from fastapi import APIRouter, HTTPException, Query
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/stock", tags=["股票数据"])


def _get_stock_service():
    """获取股票数据服务"""
    try:
        from packages.core.services.stock_data_service import StockDataService
        return StockDataService()
    except ImportError:
        return None


@router.get("/quote/{stock_code}")
async def get_stock_quote(stock_code: str):
    """获取股票实时行情"""
    try:
        service = _get_stock_service()
        if service:
            quote = service.get_realtime_quote(stock_code)
            if quote:
                return {"success": True, "data": quote}
        return {"success": False, "error": "无法获取行情数据"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/quotes/batch")
async def get_batch_stock_quotes(stock_codes: list[str]):
    """批量获取股票实时行情
    
    用于减少前端请求次数，支持一次查询多只股票
    最多支持50只股票
    """
    if not stock_codes:
        return {"success": False, "error": "股票代码列表不能为空"}
    
    # 限制最大查询数量
    if len(stock_codes) > 50:
        stock_codes = stock_codes[:50]
    
    try:
        service = _get_stock_service()
        quotes = {}
        errors = []
        
        if service:
            for code in stock_codes:
                try:
                    quote = service.get_realtime_quote(code)
                    if quote:
                        quotes[code] = quote
                    else:
                        errors.append({"code": code, "error": "无法获取行情数据"})
                except Exception as e:
                    errors.append({"code": code, "error": str(e)})
        else:
            # 尝试使用腾讯数据源
            try:
                from packages.core.realtime.data_source.tencent_realtime import TencentRealtimeAdapter
                tencent = TencentRealtimeAdapter()
                for code in stock_codes:
                    try:
                        quote = tencent.get_realtime_quote(code)
                        if quote:
                            quotes[code] = quote
                        else:
                            errors.append({"code": code, "error": "无法获取行情数据"})
                    except Exception as e:
                        errors.append({"code": code, "error": str(e)})
            except Exception as e:
                return {"success": False, "error": f"数据服务不可用: {str(e)}"}
        
        return {
            "success": True,
            "data": quotes,
            "errors": errors if errors else None,
            "count": len(quotes),
            "requested": len(stock_codes)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/kline/{stock_code}")
async def get_stock_kline(
    stock_code: str,
    period: str = Query(default="daily", description="周期: daily/weekly/monthly"),
    limit: int = Query(default=100, description="数据条数")
):
    """获取K线数据"""
    try:
        service = _get_stock_service()
        if service:
            df = service.get_daily_bars(stock_code, days=limit)
            if df is not None and not df.empty:
                kline_data = []
                for _, row in df.iterrows():
                    kline_data.append({
                        "date": str(row.get('date', row.get('trade_date', ''))),
                        "open": float(row['open']),
                        "high": float(row['high']),
                        "low": float(row['low']),
                        "close": float(row['close']),
                        "volume": float(row.get('volume', 0)),
                        "amount": float(row.get('amount', 0)) if 'amount' in row else 0
                    })
                return {"success": True, "data": kline_data}
        return {"success": False, "error": "无法获取K线数据"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/indicator/{stock_code}")
async def get_stock_indicator(
    stock_code: str,
    indicator: str = Query(..., description="指标类型: MA/EMA/MACD/RSI/KDJ/BOLL"),
    period: str = Query(default="daily", description="周期: daily/weekly/monthly")
):
    """获取技术指标数据"""
    try:
        service = _get_stock_service()
        if service:
            df = service.get_daily_bars(stock_code, days=500)
            if df is not None and not df.empty:
                kline = df.to_dict('records')
                try:
                    from packages.core.indicators import calculate_indicator
                    indicator_data = calculate_indicator(kline, indicator)
                    return {"success": True, "data": indicator_data}
                except ImportError:
                    import pandas as pd
                    df = pd.DataFrame(kline)

                    if indicator.upper() == "MA":
                        df['MA5'] = df['close'].rolling(window=5).mean()
                        df['MA10'] = df['close'].rolling(window=10).mean()
                        df['MA20'] = df['close'].rolling(window=20).mean()
                        df['MA60'] = df['close'].rolling(window=60).mean()
                        result = df[['date', 'MA5', 'MA10', 'MA20', 'MA60']].to_dict('records')
                    elif indicator.upper() == "MACD":
                        exp1 = df['close'].ewm(span=12, adjust=False).mean()
                        exp2 = df['close'].ewm(span=26, adjust=False).mean()
                        df['DIF'] = exp1 - exp2
                        df['DEA'] = df['DIF'].ewm(span=9, adjust=False).mean()
                        df['MACD'] = (df['DIF'] - df['DEA']) * 2
                        result = df[['date', 'DIF', 'DEA', 'MACD']].to_dict('records')
                    elif indicator.upper() == "RSI":
                        delta = df['close'].diff()
                        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
                        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
                        rs = gain / loss
                        df['RSI'] = 100 - (100 / (1 + rs))
                        result = df[['date', 'RSI']].to_dict('records')
                    else:
                        result = []
                    return {"success": True, "data": result}
        return {"success": False, "error": "无法计算技术指标"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/orderbook/{stock_code}")
async def get_stock_orderbook(stock_code: str):
    """获取股票五档盘口数据（真实数据来自腾讯/新浪行情）"""
    try:
        import time
        orderbook_data = None
        data_source = "unknown"
        
        # 优先使用腾讯数据源
        try:
            from packages.core.realtime.data_source.tencent_realtime import TencentRealtimeAdapter
            tencent = TencentRealtimeAdapter()
            quote = tencent.get_realtime_quote(stock_code)
            if quote and quote.get('bid1_price'):
                asks, bids = [], []
                for i in range(1, 6):
                    ask_price = quote.get(f'ask{i}_price', 0)
                    ask_volume = quote.get(f'ask{i}_volume', 0)
                    bid_price = quote.get(f'bid{i}_price', 0)
                    bid_volume = quote.get(f'bid{i}_volume', 0)
                    if ask_price > 0:
                        asks.append({"price": ask_price, "volume": ask_volume})
                    if bid_price > 0:
                        bids.append({"price": bid_price, "volume": bid_volume})
                
                orderbook_data = {
                    "stock_code": stock_code,
                    "stock_name": quote.get('name', ''),
                    "current_price": quote.get('current', 0),
                    "asks": asks, "bids": bids,
                    "pre_close": quote.get('pre_close', 0),
                    "change_pct": quote.get('change_pct', 0),
                    "timestamp": int(time.time() * 1000)
                }
                data_source = "tencent"
        except Exception as e:
            logger.warning(f"腾讯数据源获取失败: {e}")
        
        # 备用新浪数据源
        if not orderbook_data:
            try:
                from packages.core.realtime.data_source.sina_realtime import SinaRealtimeAdapter
                sina = SinaRealtimeAdapter()
                quote = sina.get_realtime_quote(stock_code)
                if quote and quote.get('bid1_price'):
                    asks, bids = [], []
                    for i in range(1, 6):
                        ask_price = quote.get(f'ask{i}_price', 0)
                        ask_volume = quote.get(f'ask{i}_volume', 0)
                        bid_price = quote.get(f'bid{i}_price', 0)
                        bid_volume = quote.get(f'bid{i}_volume', 0)
                        if ask_price > 0:
                            asks.append({"price": ask_price, "volume": ask_volume})
                        if bid_price > 0:
                            bids.append({"price": bid_price, "volume": bid_volume})
                    
                    orderbook_data = {
                        "stock_code": stock_code,
                        "stock_name": quote.get('name', ''),
                        "current_price": quote.get('current', 0),
                        "asks": asks, "bids": bids,
                        "pre_close": quote.get('pre_close', 0),
                        "change_pct": quote.get('change_pct', 0),
                        "timestamp": int(time.time() * 1000)
                    }
                    data_source = "sina"
            except Exception as e:
                logger.warning(f"新浪数据源获取失败: {e}")
        
        if orderbook_data:
            return {"success": True, "data": orderbook_data, "data_source": data_source}
        return {"success": False, "error": "无法获取五档盘口数据"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/trades/{stock_code}")
async def get_stock_trades(
    stock_code: str,
    limit: int = Query(default=50, description="返回条数")
):
    """获取股票成交明细（基于分钟级数据）"""
    try:
        import time
        trades_data = None
        data_source = "unknown"
        
        # 尝试AKShare分钟数据
        try:
            import akshare as ak
            code = stock_code.split('.')[0]
            symbol = f"sh{code}" if stock_code.endswith('.SH') or code.startswith('6') else f"sz{code}"
            df = ak.stock_zh_a_minute(symbol=symbol, period='1')
            
            if df is not None and not df.empty:
                df = df.tail(min(limit, len(df)))
                trades = []
                prev_close = None
                for _, row in df.iterrows():
                    price = float(row['close'])
                    volume = int(row['volume'])
                    if prev_close is None:
                        direction = 'neutral'
                    elif price > prev_close:
                        direction = 'buy'
                    elif price < prev_close:
                        direction = 'sell'
                    else:
                        direction = 'neutral'
                    prev_close = price
                    
                    time_str = str(row['day'])
                    time_part = time_str.split(' ')[1][:8] if ' ' in time_str else time_str
                    trades.append({
                        "price": price, "volume": volume,
                        "amount": round(price * volume, 2),
                        "direction": direction, "time": time_part
                    })
                trades.reverse()
                
                stock_name = ""
                try:
                    from packages.core.realtime.data_source.tencent_realtime import TencentRealtimeAdapter
                    quote = TencentRealtimeAdapter().get_realtime_quote(stock_code)
                    if quote:
                        stock_name = quote.get('name', '')
                except:
                    pass
                
                trades_data = {
                    "stock_code": stock_code, "stock_name": stock_name,
                    "trades": trades, "timestamp": int(time.time() * 1000)
                }
                data_source = "akshare_minute"
        except Exception as e:
            logger.warning(f"AKShare分钟数据获取失败: {e}")
        
        # 备用腾讯实时数据
        if not trades_data:
            try:
                from packages.core.realtime.data_source.tencent_realtime import TencentRealtimeAdapter
                quote = TencentRealtimeAdapter().get_realtime_quote(stock_code)
                if quote:
                    trades = [{
                        "price": quote.get('current', 0),
                        "volume": quote.get('volume', 0) * 100,
                        "amount": quote.get('amount', 0) * 10000,
                        "direction": 'buy' if quote.get('change', 0) > 0 else ('sell' if quote.get('change', 0) < 0 else 'neutral'),
                        "time": datetime.now().strftime("%H:%M:%S")
                    }]
                    trades_data = {
                        "stock_code": stock_code, "stock_name": quote.get('name', ''),
                        "trades": trades, "timestamp": int(time.time() * 1000)
                    }
                    data_source = "tencent_realtime"
            except Exception as e:
                logger.warning(f"腾讯实时数据获取失败: {e}")
        
        if trades_data:
            return {"success": True, "data": trades_data, "data_source": data_source}
        return {"success": False, "error": "无法获取成交明细数据"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
