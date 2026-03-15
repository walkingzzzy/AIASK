"""向量搜索工具 - 基于特征相似度的实现"""

from typing import Optional, List, Dict
from ..storage import get_db
from ..services.factor_calculator import factor_calculator
from ..services import technical_analysis
from ..services.vector_search import vector_search_engine
from .search import _search_stocks_tushare_fallback
from ..utils import ok, fail
import statistics


_GENERIC_SEMANTIC_HINTS = {
    '龙头', '概念', '板块', '赛道', '题材', '核心', '精选', '优选', '成长', '价值'
}


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
                        ma20 = technical_analysis.calculate_sma(closes, 20)
                        if ma20 and len(ma20) > 0:
                            target_features['trend'] = (closes[0] - ma20[-1]) / ma20[-1]
                except:
                    pass
            
            if not target_features:
                return fail('Cannot extract features from target stock')
            
            # 3. 查找候选股票：优先同行业，无同行或行业为空时回退全市场样本
            candidate_scope = 'industry' if target_industry else 'market'
            async with db.acquire() as conn:
                rows = []
                if target_industry:
                    rows = await conn.fetch(
                        """SELECT code, stock_name FROM stocks
                           WHERE industry = $1 AND code != $2
                           LIMIT 100""",
                        target_industry, code
                    )
                if not rows:
                    candidate_scope = 'market'
                    rows = await conn.fetch(
                        """SELECT code, stock_name FROM stocks
                           WHERE code != $1
                           LIMIT 100""",
                        code
                    )
                candidate_codes = [row['code'] for row in rows]
                candidate_names = {row['code']: row['stock_name'] for row in rows}
            
            if not candidate_codes:
                return fail('No candidate stocks found')
            
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
                                ma20 = technical_analysis.calculate_sma(closes, 20)
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
                'name': target_info.get('name') or target_info.get('stock_name', ''),
                'industry': target_industry,
                'candidate_scope': candidate_scope,
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
                        """SELECT code, stock_name FROM stocks
                           WHERE industry = $1 AND code != $2
                           LIMIT 100""",
                        target_industry, code
                    )
                else:
                    rows = await conn.fetch(
                        """SELECT code, stock_name FROM stocks
                           WHERE code != $1
                           LIMIT 100""",
                        code
                    )

            candidates = {row['code']: row['stock_name'] for row in rows}
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
            search_meta = dict(getattr(vector_search_engine, 'last_meta', {}) or {})

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
                'name': (target_info.get('name') or target_info.get('stock_name', '')) if target_info else '',
                'days': days,
                'results': results,
                'total_candidates': len(candidates),
                'candidate_klines_loaded': len(candidate_klines_dict),
                'calculated': len(results),
                'search_backend': search_backend,
                'actual_backend': vector_search_engine.last_backend_used,
                'allow_fallback': bool(allow_fallback),
                'backend_requested': search_meta.get('backend_requested', search_backend),
                'backend_used': search_meta.get('backend_used', vector_search_engine.last_backend_used),
                'fallback_used': bool(search_meta.get('fallback_used', False)),
                'fallback_reason': search_meta.get('fallback_reason'),
                'latency_ms': search_meta.get('latency_ms', 0.0),
            })

        except Exception as e:
            return fail(str(e))
    
    @mcp.tool()
    async def semantic_stock_search(
        query: str,
        limit: int = 20
    ):
        """
        语义化股票搜索 - 基于关键词匹配（支持中文分词、行业关键词、股票代码/名称）

        Args:
            query: 搜索查询（支持股票代码、名称、行业关键词，如"白酒"、"新能源"、"贵州茅台"）
            limit: 返回数量
        """
        try:
            db = get_db()
            query_stripped = query.strip()
            if not query_stripped:
                return fail("查询关键词不能为空")

            # 生成搜索token列表:
            #   db_tokens: 2字及以上（用于DB LIKE，避免单字误匹配）
            #   sector_tokens: 含单字（用于行业名称模糊匹配）
            def _tokenize(text: str):
                import re as _re
                base = [text.lower()]
                cjk_chars = [c for c in text if '\u4e00' <= c <= '\u9fff']
                for i in range(len(cjk_chars) - 1):
                    base.append(cjk_chars[i] + cjk_chars[i + 1])
                for seg in _re.findall(r'[\u4e00-\u9fff]{2,}', text):
                    base.append(seg.lower())
                db_tks = list(dict.fromkeys(base))
                sector_tks = list(dict.fromkeys(base + cjk_chars))
                return db_tks, sector_tks

            tokens, sector_tokens = _tokenize(query_stripped)
            weighted_tokens = [t for t in tokens if len(t) >= 2]
            generic_tokens = [t for t in weighted_tokens if t in _GENERIC_SEMANTIC_HINTS]

            def _extract_industry_query_tokens(text: str) -> List[str]:
                import re as _re3

                residual = text.lower()
                for hint in sorted(_GENERIC_SEMANTIC_HINTS, key=len, reverse=True):
                    residual = residual.replace(hint, ' ')

                refined: List[str] = []
                for seg in _re3.findall(r'[\u4e00-\u9fff]{2,}', residual):
                    refined.append(seg.lower())
                    seg_tokens, _ = _tokenize(seg)
                    refined.extend(
                        t for t in seg_tokens
                        if len(t) >= 2 and t != text.lower() and t not in _GENERIC_SEMANTIC_HINTS
                    )
                return list(dict.fromkeys(refined))

            industry_query_tokens = _extract_industry_query_tokens(query_stripped) if generic_tokens else []

            async with db.acquire() as conn:
                seen_codes: set = set()
                all_rows: List[Dict] = []

                def _append_row(row: Dict):
                    code = str(row.get('code', '') or '')
                    if not code or code in seen_codes:
                        return
                    seen_codes.add(code)
                    all_rows.append({
                        'code': code,
                        'stock_name': row.get('stock_name') or row.get('name'),
                        'industry': row.get('industry'),
                        'market_cap': row.get('market_cap'),
                        'pe_ratio': row.get('pe_ratio'),
                        'pb_ratio': row.get('pb_ratio'),
                    })

                def _has_industry_hits() -> bool:
                    if not industry_query_tokens:
                        return False
                    for row in all_rows:
                        industry_l = str(row.get('industry', '') or '').lower()
                        if any(token in industry_l for token in industry_query_tokens):
                            return True
                    return False

                def _append_sector_candidates(match_text: str):
                    try:
                        import akshare as ak_mod

                        q_lower = match_text.lower()
                        q_cjk_chars = [c for c in match_text if '\u4e00' <= c <= '\u9fff']

                        def _sector_match(name: str) -> bool:
                            name_l = name.lower()
                            if q_lower in name_l or name_l in q_lower:
                                return True
                            return any(c in name_l for c in q_cjk_chars)

                        matched_sectors = []
                        df_spot = ak_mod.stock_sector_spot()
                        if df_spot is not None and not df_spot.empty:
                            for _, srow in df_spot.iterrows():
                                bname = str(srow.get('板块', '') or '')
                                blabel = str(srow.get('label', '') or '')
                                if _sector_match(bname):
                                    matched_sectors.append((blabel, bname))
                        if len(matched_sectors) < 2:
                            df_ths = ak_mod.stock_board_industry_name_ths()
                            if df_ths is not None and not df_ths.empty:
                                for _, brow in df_ths.iterrows():
                                    bname = str(brow.get('name', '') or '')
                                    bcode = str(brow.get('code', '') or '')
                                    if _sector_match(bname):
                                        matched_sectors.append((bcode, bname))
                        for blabel, bname in matched_sectors[:2]:
                            try:
                                if not blabel.startswith('new_'):
                                    continue
                                df_cons = ak_mod.stock_sector_detail(sector=blabel)
                                if df_cons is None or df_cons.empty:
                                    continue
                                for _, crow in df_cons.head(limit).iterrows():
                                    _append_row({
                                        'code': str(crow.get('code', '') or ''),
                                        'name': str(crow.get('name', '') or ''),
                                        'industry': bname,
                                        'market_cap': None,
                                        'pe_ratio': None,
                                        'pb_ratio': None,
                                    })
                            except Exception:
                                continue
                    except Exception:
                        pass

                # 对每个token做搜索（全量token中最多取前6个）
                for token in tokens[:6]:
                    pat = f'%{token}%'
                    rows = await conn.fetch(
                        """SELECT code, stock_name, industry, market_cap, pe_ratio, pb_ratio
                           FROM stocks
                           WHERE LOWER(code) LIKE $1
                              OR LOWER(stock_name) LIKE $1
                              OR (industry IS NOT NULL AND LOWER(industry) LIKE $1)
                           ORDER BY market_cap DESC NULLS LAST
                           LIMIT $2""",
                        pat, limit * 2
                    )
                    for row in rows:
                        _append_row(dict(row))

                # 对“行业词 + 泛化词”查询补行业召回：即便已有名称命中，也继续尝试补全行业候选
                if industry_query_tokens and not _has_industry_hits():
                    for token in industry_query_tokens[:4]:
                        rows = await conn.fetch(
                            """SELECT code, stock_name, industry, market_cap, pe_ratio, pb_ratio
                               FROM stocks
                               WHERE industry IS NOT NULL AND LOWER(industry) LIKE $1
                               ORDER BY market_cap DESC NULLS LAST
                               LIMIT $2""",
                            f'%{token}%', limit * 2
                        )
                        for row in rows:
                            _append_row(dict(row))

                if industry_query_tokens and not _has_industry_hits():
                    for token in industry_query_tokens[:3]:
                        for row in _search_stocks_tushare_fallback(token, limit * 2):
                            _append_row(row)

                if industry_query_tokens and not _has_industry_hits():
                    for token in industry_query_tokens[:2]:
                        _append_sector_candidates(token)

                if not all_rows:
                    _append_sector_candidates(query_stripped)

                # 计算匹配分数
                results = []
                for row in all_rows:
                    score = 0.0
                    match_type = []
                    code_l = (row['code'] or '').lower()
                    name_l = (row['stock_name'] or '').lower()
                    industry_l = (row['industry'] or '').lower()
                    q_l = query_stripped.lower()
                    matched_name_tokens = [t for t in weighted_tokens if t in name_l]
                    matched_industry_tokens = [t for t in weighted_tokens if t in industry_l]
                    strong_name_tokens = [t for t in matched_name_tokens if t not in _GENERIC_SEMANTIC_HINTS]
                    generic_name_tokens = [t for t in matched_name_tokens if t in _GENERIC_SEMANTIC_HINTS]
                    strong_industry_tokens = [t for t in matched_industry_tokens if t not in _GENERIC_SEMANTIC_HINTS]

                    if code_l == q_l:
                        score += 1.0; match_type.append('code_exact')
                    elif q_l in code_l:
                        score += 0.8; match_type.append('code_partial')
                    if q_l in name_l:
                        score += 0.9; match_type.append('name_exact')
                    elif strong_name_tokens:
                        score += 0.6; match_type.append('name_partial')
                    elif generic_name_tokens:
                        score += 0.2; match_type.append('name_hint')
                    if industry_l and strong_industry_tokens:
                        score += 0.85; match_type.append('industry')
                        if generic_tokens:
                            score += 0.2; match_type.append('industry_context')
                    elif industry_l and matched_industry_tokens:
                        score += 0.45; match_type.append('industry_hint')
                    if score == 0:
                        score = 0.3

                    results.append({
                        'code': row['code'],
                        'name': row['stock_name'],
                        'industry': row['industry'],
                        'market_cap': float(row['market_cap']) if row.get('market_cap') else None,
                        'pe_ratio': float(row['pe_ratio']) if row.get('pe_ratio') else None,
                        'pb_ratio': float(row['pb_ratio']) if row.get('pb_ratio') else None,
                        'score': round(score, 2),
                        'match_type': match_type,
                    })

                results.sort(key=lambda x: x['score'], reverse=True)

                return ok({
                    'query': query_stripped,
                    'results': results[:limit],
                    'count': len(results[:limit]),
                })

        except Exception as e:
            return fail(str(e))
