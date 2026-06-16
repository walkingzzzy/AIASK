function safeLimit(value: unknown, fallback = 100): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? Math.max(1, Math.min(Math.trunc(parsed), 1000)) : fallback;
}

const mockIncubationHitRateReport = {
  report_date: "2026-06-05",
  generated_at: "2026-06-05T02:45:00Z",
  summary: {
    total_incubating: 8,
    total_with_signals: 7,
    auto_promoted: 1,
    stage_counts: {
      candidate: 3,
      observe: 2,
      graduation_ready: 1,
      blocked: 2
    }
  },
  hit_rate_dashboard: {
    overall: {
      total_signals: 38,
      hit_count: 23,
      hit_rate: 0.6053,
      avg_skill_lcb: 0.018,
      avg_forward_sharpe: 0.86,
      strategy_count: 8
    },
    by_family: {
      momentum: {
        hit_rate: 0.667,
        total_n: 18,
        avg_skill_lcb: 0.041,
        avg_forward_sharpe: 1.22,
        strategy_count: 3,
        promotion_ready_count: 1,
        blocked_count: 0,
        missing_forward_windows: 0
      },
      mean_reversion: {
        hit_rate: 0.455,
        total_n: 11,
        avg_skill_lcb: -0.012,
        avg_forward_sharpe: 0.21,
        strategy_count: 2,
        promotion_ready_count: 0,
        blocked_count: 1,
        missing_forward_windows: 2
      },
      event_driven: {
        hit_rate: 0.52,
        total_n: 9,
        avg_skill_lcb: 0.005,
        avg_forward_sharpe: 0.48,
        strategy_count: 3,
        promotion_ready_count: 0,
        blocked_count: 2,
        missing_forward_windows: 3
      }
    },
    by_regime: {
      bull: {
        hit_rate: 0.71,
        total_n: 14,
        avg_skill_lcb: 0.052,
        avg_forward_sharpe: 1.34,
        strategy_count: 3,
        promotion_ready_count: 1,
        blocked_count: 0,
        missing_forward_windows: 0
      },
      range: {
        hit_rate: 0.46,
        total_n: 13,
        avg_skill_lcb: -0.018,
        avg_forward_sharpe: 0.16,
        strategy_count: 3,
        promotion_ready_count: 0,
        blocked_count: 1,
        missing_forward_windows: 2
      },
      volatile: {
        hit_rate: 0.5,
        total_n: 11,
        avg_skill_lcb: 0.002,
        avg_forward_sharpe: 0.32,
        strategy_count: 2,
        promotion_ready_count: 0,
        blocked_count: 2,
        missing_forward_windows: 3
      }
    },
    by_stage: {
      candidate: { hit_rate: 0.54, total_n: 18, avg_skill_lcb: 0.006, strategy_count: 3, blocked_count: 1 },
      observe: { hit_rate: 0.49, total_n: 9, avg_skill_lcb: -0.004, strategy_count: 2, blocked_count: 1 },
      graduation_ready: { hit_rate: 0.667, total_n: 6, avg_skill_lcb: 0.041, strategy_count: 1, promotion_ready_count: 1 },
      blocked: { hit_rate: 0.42, total_n: 5, avg_skill_lcb: -0.022, strategy_count: 2, blocked_count: 2 }
    },
    trend: {
      available: true,
      improvement: 0.074,
      direction: "improving"
    }
  },
  promotion_blocker_summary: {
    status: "blocked",
    blocked_strategy_count: 3,
    top_blockers: [
      {
        reason_code: "missing_forward_window_5d",
        count: 3,
        label: "5d forward window is not complete.",
        next_action: "Wait for the 5d forward verification window or exclude incomplete samples from promotion review."
      },
      {
        reason_code: "execution_audit_pending",
        count: 2,
        label: "Execution audit replay has not accepted the strategy.",
        next_action: "Run execution audit replay and attach acceptance evidence before graduation."
      },
      {
        reason_code: "governance_review_required",
        count: 1,
        label: "Governance review is required before promotion.",
        next_action: "Complete governance review for the graduation-ready strategy."
      }
    ]
  },
  feedback_actions: {
    families_to_boost: ["momentum"],
    families_to_cooldown: ["mean_reversion"],
    families_to_freeze: ["event_driven"]
  },
  lifecycle_evidence: [
    {
      strategy_id: "strategy_momentum_cn",
      strategy_name: "Momentum CN",
      family: "momentum",
      regime: "bull",
      current_stage: "graduation_ready",
      lifecycle_state: "graduation_ready",
      observed_days: 24,
      trade_days: 18,
      hit_rate: 0.667,
      skill_lcb: 0.041,
      forward_sharpe: 1.22,
      forward_windows_completed: ["1d", "3d", "5d"],
      execution_audit: { status: "passed", accepted: true, replay_count: 12 },
      risk_gate: "passed",
      governance_status: "review_required",
      promotion_blockers: ["governance_review_required"],
      next_action: "Complete governance review and attach reviewer acceptance."
    },
    {
      strategy_id: "strategy_event_cn",
      strategy_name: "Event CN",
      family: "event_driven",
      regime: "volatile",
      current_stage: "blocked",
      lifecycle_state: "blocked",
      observed_days: 11,
      trade_days: 6,
      hit_rate: 0.5,
      skill_lcb: 0.002,
      forward_sharpe: 0.32,
      forward_windows_completed: ["1d", "3d"],
      execution_audit: { status: "pending", accepted: false, replay_count: 0 },
      risk_gate: "passed",
      governance_status: "not_started",
      promotion_blockers: ["missing_forward_window_5d", "execution_audit_pending"],
      next_action: "Finish the 5d forward window and rerun execution audit."
    },
    {
      strategy_id: "strategy_reversal_cn",
      strategy_name: "Mean Reversion CN",
      family: "mean_reversion",
      regime: "range",
      current_stage: "observe",
      lifecycle_state: "observe",
      observed_days: 14,
      trade_days: 9,
      hit_rate: 0.455,
      skill_lcb: -0.012,
      forward_sharpe: 0.21,
      forward_windows_completed: ["1d"],
      execution_audit: { status: "not_started", accepted: false, replay_count: 0 },
      risk_gate: "soft_fail",
      governance_status: "not_started",
      promotion_blockers: ["weak_skill_lcb", "missing_forward_window_3d", "missing_forward_window_5d"],
      next_action: "Keep in observe until skill LCB and forward windows recover."
    }
  ],
  source_chain: ["desktop.mockApi", "incubation_factory.hit_rate_report_generated"]
};

