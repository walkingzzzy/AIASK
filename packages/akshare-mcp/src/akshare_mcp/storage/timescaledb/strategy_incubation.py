"""TimescaleDB 策略超市 Mixin — 孵化账户 / 孵化指标 / 模拟交易"""

import json
import logging
from datetime import date, datetime
from typing import Any, List, Optional

from ...services.trade_audit_writer import aggregate_trade_position

logger = logging.getLogger(__name__)

_EXECUTION_AUDIT_REQUIRED_TABLES = (
    "strategy_candidate_evidence",
    "strategy_signal_evidence",
    "strategy_trade_positions",
    "strategy_trade_position_fills",
)
_EXECUTION_AUDIT_REQUIRED_COLUMNS = {
    "paper_orders": ("signal_id", "position_id"),
    "paper_trades": ("signal_id", "position_id"),
}
_EXECUTION_AUDIT_REQUIRED_MIGRATIONS = (
    "paper_trades_best_effort_position_backfill_v1",
    "strategy_candidate_evidence_native_backfill_v1",
    "strategy_signal_evidence_native_backfill_v1",
    "strategy_trade_positions_roundtrip_backfill_v1",
)


def _safe_rules_dict(value) -> dict:
    """将 risk_rules 字段安全地转换为 dict，防止反复 json.dumps 造成多层嵌套。"""
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass
    return {}


def _safe_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(float(value))
    except Exception:
        return default


def _string(value: Any) -> str:
    return str(value or "").strip()


def _coerce_ts(value: Any) -> Any:
    if value is None or isinstance(value, (datetime, date)):
        return value
    text = _string(value)
    if not text:
        return None
    for parser in (
        lambda item: datetime.fromisoformat(item.replace("Z", "+00:00")),
        lambda item: datetime.combine(date.fromisoformat(item[:10]), datetime.min.time()),
    ):
        try:
            return parser(text)
        except Exception:
            continue
    return value


