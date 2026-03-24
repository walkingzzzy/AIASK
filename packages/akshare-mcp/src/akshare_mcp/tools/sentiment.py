"""情绪分析与用户画像工具"""

import asyncio
import math
from datetime import date, datetime, timedelta, timezone
from typing import Any

from ..services.document_index import build_document_index
from ..services.event_extraction import extract_events
from ..services.sentiment import sentiment_analyzer
from ..storage import get_db
from ..utils import ok, fail, resolve_security_code


def _to_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _round_or_none(value: Any, digits: int = 2) -> float | None:
    num = _to_float(value)
    return round(num, digits) if num is not None else None


def _pct_change(data: list[float], days: int) -> float | None:
    if len(data) <= days:
        return None
    base = float(data[-1 - days])
    if base <= 0:
        return None
    return round((float(data[-1]) - base) / base * 100, 2)


async def _load_db_northbound_context(db, *, days: int) -> dict[str, Any] | None:
    getter = getattr(db, 'get_recent_north_fund_summary', None)
    if not callable(getter):
        return None
    payload = getter(days=max(1, int(days)), sample_limit=max(5, int(days)))
    if hasattr(payload, "__await__"):
        payload = await payload
    if not isinstance(payload, dict) or int(payload.get('sample_count') or 0) <= 0:
        return None
    recent_series = list(payload.get('series') or [])
    northbound = {
        'northbound_flow_1d': _round_or_none(recent_series[0].get('north_money'), 2) if recent_series else None,
        'northbound_flow_3d': _round_or_none(payload.get('total_net'), 2),
        'northbound_flow_5d': _round_or_none(
            sum(float(item.get('north_money') or 0.0) for item in recent_series[:5]),
            2,
        ) if recent_series else None,
        'source': payload.get('source') or 'north_fund_flow',
        'stale': bool(payload.get('stale', False)),
        'stale_age_days': payload.get('stale_age_days'),
        'latest_trade_date': payload.get('latest_trade_date'),
        'recent_items': recent_series[:5],
    }
    return northbound


async def _load_db_margin_context(db, *, days: int) -> dict[str, Any] | None:
    getter = getattr(db, 'get_recent_margin_summary', None)
    if not callable(getter):
        return None
    payload = getter(days=max(6, int(days)), sample_limit=max(6, int(days)), change_lookback_days=5)
    if hasattr(payload, "__await__"):
        payload = await payload
    if not isinstance(payload, dict) or int(payload.get('sample_count') or 0) <= 0:
        return None
    return {
        'margin_balance_latest': _round_or_none(payload.get('margin_balance_latest'), 2),
        'margin_buy_latest': _round_or_none(payload.get('margin_buy_latest'), 2),
        'margin_balance_change_5d': _round_or_none(payload.get('margin_balance_change_5d'), 2),
        'recent_rows': list(payload.get('recent_rows') or [])[:5],
        'source': payload.get('source') or 'margin_market_flow',
        'stale': bool(payload.get('stale', False)),
        'stale_age_days': payload.get('stale_age_days'),
        'latest_trade_date': payload.get('latest_trade_date'),
    }


def _pick_text(item: dict[str, Any]) -> str:
    for key in ('text', 'content', 'summary', 'title', 'headline'):
        value = item.get(key)
        if value:
            return str(value).strip()
    return ''


def _detect_event_tags(texts: list[str]) -> list[dict[str, Any]]:
    tag_rules = {
        '业绩景气': ['业绩', '增长', '盈利', '预增', '扭亏', '超预期'],
        '订单合同': ['中标', '签约', '订单', '合同'],
        '资本运作': ['回购', '增持', '减持', '定增', '融资'],
        '产品技术': ['突破', '创新', '发布', '获批', '研发'],
        '监管风险': ['处罚', '违规', '诉讼', '质押', 'ST', '退市', '风险'],
    }
    counts: dict[str, int] = {key: 0 for key in tag_rules}
    for text in texts:
        content = str(text or '')
        for tag, keywords in tag_rules.items():
            if any(keyword in content for keyword in keywords):
                counts[tag] += 1
    ranked = [
        {'tag': tag, 'count': count}
        for tag, count in sorted(counts.items(), key=lambda x: x[1], reverse=True)
        if count > 0
    ]
    return ranked[:8]

