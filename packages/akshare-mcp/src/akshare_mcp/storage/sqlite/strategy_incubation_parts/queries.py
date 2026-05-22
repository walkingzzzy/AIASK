
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
                WHERE paper_trades.source_order_id = paper_orders.id
                  AND paper_orders.position_id IS NOT NULL
                  AND ($1 IS NULL OR COALESCE(paper_trades.strategy_id, paper_orders.strategy_id) = $1)
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

    def _execution_lineage_semantic_contract_status(self, strategy: Optional[dict]) -> dict:
        payload = dict(strategy or {})
        params = dict(payload.get("params") or {})
        evidence_chain = dict(payload.get("evidence_chain") or params.get("evidence_chain") or {})
        prediction_contract = dict(
            payload.get("prediction_contract") or params.get("prediction_contract") or {}
        )
        claim_to_trade_plan_map = dict(
            payload.get("claim_to_trade_plan_map")
            or params.get("claim_to_trade_plan_map")
            or {}
        )
        trade_plan_to_dsl_map = dict(
            payload.get("trade_plan_to_dsl_map")
            or params.get("trade_plan_to_dsl_map")
            or {}
        )
        evidence_alignment_audit = dict(
            payload.get("evidence_alignment_audit")
            or params.get("evidence_alignment_audit")
            or {}
        )
        claim_to_trade_step_ids = dict(
            claim_to_trade_plan_map.get("claim_to_trade_step_ids") or {}
        )
        trade_step_to_dsl_sections = dict(
            trade_plan_to_dsl_map.get("trade_step_to_dsl_sections") or {}
        )
        hard_fail_reasons = [
            _string(item)
            for item in list(evidence_alignment_audit.get("hard_fail_reasons") or [])
            if _string(item)
        ]
        missing_fields: list[str] = []
        if not evidence_chain:
            missing_fields.append("evidence_chain")
        if not prediction_contract:
            missing_fields.append("prediction_contract")
        if not claim_to_trade_step_ids:
            missing_fields.append("claim_to_trade_plan_map")
        if not trade_step_to_dsl_sections:
            missing_fields.append("trade_plan_to_dsl_map")
        if not evidence_alignment_audit:
            missing_fields.append("evidence_alignment_audit")
        compile_stable_ready = not missing_fields and not hard_fail_reasons
        status = (
            "compile_stable_ready"
            if compile_stable_ready
            else "legacy_contract_gap"
            if payload
            else "missing_strategy"
        )
        return {
            "status": status,
            "compile_stable_ready": compile_stable_ready,
            "missing_fields": missing_fields,
            "hard_fail_reasons": hard_fail_reasons,
            "evidence_alignment_status": _string(
                evidence_alignment_audit.get("evidence_alignment_status")
                or evidence_alignment_audit.get("alignment_status")
            )
            or None,
            "evidence_alignment_score": _safe_float(
                evidence_alignment_audit.get("evidence_alignment_score")
            ),
            "semantic_integrity_score": _safe_float(
                evidence_alignment_audit.get("semantic_integrity_score")
            ),
            "mapped_claim_count": sum(
                1
                for value in claim_to_trade_step_ids.values()
                if list(value or [])
            ),
            "mapped_trade_step_count": sum(
                1
                for value in trade_step_to_dsl_sections.values()
                if list(value or [])
            ),
            "has_evidence_chain": bool(evidence_chain),
            "has_prediction_contract": bool(prediction_contract),
        }

    def _normalize_trade_audit_summary_counts(
        self,
        payload: Optional[dict[str, Any]],
    ) -> dict[str, Any]:
        normalized = dict(payload or {})
        raw_incomplete_position_count = int(
            normalized.get("incomplete_position_count") or 0
        )
        open_position_count = int(normalized.get("open_position_count") or 0)
        normalized["raw_incomplete_position_count"] = raw_incomplete_position_count
        normalized["open_position_count"] = open_position_count
        normalized["incomplete_position_count"] = max(
            0,
            raw_incomplete_position_count - open_position_count,
        )
        return normalized

    async def backfill_strategy_signal_evidence_native(
        self,
        strategy_id: Optional[str] = None,
        *,
        limit: int = 5000,
    ) -> dict:
        strategy_filter = _string(strategy_id) or None
        limit_value = max(1, min(int(limit or 5000), 10000))
        save_signal_evidence = getattr(self, "save_strategy_signal_evidence", None)
        if not callable(save_signal_evidence):
            return {
                "strategy_id": strategy_filter,
                "status": "unsupported",
                "reason": "save_strategy_signal_evidence_missing",
                "saved_signal_count": 0,
                "saved_row_count": 0,
            }

        if strategy_filter:
            orders = await self.list_strategy_paper_orders(strategy_filter, limit=limit_value)
            trades = await self.list_strategy_paper_trades(strategy_filter, limit=limit_value)
            existing_rows = await self.list_strategy_signal_evidence(
                strategy_id=strategy_filter,
                limit=limit_value,
            )
        else:
            async with self.acquire() as conn:
                order_rows = await conn.fetch(
                    """
                    SELECT *
                    FROM paper_orders
                    WHERE NULLIF(TRIM(COALESCE(signal_id, '')), '') IS NOT NULL
                    ORDER BY COALESCE(filled_at, updated_at, created_at) DESC
                    LIMIT $1
                    """,
                    limit_value,
                )
                trade_rows = await conn.fetch(
                    """
                    SELECT *
                    FROM paper_trades
                    WHERE NULLIF(TRIM(COALESCE(signal_id, '')), '') IS NOT NULL
                    ORDER BY trade_time DESC, created_at DESC
                    LIMIT $1
                    """,
                    limit_value,
                )
                signal_rows = await conn.fetch(
                    """
                    SELECT signal_id
                    FROM strategy_signal_evidence
                    ORDER BY created_at DESC
                    LIMIT $1
                    """,
                    limit_value,
                )
            orders = [dict(row) for row in order_rows]
            trades = [dict(row) for row in trade_rows]
            existing_rows = [dict(row) for row in signal_rows]

        existing_signal_ids = {
            _string(row.get("signal_id"))
            for row in list(existing_rows or [])
            if _string(row.get("signal_id"))
        }
        initial_existing_signal_count = len(existing_signal_ids)
        trades_by_signal_id: dict[str, dict] = {}
        trades_by_order_id: dict[str, dict] = {}
        for trade in list(trades or []):
            signal_id = _string(trade.get("signal_id"))
            order_id = _string(trade.get("source_order_id"))
            if signal_id and signal_id not in trades_by_signal_id:
                trades_by_signal_id[signal_id] = dict(trade)
            if order_id and order_id not in trades_by_order_id:
                trades_by_order_id[order_id] = dict(trade)

        try:
            from strategy_factory.api.semantic_contract import (
                build_signal_evidence_records,
            )
        except Exception as exc:
            build_signal_evidence_records = None
            logger.warning("native signal evidence backfill import failed: %s", exc)

        strategy_cache: dict[str, Optional[dict]] = {}
        strategy_semantic_status_cache: dict[str, dict] = {}
        semantic_gap_strategy_ids: set[str] = set()
        compile_stable_signal_count = 0
        native_generated_unmapped_signal_count = 0
        proxy_backfilled_signal_count = 0
        compile_stable_row_count = 0
        native_generated_unmapped_row_count = 0
        proxy_backfilled_row_count = 0
        skipped_existing_signal_count = 0
        skipped_missing_strategy_count = 0
        saved_signal_ids: set[str] = set()
        saved_row_count = 0

        def _normalized_phase(direction_value: str, trade_type_value: str) -> str:
            token = _string(direction_value or trade_type_value).lower()
            if token in {"sell", "short", "exit", "close", "reduce"}:
                return "exit"
            return "entry"

        def _phase_direction_token(phase: str) -> str:
            return "down" if phase == "exit" else "up"

        def _resolve_semantic_phase_lineage(strategy_payload: dict, phase: str) -> tuple[Optional[str], Optional[str], bool]:
            params = dict(strategy_payload.get("params") or {})
            claim_map = dict(
                strategy_payload.get("claim_to_trade_plan_map")
                or params.get("claim_to_trade_plan_map")
                or {}
            )
            trade_map = dict(
                strategy_payload.get("trade_plan_to_dsl_map")
                or params.get("trade_plan_to_dsl_map")
                or {}
            )
            trade_step_sections = dict(trade_map.get("trade_step_to_dsl_sections") or {})
            trade_step_to_claim_ids = dict(claim_map.get("trade_step_to_claim_ids") or {})
            claim_to_trade_step_ids = dict(claim_map.get("claim_to_trade_step_ids") or {})

            matched_trade_steps = [
                step_id
                for step_id, sections in trade_step_sections.items()
                if phase in {
                    _string(section).lower()
                    for section in list(sections or [])
                    if _string(section)
                }
            ]
            precise_mapping = bool(matched_trade_steps)
            matched_trade_steps = sorted(
                step_id for step_id in matched_trade_steps if _string(step_id)
            )
            if matched_trade_steps:
                applied_trade_step_id = matched_trade_steps[0]
            else:
                applied_trade_step_id = (
                    "exit_step_backfill" if phase == "exit" else "entry_step_backfill"
                )

            claim_candidates = [
                _string(item)
                for item in list(trade_step_to_claim_ids.get(applied_trade_step_id) or [])
                if _string(item)
            ]
            if not claim_candidates and precise_mapping:
                claim_candidates = sorted(
                    claim_id
                    for claim_id, step_ids in claim_to_trade_step_ids.items()
                    if applied_trade_step_id
                    in {
                        _string(step_id)
                        for step_id in list(step_ids or [])
                        if _string(step_id)
                    }
                )
            if claim_candidates:
                applied_claim_id = claim_candidates[0]
            else:
                applied_claim_id = (
                    "legacy_claim_exit" if phase == "exit" else "legacy_claim_entry"
                )
            precise_mapping = precise_mapping and bool(claim_candidates)
            return applied_trade_step_id, applied_claim_id, precise_mapping

        for order in list(orders or []):
            order_payload = dict(order or {})
            signal_id = _string(order_payload.get("signal_id"))
            if not signal_id:
                continue
            if signal_id in existing_signal_ids:
                skipped_existing_signal_count += 1
                continue

            trade_payload = dict(
                trades_by_order_id.get(_string(order_payload.get("id")))
                or trades_by_signal_id.get(signal_id)
                or {}
            )
            resolved_strategy_id = _string(
                order_payload.get("strategy_id")
                or trade_payload.get("strategy_id")
                or strategy_filter
            )
            if not resolved_strategy_id:
                skipped_missing_strategy_count += 1
                continue

            if resolved_strategy_id not in strategy_cache:
                strategy_cache[resolved_strategy_id] = await self.get_strategy(
                    resolved_strategy_id
                )
                strategy_semantic_status_cache[resolved_strategy_id] = (
                    self._execution_lineage_semantic_contract_status(
                        strategy_cache[resolved_strategy_id]
                    )
                )
            strategy_payload = dict(strategy_cache.get(resolved_strategy_id) or {})
            if not strategy_payload:
                skipped_missing_strategy_count += 1
                continue
            semantic_status = dict(
                strategy_semantic_status_cache.get(resolved_strategy_id) or {}
            )
            if not semantic_status.get("compile_stable_ready"):
                semantic_gap_strategy_ids.add(resolved_strategy_id)

            signal_date = (
                order_payload.get("signal_date")
                or trade_payload.get("trade_time")
                or order_payload.get("filled_at")
                or order_payload.get("created_at")
            )
            signal_ts = (
                trade_payload.get("trade_time")
                or order_payload.get("filled_at")
                or order_payload.get("updated_at")
                or order_payload.get("created_at")
            )
            code = _string(order_payload.get("code") or trade_payload.get("stock_code"))
            position_id = _string(
                order_payload.get("position_id") or trade_payload.get("position_id")
            ) or None
            account_id = _string(
                order_payload.get("account_id") or trade_payload.get("account_id")
            ) or None
            phase = _normalized_phase(
                order_payload.get("direction"),
                trade_payload.get("trade_type"),
            )
            runtime_action_reason = (
                "exit_execution_backfill"
                if phase == "exit"
                else "entry_execution_backfill"
            )

            evidence_records: list[dict] = []
            build_mode = "paper_execution_backfill"
            if callable(build_signal_evidence_records):
                try:
                    evidence_records = list(
                        build_signal_evidence_records(
                            strategy_payload,
                            signal_id=signal_id,
                            position_id=position_id,
                            account_id=account_id,
                            signal_date=signal_date,
                            code=code,
                        )
                        or []
                    )
                except Exception as exc:
                    logger.warning(
                        "native signal evidence generation failed for %s/%s: %s",
                        resolved_strategy_id,
                        signal_id,
                        exc,
                    )
                    evidence_records = []

            has_precise_mapping = any(
                _string(item.get("applied_trade_step_id"))
                or _string(item.get("applied_claim_id"))
                for item in evidence_records
            )
            if evidence_records and has_precise_mapping:
                build_mode = "compile_stable_native"
            elif evidence_records:
                build_mode = "native_generated_unmapped"
            else:
                applied_trade_step_id, applied_claim_id, precise_mapping = (
                    _resolve_semantic_phase_lineage(strategy_payload, phase)
                )
                build_mode = (
                    "paper_execution_backfill_mapped"
                    if precise_mapping
                    else "paper_execution_backfill"
                )
                evidence_id = (
                    f"paper_execution_{phase}_{_string(order_payload.get('id')) or signal_id}"
                )
                evidence_records = [
                    {
                        "id": (
                            f"{signal_id}:{evidence_id}:{applied_claim_id or 'unclaimed'}:"
                            f"{applied_trade_step_id or 'unmapped_step'}"
                        ),
                        "strategy_id": resolved_strategy_id,
                        "signal_id": signal_id,
                        "position_id": position_id,
                        "account_id": account_id,
                        "signal_date": signal_date,
                        "signal_ts": signal_ts,
                        "code": code or _string(trade_payload.get("stock_code")) or None,
                        "symbol": code or _string(trade_payload.get("stock_code")) or None,
                        "candidate_artifact_id": (
                            strategy_payload.get("candidate_artifact_id")
                            or dict(strategy_payload.get("params") or {}).get(
                                "candidate_artifact_id"
                            )
                        ),
                        "experiment_id": (
                            strategy_payload.get("experiment_id")
                            or dict(strategy_payload.get("params") or {}).get(
                                "experiment_id"
                            )
                        ),
                        "evidence_id": evidence_id,
                        "applied_claim_id": applied_claim_id,
                        "applied_trade_step_id": applied_trade_step_id,
                        "source_type": "paper_execution_backfill",
                        "direction": _phase_direction_token(phase),
                        "horizon_days": None,
                        "raw_confidence": None,
                        "calibrated_confidence": None,
                        "proxy_only": True,
                        "runtime_action_reason": runtime_action_reason,
                        "runtime_action_source": "paper_orders/paper_trades",
                        "evidence_payload": {
                            "backfill_mode": "paper_execution_native_backfill_v1",
                            "build_mode": build_mode,
                            "strategy_id": resolved_strategy_id,
                            "signal_id": signal_id,
                            "position_id": position_id,
                            "account_id": account_id,
                            "signal_ts": signal_ts,
                            "signal_date": signal_date,
                            "code": code or _string(trade_payload.get("stock_code")) or None,
                            "applied_claim_id": applied_claim_id,
                            "applied_trade_step_id": applied_trade_step_id,
                            "runtime_action_reason": runtime_action_reason,
                            "runtime_action_source": "paper_orders/paper_trades",
                            "semantic_contract_status": semantic_status.get("status"),
                            "semantic_contract_missing_fields": list(
                                semantic_status.get("missing_fields") or []
                            ),
                            "source_order_id": _string(order_payload.get("id")) or None,
                            "source_trade_id": _string(trade_payload.get("id")) or None,
                            "source_trade_type": _string(trade_payload.get("trade_type"))
                            or _string(order_payload.get("direction"))
                            or None,
                            "source_reason": _string(
                                trade_payload.get("reason") or order_payload.get("reason")
                            )
                            or None,
                        },
                    }
                ]

            for evidence in evidence_records:
                payload = {
                    "id": evidence.get("id"),
                    "signal_id": signal_id,
                    "strategy_id": resolved_strategy_id,
                    "signal_date": signal_date,
                    "signal_ts": evidence.get("signal_ts") or signal_ts,
                    "code": evidence.get("code") or evidence.get("symbol") or code,
                    "candidate_artifact_id": evidence.get("candidate_artifact_id"),
                    "experiment_id": evidence.get("experiment_id"),
                    "evidence_id": evidence.get("evidence_id"),
                    "applied_claim_id": evidence.get("applied_claim_id"),
                    "applied_trade_step_id": evidence.get("applied_trade_step_id"),
                    "source_type": evidence.get("source_type") or evidence.get("evidence_type"),
                    "direction": evidence.get("direction")
                    or _phase_direction_token(phase),
                    "horizon_days": evidence.get("horizon_days"),
                    "raw_confidence": evidence.get("raw_confidence"),
                    "calibrated_confidence": evidence.get("calibrated_confidence"),
                    "proxy_only": (
                        bool(evidence.get("proxy_only"))
                        if build_mode == "compile_stable_native"
                        else True
                    ),
                    "doc_uid": evidence.get("doc_uid"),
                    "headline_label_id": evidence.get("headline_label_id"),
                    "runtime_action_reason": evidence.get("runtime_action_reason")
                    or runtime_action_reason,
                    "runtime_action_source": evidence.get("runtime_action_source")
                    or (
                        "paper_orders/paper_trades"
                        if build_mode.startswith("paper_execution_backfill")
                        else "semantic_contract.build_signal_evidence_records"
                    ),
                    "payload": {
                        **dict(
                            evidence.get("payload")
                            or evidence.get("evidence_payload")
                            or {}
                        ),
                        "backfill_mode": "paper_execution_native_backfill_v1",
                        "build_mode": build_mode,
                        "signal_id": signal_id,
                        "strategy_id": resolved_strategy_id,
                        "position_id": position_id,
                        "account_id": account_id,
                        "source_order_id": _string(order_payload.get("id")) or None,
                        "source_trade_id": _string(trade_payload.get("id")) or None,
                        "source_trade_type": _string(trade_payload.get("trade_type"))
                        or _string(order_payload.get("direction"))
                        or None,
                        "semantic_contract_status": semantic_status.get("status"),
                        "semantic_contract_missing_fields": list(
                            semantic_status.get("missing_fields") or []
                        ),
                    },
                }
                await save_signal_evidence(payload)
                saved_row_count += 1

            existing_signal_ids.add(signal_id)
            saved_signal_ids.add(signal_id)
            if build_mode == "compile_stable_native":
                compile_stable_signal_count += 1
                compile_stable_row_count += len(evidence_records)
            elif build_mode == "native_generated_unmapped":
                native_generated_unmapped_signal_count += 1
                native_generated_unmapped_row_count += len(evidence_records)
            else:
                proxy_backfilled_signal_count += 1
                proxy_backfilled_row_count += len(evidence_records)

        status = (
            "ok"
            if saved_signal_ids
            else "no_op"
            if skipped_existing_signal_count or initial_existing_signal_count
            else "empty"
        )
        return {
            "strategy_id": strategy_filter,
            "status": status,
            "method": "strategy_signal_evidence_native_backfill_v1",
            "scanned_order_count": len(list(orders or [])),
            "scanned_trade_count": len(list(trades or [])),
            "initial_existing_signal_count": initial_existing_signal_count,
            "saved_signal_count": len(saved_signal_ids),
            "saved_row_count": saved_row_count,
            "compile_stable_signal_count": compile_stable_signal_count,
            "compile_stable_row_count": compile_stable_row_count,
            "native_generated_unmapped_signal_count": native_generated_unmapped_signal_count,
            "native_generated_unmapped_row_count": native_generated_unmapped_row_count,
            "proxy_backfilled_signal_count": proxy_backfilled_signal_count,
            "proxy_backfilled_row_count": proxy_backfilled_row_count,
            "skipped_existing_signal_count": skipped_existing_signal_count,
            "skipped_missing_strategy_count": skipped_missing_strategy_count,
            "semantic_contract_gap_strategy_ids": sorted(semantic_gap_strategy_ids),
        }

    def _build_execution_audit_blocker_details(
        self,
        *,
        verification: dict,
        acceptance_matrix: dict,
        audit_summary: dict,
    ) -> list[dict]:
        coverage = dict(verification.get("coverage") or {})
        orders = dict(coverage.get("paper_orders") or {})
        trades = dict(coverage.get("paper_trades") or {})
        lineage_source = dict(verification.get("lineage_source") or {})
        round_trip = dict(verification.get("trade_round_trip") or {})
        semantic_contract = dict(lineage_source.get("semantic_contract") or {})

        def _append(
            code: str,
            category: str,
            summary: str,
            todo: str,
            *,
            severity: str = "error",
            owner: str = "engineering",
            evidence: Optional[dict] = None,
        ) -> dict:
            payload = {
                "blocker": code,
                "category": category,
                "severity": severity,
                "owner": owner,
                "summary": summary,
                "todo": todo,
            }
            if evidence:
                payload["evidence"] = evidence
            return payload

        blocker_details: list[dict] = []
        if not acceptance_matrix.get("schema_ready"):
            blocker_details.append(
                _append(
                    "execution_audit_schema_incomplete",
                    "schema_gap",
                    "execution audit 依赖表或列仍不完整，当前结果不能作为生产验收依据。",
                    "补齐 Phase 5/6 schema，并重新执行 execution_audit_acceptance 验证表/列覆盖率。",
                )
            )
        if not acceptance_matrix.get("migration_ready"):
            blocker_details.append(
                _append(
                    "execution_audit_migrations_unverified",
                    "migration_gap",
                    "迁移标记或 backfill 标记缺失，无法证明真实生产库已经跑完闭环。",
                    "在目标 SQLite 数据库执行迁移与 backfill，并确认 migration key 全量落库。",
                )
            )
        if not acceptance_matrix.get("orders_position_link_ready"):
            blocker_details.append(
                _append(
                    "paper_orders_position_link_incomplete",
                    "data_gap",
                    "paper_orders 仍存在缺失 position_id 的链路，round-trip 聚合不完整。",
                    "重新运行 trade position linkage backfill，并核对 paper_orders.position_id 覆盖率直到 100%。",
                    evidence={
                        "total_orders": int(orders.get("total") or 0),
                        "position_id_linked": int(orders.get("position_id_linked") or 0),
                    },
                )
            )
        if not acceptance_matrix.get("trades_position_link_ready"):
            blocker_details.append(
                _append(
                    "paper_trades_position_link_incomplete",
                    "data_gap",
                    "paper_trades 仍存在缺失 position_id 的链路，无法完整复算 fill -> position。",
                    "重新运行 trade position linkage backfill，并核对 paper_trades.position_id 覆盖率直到 100%。",
                    evidence={
                        "total_trades": int(trades.get("total") or 0),
                        "position_id_linked": int(trades.get("position_id_linked") or 0),
                    },
                )
            )
        if not acceptance_matrix.get("native_lineage_ready"):
            native_status = _string(lineage_source.get("status")) or "missing"
            blocker_details.append(
                _append(
                    "native_signal_evidence_lineage_missing",
                    "code_gap"
                    if native_status in {"missing", "legacy_only", "candidate_only"}
                    else "data_gap",
                    "策略运行链缺少可审计的 native signal lineage，execution audit 无法解释 signal -> claim -> trade step。",
                    (
                        "先运行 backfill_strategy_signal_evidence_native；"
                        "若策略仍缺 claim_to_trade_plan_map/trade_plan_to_dsl_map/evidence_alignment_audit，"
                        "再执行 strategy_recompile_backfill 补齐 compile-stable semantic contract。"
                    ),
                    evidence={
                        "lineage_status": native_status,
                        "native_signal_evidence_count": int(
                            lineage_source.get("native_signal_evidence_count") or 0
                        ),
                        "native_trade_step_lineage_count": int(
                            lineage_source.get("native_trade_step_lineage_count") or 0
                        ),
                        "semantic_contract_status": semantic_contract.get("status"),
                        "semantic_contract_missing_fields": list(
                            semantic_contract.get("missing_fields") or []
                        ),
                    },
                )
            )
        if not acceptance_matrix.get("fill_round_trip_ready"):
            blocker_details.append(
                _append(
                    "trade_position_fill_round_trip_incomplete",
                    "data_gap",
                    "strategy_trade_position_fills 与 strategy_trade_positions 之间仍存在 round-trip 缺口。",
                    "检查 refresh_strategy_trade_position 聚合结果，确保每个 position 至少有对应 fill 并能完成 round-trip。",
                    evidence={
                        "position_count": int(round_trip.get("position_count") or 0),
                        "fill_count": int(round_trip.get("fill_count") or 0),
                    },
                )
            )

        realized_trade_count = int(audit_summary.get("realized_trade_count") or 0)
        incomplete_position_count = int(audit_summary.get("incomplete_position_count") or 0)
        if not acceptance_matrix.get("trade_evidence_ready"):
            blocker_details.append(
                _append(
                    "realized_trade_evidence_insufficient",
                    "sample_gap",
                    "真实已平仓样本不足，execution audit 还没有形成稳定的交易证据面。",
                    (
                        "继续运行 paper incubation，直到至少形成 1 个完全闭合的 realized position，"
                        "并把 incomplete positions 清零。"
                    ),
                    owner="operations",
                    evidence={
                        "realized_trade_count": realized_trade_count,
                        "incomplete_position_count": incomplete_position_count,
                        "open_position_count": int(
                            audit_summary.get("open_position_count") or 0
                        ),
                        "raw_incomplete_position_count": int(
                            audit_summary.get("raw_incomplete_position_count") or 0
                        ),
                    },
                )
            )

        gate_status = _string(audit_summary.get("execution_audit_gate_status"))
        if not acceptance_matrix.get("hard_gate_ready"):
            gate_reasons = [
                _string(item)
                for item in list(audit_summary.get("execution_audit_gate_reasons") or [])
                if _string(item)
            ]
            if gate_status == "bootstrap_pending":
                blocker_details.append(
                    _append(
                        "bootstrap_pending",
                        "sample_gap",
                        "execution hard gate 仍处于 bootstrap 阶段，当前只有运行痕迹，没有足够的已实现交易审计样本。",
                        "继续累积第一批闭合交易，至少让 realized_trade_count > 0 后再重跑 acceptance。",
                        owner="operations",
                        evidence={
                            "realized_trade_count": realized_trade_count,
                            "open_position_count": int(
                                audit_summary.get("open_position_count") or 0
                            ),
                        },
                    )
                )
            elif gate_status == "insufficient_samples":
                blocker_details.append(
                    _append(
                        "insufficient_samples",
                        "sample_gap",
                        "已实现交易数量未达到 hard gate 最低样本门槛。",
                        "继续孵化并累积到 production hard gate 所需样本量，然后再验证 trade_expectancy / conversion 指标。",
                        owner="operations",
                        evidence={
                            "realized_trade_count": realized_trade_count,
                            "required_trade_count": int(audit_summary.get("required_trade_count") or 20),
                            "bootstrap_trade_floor": int(audit_summary.get("bootstrap_trade_floor") or 0),
                        },
                    )
                )
            elif gate_status == "bootstrap_ready":
                blocker_details.append(
                    _append(
                        "promotion_hard_gate_pending",
                        "sample_gap",
                        "已达到 bootstrap 样本门槛且执行指标通过，但尚未达到 production hard gate 所需样本量。",
                        "继续累积 production hard gate 所需的 realized trades，再申请 promotion-ready。",
                        owner="operations",
                        evidence={
                            "realized_trade_count": realized_trade_count,
                            "required_trade_count": int(audit_summary.get("required_trade_count") or 20),
                            "bootstrap_trade_floor": int(audit_summary.get("bootstrap_trade_floor") or 0),
                        },
                    )
                )
            else:
                blocker_details.append(
                    _append(
                        gate_status or "execution_audit_gate_not_passed",
                        "performance_gap",
                        "execution hard gate 指标未通过，当前策略还不能进入 promotion-ready 区间。",
                        "针对 trade_expectancy、pnl_conversion_efficiency、execution_conversion_efficiency 做专项修复，再重跑 acceptance。",
                        owner="research",
                        evidence={"gate_reasons": gate_reasons},
                    )
                )
        return blocker_details

    async def get_strategy_trade_audit_summary(self, strategy_id: str) -> dict:
        from ...services.strategy_lifecycle_shared import evaluate_execution_audit_gate

        await self.backfill_trade_position_links(strategy_id)
        strategy = await self.get_strategy(strategy_id)
        strategy_type = _string((strategy or {}).get("strategy_type")) or None
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT
                    COALESCE(COUNT(*), 0) AS mapped_position_count,
                    COALESCE(COUNT(*) FILTER (WHERE audit_eligible), 0) AS realized_trade_count,
                    COALESCE(
                        COUNT(*) FILTER (
                            WHERE LOWER(COALESCE(status, '')) = 'open'
                        ),
                        0
                    ) AS open_position_count,
                    COALESCE(COUNT(*) FILTER (WHERE NOT audit_eligible), 0) AS incomplete_position_count,
                    COALESCE(AVG(realized_return) FILTER (WHERE audit_eligible), 0) AS trade_expectancy,
                    COALESCE(
                        SUM(realized_pnl) FILTER (WHERE audit_eligible)
                        / NULLIF(SUM(entry_amount + entry_commission) FILTER (WHERE audit_eligible), 0),
                        0
                    ) AS pnl_conversion_efficiency,
                    COALESCE(
                        AVG(execution_conversion_efficiency) FILTER (WHERE audit_eligible),
                        0
                    ) AS execution_conversion_efficiency,
                    COALESCE(
                        AVG(CASE WHEN realized_pnl > 0 THEN 1.0 ELSE 0.0 END) FILTER (WHERE audit_eligible),
                        0
                    ) AS execution_win_rate,
                    COALESCE(
                        AVG(CASE WHEN realized_pnl > 0 THEN realized_pnl END) FILTER (WHERE audit_eligible)
                        / NULLIF(ABS(AVG(CASE WHEN realized_pnl < 0 THEN realized_pnl END) FILTER (WHERE audit_eligible)), 0),
                        0
                    ) AS avg_win_loss_ratio,
                    COALESCE(SUM(realized_pnl) FILTER (WHERE audit_eligible), 0) AS realized_pnl_total
                FROM strategy_trade_positions
                WHERE strategy_id = $1
                """,
                strategy_id,
            )
        payload = self._normalize_trade_audit_summary_counts(dict(row or {}))
        realized_trade_count = int(payload.get("realized_trade_count") or 0)
        trade_expectancy = float(payload.get("trade_expectancy") or 0.0)
        pnl_conversion_efficiency = float(payload.get("pnl_conversion_efficiency") or 0.0)
        execution_conversion_efficiency = float(payload.get("execution_conversion_efficiency") or 0.0)
        gate_status, gate_reasons, metric_passes, hard_gate_metrics = evaluate_execution_audit_gate(
            {
                **payload,
                "strategy_type": strategy_type,
                "realized_trade_count": realized_trade_count,
                "trade_expectancy": trade_expectancy,
                "pnl_conversion_efficiency": pnl_conversion_efficiency,
                "execution_conversion_efficiency": execution_conversion_efficiency,
            },
            strategy_type=strategy_type,
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
            "strategy_type": strategy_type,
            "realized_trade_count": realized_trade_count,
            "incomplete_position_count": int(payload.get("incomplete_position_count") or 0),
            "raw_incomplete_position_count": int(
                payload.get("raw_incomplete_position_count") or 0
            ),
            "open_position_count": int(payload.get("open_position_count") or 0),
            "trade_expectancy": round(trade_expectancy, 6),
            "pnl_conversion_efficiency": round(pnl_conversion_efficiency, 6),
            "execution_conversion_efficiency": round(execution_conversion_efficiency, 6),
            "execution_win_rate": round(float(payload.get("execution_win_rate") or 0.0), 6),
            "avg_win_loss_ratio": round(float(payload.get("avg_win_loss_ratio") or 0.0), 6),
            "realized_pnl_total": round(float(payload.get("realized_pnl_total") or 0.0), 4),
            "audit_ready_for_hard_gate": gate_status == "passed",
            "bootstrap_gate_ready": gate_status in {"bootstrap_ready", "passed"},
            "execution_audit_gate_status": gate_status,
            "execution_audit_gate_reasons": gate_reasons,
            "hard_gate_metric_passes": metric_passes,
            "hard_gate_metrics": hard_gate_metrics,
            "bootstrap_trade_floor": int(hard_gate_metrics.get("bootstrap_trade_floor") or 0),
            "required_trade_count": int(hard_gate_metrics.get("required_trade_count") or 20),
        }

    async def get_execution_audit_verification(self, strategy_id: Optional[str] = None) -> dict:
        strategy_filter = _string(strategy_id) or None
        async with self.acquire() as conn:
            async def _table_present(table_name: str) -> bool:
                return bool(
                    await conn.fetchval(
                        "SELECT EXISTS (SELECT 1 FROM sqlite_master WHERE type IN ('table', 'view') AND name = $1)",
                        table_name,
                    )
                )

            async def _column_present(table_name: str, column_name: str) -> bool:
                return bool(
                    await conn.fetchval(
                        """
                        SELECT EXISTS (
                            SELECT 1
                            FROM pragma_table_info($1)
                            WHERE name = $2
                        )
                        """,
                        table_name,
                        column_name,
                    )
                )

            async def _count_rows(table_name: str, *, column_name: Optional[str] = None) -> int:
                where_clause = "WHERE ($1 IS NULL OR strategy_id = $1)"
                if column_name:
                    where_clause += f" AND NULLIF(TRIM(COALESCE({column_name}, '')), '') IS NOT NULL"
                row = await conn.fetchrow(
                    f"""
                    SELECT COALESCE(COUNT(*), 0) AS count
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
            signal_evidence_claim_count = 0
            signal_evidence_backfilled_count = 0
            signal_evidence_backfilled_signal_count = 0
            signal_evidence_compile_stable_count = 0
            signal_evidence_compile_stable_signal_count = 0
            signal_evidence_proxy_only_count = 0
            if table_presence["strategy_signal_evidence"]:
                row = await conn.fetchrow(
                    """
                    SELECT
                        COALESCE(
                            COUNT(*) FILTER (
                                WHERE NULLIF(TRIM(COALESCE(applied_claim_id, '')), '') IS NOT NULL
                            ),
                            0
                        ) AS claim_count,
                        COALESCE(
                            COUNT(*) FILTER (
                                WHERE COALESCE(source_type, '') = 'paper_execution_backfill'
                                   OR COALESCE(json_extract(payload, '$.backfill_mode'), '') = 'paper_execution_native_backfill_v1'
                            ),
                            0
                        ) AS backfilled_count,
                        COALESCE(
                            COUNT(DISTINCT signal_id) FILTER (
                                WHERE COALESCE(source_type, '') = 'paper_execution_backfill'
                                   OR COALESCE(json_extract(payload, '$.backfill_mode'), '') = 'paper_execution_native_backfill_v1'
                            ),
                            0
                        ) AS backfilled_signal_count,
                        COALESCE(
                            COUNT(*) FILTER (
                                WHERE NOT (
                                    COALESCE(source_type, '') = 'paper_execution_backfill'
                                    OR COALESCE(json_extract(payload, '$.backfill_mode'), '') = 'paper_execution_native_backfill_v1'
                                )
                            ),
                            0
                        ) AS compile_stable_count,
                        COALESCE(
                            COUNT(DISTINCT signal_id) FILTER (
                                WHERE NOT (
                                    COALESCE(source_type, '') = 'paper_execution_backfill'
                                    OR COALESCE(json_extract(payload, '$.backfill_mode'), '') = 'paper_execution_native_backfill_v1'
                                )
                            ),
                            0
                        ) AS compile_stable_signal_count,
                        COALESCE(
                            COUNT(*) FILTER (WHERE COALESCE(proxy_only, FALSE)),
                            0
                        ) AS proxy_only_count
                    FROM strategy_signal_evidence
                    WHERE ($1 IS NULL OR strategy_id = $1)
                    """,
                    strategy_filter,
                )
                row_payload = dict(row or {})
                signal_evidence_claim_count = int(row_payload.get("claim_count") or 0)
                signal_evidence_backfilled_count = int(
                    row_payload.get("backfilled_count") or 0
                )
                signal_evidence_backfilled_signal_count = int(
                    row_payload.get("backfilled_signal_count") or 0
                )
                signal_evidence_compile_stable_count = int(
                    row_payload.get("compile_stable_count") or 0
                )
                signal_evidence_compile_stable_signal_count = int(
                    row_payload.get("compile_stable_signal_count") or 0
                )
                signal_evidence_proxy_only_count = int(
                    row_payload.get("proxy_only_count") or 0
                )
            legacy_evidence_count = 0
            legacy_table_present = await _table_present("strategy_factory_task_evidence")
            if legacy_table_present and strategy_filter:
                row = await conn.fetchrow(
                    """
                    SELECT COALESCE(COUNT(*), 0) AS count
                    FROM strategy_factory_task_evidence
                    WHERE COALESCE(json_extract(evidence_payload, '$.strategy_id'), '') = $1
                    """,
                    strategy_filter,
                )
                legacy_evidence_count = int(dict(row or {}).get("count") or 0)
            position_count = 0
            position_status_counts: dict[str, int] = {}
            if table_presence["strategy_trade_positions"]:
                row = await conn.fetchrow(
                    """
                    SELECT COALESCE(COUNT(*), 0) AS count
                    FROM strategy_trade_positions
                    WHERE ($1 IS NULL OR strategy_id = $1)
                    """,
                    strategy_filter,
                )
                position_count = int(dict(row or {}).get("count") or 0)
                status_rows = await conn.fetch(
                    """
                    SELECT COALESCE(status, 'unknown') AS status, COUNT(*) AS count
                    FROM strategy_trade_positions
                    WHERE ($1 IS NULL OR strategy_id = $1)
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
        semantic_contract = (
            self._execution_lineage_semantic_contract_status(
                await self.get_strategy(strategy_filter)
            )
            if strategy_filter
            else None
        )

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
        lineage_status = "missing"
        if signal_evidence_trade_step_count > 0:
            lineage_status = (
                "native_compile_stable"
                if signal_evidence_compile_stable_signal_count > 0
                else "native_backfilled"
                if signal_evidence_backfilled_signal_count > 0
                else "native_ready"
            )
        elif signal_evidence_count > 0:
            lineage_status = "native_unmapped"
        elif candidate_evidence_count > 0:
            lineage_status = "candidate_only"
        elif legacy_evidence_count > 0:
            lineage_status = "legacy_only"

        if lineage_status == "native_backfilled":
            recommendations.append(
                "native lineage currently depends on paper_execution backfill; run strategy_recompile_backfill for compile-stable claim/trade-step mapping"
            )
        elif lineage_status == "native_unmapped":
            recommendations.append(
                "strategy_signal_evidence exists without trade-step lineage; repair claim_to_trade_plan_map/trade_plan_to_dsl_map and rerun native evidence backfill"
            )
        elif lineage_status in {"missing", "legacy_only", "candidate_only"} and strategy_filter:
            recommendations.append(
                "backfill strategy_signal_evidence from paper execution lineage, then re-run execution_audit_acceptance"
            )
        if semantic_contract and semantic_contract.get("missing_fields"):
            recommendations.append(
                "compile-stable semantic contract fields are incomplete: "
                + ", ".join(list(semantic_contract.get("missing_fields") or []))
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

        verification_result = {
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
                "strategy_signal_claim_lineage_count": signal_evidence_claim_count,
                "strategy_signal_backfilled_count": signal_evidence_backfilled_count,
                "strategy_signal_backfilled_signal_count": signal_evidence_backfilled_signal_count,
                "strategy_signal_compile_stable_count": signal_evidence_compile_stable_count,
                "strategy_signal_compile_stable_signal_count": signal_evidence_compile_stable_signal_count,
                "strategy_signal_proxy_only_count": signal_evidence_proxy_only_count,
                "runtime_action_signal_count": runtime_action_signal_count,
            },
            "lineage_source": {
                "status": lineage_status,
                "native_candidate_evidence_count": candidate_evidence_count,
                "native_signal_evidence_count": signal_evidence_count,
                "native_trade_step_lineage_count": signal_evidence_trade_step_count,
                "native_claim_lineage_count": signal_evidence_claim_count,
                "native_backfilled_count": signal_evidence_backfilled_count,
                "native_backfilled_signal_count": signal_evidence_backfilled_signal_count,
                "native_compile_stable_count": signal_evidence_compile_stable_count,
                "native_compile_stable_signal_count": signal_evidence_compile_stable_signal_count,
                "native_proxy_only_count": signal_evidence_proxy_only_count,
                "runtime_action_signal_count": runtime_action_signal_count,
                "legacy_evidence_count": legacy_evidence_count,
                "semantic_contract": semantic_contract,
            },
            "trade_round_trip": {
                "position_count": position_count,
                "fill_count": fill_count,
                "position_status_counts": position_status_counts,
                "audit_summary": audit_summary,
            },
            "recommendations": recommendations,
        }
        if strategy_filter and hasattr(self, "get_latest_execution_audit_snapshot"):
            snapshot = await self.get_latest_execution_audit_snapshot(strategy_filter)
            if hasattr(self, "upsert_execution_audit_snapshot"):
                try:
                    from akshare_mcp.services.strategy_lifecycle_shared.execution_audit_snapshot import (
                        build_execution_audit_snapshot_payload,
                    )

                    persisted_snapshot = await self.upsert_execution_audit_snapshot(
                        build_execution_audit_snapshot_payload(
                            strategy_id=strategy_filter,
                            verification=verification_result,
                            acceptance=dict((snapshot or {}).get("acceptance") or {}),
                            audit_summary=audit_summary,
                            verdict_status=_string(
                                dict(audit_summary or {}).get("execution_audit_gate_status")
                            ) or "missing",
                            verdict_reasons=list(
                                dict(audit_summary or {}).get("execution_audit_gate_reasons")
                                or []
                            ),
                            execution_hard_gate_passed=bool(
                                dict(audit_summary or {}).get("audit_ready_for_hard_gate")
                            ),
                            as_of=date.today().isoformat(),
                            factory_run_id=_string((snapshot or {}).get("factory_run_id")) or None,
                            correlation_id=_string((snapshot or {}).get("correlation_id"))
                            or strategy_filter,
                            trace_id=_string((snapshot or {}).get("trace_id")) or None,
                            submission_lane=_string((snapshot or {}).get("submission_lane"))
                            or None,
                            parent_task_run_id=_string(
                                (snapshot or {}).get("parent_task_run_id")
                            ) or None,
                            source_action="execution_audit_verification",
                            metadata={
                                "verification_status": status,
                                "recommendation_count": len(recommendations),
                                "lineage_status": lineage_status,
                            },
                        )
                    )
                    if persisted_snapshot:
                        snapshot = persisted_snapshot
                except Exception as exc:
                    logger.warning(
                        "execution audit verification snapshot persist failed for %s: %s",
                        strategy_filter,
                        exc,
                    )
            if snapshot:
                verification_result["snapshot"] = snapshot
                verification_result["as_of"] = snapshot.get("as_of")
                verification_result["correlation_id"] = snapshot.get("correlation_id")
                verification_result["factory_run_id"] = snapshot.get("factory_run_id")
                verification_result["execution_audit_gate_status"] = (
                    dict(snapshot.get("verdict") or {}).get("status")
                    or snapshot.get("verdict_status")
                )
                verification_result["execution_audit_gate_reasons"] = list(
                    dict(snapshot.get("verdict") or {}).get("reasons")
                    or snapshot.get("verdict_reasons")
                    or []
                )
                verification_result["execution_hard_gate_passed"] = bool(
                    dict(snapshot.get("verdict") or {}).get("hard_gate_passed")
                    if dict(snapshot.get("verdict") or {}).get("hard_gate_passed") is not None
                    else snapshot.get("execution_hard_gate_passed")
                )
        return verification_result

    def _decode_execution_audit_snapshot(self, row: dict) -> dict:
        result = dict(row)
        for key in (
            "verdict_reasons",
            "verification",
            "acceptance",
            "audit_summary",
            "snapshot",
            "metadata",
        ):
            default = [] if key == "verdict_reasons" else {}
            result[key] = self._decode_json_field(result.get(key), default)
        result["verdict"] = {
            "status": _string(result.get("verdict_status")) or "missing",
            "reasons": list(result.get("verdict_reasons") or []),
            "hard_gate_passed": bool(result.get("execution_hard_gate_passed")),
        }
        result["as_of"] = (
            result.get("as_of_date").isoformat()
            if isinstance(result.get("as_of_date"), date)
            else _string(result.get("as_of_date")) or None
        )
        return result

    def _coerce_optional_date(self, value):
        if isinstance(value, date):
            return value
        raw = _string(value)
        if not raw:
            return None
        try:
            return date.fromisoformat(raw[:10])
        except Exception:
            return None

    async def get_latest_execution_audit_snapshot(self, strategy_id: str) -> Optional[dict]:
        strategy_filter = _string(strategy_id)
        if not strategy_filter:
            return None
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT *
                FROM strategy_execution_audit_snapshots
                WHERE strategy_id = $1
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                strategy_filter,
            )
        if not row:
            return None
        return self._decode_execution_audit_snapshot(dict(row))

    async def upsert_execution_audit_snapshot(self, snapshot: dict) -> Optional[dict]:
        payload = dict(snapshot or {})
        strategy_id = _string(payload.get("strategy_id"))
        if not strategy_id:
            return None
        verdict = dict(payload.get("verdict") or {})
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO strategy_execution_audit_snapshots
                    (strategy_id, snapshot_id, as_of_date, source_run_id, factory_run_id, correlation_id, trace_id,
                     submission_lane, parent_task_run_id, source_action, verdict_status, verdict_reasons,
                     execution_hard_gate_passed, verification, acceptance, audit_summary, snapshot, metadata,
                     created_at, updated_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14,
                        $15, $16, $17, $18, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                ON CONFLICT (strategy_id) DO UPDATE SET
                    snapshot_id = EXCLUDED.snapshot_id,
                    as_of_date = EXCLUDED.as_of_date,
                    source_run_id = EXCLUDED.source_run_id,
                    factory_run_id = EXCLUDED.factory_run_id,
                    correlation_id = EXCLUDED.correlation_id,
                    trace_id = EXCLUDED.trace_id,
                    submission_lane = EXCLUDED.submission_lane,
                    parent_task_run_id = EXCLUDED.parent_task_run_id,
                    source_action = EXCLUDED.source_action,
                    verdict_status = EXCLUDED.verdict_status,
                    verdict_reasons = EXCLUDED.verdict_reasons,
                    execution_hard_gate_passed = EXCLUDED.execution_hard_gate_passed,
                    verification = EXCLUDED.verification,
                    acceptance = EXCLUDED.acceptance,
                    audit_summary = EXCLUDED.audit_summary,
                    snapshot = EXCLUDED.snapshot,
                    metadata = EXCLUDED.metadata,
                    updated_at = CURRENT_TIMESTAMP
                RETURNING *
                """,
                strategy_id,
                _string(payload.get("snapshot_id")) or f"eas_{strategy_id}",
                self._coerce_optional_date(payload.get("as_of")),
                payload.get("source_run_id"),
                payload.get("factory_run_id"),
                payload.get("correlation_id"),
                payload.get("trace_id"),
                payload.get("submission_lane"),
                payload.get("parent_task_run_id"),
                payload.get("source_action"),
                _string(verdict.get("status") or payload.get("verdict_status")) or "missing",
                json.dumps(
                    list(verdict.get("reasons") or payload.get("verdict_reasons") or []),
                    ensure_ascii=False,
                    default=str,
                ),
                bool(
                    verdict.get("hard_gate_passed")
                    if verdict.get("hard_gate_passed") is not None
                    else payload.get("execution_hard_gate_passed")
                ),
                json.dumps(payload.get("verification") or {}, ensure_ascii=False, default=str),
                json.dumps(payload.get("acceptance") or {}, ensure_ascii=False, default=str),
                json.dumps(payload.get("audit_summary") or {}, ensure_ascii=False, default=str),
                json.dumps(payload.get("snapshot") or {}, ensure_ascii=False, default=str),
                json.dumps(payload.get("metadata") or {}, ensure_ascii=False, default=str),
            )
        if not row:
            return None
        return self._decode_execution_audit_snapshot(dict(row))

    def _decode_strategy_closure_snapshot(self, row: dict) -> dict:
        result = dict(row or {})
        for key in ("snapshot", "metadata"):
            result[key] = self._decode_json_field(result.get(key), {})
        result["as_of"] = (
            result.get("as_of_date").isoformat()
            if isinstance(result.get("as_of_date"), date)
            else _string(result.get("as_of_date")) or None
        )
        return result

    async def get_latest_strategy_closure_snapshot(
        self,
        strategy_id: str,
        snapshot_type: str = "incubation_overview",
    ) -> Optional[dict]:
        strategy_filter = _string(strategy_id)
        snapshot_type_filter = _string(snapshot_type) or "incubation_overview"
        if not strategy_filter:
            return None
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT *
                FROM strategy_closure_snapshots
                WHERE strategy_id = $1
                  AND snapshot_type = $2
                ORDER BY as_of_date DESC NULLS LAST, updated_at DESC
                LIMIT 1
                """,
                strategy_filter,
                snapshot_type_filter,
            )
        if not row:
            return None
        return self._decode_strategy_closure_snapshot(dict(row))

    async def upsert_strategy_closure_snapshot(self, snapshot: dict) -> Optional[dict]:
        payload = dict(snapshot or {})
        strategy_id = _string(payload.get("strategy_id"))
        snapshot_type = _string(payload.get("snapshot_type")) or "incubation_overview"
        if not strategy_id:
            return None
        snapshot_id = _string(payload.get("snapshot_id")) or f"cls_{strategy_id}_{snapshot_type}"
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO strategy_closure_snapshots
                    (strategy_id, snapshot_type, snapshot_id, as_of_date, source_run_id, factory_run_id,
                     correlation_id, trace_id, submission_lane, parent_task_run_id, source_action,
                     snapshot, metadata, created_at, updated_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                ON CONFLICT (strategy_id, snapshot_type) DO UPDATE SET
                    snapshot_id = EXCLUDED.snapshot_id,
                    as_of_date = EXCLUDED.as_of_date,
                    source_run_id = EXCLUDED.source_run_id,
                    factory_run_id = EXCLUDED.factory_run_id,
                    correlation_id = EXCLUDED.correlation_id,
                    trace_id = EXCLUDED.trace_id,
                    submission_lane = EXCLUDED.submission_lane,
                    parent_task_run_id = EXCLUDED.parent_task_run_id,
                    source_action = EXCLUDED.source_action,
                    snapshot = EXCLUDED.snapshot,
                    metadata = EXCLUDED.metadata,
                    updated_at = CURRENT_TIMESTAMP
                RETURNING *
                """,
                strategy_id,
                snapshot_type,
                snapshot_id,
                self._coerce_optional_date(payload.get("as_of")),
                payload.get("source_run_id"),
                payload.get("factory_run_id"),
                payload.get("correlation_id"),
                payload.get("trace_id"),
                payload.get("submission_lane"),
                payload.get("parent_task_run_id"),
                payload.get("source_action"),
                json.dumps(payload.get("snapshot") or {}, ensure_ascii=False, default=str),
                json.dumps(payload.get("metadata") or {}, ensure_ascii=False, default=str),
            )
        if not row:
            return None
        return self._decode_strategy_closure_snapshot(dict(row))

    async def run_execution_audit_acceptance(
        self,
        strategy_id: Optional[str] = None,
        *,
        backfill: bool = True,
    ) -> dict:
        strategy_filter = str(strategy_id or "").strip() or None
        backfill_result = None
        if backfill:
            backfill_result = {}
            if hasattr(self, "backfill_trade_position_links"):
                backfill_result["trade_position_links"] = await self.backfill_trade_position_links(
                    strategy_filter
                )
            if hasattr(self, "backfill_strategy_signal_evidence_native"):
                backfill_result["native_signal_evidence"] = await self.backfill_strategy_signal_evidence_native(
                    strategy_filter
                )

        verification = await self.get_execution_audit_verification(strategy_filter)
        coverage = dict(verification.get("coverage") or {})
        orders = dict(coverage.get("paper_orders") or {})
        trades = dict(coverage.get("paper_trades") or {})
        lineage_source = dict(verification.get("lineage_source") or {})
        round_trip = dict(verification.get("trade_round_trip") or {})
        audit_summary = dict(round_trip.get("audit_summary") or {})

        def _is_full_ratio(value) -> bool:
            try:
                return float(value) >= 0.999999
            except Exception:
                return False

        realized_trade_count = int(audit_summary.get("realized_trade_count") or 0)
        incomplete_position_count = int(audit_summary.get("incomplete_position_count") or 0)
        acceptance_matrix = {
            "schema_ready": bool(
                dict(verification.get("schema") or {}).get("all_required_tables_present")
                and dict(verification.get("schema") or {}).get("all_required_columns_present")
            ),
            "migration_ready": bool(
                dict(verification.get("migrations") or {}).get("all_required_keys_applied")
            ),
            "orders_position_link_ready": int(orders.get("total") or 0) == 0 or _is_full_ratio(orders.get("position_id_ratio")),
            "trades_position_link_ready": int(trades.get("total") or 0) == 0 or _is_full_ratio(trades.get("position_id_ratio")),
            "native_lineage_ready": str(lineage_source.get("status") or "") in {
                "native_ready",
                "native_compile_stable",
                "native_backfilled",
            },
            "fill_round_trip_ready": int(round_trip.get("fill_count") or 0) >= int(round_trip.get("position_count") or 0),
            "bootstrap_gate_ready": bool(audit_summary.get("bootstrap_gate_ready")),
            "hard_gate_ready": bool(audit_summary.get("audit_ready_for_hard_gate")),
            "trade_evidence_ready": realized_trade_count > 0 and incomplete_position_count == 0,
        }
        acceptance_matrix["overall_ready"] = all(
            acceptance_matrix[key]
            for key in (
                "schema_ready",
                "migration_ready",
                "orders_position_link_ready",
                "trades_position_link_ready",
                "native_lineage_ready",
                "fill_round_trip_ready",
                "hard_gate_ready",
                "trade_evidence_ready",
            )
        )

        blockers = []
        if not acceptance_matrix["schema_ready"]:
            blockers.append("execution_audit_schema_incomplete")
        if not acceptance_matrix["migration_ready"]:
            blockers.append("execution_audit_migrations_unverified")
        if not acceptance_matrix["orders_position_link_ready"]:
            blockers.append("paper_orders_position_link_incomplete")
        if not acceptance_matrix["trades_position_link_ready"]:
            blockers.append("paper_trades_position_link_incomplete")
        if not acceptance_matrix["native_lineage_ready"]:
            blockers.append("native_signal_evidence_lineage_missing")
        if not acceptance_matrix["fill_round_trip_ready"]:
            blockers.append("trade_position_fill_round_trip_incomplete")
        if not acceptance_matrix["trade_evidence_ready"]:
            blockers.append("realized_trade_evidence_insufficient")
        if not acceptance_matrix["hard_gate_ready"]:
            gate_status = str(audit_summary.get("execution_audit_gate_status") or "execution_audit_gate_not_passed")
            blockers.append("promotion_hard_gate_pending" if gate_status == "bootstrap_ready" else gate_status)

        status = (
            "ready"
            if acceptance_matrix["overall_ready"]
            else "pending_data"
            if realized_trade_count <= 0 and not blockers[:1] == ["execution_audit_schema_incomplete"]
            else "needs_attention"
        )
        recommendations = list(verification.get("recommendations") or [])
        if not acceptance_matrix["overall_ready"] and "run execution_audit_acceptance after production backfill" not in recommendations:
            recommendations.append("run execution_audit_acceptance after production backfill")
        blocker_details = self._build_execution_audit_blocker_details(
            verification=verification,
            acceptance_matrix=acceptance_matrix,
            audit_summary=audit_summary,
        )
        actionable_todos = list(
            dict.fromkeys(
                item.get("todo")
                for item in blocker_details
                if _string(item.get("todo"))
            )
        )
        gap_categories = sorted(
            {
                _string(item.get("category"))
                for item in blocker_details
                if _string(item.get("category"))
            }
        )
        result = {
            "status": status,
            "strategy_id": strategy_filter,
            "method": "execution_audit_acceptance_v1",
            "backfill_executed": bool(backfill),
            "backfill_result": backfill_result,
            "acceptance_matrix": acceptance_matrix,
            "blockers": blockers,
            "blocker_details": blocker_details,
            "gap_categories": gap_categories,
            "actionable_todos": actionable_todos,
            "verification": verification,
            "trade_audit_summary": audit_summary or None,
            "recommendations": recommendations,
            "execution_audit_gate_status": _string(
                audit_summary.get("execution_audit_gate_status")
            )
            or None,
            "execution_audit_gate_reasons": list(
                audit_summary.get("execution_audit_gate_reasons") or []
            ),
            "execution_hard_gate_passed": bool(
                audit_summary.get("audit_ready_for_hard_gate")
            ),
        }
        if strategy_filter and hasattr(self, "upsert_execution_audit_snapshot"):
            try:
                from akshare_mcp.services.strategy_lifecycle_shared.execution_audit_snapshot import (
                    build_execution_audit_snapshot_payload,
                    with_execution_audit_snapshot_metadata,
                )

                snapshot = await self.upsert_execution_audit_snapshot(
                    build_execution_audit_snapshot_payload(
                        strategy_id=strategy_filter,
                        verification=verification,
                        acceptance=result,
                        audit_summary=audit_summary,
                        verdict_status=_string(audit_summary.get("execution_audit_gate_status")) or "missing",
                        verdict_reasons=list(audit_summary.get("execution_audit_gate_reasons") or []),
                        execution_hard_gate_passed=bool(
                            audit_summary.get("audit_ready_for_hard_gate")
                        ),
                        as_of=date.today().isoformat(),
                        correlation_id=_string(strategy_filter),
                        source_action="execution_audit_acceptance",
                        metadata={
                            "acceptance_status": status,
                            "backfill_executed": bool(backfill),
                            "gap_categories": list(gap_categories),
                        },
                    )
                )
            except Exception as exc:
                logger.warning(
                    "execution audit acceptance snapshot persist failed for %s: %s",
                    strategy_filter,
                    exc,
                )
                snapshot = None
            if snapshot:
                result["snapshot"] = snapshot
                result["as_of"] = snapshot.get("as_of")
                result["correlation_id"] = snapshot.get("correlation_id")
                result["factory_run_id"] = snapshot.get("factory_run_id")
                result = with_execution_audit_snapshot_metadata(
                    result,
                    snapshot=snapshot,
                )
        return result

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