class StrategyIncubationMixin:
    """孵化账户 + 孵化指标 + 模拟盘(paper) + 孵化流水线快照"""

    # ── 孵化账户 ──

    def _decode_incubation_account(self, row: dict) -> dict:
        result = dict(row)
        result["metadata"] = self._decode_json_field(result.get("metadata"), {})
        return result

    async def save_strategy_incubation_account(
        self,
        strategy_id: str,
        account_id: str,
        stage: str = "warmup",
        status: str = "active",
        source_run_id: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> dict:
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO strategy_incubation_accounts
                    (strategy_id, account_id, stage, status, source_run_id, metadata, bound_at, updated_at)
                VALUES ($1, $2, $3, $4, $5, $6::jsonb, NOW(), NOW())
                ON CONFLICT (strategy_id, account_id) DO UPDATE SET
                    stage = EXCLUDED.stage,
                    status = EXCLUDED.status,
                    source_run_id = EXCLUDED.source_run_id,
                    metadata = EXCLUDED.metadata,
                    updated_at = NOW()
                RETURNING *
                """,
                strategy_id,
                account_id,
                str(stage or "warmup"),
                str(status or "active"),
                source_run_id,
                json.dumps(metadata or {}, ensure_ascii=False, default=str),
            )
        return self._decode_incubation_account(dict(row))

    async def get_strategy_incubation_account(
        self,
        strategy_id: str,
        account_id: Optional[str] = None,
    ) -> Optional[dict]:
        async with self.acquire() as conn:
            if account_id:
                row = await conn.fetchrow(
                    """
                    SELECT * FROM strategy_incubation_accounts
                    WHERE strategy_id = $1 AND account_id = $2
                    ORDER BY updated_at DESC
                    LIMIT 1
                    """,
                    strategy_id,
                    account_id,
                )
            else:
                row = await conn.fetchrow(
                    """
                    SELECT * FROM strategy_incubation_accounts
                    WHERE strategy_id = $1
                    ORDER BY updated_at DESC
                    LIMIT 1
                    """,
                    strategy_id,
                )
        if not row:
            return None
        return self._decode_incubation_account(dict(row))

    async def list_strategy_incubation_accounts(
        self,
        strategy_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 20,
    ) -> List[dict]:
        async with self.acquire() as conn:
            sql = "SELECT * FROM strategy_incubation_accounts WHERE 1=1"
            params: list = []
            idx = 1
            if strategy_id:
                sql += f" AND strategy_id = ${idx}"
                params.append(strategy_id)
                idx += 1
            if status:
                sql += f" AND status = ${idx}"
                params.append(status)
                idx += 1
            sql += f" ORDER BY updated_at DESC LIMIT ${idx}"
            params.append(max(1, min(int(limit or 20), 200)))
            rows = await conn.fetch(sql, *params)
        return [self._decode_incubation_account(dict(row)) for row in rows]

    # ── 孵化指标 ──

    def _decode_incubation_metric(self, row: dict) -> dict:
        result = dict(row)
        result["metadata"] = self._decode_json_field(result.get("metadata"), {})
        result["blockers"] = self._decode_json_field(result.get("blockers"), [])
        result["risk_flags"] = self._decode_json_field(result.get("risk_flags"), [])
        return result

    async def save_strategy_incubation_metric(self, strategy_id: str, metric_date, metric: dict) -> dict:
        payload = dict(metric or {})
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO strategy_incubation_metrics
                    (strategy_id, account_id, metric_date, stage, total_value, cash, market_value, nav,
                     daily_return, max_drawdown, sharpe_ratio, hit_rate_5d, hit_rate_lcb_5d, skill_lcb_5d,
                     effective_n_5d, recent_hit_rate_5d, recent_skill_lcb_5d, stability_gap_5d,
                     forward_ic_5d, forward_sharpe_5d,
                     total_signals, total_orders, total_trades, turnover_rate, exposure_rate, alpha_decay,
                     drift_score, blockers, risk_flags, decision, metadata, created_at, updated_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8,
                        $9, $10, $11, $12, $13, $14,
                        $15, $16, $17, $18, $19, $20,
                        $21, $22, $23, $24, $25, $26,
                        $27, $28::jsonb, $29::jsonb, $30, $31::jsonb, NOW(), NOW())
                ON CONFLICT (strategy_id, metric_date) DO UPDATE SET
                    account_id = EXCLUDED.account_id,
                    stage = EXCLUDED.stage,
                    total_value = EXCLUDED.total_value,
                    cash = EXCLUDED.cash,
                    market_value = EXCLUDED.market_value,
                    nav = EXCLUDED.nav,
                    daily_return = EXCLUDED.daily_return,
                    max_drawdown = EXCLUDED.max_drawdown,
                    sharpe_ratio = EXCLUDED.sharpe_ratio,
                    hit_rate_5d = EXCLUDED.hit_rate_5d,
                    hit_rate_lcb_5d = EXCLUDED.hit_rate_lcb_5d,
                    skill_lcb_5d = EXCLUDED.skill_lcb_5d,
                    effective_n_5d = EXCLUDED.effective_n_5d,
                    recent_hit_rate_5d = EXCLUDED.recent_hit_rate_5d,
                    recent_skill_lcb_5d = EXCLUDED.recent_skill_lcb_5d,
                    stability_gap_5d = EXCLUDED.stability_gap_5d,
                    forward_ic_5d = EXCLUDED.forward_ic_5d,
                    forward_sharpe_5d = EXCLUDED.forward_sharpe_5d,
                    total_signals = EXCLUDED.total_signals,
                    total_orders = EXCLUDED.total_orders,
                    total_trades = EXCLUDED.total_trades,
                    turnover_rate = EXCLUDED.turnover_rate,
                    exposure_rate = EXCLUDED.exposure_rate,
                    alpha_decay = EXCLUDED.alpha_decay,
                    drift_score = EXCLUDED.drift_score,
                    blockers = EXCLUDED.blockers,
                    risk_flags = EXCLUDED.risk_flags,
                    decision = EXCLUDED.decision,
                    metadata = EXCLUDED.metadata,
                    updated_at = NOW()
                RETURNING *
                """,
                strategy_id,
                payload.get("account_id"),
                metric_date,
                str(payload.get("stage") or "warmup"),
                payload.get("total_value"),
                payload.get("cash"),
                payload.get("market_value"),
                payload.get("nav"),
                payload.get("daily_return"),
                payload.get("max_drawdown"),
                payload.get("sharpe_ratio"),
                payload.get("hit_rate_5d"),
                payload.get("hit_rate_lcb_5d"),
                payload.get("skill_lcb_5d"),
                payload.get("effective_n_5d"),
                payload.get("recent_hit_rate_5d"),
                payload.get("recent_skill_lcb_5d"),
                payload.get("stability_gap_5d"),
                payload.get("forward_ic_5d"),
                payload.get("forward_sharpe_5d"),
                int(payload.get("total_signals") or 0),
                int(payload.get("total_orders") or 0),
                int(payload.get("total_trades") or 0),
                payload.get("turnover_rate"),
                payload.get("exposure_rate"),
                payload.get("alpha_decay"),
                payload.get("drift_score"),
                json.dumps(payload.get("blockers") or [], ensure_ascii=False, default=str),
                json.dumps(payload.get("risk_flags") or [], ensure_ascii=False, default=str),
                payload.get("decision"),
                json.dumps(payload.get("metadata") or {}, ensure_ascii=False, default=str),
            )
        return self._decode_incubation_metric(dict(row))

    async def get_latest_strategy_incubation_metric(self, strategy_id: str) -> Optional[dict]:
        rows = await self.list_strategy_incubation_metrics(strategy_id, limit=1)
        return rows[0] if rows else None

    # ── Phase 5 candidate / signal evidence ──

    def _decode_strategy_candidate_evidence(self, row: dict) -> dict:
        result = dict(row)
        result["payload"] = self._decode_json_field(result.get("payload"), {})
        return result

    async def save_strategy_candidate_evidence(self, evidence: dict) -> dict:
        payload = dict(evidence or {})
        candidate_id = str(payload.get("candidate_id") or "").strip()
        evidence_id = str(payload.get("evidence_id") or "").strip()
        row_id = str(payload.get("id") or f"{candidate_id}:{evidence_id}").strip()
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO strategy_candidate_evidence
                    (id, candidate_id, strategy_id, candidate_artifact_id, experiment_id, evidence_id,
                     evidence_type, source_type, event_type, target_symbols, direction, horizon_days,
                     raw_confidence, calibrated_confidence, freshness_ts, proxy_only, support_metric,
                     doc_uid, headline_label_id, source_task_key, payload, created_at)
                VALUES ($1, $2, $3, $4, $5, $6,
                        $7, $8, $9, $10::jsonb, $11, $12,
                        $13, $14, $15, $16, $17::jsonb,
                        $18, $19, $20, $21::jsonb, NOW())
                ON CONFLICT (candidate_id, evidence_id) DO UPDATE SET
                    strategy_id = COALESCE(EXCLUDED.strategy_id, strategy_candidate_evidence.strategy_id),
                    candidate_artifact_id = COALESCE(EXCLUDED.candidate_artifact_id, strategy_candidate_evidence.candidate_artifact_id),
                    experiment_id = COALESCE(EXCLUDED.experiment_id, strategy_candidate_evidence.experiment_id),
                    evidence_type = COALESCE(EXCLUDED.evidence_type, strategy_candidate_evidence.evidence_type),
                    source_type = COALESCE(EXCLUDED.source_type, strategy_candidate_evidence.source_type),
                    event_type = COALESCE(EXCLUDED.event_type, strategy_candidate_evidence.event_type),
                    target_symbols = COALESCE(EXCLUDED.target_symbols, strategy_candidate_evidence.target_symbols),
                    direction = COALESCE(EXCLUDED.direction, strategy_candidate_evidence.direction),
                    horizon_days = COALESCE(EXCLUDED.horizon_days, strategy_candidate_evidence.horizon_days),
                    raw_confidence = COALESCE(EXCLUDED.raw_confidence, strategy_candidate_evidence.raw_confidence),
                    calibrated_confidence = COALESCE(EXCLUDED.calibrated_confidence, strategy_candidate_evidence.calibrated_confidence),
                    freshness_ts = COALESCE(EXCLUDED.freshness_ts, strategy_candidate_evidence.freshness_ts),
                    proxy_only = COALESCE(EXCLUDED.proxy_only, strategy_candidate_evidence.proxy_only),
                    support_metric = COALESCE(EXCLUDED.support_metric, strategy_candidate_evidence.support_metric),
                    doc_uid = COALESCE(EXCLUDED.doc_uid, strategy_candidate_evidence.doc_uid),
                    headline_label_id = COALESCE(EXCLUDED.headline_label_id, strategy_candidate_evidence.headline_label_id),
                    source_task_key = COALESCE(EXCLUDED.source_task_key, strategy_candidate_evidence.source_task_key),
                    payload = COALESCE(EXCLUDED.payload, strategy_candidate_evidence.payload)
                RETURNING *
                """,
                row_id,
                candidate_id,
                payload.get("strategy_id"),
                payload.get("candidate_artifact_id"),
                payload.get("experiment_id"),
                evidence_id,
                payload.get("evidence_type"),
                payload.get("source_type") or payload.get("evidence_type"),
                payload.get("event_type"),
                json.dumps(payload.get("target_symbols") or [], ensure_ascii=False, default=str),
                payload.get("direction"),
                payload.get("horizon_days"),
                payload.get("raw_confidence"),
                payload.get("calibrated_confidence"),
                _coerce_ts(payload.get("freshness_ts")),
                bool(payload.get("proxy_only")),
                json.dumps(payload.get("support_metric") or {}, ensure_ascii=False, default=str),
                payload.get("doc_uid"),
                payload.get("headline_label_id"),
                payload.get("source_task_key") or payload.get("task_key"),
                json.dumps(
                    payload.get("payload") or payload.get("evidence_payload") or payload,
                    ensure_ascii=False,
                    default=str,
                ),
            )
        return self._decode_strategy_candidate_evidence(dict(row))

    async def list_strategy_candidate_evidence(
        self,
        *,
        candidate_id: Optional[str] = None,
        strategy_id: Optional[str] = None,
        limit: int = 200,
    ) -> List[dict]:
        async with self.acquire() as conn:
            sql = "SELECT * FROM strategy_candidate_evidence WHERE 1=1"
            params: list[Any] = []
            idx = 1
            if candidate_id:
                sql += f" AND candidate_id = ${idx}"
                params.append(candidate_id)
                idx += 1
            if strategy_id:
                sql += f" AND strategy_id = ${idx}"
                params.append(strategy_id)
                idx += 1
            sql += f" ORDER BY created_at DESC LIMIT ${idx}"
            params.append(max(1, min(int(limit or 200), 5000)))
            rows = await conn.fetch(sql, *params)
        return [self._decode_strategy_candidate_evidence(dict(row)) for row in rows]

    def _decode_strategy_signal_evidence(self, row: dict) -> dict:
        result = dict(row)
        result["payload"] = self._decode_json_field(result.get("payload"), {})
        return result

    async def save_strategy_signal_evidence(self, evidence: dict) -> dict:
        payload = dict(evidence or {})
        signal_id = str(payload.get("signal_id") or "").strip()
        evidence_id = str(payload.get("evidence_id") or "").strip()
        applied_claim_id = _string(payload.get("applied_claim_id")) or None
        applied_trade_step_id = _string(payload.get("applied_trade_step_id")) or None
        row_id = str(
            payload.get("id")
            or f"{signal_id}:{evidence_id}:{applied_claim_id or 'unclaimed'}:{applied_trade_step_id or 'unmapped_step'}"
        ).strip()
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO strategy_signal_evidence
                    (id, signal_id, strategy_id, signal_date, signal_ts, code, candidate_artifact_id, experiment_id,
                     evidence_id, applied_claim_id, applied_trade_step_id, source_type, direction, horizon_days, raw_confidence,
                     calibrated_confidence, proxy_only, doc_uid, headline_label_id, runtime_action_reason, runtime_action_source,
                     payload, created_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8,
                        $9, $10, $11, $12, $13, $14, $15,
                        $16, $17, $18, $19, $20, $21, $22,
                        $23::jsonb, NOW())
                ON CONFLICT (id) DO UPDATE SET
                    strategy_id = COALESCE(EXCLUDED.strategy_id, strategy_signal_evidence.strategy_id),
                    signal_date = COALESCE(EXCLUDED.signal_date, strategy_signal_evidence.signal_date),
                    signal_ts = COALESCE(EXCLUDED.signal_ts, strategy_signal_evidence.signal_ts),
                    code = COALESCE(EXCLUDED.code, strategy_signal_evidence.code),
                    candidate_artifact_id = COALESCE(EXCLUDED.candidate_artifact_id, strategy_signal_evidence.candidate_artifact_id),
                    experiment_id = COALESCE(EXCLUDED.experiment_id, strategy_signal_evidence.experiment_id),
                    applied_claim_id = COALESCE(EXCLUDED.applied_claim_id, strategy_signal_evidence.applied_claim_id),
                    applied_trade_step_id = COALESCE(EXCLUDED.applied_trade_step_id, strategy_signal_evidence.applied_trade_step_id),
                    source_type = COALESCE(EXCLUDED.source_type, strategy_signal_evidence.source_type),
                    direction = COALESCE(EXCLUDED.direction, strategy_signal_evidence.direction),
                    horizon_days = COALESCE(EXCLUDED.horizon_days, strategy_signal_evidence.horizon_days),
                    raw_confidence = COALESCE(EXCLUDED.raw_confidence, strategy_signal_evidence.raw_confidence),
                    calibrated_confidence = COALESCE(EXCLUDED.calibrated_confidence, strategy_signal_evidence.calibrated_confidence),
                    proxy_only = COALESCE(EXCLUDED.proxy_only, strategy_signal_evidence.proxy_only),
                    doc_uid = COALESCE(EXCLUDED.doc_uid, strategy_signal_evidence.doc_uid),
                    headline_label_id = COALESCE(EXCLUDED.headline_label_id, strategy_signal_evidence.headline_label_id),
                    runtime_action_reason = COALESCE(EXCLUDED.runtime_action_reason, strategy_signal_evidence.runtime_action_reason),
                    runtime_action_source = COALESCE(EXCLUDED.runtime_action_source, strategy_signal_evidence.runtime_action_source),
                    payload = COALESCE(EXCLUDED.payload, strategy_signal_evidence.payload)
                RETURNING *
                """,
                row_id,
                signal_id,
                payload.get("strategy_id"),
                payload.get("signal_date"),
                _coerce_ts(payload.get("signal_ts") or payload.get("signal_date")),
                payload.get("code") or payload.get("symbol"),
                payload.get("candidate_artifact_id"),
                payload.get("experiment_id"),
                evidence_id,
                applied_claim_id,
                applied_trade_step_id,
                payload.get("source_type") or payload.get("evidence_type"),
                payload.get("direction"),
                payload.get("horizon_days"),
                payload.get("raw_confidence"),
                payload.get("calibrated_confidence"),
                bool(payload.get("proxy_only")),
                payload.get("doc_uid"),
                payload.get("headline_label_id"),
                payload.get("runtime_action_reason"),
                payload.get("runtime_action_source"),
                json.dumps(
                    payload.get("payload") or payload.get("evidence_payload") or payload,
                    ensure_ascii=False,
                    default=str,
                ),
            )
        return self._decode_strategy_signal_evidence(dict(row))

    async def list_strategy_signal_evidence(
        self,
        *,
        signal_id: Optional[str] = None,
        strategy_id: Optional[str] = None,
        limit: int = 200,
    ) -> List[dict]:
        async with self.acquire() as conn:
            sql = "SELECT * FROM strategy_signal_evidence WHERE 1=1"
            params: list[Any] = []
            idx = 1
            if signal_id:
                sql += f" AND signal_id = ${idx}"
                params.append(signal_id)
                idx += 1
            if strategy_id:
                sql += f" AND strategy_id = ${idx}"
                params.append(strategy_id)
                idx += 1
            sql += f" ORDER BY COALESCE(signal_ts, signal_date::timestamptz) DESC, created_at DESC LIMIT ${idx}"
            params.append(max(1, min(int(limit or 200), 5000)))
            rows = await conn.fetch(sql, *params)
        return [self._decode_strategy_signal_evidence(dict(row)) for row in rows]

    # ── 模拟盘 ──

    async def get_paper_account(self, account_id: str) -> Optional[dict]:
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM paper_accounts WHERE id = $1 LIMIT 1",
                account_id,
            )
        return dict(row) if row else None

    async def get_paper_account_by_strategy(self, strategy_id: str) -> Optional[dict]:
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM paper_accounts WHERE strategy_id = $1 ORDER BY created_at LIMIT 1",
                strategy_id,
            )
        return dict(row) if row else None

    async def save_paper_account(self, account: dict) -> dict:
        payload = dict(account or {})
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO paper_accounts
                    (id, user_id, name, initial_capital, current_capital, total_value, risk_rules,
                     strategy_id, account_type, incubation_stage, promotion_candidate, archived_reason, status, created_at, updated_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb,
                        $8, $9, $10, $11, $12, $13, NOW(), NOW())
                ON CONFLICT (id) DO UPDATE SET
                    user_id = EXCLUDED.user_id,
                    name = EXCLUDED.name,
                    initial_capital = EXCLUDED.initial_capital,
                    current_capital = EXCLUDED.current_capital,
                    total_value = EXCLUDED.total_value,
                    risk_rules = EXCLUDED.risk_rules,
                    strategy_id = EXCLUDED.strategy_id,
                    account_type = EXCLUDED.account_type,
                    incubation_stage = EXCLUDED.incubation_stage,
                    promotion_candidate = EXCLUDED.promotion_candidate,
                    archived_reason = EXCLUDED.archived_reason,
                    status = EXCLUDED.status,
                    updated_at = NOW()
                RETURNING *
                """,
                str(payload.get('id') or ''),
                payload.get('user_id') or 'default',
                str(payload.get('name') or 'paper_account'),
                float(payload.get('initial_capital') or 0.0),
                float(payload.get('current_capital') or 0.0),
                float(payload.get('total_value') or 0.0),
                json.dumps(_safe_rules_dict(payload.get('risk_rules')), ensure_ascii=False, default=str),
                payload.get('strategy_id'),
                payload.get('account_type') or 'manual',
                payload.get('incubation_stage') or 'warmup',
                bool(payload.get('promotion_candidate')),
                payload.get('archived_reason'),
                payload.get('status') or 'active',
            )
        return dict(row)

    async def update_paper_account_status(
        self,
        account_id: str,
        status: str,
        stage=None,
        promotion_candidate=None,
        observation_candidate=None,
    ) -> Optional[dict]:
        if promotion_candidate is None and observation_candidate is not None:
            promotion_candidate = False
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE paper_accounts
                SET status = $2,
                    incubation_stage = COALESCE($3, incubation_stage),
                    promotion_candidate = COALESCE($4, promotion_candidate),
                    updated_at = NOW()
                WHERE id = $1
                RETURNING *
                """,
                account_id,
                status,
                stage,
                promotion_candidate,
            )
        return dict(row) if row else None

    async def list_strategy_paper_orders(self, strategy_id: str, signal_date = None, status: Optional[str] = None, limit: int = 200) -> List[dict]:
        async with self.acquire() as conn:
            sql = "SELECT * FROM paper_orders WHERE strategy_id = $1"
            params: list = [strategy_id]
            idx = 2
            if signal_date is not None:
                sql += f" AND signal_date = ${idx}"
                params.append(signal_date)
                idx += 1
            if status:
                sql += f" AND status = ${idx}"
                params.append(status)
                idx += 1
            sql += f" ORDER BY created_at DESC LIMIT ${idx}"
            params.append(max(1, min(int(limit or 200), 2000)))
            rows = await conn.fetch(sql, *params)
        return [dict(row) for row in rows]

    async def list_strategy_paper_trades(
        self,
        strategy_id: str,
        account_id: Optional[str] = None,
        limit: int = 500,
    ) -> List[dict]:
        async with self.acquire() as conn:
            sql = "SELECT * FROM paper_trades WHERE strategy_id = $1"
            params: list = [strategy_id]
            idx = 2
            if account_id:
                sql += f" AND account_id = ${idx}"
                params.append(account_id)
                idx += 1
            sql += f" ORDER BY trade_time DESC, created_at DESC LIMIT ${idx}"
            params.append(max(1, min(int(limit or 500), 5000)))
            rows = await conn.fetch(sql, *params)
        return [dict(row) for row in rows]

    async def save_paper_order(self, order: dict) -> dict:
        payload = dict(order or {})
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO paper_orders
                    (account_id, strategy_id, signal_date, source, code, direction, shares, price,
                     order_type, stop_price, status, commission, reason, filled_at, signal_id, position_id,
                     created_at, updated_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8,
                        $9, $10, $11, $12, $13, $14, $15, $16, NOW(), NOW())
                RETURNING *
                """,
                payload.get('account_id'),
                payload.get('strategy_id'),
                payload.get('signal_date'),
                payload.get('source') or 'manual',
                payload.get('code'),
                payload.get('direction'),
                int(payload.get('shares') or 0),
                payload.get('price'),
                payload.get('order_type') or 'market',
                payload.get('stop_price'),
                payload.get('status') or 'pending',
                float(payload.get('commission') or 0.0),
                payload.get('reason'),
                payload.get('filled_at'),
                payload.get('signal_id'),
                payload.get('position_id'),
            )
        return dict(row)

    async def update_paper_order(self, order_id: int, updates: dict) -> Optional[dict]:
        payload = dict(updates or {})
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE paper_orders
                SET price = COALESCE($2, price),
                    shares = COALESCE($3, shares),
                    status = COALESCE($4, status),
                    commission = COALESCE($5, commission),
                    reason = COALESCE($6, reason),
                    filled_at = COALESCE($7, filled_at),
                    signal_id = COALESCE($8, signal_id),
                    position_id = COALESCE($9, position_id),
                    updated_at = NOW()
                WHERE id = $1
                RETURNING *
                """,
                int(order_id),
                payload.get('price'),
                payload.get('shares'),
                payload.get('status'),
                payload.get('commission'),
                payload.get('reason'),
                payload.get('filled_at'),
                payload.get('signal_id'),
                payload.get('position_id'),
            )
        return dict(row) if row else None

    async def list_paper_positions(self, account_id: str) -> List[dict]:
        async with self.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM paper_positions WHERE account_id = $1 ORDER BY stock_code",
                account_id,
            )
        return [dict(row) for row in rows]

    async def save_paper_position(self, position: dict) -> dict:
        payload = dict(position or {})
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO paper_positions
                    (account_id, stock_code, stock_name, quantity, cost_price, current_price, market_value, profit_rate, created_at, updated_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW(), NOW())
                ON CONFLICT (account_id, stock_code) DO UPDATE SET
                    stock_name = EXCLUDED.stock_name,
                    quantity = EXCLUDED.quantity,
                    cost_price = EXCLUDED.cost_price,
                    current_price = EXCLUDED.current_price,
                    market_value = EXCLUDED.market_value,
                    profit_rate = EXCLUDED.profit_rate,
                    updated_at = NOW()
                RETURNING *
                """,
                payload.get('account_id'),
                payload.get('stock_code'),
                payload.get('stock_name') or payload.get('stock_code') or '',
                int(payload.get('quantity') or 0),
                float(payload.get('cost_price') or 0.0),
                payload.get('current_price'),
                payload.get('market_value'),
                payload.get('profit_rate'),
            )
        return dict(row)

    async def save_paper_trade(self, trade: dict) -> dict:
        payload = dict(trade or {})
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO paper_trades
                    (id, account_id, stock_code, stock_name, trade_type, price, quantity, amount, commission,
                     trade_time, reason, strategy_id, source_order_id, signal_id, position_id, created_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, NOW())
                RETURNING *
                """,
                str(payload.get('id') or ''),
                payload.get('account_id'),
                payload.get('stock_code'),
                payload.get('stock_name') or payload.get('stock_code') or '',
                payload.get('trade_type'),
                float(payload.get('price') or 0.0),
                int(payload.get('quantity') or 0),
                float(payload.get('amount') or 0.0),
                float(payload.get('commission') or 0.0),
                payload.get('trade_time'),
                payload.get('reason'),
                payload.get('strategy_id'),
                payload.get('source_order_id'),
                payload.get('signal_id'),
                payload.get('position_id'),
            )
        return dict(row)

    async def update_paper_trade_linkage(self, trade_id: str, updates: dict) -> Optional[dict]:
        payload = dict(updates or {})
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE paper_trades
                SET strategy_id = COALESCE($2, strategy_id),
                    source_order_id = COALESCE($3, source_order_id),
                    signal_id = COALESCE($4, signal_id),
                    position_id = COALESCE($5, position_id)
                WHERE id = $1
                RETURNING *
                """,
                str(trade_id),
                payload.get("strategy_id"),
                payload.get("source_order_id"),
                payload.get("signal_id"),
                payload.get("position_id"),
            )
        return dict(row) if row else None

    async def get_strategy_trade_position(self, position_id: str) -> Optional[dict]:
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM strategy_trade_positions WHERE position_id = $1",
                str(position_id),
            )
        return dict(row) if row else None

    async def list_strategy_trade_positions(
        self,
        strategy_id: Optional[str] = None,
        account_id: Optional[str] = None,
        code: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 200,
    ) -> List[dict]:
        async with self.acquire() as conn:
            sql = "SELECT * FROM strategy_trade_positions WHERE 1=1"
            params: list[Any] = []
            idx = 1
            if strategy_id:
                sql += f" AND strategy_id = ${idx}"
                params.append(strategy_id)
                idx += 1
            if account_id:
                sql += f" AND account_id = ${idx}"
                params.append(account_id)
                idx += 1
            if code:
                sql += f" AND code = ${idx}"
                params.append(code)
                idx += 1
            if status:
                sql += f" AND status = ${idx}"
                params.append(status)
                idx += 1
            sql += f" ORDER BY COALESCE(closed_at, opened_at, created_at) DESC LIMIT ${idx}"
            params.append(max(1, min(int(limit or 200), 5000)))
            rows = await conn.fetch(sql, *params)
        return [dict(row) for row in rows]

    async def save_strategy_trade_position(self, position: dict) -> dict:
        payload = dict(position or {})
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO strategy_trade_positions
                    (position_id, strategy_id, account_id, signal_id, code, direction, status,
                     entry_order_id, exit_order_id, entry_trade_id, exit_trade_id,
                     entry_shares, exit_shares, remaining_shares,
                     entry_amount, exit_amount, entry_commission, exit_commission,
                     realized_pnl, realized_return, pnl_conversion_efficiency,
                     execution_conversion_efficiency, trade_expectancy, audit_eligible,
                     opened_at, closed_at, last_trade_time,
                     entry_ts, exit_ts, entry_avg_price, exit_avg_price, gross_qty,
                     gross_return, net_return, gross_pnl, net_pnl, hold_days, exit_reason,
                     mfe, mae, price_path_audit_status, created_at, updated_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7,
                        $8, $9, $10, $11,
                        $12, $13, $14,
                        $15, $16, $17, $18,
                        $19, $20, $21,
                        $22, $23, $24,
                        $25, $26, $27,
                        $28, $29, $30, $31, $32,
                        $33, $34, $35, $36, $37, $38,
                        $39, $40, $41, NOW(), NOW())
                ON CONFLICT (position_id) DO UPDATE SET
                    strategy_id = COALESCE(EXCLUDED.strategy_id, strategy_trade_positions.strategy_id),
                    account_id = COALESCE(EXCLUDED.account_id, strategy_trade_positions.account_id),
                    signal_id = COALESCE(EXCLUDED.signal_id, strategy_trade_positions.signal_id),
                    code = COALESCE(EXCLUDED.code, strategy_trade_positions.code),
                    direction = COALESCE(EXCLUDED.direction, strategy_trade_positions.direction),
                    status = COALESCE(EXCLUDED.status, strategy_trade_positions.status),
                    entry_order_id = COALESCE(EXCLUDED.entry_order_id, strategy_trade_positions.entry_order_id),
                    exit_order_id = COALESCE(EXCLUDED.exit_order_id, strategy_trade_positions.exit_order_id),
                    entry_trade_id = COALESCE(EXCLUDED.entry_trade_id, strategy_trade_positions.entry_trade_id),
                    exit_trade_id = COALESCE(EXCLUDED.exit_trade_id, strategy_trade_positions.exit_trade_id),
                    entry_shares = COALESCE(EXCLUDED.entry_shares, strategy_trade_positions.entry_shares),
                    exit_shares = COALESCE(EXCLUDED.exit_shares, strategy_trade_positions.exit_shares),
                    remaining_shares = COALESCE(EXCLUDED.remaining_shares, strategy_trade_positions.remaining_shares),
                    entry_amount = COALESCE(EXCLUDED.entry_amount, strategy_trade_positions.entry_amount),
                    exit_amount = COALESCE(EXCLUDED.exit_amount, strategy_trade_positions.exit_amount),
                    entry_commission = COALESCE(EXCLUDED.entry_commission, strategy_trade_positions.entry_commission),
                    exit_commission = COALESCE(EXCLUDED.exit_commission, strategy_trade_positions.exit_commission),
                    realized_pnl = COALESCE(EXCLUDED.realized_pnl, strategy_trade_positions.realized_pnl),
                    realized_return = COALESCE(EXCLUDED.realized_return, strategy_trade_positions.realized_return),
                    pnl_conversion_efficiency = COALESCE(EXCLUDED.pnl_conversion_efficiency, strategy_trade_positions.pnl_conversion_efficiency),
                    execution_conversion_efficiency = COALESCE(EXCLUDED.execution_conversion_efficiency, strategy_trade_positions.execution_conversion_efficiency),
                    trade_expectancy = COALESCE(EXCLUDED.trade_expectancy, strategy_trade_positions.trade_expectancy),
                    audit_eligible = COALESCE(EXCLUDED.audit_eligible, strategy_trade_positions.audit_eligible),
                    opened_at = COALESCE(EXCLUDED.opened_at, strategy_trade_positions.opened_at),
                    closed_at = COALESCE(EXCLUDED.closed_at, strategy_trade_positions.closed_at),
                    last_trade_time = COALESCE(EXCLUDED.last_trade_time, strategy_trade_positions.last_trade_time),
                    entry_ts = COALESCE(EXCLUDED.entry_ts, strategy_trade_positions.entry_ts),
                    exit_ts = COALESCE(EXCLUDED.exit_ts, strategy_trade_positions.exit_ts),
                    entry_avg_price = COALESCE(EXCLUDED.entry_avg_price, strategy_trade_positions.entry_avg_price),
                    exit_avg_price = COALESCE(EXCLUDED.exit_avg_price, strategy_trade_positions.exit_avg_price),
                    gross_qty = COALESCE(EXCLUDED.gross_qty, strategy_trade_positions.gross_qty),
                    gross_return = COALESCE(EXCLUDED.gross_return, strategy_trade_positions.gross_return),
                    net_return = COALESCE(EXCLUDED.net_return, strategy_trade_positions.net_return),
                    gross_pnl = COALESCE(EXCLUDED.gross_pnl, strategy_trade_positions.gross_pnl),
                    net_pnl = COALESCE(EXCLUDED.net_pnl, strategy_trade_positions.net_pnl),
                    hold_days = COALESCE(EXCLUDED.hold_days, strategy_trade_positions.hold_days),
                    exit_reason = COALESCE(EXCLUDED.exit_reason, strategy_trade_positions.exit_reason),
                    mfe = COALESCE(EXCLUDED.mfe, strategy_trade_positions.mfe),
                    mae = COALESCE(EXCLUDED.mae, strategy_trade_positions.mae),
                    price_path_audit_status = COALESCE(EXCLUDED.price_path_audit_status, strategy_trade_positions.price_path_audit_status),
                    updated_at = NOW()
                RETURNING *
                """,
                str(payload.get("position_id") or ""),
                payload.get("strategy_id"),
                payload.get("account_id"),
                payload.get("signal_id"),
                payload.get("code"),
                payload.get("direction") or "long",
                payload.get("status") or "pending_entry",
                payload.get("entry_order_id"),
                payload.get("exit_order_id"),
                payload.get("entry_trade_id"),
                payload.get("exit_trade_id"),
                payload.get("entry_shares"),
                payload.get("exit_shares"),
                payload.get("remaining_shares"),
                payload.get("entry_amount"),
                payload.get("exit_amount"),
                payload.get("entry_commission"),
                payload.get("exit_commission"),
                payload.get("realized_pnl"),
                payload.get("realized_return"),
                payload.get("pnl_conversion_efficiency"),
                payload.get("execution_conversion_efficiency"),
                payload.get("trade_expectancy"),
                payload.get("audit_eligible"),
                _coerce_ts(payload.get("opened_at")),
                _coerce_ts(payload.get("closed_at")),
                _coerce_ts(payload.get("last_trade_time")),
                _coerce_ts(payload.get("entry_ts")),
                _coerce_ts(payload.get("exit_ts")),
                payload.get("entry_avg_price"),
                payload.get("exit_avg_price"),
                payload.get("gross_qty"),
                payload.get("gross_return"),
                payload.get("net_return"),
                payload.get("gross_pnl"),
                payload.get("net_pnl"),
                payload.get("hold_days"),
                payload.get("exit_reason"),
                payload.get("mfe"),
                payload.get("mae"),
                payload.get("price_path_audit_status"),
            )
        return dict(row)

    async def list_strategy_trade_position_fills(
        self,
        *,
        position_id: Optional[str] = None,
        strategy_id: Optional[str] = None,
        limit: int = 500,
    ) -> List[dict]:
        async with self.acquire() as conn:
            sql = "SELECT * FROM strategy_trade_position_fills WHERE 1=1"
            params: list[Any] = []
            idx = 1
            if position_id:
                sql += f" AND position_id = ${idx}"
                params.append(position_id)
                idx += 1
            if strategy_id:
                sql += f" AND strategy_id = ${idx}"
                params.append(strategy_id)
                idx += 1
            sql += f" ORDER BY trade_time ASC, created_at ASC LIMIT ${idx}"
            params.append(max(1, min(int(limit or 500), 5000)))
            rows = await conn.fetch(sql, *params)
        return [dict(row) for row in rows]

    async def save_strategy_trade_position_fill(self, fill: dict) -> dict:
        payload = dict(fill or {})
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO strategy_trade_position_fills
                    (fill_id, position_id, trade_id, order_id, signal_id, strategy_id, account_id, code,
                     fill_side, quantity, price, amount, commission, trade_time, payload, created_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8,
                        $9, $10, $11, $12, $13, $14, $15::jsonb, NOW())
                ON CONFLICT (trade_id) DO UPDATE SET
                    position_id = COALESCE(EXCLUDED.position_id, strategy_trade_position_fills.position_id),
                    order_id = COALESCE(EXCLUDED.order_id, strategy_trade_position_fills.order_id),
                    signal_id = COALESCE(EXCLUDED.signal_id, strategy_trade_position_fills.signal_id),
                    strategy_id = COALESCE(EXCLUDED.strategy_id, strategy_trade_position_fills.strategy_id),
                    account_id = COALESCE(EXCLUDED.account_id, strategy_trade_position_fills.account_id),
                    code = COALESCE(EXCLUDED.code, strategy_trade_position_fills.code),
                    fill_side = COALESCE(EXCLUDED.fill_side, strategy_trade_position_fills.fill_side),
                    quantity = COALESCE(EXCLUDED.quantity, strategy_trade_position_fills.quantity),
                    price = COALESCE(EXCLUDED.price, strategy_trade_position_fills.price),
                    amount = COALESCE(EXCLUDED.amount, strategy_trade_position_fills.amount),
                    commission = COALESCE(EXCLUDED.commission, strategy_trade_position_fills.commission),
                    trade_time = COALESCE(EXCLUDED.trade_time, strategy_trade_position_fills.trade_time),
                    payload = COALESCE(EXCLUDED.payload, strategy_trade_position_fills.payload)
                RETURNING *
                """,
                str(payload.get("fill_id") or ""),
                payload.get("position_id"),
                payload.get("trade_id"),
                payload.get("order_id"),
                payload.get("signal_id"),
                payload.get("strategy_id"),
                payload.get("account_id"),
                payload.get("code"),
                payload.get("fill_side"),
                payload.get("quantity"),
                payload.get("price"),
                payload.get("amount"),
                payload.get("commission"),
                payload.get("trade_time"),
                json.dumps(payload.get("payload") or {}, ensure_ascii=False, default=str),
            )
        return dict(row)

    async def save_paper_nav(self, nav: dict) -> dict:
        payload = dict(nav or {})
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO paper_nav
                    (account_id, nav_date, total_value, cash, market_value, daily_return, created_at)
                VALUES ($1, $2, $3, $4, $5, $6, NOW())
                ON CONFLICT (account_id, nav_date) DO UPDATE SET
                    total_value = EXCLUDED.total_value,
                    cash = EXCLUDED.cash,
                    market_value = EXCLUDED.market_value,
                    daily_return = EXCLUDED.daily_return
                RETURNING *
                """,
                payload.get('account_id'),
                payload.get('nav_date'),
                float(payload.get('total_value') or 0.0),
                float(payload.get('cash') or 0.0),
                float(payload.get('market_value') or 0.0),
                payload.get('daily_return'),
            )
        return dict(row)

    async def get_paper_nav_rows(self, account_id: str, limit: int = 60) -> List[dict]:
        async with self.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM paper_nav WHERE account_id = $1 ORDER BY nav_date DESC LIMIT $2",
                account_id,
                max(1, min(int(limit or 60), 365)),
            )
        return [dict(row) for row in rows]

    async def get_paper_order_summary(self, account_id: str) -> dict:
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT
                    COALESCE((SELECT COUNT(*) FROM paper_orders WHERE account_id = $1), 0)::int AS total_orders,
                    COALESCE((SELECT COUNT(*) FROM paper_orders WHERE account_id = $1 AND status = 'filled'), 0)::int AS filled_orders,
                    COALESCE((SELECT COUNT(*) FROM paper_trades WHERE account_id = $1), 0)::int AS total_trades,
                    COALESCE((SELECT SUM(amount) FROM paper_trades WHERE account_id = $1), 0)::float AS trade_amount
                """,
                account_id,
            )
        return {
            'total_orders': int((row or {}).get('total_orders') or 0),
            'filled_orders': int((row or {}).get('filled_orders') or 0),
            'total_trades': int((row or {}).get('total_trades') or 0),
            'trade_amount': float((row or {}).get('trade_amount') or 0.0),
        }

    @staticmethod
    def _aggregate_trade_position(existing: Optional[dict], fills: list[dict]) -> dict:
        return aggregate_trade_position(existing, fills)

    async def _enrich_trade_position_price_path(self, position: Optional[dict]) -> dict:
        payload = dict(position or {})
        entry_ts = _coerce_ts(payload.get("entry_ts") or payload.get("opened_at"))
        exit_ts = _coerce_ts(payload.get("exit_ts") or payload.get("closed_at") or payload.get("last_trade_time"))
        entry_avg_price = _safe_float(payload.get("entry_avg_price"))
        code = _string(payload.get("code"))
        direction = _string(payload.get("direction")).lower() or "long"
        if not code or entry_avg_price is None or entry_avg_price <= 0 or entry_ts is None:
            payload["price_path_audit_status"] = "missing_entry_context"
            return payload
        if not hasattr(self, "get_klines"):
            payload["price_path_audit_status"] = "missing_kline_source"
            return payload
        start_date = entry_ts.date().isoformat() if isinstance(entry_ts, datetime) else str(entry_ts)
        resolved_end_ts = exit_ts or datetime.utcnow()
        end_date = (
            resolved_end_ts.date().isoformat()
            if isinstance(resolved_end_ts, datetime)
            else str(resolved_end_ts)
        )
        try:
            klines = await self.get_klines(code, start_date=start_date, end_date=end_date)
        except Exception:
            payload["price_path_audit_status"] = "missing_kline"
            return payload
        if not klines:
            payload["price_path_audit_status"] = "missing_kline"
            return payload
        favorable_moves: list[float] = []
        adverse_moves: list[float] = []
        for item in klines:
            high = _safe_float(dict(item).get("high"))
            low = _safe_float(dict(item).get("low"))
            if high is None or low is None:
                continue
            if direction == "short":
                favorable_moves.append((entry_avg_price - low) / entry_avg_price)
                adverse_moves.append((entry_avg_price - high) / entry_avg_price)
            else:
                favorable_moves.append((high - entry_avg_price) / entry_avg_price)
                adverse_moves.append((low - entry_avg_price) / entry_avg_price)
        payload["mfe"] = round(max(favorable_moves), 6) if favorable_moves else None
        payload["mae"] = round(min(adverse_moves), 6) if adverse_moves else None
        payload["price_path_audit_status"] = (
            "audited_closed_position"
            if str(payload.get("status") or "") == "closed"
            else "audited_open_position"
        )
        return payload

    async def refresh_strategy_trade_position(self, position_id: str) -> Optional[dict]:
        fills = await self.list_strategy_trade_position_fills(position_id=str(position_id), limit=2000)
        if not fills:
            return await self.get_strategy_trade_position(position_id)
        existing = await self.get_strategy_trade_position(position_id)
        aggregate = self._aggregate_trade_position(existing, fills)
        aggregate["position_id"] = str(position_id)
        aggregate = await self._enrich_trade_position_price_path(aggregate)
        return await self.save_strategy_trade_position(aggregate)

    async def backfill_trade_position_links(self, strategy_id: Optional[str] = None) -> dict:
        strategy_filter = str(strategy_id or "").strip() or None
        async with self.acquire() as conn:
            await conn.execute(
                """
                UPDATE paper_trades
                SET signal_id = COALESCE(paper_trades.signal_id, paper_orders.signal_id),
                    position_id = COALESCE(paper_trades.position_id, paper_orders.position_id),
                    strategy_id = COALESCE(paper_trades.strategy_id, paper_orders.strategy_id)
                FROM paper_orders
                WHERE paper_trades.source_order_id = paper_orders.id::text
                  AND paper_orders.position_id IS NOT NULL
                  AND ($1::text IS NULL OR COALESCE(paper_trades.strategy_id, paper_orders.strategy_id) = $1)
                """,
                strategy_filter,
            )
        positions_touched: set[str] = set()
        trades = await self.list_strategy_paper_trades(strategy_filter, limit=5000) if strategy_filter else []
        if not strategy_filter:
            async with self.acquire() as conn:
                rows = await conn.fetch(
                    "SELECT * FROM paper_trades ORDER BY trade_time DESC, created_at DESC LIMIT 5000"
                )
            trades = [dict(row) for row in rows]
        for trade in trades:
            position_id_value = str(trade.get("position_id") or "").strip()
            if not position_id_value:
                continue
            fill_id = str(trade.get("id") or "").strip()
            await self.save_strategy_trade_position_fill(
                {
                    "fill_id": f"fill_{fill_id}" if fill_id else "",
                    "position_id": position_id_value,
                    "trade_id": trade.get("id"),
                    "order_id": trade.get("source_order_id"),
                    "signal_id": trade.get("signal_id"),
                    "strategy_id": trade.get("strategy_id"),
                    "account_id": trade.get("account_id"),
                    "code": trade.get("stock_code"),
                    "fill_side": trade.get("trade_type"),
                    "quantity": int(trade.get("quantity") or 0),
                    "price": float(trade.get("price") or 0.0),
                    "amount": float(trade.get("amount") or 0.0),
                    "commission": float(trade.get("commission") or 0.0),
                    "trade_time": trade.get("trade_time"),
                    "payload": {"source": "paper_trades_backfill"},
                }
            )
            positions_touched.add(position_id_value)
        for position_id_value in positions_touched:
            await self.refresh_strategy_trade_position(position_id_value)
        return {
            "strategy_id": strategy_filter,
            "position_count": len(positions_touched),
            "fill_count": len(
                [
                    trade
                    for trade in trades
                    if str(trade.get("position_id") or "").strip()
                ]
            ),
        }

    async def get_strategy_trade_audit_summary(self, strategy_id: str) -> dict:
        from ...services.strategy_lifecycle_shared import evaluate_execution_audit_gate

        await self.backfill_trade_position_links(strategy_id)
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT
                    COALESCE(COUNT(*), 0)::int AS mapped_position_count,
                    COALESCE(COUNT(*) FILTER (WHERE audit_eligible), 0)::int AS realized_trade_count,
                    COALESCE(COUNT(*) FILTER (WHERE NOT audit_eligible), 0)::int AS incomplete_position_count,
                    COALESCE(AVG(realized_return) FILTER (WHERE audit_eligible), 0)::float AS trade_expectancy,
                    COALESCE(
                        SUM(realized_pnl) FILTER (WHERE audit_eligible)
                        / NULLIF(SUM(entry_amount + entry_commission) FILTER (WHERE audit_eligible), 0),
                        0
                    )::float AS pnl_conversion_efficiency,
                    COALESCE(
                        AVG(execution_conversion_efficiency) FILTER (WHERE audit_eligible),
                        0
                    )::float AS execution_conversion_efficiency,
                    COALESCE(
                        AVG(CASE WHEN realized_pnl > 0 THEN 1.0 ELSE 0.0 END) FILTER (WHERE audit_eligible),
                        0
                    )::float AS execution_win_rate,
                    COALESCE(
                        AVG(CASE WHEN realized_pnl > 0 THEN realized_pnl END) FILTER (WHERE audit_eligible)
                        / NULLIF(ABS(AVG(CASE WHEN realized_pnl < 0 THEN realized_pnl END) FILTER (WHERE audit_eligible)), 0),
                        0
                    )::float AS avg_win_loss_ratio,
                    COALESCE(SUM(realized_pnl) FILTER (WHERE audit_eligible), 0)::float AS realized_pnl_total
                FROM strategy_trade_positions
                WHERE strategy_id = $1
                """,
                strategy_id,
            )
        payload = dict(row or {})
        realized_trade_count = int(payload.get("realized_trade_count") or 0)
        trade_expectancy = float(payload.get("trade_expectancy") or 0.0)
        pnl_conversion_efficiency = float(payload.get("pnl_conversion_efficiency") or 0.0)
        execution_conversion_efficiency = float(payload.get("execution_conversion_efficiency") or 0.0)
        gate_status, gate_reasons, metric_passes, hard_gate_metrics = evaluate_execution_audit_gate(
            {
                **payload,
                "realized_trade_count": realized_trade_count,
                "trade_expectancy": trade_expectancy,
                "pnl_conversion_efficiency": pnl_conversion_efficiency,
                "execution_conversion_efficiency": execution_conversion_efficiency,
            }
        )
        return {
            "approximate": False,
            "audit_grade": realized_trade_count > 0,
            "method": "position_id_round_trip_v1",
            "source_tables": [
                "paper_orders",
                "paper_trades",
                "strategy_trade_positions",
                "strategy_trade_position_fills",
            ],
            "mapped_position_count": int(payload.get("mapped_position_count") or 0),
            "realized_trade_count": realized_trade_count,
            "incomplete_position_count": int(payload.get("incomplete_position_count") or 0),
            "trade_expectancy": round(trade_expectancy, 6),
            "pnl_conversion_efficiency": round(pnl_conversion_efficiency, 6),
            "execution_conversion_efficiency": round(execution_conversion_efficiency, 6),
            "execution_win_rate": round(float(payload.get("execution_win_rate") or 0.0), 6),
            "avg_win_loss_ratio": round(float(payload.get("avg_win_loss_ratio") or 0.0), 6),
            "realized_pnl_total": round(float(payload.get("realized_pnl_total") or 0.0), 4),
            "audit_ready_for_hard_gate": gate_status == "passed",
            "execution_audit_gate_status": gate_status,
            "execution_audit_gate_reasons": gate_reasons,
            "hard_gate_metric_passes": metric_passes,
            "hard_gate_metrics": hard_gate_metrics,
        }

    async def get_execution_audit_verification(self, strategy_id: Optional[str] = None) -> dict:
        strategy_filter = _string(strategy_id) or None
        async with self.acquire() as conn:
            async def _table_present(table_name: str) -> bool:
                return bool(
                    await conn.fetchval(
                        "SELECT to_regclass($1::text) IS NOT NULL",
                        table_name,
                    )
                )

            async def _column_present(table_name: str, column_name: str) -> bool:
                return bool(
                    await conn.fetchval(
                        """
                        SELECT EXISTS (
                            SELECT 1
                            FROM information_schema.columns
                            WHERE table_name = $1
                              AND column_name = $2
                        )
                        """,
                        table_name,
                        column_name,
                    )
                )

            async def _count_rows(table_name: str, *, column_name: Optional[str] = None) -> int:
                where_clause = "WHERE ($1::text IS NULL OR strategy_id = $1)"
                if column_name:
                    where_clause += f" AND NULLIF(TRIM(COALESCE({column_name}, '')), '') IS NOT NULL"
                row = await conn.fetchrow(
                    f"""
                    SELECT COALESCE(COUNT(*), 0)::int AS count
                    FROM {table_name}
                    {where_clause}
                    """,
                    strategy_filter,
                )
                return int(dict(row or {}).get("count") or 0)

            table_presence = {
                table_name: await _table_present(table_name)
                for table_name in _EXECUTION_AUDIT_REQUIRED_TABLES
            }
            column_presence = {
                table_name: {
                    column_name: await _column_present(table_name, column_name)
                    for column_name in required_columns
                }
                for table_name, required_columns in _EXECUTION_AUDIT_REQUIRED_COLUMNS.items()
            }
            migration_table_present = await _table_present("market_schema_migrations")
            migration_presence = {}
            if migration_table_present:
                for migration_key in _EXECUTION_AUDIT_REQUIRED_MIGRATIONS:
                    migration_presence[migration_key] = bool(
                        await conn.fetchval(
                            """
                            SELECT EXISTS (
                                SELECT 1
                                FROM market_schema_migrations
                                WHERE migration_key = $1
                            )
                            """,
                            migration_key,
                        )
                    )
            else:
                migration_presence = {
                    migration_key: False
                    for migration_key in _EXECUTION_AUDIT_REQUIRED_MIGRATIONS
                }

            orders_total = await _count_rows("paper_orders")
            orders_signal_linked = await _count_rows("paper_orders", column_name="signal_id")
            orders_position_linked = await _count_rows("paper_orders", column_name="position_id")
            trades_total = await _count_rows("paper_trades")
            trades_signal_linked = await _count_rows("paper_trades", column_name="signal_id")
            trades_position_linked = await _count_rows("paper_trades", column_name="position_id")

            candidate_evidence_count = (
                await _count_rows("strategy_candidate_evidence")
                if table_presence["strategy_candidate_evidence"]
                else 0
            )
            signal_evidence_count = (
                await _count_rows("strategy_signal_evidence")
                if table_presence["strategy_signal_evidence"]
                else 0
            )
            signal_evidence_trade_step_column_present = bool(
                table_presence["strategy_signal_evidence"]
                and await _column_present("strategy_signal_evidence", "applied_trade_step_id")
            )
            signal_evidence_trade_step_count = (
                await _count_rows("strategy_signal_evidence", column_name="applied_trade_step_id")
                if signal_evidence_trade_step_column_present
                else 0
            )
            fill_count = (
                await _count_rows("strategy_trade_position_fills")
                if table_presence["strategy_trade_position_fills"]
                else 0
            )
            runtime_action_reason_column_present = bool(
                table_presence["strategy_signal_evidence"]
                and await _column_present("strategy_signal_evidence", "runtime_action_reason")
            )
            runtime_action_signal_count = 0
            if runtime_action_reason_column_present:
                runtime_action_signal_count = await _count_rows(
                    "strategy_signal_evidence",
                    column_name="runtime_action_reason",
                )
            legacy_evidence_count = 0
            legacy_table_present = await _table_present("strategy_factory_task_evidence")
            if legacy_table_present and strategy_filter:
                row = await conn.fetchrow(
                    """
                    SELECT COALESCE(COUNT(*), 0)::int AS count
                    FROM strategy_factory_task_evidence
                    WHERE COALESCE(evidence_payload->>'strategy_id', '') = $1
                    """,
                    strategy_filter,
                )
                legacy_evidence_count = int(dict(row or {}).get("count") or 0)
            position_count = 0
            position_status_counts: dict[str, int] = {}
            if table_presence["strategy_trade_positions"]:
                row = await conn.fetchrow(
                    """
                    SELECT COALESCE(COUNT(*), 0)::int AS count
                    FROM strategy_trade_positions
                    WHERE ($1::text IS NULL OR strategy_id = $1)
                    """,
                    strategy_filter,
                )
                position_count = int(dict(row or {}).get("count") or 0)
                status_rows = await conn.fetch(
                    """
                    SELECT COALESCE(status, 'unknown') AS status, COUNT(*)::int AS count
                    FROM strategy_trade_positions
                    WHERE ($1::text IS NULL OR strategy_id = $1)
                    GROUP BY COALESCE(status, 'unknown')
                    ORDER BY status
                    """,
                    strategy_filter,
                )
                position_status_counts = {
                    str(dict(item or {}).get("status") or "unknown"): int(
                        dict(item or {}).get("count") or 0
                    )
                    for item in status_rows
                }

        schema_ok = all(table_presence.values()) and all(
            present
            for table_columns in column_presence.values()
            for present in table_columns.values()
        )
        migrations_ok = migration_table_present and all(migration_presence.values())

        audit_summary = None
        if strategy_filter and schema_ok:
            try:
                audit_summary = await self.get_strategy_trade_audit_summary(strategy_filter)
            except Exception as exc:
                logger.warning(
                    "execution audit verification summary failed for %s: %s",
                    strategy_filter,
                    exc,
                )
        if strategy_filter and schema_ok and table_presence["strategy_trade_positions"]:
            position_rows = await self.list_strategy_trade_positions(
                strategy_id=strategy_filter,
                limit=5000,
            )
            fill_rows = (
                await self.list_strategy_trade_position_fills(
                    strategy_id=strategy_filter,
                    limit=5000,
                )
                if table_presence["strategy_trade_position_fills"]
                else []
            )
            position_count = len(position_rows)
            fill_count = len(fill_rows)
            position_status_counts = {}
            for row in position_rows:
                status = str((row or {}).get("status") or "unknown")
                position_status_counts[status] = position_status_counts.get(status, 0) + 1

        recommendations: list[str] = []
        missing_tables = [
            table_name for table_name, present in table_presence.items() if not present
        ]
        if missing_tables:
            recommendations.append(
                "missing required execution-audit tables: " + ", ".join(missing_tables)
            )
        missing_columns = [
            f"{table_name}.{column_name}"
            for table_name, columns in column_presence.items()
            for column_name, present in columns.items()
            if not present
        ]
        if missing_columns:
            recommendations.append(
                "missing paper trading linkage columns: " + ", ".join(missing_columns)
            )
        missing_migrations = [
            migration_key
            for migration_key, present in migration_presence.items()
            if not present
        ]
        if missing_migrations:
            recommendations.append(
                "missing migration/backfill markers: " + ", ".join(missing_migrations)
            )
        if orders_total > 0 and orders_position_linked < orders_total:
            recommendations.append(
                "paper_orders position_id coverage is incomplete; verify phase_5/6 backfill on production data"
            )
        if trades_total > 0 and trades_position_linked < trades_total:
            recommendations.append(
                "paper_trades position_id coverage is incomplete; rerun round-trip linkage/backfill verification"
            )
        if audit_summary and int(audit_summary.get("incomplete_position_count") or 0) > 0:
            recommendations.append(
                "round-trip aggregation still has incomplete positions; inspect refresh_strategy_trade_position/backfill outputs"
            )

        if missing_tables or missing_columns:
            status = "missing_schema"
        elif missing_migrations:
            status = "pending_migration_verification"
        elif recommendations:
            status = "needs_attention"
        else:
            status = "ok"

        def _ratio(numerator: int, denominator: int) -> Optional[float]:
            if denominator <= 0:
                return None
            return round(float(numerator) / float(denominator), 6)

        return {
            "status": status,
            "strategy_id": strategy_filter,
            "method": "execution_audit_verification_v1",
            "schema": {
                "required_tables": {
                    table_name: {"present": present}
                    for table_name, present in table_presence.items()
                },
                "required_columns": {
                    table_name: {
                        column_name: {"present": present}
                        for column_name, present in columns.items()
                    }
                    for table_name, columns in column_presence.items()
                },
                "all_required_tables_present": all(table_presence.values()),
                "all_required_columns_present": all(
                    present
                    for table_columns in column_presence.values()
                    for present in table_columns.values()
                ),
            },
            "migrations": {
                "tracking_table_present": migration_table_present,
                "required_keys": {
                    migration_key: {"applied": present}
                    for migration_key, present in migration_presence.items()
                },
                "all_required_keys_applied": migrations_ok,
            },
            "coverage": {
                "paper_orders": {
                    "total": orders_total,
                    "signal_id_linked": orders_signal_linked,
                    "position_id_linked": orders_position_linked,
                    "signal_id_ratio": _ratio(orders_signal_linked, orders_total),
                    "position_id_ratio": _ratio(orders_position_linked, orders_total),
                },
                "paper_trades": {
                    "total": trades_total,
                    "signal_id_linked": trades_signal_linked,
                    "position_id_linked": trades_position_linked,
                    "signal_id_ratio": _ratio(trades_signal_linked, trades_total),
                    "position_id_ratio": _ratio(trades_position_linked, trades_total),
                },
                "strategy_candidate_evidence_count": candidate_evidence_count,
                "strategy_signal_evidence_count": signal_evidence_count,
                "strategy_signal_step_lineage_count": signal_evidence_trade_step_count,
                "runtime_action_signal_count": runtime_action_signal_count,
            },
            "lineage_source": {
                "status": (
                    "native_ready"
                    if candidate_evidence_count > 0 or signal_evidence_count > 0
                    else "legacy_only"
                    if legacy_evidence_count > 0
                    else "missing"
                ),
                "native_candidate_evidence_count": candidate_evidence_count,
                "native_signal_evidence_count": signal_evidence_count,
                "native_trade_step_lineage_count": signal_evidence_trade_step_count,
                "runtime_action_signal_count": runtime_action_signal_count,
                "legacy_evidence_count": legacy_evidence_count,
            },
            "trade_round_trip": {
                "position_count": position_count,
                "fill_count": fill_count,
                "position_status_counts": position_status_counts,
                "audit_summary": audit_summary,
            },
            "recommendations": recommendations,
        }

    async def list_strategy_incubation_metrics(
        self,
        strategy_id: str,
        limit: int = 30,
        start_date = None,
        end_date = None,
    ) -> List[dict]:
        async with self.acquire() as conn:
            sql = "SELECT * FROM strategy_incubation_metrics WHERE strategy_id = $1"
            params: list = [strategy_id]
            idx = 2
            if start_date is not None:
                sql += f" AND metric_date >= ${idx}"
                params.append(start_date)
                idx += 1
            if end_date is not None:
                sql += f" AND metric_date <= ${idx}"
                params.append(end_date)
                idx += 1
            sql += f" ORDER BY metric_date DESC LIMIT ${idx}"
            params.append(max(1, min(int(limit or 30), 365)))
            rows = await conn.fetch(sql, *params)
        return [self._decode_incubation_metric(dict(row)) for row in rows]

    # ── 孵化流水线快照 ──

    def _decode_incubation_pipeline_snapshot(self, row: dict) -> dict:
        result = dict(row)
        result["blockers"] = self._decode_json_field(result.get("blockers"), [])
        result["risk_flags"] = self._decode_json_field(result.get("risk_flags"), [])
        result["summary"] = self._decode_json_field(result.get("summary"), {})
        result["metadata"] = self._decode_json_field(result.get("metadata"), {})
        if result.get("priority_score") is None:
            result["priority_score"] = result["summary"].get("priority_score", result.get("readiness_score"))
        if result.get("gate_status") is None:
            result["gate_status"] = result["summary"].get("gate_status") or result["metadata"].get("gate_status")
        if result.get("gate_reasons") is None:
            result["gate_reasons"] = list(result["summary"].get("gate_reasons") or result["metadata"].get("gate_reasons") or [])
        return result

    async def save_strategy_incubation_pipeline_snapshot(self, snapshot: dict) -> dict:
        payload = dict(snapshot or {})
        payload["summary"] = {
            **dict(payload.get("summary") or {}),
            "priority_score": payload.get("priority_score", payload.get("readiness_score")),
            "gate_status": payload.get("gate_status"),
            "gate_reasons": list(payload.get("gate_reasons") or []),
        }
        payload["metadata"] = {
            **dict(payload.get("metadata") or {}),
            "gate_status": payload.get("gate_status"),
            "gate_reasons": list(payload.get("gate_reasons") or []),
        }
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO strategy_incubation_pipeline_snapshots
                    (strategy_id, account_id, pipeline_stage, pipeline_status, observed_days, promote_streak,
                     halt_streak, latest_decision, readiness_score, next_action, auto_review, auto_promoted,
                     blockers, risk_flags, summary, metadata, task_run_id, source, evaluated_at, created_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13::jsonb, $14::jsonb, $15::jsonb, $16::jsonb, $17, $18, $19::timestamptz, NOW())
                RETURNING *
                """,
                payload.get("strategy_id"),
                payload.get("account_id"),
                str(payload.get("pipeline_stage") or "warmup"),
                str(payload.get("pipeline_status") or "collecting"),
                int(payload.get("observed_days") or 0),
                int(payload.get("promote_streak") or 0),
                int(payload.get("halt_streak") or 0),
                payload.get("latest_decision"),
                float(payload.get("readiness_score") or 0.0),
                payload.get("next_action"),
                bool(payload.get("auto_review")),
                bool(payload.get("auto_promoted")),
                json.dumps(payload.get("blockers") or [], ensure_ascii=False, default=str),
                json.dumps(payload.get("risk_flags") or [], ensure_ascii=False, default=str),
                json.dumps(payload.get("summary") or {}, ensure_ascii=False, default=str),
                json.dumps(payload.get("metadata") or {}, ensure_ascii=False, default=str),
                payload.get("task_run_id"),
                str(payload.get("source") or "system"),
                self._coerce_timestamp(payload.get("evaluated_at")),
            )
        return self._decode_incubation_pipeline_snapshot(dict(row))

    async def get_latest_strategy_incubation_pipeline_snapshot(self, strategy_id: str) -> Optional[dict]:
        rows = await self.list_strategy_incubation_pipeline_snapshots(strategy_id=strategy_id, limit=1)
        return rows[0] if rows else None

    async def list_strategy_incubation_pipeline_snapshots(
        self,
        strategy_id: Optional[str] = None,
        pipeline_stage: Optional[str] = None,
        pipeline_status: Optional[str] = None,
        limit: int = 20,
    ) -> List[dict]:
        async with self.acquire() as conn:
            sql = "SELECT * FROM strategy_incubation_pipeline_snapshots WHERE 1=1"
            params: list = []
            idx = 1
            if strategy_id:
                sql += f" AND strategy_id = ${idx}"
                params.append(strategy_id)
                idx += 1
            if pipeline_stage:
                sql += f" AND pipeline_stage = ${idx}"
                params.append(pipeline_stage)
                idx += 1
            if pipeline_status:
                sql += f" AND pipeline_status = ${idx}"
                params.append(pipeline_status)
                idx += 1
            sql += f" ORDER BY evaluated_at DESC, created_at DESC LIMIT ${idx}"
            params.append(max(1, min(int(limit or 20), 500)))
            rows = await conn.fetch(sql, *params)
        return [self._decode_incubation_pipeline_snapshot(dict(row)) for row in rows]
