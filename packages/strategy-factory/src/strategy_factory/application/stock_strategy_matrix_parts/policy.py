
    @classmethod
    async def _fetch_history_bar_counts(
        cls,
        db,
        codes: Sequence[str],
        *,
        min_history_bars: int,
    ) -> tuple[dict[str, int], bool]:
        normalized_codes = [
            str(code or "").strip()
            for code in list(codes or [])
            if str(code or "").strip()
        ]
        if not normalized_codes:
            return {}, False

        deduped_codes = list(dict.fromkeys(normalized_codes))
        acquire = getattr(db, "acquire", None)
        if callable(acquire):
            history_counts: dict[str, int] = {}
            try:
                async with db.acquire() as conn:
                    for start in range(0, len(deduped_codes), cls._HISTORY_COUNT_CHUNK_SIZE):
                        chunk = deduped_codes[start : start + cls._HISTORY_COUNT_CHUNK_SIZE]
                        rows = await conn.fetch(
                            """
                            SELECT code, COUNT(*) AS bar_count
                            FROM kline_1d
                            WHERE code = ANY($1::text[])
                            GROUP BY code
                            """,
                            chunk,
                        )
                        for row in rows or []:
                            payload = dict(row or {})
                            code = str(payload.get("code") or "").strip()
                            if not code:
                                continue
                            history_counts[code] = max(0, int(payload.get("bar_count") or 0))
                return history_counts, True
            except Exception:
                pass

        get_klines = getattr(db, "get_klines", None)
        if not callable(get_klines) or len(deduped_codes) > 256:
            return {}, False

        history_counts = {}
        query_limit = max(int(min_history_bars or 0), cls._MIN_HISTORY_BARS)
        for code in deduped_codes:
            try:
                klines = await get_klines(code, limit=query_limit)
            except Exception:
                history_counts[code] = 0
                continue
            history_counts[code] = len(list(klines or []))
        return history_counts, True

    @staticmethod
    def _resolve_task_cursor(
        *,
        planned_task_count: int,
        requested_task_offset: int,
        effective_task_budget: int,
    ) -> tuple[int, int, bool, bool]:
        if planned_task_count <= 0:
            return 0, 0, False, False

        requested = max(0, int(requested_task_offset or 0))
        effective_offset = requested
        task_offset_fallback = False
        if effective_offset >= planned_task_count:
            effective_offset = effective_offset % planned_task_count
            task_offset_fallback = requested > 0

        actual_budget = max(1, min(int(effective_task_budget or 1), planned_task_count))
        next_task_offset = (effective_offset + actual_budget) % planned_task_count
        cursor_wrapped = bool(task_offset_fallback or effective_offset + actual_budget >= planned_task_count)
        return effective_offset, next_task_offset, cursor_wrapped, task_offset_fallback

    @staticmethod
    def _task_target_code(task: dict[str, Any]) -> str:
        return str(((task or {}).get("target_symbols") or [None])[0] or "").strip()

    @classmethod
    def _pop_family_interleaved_task(
        cls,
        bucket: list[dict[str, Any]],
        *,
        used_codes: set[str],
    ) -> dict[str, Any] | None:
        if not bucket:
            return None
        scan_limit = min(len(bucket), max(6, len(used_codes) + 2))
        for index in range(scan_limit):
            code = cls._task_target_code(bucket[index] or {})
            if not code or code not in used_codes:
                return bucket.pop(index)
        return bucket.pop(0)

    @classmethod
    def _interleave_tasks_by_family(
        cls,
        tasks: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if len(tasks) <= 1:
            return [dict(item or {}) for item in tasks]

        family_buckets: dict[str, list[dict[str, Any]]] = {}
        for item in tasks:
            task = dict(item or {})
            family = str(task.get("candidate_family") or "").strip().lower() or "unknown"
            family_buckets.setdefault(family, []).append(task)

        family_order = sorted(
            family_buckets.keys(),
            key=lambda family: (
                int((family_buckets[family][0] or {}).get("matrix_family_rank") or 0),
                int((family_buckets[family][0] or {}).get("matrix_stock_rank") or 0),
                family,
            ),
        )

        interleaved: list[dict[str, Any]] = []
        remaining = sum(len(bucket) for bucket in family_buckets.values())
        while remaining > 0:
            used_codes: set[str] = set()
            wave_progress = False
            for family in family_order:
                bucket = family_buckets.get(family) or []
                task = cls._pop_family_interleaved_task(bucket, used_codes=used_codes)
                if task is None:
                    continue
                interleaved.append(task)
                remaining -= 1
                wave_progress = True
                code = cls._task_target_code(task)
                if code:
                    used_codes.add(code)
            if not wave_progress:
                break

        if remaining > 0:
            for family in family_order:
                bucket = family_buckets.get(family) or []
                while bucket:
                    interleaved.append(bucket.pop(0))
        return interleaved

    @classmethod
    def _build_task(
        cls,
        row: dict[str, Any],
        *,
        family: str,
        rank: int,
        stock_rank: int,
        priority_score: float,
        snapshot: dict[str, Any],
        generation_limit: int,
        family_plan: dict[str, Any] | None = None,
        allocation_item: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        code = str(row.get("code") or "").strip()
        name = str(row.get("name") or code).strip() or code
        holding_bucket = cls._holding_bucket_for_family(family)
        alpha_source = cls._alpha_source_for_family(family)
        risk_level = cls._risk_level_for_family(family)
        resolved_family_plan = dict(family_plan or {})
        resolved_rank = max(1, int(resolved_family_plan.get("family_rank") or rank))
        validation_profile = cls._normalize_validation_profile(
            family,
            dict(resolved_family_plan.get("validation_profile") or {}),
        )
        budget_weight = max(
            0.0,
            min(
                cls._safe_float(resolved_family_plan.get("budget_weight") or resolved_family_plan.get("budget")),
                1.0,
            ),
        )
        failure_penalty = max(
            0.0,
            min(
                cls._safe_float(resolved_family_plan.get("failure_penalty"))
                or cls._default_failure_penalty_for_family(family, family_rank=resolved_rank),
                1.0,
            ),
        )
        priority = max(45, min(98, int(round(priority_score - (resolved_rank - 1) * 1.5))))
        task = {
            "task_id": f"bulk_matrix_{snapshot.get('date')}_{code}_{family}",
            "task_key": f"bulk_matrix:{snapshot.get('date')}:{code}:{family}",
            "task_source": "bulk_stock_matrix",
            "theme": f"stock_strategy_matrix_{family}",
            "title": f"逐股策略矩阵·{name}·{family}",
            "opportunity_type": "stock_strategy_matrix",
            "rationale": f"为 {name}({code}) 生成 {family} 家族候选，优先验证单股可执行策略。",
            "preferred_strategy_types": [family],
            "allowed_strategy_types": [family],
            "strategy_preferences": [family],
            "candidate_family": family,
            "candidate_family_id": f"{code}_{family}_{holding_bucket}",
            "holding_period_bucket": holding_bucket,
            "alpha_source": alpha_source,
            "risk_level": risk_level,
            "regime_fit": "trend_expansion" if family in {"momentum", "growth_factor"} else ("mean_reversion" if family in {"rsi", "value_factor"} else "rotation_balanced"),
            "direction_bias": "long_only",
            "generator_mode": "bulk_stock_matrix",
            "target_symbol_policy": "strict_intersection",
            "universe_expansion_policy": "forbid",
            "preference_strength": "hard",
            "preference_reason": f"stock_matrix:{code}:{family}",
            "validation_focus": str(validation_profile.get("validation_focus") or "candidate_target_only"),
            "validation_profile": validation_profile,
            "holding_window": cls._holding_window_for_family(family),
            "target_symbols": [code],
            "stock_pool": {"selection_mode": "explicit", "symbols": [code]},
            "focus_industries": [str(row.get("industry") or row.get("sector") or "").strip()] if str(row.get("industry") or row.get("sector") or "").strip() else [],
            "priority": priority,
            "generation_limit": generation_limit,
            "matrix_rank": resolved_rank,
            "matrix_stock_rank": stock_rank,
            "matrix_family_rank": resolved_rank,
            "matrix_priority_score": priority_score,
            "stock_family_budget": budget_weight,
            "stock_family_budget_weight": budget_weight,
            "stock_family_failure_penalty": failure_penalty,
            "source_symbol_summary": cls._summarize_symbol(row),
            "source_snapshot": {
                "fear_greed_index": cls._safe_float(snapshot.get("fear_greed_index") or 50.0),
                "fg_level": snapshot.get("fg_level"),
            },
        }
        if allocation_item:
            task["stock_family_priority"] = max(0.0, min(cls._safe_float(allocation_item.get("priority")), 1.0))
            task["stock_family_allocation_source"] = allocation_item.get("source_mode") or "factor_research_stock_family_allocation"
        return cls._finalize_task(task)

    async def plan(self, db, snapshot: dict[str, Any]) -> dict[str, Any]:
        if not STOCK_STRATEGY_MATRIX_ENABLED:
            task_artifact = build_task_artifact()
            self.last_report = {
                "summary": {
                    "enabled": False,
                    "task_count": 0,
                    "stock_count": 0,
                    "eligible_stock_count": 0,
                    "loaded_stock_count": 0,
                    "pages_loaded": 0,
                    "analysis_complete": False,
                    "analysis_stock_coverage_ratio": 0.0,
                    "family_counts": {},
                    "planned_family_counts": {},
                    "universe_limit": STOCK_STRATEGY_MATRIX_UNIVERSE_LIMIT,
                    "requested_universe_offset": 0,
                    "effective_universe_offset": 0,
                    "universe_offset_fallback": False,
                    "next_universe_offset": 0,
                    "cursor_wrapped": False,
                    "cursor_mode": "task_offset",
                    "requested_task_offset": 0,
                    "effective_task_offset": 0,
                    "task_offset_fallback": False,
                    "next_task_offset": 0,
                    "task_cursor_wrapped": False,
                    "max_tasks_per_run": STOCK_STRATEGY_MATRIX_MAX_TASKS_PER_RUN,
                    "max_candidates_per_run": STOCK_STRATEGY_MATRIX_MAX_CANDIDATES_PER_RUN,
                    "generation_limit_per_task": STOCK_STRATEGY_MATRIX_GENERATION_LIMIT_PER_TASK,
                    "effective_task_budget": 0,
                    "estimated_candidate_count": 0,
                    "planned_task_count": 0,
                    "planned_candidate_count": 0,
                    "batch_size": STOCK_STRATEGY_MATRIX_BATCH_SIZE,
                    "batch_count": 0,
                    "selected_batch_count": 0,
                    "batch_task_counts": {},
                    "tasks_per_shard": STOCK_STRATEGY_MATRIX_TASKS_PER_SHARD,
                    "shard_count": 0,
                    "selected_shard_count": 0,
                    "selected_shard_ids": [],
                    "stock_coverage_ratio": 0.0,
                    "allocation_mode": "stock_round_robin_by_family_rank",
                    "allocation_pass_counts": {},
                    "planned_allocation_pass_counts": {},
                    "overflow_task_count": 0,
                    "stock_family_allocation_count": 0,
                    "stock_family_allocation_applied_count": 0,
                    "stock_family_allocation_coverage_ratio": 0.0,
                    "min_history_bars": self._MIN_HISTORY_BARS,
                    "history_prefilter_applied": False,
                    "insufficient_history_filtered_count": 0,
                    "task_artifact_contract_version": task_artifact.get("contract_version"),
                    "task_artifact_available": bool(task_artifact.get("available")),
                },
                "tasks": [],
                "task_artifact": task_artifact,
            }
            return self.last_report

        universe_page_size = max(100, min(int(STOCK_STRATEGY_MATRIX_UNIVERSE_LIMIT), 1000))
        try:
            rows, universe_meta = await load_stock_universe_rows(
                db,
                limit=STOCK_STRATEGY_MATRIX_UNIVERSE_LIMIT,
                page_size=universe_page_size,
                start_offset=0,
            )
        except Exception:
            rows, universe_meta = [], {
                "pages_loaded": 0,
                "loaded_count": 0,
                "complete": False,
                "truncated": False,
                "page_size": universe_page_size,
            }

        hot_sectors = set(self._normalize_sector_labels(snapshot.get("hot_sectors") or [], limit=12))
        cold_sectors = set(self._normalize_sector_labels(snapshot.get("cold_sectors") or [], limit=12))
        active_factors = self._normalize_factor_names(snapshot)
        stock_family_allocation = self._normalize_stock_family_allocation(snapshot)
        candidate_rows = [row for row in rows if str(row.get("code") or "").strip()]
        min_history_bars = self._MIN_HISTORY_BARS
        history_counts, history_prefilter_applied = await self._fetch_history_bar_counts(
            db,
            [str(row.get("code") or "").strip() for row in candidate_rows],
            min_history_bars=min_history_bars,
        )
        filtered_rows = candidate_rows
        insufficient_history_filtered_count = 0
        if history_prefilter_applied:
            filtered_rows = [
                row
                for row in candidate_rows
                if int(history_counts.get(str(row.get("code") or "").strip()) or 0) >= min_history_bars
            ]
            insufficient_history_filtered_count = max(0, len(candidate_rows) - len(filtered_rows))

        family_preference_order = self._base_family_order(snapshot)
        family_preference_source = self._family_preference_source(snapshot)
        scoring_context = self._build_priority_scoring_context(
            filtered_rows,
            snapshot=snapshot,
            hot_sectors=hot_sectors,
            cold_sectors=cold_sectors,
            active_factors=active_factors,
            stock_family_allocation=stock_family_allocation,
        )
        ranked_entries: list[dict[str, Any]] = []
        for row in filtered_rows:
            code = str(row.get("code") or "").strip()
            if not code:
                continue
            allocation_item = dict(stock_family_allocation.get(code) or {})
            component_scores = self._row_priority_components(
                row,
                snapshot=snapshot,
                hot_sectors=hot_sectors,
                cold_sectors=cold_sectors,
                active_factors=active_factors,
                allocation_item=allocation_item,
                scoring_context=scoring_context,
            )
            row_score = round(sum(self._safe_float(value) for value in component_scores.values()), 4)
            family_plans = self._family_plans_for_row(
                row,
                snapshot=snapshot,
                hot_sectors=hot_sectors,
                cold_sectors=cold_sectors,
                active_factors=active_factors,
                allocation_item=allocation_item,
            )
            family_candidates = [
                str(plan.get("family") or "").strip().lower()
                for plan in list(family_plans or [])
                if str(plan.get("family") or "").strip()
            ]
            ranked_entries.append(
                {
                    "row": row,
                    "code": code,
                    "allocation_item": allocation_item,
                    "component_scores": component_scores,
                    "row_score": row_score,
                    "family_plans": family_plans,
                    "family_candidates": family_candidates,
                }
            )
        ranked_entries.sort(
            key=lambda entry: (
                -self._safe_float(entry.get("row_score")),
                -self._safe_float(dict(entry.get("component_scores") or {}).get("valuation_score")),
                -self._safe_float(dict(entry.get("component_scores") or {}).get("factor_alignment_score")),
                -self._safe_float(dict(entry.get("component_scores") or {}).get("allocation_score")),
                -self._safe_float(dict(entry.get("component_scores") or {}).get("size_score")),
                str(entry.get("code") or ""),
            )
        )

        effective_generation_limit = self._effective_generation_limit()
        effective_task_budget = self._effective_task_budget()
        row_plans: list[dict[str, Any]] = []
        full_market_score_rows: list[dict[str, Any]] = []
        max_family_depth = 0
        allocation_applied_count = 0
        for stock_rank, entry in enumerate(ranked_entries, 1):
            row = dict(entry.get("row") or {})
            code = str(entry.get("code") or "").strip()
            allocation_item = dict(entry.get("allocation_item") or {})
            component_scores = dict(entry.get("component_scores") or {})
            row_score = round(self._safe_float(entry.get("row_score")), 4)
            family_plans = [dict(plan or {}) for plan in list(entry.get("family_plans") or [])]
            family_candidates = [
                str(item or "").strip().lower()
                for item in list(entry.get("family_candidates") or [])
                if str(item or "").strip()
            ]
            full_market_score_rows.append(
                {
                    "code": code,
                    "name": str(row.get("name") or code).strip() or code,
                    "industry": str(row.get("industry") or row.get("sector") or "").strip() or None,
                    "market_cap": self._safe_float(row.get("market_cap")),
                    "composite_score": row_score,
                    "component_scores": component_scores,
                    "family_candidates": family_candidates,
                    "eligible": True,
                    "rank": stock_rank,
                }
            )
            row_tasks: list[dict[str, Any]] = []
            for family_plan in family_plans:
                family = str(family_plan.get("family") or "").strip().lower()
                if not family:
                    continue
                row_tasks.append(
                    self._build_task(
                        row,
                        family=family,
                        rank=max(1, self._safe_int(family_plan.get("family_rank")) or len(row_tasks) + 1),
                        stock_rank=stock_rank,
                        priority_score=row_score,
                        snapshot=snapshot,
                        generation_limit=effective_generation_limit,
                        family_plan=family_plan,
                        allocation_item=allocation_item,
                    )
                )
            if not row_tasks:
                continue
            if allocation_item:
                allocation_applied_count += 1
            max_family_depth = max(max_family_depth, len(row_tasks))
            row_plans.append(
                {
                    "code": code,
                    "stock_rank": stock_rank,
                    "priority_score": row_score,
                    "tasks": row_tasks,
                }
            )

        batch_size = max(1, int(STOCK_STRATEGY_MATRIX_BATCH_SIZE))
        row_plan_batches: list[list[dict[str, Any]]] = [
            row_plans[start : start + batch_size]
            for start in range(0, len(row_plans), batch_size)
        ]
        for batch_id, batch_rows in enumerate(row_plan_batches, 1):
            batch_stock_count = len(batch_rows)
            for batch_stock_index, row_plan in enumerate(batch_rows, 1):
                row_plan["matrix_batch_id"] = batch_id
                row_plan["matrix_batch_stock_index"] = batch_stock_index
                row_plan["matrix_batch_stock_count"] = batch_stock_count

        planned_tasks: list[dict[str, Any]] = []
        planned_family_counts: dict[str, int] = {}
        planned_codes: list[str] = []
        planned_allocation_pass_counts: dict[str, int] = {}
        for allocation_pass in range(max_family_depth):
            pass_key = str(allocation_pass + 1)
            pass_count = 0
            for batch_rows in row_plan_batches:
                for row_plan in batch_rows:
                    row_tasks = list(row_plan.get("tasks") or [])
                    if allocation_pass >= len(row_tasks):
                        continue
                    task = dict(row_tasks[allocation_pass] or {})
                    task["matrix_allocation_pass"] = allocation_pass + 1
                    task["matrix_batch_id"] = int(row_plan.get("matrix_batch_id") or 1)
                    task["matrix_batch_stock_index"] = int(row_plan.get("matrix_batch_stock_index") or 1)
                    task["matrix_batch_stock_count"] = int(row_plan.get("matrix_batch_stock_count") or len(batch_rows) or 1)
                    planned_tasks.append(task)
                    family = str(task.get("candidate_family") or "").strip().lower()
                    if family:
                        planned_family_counts[family] = planned_family_counts.get(family, 0) + 1
                    code = str(row_plan.get("code") or "").strip()
                    if code and code not in planned_codes:
                        planned_codes.append(code)
                    pass_count += 1
            if pass_count > 0:
                planned_allocation_pass_counts[pass_key] = pass_count

        planned_tasks = self._interleave_tasks_by_family(planned_tasks)
        planned_tasks, family_task_caps = self._apply_family_pressure_caps(
            planned_tasks,
            effective_task_budget=effective_task_budget,
        )
        planned_family_counts = {}
        for task in planned_tasks:
            family = str(task.get("candidate_family") or "").strip().lower()
            if family:
                planned_family_counts[family] = planned_family_counts.get(family, 0) + 1
        for plan_slot, task in enumerate(planned_tasks, 1):
            task["matrix_plan_slot"] = plan_slot

        tasks_per_shard = max(1, int(STOCK_STRATEGY_MATRIX_TASKS_PER_SHARD))
        shard_count = int(math.ceil(len(planned_tasks) / tasks_per_shard)) if planned_tasks else 0
        planned_batch_task_counts: dict[str, int] = {}
        for task in planned_tasks:
            batch_key = str(int(task.get("matrix_batch_id") or 1))
            planned_batch_task_counts[batch_key] = planned_batch_task_counts.get(batch_key, 0) + 1
        planned_batch_task_indexes: dict[str, int] = {}
        for index, task in enumerate(planned_tasks, 1):
            task["matrix_shard_id"] = int(math.ceil(index / tasks_per_shard))
            task["matrix_shard_task_index"] = ((index - 1) % tasks_per_shard) + 1
            task["matrix_shard_count"] = shard_count
            batch_key = str(int(task.get("matrix_batch_id") or 1))
            planned_batch_task_indexes[batch_key] = planned_batch_task_indexes.get(batch_key, 0) + 1
            task["matrix_batch_count"] = len(row_plan_batches)
            task["matrix_batch_task_index"] = planned_batch_task_indexes[batch_key]
            task["matrix_batch_task_count"] = int(planned_batch_task_counts.get(batch_key) or 0)

        planned_task_count = len(planned_tasks)
        requested_task_offset = max(
            0,
            int(
                snapshot.get("bulk_stock_matrix_task_offset")
                or snapshot.get("bulk_stock_matrix_universe_offset")
                or 0
            ),
        )
        effective_task_offset, next_task_offset, task_cursor_wrapped, task_offset_fallback = self._resolve_task_cursor(
            planned_task_count=planned_task_count,
            requested_task_offset=requested_task_offset,
            effective_task_budget=effective_task_budget,
        )

        tasks: list[dict[str, Any]] = []
        if planned_task_count > 0:
            actual_budget = max(1, min(effective_task_budget, planned_task_count))
            window_end = effective_task_offset + actual_budget
            if window_end <= planned_task_count:
                tasks = [dict(item or {}) for item in planned_tasks[effective_task_offset:window_end]]
            else:
                tasks = [
                    *[dict(item or {}) for item in planned_tasks[effective_task_offset:]],
                    *[dict(item or {}) for item in planned_tasks[: window_end % planned_task_count]],
                ]

        family_counts: dict[str, int] = {}
        selected_codes: list[str] = []
        allocation_pass_counts: dict[str, int] = {}
        batch_task_counts: dict[str, int] = {}
        batch_task_indexes: dict[str, int] = {}
        for index, task in enumerate(tasks, 1):
            task["matrix_budget_slot"] = index
            family = str(task.get("candidate_family") or "").strip().lower()
            if family:
                family_counts[family] = family_counts.get(family, 0) + 1
            code = str((task.get("target_symbols") or [None])[0] or "").strip()
            if code and code not in selected_codes:
                selected_codes.append(code)
            pass_key = str(int(task.get("matrix_allocation_pass") or 0))
            if pass_key and pass_key != "0":
                allocation_pass_counts[pass_key] = allocation_pass_counts.get(pass_key, 0) + 1
            batch_key = str(int(task.get("matrix_batch_id") or 1))
            batch_task_counts[batch_key] = batch_task_counts.get(batch_key, 0) + 1
        for task in tasks:
            batch_key = str(int(task.get("matrix_batch_id") or 1))
            batch_task_indexes[batch_key] = batch_task_indexes.get(batch_key, 0) + 1
            task["matrix_batch_task_index"] = batch_task_indexes[batch_key]
            task["matrix_batch_task_count"] = int(batch_task_counts.get(batch_key) or 0)

        selected_shard_ids = sorted(
            {
                int(task.get("matrix_shard_id") or 0)
                for task in tasks
                if int(task.get("matrix_shard_id") or 0) > 0
            }
        )

        eligible_stock_count = len(row_plans)
        stock_coverage_ratio = round(len(selected_codes) / eligible_stock_count, 4) if eligible_stock_count else 0.0
        analysis_stock_coverage_ratio = round(eligible_stock_count / len(rows), 4) if rows else 0.0
        overflow_task_count = max(planned_task_count - len(tasks), 0)
        stock_family_allocation_coverage_ratio = (
            round(allocation_applied_count / eligible_stock_count, 4)
            if eligible_stock_count
            else 0.0
        )
        full_market_topn = build_full_market_topn_payload(
            as_of_date=str(snapshot.get("date") or snapshot.get("snapshot_date") or "").strip() or None,
            universe_count=len(rows),
            eligible_count=eligible_stock_count,
            score_rows=full_market_score_rows,
            score_contract_version=str(scoring_context.get("score_contract_version") or ""),
            active_factors=list(scoring_context.get("active_factors") or []),
            hot_sectors=sorted(set(scoring_context.get("hot_sectors") or set())),
            cold_sectors=sorted(set(scoring_context.get("cold_sectors") or set())),
            stock_family_allocation_source_mode=scoring_context.get("allocation_source_mode"),
            stock_family_allocation_avg_priority=scoring_context.get("allocation_avg_priority"),
            selection_method="deterministic_bulk_priority_v2",
        )

        report = {
            "summary": {
                "enabled": True,
                "task_count": len(tasks),
                "stock_count": len(selected_codes),
                "eligible_stock_count": eligible_stock_count,
                "loaded_stock_count": len(rows),
                "pages_loaded": int(universe_meta.get("pages_loaded") or 0),
                "analysis_complete": bool(universe_meta.get("complete")) and not bool(universe_meta.get("truncated")),
                "analysis_stock_coverage_ratio": analysis_stock_coverage_ratio,
                "family_counts": family_counts,
                "planned_family_counts": planned_family_counts,
                "universe_limit": STOCK_STRATEGY_MATRIX_UNIVERSE_LIMIT,
                "requested_universe_offset": requested_task_offset,
                "effective_universe_offset": effective_task_offset,
                "universe_offset_fallback": task_offset_fallback,
                "next_universe_offset": next_task_offset,
                "cursor_wrapped": task_cursor_wrapped,
                "cursor_mode": "task_offset",
                "requested_task_offset": requested_task_offset,
                "effective_task_offset": effective_task_offset,
                "task_offset_fallback": task_offset_fallback,
                "next_task_offset": next_task_offset,
                "task_cursor_wrapped": task_cursor_wrapped,
                "max_tasks_per_run": STOCK_STRATEGY_MATRIX_MAX_TASKS_PER_RUN,
                "max_candidates_per_run": STOCK_STRATEGY_MATRIX_MAX_CANDIDATES_PER_RUN,
                "families_per_stock": STOCK_STRATEGY_MATRIX_FAMILIES_PER_STOCK,
                "generation_limit_per_task": effective_generation_limit,
                "effective_task_budget": effective_task_budget,
                "estimated_candidate_count": len(tasks) * effective_generation_limit,
                "planned_task_count": planned_task_count,
                "planned_candidate_count": planned_task_count * effective_generation_limit,
                "batch_size": batch_size,
                "batch_count": len(row_plan_batches),
                "selected_batch_count": len(batch_task_counts),
                "batch_task_counts": batch_task_counts,
                "tasks_per_shard": tasks_per_shard,
                "shard_count": shard_count,
                "selected_shard_count": len(selected_shard_ids),
                "selected_shard_ids": selected_shard_ids,
                "stock_coverage_ratio": stock_coverage_ratio,
                "family_preference_order": family_preference_order,
                "family_preference_source": family_preference_source,
                "family_task_caps": family_task_caps,
                "allocation_mode": (
                    "factor_research_stock_family_allocation"
                    if allocation_applied_count > 0
                    else "stock_round_robin_by_family_rank"
                ),
                "allocation_pass_counts": allocation_pass_counts,
                "planned_allocation_pass_counts": planned_allocation_pass_counts,
                "overflow_task_count": overflow_task_count,
                "stock_family_allocation_count": len(stock_family_allocation),
                "stock_family_allocation_applied_count": allocation_applied_count,
                "stock_family_allocation_coverage_ratio": stock_family_allocation_coverage_ratio,
                "min_history_bars": min_history_bars,
                "history_prefilter_applied": history_prefilter_applied,
                "insufficient_history_filtered_count": insufficient_history_filtered_count,
                "full_market_topn_contract_version": full_market_topn.get("contract_version"),
                "full_market_topn_available": bool(full_market_topn.get("available")),
                "full_market_topn_universe_count": int(full_market_topn.get("universe_count") or 0),
                "full_market_topn_eligible_count": int(full_market_topn.get("eligible_count") or 0),
                "full_market_topn_score_row_count": int(full_market_topn.get("score_row_count") or 0),
                "full_market_topn_n": int(full_market_topn.get("topn_n") or 0),
                "full_market_topn_average_score": full_market_topn.get("average_topn_score"),
                "full_market_topn_constituents_preview": [
                    {
                        "code": item.get("code"),
                        "name": item.get("name"),
                        "industry": item.get("industry"),
                        "composite_score": item.get("composite_score"),
                    }
                    for item in list(full_market_topn.get("constituents") or [])[:5]
                ],
            },
            "tasks": tasks,
            "full_market_topn": full_market_topn,
            "full_market_score_rows": full_market_score_rows,
        }
        task_artifact = build_task_artifact(
            {
                "task_scan": report,
                "task_source_counts": {"bulk_stock_matrix": len(tasks)},
                "event_task_count": 0,
                "snapshot_task_count": 0,
                "bulk_stock_task_count": len(tasks),
            }
        )
        report["task_artifact"] = task_artifact
        report["summary"] = {
            **dict(report.get("summary") or {}),
            "task_artifact_contract_version": task_artifact.get("contract_version"),
            "task_artifact_available": bool(task_artifact.get("available")),
        }
        self.last_report = report
        return self.last_report
