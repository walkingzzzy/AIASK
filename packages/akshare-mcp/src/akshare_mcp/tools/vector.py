"""向量搜索工具 - 基于特征相似度的实现"""

import asyncio
from collections import defaultdict
from typing import Optional, List, Dict, Any
from datetime import date, datetime
from ..storage import get_db
from ..services.factor_calculator import factor_calculator
from ..services import technical_analysis
from ..services.vector_search import vector_search_engine
from .search import _search_stocks_tushare_fallback
from ..utils import ok, fail, suppress_stdout
import statistics
import math


_GENERIC_SEMANTIC_HINTS = {
    '龙头', '概念', '板块', '赛道', '题材', '核心', '精选', '优选', '成长', '价值'
}
_SEMANTIC_CONCEPT_HINTS = {'概念', '板块', '题材', '赛道'}
_SEMANTIC_ST_PREFIXES = ('*st', 'st', 'sst', 's*st', '退市')
_MIN_SEMANTIC_SCORE = 0.45


def _semantic_is_special_treatment(name: str) -> bool:
    text = str(name or '').strip().lower().replace(' ', '')
    return any(text.startswith(prefix) for prefix in _SEMANTIC_ST_PREFIXES)


def _semantic_is_concept_industry(industry: str) -> bool:
    text = str(industry or '').strip().lower()
    return any(hint in text for hint in _SEMANTIC_CONCEPT_HINTS)


def _normalize_stock_row(row: Dict[str, Any]) -> Dict[str, Any]:
    payload = dict(row or {})
    code = str(payload.get('code') or payload.get('stock_code') or '').strip()
    return {
        'code': code,
        'stock_name': payload.get('stock_name') or payload.get('name') or '',
        'industry': payload.get('industry') or payload.get('sector') or '',
        'pe_ratio': payload.get('pe_ratio'),
        'pb_ratio': payload.get('pb_ratio'),
        'market_cap': payload.get('market_cap'),
    }


async def _load_candidate_stock_rows(db, target_code: str, target_industry: str, limit: int = 100) -> tuple[str, List[Dict[str, Any]]]:
    candidate_scope = 'industry' if target_industry else 'market'

    if hasattr(db, 'list_stock_universe'):
        try:
            rows: List[Dict[str, Any]] = []
            if target_industry:
                rows = [_normalize_stock_row(row) for row in await db.list_stock_universe(limit=limit, industry=target_industry)]
                rows = [row for row in rows if row['code'] and row['code'] != target_code]
            if not rows:
                candidate_scope = 'market'
                rows = [_normalize_stock_row(row) for row in await db.list_stock_universe(limit=limit)]
                rows = [row for row in rows if row['code'] and row['code'] != target_code]
            if rows:
                return candidate_scope, rows[:limit]
        except Exception:
            pass

    if not hasattr(db, 'acquire'):
        return candidate_scope, []

    async with db.acquire() as conn:
        rows = []
        if target_industry:
            rows = await conn.fetch(
                """SELECT code, stock_name, industry, pe_ratio, pb_ratio, market_cap FROM stocks
                   WHERE industry = $1 AND code != $2
                   LIMIT 100""",
                target_industry, target_code
            )
        if not rows:
            candidate_scope = 'market'
            rows = await conn.fetch(
                """SELECT code, stock_name, industry, pe_ratio, pb_ratio, market_cap FROM stocks
                   WHERE code != $1
                   LIMIT 100""",
                target_code
            )
        return candidate_scope, [_normalize_stock_row(dict(row)) for row in rows]


async def _fetch_table_columns(conn, table_name: str) -> set[str]:
    try:
        rows = await conn.fetch(
            """SELECT column_name FROM information_schema.columns
               WHERE table_schema = 'public' AND table_name = $1""",
            table_name,
        )
        names = set()
        for row in rows:
            payload = dict(row)
            name = str(payload.get('column_name') or '').strip()
            if name:
                names.add(name)
        return names
    except Exception:
        return set()


