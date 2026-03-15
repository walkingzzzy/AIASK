"""Strategy generators: rule-based and LLM-proxy strategy candidate generation."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import Any, Optional

import pandas as pd

from .llm_alpha import LLMAlphaMiner
from .strategy_dsl import compile_strategy_blueprint
from .strategy_factory.constants import LLM_FAN_OUT_COUNT, PIPELINE_MODE
from .strategy_llm_provider import get_strategy_llm_provider
from .strategy_pipeline import get_strategy_pipeline
from .strategy_spec import (
    DEFAULT_CODES,
    RESEARCH_CANDIDATE_POOL_LIMIT,
    RESEARCH_FINANCIAL_DETAIL_LIMIT,
    RESEARCH_KLINE_SCAN_LIMIT,
    RESEARCH_SYMBOL_DETAIL_LIMIT,
    RESEARCH_UNIVERSE_PAGE_SIZE,
    RESEARCH_UNIVERSE_SCAN_LIMIT,
    StrategySpec,
)
from .strategy_factory.utils import _extract_event_context

logger = logging.getLogger(__name__)


class RuleStrategyGenerator:
    def generate(self, snapshot: dict, limit: int = 2) -> list[StrategySpec]:
        fg = int(snapshot.get('fear_greed_index') or 50)
        specs: list[StrategySpec] = []
        if fg >= 60:
            specs.append(StrategySpec(
                strategy_type='momentum',
                params={'lookback': 15, 'threshold': 0.018},
                name='AI 动量强化',
                description='高情绪阶段偏向动量追随。',
                tags=['rule'],
                metadata={'generator_type': 'rule', 'generation_reason': {'fg': fg, 'regime': 'greed'}},
            ))
            specs.append(StrategySpec(
                strategy_type='ma_cross',
                params={'short_period': 6, 'long_period': 24},
                name='AI 均线趋势',
                description='情绪偏强阶段用均线趋势过滤。',
                tags=['rule'],
                metadata={'generator_type': 'rule', 'generation_reason': {'fg': fg, 'regime': 'greed'}},
            ))
        else:
            specs.append(StrategySpec(
                strategy_type='rsi',
                params={'rsi_period': 14, 'oversold': 28, 'overbought': 72},
                name='AI RSI 反转',
                description='低情绪阶段偏向均值回归与超跌反弹。',
                tags=['rule'],
                metadata={'generator_type': 'rule', 'generation_reason': {'fg': fg, 'regime': 'fear_or_neutral'}},
            ))
            specs.append(StrategySpec(
                strategy_type='value_factor',
                params={'lookback': 60, 'buy_quantile': 0.8, 'sell_quantile': 0.2},
                name='AI 价值回归',
                description='低情绪阶段偏向价值/反转。',
                tags=['rule'],
                metadata={'generator_type': 'rule', 'generation_reason': {'fg': fg, 'regime': 'fear_or_neutral'}},
            ))
        return specs[: max(1, min(int(limit or 2), 10))]


class LLMProxyStrategyGenerator:
    def __init__(self):
        self.miner = LLMAlphaMiner()
        self.external_provider = get_strategy_llm_provider()
        self.last_report: dict[str, Any] = {}

    def get_last_report(self) -> dict[str, Any]:
        return dict(self.last_report)

    @staticmethod
    def _dedupe_specs(specs: list[StrategySpec]) -> list[StrategySpec]:
        unique: list[StrategySpec] = []
        seen: set[tuple[str, str]] = set()
        for spec in list(specs or []):
            key = (
                str(spec.strategy_type or ''),
                json.dumps(spec.params or {}, sort_keys=True, ensure_ascii=False, default=str),
            )
            if key in seen:
                continue
            seen.add(key)
            unique.append(spec)
        return unique

    async def _run_external_provider_request(
        self,
        *,
        snapshot: dict[str, Any],
        frame,
        frame_cache: dict[str, pd.DataFrame],
        research_context: dict[str, Any],
        parent_strategies: list[dict[str, Any]],
        history_summary: list[dict[str, Any]],
        research_task: Optional[dict[str, Any]],
        request_limit: int,
        request_index: int,
    ) -> dict[str, Any]:
        try:
            provider_payload = await self.external_provider.generate_candidates(
                snapshot=snapshot or {},
                market_frame=frame,
                research_context=research_context,
                parent_strategies=list(parent_strategies or []),
                history_summary=history_summary,
                research_task=research_task,
                limit=request_limit,
            )
            request_metrics = dict((provider_payload or {}).get('request_metrics') or {})
            analysis = dict((provider_payload or {}).get('analysis') or {})
            returned_candidates = list((provider_payload or {}).get('candidates') or [])
            all_specs: list[StrategySpec] = []
            viable_specs: list[StrategySpec] = []
            for candidate in returned_candidates:
                spec = self._build_external_candidate_spec(
                    candidate,
                    provider_payload or {},
                    frame_cache,
                    frame,
                    research_task=research_task,
                )
                if spec is None:
                    continue
                all_specs.append(spec)
                if self._is_viable_external_spec(spec):
                    viable_specs.append(spec)
            viable_specs.sort(key=self._spec_preflight_score, reverse=True)
            all_specs.sort(key=self._spec_preflight_score, reverse=True)
            non_executable_candidate_count = max(0, len(returned_candidates) - len(all_specs))
            return {
                'status': 'succeeded',
                'request_index': request_index,
                'analysis': analysis,
                'request_report': {
                    'request_index': request_index,
                    'request_limit': request_limit,
                    'status': 'succeeded',
                    'returned_candidate_count': len(returned_candidates),
                    'compiled_candidate_count': len(all_specs),
                    'non_executable_candidate_count': non_executable_candidate_count,
                    'viable_candidate_count': len(viable_specs),
                    'candidate_names': [str((item or {}).get('name') or '') for item in returned_candidates[:4]],
                    'candidate_preflight': [
                        {
                            'name': spec.name,
                            'score': self._spec_preflight_score(spec),
                            'entry_count': int(dict(spec.metadata.get('dsl_activity') or {}).get('entry_count') or 0),
                            'exit_count': int(dict(spec.metadata.get('dsl_activity') or {}).get('exit_count') or 0),
                            'target_symbols': list(spec.metadata.get('target_symbols') or []),
                            'preflight_symbol': spec.metadata.get('preflight_symbol'),
                        }
                        for spec in all_specs[:4]
                    ],
                    'analysis': analysis,
                    'request_metrics': request_metrics,
                },
                'successful_without_specs': bool(returned_candidates) and not all_specs,
                'all_specs': all_specs,
                'viable_specs': viable_specs,
                'exception': None,
            }
        except Exception as exc:
            metrics = dict(getattr(exc, 'metrics', {}) or {})
            logger.warning(
                'LLMProxyStrategyGenerator external provider failed at request_index=%s limit=%s, retrying/fallback: %r',
                request_index,
                request_limit,
                exc,
            )
            return {
                'status': 'failed',
                'request_index': request_index,
                'analysis': {},
                'request_report': {
                    'request_index': request_index,
                    'request_limit': request_limit,
                    'status': 'failed',
                    'error_type': metrics.get('last_error_type') or exc.__class__.__name__,
                    'error': metrics.get('last_error') or str(exc) or exc.__class__.__name__,
                    'request_metrics': metrics,
                },
                'successful_without_specs': False,
                'all_specs': [],
                'viable_specs': [],
                'exception': exc,
            }

    async def _frame_from_codes(self, db, codes: list[str], limit: int = 180) -> Optional[pd.DataFrame]:
        for code in list(dict.fromkeys([str(item or '').strip() for item in list(codes or []) if str(item or '').strip()])):
            try:
                klines = await db.get_klines(code, limit=limit)
            except Exception:
                klines = []
            if not klines:
                continue
            frame = pd.DataFrame(klines)
            if not frame.empty and 'close' in frame.columns:
                return frame.tail(120).copy()
        return None

    @staticmethod
    def _build_synthetic_market_frame(research_context: Optional[dict[str, Any]] = None) -> Optional[pd.DataFrame]:
        context = dict(research_context or {})
        sources = list(context.get('symbol_insights') or []) + list(context.get('candidate_universe') or [])
        close_values = []
        volume_values = []
        for item in sources:
            try:
                close = float((item or {}).get('close') or 0.0)
            except Exception:
                close = 0.0
            if close <= 0:
                continue
            close_values.append(close)
            try:
                volume = float((item or {}).get('volume') or (item or {}).get('market_cap') or 0.0)
            except Exception:
                volume = 0.0
            volume_values.append(max(volume, 1.0))
            if len(close_values) >= 12:
                break
        if not close_values:
            return None
        rows = max(24, len(close_values) * 4)
        closes = []
        volumes = []
        for idx in range(rows):
            base_close = close_values[idx % len(close_values)]
            drift = 1.0 + ((idx % 6) - 2) * 0.0025
            closes.append(round(base_close * drift, 6))
            base_volume = volume_values[idx % len(volume_values)] if volume_values else 1.0
            volumes.append(float(max(base_volume * (1.0 + ((idx % 5) - 2) * 0.03), 1.0)))
        return pd.DataFrame({
            'open': closes,
            'high': [value * 1.003 for value in closes],
            'low': [value * 0.997 for value in closes],
            'close': closes,
            'volume': volumes,
        })

    async def _build_market_frame(self, db, research_task: Optional[dict[str, Any]] = None) -> Optional[pd.DataFrame]:
        research_task = dict(research_task or {})
        target_codes = self._normalize_code_list(research_task.get('target_symbols'))
        target_frame = await self._frame_from_codes(db, target_codes, limit=180)
        if target_frame is not None:
            return target_frame

        primary_codes: list[str] = []
        if hasattr(db, 'list_stock_universe'):
            try:
                rows = await db.list_stock_universe(limit=3, offset=0)
                primary_codes = [str((row or {}).get('code') or '').strip() for row in rows if str((row or {}).get('code') or '').strip()]
            except Exception:
                primary_codes = []
        return await self._frame_from_codes(db, [*primary_codes, *DEFAULT_CODES], limit=180)

    async def _build_symbol_frame_cache(self, db, research_context: Optional[dict[str, Any]] = None, research_task: Optional[dict[str, Any]] = None) -> dict[str, pd.DataFrame]:
        cache: dict[str, pd.DataFrame] = {}
        research_context = dict(research_context or {})
        research_task = dict(research_task or {})
        codes = self._normalize_code_list([
            research_task.get('target_symbols'),
            [item.get('code') for item in list(research_context.get('candidate_universe') or [])],
            [item.get('code') for item in list(research_context.get('symbol_insights') or [])],
        ], limit=10)
        for code in codes:
            frame = await self._frame_from_codes(db, [code], limit=180)
            if frame is not None:
                cache[code] = frame
        return cache

    def _candidate_frame_codes(
        self,
        candidate: dict[str, Any],
        research_task: Optional[dict[str, Any]] = None,
    ) -> list[str]:
        research_task = dict(research_task or {})
        return self._normalize_code_list([
            candidate.get('target_symbols'),
            candidate.get('stock_pool'),
            ((candidate.get('dsl') or {}).get('metadata') or {}).get('target_symbols'),
            research_task.get('target_symbols'),
        ], limit=10)

    def _build_external_candidate_spec(
        self,
        candidate: dict[str, Any],
        provider_payload: dict[str, Any],
        frame_cache: dict[str, pd.DataFrame],
        default_frame: Optional[pd.DataFrame],
        research_task: Optional[dict[str, Any]] = None,
    ) -> Optional[StrategySpec]:
        frame_candidates: list[tuple[str, pd.DataFrame]] = []
        for code in self._candidate_frame_codes(candidate, research_task=research_task):
            frame = frame_cache.get(code)
            if frame is not None and not frame.empty:
                frame_candidates.append((code, frame))
        if not frame_candidates and default_frame is not None and not default_frame.empty:
            frame_candidates.append(('__default__', default_frame))

        best_spec: Optional[StrategySpec] = None
        best_rank: Optional[tuple[float, int, int]] = None
        for code, frame in frame_candidates:
            spec = self._external_candidate_to_spec(candidate, provider_payload or {}, market_frame=frame)
            if spec is None:
                continue
            metadata = dict(spec.metadata or {})
            metadata['preflight_symbol'] = None if code == '__default__' else code
            spec.metadata = metadata
            activity = dict(metadata.get('dsl_activity') or {})
            rank = (
                self._spec_preflight_score(spec),
                int(min(activity.get('entry_count') or 0, activity.get('exit_count') or 0)),
                int(activity.get('active_days') or 0),
            )
            if best_rank is None or rank > best_rank:
                best_spec = spec
                best_rank = rank
        return best_spec

    @staticmethod
    def _safe_float(value: Any) -> float:
        try:
            return float(value or 0.0)
        except Exception:
            return 0.0

    @staticmethod
    def _normalize_code_list(values: Any, limit: int = 12) -> list[str]:
        codes: list[str] = []
        seen: set[str] = set()

        def visit(value: Any):
            if value is None:
                return
            if isinstance(value, dict):
                for key in ('code', 'symbol', 'stock_code'):
                    if value.get(key) is not None:
                        visit(value.get(key))
                for key in ('codes', 'symbols', 'stock_codes', 'target_symbols'):
                    if value.get(key) is not None:
                        visit(value.get(key))
                return
            if isinstance(value, (list, tuple, set)):
                for item in value:
                    visit(item)
                return
            raw = str(value or '').strip()
            if not raw:
                return
            if any(sep in raw for sep in [',', ';', '|', '\n', '\t', ' ']):
                normalized = raw.replace(';', ',').replace('|', ',').replace('\n', ',').replace('\t', ',').replace(' ', ',')
                for part in normalized.split(','):
                    visit(part)
                return
            code = raw.split('.')[0].strip()
            if not code or code in seen:
                return
            seen.add(code)
            codes.append(code)

        visit(values)
        return codes[: max(1, min(int(limit or 12), 40))]

    @classmethod
    def _summarize_symbol_frame(cls, code: str, frame: pd.DataFrame) -> Optional[dict[str, Any]]:
        if frame is None or frame.empty or 'close' not in frame.columns:
            return None
        compact = frame.tail(min(len(frame), 120)).copy()
        close = pd.to_numeric(compact['close'], errors='coerce').dropna()
        if len(close) < 20:
            return None
        volume = pd.to_numeric(compact.get('volume'), errors='coerce').dropna() if 'volume' in compact.columns else pd.Series(dtype=float)
        sma5 = float(close.tail(5).mean())
        sma20 = float(close.tail(20).mean())
        latest = float(close.iloc[-1])
        return_5d = (latest / float(close.iloc[-6]) - 1.0) if len(close) >= 6 and float(close.iloc[-6]) else 0.0
        return_20d = (latest / float(close.iloc[-21]) - 1.0) if len(close) >= 21 and float(close.iloc[-21]) else 0.0
        volatility_20d = float(close.pct_change().tail(20).std(ddof=0) or 0.0)
        volume_ratio_20 = float(volume.tail(5).mean() / max(float(volume.tail(20).mean() or 1.0), 1.0)) if len(volume) >= 20 else 1.0
        trend_state = 'sideways'
        if latest >= sma20 and sma5 >= sma20:
            trend_state = 'uptrend'
        elif latest < sma20 and sma5 < sma20:
            trend_state = 'downtrend'
        return {
            'code': code,
            'close': round(latest, 6),
            'return_5d': round(return_5d, 6),
            'return_20d': round(return_20d, 6),
            'volatility_20d': round(volatility_20d, 6),
            'price_vs_sma20': 'above' if latest >= sma20 else 'below',
            'sma5_vs_sma20': 'above' if sma5 >= sma20 else 'below',
            'trend_state': trend_state,
            'volume_ratio_20': round(volume_ratio_20, 6),
        }

    @classmethod
    def _rank_symbol_context(cls, item: dict[str, Any]) -> float:
        score = 0.0
        score += cls._safe_float(item.get('return_20d')) * 5.0
        score += cls._safe_float(item.get('return_5d')) * 2.0
        score -= cls._safe_float(item.get('volatility_20d')) * 1.5
        if item.get('trend_state') == 'uptrend':
            score += 0.35
        if item.get('price_vs_sma20') == 'above':
            score += 0.12
        if item.get('sma5_vs_sma20') == 'above':
            score += 0.08
        score += min(max(cls._safe_float(item.get('volume_ratio_20')) - 1.0, -0.5), 0.5) * 0.3
        market_cap = cls._safe_float(item.get('market_cap'))
        if market_cap > 0:
            score += min(market_cap / 1_000_000_000_000, 0.15)
        pe_ratio = item.get('pe_ratio')
        if isinstance(pe_ratio, (int, float)) and 0 < float(pe_ratio) < 40:
            score += 0.05
        pb_ratio = item.get('pb_ratio')
        if isinstance(pb_ratio, (int, float)) and 0 < float(pb_ratio) < 8:
            score += 0.03
        financial_snapshot = dict(item.get('financial_snapshot') or {})
        if cls._safe_float(financial_snapshot.get('revenue_growth')) > 0:
            score += 0.05
        if cls._safe_float(financial_snapshot.get('profit_growth')) > 0:
            score += 0.05
        factor_snapshot = dict(item.get('factor_snapshot') or {})
        positive_factor_count = len([v for v in factor_snapshot.values() if isinstance(v, (int, float)) and float(v) > 0])
        score += min(positive_factor_count, 3) * 0.03
        return round(score, 6)

    async def _load_universe_rows(self, db) -> list[dict[str, Any]]:
        if not hasattr(db, 'list_stock_universe'):
            return []
        rows: list[dict[str, Any]] = []
        offset = 0
        while len(rows) < RESEARCH_UNIVERSE_SCAN_LIMIT:
            batch_limit = min(RESEARCH_UNIVERSE_PAGE_SIZE, RESEARCH_UNIVERSE_SCAN_LIMIT - len(rows))
            if batch_limit <= 0:
                break
            try:
                batch = await db.list_stock_universe(limit=batch_limit, offset=offset)
            except TypeError:
                batch = await db.list_stock_universe(limit=batch_limit)
            except Exception:
                break
            if not batch:
                break
            rows.extend([dict(item or {}) for item in batch])
            offset += len(batch)
            if len(batch) < batch_limit:
                break
        return rows

    async def _fetch_factor_snapshot(self, db, codes: list[str], snapshot: dict[str, Any]) -> dict[str, dict[str, Any]]:
        if not codes or not hasattr(db, 'get_factor_values'):
            return {}
        factor_names: list[str] = []
        for payload in (dict(snapshot.get('factor_ic_trend') or {}), dict(snapshot.get('factor_ic') or {})):
            for key in payload.keys():
                factor_name = str(key or '').strip()
                if factor_name and factor_name not in factor_names:
                    factor_names.append(factor_name)
        factor_names = factor_names[:3]
        if not factor_names:
            return {}
        factor_snapshot: dict[str, dict[str, Any]] = {code: {} for code in codes}
        for factor_name in factor_names:
            try:
                rows = await db.get_factor_values(codes, factor_name)
            except Exception:
                continue
            latest_by_code: dict[str, tuple[str, float]] = {}
            for row in list(rows or []):
                code = str((row or {}).get('stock_code') or (row or {}).get('code') or '').strip()
                if not code:
                    continue
                factor_date = str((row or {}).get('factor_date') or '')
                factor_value = self._safe_float((row or {}).get('factor_value'))
                current = latest_by_code.get(code)
                if current is None or factor_date >= current[0]:
                    latest_by_code[code] = (factor_date, factor_value)
            for code, payload in latest_by_code.items():
                factor_snapshot.setdefault(code, {})[factor_name] = payload[1]
        return {code: values for code, values in factor_snapshot.items() if values}

    async def _build_research_context(
        self,
        db,
        snapshot: Optional[dict[str, Any]],
        *,
        parent_strategies: Optional[list[dict]] = None,
        history_summary: Optional[list[dict]] = None,
        research_task: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        snapshot = snapshot or {}
        research_task = dict(research_task or {})
        universe_rows = await self._load_universe_rows(db)
        universe_total_count = 0
        if hasattr(db, 'count_stock_universe'):
            try:
                universe_total_count = int(await db.count_stock_universe())
            except Exception:
                universe_total_count = 0
        if universe_total_count <= 0:
            universe_total_count = len(universe_rows)

        breadth_rows: list[dict[str, Any]] = []
        symbol_insights: list[dict[str, Any]] = []
        candidate_universe: list[dict[str, Any]] = []
        task_target_symbols = self._normalize_code_list(research_task.get('target_symbols'))
        task_focus_industries = [str(item).strip() for item in list(research_task.get('focus_industries') or []) if str(item).strip()]
        task_focus_markets = [str(item).strip() for item in list(research_task.get('focus_markets') or []) if str(item).strip()]
        filtered_rows = list(universe_rows)
        if task_target_symbols:
            target_set = set(task_target_symbols)
            targeted = [row for row in filtered_rows if str((row or {}).get('code') or "").strip() in target_set]
            if targeted:
                filtered_rows = targeted
        elif task_focus_industries:
            industry_filtered = [
                row for row in filtered_rows
                if any(keyword in str((row or {}).get('industry') or (row or {}).get('sector') or "") for keyword in task_focus_industries)
            ]
            if industry_filtered:
                filtered_rows = industry_filtered
        if task_focus_markets:
            market_filtered = [row for row in filtered_rows if str((row or {}).get('market') or "").strip() in set(task_focus_markets)]
            if market_filtered:
                filtered_rows = market_filtered
        scan_rows = list(filtered_rows[: min(len(filtered_rows), RESEARCH_KLINE_SCAN_LIMIT)])
        top_industries: dict[str, int] = {}
        if universe_rows:
            industry_counts: dict[str, int] = {}
            for row in universe_rows:
                industry = str((row or {}).get('industry') or (row or {}).get('sector') or '未分类').strip() or '未分类'
                industry_counts[industry] = industry_counts.get(industry, 0) + 1
            top_industries = {
                str(key): int(value)
                for key, value in sorted(industry_counts.items(), key=lambda item: item[1], reverse=True)[:8]
            }

        for row in scan_rows:
            code = str((row or {}).get('code') or '').strip()
            if not code:
                continue
            try:
                klines = await db.get_klines(code, limit=180)
            except Exception:
                klines = []
            if not klines:
                continue
            frame = pd.DataFrame(klines)
            summary = self._summarize_symbol_frame(code, frame)
            if summary is None:
                continue
            enriched = {
                **dict(row or {}),
                **summary,
                'name': (row or {}).get('name') or code,
                'industry': (row or {}).get('industry') or (row or {}).get('sector'),
                'sector': (row or {}).get('sector') or (row or {}).get('industry'),
                'market_cap': (row or {}).get('market_cap'),
                'pe_ratio': (row or {}).get('pe_ratio'),
                'pb_ratio': (row or {}).get('pb_ratio'),
            }
            breadth_rows.append(enriched)
        if breadth_rows:
            symbol_insights = [dict(item) for item in breadth_rows[:RESEARCH_SYMBOL_DETAIL_LIMIT]]
            scored = []
            for item in breadth_rows:
                ranked = dict(item)
                ranked['screen_score'] = self._rank_symbol_context(ranked)
                scored.append(ranked)
            scored.sort(key=lambda item: (self._safe_float(item.get('screen_score')), self._safe_float(item.get('market_cap'))), reverse=True)
            candidate_universe = [dict(item) for item in scored[:RESEARCH_CANDIDATE_POOL_LIMIT]]
            candidate_codes = [str(item.get('code') or '') for item in candidate_universe if str(item.get('code') or '').strip()]
            factor_snapshot = await self._fetch_factor_snapshot(db, candidate_codes, snapshot)
            for item in candidate_universe[:RESEARCH_FINANCIAL_DETAIL_LIMIT]:
                if hasattr(db, 'get_financials'):
                    try:
                        financials = await db.get_financials(item['code'], limit=1)
                    except Exception:
                        financials = []
                    item['financial_snapshot'] = dict((financials or [None])[0] or {})
            for item in candidate_universe:
                item['factor_snapshot'] = dict(factor_snapshot.get(str(item.get('code') or '')) or {})
                item['screen_score'] = self._rank_symbol_context(item)
            candidate_universe.sort(key=lambda item: (self._safe_float(item.get('screen_score')), self._safe_float(item.get('market_cap'))), reverse=True)

        if not symbol_insights:
            for code in DEFAULT_CODES:
                try:
                    klines = await db.get_klines(code, limit=180)
                except Exception:
                    klines = []
                if not klines:
                    continue
                frame = pd.DataFrame(klines)
                summary = self._summarize_symbol_frame(code, frame)
                if summary is not None:
                    symbol_insights.append(summary)
            candidate_universe = [dict(item, screen_score=self._rank_symbol_context(item)) for item in symbol_insights[: min(len(symbol_insights), RESEARCH_CANDIDATE_POOL_LIMIT)]]

        trend_up_count = len([item for item in symbol_insights if item.get('trend_state') == 'uptrend'])
        trend_down_count = len([item for item in symbol_insights if item.get('trend_state') == 'downtrend'])
        avg_return_20d = round(sum(self._safe_float(item.get('return_20d')) for item in symbol_insights) / max(len(symbol_insights), 1), 6) if symbol_insights else 0.0
        avg_volatility_20d = round(sum(self._safe_float(item.get('volatility_20d')) for item in symbol_insights) / max(len(symbol_insights), 1), 6) if symbol_insights else 0.0
        category_counts = dict(snapshot.get('category_counts') or {})
        top_categories = {
            str(key): int(value)
            for key, value in sorted(category_counts.items(), key=lambda item: item[1], reverse=True)[:5]
        }
        scanned_stock_count = len(universe_rows) if universe_rows else len(symbol_insights)
        data_ready_count = len(breadth_rows) if breadth_rows else len(symbol_insights)
        coverage_ratio = round(scanned_stock_count / max(universe_total_count, 1), 6) if universe_total_count else 0.0
        return {
            'research_task': {
                'task_id': research_task.get('task_id'),
                'theme': research_task.get('theme'),
                'opportunity_type': research_task.get('opportunity_type'),
                'focus_industries': task_focus_industries,
                'focus_markets': task_focus_markets,
                'target_symbols': task_target_symbols,
                'priority': research_task.get('priority'),
                'strategy_preferences': list(research_task.get('strategy_preferences') or []),
                'generation_limit': research_task.get('generation_limit'),
                'rationale': research_task.get('rationale'),
            },
            'market_regime': {
                'fg_level': snapshot.get('fg_level'),
                'fear_greed_index': snapshot.get('fear_greed_index'),
                'hot_sectors': list(snapshot.get('hot_sectors') or [])[:4],
                'cold_sectors': list(snapshot.get('cold_sectors') or [])[:3],
                'factor_ic': dict(snapshot.get('factor_ic') or {}),
                'factor_ic_trend': dict(snapshot.get('factor_ic_trend') or {}),
                'factor_research': dict(snapshot.get('factor_research') or {}),
            },
            'market_breadth': {
                'symbol_count': len(symbol_insights),
                'trend_up_count': trend_up_count,
                'trend_down_count': trend_down_count,
                'avg_return_20d': avg_return_20d,
                'avg_volatility_20d': avg_volatility_20d,
            },
            'symbol_insights': symbol_insights,
            'candidate_universe': candidate_universe,
            'universe_scan': {
                'total_stock_count': universe_total_count,
                'scanned_stock_count': scanned_stock_count,
                'data_ready_count': data_ready_count,
                'coverage_ratio': coverage_ratio,
                'detail_symbol_count': len(symbol_insights),
                'candidate_universe_count': len(candidate_universe),
                'top_industries': top_industries,
            },
            'selection_framework': {
                'technical': ['trend_state', 'return_20d', 'return_5d', 'volume_ratio_20', 'price_vs_sma20'],
                'fundamental': ['market_cap', 'pe_ratio', 'pb_ratio', 'revenue_growth', 'profit_growth'],
                'factor_names': [
                    str(key)
                    for key in list(
                        ((snapshot.get('factor_research') or {}).get('summary') or {}).get('top_factor_names')
                        or (snapshot.get('factor_research') or {}).get('active_factors')
                        or list((snapshot.get('factor_ic_trend') or {}).keys())[:3]
                    )[:3]
                ],
            },
            'analysis_scope': {
                'scan_mode': 'broad_universe_scan_with_focused_detail',
                'scan_limit': RESEARCH_UNIVERSE_SCAN_LIMIT,
                'kline_scan_limit': RESEARCH_KLINE_SCAN_LIMIT,
                'detail_limit': RESEARCH_SYMBOL_DETAIL_LIMIT,
                'candidate_pool_limit': RESEARCH_CANDIDATE_POOL_LIMIT,
            },
            'population_state': {
                'listed_count': int(snapshot.get('listed_count') or universe_total_count or 0),
                'incubating_count': int(snapshot.get('incubating_count') or 0),
                'top_categories': top_categories,
            },
            'parent_context': [
                {
                    'id': item.get('id'),
                    'name': item.get('name'),
                    'strategy_type': item.get('strategy_type'),
                    'status': item.get('status'),
                }
                for item in list(parent_strategies or [])[:3]
            ],
            'experiment_feedback': [
                {
                    'generator_type': item.get('generator_type'),
                    'status': item.get('status'),
                    'decision': item.get('decision'),
                    'final_score': item.get('final_score'),
                }
                for item in list(history_summary or [])[:4]
            ],
        }

    @staticmethod
    def _summarize_research_context(context: Optional[dict[str, Any]]) -> dict[str, Any]:
        payload = dict(context or {})
        breadth = dict(payload.get('market_breadth') or {})
        regime = dict(payload.get('market_regime') or {})
        universe_scan = dict(payload.get('universe_scan') or {})
        candidate_universe = list(payload.get('candidate_universe') or [])
        return {
            'symbol_count': int(breadth.get('symbol_count') or 0),
            'trend_up_count': int(breadth.get('trend_up_count') or 0),
            'trend_down_count': int(breadth.get('trend_down_count') or 0),
            'avg_return_20d': breadth.get('avg_return_20d'),
            'avg_volatility_20d': breadth.get('avg_volatility_20d'),
            'candidate_universe_count': len(candidate_universe),
            'candidate_codes': [str((item or {}).get('code') or '') for item in candidate_universe[:5]],
            'universe_total_count': int(universe_scan.get('total_stock_count') or 0),
            'universe_scanned_count': int(universe_scan.get('scanned_stock_count') or 0),
            'data_ready_count': int(universe_scan.get('data_ready_count') or 0),
            'coverage_ratio': universe_scan.get('coverage_ratio'),
            'fg_level': regime.get('fg_level'),
            'fear_greed_index': regime.get('fear_greed_index'),
            'hot_sectors': list(regime.get('hot_sectors') or [])[:3],
            'cold_sectors': list(regime.get('cold_sectors') or [])[:2],
        }

    @staticmethod
    def _fallback_variant_seed(task: dict[str, Any], target_symbols: list[str], candidate: dict[str, Any]) -> int:
        seed_text = "|".join([
            str(task.get('task_id') or ''),
            str(task.get('theme') or ''),
            str(task.get('opportunity_type') or ''),
            str(candidate.get('category') or ''),
            *[str(code) for code in list(target_symbols or [])[:6]],
        ])
        return sum(ord(ch) for ch in seed_text if ch)

    @classmethod
    def _adapt_local_fallback_params(
        cls,
        strategy_type: str,
        params: dict[str, Any],
        task: dict[str, Any],
        candidate: dict[str, Any],
        target_symbols: list[str],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        adapted = dict(params or {})
        if not task:
            return adapted, {
                'variant_seed': 0,
                'profile': 'default',
                'task_opportunity_type': None,
            }
        opportunity_type = str(task.get('opportunity_type') or 'default').strip().lower() or 'default'
        variant_seed = cls._fallback_variant_seed(task, target_symbols, candidate)
        bucket = variant_seed % 5
        symbol_count = max(1, len(target_symbols or []))

        if strategy_type == 'momentum':
            lookback_map = {
                'sector_breakout': [8, 10, 12, 15, 18],
                'rotation_balanced': [14, 18, 20, 24, 30],
                'industry_leadership': [10, 12, 16, 20, 24],
                'factor_acceleration': [6, 8, 10, 12, 15],
                'default': [10, 14, 18, 20, 24],
            }
            threshold_map = {
                'sector_breakout': [0.008, 0.01, 0.012, 0.015, 0.018],
                'rotation_balanced': [0.006, 0.008, 0.01, 0.012, 0.015],
                'industry_leadership': [0.007, 0.009, 0.011, 0.013, 0.016],
                'factor_acceleration': [0.005, 0.007, 0.009, 0.011, 0.013],
                'default': [0.008, 0.01, 0.012, 0.015, 0.018],
            }
            lookbacks = lookback_map.get(opportunity_type, lookback_map['default'])
            thresholds = threshold_map.get(opportunity_type, threshold_map['default'])
            adapted['lookback'] = int(lookbacks[bucket])
            adapted['threshold'] = round(float(thresholds[(bucket + symbol_count) % len(thresholds)]), 4)
        elif strategy_type == 'ma_cross':
            short_map = {
                'sector_breakout': [4, 5, 6, 8, 10],
                'rotation_balanced': [5, 6, 8, 10, 12],
                'industry_leadership': [4, 6, 7, 9, 11],
                'default': [5, 6, 8, 10, 12],
            }
            long_map = {
                'sector_breakout': [18, 20, 24, 30, 34],
                'rotation_balanced': [24, 30, 36, 40, 48],
                'industry_leadership': [20, 24, 28, 32, 40],
                'default': [20, 24, 30, 36, 40],
            }
            shorts = short_map.get(opportunity_type, short_map['default'])
            longs = long_map.get(opportunity_type, long_map['default'])
            adapted['short_period'] = int(shorts[bucket])
            adapted['long_period'] = int(max(longs[(bucket + 1) % len(longs)], adapted['short_period'] + 6))
        elif strategy_type == 'rsi':
            adapted['rsi_period'] = int([6, 8, 10, 12, 14][bucket])
            adapted['oversold'] = int([24, 26, 28, 30, 32][bucket])
            adapted['overbought'] = int([68, 70, 72, 74, 76][bucket])
        elif strategy_type in {'quality_factor', 'value_factor', 'growth_factor'}:
            lookbacks = [24, 30, 36, 45, 60] if opportunity_type == 'sector_breakout' else [30, 40, 50, 60, 72]
            buy_quantiles = [0.58, 0.62, 0.66, 0.7, 0.75]
            sell_quantiles = [0.22, 0.26, 0.3, 0.34, 0.38]
            adapted['lookback'] = int(lookbacks[bucket])
            adapted['buy_quantile'] = round(float(buy_quantiles[bucket]), 4)
            adapted['sell_quantile'] = round(float(sell_quantiles[(bucket + 2) % len(sell_quantiles)]), 4)

        profile = {
            'variant_seed': variant_seed,
            'variant_bucket': bucket,
            'profile': opportunity_type,
            'task_opportunity_type': opportunity_type,
            'symbol_count': symbol_count,
        }
        return adapted, profile

    @staticmethod
    def _local_category_rank(category: str, research_task: Optional[dict[str, Any]] = None) -> tuple[int, int]:
        task = dict(research_task or {})
        opportunity_type = str(task.get('opportunity_type') or '').strip().lower()
        task_source = str(task.get('task_source') or '').strip().lower()
        strategy_preferences = [str(item).strip().lower() for item in list(task.get('strategy_preferences') or []) if str(item).strip()]

        category_to_types = {
            'momentum': ('momentum',),
            'event': ('momentum',),
            'sentiment': ('momentum',),
            'trend': ('ma_cross',),
            'volatility': ('ma_cross',),
            'reversal': ('rsi',),
            'quality': ('quality_factor',),
            'risk_adjusted': ('quality_factor',),
            'value': ('value_factor',),
            'growth': ('growth_factor',),
            'liquidity': ('growth_factor', 'momentum'),
        }
        if opportunity_type in {'sector_breakout', 'trend_expansion', 'industry_leadership'} or task_source == 'event_driven':
            preferred_categories = ['event', 'momentum', 'trend', 'growth', 'liquidity', 'sentiment', 'quality', 'risk_adjusted', 'volatility', 'value', 'reversal']
        elif opportunity_type == 'oversold_repair':
            preferred_categories = ['reversal', 'value', 'quality', 'risk_adjusted', 'trend', 'momentum', 'event', 'sentiment', 'growth', 'liquidity', 'volatility']
        elif opportunity_type == 'factor_acceleration':
            preferred_categories = ['quality', 'growth', 'value', 'momentum', 'trend', 'risk_adjusted', 'event', 'sentiment', 'liquidity', 'volatility', 'reversal']
        else:
            preferred_categories = ['momentum', 'trend', 'quality', 'value', 'growth', 'event', 'sentiment', 'risk_adjusted', 'liquidity', 'volatility', 'reversal']

        prioritize_opportunity = task_source == 'event_driven' and opportunity_type in {'sector_breakout', 'trend_expansion', 'industry_leadership'}
        if strategy_preferences and not prioritize_opportunity:
            matched_index = len(strategy_preferences)
            for idx, strategy_type in enumerate(category_to_types.get(category, ())):
                if strategy_type in strategy_preferences:
                    matched_index = min(matched_index, strategy_preferences.index(strategy_type))
            if matched_index < len(strategy_preferences):
                return (matched_index, preferred_categories.index(category) if category in preferred_categories else len(preferred_categories))

        return (
            len(strategy_preferences) + 1,
            preferred_categories.index(category) if category in preferred_categories else len(preferred_categories),
        )

    @classmethod
    def _local_candidate_to_spec(cls, candidate: dict, research_task: Optional[dict[str, Any]] = None) -> Optional[StrategySpec]:
        category = str(candidate.get('category') or 'custom')
        mapping = {
            'momentum': ('momentum', {'lookback': 20, 'threshold': 0.02}),
            'trend': ('ma_cross', {'short_period': 5, 'long_period': 20}),
            'reversal': ('rsi', {'rsi_period': 14, 'oversold': 30, 'overbought': 70}),
            'value': ('value_factor', {'lookback': 60, 'buy_quantile': 0.8, 'sell_quantile': 0.2}),
            'quality': ('quality_factor', {'lookback': 50, 'buy_quantile': 0.75, 'sell_quantile': 0.25}),
            'growth': ('growth_factor', {'lookback': 40, 'buy_quantile': 0.75, 'sell_quantile': 0.25}),
            'volatility': ('ma_cross', {'short_period': 8, 'long_period': 34}),
            'risk_adjusted': ('quality_factor', {'lookback': 45, 'buy_quantile': 0.7, 'sell_quantile': 0.3}),
            'sentiment': ('momentum', {'lookback': 10, 'threshold': 0.015}),
            'event': ('momentum', {'lookback': 8, 'threshold': 0.012}),
        }
        target = mapping.get(category)
        if not target:
            return None
        task = dict(research_task or {})
        event_context = _extract_event_context(task)
        task_source = str(task.get('task_source') or '').strip().lower()
        target_symbols = cls._normalize_code_list([
            candidate.get('target_symbols'),
            candidate.get('stock_pool'),
            task.get('target_symbols'),
            task.get('stock_pool'),
        ])
        stock_pool = cls._normalize_stock_pool(candidate.get('stock_pool'), target_symbols)
        strategy_type, params = target
        params, fallback_profile = cls._adapt_local_fallback_params(strategy_type, params, task, candidate, target_symbols)
        tags = ['local_rule_v1', 'llm_proxy_fallback', category]
        if target_symbols:
            tags.append('targeted_universe')
        return StrategySpec(
            strategy_type=strategy_type,
            params=params,
            name=str(candidate.get('name') or 'AI 候选策略'),
            description=str(candidate.get('description') or candidate.get('rationale') or ''),
            tags=list(dict.fromkeys(tags)),
            metadata={
                'generator_type': str(candidate.get('_engine') or candidate.get('engine') or 'local_rule_v1'),
                'generation_reason': {
                    'source': 'event_driven_local_fallback' if task_source == 'event_driven' else 'llm_proxy_local_fallback',
                    'category': category,
                    'formula': candidate.get('formula'),
                    'rationale': candidate.get('rationale'),
                    'engine': candidate.get('_engine') or candidate.get('engine') or 'local_rule_v1',
                    'fallback_reason': 'external_llm_unavailable',
                    'target_symbols': list(target_symbols),
                    'stock_pool': stock_pool,
                    'fallback_profile': fallback_profile,
                },
                'target_symbols': list(target_symbols),
                'stock_pool': stock_pool,
                'selection_logic': list(task.get('selection_logic') or []),
                'research_scope': dict(task.get('analysis_scope') or {}),
                'research_task': task,
                'event_context': event_context,
                'fallback_profile': fallback_profile,
                'source_candidate': candidate,
            },
        )

    @classmethod
    def _normalize_stock_pool(cls, payload: Any, target_symbols: list[str]) -> dict[str, Any]:
        if isinstance(payload, dict):
            symbols = cls._normalize_code_list(payload.get('symbols') or payload.get('codes') or payload.get('stock_codes') or target_symbols)
            return {
                'selection_mode': str(payload.get('selection_mode') or payload.get('mode') or ('explicit' if symbols else 'screened')).strip() or 'screened',
                'symbols': symbols,
                'filters': dict(payload.get('filters') or {}),
                'rationale': payload.get('rationale'),
            }
        return {
            'selection_mode': 'explicit' if target_symbols else 'screened',
            'symbols': list(target_symbols),
            'filters': {},
            'rationale': None,
        }

    @classmethod
    def _external_candidate_to_spec(cls, candidate: dict, provider_payload: dict, market_frame: Optional[pd.DataFrame] = None) -> Optional[StrategySpec]:
        try:
            compiled = compile_strategy_blueprint(candidate, market_frame=market_frame, tune_for_factory=True)
        except Exception:
            return None
        compiled_meta = dict(compiled.get('metadata') or {})
        activity = dict(compiled_meta.get('dsl_activity') or {})
        analysis = dict(provider_payload.get('analysis') or {})
        research_context = dict(provider_payload.get('research_context') or {})
        target_symbols = cls._normalize_code_list([
            candidate.get('target_symbols'),
            candidate.get('stock_pool'),
            ((candidate.get('dsl') or {}).get('metadata') or {}).get('target_symbols'),
            ((candidate.get('dsl') or {}).get('metadata') or {}).get('stock_pool'),
        ])
        stock_pool = cls._normalize_stock_pool(candidate.get('stock_pool'), target_symbols)
        selection_logic = candidate.get('selection_logic') or analysis.get('selection_notes') or []
        if isinstance(selection_logic, str):
            selection_logic = [selection_logic]
        elif not isinstance(selection_logic, list):
            selection_logic = [selection_logic] if selection_logic else []
        params = dict(compiled.get('params') or {})
        if target_symbols and str(compiled.get('strategy_type') or 'dsl_rule') == 'dsl_rule':
            dsl = dict(params.get('dsl') or {})
            dsl_metadata = dict(dsl.get('metadata') or {})
            dsl_metadata['target_symbols'] = list(target_symbols)
            dsl_metadata['stock_pool'] = stock_pool
            dsl['metadata'] = dsl_metadata
            params['dsl'] = dsl
        metadata = {
            **compiled_meta,
            'generator_type': 'external_llm',
            'generation_reason': {
                'provider': provider_payload.get('provider'),
                'model': provider_payload.get('model'),
                'rationale': candidate.get('rationale'),
                'analysis': analysis,
                'research_context': research_context,
                'target_symbols': list(target_symbols),
                'stock_pool': stock_pool,
                'selection_logic': list(selection_logic),
                'dsl_summary': (params or {}).get('dsl') or {},
                'dsl_activity': activity,
                'dsl_tuning': compiled_meta.get('dsl_tuning') or {},
            },
            'llm_prompt': provider_payload.get('prompt') or {},
            'llm_analysis': analysis,
            'llm_research_context': research_context,
            'llm_response': {
                'provider': provider_payload.get('provider'),
                'model': provider_payload.get('model'),
                'analysis': analysis,
                'research_context': research_context,
                'research_task': provider_payload.get('research_task') or {},
                'candidate': candidate,
                'content': provider_payload.get('content'),
                'request_metrics': provider_payload.get('request_metrics') or {},
            },
            'target_symbols': list(target_symbols),
            'stock_pool': stock_pool,
            'selection_logic': list(selection_logic),
            'research_scope': dict(research_context.get('analysis_scope') or {}),
            'research_task': dict(provider_payload.get('research_task') or {}),
            'source_candidate': candidate,
        }
        tags = ['external_llm', *(compiled.get('tags') or []), *(candidate.get('tags') or [])]
        if target_symbols:
            tags.append('targeted_universe')
        return StrategySpec(
            strategy_type=str(compiled.get('strategy_type') or 'dsl_rule'),
            params=params,
            name=str(compiled.get('name') or candidate.get('name') or '外部 AI 策略'),
            description=str(compiled.get('description') or candidate.get('description') or candidate.get('rationale') or ''),
            tags=list(dict.fromkeys(tags)),
            metadata=metadata,
        )

    @staticmethod
    def _spec_preflight_score(spec: StrategySpec) -> float:
        activity = dict(spec.metadata.get('dsl_activity') or {})
        score = float(activity.get('score') or 0.0)
        tuning = dict(spec.metadata.get('dsl_tuning') or {})
        if tuning.get('applied'):
            score += 0.1
        return score

    @classmethod
    def _is_viable_external_spec(cls, spec: StrategySpec) -> bool:
        activity = dict(spec.metadata.get('dsl_activity') or {})
        if not activity:
            return True
        entry_count = int(activity.get('entry_count') or 0)
        exit_count = int(activity.get('exit_count') or 0)
        return entry_count > 0 and exit_count > 0 and cls._spec_preflight_score(spec) >= 0.8

    async def _recent_experiments(self, db, parent_strategies: Optional[list[dict]] = None) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for parent in list(parent_strategies or [])[:3]:
            parent_id = str((parent or {}).get('id') or '').strip()
            if not parent_id or not hasattr(db, 'list_strategy_generation_experiments'):
                continue
            rows.extend(await db.list_strategy_generation_experiments(parent_strategy_id=parent_id, limit=5))
        summary = []
        for row in rows[:12]:
            evaluation = dict(row.get('evaluation') or {})
            committee_review = dict(evaluation.get('committee_review') or {})
            summary.append({
                'parent_strategy_id': row.get('parent_strategy_id') or row.get('strategy_id'),
                'generator_type': row.get('generator_type'),
                'status': row.get('status'),
                'final_score': committee_review.get('final_score'),
                'decision': committee_review.get('decision'),
                'parameters': row.get('parameters') or {},
            })
        return summary

    # ------------------------------------------------------------------
    # Multi-stage pipeline path
    # ------------------------------------------------------------------

    async def _generate_via_pipeline(
        self,
        db,
        limit: int = 3,
        snapshot: Optional[dict] = None,
        research_task: Optional[dict[str, Any]] = None,
    ) -> list[StrategySpec]:
        """使用多阶段 Pipeline 生成策略候选。"""
        pipeline = get_strategy_pipeline()
        pipeline_result = await pipeline.run_pipeline(
            db=db,
            snapshot=snapshot or {},
            research_task=research_task,
        )

        specs: list[StrategySpec] = []
        for candidate in pipeline_result.candidates[:limit]:
            spec = self._pipeline_candidate_to_spec(candidate, pipeline_result.provenance)
            if spec is not None:
                specs.append(spec)

        stage_requests: list[dict[str, Any]] = []
        llm_attempt_count = 0
        llm_success_count = 0
        llm_elapsed_seconds = 0.0
        last_error = None
        last_error_type = None
        for stage_id, stage_result in pipeline_result.stages.items():
            if stage_result.error and last_error is None:
                last_error = stage_result.error
                last_error_type = stage_result.error.split(":", 1)[0] if ":" in stage_result.error else stage_result.error
            if not getattr(stage_result, "llm_attempted", False):
                continue
            llm_attempt_count += 1
            llm_elapsed_seconds += float(stage_result.elapsed_sec or 0.0)
            if not stage_result.used_fallback:
                llm_success_count += 1
            stage_requests.append(
                {
                    "stage_id": stage_id,
                    "status": "succeeded" if not stage_result.used_fallback else "fallback",
                    "used_fallback": bool(stage_result.used_fallback),
                    "elapsed_seconds": round(float(stage_result.elapsed_sec or 0.0), 4),
                    "prompt_chars": int(stage_result.prompt_chars or 0),
                    "response_chars": int(stage_result.response_chars or 0),
                    "error": stage_result.error,
                }
            )

        if specs:
            external_status = "succeeded" if llm_success_count > 0 else "fallback_only"
        elif pipeline_result.error:
            external_status = "failed"
        elif llm_attempt_count > 0:
            external_status = "non_executable"
        else:
            external_status = "skipped"

        self.last_report = {
            'pipeline_mode': 'staged',
            'pipeline_provenance': pipeline_result.provenance,
            'pipeline_error': pipeline_result.error,
            'selected_count': len(specs),
            'selected_generators': {'pipeline_staged': len(specs)},
            'external_provider': {
                'enabled': True,
                'provider': getattr(self.external_provider.config, 'provider', None),
                'model': getattr(self.external_provider.config, 'model', None),
                'status': external_status,
                'requests': stage_requests,
                'selected_count': len(specs),
                'viable_selected_count': len(specs),
                'fallback_count': len(specs) if external_status == 'fallback_only' else 0,
                'elapsed_seconds': round(llm_elapsed_seconds, 4),
                'last_error_type': last_error_type,
                'last_error': last_error,
            },
        }
        return specs

    @classmethod
    def _pipeline_candidate_to_spec(
        cls,
        candidate: dict[str, Any],
        provenance: dict[str, Any],
    ) -> Optional[StrategySpec]:
        """将 pipeline 产出的 candidate dict 转为 StrategySpec。"""
        if not candidate or not isinstance(candidate, dict):
            return None

        # 尝试通过 DSL 编译获得可执行策略
        compiled: Optional[dict] = None
        dsl = candidate.get('dsl')
        if dsl and isinstance(dsl, dict):
            try:
                compiled = compile_strategy_blueprint(candidate, tune_for_factory=True)
            except Exception:
                compiled = None

        if compiled:
            compiled_meta = dict(compiled.get('metadata') or {})
            params = dict(compiled.get('params') or {})
            strategy_type = str(compiled.get('strategy_type') or 'dsl_rule')
            name = str(compiled.get('name') or candidate.get('name') or 'AI Pipeline 策略')
            description = str(compiled.get('description') or candidate.get('description') or '')
        else:
            # DSL 编译失败时，尝试直接用 strategy_type + params
            strategy_type = str(candidate.get('strategy_type') or 'dsl_rule')
            params = dict(candidate.get('params') or {})
            if not params and dsl:
                params = {'dsl': dsl}
            name = str(candidate.get('name') or 'AI Pipeline 策略')
            description = str(candidate.get('description') or '')
            compiled_meta = {}

        target_symbols = cls._normalize_code_list(candidate.get('target_symbols'))

        if target_symbols and strategy_type == 'dsl_rule':
            dsl_params = dict(params.get('dsl') or {})
            dsl_metadata = dict(dsl_params.get('metadata') or {})
            dsl_metadata['target_symbols'] = list(target_symbols)
            dsl_params['metadata'] = dsl_metadata
            params['dsl'] = dsl_params

        tags = ['pipeline_staged', *(compiled_meta.get('tags') or []), *(candidate.get('tags') or [])]
        if target_symbols:
            tags.append('targeted_universe')

        metadata = {
            **compiled_meta,
            'generator_type': 'pipeline_staged',
            'target_symbols': list(target_symbols),
            'pipeline_provenance': provenance,
            'source_candidate': candidate,
        }

        return StrategySpec(
            strategy_type=strategy_type,
            params=params,
            name=name,
            description=description,
            tags=list(dict.fromkeys(tags)),
            metadata=metadata,
        )

    # ------------------------------------------------------------------
    # Main generate entry point
    # ------------------------------------------------------------------

    async def generate(self, db, limit: int = 3, snapshot: Optional[dict] = None, parent_strategies: Optional[list[dict]] = None, research_task: Optional[dict[str, Any]] = None) -> list[StrategySpec]:
        # 多阶段 pipeline 路径
        _pipeline_fallback_reason: Optional[str] = None
        if PIPELINE_MODE == 'staged' and self.external_provider.is_enabled():
            try:
                staged_specs = await self._generate_via_pipeline(
                    db=db, limit=limit, snapshot=snapshot, research_task=research_task,
                )
                if staged_specs:
                    return staged_specs
                _pipeline_fallback_reason = 'returned_empty'
                logger.info('Pipeline staged mode returned no specs, falling back to monolithic')
            except Exception as exc:
                _pipeline_fallback_reason = f'{type(exc).__name__}: {exc}'
                logger.warning('Pipeline staged mode failed: %s, falling back to monolithic', exc)

        frame = await self._build_market_frame(db, research_task=research_task)
        frame_source = 'primary_market_frame' if frame is not None and not frame.empty else 'none'
        requested_limit = max(1, min(int(limit or 3), 10))
        history_summary = await self._recent_experiments(db, parent_strategies=parent_strategies)
        research_context = await self._build_research_context(
            db,
            snapshot or {},
            parent_strategies=parent_strategies,
            history_summary=history_summary,
            research_task=research_task,
        )
        frame_cache = await self._build_symbol_frame_cache(db, research_context=research_context, research_task=research_task)
        if (frame is None or frame.empty) and frame_cache:
            for cached_frame in frame_cache.values():
                if cached_frame is not None and not cached_frame.empty:
                    frame = cached_frame.tail(120).copy()
                    frame_source = 'research_context_frame_cache'
                    break
        if frame is None or frame.empty:
            synthetic_frame = self._build_synthetic_market_frame(research_context)
            if synthetic_frame is not None and not synthetic_frame.empty:
                frame = synthetic_frame
                frame_source = 'synthetic_research_context_frame'
        report: dict[str, Any] = {
            'requested_limit': requested_limit,
            'market_frame_ready': bool(frame is not None and not frame.empty),
            'market_frame_rows': int(len(frame)) if frame is not None and not frame.empty else 0,
            'market_frame_source': frame_source,
            'research_context': research_context,
            'research_context_summary': self._summarize_research_context(research_context),
            'external_provider': {
                'enabled': bool(self.external_provider.is_enabled()),
                'provider': getattr(self.external_provider.config, 'provider', None),
                'model': getattr(self.external_provider.config, 'model', None),
                'status': 'skipped',
                'request_limits': [],
                'requests': [],
                'selected_count': 0,
                'viable_selected_count': 0,
                'fallback_count': 0,
                'analysis': {},
            },
            'selected_count': 0,
            'selected_generators': {},
            'research_task': dict(research_task or {}),
        }
        external_specs: list[StrategySpec] = []
        fallback_external_specs: list[StrategySpec] = []
        if frame is not None and not frame.empty and self.external_provider.is_enabled():
            base_request_limit = max(2, min(int(limit or 3), 3))
            request_limits = [base_request_limit for _ in range(max(1, min(int(LLM_FAN_OUT_COUNT or 1), 4)))]
            report['external_provider']['request_limits'] = list(request_limits)
            last_exc: Optional[Exception] = None
            successful_request_without_specs = False
            external_started_at = time.perf_counter()
            request_results = await asyncio.gather(*[
                self._run_external_provider_request(
                    snapshot=snapshot or {},
                    frame=frame,
                    frame_cache=frame_cache,
                    research_context=research_context,
                    parent_strategies=list(parent_strategies or []),
                    history_summary=history_summary,
                    research_task=research_task,
                    request_limit=request_limit,
                    request_index=request_index,
                )
                for request_index, request_limit in enumerate(request_limits, 1)
            ])
            aggregated_viable_specs: list[StrategySpec] = []
            aggregated_all_specs: list[StrategySpec] = []
            for result in sorted(request_results, key=lambda item: int(item.get('request_index') or 0)):
                report['external_provider']['requests'].append(dict(result.get('request_report') or {}))
                successful_request_without_specs = successful_request_without_specs or bool(result.get('successful_without_specs'))
                aggregated_viable_specs.extend(list(result.get('viable_specs') or []))
                aggregated_all_specs.extend(list(result.get('all_specs') or []))
                analysis = dict(result.get('analysis') or {})
                if analysis and not report['external_provider']['analysis']:
                    report['external_provider']['analysis'] = analysis
                if result.get('status') == 'failed' and result.get('exception') is not None:
                    last_exc = result.get('exception')
            aggregated_viable_specs = self._dedupe_specs(sorted(aggregated_viable_specs, key=self._spec_preflight_score, reverse=True))
            aggregated_all_specs = self._dedupe_specs(sorted(aggregated_all_specs, key=self._spec_preflight_score, reverse=True))
            if aggregated_viable_specs:
                external_specs = aggregated_viable_specs[:limit]
                selected_keys = {
                    (str(spec.strategy_type or ''), json.dumps(spec.params or {}, sort_keys=True, ensure_ascii=False, default=str))
                    for spec in external_specs
                }
                fallback_external_specs = [
                    spec for spec in aggregated_all_specs
                    if (
                        str(spec.strategy_type or ''),
                        json.dumps(spec.params or {}, sort_keys=True, ensure_ascii=False, default=str),
                    ) not in selected_keys
                ]
            elif aggregated_all_specs:
                fallback_external_specs = aggregated_all_specs[:limit]
            report['external_provider']['elapsed_seconds'] = round(time.perf_counter() - external_started_at, 4)
            report['external_provider']['viable_selected_count'] = len(external_specs)
            report['external_provider']['fallback_count'] = len(fallback_external_specs)
            if external_specs:
                report['external_provider']['status'] = 'succeeded'
            elif fallback_external_specs:
                report['external_provider']['status'] = 'fallback_only'
            elif successful_request_without_specs:
                report['external_provider']['status'] = 'non_executable'
                report['external_provider']['last_error_type'] = 'NoExecutableCandidates'
                report['external_provider']['last_error'] = 'external llm returned candidates but none compiled into executable strategies'
            elif last_exc is not None:
                report['external_provider']['status'] = 'failed'
                last_metrics = dict(getattr(last_exc, 'metrics', {}) or {})
                report['external_provider']['last_error_type'] = last_metrics.get('last_error_type') or last_exc.__class__.__name__
                report['external_provider']['last_error'] = last_metrics.get('last_error') or str(last_exc) or last_exc.__class__.__name__
            if self.external_provider.config.strict and last_exc is not None and not external_specs and not fallback_external_specs:
                self.last_report = report
                raise last_exc

        if frame is None or frame.empty:
            selected = (external_specs or fallback_external_specs)[:limit]
            generator_counts: dict[str, int] = {}
            for spec in selected:
                generator_type = str(spec.metadata.get('generator_type') or 'unknown')
                generator_counts[generator_type] = generator_counts.get(generator_type, 0) + 1
            report['selected_count'] = len(selected)
            report['selected_generators'] = generator_counts
            report['external_provider']['selected_count'] = generator_counts.get('external_llm', 0)
            self.last_report = report
            return selected
        local_specs: list[StrategySpec] = []
        targeted_research = bool(self._normalize_code_list((research_task or {}).get('target_symbols')))
        allow_local_specs = not targeted_research or (not external_specs and not fallback_external_specs)
        if allow_local_specs:
            local_limit = limit
            if targeted_research and str((research_task or {}).get('task_source') or '').strip().lower() == 'event_driven':
                local_limit = 1
            raw = self.miner.generate_factor_candidates(frame, news_data=None, num_candidates=max(local_limit, 3))
            raw = sorted(
                raw,
                key=lambda item: self._local_category_rank(str((item or {}).get('category') or 'custom').strip().lower(), research_task=research_task),
            )
            for candidate in raw:
                spec = self._local_candidate_to_spec(candidate, research_task=research_task)
                if spec is not None:
                    local_specs.append(spec)
                if len(local_specs) >= local_limit:
                    break
        if len(external_specs) >= limit:
            selected = external_specs[:limit]
            generator_counts: dict[str, int] = {}
            for spec in selected:
                generator_type = str(spec.metadata.get('generator_type') or 'unknown')
                generator_counts[generator_type] = generator_counts.get(generator_type, 0) + 1
            report['selected_count'] = len(selected)
            report['selected_generators'] = generator_counts
            report['external_provider']['selected_count'] = generator_counts.get('external_llm', 0)
            self.last_report = report
            return selected
        merged: list[StrategySpec] = []
        seen = set()
        if self.external_provider.config.strict:
            fallback_order = [*external_specs, *fallback_external_specs, *local_specs]
        else:
            preferred_external = fallback_external_specs[:1]
            remaining_external = fallback_external_specs[1:]
            fallback_order = [*external_specs, *preferred_external, *local_specs, *remaining_external]
        for spec in fallback_order:
            key = (spec.strategy_type, json.dumps(spec.params or {}, sort_keys=True, ensure_ascii=False, default=str))
            if key in seen:
                continue
            seen.add(key)
            merged.append(spec)
            if len(merged) >= limit:
                break
        generator_counts: dict[str, int] = {}
        for spec in merged:
            generator_type = str(spec.metadata.get('generator_type') or 'unknown')
            generator_counts[generator_type] = generator_counts.get(generator_type, 0) + 1
        report['selected_count'] = len(merged)
        report['selected_generators'] = generator_counts
        report['external_provider']['selected_count'] = generator_counts.get('external_llm', 0)
        if _pipeline_fallback_reason:
            report['pipeline_staged_fallback_reason'] = _pipeline_fallback_reason
            pipeline_report = getattr(self, 'last_report', None) or {}
            report['pipeline_staged_provenance'] = pipeline_report.get('pipeline_provenance')
            report['pipeline_staged_error'] = pipeline_report.get('pipeline_error')
        self.last_report = report
        return merged
