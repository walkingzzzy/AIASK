

def _build_generation_lane_quality_panel(records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    buckets: dict[str, dict[str, Any]] = {}
    generator_mode_counts: dict[str, int] = {}
    for record in list(records or []):
        payload = dict(record or {})
        lane = _extract_generation_lane(payload)
        lane_key = lane["lane_key"]
        generator_mode = lane["generator_mode"]
        generator_mode_counts[generator_mode] = generator_mode_counts.get(generator_mode, 0) + 1
        bucket = buckets.setdefault(
            lane_key,
            {
                "lane_key": lane_key,
                "lane_label": lane["lane_label"],
                "generation_tier": lane["generation_tier"],
                "strategy_count": 0,
                "status_counts": {},
                "generator_mode_counts": {},
                "strategy_family_counts": {},
                "raw_validation_grade_distribution": {},
                "effective_validation_grade_distribution": {},
                "raw_validation_total_scores": [],
                "strict_incubation_ready_count": 0,
                "live_candidate_ready_count": 0,
                "promotion_ready_count": 0,
                "quality_passed_count": 0,
                "raw_b_or_above_count": 0,
                "strict_ready_given_raw_b_count": 0,
                "live_ready_given_raw_b_count": 0,
            },
        )
        bucket["strategy_count"] += 1
        bucket["generator_mode_counts"][generator_mode] = (
            bucket["generator_mode_counts"].get(generator_mode, 0) + 1
        )

        status_key = normalize_status_alias(payload.get("status"))
        if status_key:
            bucket["status_counts"][status_key] = bucket["status_counts"].get(status_key, 0) + 1

        family = str(
            payload.get("candidate_family")
            or payload.get("strategy_type")
            or "unknown"
        ).strip().lower() or "unknown"
        bucket["strategy_family_counts"][family] = (
            bucket["strategy_family_counts"].get(family, 0) + 1
        )

        raw_grade = str(
            payload.get("raw_validation_grade")
            or payload.get("validation_grade")
            or ""
        ).strip().upper()
        effective_grade = str(
            payload.get("effective_validation_grade")
            or payload.get("validation_grade")
            or ""
        ).strip().upper()
        if raw_grade:
            bucket["raw_validation_grade_distribution"][raw_grade] = (
                bucket["raw_validation_grade_distribution"].get(raw_grade, 0) + 1
            )
        if effective_grade:
            bucket["effective_validation_grade_distribution"][effective_grade] = (
                bucket["effective_validation_grade_distribution"].get(effective_grade, 0) + 1
            )
        if payload.get("raw_validation_total_score") is not None:
            bucket["raw_validation_total_scores"].append(
                _safe_float(payload.get("raw_validation_total_score"))
            )

        strict_ready = payload.get("strict_incubation_ready") is True
        live_ready = payload.get("live_candidate_ready") is True
        if strict_ready:
            bucket["strict_incubation_ready_count"] += 1
        if live_ready:
            bucket["live_candidate_ready_count"] += 1
        if payload.get("promotion_ready"):
            bucket["promotion_ready_count"] += 1
        if payload.get("quality_passed"):
            bucket["quality_passed_count"] += 1
        if _is_raw_b_or_above(raw_grade):
            bucket["raw_b_or_above_count"] += 1
            if strict_ready:
                bucket["strict_ready_given_raw_b_count"] += 1
            if live_ready:
                bucket["live_ready_given_raw_b_count"] += 1

    panel: list[dict[str, Any]] = []
    for bucket in buckets.values():
        strategy_count = int(bucket.get("strategy_count") or 0)
        raw_distribution = dict(bucket.get("raw_validation_grade_distribution") or {})
        raw_scores = list(bucket.get("raw_validation_total_scores") or [])
        raw_b_or_above_count = int(bucket.get("raw_b_or_above_count") or 0)
        panel.append(
            {
                "lane_key": bucket.get("lane_key"),
                "lane_label": bucket.get("lane_label"),
                "generation_tier": bucket.get("generation_tier"),
                "strategy_count": strategy_count,
                "status_counts": dict(bucket.get("status_counts") or {}),
                "generator_mode_counts": dict(bucket.get("generator_mode_counts") or {}),
                "strategy_family_counts": dict(bucket.get("strategy_family_counts") or {}),
                "raw_validation_grade_distribution": raw_distribution,
                "effective_validation_grade_distribution": dict(
                    bucket.get("effective_validation_grade_distribution") or {}
                ),
                "raw_validation_total_score_mean": round(
                    sum(raw_scores) / len(raw_scores),
                    4,
                ) if raw_scores else 0.0,
                **_grade_rates(raw_distribution, strategy_count),
                "strict_incubation_ready_count": int(
                    bucket.get("strict_incubation_ready_count") or 0
                ),
                "strict_incubation_ready_rate": _rate(
                    int(bucket.get("strict_incubation_ready_count") or 0),
                    strategy_count,
                ),
                "live_candidate_ready_count": int(
                    bucket.get("live_candidate_ready_count") or 0
                ),
                "live_candidate_ready_rate": _rate(
                    int(bucket.get("live_candidate_ready_count") or 0),
                    strategy_count,
                ),
                "promotion_ready_count": int(bucket.get("promotion_ready_count") or 0),
                "promotion_ready_rate": _rate(
                    int(bucket.get("promotion_ready_count") or 0),
                    strategy_count,
                ),
                "quality_passed_count": int(bucket.get("quality_passed_count") or 0),
                "quality_pass_rate": _rate(
                    int(bucket.get("quality_passed_count") or 0),
                    strategy_count,
                ),
                "raw_b_or_above_count": raw_b_or_above_count,
                "raw_b_or_above_rate": _rate(raw_b_or_above_count, strategy_count),
                "strict_ready_given_raw_b_count": int(
                    bucket.get("strict_ready_given_raw_b_count") or 0
                ),
                "strict_ready_given_raw_b_rate": _rate(
                    int(bucket.get("strict_ready_given_raw_b_count") or 0),
                    raw_b_or_above_count,
                ),
                "live_ready_given_raw_b_count": int(
                    bucket.get("live_ready_given_raw_b_count") or 0
                ),
                "live_ready_given_raw_b_rate": _rate(
                    int(bucket.get("live_ready_given_raw_b_count") or 0),
                    raw_b_or_above_count,
                ),
            }
        )
    panel.sort(
        key=lambda item: (
            _FACTORY_GENERATION_LANE_SORT_ORDER.get(
                str(item.get("lane_key") or ""),
                _FACTORY_GENERATION_LANE_SORT_ORDER["unknown"],
            ),
            -int(item.get("strategy_count") or 0),
            str(item.get("lane_label") or ""),
        )
    )
    return panel, generator_mode_counts


# ── NAV calculation ──────────────────────────────────────────────────────────

async def compute_nav_series(db, strategy_id: str, max_points: int = 30) -> list:
    """Return paper-trading NAV; fall back to signal_forward_returns derived NAV."""
    try:
        if hasattr(db, "get_paper_account_by_strategy") and hasattr(db, "get_paper_nav_rows"):
            account = await db.get_paper_account_by_strategy(strategy_id)
            if account:
                nav_rows = await db.get_paper_nav_rows(account["id"], limit=max(max_points * 4, 60))
                if nav_rows:
                    nav = [
                        round(
                            float(row.get("total_value") or 0.0)
                            / max(float(account.get("initial_capital") or 1.0), 1.0),
                            4,
                        )
                        for row in reversed(nav_rows)
                    ]
                    if len(nav) > max_points:
                        step = max(1, len(nav) // max_points)
                        nav = nav[::step][:max_points]
                    return nav
        async with db.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT ss.signal_date, ss.signal, sfr.actual_return
                FROM strategy_signals ss
                JOIN signal_forward_returns sfr ON sfr.signal_id = ss.id AND sfr.forward_days = 5
                WHERE ss.strategy_id = $1 AND ss.signal != 0
                ORDER BY ss.signal_date
                """,
                strategy_id,
            )
        if not rows:
            return []
        daily: dict = {}
        for r in rows:
            d = r["signal_date"]
            ret = float(r["actual_return"] or 0) * (1 if r["signal"] == 1 else -1)
            daily.setdefault(d, []).append(ret)
        nav = [1.0]
        for d in sorted(daily):
            avg = sum(daily[d]) / len(daily[d])
            nav.append(round(nav[-1] * (1 + avg), 4))
        if len(nav) > max_points:
            step = max(1, len(nav) // max_points)
            nav = nav[::step][:max_points]
        return nav
    except Exception:
        return []


# ── Lifecycle state management (imported from strategy_lifecycle_shared) ─────


# ── Quality report helpers ───────────────────────────────────────────────────

async def save_quality_report(db, strategy_id: str, report: dict, report_type: str = "submission") -> None:
    if hasattr(db, "save_strategy_quality_report"):
        await db.save_strategy_quality_report(strategy_id, report_type, report)


def is_factory_generated_strategy(strategy: Optional[dict]) -> bool:
    payload = dict(strategy or {})
    tags = {str(tag or "").strip().lower() for tag in list(payload.get("tags") or [])}
    author_id = str(payload.get("author_id") or "").strip().lower()
    source = str(payload.get("source") or "").strip().lower()
    if "factory" in tags or "auto_generated" in tags:
        return True
    if author_id == "strategy_factory":
        return True
    return source.startswith("strategy_factory")