async def _fetch_latest_financial_map(conn, codes: List[str]) -> Dict[str, Dict[str, Any]]:
    if not codes:
        return {}
    try:
        cols = await _fetch_table_columns(conn, 'financials')
        code_col = 'stock_code' if 'stock_code' in cols else 'code'
        rows = await conn.fetch(
            f"""
            SELECT DISTINCT ON ({code_col})
                   {code_col} AS code,
                   roe,
                   debt_ratio,
                   revenue_growth
            FROM financials
            WHERE {code_col} = ANY($1::text[])
            ORDER BY {code_col}, report_date DESC
            """,
            list(dict.fromkeys(codes)),
        )
    except Exception:
        return {}

    result: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        payload = dict(row)
        code = str(payload.get('code') or '').strip()
        if not code:
            continue
        result[code] = payload
    return result


async def _fetch_kline_batch(conn, codes: List[str], limit: int) -> Dict[str, List[Dict[str, Any]]]:
    if not codes or limit <= 0:
        return {}
    try:
        rows = await conn.fetch(
            """
            SELECT code, time, open, high, low, close, volume, amount, turnover, change_pct
            FROM (
                SELECT
                    code, time, open, high, low, close, volume, amount, turnover, change_pct,
                    ROW_NUMBER() OVER (PARTITION BY code ORDER BY time DESC) AS rn
                FROM kline_1d
                WHERE code = ANY($1::text[])
            ) ranked
            WHERE rn <= $2
            ORDER BY code, time ASC
            """,
            list(dict.fromkeys(codes)),
            int(limit),
        )
    except Exception:
        return {}

    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in rows:
        payload = dict(row)
        code = str(payload.get('code') or '').strip()
        time_value = payload.get('time')
        if not code or time_value is None:
            continue
        grouped[code].append({
            'date': time_value.strftime('%Y-%m-%d') if hasattr(time_value, 'strftime') else str(time_value),
            'code': code,
            'open': float(payload['open']) if payload.get('open') is not None else None,
            'high': float(payload['high']) if payload.get('high') is not None else None,
            'low': float(payload['low']) if payload.get('low') is not None else None,
            'close': float(payload['close']) if payload.get('close') is not None else None,
            'volume': int(payload['volume']) if payload.get('volume') is not None else 0,
            'amount': float(payload['amount']) if payload.get('amount') is not None else None,
            'turnover': float(payload['turnover']) if payload.get('turnover') is not None else None,
            'change_pct': float(payload['change_pct']) if payload.get('change_pct') is not None else None,
            'source': 'timescaledb',
        })
    return grouped


async def _prefetch_candidate_context(
    db,
    candidate_rows: List[Dict[str, Any]],
    *,
    need_financials: bool,
    need_klines: bool,
    kline_limit: int,
) -> tuple[Dict[str, Dict[str, Any]], Dict[str, List[Dict[str, Any]]]]:
    candidate_codes = [str(row.get('code') or '').strip() for row in candidate_rows if str(row.get('code') or '').strip()]
    financial_map: Dict[str, Dict[str, Any]] = {}
    kline_map: Dict[str, List[Dict[str, Any]]] = {}

    if hasattr(db, 'acquire') and candidate_codes and (need_financials or need_klines):
        try:
            async with db.acquire() as conn:
                if need_financials:
                    financial_map = await _fetch_latest_financial_map(conn, candidate_codes)
                if need_klines:
                    kline_map = await _fetch_kline_batch(conn, candidate_codes, kline_limit)
        except Exception:
            financial_map = {}
            kline_map = {}

    if need_financials:
        missing_financial_codes = [code for code in candidate_codes if code not in financial_map]
        if missing_financial_codes:
            async def _load_financial(code: str):
                try:
                    rows = await db.get_financials(code, limit=1)
                    return code, (rows[0] if rows else None)
                except Exception:
                    return code, None

            for code, payload in await asyncio.gather(*[_load_financial(code) for code in missing_financial_codes]):
                if payload:
                    financial_map[code] = dict(payload)

    if need_klines:
        missing_kline_codes = [code for code in candidate_codes if code not in kline_map]
        if missing_kline_codes:
            async def _load_klines(code: str):
                try:
                    rows = await db.get_klines(code, limit=kline_limit)
                    return code, rows if rows and len(rows) >= min(20, kline_limit) else None
                except Exception:
                    return code, None

            for code, payload in await asyncio.gather(*[_load_klines(code) for code in missing_kline_codes]):
                if payload:
                    kline_map[code] = payload

    return financial_map, kline_map


