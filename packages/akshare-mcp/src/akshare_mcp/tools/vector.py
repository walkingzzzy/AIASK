"""向量搜索工具 - 基于特征相似度的实现"""

from typing import Optional, List, Dict
from ..storage import get_db
from ..services.factor_calculator import factor_calculator
from ..services import technical_analysis
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
        top_n: int = 10
    ):
        """
        基于K线形态搜索相似股票 - 使用价格序列相关性
        
        Args:
            code: 股票代码
            days: K线天数
            top_n: 返回数量
        """
        try:
            db = get_db()
            
            # 1. 获取目标股票K线
            target_klines = await db.get_klines(code, limit=days)
            if not target_klines or len(target_klines) < days:
                return fail(f'Insufficient kline data for {code}')
            
            # 归一化价格序列（使用收益率）
            target_closes = [k['close'] for k in target_klines]
            target_returns = [(target_closes[i] - target_closes[i+1]) / target_closes[i+1] 
                             for i in range(len(target_closes)-1)]
            
            if len(target_returns) < 5:
                return fail('Insufficient data for pattern matching')
            
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
            
            # 4. 计算形态相似度
            similarities = []
            
            for candidate_code, candidate_name in list(candidates.items())[:50]:
                try:
                    candidate_klines = await db.get_klines(candidate_code, limit=days)
                    if not candidate_klines or len(candidate_klines) < days:
                        continue
                    
                    candidate_closes = [k['close'] for k in candidate_klines]
                    candidate_returns = [(candidate_closes[i] - candidate_closes[i+1]) / candidate_closes[i+1] 
                                        for i in range(len(candidate_closes)-1)]
                    
                    if len(candidate_returns) < 5:
                        continue
                    
                    # 计算皮尔逊相关系数
                    min_len = min(len(target_returns), len(candidate_returns))
                    target_subset = target_returns[:min_len]
                    candidate_subset = candidate_returns[:min_len]
                    
                    # 计算相关系数
                    mean_target = statistics.mean(target_subset)
                    mean_candidate = statistics.mean(candidate_subset)
                    
                    numerator = sum((target_subset[i] - mean_target) * (candidate_subset[i] - mean_candidate) 
                                   for i in range(min_len))
                    
                    target_var = sum((x - mean_target) ** 2 for x in target_subset)
                    candidate_var = sum((x - mean_candidate) ** 2 for x in candidate_subset)
                    
                    if target_var > 0 and candidate_var > 0:
                        correlation = numerator / (target_var * candidate_var) ** 0.5
                        similarity = (correlation + 1) / 2  # 转换到[0,1]区间
                        
                        similarities.append({
                            'code': candidate_code,
                            'name': candidate_name,
                            'similarity': round(similarity, 4),
                            'correlation': round(correlation, 4)
                        })
                
                except Exception as e:
                    continue
            
            # 5. 排序并返回
            similarities.sort(key=lambda x: x['similarity'], reverse=True)
            
            return ok({
                'code': code,
                'name': target_info.get('name', '') if target_info else '',
                'days': days,
                'results': similarities[:top_n],
                'total_candidates': len(candidates),
                'calculated': len(similarities)
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
