"""向量搜索工具 - 基于特征相似度的实现"""

from typing import Optional, List, Dict
from ..storage import get_db
from ..services.factor_calculator import factor_calculator
from ..services import technical_analysis
from ..services.vector_search import vector_search_engine
from ..utils import ok, fail
import statistics


def register(mcp):
    """注册向量搜索工具"""
    
    @mcp.tool()
    async def search_similar_stocks(
        code: str,
        top_n: int = 10,
        similarity_type: str = 'both'
    ):
        """
        搜索相似股票 - 基于基本面和技术面特征相似度
        
        Args:
            code: 股票代码
            top_n: 返回数量
            similarity_type: 相似度类型 ('fundamental'基本面, 'technical'技术面, 'both'综合)
        """
        try:
            db = get_db()
            
            # 1. 获取目标股票信息
            target_info = await db.get_stock_info(code)
            if not target_info:
                return fail(f'Stock {code} not found')
            
            target_industry = target_info.get('industry', '')
            
            # 2. 获取目标股票特征
            target_features = {}
            
            # 基本面特征
            if similarity_type in ['fundamental', 'both']:
                try:
                    financials = await db.get_financials(code, limit=1)
                    if financials and len(financials) > 0:
                        latest = financials[0]
                        target_features['roe'] = latest.get('roe', 0)
                        target_features['debt_ratio'] = latest.get('debt_ratio', 0)
                        target_features['revenue_growth'] = latest.get('revenue_growth', 0)
                except:
                    pass
                
                target_features['pe'] = target_info.get('pe_ratio', 0)
                target_features['pb'] = target_info.get('pb_ratio', 0)
            
            # 技术面特征
            if similarity_type in ['technical', 'both']:
                try:
                    klines = await db.get_klines(code, limit=60)
                    if klines and len(klines) >= 20:
                        closes = [k['close'] for k in klines]
                        
                        # 动量
                        target_features['momentum'] = factor_calculator.calculate_momentum(closes[:20])
                        # 波动率
                        target_features['volatility'] = factor_calculator.calculate_volatility(closes[:20])
                        # 趋势
                        ma20 = technical_analysis.TechnicalAnalysis.calculate_sma(closes, 20)
                        if ma20 and len(ma20) > 0:
                            target_features['trend'] = (closes[0] - ma20[-1]) / ma20[-1]
                except:
                    pass
            
            if not target_features:
                return fail('Cannot extract features from target stock')
            
            # 3. 查找同行业股票
            async with db.acquire() as conn:
                rows = await conn.fetch(
                    """SELECT code, name FROM stocks 
                       WHERE industry = $1 AND code != $2 
                       LIMIT 100""",
                    target_industry, code
                )
                candidate_codes = [row['code'] for row in rows]
                candidate_names = {row['code']: row['name'] for row in rows}
            
            if not candidate_codes:
                return fail(f'No candidate stocks found in industry: {target_industry}')
            
            # 4. 计算相似度
            similarities = []
            
            for candidate_code in candidate_codes[:50]:  # 限制计算数量
                try:
                    candidate_features = {}
                    
                    # 基本面特征
                    if similarity_type in ['fundamental', 'both']:
                        candidate_info = await db.get_stock_info(candidate_code)
                        if not candidate_info:
                            continue
                        
                        try:
                            financials = await db.get_financials(candidate_code, limit=1)
                            if financials and len(financials) > 0:
                                latest = financials[0]
                                candidate_features['roe'] = latest.get('roe', 0)
                                candidate_features['debt_ratio'] = latest.get('debt_ratio', 0)
                                candidate_features['revenue_growth'] = latest.get('revenue_growth', 0)
                        except:
                            pass
                        
                        candidate_features['pe'] = candidate_info.get('pe_ratio', 0)
                        candidate_features['pb'] = candidate_info.get('pb_ratio', 0)
                    
                    # 技术面特征
                    if similarity_type in ['technical', 'both']:
                        try:
                            klines = await db.get_klines(candidate_code, limit=60)
                            if klines and len(klines) >= 20:
                                closes = [k['close'] for k in klines]
                                candidate_features['momentum'] = factor_calculator.calculate_momentum(closes[:20])
                                candidate_features['volatility'] = factor_calculator.calculate_volatility(closes[:20])
                                ma20 = technical_analysis.TechnicalAnalysis.calculate_sma(closes, 20)
                                if ma20 and len(ma20) > 0:
                                    candidate_features['trend'] = (closes[0] - ma20[-1]) / ma20[-1]
                        except:
                            pass
                    
                    if not candidate_features:
                        continue
                    
                    # 计算欧氏距离相似度
                    common_features = set(target_features.keys()) & set(candidate_features.keys())
                    if not common_features:
                        continue
                    
                    distances = []
                    for feature in common_features:
                        target_val = target_features[feature]
                        candidate_val = candidate_features[feature]
                        
                        # 归一化处理
                        if feature in ['pe', 'pb']:
                            if target_val > 0 and candidate_val > 0:
                                distances.append(abs(target_val - candidate_val) / max(target_val, candidate_val))
                        elif feature in ['roe', 'debt_ratio', 'revenue_growth', 'momentum', 'volatility', 'trend']:
                            distances.append(abs(target_val - candidate_val))
                    
                    if distances:
                        avg_distance = statistics.mean(distances)
                        similarity = 1 / (1 + avg_distance)  # 转换为相似度
                        
                        similarities.append({
                            'code': candidate_code,
                            'name': candidate_names.get(candidate_code, ''),
                            'similarity': round(similarity, 4),
                            'features': candidate_features
                        })
                
                except Exception as e:
                    continue
            
            # 5. 排序并返回
            similarities.sort(key=lambda x: x['similarity'], reverse=True)
            
            return ok({
                'code': code,
                'name': target_info.get('name', ''),
                'industry': target_industry,
                'similar_stocks': similarities[:top_n],
                'similarity_type': similarity_type,
                'total_candidates': len(candidate_codes),
                'calculated': len(similarities)
            })
        
        except Exception as e:
            return fail(str(e))
    
    @mcp.tool()
    async def search_by_kline(
        code: str,
        days: int = 20,
        top_n: int = 10,
        search_backend: str = 'python',
        allow_fallback: bool = True,
    ):
        """
        基于K线形态搜索相似股票 - 使用向量搜索引擎。

        Args:
            code: 股票代码
            days: K线天数
            top_n: 返回数量
            search_backend: 检索后端（python/index）
            allow_fallback: index 失败时是否回退 python
        """
        try:
            db = get_db()

            # 1. 获取目标股票K线
            target_klines = await db.get_klines(code, limit=days)
            if not target_klines or len(target_klines) < days:
                return fail(f'Insufficient kline data for {code}')

            # 2. 获取目标股票信息
            target_info = await db.get_stock_info(code)
            target_industry = target_info.get('industry', '') if target_info else ''

            # 3. 查找候选股票
            async with db.acquire() as conn:
                if target_industry:
                    rows = await conn.fetch(
                        """SELECT code, name FROM stocks
                           WHERE industry = $1 AND code != $2
                           LIMIT 100""",
                        target_industry, code
                    )
                else:
                    rows = await conn.fetch(
                        """SELECT code, name FROM stocks
                           WHERE code != $1
                           LIMIT 100""",
                        code
                    )

            candidates = {row['code']: row['name'] for row in rows}
            if not candidates:
                return fail('No candidate stocks found')

            # 4. 获取候选K线并执行向量检索
            candidate_klines_dict: Dict[str, List[Dict]] = {}
            for candidate_code in list(candidates.keys())[:50]:
                try:
                    candidate_klines = await db.get_klines(candidate_code, limit=days)
                    if candidate_klines and len(candidate_klines) >= days:
                        candidate_klines_dict[candidate_code] = candidate_klines
                except Exception:
                    continue

            if not candidate_klines_dict:
                return fail('No candidate kline data available')

            search_results = vector_search_engine.find_similar_patterns(
                query_klines=target_klines,
                candidate_klines_dict=candidate_klines_dict,
                top_k=top_n,
                method='returns',
                metric='correlation',
                backend=search_backend,
                allow_fallback=allow_fallback,
            )

            results = []
            for item in search_results:
                candidate_code = item.get('code', '')
                similarity = float(item.get('similarity', 0.0))
                results.append({
                    'code': candidate_code,
                    'name': candidates.get(candidate_code, ''),
                    'similarity': round(similarity, 4),
                    'source': item.get('source', vector_search_engine.last_backend_used),
                })

            return ok({
                'code': code,
                'name': target_info.get('name', '') if target_info else '',
                'days': days,
                'results': results,
                'total_candidates': len(candidates),
                'candidate_klines_loaded': len(candidate_klines_dict),
                'calculated': len(results),
                'search_backend': search_backend,
                'actual_backend': vector_search_engine.last_backend_used,
                'allow_fallback': bool(allow_fallback),
            })

        except Exception as e:
            return fail(str(e))
    
    @mcp.tool()
    async def semantic_stock_search(
        query: str,
        limit: int = 20
    ):
        """
        语义化股票搜索 - 基于关键词匹配
        
        Args:
            query: 搜索查询（支持股票代码、名称、行业关键词）
            limit: 返回数量
        """
        try:
            db = get_db()
            
            # 1. 解析查询
            query_lower = query.lower()
            
            # 2. 搜索股票
            async with db.acquire() as conn:
                # 多条件搜索
                rows = await conn.fetch(
                    """SELECT code, name, industry, market_cap, pe_ratio, pb_ratio
                       FROM stocks 
                       WHERE LOWER(code) LIKE $1 
                          OR LOWER(name) LIKE $1 
                          OR LOWER(industry) LIKE $1
                       ORDER BY market_cap DESC NULLS LAST
                       LIMIT $2""",
                    f'%{query_lower}%', limit
                )
                
                results = []
                for row in rows:
                    # 计算匹配分数
                    score = 0.0
                    match_type = []
                    
                    code_lower = row['code'].lower()
                    name_lower = row['name'].lower() if row['name'] else ''
                    industry_lower = row['industry'].lower() if row['industry'] else ''
                    
                    # 代码完全匹配
                    if code_lower == query_lower:
                        score += 1.0
                        match_type.append('code_exact')
                    elif query_lower in code_lower:
                        score += 0.8
                        match_type.append('code_partial')
                    
                    # 名称匹配
                    if query_lower in name_lower:
                        score += 0.9
                        match_type.append('name')
                    
                    # 行业匹配
                    if query_lower in industry_lower:
                        score += 0.6
                        match_type.append('industry')
                    
                    # 如果没有匹配，给个基础分
                    if score == 0:
                        score = 0.3
                    
                    results.append({
                        'code': row['code'],
                        'name': row['name'],
                        'industry': row['industry'],
                        'market_cap': float(row['market_cap']) if row['market_cap'] else None,
                        'pe_ratio': float(row['pe_ratio']) if row['pe_ratio'] else None,
                        'pb_ratio': float(row['pb_ratio']) if row['pb_ratio'] else None,
                        'score': round(score, 2),
                        'match_type': match_type
                    })
                
                # 按分数排序
                results.sort(key=lambda x: x['score'], reverse=True)
                
                return ok({
                    'query': query,
                    'results': results,
                    'count': len(results)
                })
        
        except Exception as e:
            return fail(str(e))
