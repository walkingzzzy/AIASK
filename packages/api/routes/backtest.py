"""
回测系统API路由
提供策略回测、阈值优化、滚动验证等功能
"""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import List, Optional
import logging

from packages.core.data_layer.storage.user_data_db import UserDataDB

router = APIRouter(prefix="/backtest", tags=["回测系统"])
logger = logging.getLogger(__name__)

# 初始化数据库
db = UserDataDB("./data/user_data.db")


# ==================== 请求模型 ====================

class BacktestRequest(BaseModel):
    """回测请求"""
    strategy: str = "ai_score"
    stock_codes: Optional[List[str]] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    initial_capital: float = 1000000
    holding_days: int = 20
    buy_threshold: float = 7.0
    sell_threshold: float = 5.0


class OptimizeRequest(BaseModel):
    """阈值优化请求"""
    strategy: str = "ai_score"
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    holding_days: int = 20


# ==================== 回测API ====================

@router.post("/run")
async def run_backtest(request: BacktestRequest):
    """
    运行策略回测
    
    返回回测结果，包括收益曲线、交易记录、绩效指标等
    """
    try:
        # 尝试导入并使用真实回测服务
        from packages.core.services.backtest_service import BacktestService
        from packages.core.services.stock_data_service import StockDataService
        
        backtest_service = BacktestService()
        stock_service = StockDataService()
        
        # 获取价格数据
        stock_codes = request.stock_codes or []
        if not stock_codes:
            raise HTTPException(status_code=400, detail="请提供股票代码列表")
        
        # 获取评分和价格数据
        score_data = stock_service.get_score_data(
            stock_codes, 
            request.start_date, 
            request.end_date
        )
        price_data = stock_service.get_price_data(
            stock_codes,
            request.start_date,
            request.end_date
        )
        
        if score_data is None or price_data is None or score_data.empty or price_data.empty:
            raise HTTPException(status_code=400, detail="无法获取回测所需数据")
        
        # 运行分层回测
        results = backtest_service.run_stratified_backtest(
            score_data, price_data, request.holding_days
        )
        
        if not results:
            raise HTTPException(status_code=500, detail="回测执行失败")
        
        # 计算汇总指标
        total_return = sum(r.get('avg_return', 0) for r in results) / len(results)
        win_rate = sum(r.get('win_rate', 0) for r in results) / len(results)
        sharpe = sum(r.get('sharpe_ratio', 0) for r in results) / len(results)
        max_dd = max(r.get('max_drawdown', 0) for r in results)
        
        # 保存回测结果到数据库
        result_data = {
            'stock_codes': ','.join(stock_codes),
            'start_date': request.start_date,
            'end_date': request.end_date,
            'initial_capital': request.initial_capital,
            'final_capital': request.initial_capital * (1 + total_return / 100),
            'total_return': total_return,
            'annual_return': total_return * 252 / request.holding_days if request.holding_days > 0 else 0,
            'sharpe_ratio': sharpe,
            'max_drawdown': max_dd,
            'win_rate': win_rate,
            'total_trades': sum(r.get('total_stocks', 0) for r in results),
            'config': {
                'holding_days': request.holding_days,
                'buy_threshold': request.buy_threshold,
                'sell_threshold': request.sell_threshold
            }
        }
        
        backtest_id = db.save_backtest_result(request.strategy, result_data)
        
        return {
            "success": True,
            "data": {
                "id": backtest_id,
                "strategy_name": _get_strategy_name(request.strategy),
                "start_date": request.start_date,
                "end_date": request.end_date,
                "initial_capital": request.initial_capital,
                "final_capital": result_data['final_capital'],
                "metrics": {
                    "total_return": round(total_return, 2),
                    "annual_return": round(result_data['annual_return'], 2),
                    "sharpe_ratio": round(sharpe, 2),
                    "max_drawdown": round(max_dd, 2),
                    "win_rate": round(win_rate, 2),
                    "total_trades": result_data['total_trades']
                },
                "stratified_results": results
            }
        }
    except HTTPException:
        raise
    except ImportError as e:
        logger.error(f"回测服务不可用: {e}")
        raise HTTPException(status_code=503, detail="回测服务不可用")
    except Exception as e:
        logger.error(f"回测执行错误: {e}")
        raise HTTPException(status_code=500, detail=f"回测执行失败: {str(e)}")


