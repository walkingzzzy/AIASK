"""外部 AI 策略生成 provider。"""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
from dataclasses import dataclass
from typing import Any, Optional

import httpx
import pandas as pd
from strategy_factory.domain.targets import _apply_target_symbol_policy, _normalize_research_task_contract

from ..env_loader import load_mcp_env


class StrategyLLMRequestError(RuntimeError):
    def __init__(self, message: str, *, metrics: Optional[dict[str, Any]] = None):
        super().__init__(message)
        self.metrics = dict(metrics or {})


@dataclass
class StrategyLLMConfig:
    enabled: bool = False
    provider: str = "openai_compatible"
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    timeout_sec: float = 30.0
    connect_timeout_sec: float = 8.0
    write_timeout_sec: float = 10.0
    pool_timeout_sec: float = 5.0
    temperature: float = 0.3
    max_tokens: int = 900
    retry_count: int = 2
    retry_backoff_sec: float = 1.0
    initial_compact_level: int = 0
    recent_timeout_minimal_streak: int = 1
    recent_timeout_cooldown_sec: float = 600.0
    max_concurrency: int = 3
    strict: bool = False

    @classmethod
    def from_env(cls) -> "StrategyLLMConfig":
        load_mcp_env(override=False, only_prefixes=('STRATEGY_LLM_',))
        enabled = str(os.getenv("STRATEGY_LLM_ENABLED", "")).strip().lower() in {"1", "true", "yes", "on"}
        timeout_sec = float(os.getenv("STRATEGY_LLM_TIMEOUT_SEC", "30") or 30)
        initial_compact_level = max(0, min(2, int(os.getenv("STRATEGY_LLM_INITIAL_COMPACT_LEVEL", "0") or 0)))
        recent_timeout_minimal_streak = max(1, min(8, int(os.getenv("STRATEGY_LLM_RECENT_TIMEOUT_MINIMAL_STREAK", "1") or 1)))
        recent_timeout_cooldown_sec = max(0.0, float(os.getenv("STRATEGY_LLM_RECENT_TIMEOUT_COOLDOWN_SEC", "600") or 600))
        return cls(
            enabled=enabled,
            provider=str(os.getenv("STRATEGY_LLM_PROVIDER", "openai_compatible") or "openai_compatible"),
            base_url=str(os.getenv("STRATEGY_LLM_BASE_URL", "") or "").strip(),
            api_key=str(os.getenv("STRATEGY_LLM_API_KEY", "") or "").strip(),
            model=str(os.getenv("STRATEGY_LLM_MODEL", "") or "").strip(),
            timeout_sec=timeout_sec,
            connect_timeout_sec=float(os.getenv("STRATEGY_LLM_CONNECT_TIMEOUT_SEC", str(min(timeout_sec, 8.0))) or min(timeout_sec, 8.0)),
            write_timeout_sec=float(os.getenv("STRATEGY_LLM_WRITE_TIMEOUT_SEC", str(min(timeout_sec, 10.0))) or min(timeout_sec, 10.0)),
            pool_timeout_sec=float(os.getenv("STRATEGY_LLM_POOL_TIMEOUT_SEC", str(min(timeout_sec, 5.0))) or min(timeout_sec, 5.0)),
            temperature=float(os.getenv("STRATEGY_LLM_TEMPERATURE", "0.3") or 0.3),
            max_tokens=max(128, int(os.getenv("STRATEGY_LLM_MAX_TOKENS", "900") or 900)),
            retry_count=max(0, int(os.getenv("STRATEGY_LLM_RETRY_COUNT", "2") or 2)),
            retry_backoff_sec=max(0.0, float(os.getenv("STRATEGY_LLM_RETRY_BACKOFF_SEC", "1.0") or 1.0)),
            initial_compact_level=initial_compact_level,
            recent_timeout_minimal_streak=recent_timeout_minimal_streak,
            recent_timeout_cooldown_sec=recent_timeout_cooldown_sec,
            max_concurrency=max(1, min(8, int(os.getenv("STRATEGY_LLM_MAX_CONCURRENCY", "3") or 3))),
            strict=str(os.getenv("STRATEGY_LLM_STRICT_MODE", "")).strip().lower() in {"1", "true", "yes", "on"},
        )


