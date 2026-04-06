"""TimescaleDB 适配器 — 策略 AI Mixin (generation experiments / task runs / factory runs)"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class StrategyAIMixin:
    """AI 生成实验 / 任务运行 / 工厂运行"""

    # ------------------------------------------------------------------
    # generation experiments
    # ------------------------------------------------------------------

    def _decode_generation_experiment(self, row: dict) -> dict:
        result = dict(row)
        for key in ("parameters", "strategy_spec", "evaluation", "result"):
            result[key] = self._decode_json_field(result.get(key), {})
        return result

    async def save_strategy_generation_experiment(self, experiment: dict) -> dict:
        payload = dict(experiment or {})
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO strategy_generation_experiments
                    (experiment_id, strategy_id, parent_strategy_id, generated_strategy_id, task_run_id,
                     source, generator_type, optimizer_type, status, hypothesis,
                     prompt, parameters, strategy_spec, evaluation, result, parent_experiment_id,
                     artifact_id, created_at, updated_at)
                VALUES ($1, $2, $3, $4, $5,
                        $6, $7, $8, $9, $10,
                        $11, $12::jsonb, $13::jsonb, $14::jsonb, $15::jsonb, $16,
                        $17, NOW(), NOW())
                ON CONFLICT (experiment_id) DO UPDATE SET
                    strategy_id = EXCLUDED.strategy_id,
                    parent_strategy_id = EXCLUDED.parent_strategy_id,
                    generated_strategy_id = EXCLUDED.generated_strategy_id,
                    task_run_id = EXCLUDED.task_run_id,
                    source = EXCLUDED.source,
                    generator_type = EXCLUDED.generator_type,
                    optimizer_type = EXCLUDED.optimizer_type,
                    status = EXCLUDED.status,
                    hypothesis = EXCLUDED.hypothesis,
                    prompt = EXCLUDED.prompt,
                    parameters = EXCLUDED.parameters,
                    strategy_spec = EXCLUDED.strategy_spec,
                    evaluation = EXCLUDED.evaluation,
                    result = EXCLUDED.result,
                    parent_experiment_id = EXCLUDED.parent_experiment_id,
                    artifact_id = EXCLUDED.artifact_id,
                    updated_at = NOW()
                RETURNING *
                """,
                str(payload.get("experiment_id") or ""),
                payload.get("strategy_id"),
                payload.get("parent_strategy_id"),
                payload.get("generated_strategy_id"),
                payload.get("task_run_id"),
                str(payload.get("source") or "unknown"),
                str(payload.get("generator_type") or "rule"),
                payload.get("optimizer_type"),
                str(payload.get("status") or "draft"),
                payload.get("hypothesis"),
                payload.get("prompt"),
                json.dumps(payload.get("parameters") or {}, ensure_ascii=False, default=str),
                json.dumps(payload.get("strategy_spec") or {}, ensure_ascii=False, default=str),
                json.dumps(payload.get("evaluation") or {}, ensure_ascii=False, default=str),
                json.dumps(payload.get("result") or {}, ensure_ascii=False, default=str),
                payload.get("parent_experiment_id"),
                payload.get("artifact_id"),
            )
        return self._decode_generation_experiment(dict(row))

    async def get_strategy_generation_experiment(self, experiment_id: str) -> Optional[dict]:
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT * FROM strategy_generation_experiments
                WHERE experiment_id = $1
                LIMIT 1
                """,
                experiment_id,
            )
        if not row:
            return None
        return self._decode_generation_experiment(dict(row))

    async def list_strategy_generation_experiments(
        self,
        strategy_id: Optional[str] = None,
        parent_strategy_id: Optional[str] = None,
        generated_strategy_id: Optional[str] = None,
        task_run_id: Optional[int] = None,
        status: Optional[str] = None,
        source: Optional[str] = None,
        limit: int = 20,
    ) -> List[dict]:
        async with self.acquire() as conn:
            sql = "SELECT * FROM strategy_generation_experiments WHERE 1=1"
            params: list = []
            idx = 1
            if strategy_id:
                sql += f" AND (strategy_id = ${idx} OR parent_strategy_id = ${idx} OR generated_strategy_id = ${idx})"
                params.append(strategy_id)
                idx += 1
            if parent_strategy_id:
                sql += f" AND parent_strategy_id = ${idx}"
                params.append(parent_strategy_id)
                idx += 1
            if generated_strategy_id:
                sql += f" AND generated_strategy_id = ${idx}"
                params.append(generated_strategy_id)
                idx += 1
            if task_run_id is not None:
                sql += f" AND task_run_id = ${idx}"
                params.append(int(task_run_id))
                idx += 1
            if status:
                sql += f" AND status = ${idx}"
                params.append(status)
                idx += 1
            if source:
                sql += f" AND source = ${idx}"
                params.append(source)
                idx += 1
            sql += f" ORDER BY created_at DESC LIMIT ${idx}"
            params.append(max(1, min(int(limit or 20), 200)))
            rows = await conn.fetch(sql, *params)
        return [self._decode_generation_experiment(dict(row)) for row in rows]

    # ------------------------------------------------------------------
    # task runs
    # ------------------------------------------------------------------

    def _decode_task_run(self, row: dict) -> dict:
        result = dict(row)
        result["payload"] = self._decode_json_field(result.get("payload"), {})
        result["result"] = self._decode_json_field(result.get("result"), {})
        return result

    async def save_strategy_task_run(self, run: dict) -> dict:
        payload = dict(run or {})
        started_at = self._coerce_timestamp(payload.get("started_at"))
        completed_at = self._coerce_timestamp(payload.get("completed_at"))
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO strategy_task_runs
                    (strategy_id, task_name, task_scope, task_key, status, trace_id, payload, result, error, started_at, completed_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8::jsonb, $9, COALESCE($10::timestamptz, NOW()), $11::timestamptz)
                RETURNING *
                """,
                payload.get("strategy_id"),
                str(payload.get("task_name") or "unknown"),
                payload.get("task_scope"),
                payload.get("task_key"),
                str(payload.get("status") or "running"),
                payload.get("trace_id"),
                json.dumps(payload.get("payload") or {}, ensure_ascii=False, default=str),
                json.dumps(payload.get("result") or {}, ensure_ascii=False, default=str),
                payload.get("error"),
                started_at,
                completed_at,
            )
        return self._decode_task_run(dict(row))

    async def update_strategy_task_run(
        self,
        run_id: int,
        status: Optional[str] = None,
        result: Optional[dict] = None,
        error: Optional[str] = None,
        completed_at=None,
    ) -> Optional[dict]:
        completed_at_value = self._coerce_timestamp(completed_at)
        result_json = None if result is None else json.dumps(result, ensure_ascii=False, default=str)
        sql = """
            UPDATE strategy_task_runs
            SET status = COALESCE($2, status),
                result = CASE WHEN $3::jsonb IS NULL THEN result ELSE $3::jsonb END,
                error = COALESCE($4, error),
                completed_at = COALESCE($5::timestamptz, completed_at, NOW())
            WHERE id = $1
            RETURNING *
            """
        for attempt in range(3):
            try:
                async with self.acquire() as conn:
                    row = await conn.fetchrow(
                        sql,
                        int(run_id),
                        status,
                        result_json,
                        error,
                        completed_at_value,
                        timeout=60.0,
                    )
                if not row:
                    return None
                return self._decode_task_run(dict(row))
            except asyncio.TimeoutError:
                if attempt >= 2:
                    raise
                await asyncio.sleep(1.0 * (attempt + 1))
            except Exception:
                raise

    async def list_strategy_task_runs(
        self,
        strategy_id: Optional[str] = None,
        task_name: Optional[str] = None,
        task_scope: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 20,
    ) -> List[dict]:
        async with self.acquire() as conn:
            sql = "SELECT * FROM strategy_task_runs WHERE 1=1"
            params: list = []
            idx = 1
            if strategy_id:
                sql += f" AND strategy_id = ${idx}"
                params.append(strategy_id)
                idx += 1
            if task_name:
                sql += f" AND task_name = ${idx}"
                params.append(task_name)
                idx += 1
            if task_scope:
                sql += f" AND task_scope = ${idx}"
                params.append(task_scope)
                idx += 1
            if status:
                sql += f" AND status = ${idx}"
                params.append(status)
                idx += 1
            sql += f" ORDER BY started_at DESC LIMIT ${idx}"
            params.append(max(1, min(int(limit or 20), 500)))
            rows = await conn.fetch(sql, *params)
        return [self._decode_task_run(dict(row)) for row in rows]

    # ------------------------------------------------------------------
    # factory runs
    # ------------------------------------------------------------------

    def _decode_factory_run(self, row: dict) -> dict:
        result = dict(row)
        for key in ("summary", "stages", "snapshot_summary"):
            result[key] = self._decode_json_field(result.get(key), {})
        return result

    async def save_strategy_factory_run(self, run: dict) -> None:
        run_id = str(run.get("run_id") or "").strip()
        if not run_id:
            raise ValueError("run_id is required")
        started_at = self._coerce_timestamp(run.get("started_at")) or datetime.now(timezone.utc)
        completed_at = self._coerce_timestamp(run.get("completed_at"))
        async with self.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO strategy_factory_runs
                    (run_id, status, started_at, completed_at, elapsed_seconds, summary, stages,
                     snapshot_summary, error)
                VALUES ($1, $2, $3::timestamptz, $4::timestamptz, $5, $6::jsonb, $7::jsonb,
                        $8::jsonb, $9)
                ON CONFLICT (run_id) DO UPDATE SET
                    status = EXCLUDED.status,
                    completed_at = EXCLUDED.completed_at,
                    elapsed_seconds = EXCLUDED.elapsed_seconds,
                    summary = EXCLUDED.summary,
                    stages = EXCLUDED.stages,
                    snapshot_summary = EXCLUDED.snapshot_summary,
                    error = EXCLUDED.error
                """,
                run_id,
                str(run.get("status") or "unknown"),
                started_at,
                completed_at,
                float(run.get("elapsed_seconds") or 0),
                json.dumps(run.get("summary") or {}, ensure_ascii=False, default=str),
                json.dumps(run.get("stages") or {}, ensure_ascii=False, default=str),
                json.dumps(run.get("snapshot_summary") or {}, ensure_ascii=False, default=str),
                run.get("error"),
            )

    async def list_strategy_factory_runs(self, limit: int = 20) -> List[dict]:
        async with self.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM strategy_factory_runs
                ORDER BY started_at DESC
                LIMIT $1
                """,
                max(1, min(int(limit or 20), 100)),
            )
        return [self._decode_factory_run(dict(row)) for row in rows]

    async def get_strategy_factory_run(self, run_id: str) -> Optional[dict]:
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT * FROM strategy_factory_runs
                WHERE run_id = $1
                LIMIT 1
                """,
                run_id,
            )
        if not row:
            return None
        return self._decode_factory_run(dict(row))

    async def get_latest_strategy_factory_run(self) -> Optional[dict]:
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT * FROM strategy_factory_runs
                ORDER BY started_at DESC
                LIMIT 1
                """
            )
        if not row:
            return None
        return self._decode_factory_run(dict(row))

    # ------------------------------------------------------------------
    # strategy factory event-driven store
    # ------------------------------------------------------------------

    def _decode_factory_event_cluster(self, row: dict) -> dict:
        result = dict(row)
        for key in ("source_types", "entities", "commodities", "regions", "themes"):
            result[key] = self._decode_json_field(result.get(key), [])
        result["evidence"] = self._decode_json_field(result.get("evidence"), {})
        return result

    def _decode_factory_theme_definition(self, row: dict) -> dict:
        result = dict(row)
        result["aliases"] = self._decode_json_field(result.get("aliases"), [])
        result["metadata"] = self._decode_json_field(result.get("metadata"), {})
        return result

    def _decode_factory_company_theme_exposure(self, row: dict) -> dict:
        result = dict(row)
        result["evidence"] = self._decode_json_field(result.get("evidence"), {})
        return result

    def _decode_factory_event_signal(self, row: dict) -> dict:
        result = dict(row)
        result["evidence"] = self._decode_json_field(result.get("evidence"), {})
        return result

    def _decode_factory_task_evidence(self, row: dict) -> dict:
        result = dict(row)
        result["evidence_payload"] = self._decode_json_field(result.get("evidence_payload"), {})
        return result

    def _decode_factory_market_internal_snapshot(self, row: dict) -> dict:
        result = dict(row)
        result["hot_sectors"] = self._decode_json_field(result.get("hot_sectors"), [])
        result["cold_sectors"] = self._decode_json_field(result.get("cold_sectors"), [])
        result["metadata"] = self._decode_json_field(result.get("metadata"), {})
        return result

    async def save_factory_market_internal_snapshot(self, item: dict) -> dict:
        payload = dict(item or {})
        snapshot_date = self._coerce_date(payload.get("snapshot_date") or payload.get("date"))
        if snapshot_date is None:
            raise ValueError("snapshot_date is required")
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO strategy_factory_market_internals
                    (snapshot_date, engine, symbol_count, trend_up_count, trend_down_count, avg_return_5d,
                     avg_return_20d, avg_volume_ratio, breadth_score, margin_proxy_5d_change_pct,
                     hot_sectors, cold_sectors, metadata, created_at, updated_at)
                VALUES ($1, $2, $3, $4, $5, $6,
                        $7, $8, $9, $10,
                        $11::jsonb, $12::jsonb, $13::jsonb, NOW(), NOW())
                ON CONFLICT (snapshot_date) DO UPDATE SET
                    engine = EXCLUDED.engine,
                    symbol_count = EXCLUDED.symbol_count,
                    trend_up_count = EXCLUDED.trend_up_count,
                    trend_down_count = EXCLUDED.trend_down_count,
                    avg_return_5d = EXCLUDED.avg_return_5d,
                    avg_return_20d = EXCLUDED.avg_return_20d,
                    avg_volume_ratio = EXCLUDED.avg_volume_ratio,
                    breadth_score = EXCLUDED.breadth_score,
                    margin_proxy_5d_change_pct = EXCLUDED.margin_proxy_5d_change_pct,
                    hot_sectors = EXCLUDED.hot_sectors,
                    cold_sectors = EXCLUDED.cold_sectors,
                    metadata = EXCLUDED.metadata,
                    updated_at = NOW()
                RETURNING *
                """,
                snapshot_date,
                str(payload.get("engine") or "local_db_rule_v1"),
                int(payload.get("symbol_count") or 0),
                int(payload.get("trend_up_count") or 0),
                int(payload.get("trend_down_count") or 0),
                float(payload.get("avg_return_5d") or 0.0),
                float(payload.get("avg_return_20d") or 0.0),
                float(payload.get("avg_volume_ratio") or 1.0),
                float(payload.get("breadth_score") or 0.0),
                float(payload.get("margin_proxy_5d_change_pct") or 0.0),
                json.dumps(payload.get("hot_sectors") or [], ensure_ascii=False, default=str),
                json.dumps(payload.get("cold_sectors") or [], ensure_ascii=False, default=str),
                json.dumps(payload.get("metadata") or {}, ensure_ascii=False, default=str),
            )
        return self._decode_factory_market_internal_snapshot(dict(row))

    async def get_factory_market_internal_snapshot(self, snapshot_date = None) -> Optional[dict]:
        normalized_snapshot_date = None if snapshot_date is None else self._coerce_date(snapshot_date)
        if snapshot_date is not None and normalized_snapshot_date is None:
            raise ValueError("snapshot_date is invalid")
        async with self.acquire() as conn:
            if normalized_snapshot_date is None:
                row = await conn.fetchrow(
                    """
                    SELECT * FROM strategy_factory_market_internals
                    ORDER BY snapshot_date DESC
                    LIMIT 1
                    """
                )
            else:
                row = await conn.fetchrow(
                    """
                    SELECT * FROM strategy_factory_market_internals
                    WHERE snapshot_date = $1
                    LIMIT 1
                    """,
                    normalized_snapshot_date,
                )
        if not row:
            return None
        return self._decode_factory_market_internal_snapshot(dict(row))

    async def list_factory_market_internal_snapshots(self, limit: int = 20) -> List[dict]:
        async with self.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM strategy_factory_market_internals
                ORDER BY snapshot_date DESC
                LIMIT $1
                """,
                max(1, min(int(limit or 20), 200)),
            )
        return [self._decode_factory_market_internal_snapshot(dict(row)) for row in rows]

    async def save_factory_event_cluster(self, item: dict) -> dict:
        payload = dict(item or {})
        event_id = str(payload.get("event_id") or "").strip()
        event_name = str(payload.get("event_name") or payload.get("summary") or "").strip()
        if not event_id:
            raise ValueError("event_id is required")
        if not event_name:
            raise ValueError("event_name is required")
        occurred_at = self._coerce_timestamp(payload.get("occurred_at"))
        last_seen_at = self._coerce_timestamp(payload.get("last_seen_at")) or datetime.now(timezone.utc)
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO strategy_factory_event_clusters
                    (event_id, event_type, event_name, event_scope, summary, direction, intensity, horizon,
                     confidence, source_count, source_types, entities, commodities, regions, themes, evidence,
                     occurred_at, last_seen_at, status, created_at, updated_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8,
                        $9, $10, $11::jsonb, $12::jsonb, $13::jsonb, $14::jsonb, $15::jsonb, $16::jsonb,
                        $17::timestamptz, $18::timestamptz, $19, NOW(), NOW())
                ON CONFLICT (event_id) DO UPDATE SET
                    event_type = EXCLUDED.event_type,
                    event_name = EXCLUDED.event_name,
                    event_scope = EXCLUDED.event_scope,
                    summary = EXCLUDED.summary,
                    direction = EXCLUDED.direction,
                    intensity = EXCLUDED.intensity,
                    horizon = EXCLUDED.horizon,
                    confidence = EXCLUDED.confidence,
                    source_count = EXCLUDED.source_count,
                    source_types = EXCLUDED.source_types,
                    entities = EXCLUDED.entities,
                    commodities = EXCLUDED.commodities,
                    regions = EXCLUDED.regions,
                    themes = EXCLUDED.themes,
                    evidence = EXCLUDED.evidence,
                    occurred_at = EXCLUDED.occurred_at,
                    last_seen_at = EXCLUDED.last_seen_at,
                    status = EXCLUDED.status,
                    updated_at = NOW()
                RETURNING *
                """,
                event_id,
                str(payload.get("event_type") or "macro"),
                event_name,
                str(payload.get("event_scope") or "market"),
                payload.get("summary"),
                str(payload.get("direction") or "neutral"),
                float(payload.get("intensity") or 0.0),
                str(payload.get("horizon") or "swing_5_20d"),
                float(payload.get("confidence") or 0.0),
                int(payload.get("source_count") or 0),
                json.dumps(payload.get("source_types") or [], ensure_ascii=False, default=str),
                json.dumps(payload.get("entities") or [], ensure_ascii=False, default=str),
                json.dumps(payload.get("commodities") or [], ensure_ascii=False, default=str),
                json.dumps(payload.get("regions") or [], ensure_ascii=False, default=str),
                json.dumps(payload.get("themes") or [], ensure_ascii=False, default=str),
                json.dumps(payload.get("evidence") or {}, ensure_ascii=False, default=str),
                occurred_at,
                last_seen_at,
                str(payload.get("status") or "active"),
            )
        return self._decode_factory_event_cluster(dict(row))

    async def list_factory_event_clusters(
        self,
        status: Optional[str] = None,
        event_type: Optional[str] = None,
        limit: int = 20,
    ) -> List[dict]:
        async with self.acquire() as conn:
            sql = "SELECT * FROM strategy_factory_event_clusters WHERE 1=1"
            params: list = []
            idx = 1
            if status:
                sql += f" AND status = ${idx}"
                params.append(str(status))
                idx += 1
            if event_type:
                sql += f" AND event_type = ${idx}"
                params.append(str(event_type))
                idx += 1
            sql += f" ORDER BY last_seen_at DESC, confidence DESC LIMIT ${idx}"
            params.append(max(1, min(int(limit or 20), 200)))
            rows = await conn.fetch(sql, *params)
        return [self._decode_factory_event_cluster(dict(row)) for row in rows]

    async def save_factory_theme_definition(self, item: dict) -> dict:
        payload = dict(item or {})
        theme_code = str(payload.get("theme_code") or "").strip()
        theme_name = str(payload.get("theme_name") or theme_code).strip()
        if not theme_code:
            raise ValueError("theme_code is required")
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO strategy_factory_theme_definitions
                    (theme_code, theme_name, parent_theme_code, description, direction_rule,
                     aliases, metadata, active, created_at, updated_at)
                VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7::jsonb, $8, NOW(), NOW())
                ON CONFLICT (theme_code) DO UPDATE SET
                    theme_name = EXCLUDED.theme_name,
                    parent_theme_code = EXCLUDED.parent_theme_code,
                    description = EXCLUDED.description,
                    direction_rule = EXCLUDED.direction_rule,
                    aliases = EXCLUDED.aliases,
                    metadata = EXCLUDED.metadata,
                    active = EXCLUDED.active,
                    updated_at = NOW()
                RETURNING *
                """,
                theme_code,
                theme_name,
                payload.get("parent_theme_code"),
                payload.get("description"),
                payload.get("direction_rule"),
                json.dumps(payload.get("aliases") or [], ensure_ascii=False, default=str),
                json.dumps(payload.get("metadata") or {}, ensure_ascii=False, default=str),
                bool(payload.get("active", True)),
            )
        return self._decode_factory_theme_definition(dict(row))

    async def list_factory_theme_definitions(self, active_only: bool = True, limit: int = 200) -> List[dict]:
        async with self.acquire() as conn:
            if active_only:
                rows = await conn.fetch(
                    """
                    SELECT * FROM strategy_factory_theme_definitions
                    WHERE active = TRUE
                    ORDER BY theme_code ASC
                    LIMIT $1
                    """,
                    max(1, min(int(limit or 200), 500)),
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT * FROM strategy_factory_theme_definitions
                    ORDER BY theme_code ASC
                    LIMIT $1
                    """,
                    max(1, min(int(limit or 200), 500)),
                )
        return [self._decode_factory_theme_definition(dict(row)) for row in rows]

    async def save_factory_company_theme_exposure(self, item: dict) -> dict:
        payload = dict(item or {})
        symbol = str(payload.get("symbol") or "").strip()
        theme_code = str(payload.get("theme_code") or "").strip()
        exposure_type = str(payload.get("exposure_type") or "revenue")
        if not symbol or not theme_code:
            raise ValueError("symbol and theme_code are required")
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO strategy_factory_company_theme_exposures
                    (symbol, theme_code, exposure_type, direction, exposure_score, evidence, created_at, updated_at)
                VALUES ($1, $2, $3, $4, $5, $6::jsonb, NOW(), NOW())
                ON CONFLICT (symbol, theme_code, exposure_type) DO UPDATE SET
                    direction = EXCLUDED.direction,
                    exposure_score = EXCLUDED.exposure_score,
                    evidence = EXCLUDED.evidence,
                    updated_at = NOW()
                RETURNING *
                """,
                symbol,
                theme_code,
                exposure_type,
                str(payload.get("direction") or "positive"),
                float(payload.get("exposure_score") or 0.0),
                json.dumps(payload.get("evidence") or {}, ensure_ascii=False, default=str),
            )
        return self._decode_factory_company_theme_exposure(dict(row))

    async def list_factory_company_theme_exposures(
        self,
        theme_codes: Optional[List[str]] = None,
        symbols: Optional[List[str]] = None,
        limit: int = 200,
    ) -> List[dict]:
        async with self.acquire() as conn:
            sql = "SELECT * FROM strategy_factory_company_theme_exposures WHERE 1=1"
            params: list = []
            idx = 1
            normalized_theme_codes = [str(item).strip() for item in list(theme_codes or []) if str(item).strip()]
            normalized_symbols = [str(item).strip() for item in list(symbols or []) if str(item).strip()]
            if normalized_theme_codes:
                sql += f" AND theme_code = ANY(${idx}::text[])"
                params.append(normalized_theme_codes)
                idx += 1
            if normalized_symbols:
                sql += f" AND symbol = ANY(${idx}::text[])"
                params.append(normalized_symbols)
                idx += 1
            sql += f" ORDER BY exposure_score DESC, updated_at DESC LIMIT ${idx}"
            params.append(max(1, min(int(limit or 200), 500)))
            rows = await conn.fetch(sql, *params)
        return [self._decode_factory_company_theme_exposure(dict(row)) for row in rows]

    async def save_factory_event_signal(self, item: dict) -> dict:
        payload = dict(item or {})
        event_id = str(payload.get("event_id") or "").strip()
        symbol = str(payload.get("symbol") or payload.get("code") or "").strip()
        theme_code = str(payload.get("theme_code") or "").strip()
        observed_at = self._coerce_timestamp(payload.get("observed_at")) or datetime.now(timezone.utc)
        if not event_id or not symbol:
            raise ValueError("event_id and symbol are required")
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO strategy_factory_event_signals
                    (event_id, symbol, theme_code, direction, theme_score, exposure_score, price_confirm_score,
                     flow_confirm_score, fundamental_confirm_score, final_score, rationale, evidence,
                     observed_at, created_at, updated_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7,
                        $8, $9, $10, $11, $12::jsonb,
                        $13::timestamptz, NOW(), NOW())
                ON CONFLICT (event_id, symbol, theme_code) DO UPDATE SET
                    direction = EXCLUDED.direction,
                    theme_score = EXCLUDED.theme_score,
                    exposure_score = EXCLUDED.exposure_score,
                    price_confirm_score = EXCLUDED.price_confirm_score,
                    flow_confirm_score = EXCLUDED.flow_confirm_score,
                    fundamental_confirm_score = EXCLUDED.fundamental_confirm_score,
                    final_score = EXCLUDED.final_score,
                    rationale = EXCLUDED.rationale,
                    evidence = EXCLUDED.evidence,
                    observed_at = EXCLUDED.observed_at,
                    updated_at = NOW()
                RETURNING *
                """,
                event_id,
                symbol,
                theme_code,
                str(payload.get("direction") or "positive"),
                float(payload.get("theme_score") or 0.0),
                float(payload.get("exposure_score") or 0.0),
                float(payload.get("price_confirm_score") or 0.0),
                float(payload.get("flow_confirm_score") or 0.0),
                float(payload.get("fundamental_confirm_score") or 0.0),
                float(payload.get("final_score") or 0.0),
                payload.get("rationale"),
                json.dumps(payload.get("evidence") or {}, ensure_ascii=False, default=str),
                observed_at,
            )
        return self._decode_factory_event_signal(dict(row))

    async def list_factory_event_signals(
        self,
        event_id: Optional[str] = None,
        theme_code: Optional[str] = None,
        symbols: Optional[List[str]] = None,
        min_final_score: Optional[float] = None,
        limit: int = 200,
    ) -> List[dict]:
        async with self.acquire() as conn:
            sql = "SELECT * FROM strategy_factory_event_signals WHERE 1=1"
            params: list = []
            idx = 1
            if event_id:
                sql += f" AND event_id = ${idx}"
                params.append(str(event_id))
                idx += 1
            if theme_code is not None:
                sql += f" AND theme_code = ${idx}"
                params.append(str(theme_code))
                idx += 1
            normalized_symbols = [str(item).strip() for item in list(symbols or []) if str(item).strip()]
            if normalized_symbols:
                sql += f" AND symbol = ANY(${idx}::text[])"
                params.append(normalized_symbols)
                idx += 1
            if min_final_score is not None:
                sql += f" AND final_score >= ${idx}"
                params.append(float(min_final_score))
                idx += 1
            sql += f" ORDER BY final_score DESC, observed_at DESC LIMIT ${idx}"
            params.append(max(1, min(int(limit or 200), 500)))
            rows = await conn.fetch(sql, *params)
        return [self._decode_factory_event_signal(dict(row)) for row in rows]

    async def save_factory_task_evidence(self, item: dict) -> dict:
        payload = dict(item or {})
        task_key = str(payload.get("task_key") or "").strip()
        evidence_type = str(payload.get("evidence_type") or "").strip()
        if not task_key or not evidence_type:
            raise ValueError("task_key and evidence_type are required")
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO strategy_factory_task_evidence
                    (task_key, event_id, theme_code, symbol, evidence_type, weight, evidence_payload, created_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, NOW())
                RETURNING *
                """,
                task_key,
                payload.get("event_id"),
                str(payload.get("theme_code") or ""),
                payload.get("symbol"),
                evidence_type,
                float(payload.get("weight") or 0.0),
                json.dumps(payload.get("evidence_payload") or {}, ensure_ascii=False, default=str),
            )
        return self._decode_factory_task_evidence(dict(row))

    async def list_factory_task_evidence(
        self,
        task_key: Optional[str] = None,
        event_id: Optional[str] = None,
        limit: int = 200,
    ) -> List[dict]:
        async with self.acquire() as conn:
            sql = "SELECT * FROM strategy_factory_task_evidence WHERE 1=1"
            params: list = []
            idx = 1
            if task_key:
                sql += f" AND task_key = ${idx}"
                params.append(str(task_key))
                idx += 1
            if event_id:
                sql += f" AND event_id = ${idx}"
                params.append(str(event_id))
                idx += 1
            sql += f" ORDER BY created_at DESC LIMIT ${idx}"
            params.append(max(1, min(int(limit or 200), 500)))
            rows = await conn.fetch(sql, *params)
        return [self._decode_factory_task_evidence(dict(row)) for row in rows]