const mockIncubationDomainEvents = [
  {
    id: "inc_evt_report_001",
    event_id: "inc_evt_report_001",
    event_type: "incubation_factory.hit_rate_report_generated",
    aggregate_id: "incubation_factory",
    severity: "info",
    created_at: "2026-06-05T02:45:00Z",
    payload: mockIncubationHitRateReport
  },
  {
    id: "inc_evt_stage_001",
    event_id: "inc_evt_stage_001",
    event_type: "incubation.stage_transitioned",
    aggregate_id: "strategy_momentum_cn",
    strategy_id: "strategy_momentum_cn",
    status: "graduation_ready",
    severity: "info",
    created_at: "2026-06-05T02:40:00Z",
    payload: {
      strategy_id: "strategy_momentum_cn",
      strategy_name: "Momentum CN",
      from_stage: "observe",
      to_stage: "graduation_ready",
      family: "momentum",
      regime: "bull",
      lifecycle_state: "graduation_ready",
      evidence: mockIncubationHitRateReport.lifecycle_evidence[0]
    }
  },
  {
    id: "inc_evt_stage_002",
    event_id: "inc_evt_stage_002",
    event_type: "incubation.stage_transitioned",
    aggregate_id: "strategy_event_cn",
    strategy_id: "strategy_event_cn",
    status: "blocked",
    severity: "warn",
    created_at: "2026-06-05T02:35:00Z",
    payload: {
      strategy_id: "strategy_event_cn",
      strategy_name: "Event CN",
      from_stage: "candidate",
      to_stage: "blocked",
      family: "event_driven",
      regime: "volatile",
      lifecycle_state: "blocked",
      evidence: mockIncubationHitRateReport.lifecycle_evidence[1],
      promotion_blockers: ["missing_forward_window_5d", "execution_audit_pending"]
    }
  },
  {
    id: "inc_evt_stage_003",
    event_id: "inc_evt_stage_003",
    event_type: "incubation.stage_transitioned",
    aggregate_id: "strategy_reversal_cn",
    strategy_id: "strategy_reversal_cn",
    status: "observe",
    severity: "warn",
    created_at: "2026-06-05T02:30:00Z",
    payload: {
      strategy_id: "strategy_reversal_cn",
      strategy_name: "Mean Reversion CN",
      from_stage: "candidate",
      to_stage: "observe",
      family: "mean_reversion",
      regime: "range",
      lifecycle_state: "observe",
      evidence: mockIncubationHitRateReport.lifecycle_evidence[2],
      promotion_blockers: ["weak_skill_lcb", "missing_forward_window_3d", "missing_forward_window_5d"]
    }
  },
  {
    id: "factory_evt_run_001",
    event_id: "factory_evt_run_001",
    event_type: "factory.run_completed",
    aggregate_id: "factory_run_mock",
    strategy_id: "strategy_mock",
    status: "completed",
    severity: "info",
    created_at: "2026-06-05T01:55:00Z",
    payload: {
      decision: "review",
      strategy_id: "strategy_mock",
      candidate_count: 12
    }
  }
];

export function incubationFactoryStatusPayload() {
  return {
    status: "ready",
    run_count: 3,
    error_count: 0,
    last_run_at: "2026-06-05T02:45:00Z",
    last_result_status: "completed",
    report: mockIncubationHitRateReport,
    latest_lifecycle_state: mockIncubationHitRateReport.lifecycle_evidence[0],
    promotion_blocker_summary: mockIncubationHitRateReport.promotion_blocker_summary,
    source_chain: ["desktop.mockApi", "agent_incubation_factory_status"]
  };
}

export function strategyDomainEventsPayload(body: Record<string, unknown>) {
  const requestedType = String(body.event_type || "");
  const limit = safeLimit(body.limit, 20);
  const events = requestedType
    ? mockIncubationDomainEvents.filter((event) => event.event_type === requestedType)
    : mockIncubationDomainEvents;
  return {
    events: events.slice(0, limit),
    count: events.length,
    event_type: requestedType || "all",
    source_chain: ["desktop.mockApi", "agent_strategy_domain_events"]
  };
}
