
    @classmethod
    def _summarize_large_factory_run_field(
        cls,
        field_name: str,
        value: Any,
        *,
        size_bytes: int,
    ) -> dict[str, Any]:
        payload = dict(value) if isinstance(value, dict) else {}
        summary: dict[str, Any] = {
            "storage_mode": "inline_fallback_summary",
            "field_name": str(field_name or "unknown"),
            "truncated": True,
            "original_size_bytes": int(size_bytes),
        }
        if not payload:
            return summary
        summary["top_level_keys"] = sorted(str(key) for key in payload.keys())[:80]

        if field_name == "stages":
            summary["stage_count"] = len(payload)
            summary["stage_names"] = [str(key) for key in list(payload.keys())[:20]]
            for stage_name, stage_payload in payload.items():
                summary[str(stage_name)] = cls._summarize_factory_stage_payload(
                    str(stage_name),
                    stage_payload,
                )
            return summary

        if field_name == "snapshot_summary":
            summary.update(
                cls._compact_mapping(
                    payload,
                    keys=(
                        "date",
                        "fear_greed",
                        "fear_greed_index",
                        "fg_level",
                        "listed_count",
                        "incubating_count",
                        "degraded",
                        "completion_ratio",
                        "failure_reason_count",
                    ),
                )
            )
            missing_sources = cls._preview_plain_list(payload.get("missing_sources"), limit=12)
            if missing_sources:
                summary["missing_sources"] = missing_sources
            factor_research = dict(payload.get("factor_research") or {})
            if factor_research:
                factor_summary = dict(factor_research.get("summary") or {})
                active_candidate_pool = dict(factor_research.get("active_candidate_pool") or {})
                factor_research_summary: dict[str, Any] = {}
                if factor_summary:
                    factor_research_summary["summary"] = cls._summarize_scalar_mapping(
                        factor_summary,
                        limit=40,
                    )
                if active_candidate_pool:
                    compact_pool = cls._compact_mapping(
                        active_candidate_pool,
                        keys=("count", "family_count"),
                    )
                    top_candidates = list(active_candidate_pool.get("top_candidates") or [])
                    if top_candidates:
                        compact_pool["top_candidates"] = [
                            cls._compact_mapping(
                                dict(item or {}),
                                keys=("name", "family", "priority", "score", "source"),
                            )
                            for item in top_candidates[:10]
                        ]
                        compact_pool["top_candidate_count"] = len(top_candidates)
                    if compact_pool:
                        factor_research_summary["active_candidate_pool"] = compact_pool
                source_chain = cls._preview_plain_list(factor_research.get("source_chain"), limit=10)
                if source_chain:
                    factor_research_summary["source_chain"] = source_chain
                if factor_research.get("degraded") not in (None, "", [], {}):
                    factor_research_summary["degraded"] = bool(factor_research.get("degraded"))
                if factor_research_summary:
                    summary["factor_research"] = factor_research_summary
            return summary

        if field_name == "summary":
            for key, item in payload.items():
                if isinstance(item, (str, int, float, bool)) or item is None:
                    summary[key] = item
                    continue
                if key == "autonomy_task_briefs":
                    values = list(item or [])
                    summary["autonomy_task_briefs"] = [
                        cls._compact_mapping(
                            dict(entry or {}),
                            keys=(
                                "task_id",
                                "task_source",
                                "opportunity_type",
                                "candidate_family",
                                "factor_name",
                                "generation_limit",
                                "generated_count",
                            ),
                        )
                        for entry in values[:20]
                    ]
                    summary["autonomy_task_brief_count"] = len(values)
                    continue
                if isinstance(item, dict):
                    nested = cls._summarize_scalar_mapping(item, limit=40)
                    if nested:
                        summary[key] = nested
                    continue
                if isinstance(item, list):
                    preview = cls._preview_plain_list(item, limit=20)
                    if preview:
                        summary[key] = preview
                    summary[f"{key}_count"] = len(item)
            return summary

        return summary

    @classmethod
    def _encode_factory_run_json(cls, field_name: str, value: Any) -> str:
        encoded = json.dumps(value or {}, ensure_ascii=False, default=str)
        size_bytes = len(encoded.encode("utf-8"))
        limit = cls._factory_run_field_max_bytes(field_name)
        if size_bytes <= limit:
            return encoded
        if str(field_name or "").strip().lower() == "stages":
            compacted, changed = cls._compact_factory_run_stages_to_fit(
                value,
                max_bytes=limit,
            )
            if changed:
                compacted_json = json.dumps(compacted, ensure_ascii=False, default=str)
                compacted_size = len(compacted_json.encode("utf-8"))
                if compacted_size <= limit:
                    logger.info(
                        "strategy_factory_runs.%s compacted inline (%s bytes -> %s bytes, limit=%s)",
                        field_name,
                        size_bytes,
                        compacted_size,
                        limit,
                    )
                    return compacted_json
        logger.warning(
            "strategy_factory_runs.%s exceeds soft limit (%s bytes > %s bytes); storing fallback summary instead",
            field_name,
            size_bytes,
            limit,
        )
        fallback = cls._summarize_large_factory_run_field(
            field_name,
            value,
            size_bytes=size_bytes,
        )
        fallback_json = json.dumps(fallback, ensure_ascii=False, default=str)
        if len(fallback_json.encode("utf-8")) <= limit:
            return fallback_json
        minimal = {
            "storage_mode": "inline_fallback_summary",
            "field_name": str(field_name or "unknown"),
            "truncated": True,
            "original_size_bytes": int(size_bytes),
            "fallback_truncated": True,
            "top_level_keys": sorted(str(key) for key in list((value or {}).keys())[:80]),
        }
        return json.dumps(minimal, ensure_ascii=False, default=str)

    @classmethod
    def _summarize_large_generation_experiment_field(
        cls,
        field_name: str,
        value: Any,
        *,
        size_bytes: int,
    ) -> dict[str, Any]:
        payload = dict(value) if isinstance(value, dict) else {}
        summary: dict[str, Any] = {
            "storage_mode": "inline_fallback_summary",
            "field_name": str(field_name or "unknown"),
            "truncated": True,
            "original_size_bytes": int(size_bytes),
        }
        if not payload:
            return summary
        summary["top_level_keys"] = sorted(str(key) for key in payload.keys())[:50]

        scalar_preview = {
            key: payload.get(key)
            for key in list(payload.keys())[:20]
            if isinstance(payload.get(key), (str, int, float, bool)) or payload.get(key) is None
        }
        if scalar_preview:
            summary["scalar_preview"] = scalar_preview

        if field_name == "parameters":
            summary["parameter_keys"] = sorted(str(key) for key in payload.keys())[:50]
            target_symbols = cls._preview_plain_list(payload.get("target_symbols"), limit=12)
            if target_symbols:
                summary["target_symbols"] = target_symbols
            return summary

        if field_name == "strategy_spec":
            for key in ("strategy_type", "name", "description"):
                if payload.get(key) not in (None, "", [], {}):
                    summary[key] = payload.get(key)
            tags = cls._preview_plain_list(payload.get("tags"), limit=12)
            if tags:
                summary["tags"] = tags
            target_symbols = cls._preview_plain_list(payload.get("target_symbols"), limit=12)
            if target_symbols:
                summary["target_symbols"] = target_symbols
            research_task = dict(payload.get("research_task") or {})
            if research_task:
                summary["research_task"] = {
                    key: research_task.get(key)
                    for key in (
                        "task_id",
                        "task_key",
                        "task_source",
                        "theme_code",
                        "event_id",
                        "candidate_family",
                        "factor_name",
                    )
                    if research_task.get(key) not in (None, "", [], {})
                }
            event_context = dict(payload.get("event_context") or {})
            if event_context:
                summary["event_context"] = {
                    key: event_context.get(key)
                    for key in (
                        "task_source",
                        "event_id",
                        "theme_code",
                        "event_type",
                        "candidate_family",
                        "factor_name",
                    )
                    if event_context.get(key) not in (None, "", [], {})
                }
            return summary

        if field_name == "evaluation":
            for key in ("source", "task_run_id"):
                if payload.get(key) not in (None, "", [], {}):
                    summary[key] = payload.get(key)
            committee_review = dict(payload.get("committee_review") or {})
            if committee_review:
                summary["committee_review"] = {
                    key: committee_review.get(key)
                    for key in ("decision", "final_score", "rank", "review_rank", "is_champion")
                    if committee_review.get(key) not in (None, "", [], {})
                }
            submission_result = dict(payload.get("submission_result") or {})
            if submission_result:
                summary["submission_result"] = {
                    key: submission_result.get(key)
                    for key in ("passed", "duplicate", "reason_code", "strategy_id")
                    if submission_result.get(key) not in (None, "", [], {})
                }
            return summary

        if field_name == "result":
            for key in (
                "status",
                "strategy_id",
                "passed",
                "duplicate",
                "reason_code",
                "admission_stage",
                "submission_lane",
                "research_candidate_ready",
                "incubation_candidate_ready",
                "live_candidate_ready",
            ):
                if payload.get(key) not in (None, "", [], {}):
                    summary[key] = payload.get(key)
            return summary

        return summary

    @classmethod
    def _encode_generation_experiment_json(cls, field_name: str, value: Any) -> str:
        encoded = json.dumps(value or {}, ensure_ascii=False, default=str)
        size_bytes = len(encoded.encode("utf-8"))
        if size_bytes <= cls._generation_experiment_field_max_bytes():
            return encoded
        logger.warning(
            "strategy_generation_experiments.%s exceeds soft limit (%s bytes > %s bytes); storing fallback summary instead",
            field_name,
            size_bytes,
            cls._generation_experiment_field_max_bytes(),
        )
        fallback = cls._summarize_large_generation_experiment_field(
            field_name,
            value,
            size_bytes=size_bytes,
        )
        return json.dumps(fallback, ensure_ascii=False, default=str)

    @classmethod
    def _summarize_large_task_run_result(cls, result: Any, *, size_bytes: int) -> dict:
        payload = dict(result) if isinstance(result, dict) else {}
        summary = {
            "storage_mode": "inline_fallback_summary",
            "truncated": True,
            "original_size_bytes": int(size_bytes),
        }
        if payload:
            summary["top_level_keys"] = sorted(str(key) for key in payload.keys())[:50]
            for key in (
                "task_run_id",
                "status",
                "source",
                "snapshot_date",
                "generated_count",
                "reviewed_count",
                "rejected_count",
            ):
                value = payload.get(key)
                if value not in (None, "", [], {}):
                    summary[key] = value
            artifact = payload.get("full_result_artifact")
            if isinstance(artifact, dict) and artifact:
                summary["full_result_artifact"] = {
                    key: artifact.get(key)
                    for key in ("artifact_id", "path", "format", "size_bytes")
                    if artifact.get(key) not in (None, "", [], {})
                }
            lifecycle = payload.get("lifecycle")
            if isinstance(lifecycle, dict) and lifecycle:
                summary["lifecycle"] = {
                    key: lifecycle.get(key)
                    for key in (
                        "state",
                        "current_phase",
                        "failed_phase",
                        "terminal_phase",
                        "phase_status_counts",
                    )
                    if lifecycle.get(key) not in (None, "", [], {})
                }
        return summary

    @classmethod
    def _encode_task_run_result_json(cls, result: Optional[dict]) -> Optional[str]:
        if result is None:
            return None
        result_json = json.dumps(result, ensure_ascii=False, default=str)
        size_bytes = len(result_json.encode("utf-8"))
        if size_bytes <= cls._task_run_result_max_bytes():
            return result_json
        logger.warning(
            "strategy_task_runs.result exceeds soft limit (%s bytes > %s bytes); storing fallback summary instead",
            size_bytes,
            cls._task_run_result_max_bytes(),
        )
        fallback = cls._summarize_large_task_run_result(result, size_bytes=size_bytes)
        return json.dumps(fallback, ensure_ascii=False, default=str)

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
                self._encode_generation_experiment_json("parameters", payload.get("parameters") or {}),
                self._encode_generation_experiment_json("strategy_spec", payload.get("strategy_spec") or {}),
                self._encode_generation_experiment_json("evaluation", payload.get("evaluation") or {}),
                self._encode_generation_experiment_json("result", payload.get("result") or {}),
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

    async def get_strategy_task_run(self, run_id: int) -> Optional[dict]:
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM strategy_task_runs WHERE id = $1",
                int(run_id),
            )
        return self._decode_task_run(dict(row)) if row else None

    async def save_strategy_task_run(self, run: dict) -> dict:
        payload = dict(run or {})
        started_at = self._coerce_timestamp(payload.get("started_at"))
        completed_at = self._coerce_timestamp(payload.get("completed_at"))
        lease_until = self._coerce_timestamp(payload.get("lease_until"))
        heartbeat_at = self._coerce_timestamp(payload.get("heartbeat_at"))
        last_claimed_at = self._coerce_timestamp(payload.get("last_claimed_at"))
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO strategy_task_runs
                    (strategy_id, task_name, task_scope, task_key, status, trace_id,
                     payload, result, error, lease_owner, lease_until, heartbeat_at,
                     attempt_count, max_attempts, last_claimed_at, started_at, completed_at)
                VALUES ($1, $2, $3, $4, $5, $6,
                        $7::jsonb, $8::jsonb, $9, $10, $11::timestamptz, $12::timestamptz,
                        $13, $14, $15::timestamptz, COALESCE($16::timestamptz, NOW()), $17::timestamptz)
                RETURNING *
                """,
                payload.get("strategy_id"),
                str(payload.get("task_name") or "unknown"),
                payload.get("task_scope"),
                payload.get("task_key"),
                str(payload.get("status") or "running"),
                payload.get("trace_id"),
                json.dumps(payload.get("payload") or {}, ensure_ascii=False, default=str),
                self._encode_task_run_result_json(payload.get("result") or {}),
                payload.get("error"),
                payload.get("lease_owner"),
                lease_until,
                heartbeat_at,
                int(payload.get("attempt_count") or 0),
                int(payload.get("max_attempts") or 3),
                last_claimed_at,
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
        lease_owner: Any = None,
        lease_until: Any = None,
        heartbeat_at: Any = None,
        attempt_count: Any = None,
        max_attempts: Any = None,
        last_claimed_at: Any = None,
        clear_lease: bool = False,
    ) -> Optional[dict]:
        completed_at_value = self._coerce_timestamp(completed_at)
        lease_until_value = self._coerce_timestamp(lease_until)
        heartbeat_at_value = self._coerce_timestamp(heartbeat_at)
        last_claimed_at_value = self._coerce_timestamp(last_claimed_at)
        attempt_count_value = int(attempt_count) if attempt_count is not None else None
        max_attempts_value = int(max_attempts) if max_attempts is not None else None
        result_json = self._encode_task_run_result_json(result)
        sql = """
            UPDATE strategy_task_runs
            SET status = COALESCE($2, status),
                result = CASE WHEN $3::jsonb IS NULL THEN result ELSE $3::jsonb END,
                error = COALESCE($4, error),
                completed_at = CASE
                    WHEN $5::timestamptz IS NOT NULL THEN $5::timestamptz
                    WHEN $2 = ANY($13::text[]) THEN COALESCE(completed_at, NOW())
                    ELSE completed_at
                END,
                lease_owner = CASE WHEN $12 THEN NULL ELSE COALESCE($6, lease_owner) END,
                lease_until = CASE WHEN $12 THEN NULL ELSE COALESCE($7::timestamptz, lease_until) END,
                heartbeat_at = COALESCE($8::timestamptz, heartbeat_at),
                attempt_count = COALESCE($9, attempt_count),
                max_attempts = COALESCE($10, max_attempts),
                last_claimed_at = COALESCE($11::timestamptz, last_claimed_at)
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
                        lease_owner,
                        lease_until_value,
                        heartbeat_at_value,
                        attempt_count_value,
                        max_attempts_value,
                        last_claimed_at_value,
                        bool(clear_lease),
                        [
                            "completed",
                            "failed",
                            "failed_timeout",
                            "retryable_timeout",
                            "retryable_failure",
                            "cancelled",
                        ],
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
        task_key: Optional[str] = None,
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
            if task_key:
                sql += f" AND task_key = ${idx}"
                params.append(task_key)
                idx += 1
            sql += f" ORDER BY started_at DESC LIMIT ${idx}"
            params.append(max(1, min(int(limit or 20), 500)))
            rows = await conn.fetch(sql, *params)
        return [self._decode_task_run(dict(row)) for row in rows]

    async def claim_strategy_task_run(
        self,
        *,
        task_scope: str,
        task_names: Optional[List[str]] = None,
        lease_owner: Optional[str] = None,
        lease_seconds: int = 300,
    ) -> Optional[dict]:
        names = [str(item).strip() for item in list(task_names or []) if str(item).strip()]
        owner = str(lease_owner or "").strip() or None
        lease_seconds = max(30, min(int(lease_seconds or 300), 24 * 3600))
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """
                WITH next_run AS (
                    SELECT id
                    FROM strategy_task_runs
                    WHERE task_scope = $1
                      AND (COALESCE(array_length($2::text[], 1), 0) = 0 OR task_name = ANY($2::text[]))
                      AND (
                        status = 'queued'
                        OR status IN ('retryable_timeout', 'retryable_failure')
                        OR (
                            status = 'running'
                            AND COALESCE(lease_until, started_at + INTERVAL '30 minutes') < NOW()
                            AND COALESCE(attempt_count, 0) < COALESCE(max_attempts, 3)
                        )
                      )
                      AND COALESCE(attempt_count, 0) < COALESCE(max_attempts, 3)
                    ORDER BY started_at ASC, id ASC
                    FOR UPDATE SKIP LOCKED
                    LIMIT 1
                )
                UPDATE strategy_task_runs target
                SET status = 'running',
                    started_at = NOW(),
                    completed_at = NULL,
                    error = NULL,
                    lease_owner = $3,
                    lease_until = NOW() + ($4::int * INTERVAL '1 second'),
                    heartbeat_at = NOW(),
                    last_claimed_at = NOW(),
                    attempt_count = COALESCE(target.attempt_count, 0) + 1
                FROM next_run
                WHERE target.id = next_run.id
                RETURNING target.*
                """,
                task_scope,
                names,
                owner,
                lease_seconds,
            )
        return self._decode_task_run(dict(row)) if row else None

    async def heartbeat_strategy_task_run(
        self,
        run_id: int,
        *,
        lease_owner: Optional[str] = None,
        lease_seconds: int = 300,
    ) -> Optional[dict]:
        owner = str(lease_owner or "").strip() or None
        lease_seconds = max(30, min(int(lease_seconds or 300), 24 * 3600))
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE strategy_task_runs
                SET heartbeat_at = NOW(),
                    lease_owner = COALESCE($2, lease_owner),
                    lease_until = NOW() + ($3::int * INTERVAL '1 second')
                WHERE id = $1
                  AND status = 'running'
                  AND ($2::text IS NULL OR lease_owner IS NULL OR lease_owner = $2)
                RETURNING *
                """,
                int(run_id),
                owner,
                lease_seconds,
            )
        return self._decode_task_run(dict(row)) if row else None

    async def get_strategy_task_queue_stats(
        self,
        *,
        task_scope: Optional[str] = None,
        task_names: Optional[List[str]] = None,
    ) -> dict:
        names = [str(item).strip() for item in list(task_names or []) if str(item).strip()]
        async with self.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT task_name,
                       status,
                       COUNT(*)::int AS count,
                       EXTRACT(EPOCH FROM MAX(NOW() - started_at))::double precision AS max_age_seconds,
                       EXTRACT(EPOCH FROM MIN(started_at))::double precision AS oldest_started_epoch
                FROM strategy_task_runs
                WHERE ($1::text IS NULL OR task_scope = $1)
                  AND (COALESCE(array_length($2::text[], 1), 0) = 0 OR task_name = ANY($2::text[]))
                  AND status IN ('queued', 'running', 'retryable_timeout', 'retryable_failure')
                GROUP BY task_name, status
                ORDER BY task_name ASC, status ASC
                """,
                task_scope,
                names,
            )
            stale_rows = await conn.fetch(
                """
                SELECT task_name, COUNT(*)::int AS count
                FROM strategy_task_runs
                WHERE ($1::text IS NULL OR task_scope = $1)
                  AND (COALESCE(array_length($2::text[], 1), 0) = 0 OR task_name = ANY($2::text[]))
                  AND status = 'running'
                  AND COALESCE(lease_until, started_at + INTERVAL '30 minutes') < NOW()
                GROUP BY task_name
                """,
                task_scope,
                names,
            )
        by_task: dict[str, dict[str, int]] = {}
        max_age_by_task: dict[str, float] = {}
        for row in rows:
            task_name = str(row.get("task_name") or "unknown")
            status = str(row.get("status") or "unknown")
            count = int(row.get("count") or 0)
            by_task.setdefault(task_name, {})[status] = count
            max_age_by_task[task_name] = max(max_age_by_task.get(task_name, 0.0), float(row.get("max_age_seconds") or 0.0))
        stale_running_by_task = {
            str(row.get("task_name") or "unknown"): int(row.get("count") or 0)
            for row in stale_rows
        }
        return {
            "task_scope": task_scope,
            "task_names": names,
            "queue_depth_by_task": by_task,
            "max_age_seconds_by_task": max_age_by_task,
            "stale_running_by_task": stale_running_by_task,
            "queued_total": sum(int(statuses.get("queued") or 0) for statuses in by_task.values()),
            "running_total": sum(int(statuses.get("running") or 0) for statuses in by_task.values()),
            "stale_running_total": sum(stale_running_by_task.values()),
        }

    # ------------------------------------------------------------------
    # factory runs
    # ------------------------------------------------------------------

    def _decode_factory_run(self, row: dict) -> dict:
        result = dict(row)
        for key in ("summary", "stages", "snapshot_summary", "artifact_refs", "parity_result"):
            result[key] = self._decode_json_field(result.get(key), {})
        if not isinstance(result.get("artifact_refs"), list):
            result["artifact_refs"] = []
        return result