@router.post("/stratified")
async def run_stratified_backtest(
    holding_days: int = Query(20, description="持有天数")
):
    """
    分层回测 - 需要真实数据支持
    """
    raise HTTPException(status_code=503, detail="分层回测需要通过 /run 端点执行，请提供股票代码和日期范围")


@router.post("/optimize")
async def optimize_thresholds(request: OptimizeRequest):
    """
    优化买入/卖出阈值 - 需要真实数据支持
    """
    raise HTTPException(status_code=503, detail="阈值优化服务暂不可用，需要配置真实数据源")


@router.post("/rolling")
async def run_rolling_validation(
    train_window: int = Query(252, description="训练窗口（交易日）"),
    test_window: int = Query(63, description="测试窗口（交易日）"),
    step: int = Query(21, description="滚动步长")
):
    """
    滚动验证 - 需要真实数据支持
    """
    raise HTTPException(status_code=503, detail="滚动验证服务暂不可用，需要配置真实数据源")


@router.get("/strategies")
async def get_available_strategies():
    """
    获取可用的回测策略
    """
    return {
        "success": True,
        "data": [
            {
                "id": "ai_score",
                "name": "AI评分策略",
                "description": "基于AI综合评分进行买卖决策",
                "parameters": ["buy_threshold", "sell_threshold", "holding_days"]
            },
            {
                "id": "limit_up",
                "name": "涨停追踪策略",
                "description": "追踪涨停板股票，次日买入",
                "parameters": ["holding_days", "stop_loss"]
            },
            {
                "id": "fund_flow",
                "name": "资金流向策略",
                "description": "跟踪主力资金流入股票",
                "parameters": ["flow_threshold", "holding_days"]
            },
            {
                "id": "sentiment",
                "name": "情绪分析策略",
                "description": "基于市场情绪指标交易",
                "parameters": ["sentiment_threshold", "holding_days"]
            },
            {
                "id": "momentum",
                "name": "动量策略",
                "description": "追踪强势股票的动量效应",
                "parameters": ["lookback_days", "holding_days"]
            }
        ]
    }


@router.get("/results")
async def get_backtest_results(
    limit: int = Query(10, description="返回数量"),
    strategy: str = Query(None, description="策略筛选")
):
    """
    获取回测结果列表
    """
    try:
        results = db.get_backtest_results(strategy=strategy, limit=limit)
        return {
            "success": True,
            "data": [
                {
                    "id": r["id"],
                    "strategy": r["strategy"],
                    "start_date": r["start_date"],
                    "end_date": r["end_date"],
                    "total_return": r["total_return"],
                    "sharpe_ratio": r["sharpe_ratio"],
                    "created_at": r["created_at"]
                }
                for r in results
            ]
        }
    except Exception as e:
        logger.error(f"获取回测结果失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/results/{backtest_id}")
async def get_backtest_detail(backtest_id: int):
    """
    获取回测详情
    """
    try:
        result = db.get_backtest_detail(backtest_id)
        if not result:
            raise HTTPException(status_code=404, detail="回测记录不存在")
        return {
            "success": True,
            "data": result
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取回测详情失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history")
async def get_backtest_history(
    limit: int = Query(10, description="返回数量")
):
    """
    获取历史回测记录（兼容旧接口）
    """
    return await get_backtest_results(limit=limit)


def _get_strategy_name(strategy_id: str) -> str:
    """获取策略名称"""
    names = {
        "ai_score": "AI评分策略",
        "limit_up": "涨停追踪策略",
        "fund_flow": "资金流向策略",
        "sentiment": "情绪分析策略",
        "momentum": "动量策略"
    }
    return names.get(strategy_id, strategy_id)
