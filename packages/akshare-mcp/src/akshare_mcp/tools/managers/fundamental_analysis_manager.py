"""基本面分析管理器 - 杜邦分析、同行对比、内在价值（增强版）"""

from typing import Optional
import json
from ...storage import get_db
from ...utils import ok, fail, normalize_code
from ...data_source import data_source
import logging

logger = logging.getLogger(__name__)

def _normalize_kwargs(code: Optional[str], kwargs: dict) -> tuple[Optional[str], dict]:
    # 支持 kwargs="{}" 形式（JSON 字符串）
    if kwargs.get("kwargs") and isinstance(kwargs.get("kwargs"), str):
        try:
            extra = json.loads(kwargs.get("kwargs") or "{}")
            if isinstance(extra, dict):
                kwargs = {**kwargs, **extra}
        except Exception:
            pass
    # 支持多种 code 传参
    code = code or kwargs.get("code") or kwargs.get("Code") or kwargs.get("stock_code") or kwargs.get("symbol")
    # compare 动作常见传参别名
    if "codes" not in kwargs and "Codes" in kwargs:
        kwargs["codes"] = kwargs.get("Codes")
    return code, kwargs


def register_fundamental_analysis_manager(mcp):
    """注册基本面分析管理器工具"""
    
    @mcp.tool()
    async def fundamental_analysis_manager(action: str, code: Optional[str] = None, **kwargs):
        """基本面分析管理器（统一 action + kwargs 协议）

        Args:
            action (str, required): 操作类型，可选 help/analyze/dupont/compare
            code (str, optional): 股票代码
            kwargs: JSON 字符串或关键字参数，不同 action 所需参数:
                - help: 无需额外参数
                - analyze: code(str, 股票代码)
                - dupont: code(str, 杜邦分析)
                - compare: code(str), peers(list[str], optional, 对比公司列表)

        Returns:
            dict: {"success": bool, "data": {...}, "error": str|None}

        Examples:
            # 查看帮助
            fundamental_analysis_manager(action="help", kwargs="{}")
            # 基本面分析
            fundamental_analysis_manager(action="analyze", code="600519", kwargs="{}")
            # 杜邦分析
            fundamental_analysis_manager(action="dupont", code="600519", kwargs="{}")
            # 同行对比
            fundamental_analysis_manager(action="compare", code="600519", kwargs='{"peers":["000858","002304"]}')
        """
        try:
            db = get_db()
            code, kwargs = _normalize_kwargs(code, kwargs)
            
            if action == 'help':
                return ok({
                    'supported_actions': {
                        'analyze': '基本面分析（需要 code）',
                        'dupont': '杜邦分析（需要 code）',
                        'compare': '同行对比（需要 code, peers）',
                        'help': '显示帮助信息',
                    }
                })
            
            elif action == 'analyze' and code:
                code = normalize_code(code)
                
                # 1. 尝试从DB获取财务数据
                financials = await db.get_financials(code, limit=4)
                
                # 2. DB无数据时从数据源获取
                if not financials:
                    logger.info(f"[FundamentalManager] Fetching financials for {code}")
                    
                    # 尝试Tushare Pro — 同时获取利润表和财务指标
                    ts_pro = data_source.get_tushare_pro()
                    if ts_pro:
                        try:
                            ts_code = f"{code}.SH" if code.startswith('6') else f"{code}.SZ"
                            # 利润表
                            df_income = ts_pro.income(ts_code=ts_code, fields='end_date,revenue,n_income,basic_eps,total_revenue')
                            # 财务指标（ROE、负债率等）
                            df_fina = None
                            try:
                                df_fina = ts_pro.fina_indicator(ts_code=ts_code, fields='end_date,roe,debt_to_assets,grossprofit_margin,netprofit_yoy,or_yoy')
                            except Exception:
                                pass
                            
                            # 如果 fina_indicator 没有 debt_to_assets，尝试 balancesheet
                            df_balance = None
                            try:
                                df_balance = ts_pro.balancesheet(ts_code=ts_code, fields='end_date,total_liab,total_assets')
                            except Exception:
                                pass
                            
                            if df_income is not None and not df_income.empty:
                                records = df_income.head(4).to_dict('records')
                                # 清理 pandas NaN 值
                                import pandas as pd
                                for rec in records:
                                    for k, v in list(rec.items()):
                                        try:
                                            if pd.isna(v):
                                                rec[k] = None
                                        except (TypeError, ValueError):
                                            pass
                                # 合并财务指标 — 使用前缀匹配（如 20241231 匹配 2024）
                                if df_fina is not None and not df_fina.empty:
                                    fina_map = {}
                                    for _, row in df_fina.iterrows():
                                        ed = str(row.get('end_date', ''))
                                        fina_map[ed] = row.to_dict()
                                    for rec in records:
                                        ed = str(rec.get('end_date', ''))
                                        fina = fina_map.get(ed)
                                        # 如果精确匹配失败，尝试同年最近的报告期
                                        if not fina and ed:
                                            year_prefix = ed[:4]
                                            candidates = [(k, v) for k, v in fina_map.items() if k.startswith(year_prefix)]
                                            if candidates:
                                                # 取最近的报告期
                                                candidates.sort(key=lambda x: x[0], reverse=True)
                                                fina = candidates[0][1]
                                            else:
                                                # 取 fina_indicator 中最新的一条
                                                all_fina = sorted(fina_map.items(), key=lambda x: x[0], reverse=True)
                                                if all_fina:
                                                    fina = all_fina[0][1]
                                        if fina:
                                            rec['roe'] = rec.get('roe') or fina.get('roe')
                                            rec['debt_ratio'] = rec.get('debt_ratio') or fina.get('debt_to_assets')
                                            rec['gross_margin'] = rec.get('gross_margin') or fina.get('grossprofit_margin')
                                            rec['revenue_growth'] = rec.get('revenue_growth') or fina.get('or_yoy')
                                            rec['profit_growth'] = rec.get('profit_growth') or fina.get('netprofit_yoy')
                                
                                # 如果 income 没有匹配到 fina_indicator，直接用 fina_indicator 最新数据补充
                                if df_fina is not None and not df_fina.empty and records:
                                    latest_fina = df_fina.iloc[0].to_dict()
                                    for rec in records:
                                        if rec.get('roe') is None:
                                            rec['roe'] = latest_fina.get('roe')
                                        if rec.get('debt_ratio') is None:
                                            rec['debt_ratio'] = latest_fina.get('debt_to_assets')
                                        if rec.get('gross_margin') is None:
                                            rec['gross_margin'] = latest_fina.get('grossprofit_margin')
                                        if rec.get('revenue_growth') is None:
                                            rec['revenue_growth'] = latest_fina.get('or_yoy')
                                        if rec.get('profit_growth') is None:
                                            rec['profit_growth'] = latest_fina.get('netprofit_yoy')
                                
                                # 从资产负债表补充 debt_ratio
                                if df_balance is not None and not df_balance.empty:
                                    balance_map = {}
                                    for _, row in df_balance.iterrows():
                                        ed = str(row.get('end_date', ''))
                                        total_liab = row.get('total_liab')
                                        total_assets = row.get('total_assets')
                                        if total_liab is not None and total_assets is not None and float(total_assets or 0) > 0:
                                            balance_map[ed] = float(total_liab) / float(total_assets) * 100
                                    for rec in records:
                                        ed = str(rec.get('end_date', ''))
                                        if rec.get('debt_ratio') is None and ed in balance_map:
                                            rec['debt_ratio'] = balance_map[ed]
                                
                                financials = records
                        except Exception as e:
                            logger.warning(f"[FundamentalManager] Tushare failed: {e}")
                
                # 3. 降级到TDX
                if not financials:
                    stock_info = data_source.get_stock_info_priority_tdx(code)
                    if stock_info:
                        financials = [{
                            'code': code,
                            'name': stock_info.get('name'),
                            'industry': stock_info.get('industry'),
                            'pe_ratio': stock_info.get('pe_ratio'),
                            'pb_ratio': stock_info.get('pb_ratio'),
                            'market_cap': stock_info.get('market_cap'),
                            'source': 'tdx'
                        }]
                
                if not financials:
                    return fail(f'无法获取 {code} 的财务数据')
                
                # 4. 计算关键指标
                metrics = {}
                if financials and isinstance(financials[0], dict):
                    latest = financials[0]
                    
                    def _safe_num(val, default=0):
                        if val is None:
                            return default
                        try:
                            import math
                            import pandas as pd
                            if pd.isna(val):
                                return default
                            v = float(val)
                            return default if math.isnan(v) else v
                        except (ValueError, TypeError):
                            return default
                    
                    metrics = {
                        'revenue': _safe_num(latest.get('revenue') or latest.get('total_revenue')),
                        'net_income': _safe_num(latest.get('n_income') or latest.get('net_income') or latest.get('netProfit') or latest.get('net_profit')),
                        'eps': _safe_num(latest.get('basic_eps') or latest.get('eps')),
                        'pe_ratio': latest.get('pe_ratio'),
                        'pb_ratio': latest.get('pb_ratio'),
                        'roe': _safe_num(latest.get('roe'), None),
                        'debt_ratio': _safe_num(latest.get('debt_ratio') or latest.get('debt_to_assets') or latest.get('debtRatio'), None),
                        'gross_margin': _safe_num(latest.get('gross_margin') or latest.get('grossprofit_margin') or latest.get('grossProfitMargin'), None),
                        'revenue_growth': _safe_num(latest.get('revenue_growth') or latest.get('or_yoy'), None),
                        'profit_growth': _safe_num(latest.get('profit_growth') or latest.get('netprofit_yoy'), None),
                    }
                
                # 如果核心字段仍为空，尝试 get_financials 工具补充
                if not metrics.get('revenue') and not metrics.get('net_income'):
                    try:
                        from ..finance import get_financials
                        fin_res = get_financials(code)
                        if fin_res.get('success') and fin_res.get('data'):
                            fin_data = fin_res['data']
                            metrics['revenue'] = metrics.get('revenue') or fin_data.get('revenue') or 0
                            metrics['net_income'] = metrics.get('net_income') or fin_data.get('netProfit') or fin_data.get('net_income') or 0
                            metrics['eps'] = metrics.get('eps') or fin_data.get('eps') or 0
                            metrics['pe_ratio'] = metrics.get('pe_ratio') or fin_data.get('pe_ratio')
                            metrics['roe'] = fin_data.get('roe')
                            metrics['source'] = fin_data.get('source', 'finance_tool')
                    except Exception:
                        pass
                
                return ok({
                    'code': code,
                    'financials': financials,
                    'metrics': metrics,
                    'data_points': len(financials)
                })
            
            elif action == 'dupont':
                if not code:
                    return fail('需要提供股票代码')
                
                code = normalize_code(code)
                financials = await db.get_financials(code, limit=1)
                if not financials:
                    return fail('无财务数据')
                
                latest = financials[0]
                roe = latest.get('roe', 0)
                
                return ok({
                    'code': code,
                    'roe': float(roe),
                    'analysis': '杜邦分析'
                })
            
            elif action == 'compare':
                codes = kwargs.get('codes', [])
                if not codes:
                    return fail('需要提供股票代码列表')
                
                comparison = []
                for c in codes[:5]:
                    result = await fundamental_analysis_manager('analyze', code=c)
                    if result.get('success'):
                        comparison.append({
                            'code': c,
                            'metrics': result['data']['metrics']
                        })
                
                return ok({'comparison': comparison})
            
            else:
                return fail(f'Unknown action: {action}. Supported: help, analyze, dupont, compare')
        except Exception as e:
            logger.error(f"[FundamentalManager] Error: {e}")
            return fail(str(e))
