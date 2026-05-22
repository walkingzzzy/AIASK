
    def build_research_context(
        self,
        results: list[StrategyResult],
        *,
        top_rankings: dict[str, list[dict[str, Any]]],
    ) -> dict[str, Any]:
        strategy_blocks = []
        for result in results:
            strategy_blocks.append(
                {
                    "strategy_code": result.strategy_code,
                    "name": result.name,
                    "family": result.family,
                    "instrument_profile": deepcopy(result.candidate.get("instrument_profile") or {}),
                    "parameters": deepcopy(result.config),
                    "summary": deepcopy(result.summary),
                    "execution_assumptions": deepcopy(result.candidate.get("execution_assumptions") or {}),
                    "failure_mode": deepcopy((result.candidate.get("hypothesis_artifact") or {}).get("failure_mode") or {}),
                }
            )
        leaderboard = []
        for family, items in top_rankings.items():
            for rank, item in enumerate(items[:5], start=1):
                summary = dict(item["backtest"]["summary"] or {})
                leaderboard.append(
                    {
                        "family": family,
                        "rank": rank,
                        "strategy_code": item["config"].strategy_code,
                        "annualized_return": round(_safe_float(summary.get("annualized_return")), 6),
                        "post_cost_sharpe": round(_safe_float(summary.get("post_cost_sharpe")), 6),
                        "max_drawdown": round(_safe_float(summary.get("max_drawdown")), 6),
                        "trade_count": _safe_int(summary.get("trade_count")),
                        "alpha_decay": round(_safe_float(summary.get("alpha_decay")), 6),
                    }
                )
        generalization_seed = {
            "logic_abstraction": [
                "稳定 backwardation + 近端不出现极端升水时，远月 carry 与趋势延续可以共振。",
                "spread z-score 回落但曲线单调性未破坏时，买近抛远更适合作为主交易方向。",
                "容量评估必须把 far-month 流动性折扣、gross margin 与交割保护同时纳入。",
            ],
            "failure_modes": [
                "现货持续弱势导致近端异常升水，期限结构反转。",
                "极端行情下单边趋势主导，短 spread 方向风险急剧放大。",
                "远月流动性恶化使得成本和回撤同步恶化。",
            ],
        }
        return {
            "strategy_context": {
                "adapter_name": "futures_calendar_research_adapter",
                "underlying": "SC",
                "objective_profile": "high_precision",
                "trade_density_preference": "low",
                "data_path": str(self.data_path),
                "window": {"start": "2018-07-26", "end": "2025-02-19"},
                "memo_summary": self._memo_text[:800],
                "roll_rule_summary": self._notes_text[:500],
                "strategies": strategy_blocks,
            },
            "backtest_summary": {
                "leaderboard": leaderboard,
                "selection_rule": (
                    "先筛 annualized_return>10% 且 trade_count>=6；"
                    "若无候选达标，则回退为按 annualized_return / post_cost_sharpe / win_rate / drawdown / trade_count 选最优候选。"
                ),
            },
            "regime_panel": {
                result.strategy_code: deepcopy(result.regime_panel)
                for result in results
            },
            "capacity_panel": {
                result.strategy_code: deepcopy(result.capacity_panel)
                for result in results
            },
            "generalization_seed": generalization_seed,
        }

    @staticmethod
    def _generalization_report(enable_online_validation: bool) -> dict[str, Any]:
        rows: list[dict[str, Any]] = []
        history_lookup: dict[str, Any] = {}
        fee_lookup: dict[str, Any] = {}
        if enable_online_validation:
            # PR-DQ5: 不直接调用外部 API。期货手续费和历史数据应从本地缓存读取。
            # 当本地无缓存时优雅降级（空 dict），不阻塞流程。
            import logging as _logging
            _logging.getLogger(__name__).debug(
                "futures_calendar_research: online_validation requested but external API calls disabled per data quality policy"
            )
        for code, label in GENERALIZATION_UNDERLYINGS:
            history = history_lookup.get(code)
            fee_row = fee_lookup.get(code) or fee_lookup.get(f"{code}0") or {}
            history_ok = isinstance(history, pd.DataFrame) and not history.empty and len(history) >= 120
            fee_ok = bool(fee_row)
            validation_mode = (
                "light_online_validation"
                if enable_online_validation and history_ok
                else "candidate_generation_only"
            )
            rows.append(
                {
                    "underlying": code,
                    "name": label,
                    "validation_mode": validation_mode,
                    "history_available": bool(history_ok),
                    "fee_available": bool(fee_ok),
                    "light_logic_fit": "stable_curve_needed",
                    "notes": (
                        "在线历史与费用可用，保留为轻量验证种子。"
                        if validation_mode == "light_online_validation"
                        else "保留候选生成 + 轻量逻辑验证，不阻断 SC 主闭环。"
                    ),
                }
            )
        return {"rows": rows}

    async def _llm_optimize_candidates(
        self,
        *,
        research_context: dict[str, Any],
        baseline_candidates: list[dict[str, Any]],
    ) -> dict[str, Any]:
        try:
            from ...infrastructure.mcp_services import get_strategy_llm_provider_loader
            get_strategy_llm_provider = get_strategy_llm_provider_loader()
        except Exception as exc:
            return {
                "status": "provider_import_failed",
                "reason": str(exc),
                "candidates": baseline_candidates,
            }
        provider = get_strategy_llm_provider()
        if not provider.is_enabled():
            return {
                "status": "provider_disabled",
                "reason": "StrategyLLMProvider is not configured in the current environment.",
                "candidates": baseline_candidates,
            }
        task = {
            "task_id": "sc_calendar_llm_refine",
            "task_source": "snapshot",
            "opportunity_type": "futures_calendar_refine",
            "target_symbols": ["SC"],
            "preferred_strategy_types": ["dsl_rule", "open_dsl"],
            "allowed_strategy_types": ["dsl_rule", "open_dsl"],
            "validation_focus": "candidate_target_only",
        }
        llm_timeout_sec = min(max(_safe_float(getattr(provider.config, "connect_timeout_sec", 5.0), 5.0) + 2.0, 5.0), 8.0)
        try:
            provider_payload = await asyncio.wait_for(
                provider.generate_candidates(
                    snapshot={"underlying": "SC"},
                    market_frame=_to_ohlcv_projection(pd.Series(np.linspace(1.0, 2.0, 80))),
                    research_context=research_context,
                    parent_strategies=baseline_candidates,
                    history_summary=[],
                    research_task=task,
                    limit=2,
                ),
                timeout=llm_timeout_sec,
            )
        except asyncio.TimeoutError:
            return {
                "status": "provider_timeout",
                "reason": f"StrategyLLMProvider did not respond within {llm_timeout_sec:.1f}s; fallback to baseline candidates.",
                "candidates": baseline_candidates,
            }
        except Exception as exc:
            return {
                "status": "provider_failed",
                "reason": str(exc),
                "candidates": baseline_candidates,
            }
        candidates = list((provider_payload or {}).get("candidates") or [])
        return {
            "status": "provider_succeeded" if candidates else "provider_empty",
            "reason": None,
            "candidates": candidates or baseline_candidates,
            "provider_metrics": dict((provider_payload or {}).get("request_metrics") or {}),
        }

    def _write_reports(
        self,
        *,
        output_dir: Path,
        trend_result: StrategyResult,
        spread_result: StrategyResult,
        top_rankings: dict[str, list[dict[str, Any]]],
        research_context: dict[str, Any],
        llm_bundle: dict[str, Any],
        generalization_report: dict[str, Any],
    ) -> dict[str, str]:
        output_dir = _ensure_output_dir(output_dir)
        trend_summary = dict(trend_result.summary)
        spread_summary = dict(spread_result.summary)
        screen_pass_counts = {
            family: sum(
                1
                for item in items
                if _safe_float((item.get("backtest") or {}).get("summary", {}).get("annualized_return")) >= 0.10
                and _safe_int((item.get("backtest") or {}).get("summary", {}).get("trade_count")) >= 6
            )
            for family, items in top_rankings.items()
        }
        ranking_rows = []
        for family, items in top_rankings.items():
            for rank, item in enumerate(items[:5], start=1):
                summary = dict(item["backtest"]["summary"] or {})
                ranking_rows.append(
                    {
                        "family": family,
                        "rank": rank,
                        "strategy_code": item["config"].strategy_code,
                        "annualized_return": f"{_safe_float(summary.get('annualized_return')):.2%}",
                        "post_cost_sharpe": f"{_safe_float(summary.get('post_cost_sharpe')):.2f}",
                        "max_drawdown": f"{_safe_float(summary.get('max_drawdown')):.2%}",
                        "trade_count": _safe_int(summary.get("trade_count")),
                        "alpha_decay": f"{_safe_float(summary.get('alpha_decay')):.2f}",
                    }
                )
        ranking_table = _markdown_table(
            ranking_rows,
            [
                ("Family", "family"),
                ("Rank", "rank"),
                ("Code", "strategy_code"),
                ("Ann.Return", "annualized_return"),
                ("Post Sharpe", "post_cost_sharpe"),
                ("Max DD", "max_drawdown"),
                ("Trades", "trade_count"),
                ("Alpha Decay", "alpha_decay"),
            ],
        )
        full_report_md = "\n".join(
            [
                "# SC 原油跨月价差全量回测报告",
                "",
                f"- 数据源：`{self.data_path}`",
                "- 窗口：2018-07-26 至 2025-02-19",
                "- regime 口径：`spread_1_2 > 0 -> backwardation`，其余归入 `contango_or_flat`。",
                "- 交割保护：front roll 前 3 日禁止持仓。",
                "",
                "## 候选排序",
                ranking_table,
                "",
                "## 门槛筛选",
                f"- 趋势策略通过 `annualized_return>10% & trade_count>=6` 的候选数：{screen_pass_counts.get('trend', 0)}",
                f"- 套利策略通过 `annualized_return>10% & trade_count>=6` 的候选数：{screen_pass_counts.get('spread', 0)}",
                "- 若某一策略族无达标候选，本报告保留保守成本/容量假设下的最优备选，不强行把未达标结果包装成通过门槛。",
                "",
                "## 趋势策略冠军",
                f"- 名称：`{trend_result.name}`",
                f"- 年化：{_safe_float(trend_summary.get('annualized_return')):.2%}",
                f"- Post-cost Sharpe：{_safe_float(trend_summary.get('post_cost_sharpe')):.2f}",
                f"- 最大回撤：{_safe_float(trend_summary.get('max_drawdown')):.2%}",
                f"- 交易数：{_safe_int(trend_summary.get('trade_count'))}",
                "",
                "## 套利策略冠军",
                f"- 名称：`{spread_result.name}`",
                f"- 年化：{_safe_float(spread_summary.get('annualized_return')):.2%}",
                f"- Post-cost Sharpe：{_safe_float(spread_summary.get('post_cost_sharpe')):.2f}",
                f"- 最大回撤：{_safe_float(spread_summary.get('max_drawdown')):.2%}",
                f"- 交易数：{_safe_int(spread_summary.get('trade_count'))}",
                "",
                "## 研究上下文",
                f"- research_context blocks：{', '.join(research_context.keys())}",
                f"- LLM enrichment status：`{llm_bundle.get('status')}`",
                f"- LLM note：{llm_bundle.get('reason') or 'provider returned optimized candidates.'}",
                "",
            ]
        )
        full_report_path = output_dir / "sc_full_backtest_report.md"
        full_report_path.write_text(full_report_md, encoding="utf-8")

        stress_rows = []
        for strategy_label, result in (("trend", trend_result), ("spread", spread_result)):
            for item in result.capacity_panel:
                stress_rows.append({"strategy": strategy_label, **item})
        stress_frame = pd.DataFrame(stress_rows)
        stress_csv_path = output_dir / "sc_capacity_stress_matrix.csv"
        stress_frame.to_csv(stress_csv_path, index=False)
        stress_md_path = output_dir / "sc_capacity_stress_matrix.md"
        stress_md_path.write_text(
            "# SC 五档资金压力测试\n\n"
            + _markdown_table(
                stress_rows,
                [
                    ("Strategy", "strategy"),
                    ("Capital", "capital"),
                    ("Ann.Return", "annualized_return"),
                    ("Post Sharpe", "post_cost_sharpe"),
                    ("Max DD", "max_drawdown"),
                    ("Trades", "trade_count"),
                    ("Cap", "capacity_limit_contracts"),
                    ("Bind", "binding_constraint"),
                ],
            )
            + "\n",
            encoding="utf-8",
        )

        candidate_bundle = {
            "llm_status": llm_bundle.get("status"),
            "llm_reason": llm_bundle.get("reason"),
            "baseline_candidates": [trend_result.candidate, spread_result.candidate],
            "optimized_candidates": list(llm_bundle.get("candidates") or []),
            "compiled_dsl": {
                trend_result.strategy_code: trend_result.compiled_dsl,
                spread_result.strategy_code: spread_result.compiled_dsl,
            },
            "research_context": research_context,
        }
        candidate_json_path = output_dir / "sc_ai_candidate_bundle.json"
        candidate_json_path.write_text(
            json.dumps(candidate_bundle, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        candidate_md_path = output_dir / "sc_ai_candidate_bundle.md"
        candidate_md_path.write_text(
            "\n".join(
                [
                    "# SC AI Candidate Bundle",
                    "",
                    f"- LLM status: `{llm_bundle.get('status')}`",
                    f"- LLM note: {llm_bundle.get('reason') or 'provider returned optimized candidates.'}",
                    "",
                    "## Baseline Candidates",
                    f"- `{trend_result.name}` -> `{trend_result.strategy_code}`",
                    f"- `{spread_result.name}` -> `{spread_result.strategy_code}`",
                    "",
                    "## Research Context Blocks",
                    f"- {', '.join(research_context.keys())}",
                    "",
                ]
            ),
            encoding="utf-8",
        )

        generalization_md_path = output_dir / "cross_asset_candidate_validation.md"
        generalization_md_path.write_text(
            "# 跨品种候选验证报告\n\n"
            + _markdown_table(
                list(generalization_report.get("rows") or []),
                [
                    ("Underlying", "underlying"),
                    ("Name", "name"),
                    ("Mode", "validation_mode"),
                    ("History", "history_available"),
                    ("Fee", "fee_available"),
                    ("Notes", "notes"),
                ],
            )
            + "\n",
            encoding="utf-8",
        )

        research_payload_path = output_dir / "sc_research_context_payload.json"
        research_payload_path.write_text(
            json.dumps(research_context, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        return {
            "full_backtest_report_md": str(full_report_path),
            "capacity_stress_csv": str(stress_csv_path),
            "capacity_stress_md": str(stress_md_path),
            "candidate_bundle_json": str(candidate_json_path),
            "candidate_bundle_md": str(candidate_md_path),
            "cross_asset_validation_md": str(generalization_md_path),
            "research_context_json": str(research_payload_path),
        }

    async def run(
        self,
        *,
        enable_online_generalization: bool = False,
    ) -> dict[str, Any]:
        output_dir = _ensure_output_dir(self.output_dir)
        frame = self.add_features(self.load_curve_frame(self.data_path))
        trend_ranked = self._rank_results(self._run_trend_grid(frame, capital=1_000_000.0))
        spread_ranked = self._rank_results(self._run_spread_grid(frame, capital=1_000_000.0))
        trend_result = self._materialize_result(frame, family="trend", ranked_item=trend_ranked[0])
        spread_result = self._materialize_result(frame, family="spread", ranked_item=spread_ranked[0])
        research_context = self.build_research_context(
            [trend_result, spread_result],
            top_rankings={"trend": trend_ranked, "spread": spread_ranked},
        )
        llm_bundle = await self._llm_optimize_candidates(
            research_context=research_context,
            baseline_candidates=[trend_result.candidate, spread_result.candidate],
        )
        generalization_report = self._generalization_report(
            enable_online_validation=enable_online_generalization,
        )
        output_paths = self._write_reports(
            output_dir=output_dir,
            trend_result=trend_result,
            spread_result=spread_result,
            top_rankings={"trend": trend_ranked, "spread": spread_ranked},
            research_context=research_context,
            llm_bundle=llm_bundle,
            generalization_report=generalization_report,
        )
        return {
            "output_dir": str(output_dir),
            "trend": asdict(trend_result),
            "spread": asdict(spread_result),
            "research_context": research_context,
            "llm_bundle": llm_bundle,
            "generalization_report": generalization_report,
            "output_paths": output_paths,
        }
