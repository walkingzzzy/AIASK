
    @classmethod
    def _collapse_refresh_existing_candidates(cls, unique: List[dict]) -> tuple[List[dict], List[dict]]:
        collapsed: List[dict] = []
        dropped: List[dict] = []
        kept_by_strategy: dict[str, int] = {}

        for candidate in unique:
            detail = dict(candidate.get('dedup_result') or {})
            if not detail.get('refresh_existing') or str(detail.get('refresh_mode') or '').strip().lower() != 'refresh_metrics_only':
                collapsed.append(candidate)
                continue
            matched_strategy_id = str(detail.get('matched_strategy_id') or '').strip()
            if not matched_strategy_id:
                collapsed.append(candidate)
                continue
            current_rank = cls._candidate_refresh_rank(candidate)
            if matched_strategy_id not in kept_by_strategy:
                kept_by_strategy[matched_strategy_id] = len(collapsed)
                collapsed.append(candidate)
                continue

            kept_index = kept_by_strategy[matched_strategy_id]
            kept_candidate = collapsed[kept_index]
            kept_rank = cls._candidate_refresh_rank(kept_candidate)
            if current_rank > kept_rank:
                previous = dict(kept_candidate)
                previous_detail = dict(previous.get('dedup_result') or {})
                previous_detail.update({
                    'duplicate': True,
                    'duplicate_level': 'refresh_existing_conflict',
                    'match_type': 'refresh_existing',
                    'reason': f"同一目标策略 {matched_strategy_id} 已有更优刷新候选，按回测表现折叠当前候选",
                })
                previous['dedup_result'] = previous_detail
                dropped.append(previous)
                collapsed[kept_index] = candidate
            else:
                current = dict(candidate)
                current_detail = dict(current.get('dedup_result') or {})
                current_detail.update({
                    'duplicate': True,
                    'duplicate_level': 'refresh_existing_conflict',
                    'match_type': 'refresh_existing',
                    'reason': f"同一目标策略 {matched_strategy_id} 已有更优刷新候选，按回测表现折叠当前候选",
                })
                current['dedup_result'] = current_detail
                dropped.append(current)

        return collapsed, dropped

    @staticmethod
    def _merge_metrics(left: Optional[dict], right: Optional[dict]) -> dict:
        merged: dict[str, int] = {}
        for key in {
            "scanned_count",
            "coarse_candidate_count",
            "coarse_tag_hit_count",
            "coarse_target_hit_count",
            "vector_candidate_count",
            "vector_candidate_trimmed_count",
        }:
            merged[key] = int((left or {}).get(key) or 0) + int((right or {}).get(key) or 0)
        return merged

    @staticmethod
    def _select_detail(base_detail: Optional[dict], intra_detail: Optional[dict]) -> dict:
        left = dict(base_detail or {})
        right = dict(intra_detail or {})
        if (
            left.get("refresh_existing")
            and right.get("duplicate")
            and not str(right.get("matched_strategy_id") or "").strip()
        ):
            return left
        if right.get("duplicate"):
            return right
        if left.get("duplicate"):
            return left
        if left.get("refresh_existing"):
            return left
        if right.get("refresh_existing"):
            return right
        left_similarity = float(left.get("effective_similarity") or 0.0)
        right_similarity = float(right.get("effective_similarity") or 0.0)
        return right if right_similarity > left_similarity else left

    async def _analyze_against_existing(
        self,
        candidates: List[dict],
        existing_by_type: Dict[str, List[dict]],
        db,
    ) -> List[tuple[dict, dict, dict]]:
        concurrency = max(1, int(_compat_setting("DEDUP_CONCURRENCY", DEDUP_CONCURRENCY) or 1))
        sem = asyncio.Semaphore(concurrency)

        async def _run(candidate: dict) -> tuple[dict, dict, dict]:
            strategy_type = self._normalize_strategy_type(candidate.get("strategy_type"))
            persisted_bucket = list(existing_by_type.get(strategy_type, []))
            async with sem:
                detail, metrics = await self._find_duplicate(candidate, persisted_bucket, db)
            return candidate, detail, metrics

        return await asyncio.gather(*[_run(candidate) for candidate in list(candidates or [])])

    async def deduplicate(self, candidates: List[dict], db) -> List[dict]:
        # PR-S9: 分页扫描全部 listed + incubating，避免被 limit=500 截断而漏检
        existing: List[dict] = []
        max_total = int(os.getenv("STRATEGY_FACTORY_DEDUP_MAX_EXISTING", "5000") or 5000)
        page_size = int(os.getenv("STRATEGY_FACTORY_DEDUP_PAGE_SIZE", "500") or 500)
        page_size = max(50, min(page_size, 2000))
        for status in ("listed", "incubating", "submitted"):
            try:
                submitted_loader = None
                if status == "submitted" and hasattr(db, "list_submitted_strategies_for_dedup"):
                    submitted_loader = getattr(db, "list_submitted_strategies_for_dedup")
                # 优先尝试分页；DB 不支持 offset 时降级到单次拉取
                offset = 0
                pages_loaded = 0
                while len(existing) < max_total:
                    try:
                        if callable(submitted_loader):
                            rows = await submitted_loader(limit=page_size, offset=offset)
                        else:
                            rows = await db.list_strategies(status, limit=page_size, offset=offset)
                    except TypeError:
                        # 旧接口不接受 offset
                        if callable(submitted_loader):
                            rows = await submitted_loader(limit=page_size) if offset == 0 else []
                        else:
                            rows = await db.list_strategies(status, limit=page_size) if offset == 0 else []
                    rows = list(rows or [])
                    if not rows:
                        break
                    existing.extend(rows)
                    pages_loaded += 1
                    if len(rows) < page_size:
                        break
                    offset += len(rows)
                    if pages_loaded > 50:  # 防止失控
                        break
            except Exception as exc:
                logger.warning("deduplicator: failed to load %s strategies: %s", status, exc)

        existing_by_type = self._bucket_existing_by_type(existing)
        await self._prewarm_candidate_behaviors(candidates, db)
        analyzed_candidates = await self._analyze_against_existing(candidates, existing_by_type, db)

        unique: List[dict] = []
        dropped: List[dict] = []
        vector_checks = 0
        refreshed_existing = 0
        existing_scan_count = 0
        coarse_candidate_count = 0
        coarse_tag_hit_count = 0
        coarse_target_hit_count = 0
        vector_candidate_count = 0
        vector_candidate_trimmed_count = 0
        intra_batch_checks = 0

        for candidate, persisted_detail, persisted_metrics in analyzed_candidates:
            strategy_type = self._normalize_strategy_type(candidate.get("strategy_type"))
            metrics = dict(persisted_metrics or {})
            detail = dict(persisted_detail or {})
            intra_bucket = [item for item in unique if self._normalize_strategy_type(item.get("strategy_type")) == strategy_type]
            if intra_bucket and not detail.get("duplicate"):
                intra_batch_checks += 1
                intra_detail, intra_metrics = await self._find_duplicate(candidate, intra_bucket, db)
                metrics = self._merge_metrics(metrics, intra_metrics)
                detail = self._select_detail(detail, intra_detail)
            candidate["dedup_result"] = detail
            existing_scan_count += int(metrics.get("scanned_count") or 0)
            coarse_candidate_count += int(metrics.get("coarse_candidate_count") or 0)
            coarse_tag_hit_count += int(metrics.get("coarse_tag_hit_count") or 0)
            coarse_target_hit_count += int(metrics.get("coarse_target_hit_count") or 0)
            vector_candidate_count += int(metrics.get("vector_candidate_count") or 0)
            vector_candidate_trimmed_count += int(metrics.get("vector_candidate_trimmed_count") or 0)
            if detail.get("vector_checked"):
                vector_checks += 1
            if detail.get("duplicate"):
                dropped.append({**candidate})
                continue
            if detail.get("refresh_existing"):
                refreshed_existing += 1
            unique.append(candidate)

        collapsed_unique, collapsed_dropped = self._collapse_refresh_existing_candidates(unique)
        dropped.extend(collapsed_dropped)
        unique = collapsed_unique
        refreshed_existing = len([item for item in unique if dict(item.get("dedup_result") or {}).get("refresh_existing")])
        coarse_filtered_count = max(existing_scan_count - coarse_candidate_count, 0)
        coarse_hit_ratio = round(coarse_candidate_count / existing_scan_count, 4) if existing_scan_count else 0.0
        refresh_decision_basis_counts: dict[str, int] = {}
        revision_trigger_reason_counts: dict[str, int] = {}
        tested_object_hash_changed_count = 0
        existing_identity_available_count = 0
        existing_tested_object_available_count = 0
        for item in [*unique, *dropped]:
            dedup_result = dict(item.get("dedup_result") or {})
            refresh_decision_basis = str(dedup_result.get("refresh_decision_basis") or "").strip().lower()
            if refresh_decision_basis:
                refresh_decision_basis_counts[refresh_decision_basis] = (
                    refresh_decision_basis_counts.get(refresh_decision_basis, 0) + 1
                )
            revision_trigger_reason = str(dedup_result.get("revision_trigger_reason") or "").strip().lower()
            if revision_trigger_reason:
                revision_trigger_reason_counts[revision_trigger_reason] = (
                    revision_trigger_reason_counts.get(revision_trigger_reason, 0) + 1
                )
            if bool(dedup_result.get("tested_object_hash_changed", dedup_result.get("tested_object_changed"))):
                tested_object_hash_changed_count += 1
            if bool(dedup_result.get("existing_identity_available")):
                existing_identity_available_count += 1
            if bool(dedup_result.get("existing_tested_object_available")):
                existing_tested_object_available_count += 1
        self.last_report = {
            "summary": {
                "input_count": len(candidates),
                "existing_count": len(existing),
                "existing_scan_count": existing_scan_count,
                "coarse_candidate_count": coarse_candidate_count,
                "coarse_filtered_count": coarse_filtered_count,
                "coarse_hit_ratio": coarse_hit_ratio,
                "coarse_tag_hit_count": coarse_tag_hit_count,
                "coarse_target_hit_count": coarse_target_hit_count,
                "kept_count": len(unique),
                "dropped_count": len(dropped),
                "refreshed_existing_count": refreshed_existing,
                "vector_checks": vector_checks,
                "vector_candidate_count": vector_candidate_count,
                "vector_candidate_trimmed_count": vector_candidate_trimmed_count,
                "candidate_analysis_concurrency": max(1, int(_compat_setting("DEDUP_CONCURRENCY", DEDUP_CONCURRENCY) or 1)),
                "persisted_existing_phase_count": len(analyzed_candidates),
                "intra_batch_check_count": intra_batch_checks,
                "param_threshold": self.THRESHOLD,
                "vector_threshold": self.VECTOR_THRESHOLD,
                "refresh_decision_basis_counts": refresh_decision_basis_counts,
                "revision_trigger_reason_counts": revision_trigger_reason_counts,
                "tested_object_hash_changed_count": tested_object_hash_changed_count,
                "existing_identity_available_count": existing_identity_available_count,
                "existing_tested_object_available_count": existing_tested_object_available_count,
            },
            "kept": [self._report_item(item) for item in unique],
            "dropped": [self._report_item(item) for item in dropped],
        }
        return unique

    @staticmethod
    def _candidate_task_signature(candidate: Optional[dict]) -> str:
        payload = dict(candidate or {})
        research_task = _normalize_research_task_contract(payload.get("research_task") or {})
        event_context = dict(payload.get("event_context") or {}) or _extract_event_context(research_task)
        return _build_task_signature({**research_task, **event_context})

    @staticmethod
    def _existing_task_signature(existing_item: Optional[dict]) -> str:
        payload = dict(existing_item or {})
        params = dict(payload.get("params") or {})
        explicit_signature = str(params.get("task_signature") or payload.get("task_signature") or "").strip()
        if explicit_signature:
            return explicit_signature

        raw_research_task = params.get("research_task") or payload.get("research_task") or {}
        raw_event_context = params.get("event_context") or payload.get("event_context") or {}
        if not raw_research_task and not raw_event_context:
            return ""

        research_task = _normalize_research_task_contract(raw_research_task)
        event_context = dict(raw_event_context or {}) or _extract_event_context(research_task)
        signature = _build_task_signature({**research_task, **event_context})
        if not any(
            [
                research_task.get("task_source"),
                research_task.get("task_id"),
                research_task.get("event_id"),
                research_task.get("theme_code"),
                event_context.get("event_id"),
                event_context.get("theme_code"),
            ]
        ):
            return ""
        return str(signature).strip()

    @staticmethod
    def _candidate_identity_signature(candidate: Optional[dict]) -> str:
        return build_candidate_identity_signature(candidate)

    @staticmethod
    def _candidate_tested_object_hash(candidate: Optional[dict]) -> str:
        payload = dict(candidate or {})
        params = dict(payload.get("params") or {})
        explicit_hash = str(payload.get("tested_object_hash") or params.get("tested_object_hash") or "").strip()
        if explicit_hash:
            return explicit_hash
        return build_tested_object_hash(candidate)

    @staticmethod
    def _has_explicit_identity_contract(item: Optional[dict]) -> bool:
        payload = dict(item or {})
        params = dict(payload.get("params") or {})
        for source in (payload, params):
            for key in (
                "portfolio_spec",
                "execution_assumptions",
                "validation_profile",
                "holding_horizon",
                "trade_plan",
                "risk_rules",
                "rebalance_rule",
                "stock_pool",
                "target_pool_id",
                "lineage",
            ):
                value = source.get(key)
                if value not in (None, "", [], {}):
                    return True
        return False

    @staticmethod
    def _has_explicit_tested_object_hash(item: Optional[dict]) -> bool:
        payload = dict(item or {})
        params = dict(payload.get("params") or {})
        return bool(str(payload.get("tested_object_hash") or params.get("tested_object_hash") or "").strip())

    @classmethod
    def _existing_identity_signature(cls, existing_item: Optional[dict]) -> str:
        if not cls._has_explicit_identity_contract(existing_item):
            return ""
        return build_candidate_identity_signature(existing_item)

    @classmethod
    def _existing_tested_object_hash(cls, existing_item: Optional[dict]) -> str:
        return cls._candidate_tested_object_hash(existing_item)

    @staticmethod
    def _decision_detail(decision: Optional[dict[str, Any]]) -> dict[str, Any]:
        payload = dict(decision or {})
        return {
            "refresh_decision_basis": payload.get("refresh_decision_basis"),
            "revision_trigger_reason": payload.get("revision_trigger_reason"),
            "refresh_improvement_required": payload.get("refresh_improvement_required"),
            "refresh_improvement_passed": payload.get("refresh_improvement_passed"),
            "refresh_candidate_score": payload.get("refresh_candidate_score"),
            "refresh_existing_score": payload.get("refresh_existing_score"),
            "refresh_lineage_limit_reached": payload.get("refresh_lineage_limit_reached"),
            "revision_lineage_limit_reached": payload.get("revision_lineage_limit_reached"),
            "identity_changed": payload.get("identity_changed"),
            "tested_object_changed": payload.get("tested_object_changed"),
            "tested_object_hash_changed": payload.get("tested_object_hash_changed"),
            "task_signature_changed": payload.get("task_signature_changed"),
            "legacy_identity_partial": payload.get("legacy_identity_partial"),
            "tested_object_backfill_incomplete": payload.get("tested_object_backfill_incomplete"),
            "parent_lineage_matched": payload.get("parent_lineage_matched"),
            "existing_identity_available": payload.get("existing_identity_available"),
            "existing_tested_object_available": payload.get("existing_tested_object_available"),
            "candidate_tested_object_hash": payload.get("candidate_tested_object_hash"),
            "existing_tested_object_hash": payload.get("existing_tested_object_hash"),
            "low_quality_lineage_active": payload.get("low_quality_lineage_active"),
            "low_quality_lineage_streak": payload.get("low_quality_lineage_streak"),
            "lineage_structural_shift_required": payload.get("lineage_structural_shift_required"),
            "lineage_structural_shift_applied": payload.get("lineage_structural_shift_applied"),
            "recommended_holding_bucket_shift": payload.get("recommended_holding_bucket_shift"),
            "recommended_generator_mode_shift": payload.get("recommended_generator_mode_shift"),
            "recommended_universe_shift": payload.get("recommended_universe_shift"),
            "lineage_retire_recommended": payload.get("lineage_retire_recommended"),
            "lineage_quality_basis_grade": payload.get("lineage_quality_basis_grade"),
        }

    @classmethod
    def _semantic_result_priority(
        cls,
        decision: Optional[dict[str, Any]],
        match: Optional[dict[str, Any]],
    ) -> tuple[int, int, int, int, float, float]:
        payload = dict(decision or {})
        basis = str(payload.get("refresh_decision_basis") or "").strip().lower()
        basis_rank = {
            "same_tested_object_and_identity": 6,
            "same_tested_object_but_legacy_identity_partial": 5,
            "same_tested_object_with_legacy_identity_backfill": 5,
            "legacy_partial_parent_lineage_refresh": 5,
            "legacy_partial_event_context_refresh": 5,
            "legacy_partial_task_signature_refresh": 5,
            "tested_object_changed": 4,
            "identity_changed": 3,
            "task_signature_changed": 2,
            "target_universe_changed": 1,
        }
        return (
            2 if payload.get("refresh_existing") else 1,
            basis_rank.get(basis, 0),
            1 if payload.get("parent_lineage_matched") else 0,
            1 if payload.get("exact_target_universe_match") else 0,
            float((match or {}).get("target_overlap") or -1.0),
            float((match or {}).get("effective_similarity") or 0.0),
        )

    @classmethod
    def _semantic_result_from_decision(
        cls,
        candidate: Optional[dict],
        match: Optional[dict[str, Any]],
        existing_item: Optional[dict],
        decision: Optional[dict[str, Any]],
    ) -> Optional[tuple[tuple[int, int, int, int, float, float], dict[str, Any]]]:
        payload = dict(decision or {})
        match_payload = dict(match or {})
        decision_detail = cls._decision_detail(payload)
        basis = str(payload.get("refresh_decision_basis") or "").strip().lower()
        effective_similarity = float(match_payload.get("effective_similarity") or 0.0)
        if payload.get("refresh_existing"):
            if basis not in {
                "same_tested_object_and_identity",
                "same_tested_object_with_legacy_identity_backfill",
                "legacy_partial_parent_lineage_refresh",
                "legacy_partial_event_context_refresh",
                "legacy_partial_task_signature_refresh",
            }:
                return None
            return cls._semantic_result_priority(payload, match_payload), {
                "duplicate": False,
                "refresh_existing": True,
                "duplicate_level": "refresh_existing",
                "match_type": "semantic",
                "refresh_mode": "refresh_metrics_only",
                "reason": (
                    f"命中同一 tested object（{basis}），即使综合相似度 {effective_similarity:.4f} < "
                    f"阈值 {cls.THRESHOLD:.2f} 仍转为刷新复用"
                ),
                "threshold": cls.THRESHOLD,
                "vector_threshold": cls.VECTOR_THRESHOLD,
                "vector_checked": False,
                "task_signature": cls._candidate_task_signature(candidate),
                **decision_detail,
                **match_payload,
            }
        if payload.get("spawn_revision_from_existing"):
            return cls._semantic_result_priority(payload, match_payload), {
                "duplicate": False,
                "refresh_existing": False,
                "duplicate_level": "spawn_revision_from_existing",
                "match_type": "semantic",
                "refresh_mode": "spawn_revision_from_existing",
                "parent_strategy_id": (existing_item or {}).get("id"),
                "reason": (
                    f"命中语义级修订条件（{basis or 'revision'}），即使综合相似度 {effective_similarity:.4f} < "
                    f"阈值 {cls.THRESHOLD:.2f} 仍保留为基于已有策略派生的新实验"
                ),
                "threshold": cls.THRESHOLD,
                "vector_threshold": cls.VECTOR_THRESHOLD,
                "vector_checked": False,
                "task_signature": cls._candidate_task_signature(candidate),
                **decision_detail,
                **match_payload,
            }
        return None