class StrategyLLMProvider:
    def __init__(self, config: Optional[StrategyLLMConfig] = None):
        self.config = config or StrategyLLMConfig.from_env()
        self._recent_timeout_streak = 0
        self._recent_timeout_cooldown_until = 0.0
        self._last_failure_type: Optional[str] = None
        self._client = httpx.AsyncClient(follow_redirects=True, http2=False)
        self._request_semaphore = asyncio.Semaphore(max(1, int(self.config.max_concurrency or 1)))

    async def close(self) -> None:
        """关闭共享 HTTP 连接池。"""
        try:
            await self._client.aclose()
        except Exception:
            pass

    def is_enabled(self) -> bool:
        return bool(self.config.enabled and self.config.base_url and self.config.api_key and self.config.model)

    def _endpoint(self) -> str:
        base = self.config.base_url.rstrip("/")
        if base.endswith("/chat/completions"):
            return base
        return f"{base}/chat/completions"

    @staticmethod
    def _error_text(exc: Exception) -> str:
        text = str(exc or "").strip()
        return text or exc.__class__.__name__

    @staticmethod
    def _round_number(value: Any, digits: int = 6) -> Any:
        try:
            if isinstance(value, bool):
                return value
            if isinstance(value, int):
                return value
            if isinstance(value, float):
                return round(value, digits)
        except Exception:
            return value
        return value

    @staticmethod
    def _compact_text(value: Any, limit: int = 120) -> str:
        text = str(value or '').strip()
        if len(text) <= limit:
            return text
        return text[: max(0, limit - 1)] + '...'

    @staticmethod
    def _extract_json_text(text: str) -> str:
        raw = str(text or "").strip()
        if not raw:
            return raw
        fence = re.search(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", raw, flags=re.S)
        if fence:
            return fence.group(1).strip()
        if raw.startswith("{") or raw.startswith("["):
            return raw
        start = raw.find("{")
        end = raw.rfind("}")
        if start >= 0 and end > start:
            return raw[start : end + 1]
        start = raw.find("[")
        end = raw.rfind("]")
        if start >= 0 and end > start:
            return raw[start : end + 1]
        return raw

    @staticmethod
    def _extract_content(payload: dict[str, Any]) -> str:
        choices = list(payload.get("choices") or [])
        if choices:
            message = dict((choices[0] or {}).get("message") or {})
            content = message.get("content")
            if isinstance(content, list):
                return "\n".join(str(item.get("text") or item) for item in content)
            return str(content or "")
        output = list(payload.get("output") or [])
        parts = []
        for item in output:
            for content in list((item or {}).get("content") or []):
                text = content.get("text") if isinstance(content, dict) else None
                if text:
                    parts.append(str(text))
        return "\n".join(parts)

    @staticmethod
    def _normalize_analysis(analysis: Any) -> dict[str, Any]:
        if not isinstance(analysis, dict):
            return {}
        normalized: dict[str, Any] = {}
        for key in ("market_regime", "style_bias", "hypothesis", "selection_notes", "risk_focus", "evidence", "universe_view", "selection_plan", "trade_plan"):
            value = analysis.get(key)
            if value is None:
                continue
            if isinstance(value, list):
                normalized[key] = [str(item) for item in value[:6]]
            elif isinstance(value, dict):
                normalized[key] = value
            else:
                normalized[key] = str(value)
        for key, value in analysis.items():
            if key not in normalized and len(normalized) < 10:
                normalized[key] = value
        return normalized

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
    def _normalize_candidate_payload(cls, candidate: Any, research_task: Optional[dict[str, Any]] = None) -> Optional[dict[str, Any]]:
        if not isinstance(candidate, dict):
            return None
        normalized_task = _normalize_research_task_contract(research_task)
        research_symbols = cls._normalize_code_list(normalized_task.get('target_symbols'), limit=8)
        dsl_payload = candidate.get('dsl')
        if not isinstance(dsl_payload, dict):
            dsl_payload = {
                'version': candidate.get('version'),
                'timeframe': candidate.get('timeframe'),
                'entry': candidate.get('entry'),
                'exit': candidate.get('exit'),
                'metadata': candidate.get('metadata') or {},
                'risk_rules': candidate.get('risk_rules') or {},
            }
        if not isinstance(dsl_payload, dict) or not dsl_payload.get('entry'):
            return None
        dsl = dict(dsl_payload)
        metadata = dict(dsl.get('metadata') or {})
        raw_target_symbols = cls._normalize_code_list([
            candidate.get('target_symbols'),
            candidate.get('stock_pool'),
            metadata.get('target_symbols'),
            metadata.get('stock_pool'),
        ], limit=8)
        stock_pool_payload = candidate.get('stock_pool')
        fallback_symbols = cls._normalize_code_list([
            stock_pool_payload,
            metadata.get('stock_pool'),
            research_symbols,
        ], limit=8)
        policy_result = _apply_target_symbol_policy(
            raw_target_symbols,
            normalized_task,
            fallback_symbols=fallback_symbols,
            limit=8,
        )
        target_symbols = list(policy_result.get('target_symbols') or [])
        stock_pool_payload = candidate.get('stock_pool')
        stock_pool_symbols = cls._normalize_code_list([
            stock_pool_payload,
            metadata.get('stock_pool'),
            target_symbols,
        ], limit=8)
        stock_pool: dict[str, Any] = {
            'selection_mode': 'explicit' if stock_pool_symbols else 'screened',
            'symbols': stock_pool_symbols,
        }
        if isinstance(stock_pool_payload, dict):
            selection_mode = str(stock_pool_payload.get('selection_mode') or stock_pool_payload.get('mode') or stock_pool.get('selection_mode') or '').strip()
            if selection_mode:
                stock_pool['selection_mode'] = selection_mode
            filters = dict(stock_pool_payload.get('filters') or {})
            if filters:
                stock_pool['filters'] = filters
            rationale = stock_pool_payload.get('rationale')
            if rationale not in (None, ''):
                stock_pool['rationale'] = str(rationale)
        constraint_check = dict(policy_result.get('constraint_check') or {})
        if (
            constraint_check.get('expansion_applied')
            and stock_pool_symbols
            and not str(stock_pool.get('rationale') or '').strip()
        ):
            stock_pool['rationale'] = str(
                constraint_check.get('expansion_reason')
                or constraint_check.get('constraint_violation')
                or 'expanded_from_candidate_universe'
            )
        metadata['target_symbols'] = list(target_symbols)
        metadata['stock_pool'] = stock_pool
        metadata['constraint_check'] = constraint_check
        metadata['targeting_policy'] = {
            'target_symbol_policy': normalized_task.get('target_symbol_policy'),
            'universe_expansion_policy': normalized_task.get('universe_expansion_policy'),
            'validation_focus': normalized_task.get('validation_focus'),
        }
        dsl['metadata'] = metadata
        dsl = cls._sanitize_dsl_for_candidate(dsl)
        tags = candidate.get('tags') or []
        if not isinstance(tags, list):
            tags = [tags]
        strategy_type = str(candidate.get('strategy_type') or 'dsl_rule').strip() or 'dsl_rule'
        hypothesis = str(
            candidate.get('hypothesis')
            or candidate.get('rationale')
            or candidate.get('description')
            or ''
        ).strip()
        holding_horizon = dict(candidate.get('holding_horizon') or {})
        if not holding_horizon:
            holding_horizon = dict(normalized_task.get('holding_window') or {})
        risk_rules = dict(candidate.get('risk_rules') or dsl.get('risk_rules') or {})
        if not risk_rules:
            max_holding_days = int(holding_horizon.get('max_days') or 0)
            risk_rules = {
                'stop_loss_pct': 0.08 if normalized_task.get('task_source') == 'event_driven' else 0.1,
                'take_profit_pct': 0.18 if normalized_task.get('task_source') == 'event_driven' else 0.2,
                'max_holding_days': max_holding_days or 20,
            }
        dsl['risk_rules'] = dict(risk_rules)
        rebalance_rule = dict(candidate.get('rebalance_rule') or {})
        if not rebalance_rule:
            rebalance_rule = {'mode': 'event_driven_hold' if normalized_task.get('task_source') == 'event_driven' else 'signal_rebalance'}
        trade_plan = candidate.get('trade_plan')
        if isinstance(trade_plan, dict):
            normalized_trade_plan = dict(trade_plan)
        elif trade_plan not in (None, '', [], {}):
            normalized_trade_plan = {'summary': str(trade_plan)}
        else:
            normalized_trade_plan = {'entry_bias': 'trend_follow' if normalized_task.get('task_source') == 'event_driven' else 'signal_confirmed'}
        execution_assumptions = dict(candidate.get('execution_assumptions') or {})
        if not execution_assumptions:
            execution_assumptions = {
                'commission_rate': 0.00025,
                'slippage_bps': 8 if normalized_task.get('task_source') == 'event_driven' else 5,
                'tradability_filter': True,
                'slippage_model': 'fixed',
            }
        execution_notes = candidate.get('execution_notes')
        if execution_notes in (None, '', [], {}):
            normalized_execution_notes = 'prefer liquid session execution with tradability filter'
        elif isinstance(execution_notes, list):
            normalized_execution_notes = [str(item) for item in execution_notes[:3] if str(item or '').strip()]
        else:
            normalized_execution_notes = str(execution_notes)
        portfolio_spec = dict(candidate.get('portfolio_spec') or {})
        if not portfolio_spec:
            portfolio_spec = {
                'position_assumption': 'equal_weight_proxy' if len(target_symbols) > 1 else 'single_name_full_notional',
                'target_weight_scheme': 'equal_weight' if len(target_symbols) > 1 else 'single_name',
            }
        position_sizing = candidate.get('position_sizing')
        if isinstance(position_sizing, dict):
            normalized_position_sizing = dict(position_sizing)
        elif position_sizing not in (None, '', [], {}):
            normalized_position_sizing = {'summary': str(position_sizing)}
        else:
            normalized_position_sizing = {
                'mode': portfolio_spec.get('target_weight_scheme') or 'equal_weight',
                'position_assumption': portfolio_spec.get('position_assumption'),
            }
        validation_profile = dict(candidate.get('validation_profile') or {})
        if not validation_profile:
            validation_profile = {
                'profile': 'event_trade_validation' if normalized_task.get('validation_focus') == 'event_target_only' else 'trade_rule_validation',
                'validation_focus': normalized_task.get('validation_focus'),
                'primary_validation_layer': 'target' if normalized_task.get('validation_focus') == 'event_target_only' else 'combined',
            }
        normalized: dict[str, Any] = {
            'name': str(candidate.get('name') or '外部 AI 候选策略'),
            'strategy_type': strategy_type,
            'target_symbols': list(target_symbols),
            'stock_pool': stock_pool,
            'dsl': dsl,
            'hypothesis': hypothesis,
            'holding_horizon': holding_horizon,
            'trade_plan': normalized_trade_plan,
            'risk_rules': dict(risk_rules),
            'position_sizing': normalized_position_sizing,
            'execution_notes': normalized_execution_notes,
            'rebalance_rule': rebalance_rule,
            'portfolio_spec': portfolio_spec,
            'execution_assumptions': execution_assumptions,
            'validation_profile': validation_profile,
            'targeting_policy': dict(metadata.get('targeting_policy') or {}),
            'constraint_check': constraint_check,
            'tags': [str(item) for item in tags if str(item or '').strip()][:8],
        }
        description = candidate.get('description')
        if description not in (None, ''):
            normalized['description'] = str(description)
        rationale = candidate.get('rationale')
        if rationale not in (None, ''):
            normalized['rationale'] = str(rationale)
        selection_logic = candidate.get('selection_logic')
        if selection_logic not in (None, '', [], {}):
            if isinstance(selection_logic, list):
                normalized['selection_logic'] = [str(item) for item in selection_logic[:4]]
            else:
                normalized['selection_logic'] = [str(selection_logic)]
        return normalized

    @classmethod
    def _minimal_output_example(cls, target_symbols: list[str]) -> dict[str, Any]:
        symbols = cls._normalize_code_list(target_symbols, limit=2)
        if not symbols:
            symbols = ['000300']
        stock_pool = {
            'selection_mode': 'explicit',
            'symbols': list(symbols),
        }
        return {
            'candidates': [{
                'name': 'single_stock_trend_follow',
                'strategy_type': 'dsl_rule',
                'hypothesis': '目标股票在中短期趋势延续中更容易产生顺势机会。',
                'holding_horizon': {'max_days': 10},
                'trade_plan': {'entry_bias': 'trend_follow', 'exit_bias': 'signal_or_time_stop'},
                'risk_rules': {'stop_loss_pct': 0.08, 'take_profit_pct': 0.18, 'max_holding_days': 10},
                'position_sizing': {'mode': 'single_name', 'position_assumption': 'single_name_full_notional'},
                'execution_notes': 'prefer liquid session execution',
                'rebalance_rule': {'mode': 'signal_rebalance'},
                'portfolio_spec': {'position_assumption': 'single_name_full_notional', 'target_weight_scheme': 'single_name'},
                'execution_assumptions': {'commission_rate': 0.00025, 'slippage_bps': 5, 'tradability_filter': True, 'slippage_model': 'fixed'},
                'validation_profile': {'profile': 'trade_rule_validation', 'validation_focus': 'target_plus_representative'},
                'target_symbols': list(symbols),
                'stock_pool': stock_pool,
                'dsl': {
                    'version': '1.0',
                    'timeframe': 'daily',
                    'entry': {
                        'any': [{
                            'op': 'cross_above',
                            'left': {'field': 'close'},
                            'right': {'indicator': 'sma', 'field': 'close', 'window': 10},
                        }],
                    },
                    'exit': {
                        'any': [{
                            'op': 'cross_below',
                            'left': {'field': 'close'},
                            'right': {'indicator': 'sma', 'field': 'close', 'window': 10},
                        }],
                    },
                    'metadata': {
                        'target_symbols': list(symbols),
                        'stock_pool': stock_pool,
                    },
                },
                'tags': ['external_llm', 'daily_dsl'],
            }],
        }

    @classmethod
    def _sanitize_expr_for_candidate(cls, expr: Any) -> dict[str, Any]:
        if not isinstance(expr, dict):
            return dict(expr or {}) if isinstance(expr, dict) else {}
        payload = dict(expr)
        indicator = str(payload.get('indicator') or '').strip().lower()
        if indicator:
            field = str(payload.get('field') or 'close').strip().lower() or 'close'
            if field not in {'open', 'high', 'low', 'close', 'volume'}:
                field = 'close'
            payload['field'] = field
        field = str(payload.get('field') or '').strip().lower()
        if field in {'open', 'high', 'low', 'close', 'volume'}:
            payload['field'] = field
        return payload

    @classmethod
    def _sanitize_condition_for_candidate(cls, node: Any) -> dict[str, Any]:
        if not isinstance(node, dict):
            return {}
        if 'all' in node:
            return {'all': [cls._sanitize_condition_for_candidate(item) for item in list(node.get('all') or []) if cls._sanitize_condition_for_candidate(item)]}
        if 'any' in node:
            return {'any': [cls._sanitize_condition_for_candidate(item) for item in list(node.get('any') or []) if cls._sanitize_condition_for_candidate(item)]}
        if 'not' in node:
            child = cls._sanitize_condition_for_candidate(node.get('not'))
            return {'not': child} if child else {}
        op = str(node.get('op') or '').strip().lower()
        left = cls._sanitize_expr_for_candidate(node.get('left') or {})
        right = cls._sanitize_expr_for_candidate(node.get('right') or {})
        left_indicator = str(left.get('indicator') or '').strip().lower()
        right_indicator = str(right.get('indicator') or '').strip().lower()
        if left_indicator == 'volume_ratio' and 'value' not in right and right_indicator != 'volume_ratio':
            right = {'value': 1.0}
        elif left_indicator == 'rsi' and 'value' not in right and right_indicator != 'rsi':
            right = {'value': 60.0 if op in {'gt', 'gte', 'cross_above'} else 40.0}
        elif left_indicator == 'roc' and 'value' not in right and right_indicator != 'roc':
            right = {'value': 0.01 if op in {'gt', 'gte', 'cross_above'} else -0.01}
        elif left_indicator == 'zscore' and 'value' not in right and right_indicator != 'zscore':
            right = {'value': 0.5 if op in {'gt', 'gte', 'cross_above'} else -0.5}
        return {'op': op, 'left': left, 'right': right}

    @classmethod
    def _sanitize_dsl_for_candidate(cls, dsl: dict[str, Any]) -> dict[str, Any]:
        payload = dict(dsl or {})
        payload['entry'] = cls._sanitize_condition_for_candidate(payload.get('entry'))
        payload['exit'] = cls._sanitize_condition_for_candidate(payload.get('exit'))
        return payload

    @staticmethod
    def _summarize_market_frame(frame: Optional[pd.DataFrame]) -> dict[str, Any]:
        if frame is None or frame.empty:
            return {"rows": 0}
        compact = frame.tail(min(len(frame), 120)).copy()
        result = {"rows": int(len(compact)), "columns": [str(col) for col in compact.columns.tolist()]}
        if "close" in compact.columns:
            close = pd.to_numeric(compact["close"], errors="coerce").dropna()
            if len(close) >= 2:
                result["close"] = {
                    "latest": float(close.iloc[-1]),
                    "period_return_20": float(close.iloc[-1] / max(close.iloc[max(0, len(close) - 20)], 1e-9) - 1.0) if len(close) >= 20 else float(close.iloc[-1] / max(close.iloc[0], 1e-9) - 1.0),
                    "period_return_full": float(close.iloc[-1] / max(close.iloc[0], 1e-9) - 1.0),
                    "volatility_20": float(close.pct_change().dropna().tail(20).std() if len(close) > 20 else close.pct_change().dropna().std() or 0.0),
                }
        if "volume" in compact.columns:
            volume = pd.to_numeric(compact["volume"], errors="coerce").dropna()
            if len(volume) >= 5:
                result["volume"] = {
                    "latest": float(volume.iloc[-1]),
                    "mean_20": float(volume.tail(20).mean()),
                }
        return result

    @staticmethod
    def _normalize_limit(limit: int) -> int:
        return max(1, min(int(limit or 3), 8))

    @staticmethod
    def _prompt_profile_name(compact_level: int) -> str:
        if compact_level <= 0:
            return "normal"
        if compact_level == 1:
            return "compact"
        return "minimal"

    @classmethod
    def _compact_snapshot(cls, snapshot: dict[str, Any], compact_level: int = 0) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        for key in (
            "date",
            "fear_greed_index",
            "fg_level",
            "listed_count",
            "incubating_count",
            "degraded",
            "margin_5d_change_pct",
            "north_fund_3d_net",
            "factor_ic",
            "factor_ic_trend",
        ):
            if key in snapshot and snapshot.get(key) is not None:
                payload[key] = cls._round_number(snapshot.get(key), digits=4)

        hot_limit = 4 if compact_level <= 0 else 2
        cold_limit = 3 if compact_level <= 0 else 2
        if snapshot.get("hot_sectors"):
            payload["hot_sectors"] = [str(item) for item in list(snapshot.get("hot_sectors") or [])[:hot_limit]]
        if snapshot.get("cold_sectors"):
            payload["cold_sectors"] = [str(item) for item in list(snapshot.get("cold_sectors") or [])[:cold_limit]]

        category_counts = snapshot.get("category_counts") or {}
        if isinstance(category_counts, dict) and category_counts:
            sorted_items = sorted(category_counts.items(), key=lambda item: item[1], reverse=True)
            payload["category_counts"] = {str(key): int(value) for key, value in sorted_items[: max(2, 5 - compact_level)]}

        completeness = dict(snapshot.get("completeness") or {})
        if completeness:
            payload["data_quality"] = {
                "completion_ratio": cls._round_number(completeness.get("completion_ratio") or 0.0, digits=4),
                "missing_sources": [
                    str(item) for item in list(completeness.get("missing_sources") or [])[: max(1, 3 - min(compact_level, 2))]
                ],
            }

        failure_reasons = list(snapshot.get("failure_reasons") or [])
        if failure_reasons:
            payload["failure_reasons"] = [
                {
                    "source": str((item or {}).get("source") or ""),
                    "reason": str((item or {}).get("reason") or ""),
                }
                for item in failure_reasons[: max(1, 2 - min(compact_level, 1))]
            ]
        return payload

    @classmethod
    def _compact_parent_strategies(cls, parent_strategies: list[dict[str, Any]], compact_level: int = 0) -> list[dict[str, Any]]:
        rows = []
        for item in list(parent_strategies or [])[: max(1, 3 - min(compact_level, 1))]:
            rows.append({
                "id": item.get("id"),
                "name": item.get("name"),
                "strategy_type": item.get("strategy_type"),
                "status": item.get("status"),
                "tags": list(item.get("tags") or [])[: max(1, 3 - compact_level)],
            })
        return rows

    @classmethod
    def _compact_history_summary(cls, history_summary: list[dict[str, Any]], compact_level: int = 0) -> list[dict[str, Any]]:
        rows = []
        for item in list(history_summary or [])[: max(2, 6 - compact_level * 2)]:
            rows.append({
                "parent_strategy_id": item.get("parent_strategy_id"),
                "generator_type": item.get("generator_type"),
                "status": item.get("status"),
                "decision": item.get("decision"),
                "final_score": cls._round_number(item.get("final_score"), digits=4),
            })
        return rows

    @classmethod
    def _compact_symbol_insight(cls, item: dict[str, Any], compact_level: int = 0) -> dict[str, Any]:
        payload = {
            "code": item.get("code"),
            "name": item.get("name"),
            "industry": item.get("industry"),
            "close": cls._round_number(item.get("close"), digits=4),
            "return_20d": cls._round_number(item.get("return_20d"), digits=4),
            "trend_state": item.get("trend_state"),
        }
        if compact_level <= 1:
            payload["return_5d"] = cls._round_number(item.get("return_5d"), digits=4)
            payload["volume_ratio_20"] = cls._round_number(item.get("volume_ratio_20"), digits=4)
        if compact_level == 0:
            payload["volatility_20d"] = cls._round_number(item.get("volatility_20d"), digits=4)
            payload["price_vs_sma20"] = item.get("price_vs_sma20")
        return payload

    @classmethod
    def _compact_candidate_universe_item(cls, item: dict[str, Any], compact_level: int = 0) -> dict[str, Any]:
        payload = {
            "code": item.get("code"),
            "name": item.get("name"),
            "industry": item.get("industry"),
            "return_20d": cls._round_number(item.get("return_20d"), digits=4),
            "trend_state": item.get("trend_state"),
            "volume_ratio_20": cls._round_number(item.get("volume_ratio_20"), digits=4),
            "screen_score": cls._round_number(item.get("screen_score"), digits=4),
        }
        if compact_level == 0:
            payload["market_cap"] = cls._round_number(item.get("market_cap"), digits=4)
            payload["pe_ratio"] = cls._round_number(item.get("pe_ratio"), digits=4)
            payload["pb_ratio"] = cls._round_number(item.get("pb_ratio"), digits=4)
            payload["factor_snapshot"] = {str(key): cls._round_number(value, digits=4) for key, value in dict(item.get("factor_snapshot") or {}).items()}
            payload["financial_snapshot"] = {
                "revenue_growth": cls._round_number((item.get("financial_snapshot") or {}).get("revenue_growth"), digits=4),
                "profit_growth": cls._round_number((item.get("financial_snapshot") or {}).get("profit_growth"), digits=4),
                "roe": cls._round_number((item.get("financial_snapshot") or {}).get("roe"), digits=4),
            }
        elif compact_level == 1:
            factor_snapshot = dict(item.get("factor_snapshot") or {})
            if factor_snapshot:
                top_factor_items = list(factor_snapshot.items())[:3]
                payload["factor_snapshot"] = {str(key): cls._round_number(value, digits=4) for key, value in top_factor_items}
        return payload

    @classmethod
    def _compact_research_context(cls, research_context: Optional[dict[str, Any]], compact_level: int = 0) -> dict[str, Any]:
        context = dict(research_context or {})
        market_regime = dict(context.get("market_regime") or {})
        market_breadth = dict(context.get("market_breadth") or {})
        symbol_limit = 4 if compact_level <= 0 else (2 if compact_level == 1 else 1)
        candidate_limit = 8 if compact_level <= 0 else (4 if compact_level == 1 else 2)
        symbols = list(context.get("symbol_insights") or [])[:symbol_limit]
        candidate_universe = list(context.get("candidate_universe") or [])[:candidate_limit]
        population_state = dict(context.get("population_state") or {})
        universe_scan = dict(context.get("universe_scan") or {})
        analysis_scope = dict(context.get("analysis_scope") or {})
        selection_framework = dict(context.get("selection_framework") or {})
        if compact_level >= 2:
            return {
                "market_regime": {
                    "fg_level": market_regime.get("fg_level"),
                    "fear_greed_index": cls._round_number(market_regime.get("fear_greed_index"), digits=4),
                },
                "candidate_universe_symbols": cls._normalize_code_list([
                    [item.get("code") for item in candidate_universe],
                    [item.get("symbol") for item in candidate_universe],
                ], limit=4),
                "symbol_insight_codes": cls._normalize_code_list([
                    [item.get("code") for item in symbols[:1]],
                    [item.get("symbol") for item in symbols[:1]],
                ], limit=2),
            }
        return {
            "market_regime": {
                "fg_level": market_regime.get("fg_level"),
                "fear_greed_index": cls._round_number(market_regime.get("fear_greed_index"), digits=4),
                "hot_sectors": list(market_regime.get("hot_sectors") or [])[: max(2, 4 - compact_level)],
                "cold_sectors": list(market_regime.get("cold_sectors") or [])[: max(1, 3 - compact_level)],
                "factor_ic_trend": dict(list((market_regime.get("factor_ic_trend") or {}).items())[: max(2, 4 - compact_level)]),
            },
            "market_breadth": {
                "symbol_count": market_breadth.get("symbol_count"),
                "trend_up_count": market_breadth.get("trend_up_count"),
                "trend_down_count": market_breadth.get("trend_down_count"),
                "avg_return_20d": cls._round_number(market_breadth.get("avg_return_20d"), digits=4),
                "avg_volatility_20d": cls._round_number(market_breadth.get("avg_volatility_20d"), digits=4),
            },
            "symbol_insights": [cls._compact_symbol_insight(item, compact_level=compact_level) for item in symbols],
            "candidate_universe": [cls._compact_candidate_universe_item(item, compact_level=compact_level) for item in candidate_universe],
            "universe_scan": {
                "total_stock_count": universe_scan.get("total_stock_count"),
                "scanned_stock_count": universe_scan.get("scanned_stock_count"),
                "data_ready_count": universe_scan.get("data_ready_count"),
                "coverage_ratio": cls._round_number(universe_scan.get("coverage_ratio"), digits=4),
                "candidate_universe_count": universe_scan.get("candidate_universe_count"),
                "top_industries": dict(list((universe_scan.get("top_industries") or {}).items())[: max(2, 6 - compact_level)]),
            },
            "analysis_scope": {
                "scan_mode": analysis_scope.get("scan_mode"),
                "scan_limit": analysis_scope.get("scan_limit"),
                "kline_scan_limit": analysis_scope.get("kline_scan_limit"),
                "detail_limit": analysis_scope.get("detail_limit"),
                "candidate_pool_limit": analysis_scope.get("candidate_pool_limit"),
            },
            "selection_framework": {
                "technical": list(selection_framework.get("technical") or [])[:4],
                "fundamental": list(selection_framework.get("fundamental") or [])[:4],
                "factor_names": list(selection_framework.get("factor_names") or [])[:3],
            },
            "population_state": {
                "listed_count": population_state.get("listed_count"),
                "incubating_count": population_state.get("incubating_count"),
                "top_categories": dict(list((population_state.get("top_categories") or {}).items())[: max(2, 5 - compact_level)]),
            },
        }

    @classmethod
    def _compact_market_summary(cls, market_summary: Optional[dict[str, Any]], compact_level: int = 0) -> dict[str, Any]:
        summary = dict(market_summary or {})
        if compact_level < 2:
            return summary
        payload = {"rows": summary.get("rows")}
        close = dict(summary.get("close") or {})
        if close:
            payload["close"] = {
                "latest": cls._round_number(close.get("latest"), digits=4),
                "period_return_20": cls._round_number(close.get("period_return_20"), digits=4),
                "volatility_20": cls._round_number(close.get("volatility_20"), digits=4),
            }
        volume = dict(summary.get("volume") or {})
        if volume:
            payload["volume"] = {
                "latest": cls._round_number(volume.get("latest"), digits=4),
                "mean_20": cls._round_number(volume.get("mean_20"), digits=4),
            }
        return payload

    @classmethod
    def _compact_research_task(cls, research_task: Optional[dict[str, Any]], compact_level: int = 0) -> dict[str, Any]:
        task = _normalize_research_task_contract(research_task)
        compact = {
            "task_id": task.get("task_id"),
            "task_source": task.get("task_source"),
            "opportunity_type": task.get("opportunity_type"),
            "target_symbols": list(task.get("target_symbols") or [])[:5],
            "preferred_strategy_types": list(task.get("preferred_strategy_types") or [])[:4],
            "allowed_strategy_types": list(task.get("allowed_strategy_types") or [])[:6],
            "target_symbol_policy": task.get("target_symbol_policy"),
            "universe_expansion_policy": task.get("universe_expansion_policy"),
            "preference_strength": task.get("preference_strength"),
            "validation_focus": task.get("validation_focus"),
        }
        is_event_driven_task = any(task.get(key) not in (None, "", [], {}) for key in ("event_id", "theme_code", "direction", "horizon"))
        if is_event_driven_task:
            compact.update({
                "event_id": task.get("event_id"),
                "event_type": task.get("event_type"),
                "theme": task.get("theme"),
                "theme_code": task.get("theme_code"),
                "direction": task.get("direction"),
                "horizon": task.get("horizon"),
                "event_window": dict(task.get("event_window") or {}),
                "estimation_window": dict(task.get("estimation_window") or {}),
                "holding_window": dict(task.get("holding_window") or {}),
            })
        if compact_level <= 1:
            compact["theme"] = task.get("theme") or compact.get("theme")
            if task.get("stock_pool"):
                compact["stock_pool"] = task.get("stock_pool")
            if task.get("selection_logic"):
                compact["selection_logic"] = list(task.get("selection_logic") or [])[:3]
            if task.get("focus_industries"):
                compact["focus_industries"] = list(task.get("focus_industries") or [])[:3]
            evidence_bundle = dict(task.get("evidence_bundle") or {})
            if evidence_bundle:
                compact["evidence_summary"] = {
                    "event_summary": cls._compact_text(evidence_bundle.get("event_summary") or task.get("event_summary"), limit=120),
                    "theme_name": evidence_bundle.get("theme_name") or task.get("theme"),
                    "direction": evidence_bundle.get("direction") or task.get("direction"),
                    "horizon": evidence_bundle.get("horizon") or task.get("horizon"),
                    "signal_count": evidence_bundle.get("signal_count"),
                    "top_symbols": cls._normalize_code_list([
                        evidence_bundle.get("target_symbols"),
                        ((evidence_bundle.get("score_summary") or {}).get("top_symbols") if isinstance(evidence_bundle.get("score_summary"), dict) else None),
                    ], limit=4),
                    "supporting_reasons": [
                        cls._compact_text(item, limit=72)
                        for item in list(evidence_bundle.get("supporting_reasons") or [])[:3]
                    ],
                    "score_summary": dict(evidence_bundle.get("score_summary") or {}),
                }
        if compact_level >= 2:
            compact = {
                key: compact.get(key)
                for key in ("task_id", "opportunity_type", "target_symbols")
                if compact.get(key) not in (None, [], {}, "")
            }
        return {key: value for key, value in compact.items() if value not in (None, [], {}, "")}

    @staticmethod
    def _prompt_target_symbol_rule(task: Optional[dict[str, Any]]) -> str:
        policy = str((task or {}).get("target_symbol_policy") or "").strip().lower()
        if policy == "strict_intersection":
            return "strict_intersection_with_research_task"
        if policy == "prefer_intersection":
            return "prefer_intersection_with_research_task"
        return policy or "prefer_intersection_with_research_task"

    @classmethod
    def _build_prompt(
        cls,
        snapshot: dict[str, Any],
        market_summary: dict[str, Any],
        research_context: Optional[dict[str, Any]],
        parent_strategies: list[dict[str, Any]],
        history_summary: list[dict[str, Any]],
        limit: int,
        research_task: Optional[dict[str, Any]] = None,
        compact_level: int = 0,
    ) -> tuple[str, str]:
        requested_limit = cls._normalize_limit(limit)
        profile_name = cls._prompt_profile_name(compact_level)
        normalized_task = _normalize_research_task_contract(research_task)
        prompt_target_symbol_rule = cls._prompt_target_symbol_rule(normalized_task)
        compact_market_summary = cls._compact_market_summary(market_summary, compact_level=compact_level)
        compact_research_context = cls._compact_research_context(research_context, compact_level=compact_level)
        compact_task = cls._compact_research_task(research_task, compact_level=compact_level)

        if compact_level >= 2:
            example_symbols = cls._normalize_code_list([
                compact_task.get('target_symbols'),
                compact_research_context.get('candidate_universe_symbols'),
                compact_research_context.get('symbol_insight_codes'),
            ], limit=2)
            if not example_symbols:
                example_symbols = cls._normalize_code_list((research_task or {}).get('target_symbols'), limit=2)
            output_contract = {
                'root': 'json_object',
                'required': ['candidates'],
                'analysis_fields': [],
                'candidate_fields': ['name', 'strategy_type', 'hypothesis', 'holding_horizon', 'trade_plan', 'risk_rules', 'position_sizing', 'execution_notes', 'rebalance_rule', 'portfolio_spec', 'execution_assumptions', 'validation_profile', 'target_symbols', 'stock_pool', 'dsl', 'tags'],
                'dsl_required_fields': ['version', 'timeframe', 'entry', 'exit', 'metadata'],
                'target_symbol_rule': prompt_target_symbol_rule,
                'prefer_single_high_confidence_candidate': True,
                'candidate_limit': 1,
            }
            system_prompt = ''.join([
                '你是量化策略助手，只返回严格 JSON。',
                '基于 target_symbols 生成 1 个可执行股票日频 DSL candidate。',
                '如果 research_task 提供了 event_id/theme_code/direction/evidence_summary，必须围绕该事件证据输出。',
                '不要 analysis，不要解释，不要 markdown。',
                '返回根对象 {"candidates":[...]}。',
                'candidate 仅保留 name,target_symbols,stock_pool,dsl,tags。',
                'dsl 必须是对象，且必须包含 version,timeframe,entry,exit,metadata。',
                '字段仅限 open/high/low/close/volume；指标优先仅用 sma,ema,roc,rsi,volume_ratio；',
                '条件运算仅限 gt,gte,lt,lte,cross_above,cross_below；组合仅限 all,any,not。',
                '不要使用 highest/lowest/atr/stddev，也不要写 close 与 highest/lowest 的交叉突破。',
                'dsl.metadata 必须回填 target_symbols 和 stock_pool。',
                'volume_ratio 右侧优先用 value≈1.0；rsi 右侧优先用 value 40/60；不要把 volume_ratio/rsi/roc 直接和 open/high/low/close/volume 比较。',
            ])
            user_payload = {
                'task': 'generate_one_stock_dsl_candidate',
                'prompt_profile': profile_name,
                'limit': 1,
                'research_task': compact_task,
                'market_hint': dict(compact_research_context.get('market_regime') or {}),
                'candidate_universe_symbols': list(compact_research_context.get('candidate_universe_symbols') or []),
                'output_contract': output_contract,
                'output_example': cls._minimal_output_example(example_symbols),
            }
            if not user_payload['market_hint']:
                user_payload.pop('market_hint', None)
            if not user_payload['candidate_universe_symbols']:
                user_payload.pop('candidate_universe_symbols', None)
            if not user_payload['research_task']:
                user_payload.pop('research_task', None)
            user_prompt = json.dumps(user_payload, ensure_ascii=False, default=str, separators=(',', ':'))
            return system_prompt, user_prompt

        analysis_fields = ['market_regime', 'style_bias', 'hypothesis', 'evidence', 'risk_focus', 'selection_notes', 'universe_view', 'selection_plan', 'trade_plan']
        analysis_length_rule = 'analysis 每个字段必须短：字符串不超过 60 个字，列表最多 2 项，不要复述输入。' if compact_level >= 1 else 'analysis 需要结构化且基于输入证据。'
        candidate_priority_rule = '优先返回 1 个高置信、可执行候选；不要为了凑数量返回弱候选。' if compact_level >= 1 else '按 limit 返回高质量候选。'
        context_rule = '如果 research_task.target_symbols 与 candidate_universe 有交集，target_symbols 必须只取交集；如果没有交集，才允许退回 candidate_universe。'
        event_rule = '如果 research_task 提供 event_id/theme_code/direction/evidence_summary，必须优先围绕该事件主题、方向和证据构建候选。'
        system_prompt = ''.join([
            '你是量化策略研究员。必须输出严格 JSON，不要输出解释文本。',
            '先基于输入的市场研究上下文给出结构化 analysis，再给出可执行的股票日频策略 DSL 候选。',
            '你拿到的是程序从股票数据库扫描、聚合、压缩后的研究上下文，必须优先使用 candidate_universe 中的真实股票数据。',
            '每个候选策略必须明确目标股票或股票池，不允许只给抽象模板。',
            '如果提供了 research_task，必须围绕该任务的市场机会、行业或目标股票池生成候选，而不是泛化输出。',
            context_rule,
            event_rule,
            '允许字段: open/high/low/close/volume。',
            '允许指标: sma, ema, roc, rsi, stddev, zscore, highest, lowest, volume_ratio, atr。',
            '允许条件运算: gt, gte, lt, lte, eq, ne, cross_above, cross_below。',
            '允许组合: all, any, not。',
            '优先生成可中等频率触发的策略：最近一年通常至少 1-6 次完整交易，不要只有单边长期持有。',
            'entry/exit 各自尽量不超过 2-3 个子条件，避免过度稀疏和过拟合。',
            '窗口优先 3-30 日；volume_ratio 阈值优先 0.95-1.10；ROC 阈值绝对值优先 0.3%-3%；RSI 优先 35/65 或 40/60 一类稳健区间。',
                '必须提供明确 exit 规则，并兼顾趋势延续或回撤退出。',
                analysis_length_rule,
                candidate_priority_rule,
                f"analysis 必须包含: {', '.join(analysis_fields)}。",
                '根对象只允许包含 analysis 与 candidates。',
            '每个 candidate 必须包含: name, description, rationale, hypothesis, holding_horizon, trade_plan, risk_rules, position_sizing, execution_notes, rebalance_rule, portfolio_spec, execution_assumptions, validation_profile, target_symbols, stock_pool, selection_logic, dsl, tags。',
            'DSL 条件节点必须使用标准对象格式 {"op":...,"left":...,"right":...}，不要使用 {"gt":[...]} 这类简写。',
            'target_symbols 数量建议 1-5 只；stock_pool 必须包含 selection_mode 与 symbols；dsl.metadata 必须回填 target_symbols 与 stock_pool。',
            '不要生成 Python 代码，不要生成自然语言规则，只能生成 JSON DSL。',
        ])
        output_contract = {
            'root': 'json_object',
            'required': ['analysis', 'candidates'],
            'analysis_fields': analysis_fields,
            'target_symbol_rule': prompt_target_symbol_rule,
            'prefer_single_high_confidence_candidate': compact_level >= 1,
            'candidate_fields': ['name', 'description', 'rationale', 'hypothesis', 'holding_horizon', 'trade_plan', 'risk_rules', 'position_sizing', 'execution_notes', 'rebalance_rule', 'portfolio_spec', 'execution_assumptions', 'validation_profile', 'target_symbols', 'stock_pool', 'selection_logic', 'dsl', 'tags'],
            'task_alignment': ['research_task.theme', 'research_task.opportunity_type', 'research_task.target_symbols', 'research_task.preferred_strategy_types', 'research_task.validation_focus'],
            'max_selection_logic_items': 2 if compact_level >= 1 else 3,
            'max_conditions_per_side': 3,
            'analysis_max_items': 2 if compact_level >= 1 else 4,
        }
        user_payload = {
            'task': 'generate_stock_daily_dsl_candidates',
            'prompt_profile': profile_name,
            'limit': requested_limit,
            'snapshot': cls._compact_snapshot(snapshot or {}, compact_level=compact_level),
            'market_summary': compact_market_summary,
            'research_context': compact_research_context,
            'research_task': compact_task,
            'output_contract': output_contract,
        }
        compact_parents = cls._compact_parent_strategies(parent_strategies, compact_level=compact_level)
        compact_history = cls._compact_history_summary(history_summary, compact_level=compact_level)
        if compact_parents:
            user_payload['parent_strategies'] = compact_parents
        if compact_history:
            user_payload['recent_experiments'] = compact_history
        user_prompt = json.dumps(user_payload, ensure_ascii=False, default=str, separators=(',', ':'))
        return system_prompt, user_prompt

    def _timeout_for_attempt(self, attempt: int, total_attempts: int) -> float:
        base = max(float(self.config.timeout_sec or 0), 5.0)
        if total_attempts <= 1:
            return min(base, 25.0)
        schedule = [min(base, 12.0), min(base, 20.0), min(base, 30.0)]
        timeout_sec = schedule[min(max(attempt - 1, 0), len(schedule) - 1)]
        return max(5.0, timeout_sec)

    def _request_timeout(self, request_timeout_sec: float) -> httpx.Timeout:
        connect_timeout = max(1.0, min(float(self.config.connect_timeout_sec or request_timeout_sec), request_timeout_sec))
        write_timeout = max(1.0, min(float(self.config.write_timeout_sec or request_timeout_sec), request_timeout_sec))
        pool_timeout = max(1.0, min(float(self.config.pool_timeout_sec or request_timeout_sec), request_timeout_sec))
        return httpx.Timeout(connect=connect_timeout, read=request_timeout_sec, write=write_timeout, pool=pool_timeout)

    def _request_limit_for_attempt(self, limit: int, attempt: int, *, initial_compact_level: int = 0) -> int:
        requested_limit = self._normalize_limit(limit)
        base_reduction = 1 if initial_compact_level >= 1 and requested_limit > 1 else 0
        return max(1, requested_limit - base_reduction - max(0, attempt - 1))

    @staticmethod
    def _compact_level_for_attempt(attempt: int, total_attempts: int) -> int:
        index = max(int(attempt or 1) - 1, 0)
        if int(total_attempts or 1) <= 1:
            return 0
        if index == 0:
            return 0
        return 2

    def _max_tokens_for_attempt(self, request_limit: int, compact_level: int) -> int:
        base = max(128, int(self.config.max_tokens or 900))
        analysis_budget = 260 if compact_level <= 0 else (160 if compact_level == 1 else 96)
        candidate_budget = max(1, int(request_limit or 1)) * (220 if compact_level <= 0 else (170 if compact_level == 1 else 140))
        return max(128, min(base, analysis_budget + candidate_budget))

    @staticmethod
    def _is_timeout_like_error(exc: Exception) -> bool:
        return isinstance(exc, (httpx.TimeoutException, httpx.ConnectError, httpx.ReadError, httpx.RemoteProtocolError))

    def _recent_timeout_degrade_state(self) -> tuple[int, Optional[str]]:
        initial_level = max(0, min(int(self.config.initial_compact_level or 0), 2))
        now = time.monotonic()
        if self._recent_timeout_cooldown_until > 0 and self._recent_timeout_cooldown_until <= now:
            self._recent_timeout_streak = 0
            self._recent_timeout_cooldown_until = 0.0
        if self._recent_timeout_streak >= max(1, int(self.config.recent_timeout_minimal_streak or 1)) and self._recent_timeout_cooldown_until > now:
            return max(initial_level, 2), 'recent_timeout'
        return initial_level, None

    def _record_request_failure(self, exc: Exception) -> None:
        self._last_failure_type = exc.__class__.__name__
        if self._is_timeout_like_error(exc):
            self._recent_timeout_streak += 1
            self._recent_timeout_cooldown_until = time.monotonic() + max(0.0, float(self.config.recent_timeout_cooldown_sec or 0.0))

    def _record_request_success(self) -> None:
        self._recent_timeout_streak = 0
        self._recent_timeout_cooldown_until = 0.0
        self._last_failure_type = None

    async def generate_candidates(
        self,
        *,
        snapshot: Optional[dict[str, Any]] = None,
        market_frame: Optional[pd.DataFrame] = None,
        research_context: Optional[dict[str, Any]] = None,
        parent_strategies: Optional[list[dict[str, Any]]] = None,
        history_summary: Optional[list[dict[str, Any]]] = None,
        research_task: Optional[dict[str, Any]] = None,
        limit: int = 3,
    ) -> Optional[dict[str, Any]]:
        if not self.is_enabled():
            return None

        started_at = time.perf_counter()
        requested_limit = self._normalize_limit(limit)
        market_summary = self._summarize_market_frame(market_frame)
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        last_exc: Optional[Exception] = None
        attempts = max(1, int(self.config.retry_count or 0) + 1)
        attempt_reports: list[dict[str, Any]] = []
        initial_compact_level, degrade_reason = self._recent_timeout_degrade_state()
        initial_prompt_profile = self._prompt_profile_name(initial_compact_level)
        effective_attempts = 1 if degrade_reason == 'recent_timeout' else attempts
        client = self._client
        for attempt in range(1, effective_attempts + 1):
            compact_level = max(initial_compact_level, self._compact_level_for_attempt(attempt, effective_attempts))
            request_limit = self._request_limit_for_attempt(requested_limit, attempt, initial_compact_level=initial_compact_level)
            compact_research_context = self._compact_research_context(research_context, compact_level=compact_level)
            system_prompt, user_prompt = self._build_prompt(
                snapshot or {},
                market_summary,
                compact_research_context,
                list(parent_strategies or []),
                list(history_summary or []),
                request_limit,
                research_task=research_task,
                compact_level=compact_level,
            )
            prompt_profile = self._prompt_profile_name(compact_level)
            request_timeout_sec = self._timeout_for_attempt(attempt, effective_attempts)
            if degrade_reason == 'recent_timeout' and attempt == 1:
                request_timeout_sec = max(request_timeout_sec, min(float(self.config.timeout_sec or request_timeout_sec), 15.0))
            max_tokens = self._max_tokens_for_attempt(request_limit, compact_level)
            payload = {
                "model": self.config.model,
                "temperature": self.config.temperature,
                "max_tokens": max_tokens,
                "response_format": {"type": "json_object"},
                "stream": False,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            }
            request_started_at = time.perf_counter()
            try:
                async with self._request_semaphore:
                    response = await client.post(
                        self._endpoint(),
                        headers=headers,
                        json=payload,
                        timeout=self._request_timeout(request_timeout_sec),
                    )
                response.raise_for_status()
                body = response.json()
                content = self._extract_content(body)
                json_text = self._extract_json_text(content)
                data = json.loads(json_text)
                raw_candidates = data.get("candidates") if isinstance(data, dict) else None
                if not isinstance(raw_candidates, list):
                    raise ValueError("external llm response missing candidates")
                analysis = self._normalize_analysis(data.get("analysis") if isinstance(data, dict) else {})
                candidates = []
                for item in raw_candidates:
                    normalized_candidate = self._normalize_candidate_payload(item, research_task=research_task)
                    if normalized_candidate is not None:
                        candidates.append(normalized_candidate)
                if not candidates:
                    raise ValueError("external llm response missing executable candidates")
                selected_candidates = candidates[:requested_limit]
                self._record_request_success()
                request_metrics = {
                    "status": "succeeded",
                    "endpoint": self._endpoint(),
                    "provider": self.config.provider,
                    "model": self.config.model,
                    "requested_limit": requested_limit,
                    "attempt_count": attempt,
                    "prompt_profile": prompt_profile,
                    "initial_prompt_profile": initial_prompt_profile,
                    "degrade_reason": degrade_reason,
                    "recent_timeout_streak": self._recent_timeout_streak,
                    "prompt_chars": len(system_prompt) + len(user_prompt),
                    "max_tokens": max_tokens,
                    "response_chars": len(content),
                    "raw_candidate_count": len(raw_candidates),
                    "returned_candidate_count": len(candidates),
                    "selected_candidate_count": len(selected_candidates),
                    "analysis_present": bool(analysis),
                    "analysis_keys": sorted(list(analysis.keys())),
                    "elapsed_seconds": round(time.perf_counter() - started_at, 4),
                    "attempts": [*attempt_reports, {
                        "attempt": attempt,
                        "status": "succeeded",
                        "request_limit": request_limit,
                        "timeout_sec": request_timeout_sec,
                        "prompt_profile": prompt_profile,
                        "prompt_chars": len(system_prompt) + len(user_prompt),
                        "max_tokens": max_tokens,
                        "elapsed_seconds": round(time.perf_counter() - request_started_at, 4),
                        "raw_candidate_count": len(raw_candidates),
                        "returned_candidate_count": len(candidates),
                        "analysis_present": bool(analysis),
                    }],
                }
                return {
                    "provider": self.config.provider,
                    "model": self.config.model,
                    "prompt": {
                        "system": system_prompt,
                        "user": user_prompt,
                        "profile": prompt_profile,
                    },
                    "raw_response": body,
                    "content": content,
                    "analysis": analysis,
                    "research_context": compact_research_context,
                    "research_task": dict(research_task or {}),
                    "candidates": selected_candidates,
                    "request_metrics": request_metrics,
                }
            except (
                httpx.TimeoutException,
                httpx.ConnectError,
                httpx.ReadError,
                httpx.RemoteProtocolError,
                httpx.HTTPStatusError,
                json.JSONDecodeError,
                ValueError,
            ) as exc:
                last_exc = exc
                attempt_reports.append({
                    "attempt": attempt,
                    "status": "failed",
                    "request_limit": request_limit,
                    "timeout_sec": request_timeout_sec,
                    "prompt_profile": prompt_profile,
                    "prompt_chars": len(system_prompt) + len(user_prompt),
                    "max_tokens": max_tokens,
                    "degrade_reason": degrade_reason,
                    "initial_prompt_profile": initial_prompt_profile,
                    "elapsed_seconds": round(time.perf_counter() - request_started_at, 4),
                    "error_type": exc.__class__.__name__,
                    "error": self._error_text(exc),
                    "status_code": getattr(getattr(exc, "response", None), "status_code", None),
                })
                if attempt >= attempts:
                    break
                await asyncio.sleep(self.config.retry_backoff_sec * attempt)

        if last_exc is not None:
            self._record_request_failure(last_exc)
        metrics = {
            "status": "failed",
            "endpoint": self._endpoint(),
            "provider": self.config.provider,
            "model": self.config.model,
            "requested_limit": requested_limit,
            "initial_prompt_profile": initial_prompt_profile,
            "degrade_reason": degrade_reason,
            "recent_timeout_streak": self._recent_timeout_streak,
            "recent_timeout_cooldown_sec": round(max(self._recent_timeout_cooldown_until - time.monotonic(), 0.0), 4),
            "elapsed_seconds": round(time.perf_counter() - started_at, 4),
            "attempt_count": len(attempt_reports),
            "attempts": attempt_reports,
            "last_error_type": last_exc.__class__.__name__ if last_exc else "RuntimeError",
            "last_error": self._error_text(last_exc or RuntimeError("external llm request failed")),
        }
        raise StrategyLLMRequestError(
            f"external llm request failed after {len(attempt_reports)} attempts: {metrics['last_error_type']}",
            metrics=metrics,
        ) from last_exc

    # ------------------------------------------------------------------
    # Multi-stage pipeline: single-stage LLM call
    # ------------------------------------------------------------------

    async def call_stage(
        self,
        *,
        stage_id: str,
        input_data: dict[str, Any],
        system_prompt: str,
        max_tokens: int = 500,
        temperature: float = 0.2,
        timeout_sec: Optional[float] = None,
    ) -> dict[str, Any]:
        """Execute a single pipeline stage via the external LLM.

        This reuses the existing HTTP infrastructure (retry, timeout
        degradation, cooldown tracking) but with a much simpler prompt
        structure: a short system prompt + JSON-serialised input data.

        Returns the parsed JSON dict from the LLM response.
        Raises ``StrategyLLMRequestError`` on failure.
        """
        if not self.is_enabled():
            raise StrategyLLMRequestError(
                f"call_stage({stage_id}): LLM provider not enabled",
                metrics={"stage_id": stage_id, "status": "disabled"},
            )

        started_at = time.perf_counter()
        stage_timeout = float(timeout_sec or 10.0)
        _compact_level, degrade_reason = self._recent_timeout_degrade_state()
        if degrade_reason == 'recent_timeout':
            raise StrategyLLMRequestError(
                f"call_stage({stage_id}) skipped during timeout cooldown",
                metrics={
                    "stage_id": stage_id,
                    "status": "cooldown_skip",
                    "last_error_type": "RecentTimeoutCooldown",
                    "recent_timeout_streak": self._recent_timeout_streak,
                    "recent_timeout_cooldown_sec": round(
                        max(self._recent_timeout_cooldown_until - time.monotonic(), 0.0),
                        4,
                    ),
                    "elapsed_seconds": round(time.perf_counter() - started_at, 4),
                },
            )
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        user_prompt = json.dumps(input_data, ensure_ascii=False, default=str, separators=(",", ":"))
        payload = {
            "model": self.config.model,
            "temperature": temperature,
            "max_tokens": max(128, max_tokens),
            "response_format": {"type": "json_object"},
            "stream": False,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }

        last_exc: Optional[Exception] = None
        attempts = 1  # single attempt per stage — fail fast and fallback

        client = self._client
        for attempt in range(1, attempts + 1):
            request_started_at = time.perf_counter()
            try:
                async with self._request_semaphore:
                    response = await client.post(
                        self._endpoint(),
                        headers=headers,
                        json=payload,
                        timeout=self._request_timeout(stage_timeout),
                    )
                response.raise_for_status()
                body = response.json()
                content = self._extract_content(body)
                json_text = self._extract_json_text(content)
                data = json.loads(json_text)
                if isinstance(data, list):
                    # LLM 返回了裸数组 — 根据 stage_id 包装成 dict
                    _STAGE_LIST_KEY = {
                        "event_recognition": "events",
                        "theme_propagation": "themes",
                        "exposure_mapping": "exposures",
                        "market_confirmation": "confirmations",
                        "strategy_generation": "candidates",
                    }
                    wrap_key = _STAGE_LIST_KEY.get(stage_id, "results")
                    data = {wrap_key: data}
                if not isinstance(data, dict):
                    raise ValueError(f"call_stage({stage_id}): expected JSON object, got {type(data).__name__}")
                self._record_request_success()
                return data
            except (
                httpx.TimeoutException,
                httpx.ConnectError,
                httpx.ReadError,
                httpx.RemoteProtocolError,
                httpx.HTTPStatusError,
                json.JSONDecodeError,
                ValueError,
            ) as exc:
                last_exc = exc
                if attempt >= attempts:
                    break
                await asyncio.sleep(min(self.config.retry_backoff_sec * attempt, 3.0))

        if last_exc is not None:
            self._record_request_failure(last_exc)
        raise StrategyLLMRequestError(
            f"call_stage({stage_id}) failed after {attempts} attempts: {self._error_text(last_exc or RuntimeError('unknown'))}",
            metrics={
                "stage_id": stage_id,
                "status": "failed",
                "elapsed_seconds": round(time.perf_counter() - started_at, 4),
                "last_error_type": (last_exc.__class__.__name__ if last_exc else "RuntimeError"),
            },
        ) from last_exc


_strategy_llm_provider: Optional[StrategyLLMProvider] = None


def get_strategy_llm_provider() -> StrategyLLMProvider:
    global _strategy_llm_provider
    if _strategy_llm_provider is None:
        _strategy_llm_provider = StrategyLLMProvider()
    return _strategy_llm_provider


async def close_strategy_llm_provider() -> None:
    global _strategy_llm_provider
    provider = _strategy_llm_provider
    _strategy_llm_provider = None
    if provider is None:
        return
    await provider.close()
