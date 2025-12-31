"""
估值分析API路由
提供股票估值分析和DCF模型接口
"""
from fastapi import APIRouter, HTTPException
from typing import Dict, Any
import logging

from packages.core.valuation.valuation_summary import ValuationSummary
from packages.core.valuation.dcf_model import DCFValuation
from packages.core.valuation.ddm_model import DDMValuation
from packages.core.valuation.peg_model import PEGValuation

router = APIRouter(prefix="/api/valuation", tags=["估值分析"])
logger = logging.getLogger(__name__)

# 初始化估值服务
valuation_summary = ValuationSummary()
dcf_model = DCFValuation()
ddm_model = DDMValuation()
peg_model = PEGValuation()


@router.get("/{code}", response_model=Dict[str, Any])
async def get_valuation(code: str):
    """
    获取股票综合估值分析

    - **code**: 股票代码
    """
    try:
        result = valuation_summary.get_comprehensive_valuation(code)
        
        if 'error' in result and result.get('valuation_results') is None:
            raise HTTPException(
                status_code=503,
                detail=f"估值服务不可用: {result['error']}"
            )
        
        return {"success": True, "data": result}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取估值失败: {code}, 错误: {str(e)}")
        raise HTTPException(status_code=503, detail=f"估值服务不可用: {str(e)}")


@router.get("/{code}/dcf", response_model=Dict[str, Any])
async def get_dcf_valuation(code: str):
    """
    获取DCF估值模型（需要财务数据支持）

    - **code**: 股票代码
    """
    try:
        # DCF模型需要财务数据，通过综合估值获取
        result = valuation_summary.get_comprehensive_valuation(code)
        
        if 'error' in result and result.get('valuation_results') is None:
            raise HTTPException(
                status_code=503,
                detail=f"DCF估值服务不可用: {result['error']}"
            )
        
        # 提取DCF相关数据
        dcf_data = {
            'stock_code': code,
            'fair_value_low': result.get('fair_value_low', 0),
            'fair_value_mid': result.get('fair_value_mid', 0),
            'fair_value_high': result.get('fair_value_high', 0),
            'current_price': result.get('current_price', 0),
            'margin_of_safety': result.get('margin_of_safety', 0),
            'recommendation': result.get('overall_recommendation', ''),
        }
        
        return {"success": True, "data": dcf_data}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取DCF估值失败: {code}, 错误: {str(e)}")
        raise HTTPException(status_code=503, detail=f"DCF估值服务不可用: {str(e)}")


@router.get("/{code}/ddm", response_model=Dict[str, Any])
async def get_ddm_valuation(code: str):
    """
    获取DDM股利折现估值

    - **code**: 股票代码
    """
    try:
        result = ddm_model.gordon_growth_model(code)
        
        if 'error' in result:
            raise HTTPException(
                status_code=503,
                detail=f"DDM估值服务不可用: {result['error']}"
            )
        
        return {"success": True, "data": result}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取DDM估值失败: {code}, 错误: {str(e)}")
        raise HTTPException(status_code=503, detail=f"DDM估值服务不可用: {str(e)}")


@router.get("/{code}/peg", response_model=Dict[str, Any])
async def get_peg_valuation(code: str):
    """
    获取PEG估值

    - **code**: 股票代码
    """
    try:
        result = peg_model.calculate_peg(code)
        
        if 'error' in result:
            raise HTTPException(
                status_code=503,
                detail=f"PEG估值服务不可用: {result['error']}"
            )
        
        return {"success": True, "data": result}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取PEG估值失败: {code}, 错误: {str(e)}")
        raise HTTPException(status_code=503, detail=f"PEG估值服务不可用: {str(e)}")


@router.get("/{code}/compare", response_model=Dict[str, Any])
async def compare_valuation(code: str):
    """
    多模型对比估值分析

    - **code**: 股票代码
    """
    try:
        df = valuation_summary.compare_valuation_models(code)
        
        if df.empty:
            raise HTTPException(
                status_code=503,
                detail="估值对比服务不可用: 无法获取有效估值数据"
            )
        
        return {
            "success": True,
            "data": {
                "target": code,
                "comparisons": df.to_dict(orient='records')
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取估值对比失败: {code}, 错误: {str(e)}")
        raise HTTPException(status_code=503, detail=f"估值对比服务不可用: {str(e)}")