def register(mcp):
    @mcp.tool()
    async def analyze_stock_sentiment(
        code: str | None = None,
        stock_code: str | None = None,
        symbol: str | None = None,
        ticker: str | None = None,
    ):
        """分析个股市场情绪（三分量复合评分：价量动量+新闻情绪+资金流向）"""
        try:
            code = resolve_security_code(code, stock_code=stock_code, symbol=symbol, ticker=ticker)
            if not code:
                return fail('需要提供股票代码（支持 code / stock_code / symbol / ticker）')
            db = get_db()
            klines = await db.get_klines(code, limit=100)

            if not klines:
                return fail('No data')

            # Best-effort: fetch news headlines
            news_headlines = []
            try:
                async with db.acquire() as conn:
                    rows = await conn.fetch(
                        """
                        SELECT chunk_text AS content
                        FROM market_doc_chunks
                        WHERE stock_code = $1 AND LOWER(COALESCE(doc_type, '')) = 'news'
                        ORDER BY published_at DESC NULLS LAST, id DESC
                        LIMIT 20
                        """,
                        code,
                    )
                    news_headlines = [r['content'][:200] for r in rows if r.get('content')]
                    if not news_headlines:
                        rows = await conn.fetch(
                            "SELECT content FROM vector_documents WHERE stock_code = $1 AND doc_type = 'news' ORDER BY date DESC LIMIT 20",
                            code,
                        )
                        news_headlines = [r['content'][:200] for r in rows if r.get('content')]
            except Exception:
                pass

            # Best-effort: fetch fund flow data
            fund_flow_data = None
            try:
                async with db.acquire() as conn:
                    row = await conn.fetchrow(
                        "SELECT * FROM stock_fund_flow WHERE code = $1 ORDER BY trade_date DESC LIMIT 1",
                        code,
                    )
                    if row:
                        fund_flow_data = dict(row)
            except Exception:
                pass

            result = sentiment_analyzer.analyze_sentiment(klines, news_headlines, fund_flow_data)
            result['code'] = code

            return ok(result)
        except Exception as e:
            return fail(str(e))

    @mcp.tool()
    async def calculate_fear_greed_index():
        """计算市场恐惧贪婪指数（基于上证指数K线和涨跌停统计）"""
        try:
            db = get_db()
            index_klines = await db.get_klines('sh000001', limit=60)
            breadth_data = None
            try:
                limit_up = await db.get_limit_up_stats()
                if limit_up:
                    breadth_data = limit_up
            except Exception:
                pass
            result = sentiment_analyzer.calculate_fear_greed_index(
                index_klines=index_klines or None,
                breadth_data=breadth_data,
            )
            return ok(result)
        except Exception as e:
            return fail(str(e))

    @mcp.tool()
    async def get_market_sentiment_context(
        north_days: int = 5,
        margin_days: int = 10,
        top_sector_n: int = 5,
    ):
        """获取市场级情绪上下文，聚合恐贪、北向资金、融资余额与板块热度。"""
        try:
            from .fund_flow import get_margin_data, get_north_fund, get_sector_fund_flow

            db = get_db()
            warnings: list[str] = []

            index_klines = await db.get_klines('sh000001', limit=60)
            breadth_data = None
            try:
                breadth_data = await db.get_limit_up_stats()
            except Exception as exc:
                warnings.append(f"breadth:{exc}")

            fear_greed = sentiment_analyzer.calculate_fear_greed_index(
                index_klines=index_klines or None,
                breadth_data=breadth_data,
            )

            closes = [float(k.get('close', 0) or 0) for k in (index_klines or []) if isinstance(k, dict)]
            valid_closes = [x for x in closes if x > 0]
            index_context = {
                'code': 'sh000001',
                'close': _round_or_none(valid_closes[-1], 2) if valid_closes else None,
                'change_5d_pct': _pct_change(valid_closes, 5) if len(valid_closes) >= 6 else None,
                'change_20d_pct': _pct_change(valid_closes, 20) if len(valid_closes) >= 21 else None,
            }

            northbound = {
                'northbound_flow_1d': None,
                'northbound_flow_3d': None,
                'northbound_flow_5d': None,
                'source': None,
                'stale': False,
                'stale_age_days': None,
                'latest_trade_date': None,
                'recent_items': [],
            }
            try:
                db_northbound = await _load_db_northbound_context(db, days=max(1, int(north_days)))
                if db_northbound is not None:
                    northbound.update(db_northbound)
                else:
                    nf = await asyncio.to_thread(get_north_fund, max(1, int(north_days)))
                    if nf.get('success'):
                        payload = nf.get('data', {}) or {}
                        items = payload.get('items', []) if isinstance(payload, dict) else []
                        recent_items = items[-max(1, int(north_days)):] if items else []
                        northbound.update({
                            'northbound_flow_1d': _round_or_none(recent_items[-1].get('total'), 2) if recent_items else None,
                            'northbound_flow_3d': _round_or_none(sum(float(x.get('total') or 0) for x in recent_items[-3:]), 2) if recent_items else None,
                            'northbound_flow_5d': _round_or_none(sum(float(x.get('total') or 0) for x in recent_items[-5:]), 2) if recent_items else None,
                            'source': payload.get('source'),
                            'stale': bool(payload.get('stale', False)),
                            'stale_age_days': payload.get('stale_age_days'),
                            'latest_trade_date': payload.get('latest_trade_date'),
                            'recent_items': recent_items[-5:],
                        })
                    else:
                        warnings.append(f"north_fund:{nf.get('error', 'unknown')}")
            except Exception as exc:
                warnings.append(f"north_fund:{exc}")

            margin_context = {
                'margin_balance_latest': None,
                'margin_buy_latest': None,
                'margin_balance_change_5d': None,
                'source': None,
                'stale': False,
                'stale_age_days': None,
                'latest_trade_date': None,
                'recent_rows': [],
            }
            try:
                db_margin = await _load_db_margin_context(db, days=max(6, int(margin_days)))
                if db_margin is not None:
                    margin_context.update(db_margin)
                else:
                    mg = await asyncio.to_thread(get_margin_data, '', max(6, int(margin_days)))
                    if mg.get('success') and isinstance(mg.get('data'), list) and mg.get('data'):
                        rows = mg.get('data') or []
                        latest = rows[0]
                        older = rows[min(5, len(rows) - 1)]
                        recent_bal = float(latest.get('marginBalance') or 0)
                        older_bal = float(older.get('marginBalance') or 0)
                        margin_context.update({
                            'margin_balance_latest': _round_or_none(latest.get('marginBalance'), 2),
                            'margin_buy_latest': _round_or_none(latest.get('marginBuy'), 2),
                            'margin_balance_change_5d': round((recent_bal - older_bal) / older_bal * 100, 2) if older_bal > 0 else None,
                            'recent_rows': rows[:5],
                            'source': 'fund_flow_market',
                        })
                    else:
                        warnings.append(f"margin_data:{mg.get('error', 'unknown')}")
            except Exception as exc:
                warnings.append(f"margin_data:{exc}")

            sector_context = {
                'hot_sectors': [],
                'cold_sectors': [],
            }
            try:
                sf = await asyncio.to_thread(get_sector_fund_flow, max(10, int(top_sector_n) * 2))
                if sf.get('success') and isinstance(sf.get('data'), list):
                    sectors = list(sf.get('data') or [])
                    sectors = [s for s in sectors if isinstance(s, dict)]
                    sectors_sorted = sorted(sectors, key=lambda x: float(x.get('mainNetInflow') or 0), reverse=True)
                    top_n = max(1, int(top_sector_n))
                    sector_context['hot_sectors'] = sectors_sorted[:top_n]
                    sector_context['cold_sectors'] = list(reversed(sectors_sorted[-top_n:]))
                else:
                    warnings.append(f"sector_flow:{sf.get('error', 'unknown')}")
            except Exception as exc:
                warnings.append(f"sector_flow:{exc}")

            return ok({
                'fear_greed_index': fear_greed.get('index'),
                'fear_greed_level': fear_greed.get('level'),
                'fear_greed_components': fear_greed.get('components', {}),
                'index_context': index_context,
                'northbound_flow_1d': northbound['northbound_flow_1d'],
                'northbound_flow_3d': northbound['northbound_flow_3d'],
                'northbound_flow_5d': northbound['northbound_flow_5d'],
                'northbound_context': northbound,
                'margin_balance_latest': margin_context['margin_balance_latest'],
                'margin_buy_latest': margin_context['margin_buy_latest'],
                'margin_balance_change_5d': margin_context['margin_balance_change_5d'],
                'margin_context': margin_context,
                'hot_sectors': sector_context['hot_sectors'],
                'cold_sectors': sector_context['cold_sectors'],
                'breadth': breadth_data or {},
                'warnings': warnings,
                'source_chain': [
                    'sentiment.calculate_fear_greed_index',
                    'db.get_recent_north_fund_summary',
                    'db.get_recent_margin_summary',
                    'fund_flow.get_north_fund(fallback)',
                    'fund_flow.get_margin_data(fallback)',
                    'fund_flow.get_sector_fund_flow',
                ],
            })
        except Exception as e:
            return fail(str(e))

    @mcp.tool()
    async def get_stock_text_signals(
        code: str | None = None,
        news_limit: int = 20,
        notice_days: int = 30,
        report_limit: int = 10,
        stock_code: str | None = None,
        symbol: str | None = None,
        ticker: str | None = None,
    ):
        """聚合个股新闻/公告/研报原文，输出文本信号与事件标签。"""
        try:
            from ..services.llm_alpha import TextSignalPipeline
            from .news.news_feed import get_stock_news
            from .news.notices import get_stock_notices
            from .news.research import get_research_reports

            normalized_code = resolve_security_code(
                code,
                stock_code=stock_code,
                symbol=symbol,
                ticker=ticker,
            )
            if not normalized_code:
                return fail('需要提供股票代码（支持 code / stock_code / symbol / ticker）')

            warnings: list[str] = []
            news_items: list[dict[str, Any]] = []
            notice_items: list[dict[str, Any]] = []
            report_items: list[dict[str, Any]] = []

            news_resp = await asyncio.to_thread(get_stock_news, normalized_code, max(1, int(news_limit)))
            if news_resp.get('success') and isinstance(news_resp.get('data'), list):
                news_items = [dict(item) for item in (news_resp.get('data') or []) if isinstance(item, dict)]
            else:
                warnings.append(f"stock_news:{news_resp.get('error', 'unknown')}")

            end_date = date.today()
            start_date = end_date - timedelta(days=max(1, int(notice_days)))
            notice_resp = await asyncio.to_thread(
                get_stock_notices,
                start_date.isoformat(),
                end_date.isoformat(),
                ['全部'],
                normalized_code,
            )
            if notice_resp.get('success') and isinstance(notice_resp.get('data'), dict):
                notice_items = [
                    dict(item) for item in (notice_resp.get('data', {}).get('events') or []) if isinstance(item, dict)
                ]
            else:
                warnings.append(f"stock_notices:{notice_resp.get('error', 'unknown')}")

            report_resp = await asyncio.to_thread(get_research_reports, normalized_code, '', max(1, int(report_limit)))
            if report_resp.get('success'):
                report_data = report_resp.get('data')
                if isinstance(report_data, dict):
                    report_items = [dict(item) for item in (report_data.get('reports') or []) if isinstance(item, dict)]
                elif isinstance(report_data, list):
                    report_items = [dict(item) for item in report_data if isinstance(item, dict)]
            else:
                warnings.append(f"research_reports:{report_resp.get('error', 'unknown')}")

            merged_items: list[dict[str, Any]] = []
            for item in news_items[: max(1, int(news_limit))]:
                merged_items.append({
                    'type': 'news',
                    'date': item.get('date'),
                    'title': item.get('title') or item.get('headline') or '',
                    'source': item.get('source') or 'stock_news',
                    'text': _pick_text(item),
                })
            for item in notice_items[: max(3, int(news_limit))]:
                merged_items.append({
                    'type': 'notice',
                    'date': item.get('date'),
                    'title': item.get('title') or item.get('name') or '',
                    'source': item.get('source') or 'stock_notices',
                    'text': _pick_text(item),
                })
            for item in report_items[: max(1, int(report_limit))]:
                report_text = ' '.join(
                    str(x).strip() for x in [item.get('title'), item.get('rating'), item.get('institution')] if x
                ).strip()
                merged_items.append({
                    'type': 'research',
                    'date': item.get('date'),
                    'title': item.get('title') or '',
                    'source': item.get('institution') or 'research_reports',
                    'text': report_text,
                    'rating': item.get('rating'),
                    'target_price': item.get('targetPrice'),
                })

            document_index = build_document_index(merged_items)
            documents = document_index.get('documents', [])
            texts = [item['text'] for item in documents if item.get('text')]
            text_signal = TextSignalPipeline.aggregate_signals(texts)
            extraction = extract_events(documents)
            event_tags = extraction.get('event_tags', [])

            rating_counts: dict[str, int] = {}
            target_prices = []
            for item in report_items:
                rating = str(item.get('rating') or '').strip()
                if rating:
                    rating_counts[rating] = rating_counts.get(rating, 0) + 1
                tp = _to_float(item.get('targetPrice'))
                if tp is not None and tp > 0:
                    target_prices.append(tp)

            return ok({
                'code': normalized_code,
                'signal_score': text_signal.get('signal_score', 0.0),
                'sentiment': text_signal.get('sentiment', 'neutral'),
                'positive_count': text_signal.get('positive_count', 0),
                'negative_count': text_signal.get('negative_count', 0),
                'evidence': text_signal.get('evidence', []),
                'event_tags': event_tags,
                'event_summary': extraction.get('summary_counts', {}),
                'entities': extraction.get('entities', {}),
                'keyword_hits': extraction.get('keyword_hits', {}),
                'source_counts': {
                    'news': len(news_items),
                    'notices': len(notice_items),
                    'research_reports': len(report_items),
                    'total_texts': len(texts),
                },
                'document_index': document_index.get('stats', {}),
                'rating_summary': {
                    'counts': rating_counts,
                    'avg_target_price': _round_or_none(sum(target_prices) / len(target_prices), 2) if target_prices else None,
                },
                'raw_texts': documents[: max(int(news_limit) + int(report_limit), 10)],
                'warnings': warnings,
                'source_chain': [
                    'news.get_stock_news',
                    'news.get_stock_notices',
                    'news.get_research_reports',
                    'services.llm_alpha.TextSignalPipeline',
                    'services.document_index',
                    'services.event_extraction',
                ],
            })
        except Exception as e:
            return fail(str(e))

    @mcp.tool()
    async def update_user_profile(
        user_id: str = 'default',
        neuroticism: float = 0.5,
        openness: float = 0.5,
        herd_tendency: float = 0.5,
        greed_fear_axis: float = 0.0,
        confidence: float = 0.5,
    ):
        """更新用户投资者画像快照（AI推断的大五人格维度）

        Args:
            user_id: 用户ID
            neuroticism: 神经质程度 0~1
            openness: 开放性 0~1
            herd_tendency: 从众倾向 0~1
            greed_fear_axis: 贪婪恐惧轴 -1~1
            confidence: 置信度 0~1
        """
        try:
            db = get_db()
            async with db.acquire() as conn:
                await conn.execute(
                    """INSERT INTO user_profile_snapshots
                       (user_id, neuroticism, openness, herd_tendency, greed_fear_axis, confidence, source)
                       VALUES ($1, $2, $3, $4, $5, $6, 'ai_inference')""",
                    user_id,
                    max(0.0, min(1.0, neuroticism)),
                    max(0.0, min(1.0, openness)),
                    max(0.0, min(1.0, herd_tendency)),
                    max(-1.0, min(1.0, greed_fear_axis)),
                    max(0.0, min(1.0, confidence)),
                )
            return ok({'user_id': user_id, 'recorded': True})
        except Exception as e:
            return fail(str(e))

    @mcp.tool()
    async def get_user_profile(user_id: str = 'default'):
        """获取用户投资者画像（指数衰减加权平均，半衰期7天）

        Args:
            user_id: 用户ID
        """
        try:
            db = get_db()
            async with db.acquire() as conn:
                rows = await conn.fetch(
                    """SELECT neuroticism, openness, herd_tendency, greed_fear_axis, confidence, created_at
                       FROM user_profile_snapshots
                       WHERE user_id = $1
                       ORDER BY created_at DESC
                       LIMIT 50""",
                    user_id,
                )
            if not rows:
                return ok({'user_id': user_id, 'profile': None, 'message': 'No profile data'})

            now = datetime.now(timezone.utc)
            half_life_days = 7.0
            decay_rate = math.log(2) / half_life_days

            total_weight = 0.0
            weighted = {'neuroticism': 0.0, 'openness': 0.0, 'herd_tendency': 0.0, 'greed_fear_axis': 0.0, 'confidence': 0.0}

            for row in rows:
                age_days = (now - row['created_at'].replace(tzinfo=timezone.utc)).total_seconds() / 86400.0
                w = math.exp(-decay_rate * age_days)
                total_weight += w
                for key in weighted:
                    weighted[key] += w * float(row[key] or 0)

            if total_weight > 0:
                for key in weighted:
                    weighted[key] = round(weighted[key] / total_weight, 4)

            latest = dict(rows[0])
            latest['created_at'] = str(latest['created_at'])

            return ok({
                'user_id': user_id,
                'weighted_profile': weighted,
                'latest_snapshot': latest,
                'snapshot_count': len(rows),
            })
        except Exception as e:
            return fail(str(e))

    @mcp.tool()
    async def log_recommendation_audit(
        user_id: str = 'default',
        strategy_id: str = '',
        code: str = '',
        stock_code: str = '',
        action: str = '',
        emotion_polarity: float = 0.0,
        emotion_intensity: float = 0.0,
        cognitive_biases='',
        risk_aversion: float = 2.5,
        kyc_level: str = '',
        reasoning_chain: str = '',
    ):
        """记录推荐审计日志（推荐策略/股票时必须调用）

        Args:
            user_id: 用户ID
            strategy_id: 策略ID
            stock_code: 股票代码
            action: 推荐动作 buy/sell/hold
            emotion_polarity: 情绪极性 -1~1
            emotion_intensity: 情绪强度 0~1
            cognitive_biases: 逗号分隔的认知偏差列表
            risk_aversion: 风险厌恶系数
            kyc_level: KYC等级
            reasoning_chain: 推理链路说明
        """
        try:
            db = get_db()
            stock_code = resolve_security_code(code, stock_code=stock_code)
            if isinstance(cognitive_biases, (list, tuple, set)):
                biases_list = [str(b).strip() for b in cognitive_biases if str(b).strip()]
            else:
                raw_biases = str(cognitive_biases or '')
                biases_list = [b.strip() for b in raw_biases.split(',') if b.strip()]

            async with db.acquire() as conn:
                await conn.execute(
                    """INSERT INTO recommendation_audit_log
                       (user_id, strategy_id, stock_code, action,
                        emotion_polarity, emotion_intensity, cognitive_biases,
                        risk_aversion, kyc_level, reasoning_chain)
                       VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)""",
                    user_id, strategy_id or None, stock_code or None, action,
                    emotion_polarity, emotion_intensity, biases_list,
                    risk_aversion, kyc_level or None, reasoning_chain,
                )
            return ok({'logged': True})
        except Exception as e:
            return fail(str(e))
