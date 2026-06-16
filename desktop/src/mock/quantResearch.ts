export function mockQuantPresets(database: unknown) {
  return {
    object: "aiask.quant_presets",
    data_status: { status: "ready", database },
    templates: [{ id: "mock", label: "Mock", universe: ["600519", "000001"], benchmark: "000300", factors: ["momentum", "volatility"], rebalance_frequency: "monthly", cost_bps: 3, slippage_bps: 1 }],
    factor_library: ["momentum", "volatility", "value"],
    risk_defaults: { max_weight: 0.35 },
    disclaimer: "MOCK_NOT_INVESTMENT_ADVICE"
  };
}

export function mockQuantResearchArtifact(researchId = "research_mock") {
  const stages = [
    { name: "definition", status: "completed", output: { universe: ["600519", "000001"], factors: ["momentum", "volatility"], benchmark: "000300" }, error: null },
    { name: "data_gate", status: "completed", output: { status: "ready", ready: true, missing: [], stale: [], coverage: { requested: 2, ready: 2 } }, error: null },
    { name: "factor_validation", status: "completed", output: { status: "passed", ic_mean: 0.041, coverage: 0.92, redundant_factors: [] }, error: null },
    { name: "backtest_suite", status: "completed", output: { status: "completed", oos_sharpe: 1.12, max_drawdown: -0.082, turnover: 0.18 }, error: null },
    { name: "portfolio_risk", status: "completed", output: { status: "completed", var_95: -0.021, concentration: "medium", stress: "passed" }, error: null },
    { name: "strategy_factory_review", status: "completed", output: { status: "reviewing", recommendation: "observe", decision: "not_promoted" }, error: null }
  ];
  return {
    research_id: researchId,
    status: "completed",
    payload: { stages },
    report: {
      object: "aiask.quant_research_report",
      research_id: researchId,
      status: "completed",
      summary: { benchmark: "000300", universe_size: 2, factor_count: 2, failed_stage: null },
      universe: ["600519", "000001"],
      backtest_assumptions: { cost_bps: 3, slippage_bps: 1, benchmark: "000300", rebalance_frequency: "monthly" },
      backtest: { oos_sharpe: 1.12, walk_forward_score: 0.68, max_drawdown: -0.082 },
      portfolio_risk: { var_95: -0.021, concentration: "medium", stress: "passed" },
      strategy_factory: { status: "reviewing", recommendation: "observe", decision: "not_promoted" },
      limitations: ["Mock research is decision support only."],
      stages,
      disclaimer: "MOCK_NOT_INVESTMENT_ADVICE"
    }
  };
}
