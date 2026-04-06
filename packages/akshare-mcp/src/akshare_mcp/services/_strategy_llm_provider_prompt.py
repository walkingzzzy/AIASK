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
            max_concurrency=max(1, min(16, int(os.getenv("STRATEGY_LLM_MAX_CONCURRENCY", "3") or 3))),
            strict=str(os.getenv("STRATEGY_LLM_STRICT_MODE", "")).strip().lower() in {"1", "true", "yes", "on"},
        )


class _StrategyLLMProviderPromptMixin:
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
            target_alignment_contract = dict(normalized_task.get('target_alignment_contract') or {})
            prompt_target_symbol_rule = cls._prompt_target_symbol_rule(normalized_task)
            compact_market_summary = cls._compact_market_summary(market_summary, compact_level=compact_level)
            compact_research_context = cls._compact_research_context(research_context, compact_level=compact_level)
            compact_task = cls._compact_research_task(research_task, compact_level=compact_level)
            max_target_symbols = max(
                1,
                int(
                    target_alignment_contract.get('max_candidate_target_symbols')
                    or max(1, min(len(list(normalized_task.get('target_symbols') or [])) or 5, 8))
                ),
            )
            min_target_coverage_ratio = float(target_alignment_contract.get('min_coverage_ratio') or 0.0)
            min_target_intersection_ratio = float(target_alignment_contract.get('min_intersection_ratio') or 0.0)
            min_target_overlap_count = int(target_alignment_contract.get('min_required_overlap_count') or 0)
            strict_snapshot_target_pool = (
                str(normalized_task.get('task_source') or '').strip().lower() == 'snapshot'
                and bool(target_alignment_contract.get('strict_target_subset_required'))
                and bool(normalized_task.get('target_symbols'))
            )
            disallow_market_fallback = strict_snapshot_target_pool and not target_alignment_contract.get('market_fallback_allowed', True)
            focus_strategy_families = list(target_alignment_contract.get('focus_strategy_families') or [])
            strict_snapshot_rule = ''
            if strict_snapshot_target_pool:
                strict_snapshot_rule = (
                    f'这是定向 target pool 任务，target_symbols 只能从 research_task.target_symbols 中选择，'
                    f'不得扩展到 candidate_universe 或全市场；候选至少要覆盖 {max(1, min_target_overlap_count)} 只 research_task 目标，'
                    f'且 target_symbols 不得超过 {max_target_symbols} 只。'
                )

            if compact_level >= 2:
                example_symbols = cls._normalize_code_list([
                    compact_task.get('target_symbols'),
                    compact_research_context.get('candidate_universe_symbols'),
                    compact_research_context.get('symbol_insight_codes'),
                ], limit=2)
                if not example_symbols:
                    example_symbols = cls._normalize_code_list((research_task or {}).get('target_symbols'), limit=2)
                required_contract_fields = [
                    'holding_horizon',
                    'trade_plan',
                    'risk_rules',
                    'position_sizing',
                    'execution_notes',
                    'rebalance_rule',
                    'portfolio_spec',
                    'execution_assumptions',
                    'validation_profile',
                ]
                output_contract = {
                    'root': 'json_object',
                    'required': ['candidates'],
                    'analysis_fields': [],
                    'candidate_fields': ['name', 'strategy_type', 'hypothesis', 'holding_horizon', 'trade_plan', 'risk_rules', 'position_sizing', 'execution_notes', 'rebalance_rule', 'portfolio_spec', 'execution_assumptions', 'validation_profile', 'target_symbols', 'stock_pool', 'dsl', 'tags'],
                    'required_candidate_fields': ['name', 'strategy_type', 'target_symbols', 'stock_pool', 'dsl', *required_contract_fields],
                    'dsl_required_fields': ['version', 'timeframe', 'entry', 'exit', 'metadata'],
                    'contract_required_fields': required_contract_fields,
                    'target_symbol_rule': prompt_target_symbol_rule,
                    'target_alignment_contract': {
                        'max_target_symbols': max_target_symbols,
                        'min_target_coverage_ratio': round(min_target_coverage_ratio, 4),
                        'min_target_intersection_ratio': round(min_target_intersection_ratio, 4),
                        'min_target_overlap_count': max(0, min_target_overlap_count),
                        'disallow_market_fallback': disallow_market_fallback,
                    },
                    'prefer_single_high_confidence_candidate': True,
                    'candidate_limit': 1,
                }
                system_prompt = ''.join([
                    '你是量化策略助手，只返回严格 JSON。',
                    '基于 target_symbols 生成 1 个可执行股票日频 DSL candidate。',
                    '如果 research_task 提供了 event_id/theme_code/direction/evidence_summary，必须围绕该事件证据输出。',
                    '不要 analysis，不要解释，不要 markdown。',
                    '返回根对象 {"candidates":[...]}。',
                    'candidate 必须包含 name,strategy_type,hypothesis,holding_horizon,trade_plan,risk_rules,position_sizing,execution_notes,rebalance_rule,portfolio_spec,execution_assumptions,validation_profile,target_symbols,stock_pool,dsl,tags。',
                    'portfolio_spec / execution_assumptions / validation_profile 必须给出完整对象，不得省略，也不得依赖系统回填默认值。',
                    'dsl 必须是对象，且必须包含 version,timeframe,entry,exit,metadata。',
                    'dsl.metadata 必须回填 target_symbols,stock_pool,portfolio_spec,execution_assumptions,validation_profile,targeting_policy,constraint_check。',
                    strict_snapshot_rule,
                    '字段仅限 open/high/low/close/volume；指标优先仅用 sma,ema,roc,rsi,volume_ratio；',
                    '条件运算仅限 gt,gte,lt,lte,cross_above,cross_below；组合仅限 all,any,not。',
                    '不要使用 highest/lowest/atr/stddev，也不要写 close 与 highest/lowest 的交叉突破。',
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
            if strict_snapshot_target_pool:
                context_rule = strict_snapshot_rule
            elif prompt_target_symbol_rule == 'strict_intersection_with_research_task':
                context_rule = (
                    '如果 research_task.target_symbols 与 candidate_universe 有交集，'
                    'target_symbols 必须只取交集；如果没有交集，不允许退回 candidate_universe。'
                    '只有在 research_task 显式提供 same_theme_symbols 或 theme_members 时，'
                    '才允许只在该同主题集合内补充候选。'
                )
            else:
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
                'holding_horizon / trade_plan / risk_rules / position_sizing / rebalance_rule / portfolio_spec / execution_assumptions / validation_profile 必须是完整对象，不得留空，不得依赖系统回填默认值。',
                'DSL 条件节点必须使用标准对象格式 {"op":...,"left":...,"right":...}，不要使用 {"gt":[...]} 这类简写。',
                f'target_symbols 数量建议 1-{max_target_symbols} 只；stock_pool 必须包含 selection_mode 与 symbols；dsl.metadata 必须回填 target_symbols,stock_pool,portfolio_spec,execution_assumptions,validation_profile,targeting_policy,constraint_check。',
                '不要生成 Python 代码，不要生成自然语言规则，只能生成 JSON DSL。',
            ])
            output_contract = {
                'root': 'json_object',
                'required': ['analysis', 'candidates'],
                'analysis_fields': analysis_fields,
                'required_candidate_fields': ['name', 'strategy_type', 'hypothesis', 'holding_horizon', 'trade_plan', 'risk_rules', 'position_sizing', 'execution_notes', 'rebalance_rule', 'portfolio_spec', 'execution_assumptions', 'validation_profile', 'target_symbols', 'stock_pool', 'dsl'],
                'target_symbol_rule': prompt_target_symbol_rule,
                'target_alignment_contract': {
                    'max_target_symbols': max_target_symbols,
                    'min_target_coverage_ratio': round(min_target_coverage_ratio, 4),
                    'min_target_intersection_ratio': round(min_target_intersection_ratio, 4),
                    'min_target_overlap_count': max(0, min_target_overlap_count),
                    'disallow_market_fallback': disallow_market_fallback,
                    'focus_strategy_families': focus_strategy_families[:4],
                },
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
