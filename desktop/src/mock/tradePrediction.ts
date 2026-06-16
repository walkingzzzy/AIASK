const mockTradePredictionOutcomes = [
  {
    outcome_id: "tpo_mock_001",
    prediction_id: "tp_mock_001",
    strategy_id: "strategy_momentum_cn",
    stock_code: "600519",
    actual_trading_date: "2026-06-04",
    score_version: "trade_prediction_score_v2",
    score_status: "ok",
    data_quality_status: "ok",
    trade_prediction_score: 0.82,
    outcome_json: {
      direction_hit: true,
      target_touch: true,
      risk_proxy_score: 0.78,
      time_bucket_hit_rate: 0.75,
      entry_window_hit: true,
      exit_window_hit: true,
      planned_trade_return: 0.034
    },
    metadata: { family: "momentum", stage: "candidate", regime: "bull", event: "policy_shock", factor: "momentum_20d" },
    calculated_at: "2026-06-04T07:15:00Z"
  },
  {
    outcome_id: "tpo_mock_002",
    prediction_id: "tp_mock_002",
    strategy_id: "strategy_reversal_cn",
    stock_code: "000001",
    actual_trading_date: "2026-06-04",
    score_version: "trade_prediction_score_v2",
    score_status: "partial_intraday_missing",
    data_quality_status: "intraday_missing",
    trade_prediction_score: 0.51,
    outcome_json: {
      direction_hit: true,
      target_touch: false,
      risk_proxy_score: 0.44,
      planned_trade_return: 0.008
    },
    metadata: { family: "mean_reversion", stage: "observe", regime: "range", event: "earnings", factor: "reversal_5d" },
    calculated_at: "2026-06-04T07:20:00Z"
  },
  {
    outcome_id: "tpo_mock_003",
    prediction_id: "tp_mock_003",
    strategy_id: "strategy_event_cn",
    stock_code: "002475",
    actual_trading_date: "2026-06-03",
    score_version: "trade_prediction_score_daily_v1",
    score_status: "partial_daily_only",
    data_quality_status: "ok",
    trade_prediction_score: 0.66,
    outcome_json: {
      direction_hit: true,
      target_touch: true,
      risk_proxy_score: 0.62,
      planned_trade_return: 0.019
    },
    metadata: { family: "event_driven", stage: "graduation_ready", regime: "volatile", event: "supply_chain", factor: "event_strength" },
    calculated_at: "2026-06-03T07:10:00Z"
  },
  {
    outcome_id: "tpo_mock_004",
    prediction_id: "tp_mock_004",
    strategy_id: "strategy_event_cn",
    stock_code: "300750",
    actual_trading_date: "2026-06-03",
    score_version: "trade_prediction_score_v2",
    score_status: "insufficient_samples",
    data_quality_status: "partial_gap",
    trade_prediction_score: 0.38,
    outcome_json: {
      direction_hit: false,
      target_touch: false,
      risk_proxy_score: 0.31,
      time_bucket_hit_rate: 0.25,
      entry_window_hit: false,
      exit_window_hit: false,
      planned_trade_return: -0.012
    },
    metadata: { family: "event_driven", stage: "candidate", regime: "volatile", event: "policy_shock", factor: "event_strength" },
    calculated_at: "2026-06-03T07:18:00Z"
  }
];

function safeLimit(value: unknown, fallback = 100): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? Math.max(1, Math.min(Math.trunc(parsed), 1000)) : fallback;
}

function matchesFilter(item: Record<string, unknown>, filters: Record<string, unknown>, key: string): boolean {
  const value = filters[key];
  if (value === undefined || value === null || value === "") return true;
  return String(item[key] || "") === String(value);
}

function tradePredictionOutcomeItems(filters: Record<string, unknown> = {}) {
  const limit = safeLimit(filters.limit, 100);
  return mockTradePredictionOutcomes
    .filter((item) =>
      ["prediction_id", "strategy_id", "stock_code", "score_version", "score_status", "data_quality_status"].every((key) =>
        matchesFilter(item, filters, key)
      )
    )
    .filter((item) => {
      const date = String(item.actual_trading_date || "");
      const lte = String(filters.actual_trading_date_lte || "");
      const gte = String(filters.actual_trading_date_gte || "");
      if (lte && date > lte) return false;
      if (gte && date < gte) return false;
      return true;
    })
    .slice(0, limit);
}

