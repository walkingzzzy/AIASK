type TradePredictionOutcomeFixture = {
  outcome_id: string;
  prediction_id: string;
  strategy_id: string;
  stock_code: string;
  actual_trading_date: string;
  score_version: string;
  score_status: string;
  data_quality_status: string;
  trade_prediction_score: number;
  outcome_json: Record<string, unknown>;
  metadata: Record<string, unknown>;
  calculated_at: string;
};

export const tradePredictionOutcomesFixture: TradePredictionOutcomeFixture[] = [
  {
    outcome_id: "tpo_e2e_001",
    prediction_id: "tp_e2e_001",
    strategy_id: "strategy_e2e_momentum",
    stock_code: "600519",
    actual_trading_date: "2026-06-04",
    score_version: "trade_prediction_score_v2",
    score_status: "ok",
    data_quality_status: "ok",
    trade_prediction_score: 0.82,
    outcome_json: { direction_hit: true, target_touch: true, planned_trade_return: 0.034 },
    metadata: { family: "momentum", stage: "candidate", regime: "bull", event: "policy_shock", factor: "momentum_20d" },
    calculated_at: "2026-06-04T07:15:00Z"
  },
  {
    outcome_id: "tpo_e2e_002",
    prediction_id: "tp_e2e_002",
    strategy_id: "strategy_e2e_reversal",
    stock_code: "000001",
    actual_trading_date: "2026-06-04",
    score_version: "trade_prediction_score_v2",
    score_status: "partial_intraday_missing",
    data_quality_status: "intraday_missing",
    trade_prediction_score: 0.51,
    outcome_json: { direction_hit: true, target_touch: false, planned_trade_return: 0.008 },
    metadata: { family: "mean_reversion", stage: "observe", regime: "range", event: "earnings", factor: "reversal_5d" },
    calculated_at: "2026-06-04T07:20:00Z"
  },
  {
    outcome_id: "tpo_e2e_003",
    prediction_id: "tp_e2e_003",
    strategy_id: "strategy_e2e_event",
    stock_code: "300750",
    actual_trading_date: "2026-06-03",
    score_version: "trade_prediction_score_v2",
    score_status: "insufficient_samples",
    data_quality_status: "partial_gap",
    trade_prediction_score: 0.38,
    outcome_json: { direction_hit: false, target_touch: false, planned_trade_return: -0.012 },
    metadata: { family: "event_driven", stage: "candidate", regime: "volatile", event: "policy_shock", factor: "event_strength" },
    calculated_at: "2026-06-03T07:18:00Z"
  }
];

export function queryRecord(query: URLSearchParams): Record<string, unknown> {
  const record: Record<string, unknown> = {};
  query.forEach((value, key) => {
    record[key] = value;
  });
  return record;
}

function safeLimit(value: unknown, fallback = 100): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? Math.max(1, Math.min(Math.trunc(parsed), 1000)) : fallback;
}

function matchesTradePredictionFilter(item: TradePredictionOutcomeFixture, filters: Record<string, unknown>, key: keyof TradePredictionOutcomeFixture): boolean {
  const value = filters[key];
  if (value === undefined || value === null || value === "") return true;
  return String(item[key] || "") === String(value);
}

function tradePredictionOutcomeItems(filters: Record<string, unknown> = {}) {
  const limit = safeLimit(filters.limit, 100);
  return tradePredictionOutcomesFixture
    .filter((item) =>
      (["prediction_id", "strategy_id", "stock_code", "score_version", "score_status", "data_quality_status"] as const).every((key) =>
        matchesTradePredictionFilter(item, filters, key)
      )
    )
    .slice(0, limit);
}

function countBy<T>(items: T[], valueFor: (item: T) => string): Record<string, number> {
  const counts: Record<string, number> = {};
  for (const item of items) {
    const value = valueFor(item);
    counts[value] = (counts[value] || 0) + 1;
  }
  return counts;
}

