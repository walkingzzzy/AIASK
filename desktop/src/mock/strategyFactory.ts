import type { ToolEnvelope } from "../types";

type EnvelopeBuilder = (tool: string, data: unknown, success?: boolean) => ToolEnvelope;

export function strategyFactoryStatusPayload() {
  return {
    status: "ready",
    runtime_enabled: true,
    event_runtime_mode: "readonly",
    daily_run_count: 7,
    cycle_count: 24,
    recent_run_diagnostics: {
      analyzed_run_count: 5,
      quality_progress: {
        recent_raw_b_or_above_rate_mean: 0.5,
        recent_strict_ready_given_raw_b_rate_mean: 0
      },
      blocker_reason_topn: [
        { reason_code: "diagnostic_only_not_allowed_for_incubation", count: 15 },
        { reason_code: "default_profile_not_allowed_for_single_name_runtime", count: 10 },
        { reason_code: "execution_readiness_tier:missing_executable_contract", count: 10 }
      ],
      recent_runs: [{ run_id: "run_factory_1", status: "completed" }]
    },
    strict_incubation_blocker_summary: {
      contract_version: "strategy_factory.strict_incubation_blockers.v1",
      status: "blocked",
      headline: "Recent runs still fail formal admission because strict incubation readiness is zero.",
      window_size: 5,
      analyzed_run_count: 5,
      analyzed_strategy_count: 20,
      submitted_count: 35,
      strict_not_ready_count: 20,
      raw_b_or_above_count: 10,
      raw_b_or_above_rate: 0.5,
      strict_ready_given_raw_b_count: 0,
      strict_ready_given_raw_b_rate: 0,
      observe_lane_count: 18,
      diagnostic_lane_count: 2,
      top_blockers: [
        {
          reason_code: "diagnostic_only_not_allowed_for_incubation",
          count: 15,
          label: "Diagnostic-only runtime cannot enter formal incubation.",
          next_action: "Route only non-diagnostic runtime evidence to formal incubation; keep diagnostic samples in observe."
        },
        {
          reason_code: "default_profile_not_allowed_for_single_name_runtime",
          count: 10,
          label: "Default runtime profile is not allowed for single-name formal runtime.",
          next_action: "Attach a single-name runtime profile before requesting formal admission."
        },
        {
          reason_code: "execution_readiness_tier:missing_executable_contract",
          count: 10,
          label: "Executable contract readiness is missing.",
          next_action: "Persist the executable DSL/runtime contract and replay admission."
        }
      ],
      sample_blocked_strategies: [
        {
          strategy_id: "factory_mock_strict_1",
          family: "momentum",
          grade: "A",
          submission_lane: "observe_incubation",
          strict_incubation_ready: false,
          blockers: [
            "diagnostic_only_not_allowed_for_incubation",
            "default_profile_not_allowed_for_single_name_runtime",
            "execution_readiness_tier:missing_executable_contract"
          ]
        }
      ],
      next_action: "Route only non-diagnostic runtime evidence to formal incubation; keep diagnostic samples in observe."
    },
    configured: true,
    database_configured: true,
    run_count: 7
  };
}

export function strategyFactoryRunsPayload() {
  return { runs: [{ run_id: "factory_run_mock", status: "completed", candidates: 12 }] };
}

export function strategyReviewSnapshotPayload() {
  return { status: "ready", reviews: [{ strategy_id: "strategy_mock", decision: "incubate" }] };
}

export function mockStrategyFactory(envelope: EnvelopeBuilder) {
  return {
    status: envelope("agent_factory_status", strategyFactoryStatusPayload()),
    runs: envelope("agent_factory_runs", strategyFactoryRunsPayload()),
    review_snapshot: envelope("agent_strategy_review_snapshot", strategyReviewSnapshotPayload())
  };
}

function factoryEventItems(statusOverride: unknown) {
  return [
    {
      event_id: "evt_mock_001",
      event_name: "稀土出口管制(mock)",
      event_type: "policy_shock",
      event_source: "manual",
      status: statusOverride || "active",
      direction: "bullish",
      intensity: 0.85,
      confidence: 0.7,
      primary_themes: ["critical_minerals", "rare_earth"],
      operator_id: "operator_alice",
      approver_id: "approver_bob",
      created_at: "2026-05-24T08:00:00Z",
      valid_from: "2026-05-24T08:00:00Z",
      valid_until: "2026-06-24T08:00:00Z"
    },
    {
      event_id: "evt_mock_002",
      event_name: "AI 芯片新规(mock)",
      event_type: "regulation",
      event_source: "news_llm",
      status: "pending_review",
      direction: "bearish",
      intensity: 0.6,
      confidence: 0.55,
      primary_themes: ["AI_chip"],
      operator_id: "news_pipeline",
      approver_id: null,
      created_at: "2026-05-24T07:30:00Z",
      valid_from: "2026-05-24T07:30:00Z",
      valid_until: "2026-05-31T07:30:00Z"
    }
  ];
}

export function factoryEventListPayload(body: Record<string, unknown>) {
  const events = factoryEventItems(body.status);
  return { events, count: events.length };
}

export function factoryEventPreviewTasksPayload(body: Record<string, unknown>) {
  return {
    event_id: body.event_id || "evt_mock_001",
    impacts: [
      { theme_code: "critical_minerals", depth: 0, magnitude: 0.85, source_path: "primary" },
      { theme_code: "rare_earth", depth: 0, magnitude: 0.85, source_path: "primary" },
      { theme_code: "metals_processing", depth: 1, magnitude: 0.42, source_path: "critical_minerals -> metals_processing" }
    ],
    candidate_symbols: ["600111", "600259", "600392", "002460", "300618"],
    target_count: 5,
    warnings: [],
    preview_mode: "real_bfs"
  };
}

export function factoryEventLineagePayload(body: Record<string, unknown>) {
  return { lineage: [{ event_id: body.event_id || "evt_mock_001", task_id: "task_mock", status: "planned" }] };
}

export function factoryThemeExposureStatusPayload(body: Record<string, unknown>) {
  return { status: "ready", exposures: [{ theme: body.theme || "AI_chip", exposure: 0.42 }] };
}

export function factoryEventOutboxStatusPayload() {
  return { counts: { pending: 0, sent: 2 }, latest: [] };
}

function parseStrategyManagerKwargs(body: Record<string, unknown>) {
  if (typeof body.kwargs === "string") {
    try {
      return JSON.parse(body.kwargs as string) as Record<string, unknown>;
    } catch {
      return {};
    }
  }
  if (body.kwargs && typeof body.kwargs === "object") return body.kwargs as Record<string, unknown>;
  return {};
}

export function strategyManagerPayload(body: Record<string, unknown>) {
  const action = String(body.action || "");
  const kwargs = parseStrategyManagerKwargs(body);
  if (action === "factory_event_list") {
    const events = factoryEventItems(kwargs.status);
    return { events, count: events.length };
  }
  if (action === "factory_event_preview_tasks") return factoryEventPreviewTasksPayload(kwargs);
  return { action, message: "mock strategy_manager handler" };
}
