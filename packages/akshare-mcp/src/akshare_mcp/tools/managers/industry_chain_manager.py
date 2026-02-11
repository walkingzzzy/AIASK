"""产业链管理器 - 产业链分析和关联股票"""

import json
import logging
from ...utils import ok, fail
from ...storage import get_db

logger = logging.getLogger(__name__)

# 预置产业链数据（基于行业知识）
INDUSTRY_CHAINS = {
    '新能源汽车': {
        'upstream': ['锂矿开采', '正极材料', '负极材料', '电解液', '隔膜'],
        'midstream': ['动力电池', '电机电控', '汽车零部件'],
        'downstream': ['整车制造', '充电桩', '换电站'],
        'key_stocks': {
            'upstream': ['002460', '300750', '603799'],
            'midstream': ['300750', '002594', '002129'],
            'downstream': ['002594', '600104', '300750']
        }
    },
    '半导体': {
        'upstream': ['硅片', '光刻胶', '电子气体', '靶材'],
        'midstream': ['芯片设计', '晶圆制造', '封装测试'],
        'downstream': ['消费电子', '汽车电子', '工业控制'],
        'key_stocks': {
            'upstream': ['688981', '603005', '688396'],
            'midstream': ['688981', '688008', '002371'],
            'downstream': ['002371', '000725', '002049']
        }
    },
    '光伏': {
        'upstream': ['多晶硅', '硅片', '银浆', '玻璃'],
        'midstream': ['电池片', '组件', '逆变器'],
        'downstream': ['光伏电站', '分布式光伏', '储能'],
        'key_stocks': {
            'upstream': ['601012', '688223', '300393'],
            'midstream': ['601012', '688223', '300274'],
            'downstream': ['601012', '300274', '002459']
        }
    },
    '白酒': {
        'upstream': ['粮食种植', '包装材料', '酒瓶生产'],
        'midstream': ['白酒生产', '品牌运营', '渠道建设'],
        'downstream': ['经销商', '零售终端', '电商平台'],
        'key_stocks': {
            'upstream': ['600873', '002571', '600779'],
            'midstream': ['600519', '000858', '000568'],
            'downstream': ['600519', '000858', '603369']
        }
    },
    '医药': {
        'upstream': ['原料药', '医药中间体', '医疗器械原材料'],
        'midstream': ['制剂生产', '医疗器械制造', 'CRO/CDMO'],
        'downstream': ['医院', '药店', '医药流通'],
        'key_stocks': {
            'upstream': ['002821', '300759', '688180'],
            'midstream': ['600276', '300015', '603259'],
            'downstream': ['600276', '000028', '603883']
        }
    }
}


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
    return kwargs


def register_industry_chain_manager(mcp):
    """注册产业链管理器工具"""
    
    @mcp.tool()
    async def industry_chain_manager(action: str, **kwargs):
        """产业链管理器（统一 action + kwargs 协议）

        Args:
            action (str, required): 操作类型，可选 help/get_chain/related_stocks
            kwargs: JSON 字符串或关键字参数，不同 action 所需参数:
                - help: 无需额外参数
                - get_chain: keyword(str, 产业链关键词) 或 chain_id(str)
                - related_stocks: keyword(str) 或 chain_id(str)

        Returns:
            dict: {"success": bool, "data": {...}, "error": str|None}

        Examples:
            # 查看帮助
            industry_chain_manager(action="help", kwargs="{}")
            # 获取新能源汽车产业链
            industry_chain_manager(action="get_chain", kwargs='{"keyword":"新能源汽车"}')
            # 获取产业链关联股票
            industry_chain_manager(action="related_stocks", kwargs='{"keyword":"半导体"}')
        """
        try:
            kwargs = _normalize_kwargs(kwargs)
            db = get_db()
            
            if action == 'help':
                return ok({
                    'supported_actions': {
                        'get_chain': '获取产业链信息（需要 keyword/industry）',
                        'related_stocks': '获取产业链关联股票（需要 code）',
                        'help': '显示帮助信息',
                    }
                })
            
            elif action == 'get_chain':
                industry = (
                    kwargs.get('industry')
                    or kwargs.get('industry_name')
                    or kwargs.get('keyword')
                    or kwargs.get('name')
                    or kwargs.get('query')
                    or kwargs.get('sector')
                )
                if not industry or (isinstance(industry, str) and not industry.strip()):
                    return fail('需要提供行业名称（可传 industry / keyword / query / sector 等）')
                industry = industry.strip() if isinstance(industry, str) else str(industry)
                
                # 查找匹配的产业链
                matched_chain = None
                for chain_name, chain_data in INDUSTRY_CHAINS.items():
                    if industry in chain_name or chain_name in industry:
                        matched_chain = chain_name
                        break
                
                if matched_chain:
                    chain_data = INDUSTRY_CHAINS[matched_chain]
                    return ok({
                        'industry': matched_chain,
                        'upstream': chain_data['upstream'],
                        'midstream': chain_data['midstream'],
                        'downstream': chain_data['downstream'],
                        'key_stocks': chain_data['key_stocks'],
                        'source': 'preset'
                    })
                else:
                    # 尝试从数据库查找同行业股票
                    async with db.acquire() as conn:
                        rows = await conn.fetch(
                            "SELECT stock_code, stock_name FROM stocks WHERE industry LIKE $1 LIMIT 10",
                            f'%{industry}%'
                        )
                        related_stocks = [{'code': row['stock_code'], 'name': row['stock_name']} for row in rows]
                    
                    return ok({
                        'industry': industry,
                        'upstream': [],
                        'midstream': [],
                        'downstream': [],
                        'related_stocks': related_stocks,
                        'message': f'未找到 {industry} 的预置产业链数据，返回同行业股票',
                        'available_chains': list(INDUSTRY_CHAINS.keys())
                    })
            
            elif action == 'related_stocks':
                code = kwargs.get('code') or kwargs.get('Code') or kwargs.get('stock_code')
                if not code:
                    code = kwargs.get('chain_id')
                if not code:
                    return fail('需要提供股票代码')
                
                # 获取股票所属行业
                async with db.acquire() as conn:
                    stock_info = await conn.fetchrow(
                        "SELECT stock_name, industry FROM stocks WHERE stock_code = $1",
                        code
                    )
                
                if not stock_info:
                    return ok({
                        'code': code,
                        'related_stocks': [],
                        'message': '未找到该股票信息'
                    })
                
                industry = stock_info['industry']
                
                # 查找同行业股票
                async with db.acquire() as conn:
                    rows = await conn.fetch(
                        "SELECT stock_code, stock_name FROM stocks WHERE industry = $1 AND stock_code != $2 LIMIT 20",
                        industry, code
                    )
                    related_stocks = [{'code': row['stock_code'], 'name': row['stock_name']} for row in rows]
                
                return ok({
                    'code': code,
                    'name': stock_info['stock_name'],
                    'industry': industry,
                    'related_stocks': related_stocks,
                    'count': len(related_stocks)
                })
            
            else:
                return fail(f'Unknown action: {action}. Supported: help, get_chain, related_stocks')
        except Exception as e:
            logger.error(f"[IndustryChain] Error: {e}")
            return fail(str(e))