export function tradePredictionStatus(filters: Record<string, unknown> = {}) {
  const outcomes = tradePredictionOutcomeItems(filters);
  const scores = outcomes.map((outcome) => outcome.trade_prediction_score).filter((score) => Number.isFinite(score));
  const partialCount = outcomes.filter((outcome) => outcome.score_status !== "ok").length;
  const scoreDistribution = countBy(outcomes, (outcome) =>
    outcome.trade_prediction_score >= 0.8
      ? "0.80-1.00"
      : outcome.trade_prediction_score >= 0.6
        ? "0.60-0.79"
        : outcome.trade_prediction_score >= 0.4
          ? "0.40-0.59"
          : "0.00-0.39"
  );
  return {
    object: "trade_prediction.status",
    status: "ready",
    configured: true,
    generated_at: "2026-06-05T02:30:00Z",
    prediction_count: outcomes.length + 1,
    outcome_count: outcomes.length,
    sample_n: outcomes.length,
    pending_count: 1,
    evaluated_count: outcomes.length,
    partial_count: partialCount,
    prediction_status_counts: { frozen: outcomes.length, pending: 1 },
    score_status_counts: countBy(outcomes, (outcome) => outcome.score_status),
    latest_score_status_counts: countBy(outcomes, (outcome) => outcome.score_status),
    score_version_counts: countBy(outcomes, (outcome) => outcome.score_version),
    data_quality_status_counts: countBy(outcomes, (outcome) => outcome.data_quality_status),
    latest_data_quality_status_counts: countBy(outcomes, (outcome) => outcome.data_quality_status),
    score_distribution: scoreDistribution,
    score_summary: {
      avg: scores.length ? Number((scores.reduce((sum, score) => sum + score, 0) / scores.length).toFixed(6)) : null,
      min: scores.length ? Math.min(...scores) : null,
      max: scores.length ? Math.max(...scores) : null
    }
  };
}

export function tradePredictionOutcomes(filters: Record<string, unknown> = {}) {
  const items = tradePredictionOutcomeItems(filters);
  return {
    object: "trade_prediction.outcomes",
    status: "ready",
    configured: true,
    items,
    count: items.length
  };
}

export function tradePredictionMatrix(filters: Record<string, unknown> = {}) {
  const dimensions = String(filters.dimensions || "family,stage,regime,event,factor")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
  const rows = dimensions.flatMap((dimension) => {
    const grouped = new Map<string, TradePredictionOutcomeFixture[]>();
    for (const outcome of tradePredictionOutcomeItems(filters)) {
      const value = String(outcome.metadata[dimension] || "unknown");
      grouped.set(value, [...(grouped.get(value) || []), outcome]);
    }
    return Array.from(grouped.entries()).map(([value, outcomes]) => {
      const sampleN = outcomes.length;
      const scoreAvg = outcomes.reduce((sum, outcome) => sum + outcome.trade_prediction_score, 0) / sampleN;
      const scoreLcb = Math.max(0, scoreAvg - 1.96 * Math.sqrt((scoreAvg * (1 - scoreAvg)) / sampleN));
      return {
        dimension,
        value,
        sample_n: sampleN,
        score_avg: Number(scoreAvg.toFixed(6)),
        score_lcb_95: Number(scoreLcb.toFixed(6)),
        direction_hit_rate: Number((outcomes.filter((outcome) => outcome.outcome_json.direction_hit).length / sampleN).toFixed(6)),
        target_touch_rate: Number((outcomes.filter((outcome) => outcome.outcome_json.target_touch).length / sampleN).toFixed(6)),
        score_status_counts: countBy(outcomes, (outcome) => outcome.score_status),
        data_quality_status_counts: countBy(outcomes, (outcome) => outcome.data_quality_status)
      };
    });
  });
  return {
    object: "trade_prediction.matrix",
    status: "ready",
    configured: true,
    generated_at: "2026-06-05T02:30:00Z",
    score_version: filters.score_version ? String(filters.score_version) : null,
    dimensions,
    rows,
    row_count: rows.length
  };
}

export function tradePredictionEnvelope(data: unknown) {
  return { success: true, data, error: null, error_code: null };
}

