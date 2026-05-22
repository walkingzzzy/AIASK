
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
                    (run_id, status, started_at, completed_at, elapsed_seconds, execution_mode,
                     engine_version, parity_status, summary, stages, snapshot_summary, artifact_refs,
                     parity_result, error)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9,
                        $10, $11, $12, $13, $14)
                ON CONFLICT (run_id) DO UPDATE SET
                    status = EXCLUDED.status,
                    completed_at = EXCLUDED.completed_at,
                    elapsed_seconds = EXCLUDED.elapsed_seconds,
                    execution_mode = EXCLUDED.execution_mode,
                    engine_version = EXCLUDED.engine_version,
                    parity_status = EXCLUDED.parity_status,
                    summary = EXCLUDED.summary,
                    stages = EXCLUDED.stages,
                    snapshot_summary = EXCLUDED.snapshot_summary,
                    artifact_refs = EXCLUDED.artifact_refs,
                    parity_result = EXCLUDED.parity_result,
                    error = EXCLUDED.error
                """,
                run_id,
                str(run.get("status") or "unknown"),
                started_at,
                completed_at,
                float(run.get("elapsed_seconds") or 0),
                str(run.get("execution_mode") or "legacy_primary"),
                str(run.get("engine_version") or "strategy_factory.v2"),
                (
                    str((run.get("parity_result") or {}).get("status") or "").strip()
                    or None
                ),
                self._encode_factory_run_json("summary", run.get("summary") or {}),
                self._encode_factory_run_json("stages", run.get("stages") or {}),
                self._encode_factory_run_json("snapshot_summary", run.get("snapshot_summary") or {}),
                json.dumps(run.get("artifact_refs") or [], ensure_ascii=False, default=str),
                json.dumps(run.get("parity_result") or {}, ensure_ascii=False, default=str),
                run.get("error"),
            )

    def _decode_factory_run_artifact(self, row: dict) -> dict:
        result = dict(row)
        result["payload_json"] = self._decode_json_field(result.get("payload_json"), {})
        return result

    async def save_strategy_factory_run_artifact(self, payload: dict) -> dict:
        data = dict(payload or {})
        run_id = str(data.get("run_id") or "").strip()
        artifact_type = str(data.get("artifact_type") or "").strip()
        artifact_version = str(data.get("artifact_version") or "1").strip() or "1"
        if not run_id:
            raise ValueError("run_id is required")
        if not artifact_type:
            raise ValueError("artifact_type is required")
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO strategy_factory_run_artifacts
                    (run_id, artifact_type, artifact_version, payload_json, payload_hash, storage_mode)
                VALUES ($1, $2, $3, $4, $5, $6)
                RETURNING *
                """,
                run_id,
                artifact_type,
                artifact_version,
                json.dumps(data.get("payload_json") or {}, ensure_ascii=False, default=str),
                str(data.get("payload_hash") or "").strip() or None,
                str(data.get("storage_mode") or "inline_json").strip() or "inline_json",
            )
        return self._decode_factory_run_artifact(dict(row))

    async def list_strategy_factory_run_artifacts(self, run_id: str) -> List[dict]:
        async with self.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM strategy_factory_run_artifacts
                WHERE run_id = $1
                ORDER BY created_at ASC, id ASC
                """,
                run_id,
            )
        return [self._decode_factory_run_artifact(dict(row)) for row in rows]

    def _decode_factory_dispatch(self, row: dict) -> dict:
        result = dict(row)
        result["metadata"] = self._decode_json_field(result.get("metadata"), {})
        return result

    async def create_strategy_factory_dispatch(self, payload: dict) -> dict:
        data = dict(payload or {})
        dispatch_id = str(data.get("dispatch_id") or "").strip()
        if not dispatch_id:
            raise ValueError("dispatch_id is required")
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO strategy_factory_dispatches
                    (dispatch_id, status, execution_mode, requested_at, started_at, completed_at, run_id, message, error, metadata)
                VALUES ($1, $2, $3, COALESCE($4, CURRENT_TIMESTAMP), $5, $6, $7, $8, $9, $10)
                ON CONFLICT (dispatch_id) DO UPDATE SET
                    status = EXCLUDED.status,
                    execution_mode = EXCLUDED.execution_mode,
                    requested_at = EXCLUDED.requested_at,
                    started_at = EXCLUDED.started_at,
                    completed_at = EXCLUDED.completed_at,
                    run_id = EXCLUDED.run_id,
                    message = EXCLUDED.message,
                    error = EXCLUDED.error,
                    metadata = EXCLUDED.metadata,
                    updated_at = CURRENT_TIMESTAMP
                RETURNING *
                """,
                dispatch_id,
                str(data.get("status") or "queued"),
                str(data.get("execution_mode") or "legacy_primary"),
                self._coerce_timestamp(data.get("requested_at")),
                self._coerce_timestamp(data.get("started_at")),
                self._coerce_timestamp(data.get("completed_at")),
                str(data.get("run_id") or "").strip() or None,
                data.get("message"),
                data.get("error"),
                json.dumps(data.get("metadata") or {}, ensure_ascii=False, default=str),
            )
        return self._decode_factory_dispatch(dict(row))

    async def update_strategy_factory_dispatch(self, dispatch_id: str, **kwargs) -> Optional[dict]:
        existing = await self.get_strategy_factory_dispatch(dispatch_id)
        if not existing:
            return None
        merged = {**existing, **dict(kwargs or {}), "dispatch_id": dispatch_id}
        return await self.create_strategy_factory_dispatch(merged)

    async def get_strategy_factory_dispatch(self, dispatch_id: str) -> Optional[dict]:
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT * FROM strategy_factory_dispatches
                WHERE dispatch_id = $1
                LIMIT 1
                """,
                dispatch_id,
            )
        if not row:
            return None
        return self._decode_factory_dispatch(dict(row))

    async def list_strategy_factory_dispatches(self, status: str | None = None, limit: int = 20) -> List[dict]:
        resolved_status = str(status or "").strip()
        resolved_limit = max(1, min(int(limit or 20), 100))
        async with self.acquire() as conn:
            if resolved_status:
                rows = await conn.fetch(
                    """
                    SELECT * FROM strategy_factory_dispatches
                    WHERE status = $1
                    ORDER BY requested_at ASC, id ASC
                    LIMIT $2
                    """,
                    resolved_status,
                    resolved_limit,
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT * FROM strategy_factory_dispatches
                    ORDER BY requested_at DESC, id DESC
                    LIMIT $1
                    """,
                    resolved_limit,
                )
        return [self._decode_factory_dispatch(dict(row)) for row in rows]

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

    def _decode_strategy_factory_topn_snapshot(self, row: dict) -> dict:
        result = dict(row or {})
        for key in ("selection_rules", "constituents", "metadata"):
            default = [] if key == "constituents" else {}
            result[key] = self._decode_json_field(result.get(key), default)
        as_of_date = result.get("as_of_date")
        result["as_of_date"] = (
            as_of_date.isoformat()
            if hasattr(as_of_date, "isoformat")
            else str(as_of_date or "").strip() or None
        )
        return result

    def _decode_strategy_factory_full_market_score(self, row: dict) -> dict:
        result = dict(row or {})
        result["component_scores"] = self._decode_json_field(result.get("component_scores"), {})
        result["family_candidates"] = self._decode_json_field(result.get("family_candidates"), [])
        as_of_date = result.get("as_of_date")
        result["as_of_date"] = (
            as_of_date.isoformat()
            if hasattr(as_of_date, "isoformat")
            else str(as_of_date or "").strip() or None
        )
        return result

    async def save_strategy_factory_topn_snapshot(self, payload: dict) -> dict:
        data = dict(payload or {})
        snapshot_id = str(data.get("snapshot_id") or "").strip()
        run_id = str(data.get("run_id") or "").strip()
        if not snapshot_id:
            raise ValueError("snapshot_id is required")
        if not run_id:
            raise ValueError("run_id is required")
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO strategy_factory_topn_snapshots
                    (snapshot_id, run_id, as_of_date, trace_id, correlation_id, source_action,
                     universe_count, eligible_count, topn_n, selection_rules, constituents,
                     portfolio_candidate_id, metadata, created_at, updated_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                ON CONFLICT (snapshot_id) DO UPDATE SET
                    run_id = EXCLUDED.run_id,
                    as_of_date = EXCLUDED.as_of_date,
                    trace_id = EXCLUDED.trace_id,
                    correlation_id = EXCLUDED.correlation_id,
                    source_action = EXCLUDED.source_action,
                    universe_count = EXCLUDED.universe_count,
                    eligible_count = EXCLUDED.eligible_count,
                    topn_n = EXCLUDED.topn_n,
                    selection_rules = EXCLUDED.selection_rules,
                    constituents = EXCLUDED.constituents,
                    portfolio_candidate_id = EXCLUDED.portfolio_candidate_id,
                    metadata = EXCLUDED.metadata,
                    updated_at = CURRENT_TIMESTAMP
                RETURNING *
                """,
                snapshot_id,
                run_id,
                self._coerce_date(data.get("as_of_date")),
                str(data.get("trace_id") or "").strip() or None,
                str(data.get("correlation_id") or "").strip() or None,
                str(data.get("source_action") or "").strip() or None,
                int(data.get("universe_count") or 0),
                int(data.get("eligible_count") or 0),
                int(data.get("topn_n") or 20),
                json.dumps(data.get("selection_rules") or {}, ensure_ascii=False, default=str),
                json.dumps(data.get("constituents") or [], ensure_ascii=False, default=str),
                str(data.get("portfolio_candidate_id") or "").strip() or None,
                json.dumps(data.get("metadata") or {}, ensure_ascii=False, default=str),
            )
        return self._decode_strategy_factory_topn_snapshot(dict(row))

    async def get_strategy_factory_topn_snapshot(self, run_id: str) -> Optional[dict]:
        normalized_run_id = str(run_id or "").strip()
        if not normalized_run_id:
            return None
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT *
                FROM strategy_factory_topn_snapshots
                WHERE run_id = $1
                LIMIT 1
                """,
                normalized_run_id,
            )
        if not row:
            return None
        return self._decode_strategy_factory_topn_snapshot(dict(row))

    async def get_latest_strategy_factory_topn_snapshot(self) -> Optional[dict]:
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT *
                FROM strategy_factory_topn_snapshots
                ORDER BY as_of_date DESC NULLS LAST, updated_at DESC
                LIMIT 1
                """
            )
        if not row:
            return None
        return self._decode_strategy_factory_topn_snapshot(dict(row))

    async def replace_strategy_factory_full_market_scores(
        self,
        *,
        run_id: str,
        snapshot_id: str,
        as_of_date,
        trace_id: str | None,
        correlation_id: str | None,
        rows: list[dict],
    ) -> int:
        normalized_run_id = str(run_id or "").strip()
        normalized_snapshot_id = str(snapshot_id or "").strip()
        if not normalized_run_id:
            raise ValueError("run_id is required")
        if not normalized_snapshot_id:
            raise ValueError("snapshot_id is required")
        encoded_as_of = self._coerce_date(as_of_date)
        normalized_trace_id = str(trace_id or "").strip() or None
        normalized_correlation_id = str(correlation_id or "").strip() or None
        normalized_rows = [
            dict(item or {})
            for item in list(rows or [])
            if isinstance(item, dict) and str(dict(item or {}).get("code") or "").strip()
        ]
        async with self.acquire() as conn:
            await conn.execute(
                """
                DELETE FROM strategy_factory_full_market_scores
                WHERE run_id = $1
                """,
                normalized_run_id,
            )
            if not normalized_rows:
                return 0
            await conn.executemany(
                """
                INSERT INTO strategy_factory_full_market_scores
                    (run_id, snapshot_id, as_of_date, trace_id, correlation_id, code, rank,
                     composite_score, industry, market_cap, component_scores, family_candidates,
                     eligible, created_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, CURRENT_TIMESTAMP)
                """,
                [
                    (
                        normalized_run_id,
                        normalized_snapshot_id,
                        encoded_as_of,
                        normalized_trace_id,
                        normalized_correlation_id,
                        str(item.get("code") or "").strip(),
                        int(item.get("rank") or 0),
                        float(item.get("composite_score") or 0.0),
                        str(item.get("industry") or "").strip() or None,
                        float(item.get("market_cap") or 0.0),
                        json.dumps(item.get("component_scores") or {}, ensure_ascii=False, default=str),
                        json.dumps(item.get("family_candidates") or [], ensure_ascii=False, default=str),
                        bool(item.get("eligible", True)),
                    )
                    for item in normalized_rows
                ],
            )
        return len(normalized_rows)

    async def count_strategy_factory_full_market_scores(self, run_id: str) -> int:
        normalized_run_id = str(run_id or "").strip()
        if not normalized_run_id:
            return 0
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT COUNT(*) AS score_count
                FROM strategy_factory_full_market_scores
                WHERE run_id = $1
                """,
                normalized_run_id,
            )
        return int((dict(row or {})).get("score_count") or 0)

    async def list_strategy_factory_full_market_scores(self, run_id: str, limit: int = 20) -> List[dict]:
        normalized_run_id = str(run_id or "").strip()
        if not normalized_run_id:
            return []
        async with self.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT *
                FROM strategy_factory_full_market_scores
                WHERE run_id = $1
                ORDER BY rank ASC, code ASC
                LIMIT $2
                """,
                normalized_run_id,
                max(1, min(int(limit or 20), 500)),
            )
        return [self._decode_strategy_factory_full_market_score(dict(row)) for row in rows]

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
                        $11, $12, $13, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
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
                    updated_at = CURRENT_TIMESTAMP
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
                        $9, $10, $11, $12, $13, $14, $15, $16,
                        $17, $18, $19, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
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
                    updated_at = CURRENT_TIMESTAMP
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
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                ON CONFLICT (theme_code) DO UPDATE SET
                    theme_name = EXCLUDED.theme_name,
                    parent_theme_code = EXCLUDED.parent_theme_code,
                    description = EXCLUDED.description,
                    direction_rule = EXCLUDED.direction_rule,
                    aliases = EXCLUDED.aliases,
                    metadata = EXCLUDED.metadata,
                    active = EXCLUDED.active,
                    updated_at = CURRENT_TIMESTAMP
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
                VALUES ($1, $2, $3, $4, $5, $6, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                ON CONFLICT (symbol, theme_code, exposure_type) DO UPDATE SET
                    direction = EXCLUDED.direction,
                    exposure_score = EXCLUDED.exposure_score,
                    evidence = EXCLUDED.evidence,
                    updated_at = CURRENT_TIMESTAMP
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
                sql += f" AND theme_code IN (${idx})"
                params.append(normalized_theme_codes)
                idx += 1
            if normalized_symbols:
                sql += f" AND symbol IN (${idx})"
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
                        $8, $9, $10, $11, $12,
                        $13, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
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
                    updated_at = CURRENT_TIMESTAMP
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
                sql += f" AND symbol IN (${idx})"
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

    # =========================================================================
    # PR-1: Theme Graph DAO methods (2026-05-14)
    # =========================================================================

    async def list_theme_nodes(self, *, is_active: bool = True, limit: int = 200) -> list:
        async with self.acquire() as conn:
            sql = "SELECT * FROM strategy_factory_theme_nodes WHERE is_active = $1 ORDER BY theme_code LIMIT $2"
            rows = await conn.fetch(sql, 1 if is_active else 0, max(1, min(int(limit), 500)))
        result = []
        for row in rows:
            item = dict(row)
            for json_field in ("aliases", "industry_tags"):
                raw = item.get(json_field)
                if isinstance(raw, str):
                    try:
                        item[json_field] = __import__("json").loads(raw)
                    except Exception:
                        item[json_field] = []
            result.append(item)
        return result

    async def get_theme_node(self, theme_code: str):
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM strategy_factory_theme_nodes WHERE theme_code = $1",
                str(theme_code).strip(),
            )
        if row is None:
            return None
        item = dict(row)
        for json_field in ("aliases", "industry_tags"):
            raw = item.get(json_field)
            if isinstance(raw, str):
                try:
                    item[json_field] = __import__("json").loads(raw)
                except Exception:
                    item[json_field] = []
        return item

    async def upsert_theme_node(self, payload: dict) -> dict:
        import json as _json
        theme_code = str(payload.get("theme_code") or "").strip()
        if not theme_code:
            raise ValueError("theme_code is required")
        async with self.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO strategy_factory_theme_nodes
                    (theme_code, theme_name, parent_theme_code, breadth, default_horizon,
                     aliases, industry_tags, description, shock_detection_profile,
                     benchmark_index_code, manual_locked, is_active, updated_by)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
                ON CONFLICT(theme_code) DO UPDATE SET
                    theme_name = EXCLUDED.theme_name,
                    parent_theme_code = EXCLUDED.parent_theme_code,
                    breadth = EXCLUDED.breadth,
                    default_horizon = EXCLUDED.default_horizon,
                    aliases = EXCLUDED.aliases,
                    industry_tags = EXCLUDED.industry_tags,
                    description = EXCLUDED.description,
                    shock_detection_profile = EXCLUDED.shock_detection_profile,
                    benchmark_index_code = EXCLUDED.benchmark_index_code,
                    manual_locked = EXCLUDED.manual_locked,
                    is_active = EXCLUDED.is_active,
                    updated_by = EXCLUDED.updated_by,
                    updated_at = CURRENT_TIMESTAMP
                """,
                theme_code,
                str(payload.get("theme_name") or theme_code),
                payload.get("parent_theme_code"),
                str(payload.get("breadth") or "medium"),
                str(payload.get("default_horizon") or "swing_5_20d"),
                _json.dumps(payload.get("aliases") or [], ensure_ascii=False),
                _json.dumps(payload.get("industry_tags") or [], ensure_ascii=False),
                payload.get("description"),
                str(payload.get("shock_detection_profile") or "fast"),
                str(payload.get("benchmark_index_code") or "000300"),
                int(payload.get("manual_locked") or 0),
                int(payload.get("is_active", 1)),
                payload.get("updated_by"),
            )
        return await self.get_theme_node(theme_code) or {"theme_code": theme_code}

    async def list_theme_edges(self, *, source: str = None, target: str = None, is_active: bool = True, limit: int = 200) -> list:
        async with self.acquire() as conn:
            conditions = ["is_active = $1"]
            params = [1 if is_active else 0]
            idx = 2
            if source:
                conditions.append(f"source_theme_code = ${idx}")
                params.append(str(source).strip())
                idx += 1
            if target:
                conditions.append(f"target_theme_code = ${idx}")
                params.append(str(target).strip())
                idx += 1
            where = " AND ".join(conditions)
            params.append(max(1, min(int(limit), 500)))
            sql = f"SELECT * FROM strategy_factory_theme_edges WHERE {where} ORDER BY source_theme_code, target_theme_code LIMIT ${idx}"
            rows = await conn.fetch(sql, *params)
        result = []
        for row in rows:
            item = dict(row)
            raw_evidence = item.get("evidence")
            if isinstance(raw_evidence, str):
                try:
                    item["evidence"] = __import__("json").loads(raw_evidence)
                except Exception:
                    item["evidence"] = {}
            result.append(item)
        return result

    async def upsert_theme_edge(self, payload: dict) -> dict:
        import json as _json
        source = str(payload.get("source_theme_code") or "").strip()
        target = str(payload.get("target_theme_code") or "").strip()
        relation = str(payload.get("relation_type") or "").strip()
        if not source or not target or not relation:
            raise ValueError("source_theme_code, target_theme_code, relation_type are required")
        async with self.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO strategy_factory_theme_edges
                    (source_theme_code, target_theme_code, relation_type,
                     direction_sign, magnitude_factor, lag_days, confidence,
                     confidence_source, manual_locked, evidence, is_active, updated_by)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                ON CONFLICT(source_theme_code, target_theme_code, relation_type) DO UPDATE SET
                    direction_sign = EXCLUDED.direction_sign,
                    magnitude_factor = EXCLUDED.magnitude_factor,
                    lag_days = EXCLUDED.lag_days,
                    confidence = EXCLUDED.confidence,
                    confidence_source = EXCLUDED.confidence_source,
                    manual_locked = EXCLUDED.manual_locked,
                    evidence = EXCLUDED.evidence,
                    is_active = EXCLUDED.is_active,
                    updated_by = EXCLUDED.updated_by,
                    updated_at = CURRENT_TIMESTAMP
                """,
                source, target, relation,
                int(payload.get("direction_sign") or 1),
                float(payload.get("magnitude_factor") or 0.5),
                int(payload.get("lag_days") or 0),
                float(payload.get("confidence") or 0.5),
                str(payload.get("confidence_source") or "manual"),
                int(payload.get("manual_locked") or 0),
                _json.dumps(payload.get("evidence") or {}, ensure_ascii=False, default=str),
                int(payload.get("is_active", 1)),
                payload.get("updated_by"),
            )
            row = await conn.fetchrow(
                "SELECT * FROM strategy_factory_theme_edges WHERE source_theme_code = $1 AND target_theme_code = $2 AND relation_type = $3",
                source, target, relation,
            )
        return dict(row) if row else {"source_theme_code": source, "target_theme_code": target}

    async def list_event_injections(self, *, status: str = None, source: str = None, limit: int = 50) -> list:
        async with self.acquire() as conn:
            conditions = []
            params = []
            idx = 1
            if status:
                conditions.append(f"status = ${idx}")
                params.append(str(status).strip())
                idx += 1
            if source:
                conditions.append(f"source = ${idx}")
                params.append(str(source).strip())
                idx += 1
            where = (" WHERE " + " AND ".join(conditions)) if conditions else ""
            params.append(max(1, min(int(limit), 200)))
            sql = f"SELECT * FROM strategy_factory_event_injections{where} ORDER BY created_at DESC LIMIT ${idx}"
            rows = await conn.fetch(sql, *params)
        result = []
        for row in rows:
            item = dict(row)
            for json_field in ("primary_themes", "evidence"):
                raw = item.get(json_field)
                if isinstance(raw, str):
                    try:
                        item[json_field] = __import__("json").loads(raw)
                    except Exception:
                        pass
            result.append(item)
        return result

    async def upsert_event_injection(self, payload: dict) -> dict:
        import json as _json
        from uuid import uuid4
        event_id = str(payload.get("event_id") or f"manual_{uuid4().hex[:12]}").strip()
        async with self.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO strategy_factory_event_injections
                    (event_id, source, event_name, event_type, direction,
                     confidence, intensity, horizon, scope, primary_themes,
                     rationale, evidence, valid_from, valid_until, status,
                     operator_id)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16)
                ON CONFLICT(event_id) DO UPDATE SET
                    event_name = EXCLUDED.event_name,
                    event_type = EXCLUDED.event_type,
                    direction = EXCLUDED.direction,
                    confidence = EXCLUDED.confidence,
                    intensity = EXCLUDED.intensity,
                    horizon = EXCLUDED.horizon,
                    scope = EXCLUDED.scope,
                    primary_themes = EXCLUDED.primary_themes,
                    rationale = EXCLUDED.rationale,
                    evidence = EXCLUDED.evidence,
                    valid_from = EXCLUDED.valid_from,
                    valid_until = EXCLUDED.valid_until,
                    status = EXCLUDED.status,
                    updated_at = CURRENT_TIMESTAMP
                """,
                event_id,
                str(payload.get("source") or "manual"),
                str(payload.get("event_name") or ""),
                str(payload.get("event_type") or ""),
                payload.get("direction"),
                float(payload.get("confidence") or 0.7),
                float(payload.get("intensity") or 0.5),
                str(payload.get("horizon") or "swing_5_20d"),
                str(payload.get("scope") or "theme"),
                _json.dumps(payload.get("primary_themes") or [], ensure_ascii=False),
                payload.get("rationale"),
                _json.dumps(payload.get("evidence") or {}, ensure_ascii=False, default=str),
                str(payload.get("valid_from") or ""),
                str(payload.get("valid_until") or ""),
                str(payload.get("status") or "pending_review"),
                payload.get("operator_id"),
            )
        return {"event_id": event_id, "status": payload.get("status") or "pending_review"}

    async def update_event_outcome(self, event_id: str, *, actual_outcome: str, outcome_notes: str = None) -> dict:
        async with self.acquire() as conn:
            await conn.execute(
                """
                UPDATE strategy_factory_event_injections
                SET actual_outcome = $1, outcome_notes = $2,
                    outcome_recorded_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                WHERE event_id = $3
                """,
                str(actual_outcome).strip(),
                outcome_notes,
                str(event_id).strip(),
            )
        return {"event_id": event_id, "actual_outcome": actual_outcome}

    async def upsert_event_task_lineage(self, payload: dict) -> dict:
        import json as _json
        async with self.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO strategy_factory_event_task_lineage
                    (event_id, task_id, theme_code, impact_direction,
                     impact_magnitude, target_symbols, target_count, breadth_resolved)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                """,
                str(payload.get("event_id") or ""),
                str(payload.get("task_id") or ""),
                str(payload.get("theme_code") or ""),
                str(payload.get("impact_direction") or "positive"),
                float(payload.get("impact_magnitude") or 0),
                _json.dumps(payload.get("target_symbols") or [], ensure_ascii=False),
                int(payload.get("target_count") or 0),
                str(payload.get("breadth_resolved") or "medium"),
            )
        return {"event_id": payload.get("event_id"), "task_id": payload.get("task_id")}

    async def list_theme_exposure(self, theme_code: str = None, min_exposure: float = 0.3, limit: int = 30) -> list:
        """Query theme exposure matrix for a specific theme."""
        async with self.acquire() as conn:
            if theme_code:
                rows = await conn.fetch(
                    "SELECT * FROM strategy_factory_theme_exposure WHERE theme_code = $1 AND exposure_score >= $2 ORDER BY exposure_score DESC LIMIT $3",
                    theme_code, min_exposure, limit,
                )
            else:
                rows = await conn.fetch(
                    "SELECT * FROM strategy_factory_theme_exposure WHERE exposure_score >= $1 ORDER BY exposure_score DESC LIMIT $2",
                    min_exposure, limit,
                )
        return [dict(r) for r in rows]