async def _fill_missing_candidate_stock_info(db, candidate_rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    missing_codes = [
        str(row.get('code') or '').strip()
        for row in candidate_rows
        if str(row.get('code') or '').strip() and (row.get('pe_ratio') is None or row.get('pb_ratio') is None or not row.get('industry'))
    ]
    if not missing_codes:
        return {}

    async def _load(code: str):
        try:
            return code, (await db.get_stock_info(code) or {})
        except Exception:
            return code, {}

    filled: Dict[str, Dict[str, Any]] = {}
    for code, payload in await asyncio.gather(*[_load(code) for code in list(dict.fromkeys(missing_codes))]):
        if payload:
            filled[code] = dict(payload)
    return filled


def _extract_technical_features(klines: List[Dict[str, Any]]) -> Dict[str, float]:
    if not klines or len(klines) < 20:
        return {}
    closes = [float(k['close']) for k in klines if k.get('close') is not None]
    if len(closes) < 20:
        return {}
    recent_closes = closes[-20:]
    features: Dict[str, float] = {
        'momentum': factor_calculator.calculate_momentum(recent_closes),
        'volatility': factor_calculator.calculate_volatility(recent_closes),
    }
    ma20 = technical_analysis.calculate_sma(closes, 20)
    if ma20 and len(ma20) > 0 and ma20[-1]:
        features['trend'] = (closes[-1] - ma20[-1]) / ma20[-1]
    return features


def _build_target_features(
    target_info: Dict[str, Any],
    financial_row: Optional[Dict[str, Any]],
    target_klines: Optional[List[Dict[str, Any]]],
    similarity_type: str,
) -> Dict[str, float]:
    target_features: Dict[str, float] = {}
    if similarity_type in ['fundamental', 'both']:
        if financial_row:
            target_features['roe'] = financial_row.get('roe', 0)
            target_features['debt_ratio'] = financial_row.get('debt_ratio', 0)
            target_features['revenue_growth'] = financial_row.get('revenue_growth', 0)
        target_features['pe'] = target_info.get('pe_ratio', 0)
        target_features['pb'] = target_info.get('pb_ratio', 0)
    if similarity_type in ['technical', 'both']:
        target_features.update(_extract_technical_features(target_klines or []))
    return target_features


def _build_candidate_features(
    candidate_row: Dict[str, Any],
    filled_info: Optional[Dict[str, Any]],
    financial_row: Optional[Dict[str, Any]],
    klines: Optional[List[Dict[str, Any]]],
    similarity_type: str,
) -> Dict[str, float]:
    features: Dict[str, float] = {}
    info = dict(candidate_row or {})
    info.update({k: v for k, v in dict(filled_info or {}).items() if v is not None})
    if similarity_type in ['fundamental', 'both']:
        if financial_row:
            features['roe'] = financial_row.get('roe', 0)
            features['debt_ratio'] = financial_row.get('debt_ratio', 0)
            features['revenue_growth'] = financial_row.get('revenue_growth', 0)
        features['pe'] = info.get('pe_ratio', 0)
        features['pb'] = info.get('pb_ratio', 0)
    if similarity_type in ['technical', 'both']:
        features.update(_extract_technical_features(klines or []))
    return features


def _compute_feature_scales(target_features: Dict[str, float], candidate_payloads: List[Dict[str, Any]]) -> Dict[str, float]:
    scales: Dict[str, float] = {}
    feature_names = set(target_features.keys())
    for payload in candidate_payloads:
        feature_names.update(dict(payload.get('features') or {}).keys())

    for feature in feature_names:
        values = []
        if feature in target_features:
            values.append(float(target_features[feature] or 0))
        for payload in candidate_payloads:
            features = dict(payload.get('features') or {})
            if feature in features:
                values.append(float(features[feature] or 0))
        if not values:
            continue
        try:
            scale = statistics.pstdev(values) if len(values) > 1 else 0.0
        except statistics.StatisticsError:
            scale = 0.0
        if scale <= 1e-9:
            span = max(values) - min(values) if len(values) > 1 else 0.0
            scale = span if span > 1e-9 else max(max(abs(value) for value in values), 1.0)
        scales[feature] = float(scale or 1.0)
    return scales


def _normalize_kline_vector(values: List[float]) -> List[float]:
    resolved = [float(item) for item in list(values or [])]
    if not resolved:
        return []
    norm = math.sqrt(sum(item * item for item in resolved))
    if norm <= 0:
        return resolved
    return [item / norm for item in resolved]


def _coerce_date_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, date) and not isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, datetime):
        return value.date().isoformat()
    text = str(value or "").strip()
    return text[:10] if text else ""


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
            target_financial_row = None
            target_klines = None
            if similarity_type in ['fundamental', 'both']:
                try:
                    financials = await db.get_financials(code, limit=1)
                    if financials:
                        target_financial_row = financials[0]
                except Exception:
                    pass
            if similarity_type in ['technical', 'both']:
                try:
                    target_klines = await db.get_klines(code, limit=60)
                except Exception:
                    target_klines = None

            target_features = _build_target_features(
                dict(target_info or {}),
                target_financial_row,
                target_klines,
                similarity_type,
            )
            
            if not target_features:
                return fail('Cannot extract features from target stock')
            
            # 3. 查找候选股票：优先同行业，无同行或行业为空时回退全市场样本
            candidate_scope, candidate_rows = await _load_candidate_stock_rows(db, code, target_industry, limit=100)
            candidate_rows = candidate_rows[:50]
            candidate_codes = [row['code'] for row in candidate_rows if row.get('code')]
            candidate_names = {row['code']: row.get('stock_name', '') for row in candidate_rows if row.get('code')}
            
            if not candidate_codes:
                return fail('No candidate stocks found')

            filled_stock_info = await _fill_missing_candidate_stock_info(db, candidate_rows)
            financial_map, kline_map = await _prefetch_candidate_context(
                db,
                candidate_rows,
                need_financials=similarity_type in ['fundamental', 'both'],
                need_klines=similarity_type in ['technical', 'both'],
                kline_limit=60,
            )
            
            # 4. 计算相似度
            candidate_payloads = []
            for candidate_row in candidate_rows:
                candidate_code = str(candidate_row.get('code') or '').strip()
                if not candidate_code:
                    continue
                candidate_features = _build_candidate_features(
                    candidate_row,
                    filled_stock_info.get(candidate_code),
                    financial_map.get(candidate_code),
                    kline_map.get(candidate_code),
                    similarity_type,
                )
                if not candidate_features:
                    continue
                candidate_payloads.append({
                    'code': candidate_code,
                    'name': candidate_names.get(candidate_code, ''),
                    'features': candidate_features,
                })

            feature_scales = _compute_feature_scales(target_features, candidate_payloads)
            similarities = []
            for payload in candidate_payloads:
                candidate_features = dict(payload.get('features') or {})
                common_features = set(target_features.keys()) & set(candidate_features.keys())
                if not common_features:
                    continue
                distances = [
                    abs(float(target_features[feature] or 0) - float(candidate_features[feature] or 0))
                    / max(float(feature_scales.get(feature) or 1.0), 1e-6)
                    for feature in common_features
                ]
                if not distances:
                    continue
                avg_distance = statistics.mean(distances)
                similarity = 1 / (1 + avg_distance)
                similarities.append({
                    'code': payload['code'],
                    'name': payload['name'],
                    'similarity': round(similarity, 4),
                    'features': candidate_features,
                })
            
            # 5. 排序并返回
            similarities.sort(key=lambda x: x['similarity'], reverse=True)
            
            return ok({
                'code': code,
                'name': target_info.get('name') or target_info.get('stock_name', ''),
                'industry': target_industry,
                'candidate_scope': candidate_scope,
                'similar_stocks': similarities[:top_n],
                'similarity_type': similarity_type,
                'total_candidates': len(candidate_rows),
                'calculated': len(similarities)
            })
        
        except Exception as e:
            return fail(str(e))
    
    @mcp.tool()
    async def search_by_kline(
        code: str,
        days: int = 20,
        top_n: int = 10,
        search_backend: str = 'db',
        allow_fallback: bool = True,
    ):
        """
        基于K线形态搜索相似股票 - 使用向量搜索引擎。

        Args:
            code: 股票代码
            days: K线天数
            top_n: 返回数量
            search_backend: 检索后端（db/python/index）
            allow_fallback: 检索失败时是否回退 python
        """
        try:
            db = get_db()
            backend_requested = str(search_backend or 'db').strip().lower()
            if backend_requested in {'pgvector', 'timescaledb'}:
                backend_requested = 'db'
            if backend_requested not in {'db', 'python', 'index'}:
                backend_requested = 'python'
            fallback_reason = None

            # 1. 获取目标股票K线
            target_lookback = max(int(days) * 4, 60)
            target_klines = await db.get_klines(code, limit=target_lookback)
            if not target_klines or len(target_klines) < days:
                return fail(f'Insufficient kline data for {code}')
            target_klines = list(target_klines)[-int(days):]

            # 2. 获取目标股票信息
            target_info = await db.get_stock_info(code)
            target_industry = target_info.get('industry', '') if target_info else ''

            # 3. 查找候选股票
            _, candidate_rows = await _load_candidate_stock_rows(db, code, target_industry, limit=100)
            candidate_rows = candidate_rows[:50]
            candidates = {row['code']: row.get('stock_name', '') for row in candidate_rows if row.get('code')}
            if not candidates:
                return fail('No candidate stocks found')

            search_meta = {
                'backend_requested': backend_requested,
                'backend_used': backend_requested,
                'fallback_used': False,
                'fallback_reason': None,
                'latency_ms': 0.0,
            }
            results = []
            candidate_klines_loaded = 0

            if backend_requested == 'db':
                try:
                    query_vector = vector_search_engine.kline_to_vector(target_klines, method='returns')
                    query_vector_values = _normalize_kline_vector(query_vector.tolist() if hasattr(query_vector, 'tolist') else query_vector)
                    if query_vector_values and hasattr(db, 'search_kline_pattern_windows'):
                        db_rows = await db.search_kline_pattern_windows(
                            query_embedding=query_vector_values,
                            window_size=int(days),
                            vector_method='returns',
                            period='daily',
                            adjust='',
                            stock_codes=list(candidates.keys()),
                            exclude_stock_code=code,
                            limit=max(int(top_n) * 5, 20),
                        )
                        if db_rows:
                            results = [
                                {
                                    'code': str(item.get('stock_code') or ''),
                                    'name': item.get('stock_name') or candidates.get(str(item.get('stock_code') or ''), ''),
                                    'similarity': round(float(item.get('similarity') or 0.0), 4),
                                    'source': 'db',
                                    'end_date': _coerce_date_str(item.get('end_date')),
                                    'start_date': _coerce_date_str(item.get('start_date')),
                                    'forward_return_5d': item.get('forward_return_5d'),
                                    'forward_return_10d': item.get('forward_return_10d'),
                                    'forward_return_20d': item.get('forward_return_20d'),
                                }
                                for item in db_rows[:int(top_n)]
                                if str(item.get('stock_code') or '')
                            ]
                            candidate_klines_loaded = len(db_rows)
                            search_meta = {
                                'backend_requested': 'db',
                                'backend_used': 'db',
                                'fallback_used': False,
                                'fallback_reason': None,
                                'latency_ms': 0.0,
                            }
                        else:
                            fallback_reason = 'db_empty_result'
                    else:
                        fallback_reason = 'db_backend_unsupported'
                except Exception as exc:
                    fallback_reason = f'db_exception:{type(exc).__name__}'

                if results:
                    return ok({
                        'code': code,
                        'name': (target_info.get('name') or target_info.get('stock_name', '')) if target_info else '',
                        'days': days,
                        'results': results,
                        'total_candidates': len(candidates),
                        'candidate_klines_loaded': candidate_klines_loaded,
                        'calculated': len(results),
                        'search_backend': backend_requested,
                        'actual_backend': search_meta.get('backend_used', 'db'),
                        'allow_fallback': bool(allow_fallback),
                        'backend_requested': search_meta.get('backend_requested', 'db'),
                        'backend_used': search_meta.get('backend_used', 'db'),
                        'fallback_used': bool(search_meta.get('fallback_used', False)),
                        'fallback_reason': search_meta.get('fallback_reason'),
                        'latency_ms': search_meta.get('latency_ms', 0.0),
                    })

                if not allow_fallback:
                    return ok({
                        'code': code,
                        'name': (target_info.get('name') or target_info.get('stock_name', '')) if target_info else '',
                        'days': days,
                        'results': [],
                        'total_candidates': len(candidates),
                        'candidate_klines_loaded': 0,
                        'calculated': 0,
                        'search_backend': backend_requested,
                        'actual_backend': 'db',
                        'allow_fallback': bool(allow_fallback),
                        'backend_requested': 'db',
                        'backend_used': 'db',
                        'fallback_used': False,
                        'fallback_reason': fallback_reason or 'db_empty_result',
                        'latency_ms': 0.0,
                    })

            # 4. 获取候选K线并执行向量检索
            _, candidate_klines_dict = await _prefetch_candidate_context(
                db,
                candidate_rows,
                need_financials=False,
                need_klines=True,
                kline_limit=days,
            )
            candidate_klines_dict = {
                candidate_code: rows
                for candidate_code, rows in candidate_klines_dict.items()
                if rows and len(rows) >= days
            }

            if not candidate_klines_dict:
                return fail('No candidate kline data available')

            engine_backend = backend_requested if backend_requested in {'python', 'index'} else 'python'
            search_results = vector_search_engine.find_similar_patterns(
                query_klines=target_klines,
                candidate_klines_dict=candidate_klines_dict,
                top_k=top_n,
                method='returns',
                metric='correlation',
                backend=engine_backend,
                allow_fallback=allow_fallback,
            )
            search_meta = dict(getattr(vector_search_engine, 'last_meta', {}) or {})
            if backend_requested == 'db':
                search_meta['backend_requested'] = 'db'
                search_meta['fallback_used'] = True
                search_meta['fallback_reason'] = fallback_reason or search_meta.get('fallback_reason') or 'db_empty_result'

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
            candidate_klines_loaded = len(candidate_klines_dict)

            return ok({
                'code': code,
                'name': (target_info.get('name') or target_info.get('stock_name', '')) if target_info else '',
                'days': days,
                'results': results,
                'total_candidates': len(candidates),
                'candidate_klines_loaded': candidate_klines_loaded,
                'calculated': len(results),
                'search_backend': backend_requested,
                'actual_backend': vector_search_engine.last_backend_used,
                'allow_fallback': bool(allow_fallback),
                'backend_requested': search_meta.get('backend_requested', backend_requested),
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

            # 检测财务指标条件表达式，如 "ROE>10"、"PE<20"、"净利润增速>15%"
            import re as _re_fin
            _FIN_METRIC_PATTERN = _re_fin.compile(
                r'(roe|pe|pb|eps|市盈率|市净率|净利润|营收|增速|负债率|股息率|市值|换手率)'
                r'\s*[><=!<>]{1,2}\s*[\d.]+',
                _re_fin.IGNORECASE,
            )
            if _FIN_METRIC_PATTERN.search(query_stripped):
                return ok({
                    'query': query_stripped,
                    'results': [],
                    'count': 0,
                    'hint': (
                        '检测到财务指标筛选条件（如 ROE>10、PE<20）。'
                        '本工具仅支持按股票代码、名称、行业关键词搜索；'
                        '财务条件筛选请使用 parse_selection_query 工具。'
                    ),
                    'suggestion': 'parse_selection_query',
                })

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
                        from .market_blocks import _fetch_concept_stocks_from_ths

                        q_lower = match_text.lower()
                        strong_sector_tokens = [
                            token.lower()
                            for token in sector_tokens
                            if len(token) >= 2 and token not in _GENERIC_SEMANTIC_HINTS
                        ]

                        def _sector_match(name: str) -> bool:
                            name_l = name.lower()
                            if q_lower in name_l or name_l in q_lower:
                                return True
                            return any(token in name_l for token in strong_sector_tokens)

                        matched_sectors = []
                        seen_sector_keys = set()
                        candidate_limit = min(max(limit * 5, 50), 120)

                        def _append_sector(label: str, name: str):
                            label_s = str(label or '').strip()
                            name_s = str(name or '').strip()
                            if not label_s or not name_s:
                                return
                            key = (label_s, name_s)
                            if key in seen_sector_keys:
                                return
                            seen_sector_keys.add(key)
                            matched_sectors.append((label_s, name_s))

                        with suppress_stdout("[semantic_stock_search] stock_sector_spot"):
                            df_spot = ak_mod.stock_sector_spot()
                        if df_spot is not None and not df_spot.empty:
                            for _, srow in df_spot.iterrows():
                                bname = str(srow.get('板块', '') or '')
                                blabel = str(srow.get('label', '') or '')
                                if _sector_match(bname):
                                    _append_sector(blabel, bname)
                        if len(matched_sectors) < 2:
                            with suppress_stdout("[semantic_stock_search] stock_board_industry_name_ths"):
                                df_ths = ak_mod.stock_board_industry_name_ths()
                            if df_ths is not None and not df_ths.empty:
                                for _, brow in df_ths.iterrows():
                                    bname = str(brow.get('name', '') or '')
                                    bcode = str(brow.get('code', '') or '')
                                    if _sector_match(bname):
                                        _append_sector(bcode, bname)
                        if len(matched_sectors) < 3:
                            with suppress_stdout("[semantic_stock_search] stock_board_concept_name_ths"):
                                df_concept_ths = ak_mod.stock_board_concept_name_ths()
                            if df_concept_ths is not None and not df_concept_ths.empty:
                                for _, crow in df_concept_ths.iterrows():
                                    bname = str(crow.get('name', '') or '')
                                    bcode = str(crow.get('code', '') or '')
                                    if _sector_match(bname):
                                        _append_sector(bcode, bname)
                        for blabel, bname in matched_sectors[:3]:
                            try:
                                if not blabel.startswith('new_'):
                                    if blabel.isdigit() and len(blabel) == 6:
                                        with suppress_stdout("[semantic_stock_search] ths_concept_constituents"):
                                            concept_rows = _fetch_concept_stocks_from_ths(blabel, bname)
                                        for item in concept_rows[:candidate_limit]:
                                            _append_row({
                                                'code': str(item.get('stock_code', '') or ''),
                                                'name': str(item.get('stock_name', '') or ''),
                                                'industry': bname,
                                                'market_cap': None,
                                                'pe_ratio': None,
                                                'pb_ratio': None,
                                            })
                                    continue
                                with suppress_stdout("[semantic_stock_search] stock_sector_detail"):
                                    df_cons = ak_mod.stock_sector_detail(sector=blabel)
                                if df_cons is None or df_cons.empty:
                                    continue
                                for _, crow in df_cons.head(candidate_limit).iterrows():
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

                # 用 stocks 主表补齐市值/估值字段，帮助行业结果按龙头优先排序。
                missing_detail_codes = [
                    row['code']
                    for row in all_rows
                    if row.get('market_cap') is None or row.get('pe_ratio') is None or row.get('pb_ratio') is None
                ]
                if missing_detail_codes:
                    detail_rows = await conn.fetch(
                        """SELECT code, market_cap, pe_ratio, pb_ratio
                           FROM stocks
                           WHERE code = ANY($1::text[])""",
                        list(dict.fromkeys(missing_detail_codes))
                    )
                    detail_map = {str(row['code']): dict(row) for row in detail_rows}
                    for row in all_rows:
                        detail = detail_map.get(str(row.get('code') or ''))
                        if not detail:
                            continue
                        if row.get('market_cap') is None:
                            row['market_cap'] = detail.get('market_cap')
                        if row.get('pe_ratio') is None:
                            row['pe_ratio'] = detail.get('pe_ratio')
                        if row.get('pb_ratio') is None:
                            row['pb_ratio'] = detail.get('pb_ratio')

                # 计算匹配分数
                results = []
                query_explicitly_conceptual = any(hint in query_stripped for hint in _SEMANTIC_CONCEPT_HINTS)
                for row in all_rows:
                    score = 0.0
                    match_type = []
                    code_l = (row['code'] or '').lower()
                    name_l = (row['stock_name'] or '').lower()
                    industry_l = (row['industry'] or '').lower()
                    q_l = query_stripped.lower()
                    is_st = _semantic_is_special_treatment(row.get('stock_name'))
                    is_concept = _semantic_is_concept_industry(row.get('industry'))
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
                        if is_concept and not query_explicitly_conceptual:
                            score += 0.6; match_type.append('industry_concept')
                        else:
                            score += 0.85; match_type.append('industry')
                        if generic_tokens:
                            score += 0.2; match_type.append('industry_context')
                    elif industry_l and matched_industry_tokens:
                        score += 0.45; match_type.append('industry_hint')
                    if is_concept and not query_explicitly_conceptual:
                        score -= 0.1; match_type.append('concept_penalty')
                    if is_st:
                        score -= 0.9; match_type.append('special_treatment_penalty')
                    if score == 0:
                        continue
                    if score < _MIN_SEMANTIC_SCORE and not {'code_exact', 'code_partial', 'name_exact'} & set(match_type):
                        continue

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

                results.sort(
                    key=lambda x: (
                        x['score'],
                        x['market_cap'] if x.get('market_cap') is not None else float('-inf'),
                    ),
                    reverse=True,
                )

                final_results = results[:limit]
                response_payload = {
                    'query': query_stripped,
                    'results': final_results,
                    'count': len(final_results),
                }
                if not final_results:
                    response_payload['hint'] = (
                        f'未找到与"{query_stripped}"匹配的股票。'
                        '建议尝试：行业名称（如"白酒"、"新能源"）、股票名称或代码；'
                        '若要按财务指标筛选请使用 parse_selection_query 工具。'
                    )
                return ok(response_payload)

        except Exception as e:
            return fail(str(e))