export function tradePredictionStatus(filters: Record<string, unknown> = {}) {
  const outcomes = tradePredictionOutcomeItems(filters);
  const scoreStatusCounts: Record<string, number> = {};
  const scoreVersionCounts: Record<string, number> = {};
  const dataQualityCounts: Record<string, number> = {};
  const scoreDistribution: Record<string, number> = {};
  const scores: number[] = [];
  const evaluated = new Set<string>();
  let partialCount = 0;

  for (const outcome of outcomes) {
    const scoreStatus = String(outcome.score_status || "unknown");
    const scoreVersion = String(outcome.score_version || "unknown");
    const dataQuality = String(outcome.data_quality_status || "unknown");
    scoreStatusCounts[scoreStatus] = (scoreStatusCounts[scoreStatus] || 0) + 1;
    scoreVersionCounts[scoreVersion] = (scoreVersionCounts[scoreVersion] || 0) + 1;
    dataQualityCounts[dataQuality] = (dataQualityCounts[dataQuality] || 0) + 1;
    evaluated.add(String(outcome.prediction_id));
    if (["partial_daily_only", "partial_intraday_missing", "insufficient_samples", "post_hoc_rejected"].includes(scoreStatus)) {
      partialCount += 1;
    }
    const score = Number(outcome.trade_prediction_score);
    if (Number.isFinite(score)) {
      scores.push(score);
      const bucket = score >= 0.8 ? "0.80-1.00" : score >= 0.6 ? "0.60-0.79" : score >= 0.4 ? "0.40-0.59" : score >= 0.2 ? "0.20-0.39" : "0.00-0.19";
      scoreDistribution[bucket] = (scoreDistribution[bucket] || 0) + 1;
    }
  }

  const pendingCount = filters.strategy_id || filters.stock_code ? 0 : 1;
  return {
    object: "trade_prediction.status",
    status: "ready",
    configured: true,
    generated_at: "2026-06-05T02:30:00Z",
    prediction_count: outcomes.length + pendingCount,
    outcome_count: outcomes.length,
    sample_n: evaluated.size,
    pending_count: pendingCount,
    evaluated_count: evaluated.size,
    partial_count: partialCount,
    prediction_status_counts: { frozen: outcomes.length, pending: pendingCount },
    score_status_counts: scoreStatusCounts,
    latest_score_status_counts: scoreStatusCounts,
    score_version_counts: scoreVersionCounts,
    data_quality_status_counts: dataQualityCounts,
    latest_data_quality_status_counts: dataQualityCounts,
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
  const rawDimensions = filters.dimensions;
  const dimensions = Array.isArray(rawDimensions)
    ? rawDimensions.map(String).filter(Boolean)
    : String(rawDimensions || "family,stage,regime,event,factor").split(",").map((item) => item.trim()).filter(Boolean);
  const items = tradePredictionOutcomeItems(filters);
  const cells = new Map<string, { dimension: string; value: string; scores: number[]; directionHits: number; targetTouches: number; statusCounts: Record<string, number>; dataQualityCounts: Record<string, number> }>();
  for (const item of items) {
    const metadata = (item.metadata || {}) as Record<string, unknown>;
    const outcomeJson = (item.outcome_json || {}) as Record<string, unknown>;
    for (const dimension of dimensions) {
      const value = String(metadata[dimension] || "unknown");
      const key = `${dimension}:${value}`;
      const cell = cells.get(key) || { dimension, value, scores: [], directionHits: 0, targetTouches: 0, statusCounts: {}, dataQualityCounts: {} };
      const score = Number(item.trade_prediction_score);
      if (Number.isFinite(score)) cell.scores.push(score);
      if (outcomeJson.direction_hit) cell.directionHits += 1;
      if (outcomeJson.target_touch) cell.targetTouches += 1;
      const status = String(item.score_status || "unknown");
      const quality = String(item.data_quality_status || "unknown");
      cell.statusCounts[status] = (cell.statusCounts[status] || 0) + 1;
      cell.dataQualityCounts[quality] = (cell.dataQualityCounts[quality] || 0) + 1;
      cells.set(key, cell);
    }
  }
  const rows = Array.from(cells.values())
    .map((cell) => {
      const sample_n = cell.scores.length;
      const scoreAvg = sample_n ? cell.scores.reduce((sum, score) => sum + score, 0) / sample_n : null;
      const scoreLcb = scoreAvg === null || sample_n === 0 ? null : Math.max(0, scoreAvg - 1.96 * Math.sqrt((scoreAvg * (1 - scoreAvg)) / sample_n));
      return {
        dimension: cell.dimension,
        value: cell.value,
        sample_n,
        score_avg: scoreAvg === null ? null : Number(scoreAvg.toFixed(6)),
        score_lcb_95: scoreLcb === null ? null : Number(scoreLcb.toFixed(6)),
        direction_hit_rate: sample_n ? Number((cell.directionHits / sample_n).toFixed(6)) : null,
        target_touch_rate: sample_n ? Number((cell.targetTouches / sample_n).toFixed(6)) : null,
        score_status_counts: cell.statusCounts,
        data_quality_status_counts: cell.dataQualityCounts
      };
    })
    .sort((left, right) => String(left.dimension).localeCompare(String(right.dimension)) || right.sample_n - left.sample_n);
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
