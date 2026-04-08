import type { Page, Route } from '@playwright/test';

export const DEMO_STRATEGY_ID = 'demo-strategy-p3';
export const DEMO_STRATEGY_NAME = 'P3 反馈闭环演示策略';
export const DEMO_RUN_ID = 'run-p3-001';

export const factorySummary = {
  candidates_spawned: 8,
  autonomy_generated: 6,
  candidates_passed_backtest: 5,
  candidates_after_dedup: 4,
  passed_quality_gate: 3,
  eliminated: 1,
  elapsed_seconds: 92,
  snapshot_completion_ratio: 0.95,
  snapshot_degraded: false,
  snapshot_failure_reason_count: 0,
  autonomy_task_count: 3,
  event_task_count: 1,
  snapshot_task_count: 1,
  event_snapshot_mixed: true,
  task_source_counts: {
    event_driven: 2,
    snapshot: 1,
  },
  scanner_task_types: {
    momentum: 2,
    quality: 1,
  },
  lifecycle_feedback_input_contract_version: 'p3-feedback/v1',
  lifecycle_feedback_input_available: true,
  budget_feedback_available: true,
  budget_feedback_family_count: 4,
  budget_feedback_strategy_count: 12,
  budget_feedback_target_pool_scope_count: 3,
  budget_feedback_generator_mode_scope_count: 2,
  budget_feedback_runtime_alert_count: 6,
  budget_feedback_runtime_risk_event_count: 2,
  budget_feedback_promotion_review_count: 5,
  budget_feedback_promotion_review_status_counts: {
    approved: 3,
    watch: 2,
  },
  blocked_feedback_task_count: 2,
  planned_feedback_cooldown_task_count: 1,
  planned_feedback_control_mode_counts: {
    manual_review: 2,
    auto_block: 1,
  },
  planned_feedback_target_pool_control_mode_counts: {
    pool_watch: 2,
  },
  planned_feedback_generator_mode_control_mode_counts: {
    cooldown: 1,
  },
  selected_feedback_control_mode_counts: {
    manual_review: 1,
  },
  selected_feedback_target_pool_control_mode_counts: {
    priority_pool: 1,
  },
  selected_feedback_generator_mode_control_mode_counts: {
    balanced: 1,
  },
  feedback_control_mode_counts: {
    greenlight: 2,
    manual_review: 1,
  },
  feedback_target_pool_control_mode_counts: {
    core_pool: 2,
  },
  feedback_generator_mode_control_mode_counts: {
    momentum_mode: 2,
  },
  suppressed_families: ['high_beta', 'mean_reversion'],
  suppressed_target_pools: ['micro_cap'],
  suppressed_generator_modes: ['aggressive'],
  external_llm_provider_control_mode: 'manual_review',
  generator_mode_controls: {
    momentum: {
      control_mode: 'greenlight',
      source: 'promotion_review',
      families: ['momentum', 'quality'],
      control_reasons: ['approved', 'stable'],
    },
    aggressive: {
      control_mode: 'auto_block',
      source: 'runtime_alert',
      families: ['high_beta'],
      control_reasons: ['drawdown breach'],
    },
  },
  partial_stage_count: 1,
};

export const factoryRunDetail = {
  run_id: DEMO_RUN_ID,
  status: 'success',
  completed_at: '2026-04-08T10:31:32',
  elapsed_seconds: 92,
  summary: factorySummary,
  feedback_summary: {
    lifecycle_feedback_input_contract_version: 'p3-feedback/v1',
    lifecycle_feedback_input_observed: true,
    feedback_available: true,
    family_count: 4,
    strategy_count: 12,
    target_pool_scope_count: 3,
    generator_mode_scope_count: 2,
    runtime_alert_count: 6,
    runtime_risk_event_count: 2,
    promotion_review_count: 5,
    promotion_review_status_counts: {
      approved: 3,
      watch: 2,
    },
    blocked_task_count: 2,
    planned_cooldown_task_count: 1,
    planned_control_mode_counts: {
      manual_review: 2,
      auto_block: 1,
    },
    planned_target_pool_control_mode_counts: {
      pool_watch: 2,
    },
    planned_generator_mode_control_mode_counts: {
      cooldown: 1,
    },
    selected_control_mode_counts: {
      manual_review: 1,
    },
    selected_target_pool_control_mode_counts: {
      priority_pool: 1,
    },
    selected_generator_mode_control_mode_counts: {
      balanced: 1,
    },
    submission_control_mode_counts: {
      greenlight: 2,
      manual_review: 1,
    },
    submission_target_pool_control_mode_counts: {
      core_pool: 2,
    },
    submission_generator_mode_control_mode_counts: {
      momentum_mode: 2,
    },
    suppressed_families: ['high_beta', 'mean_reversion'],
    suppressed_target_pools: ['micro_cap'],
    suppressed_generator_modes: ['aggressive'],
  },
  research_summary: {
    research_plane_contract_version: 'research-summary/v1',
  },
  research_plane: {
    available: true,
    contract_version: 'research-plane/v1',
    plane: 'research',
    source_chain: ['strategy_manager', 'domain_projection'],
  },
  research_artifact: {
    available: true,
    contract_version: 'research-artifact/v1',
    active_factor_count: 12,
    active_candidate_count: 8,
    factor_source_mode: 'governed_pool',
    governed_candidate_pool_active: true,
    lifecycle_feedback_input_available: true,
    lifecycle_feedback_input_contract_version: 'p3-feedback/v1',
    lifecycle_feedback_family_count: 4,
    lifecycle_feedback_strategy_count: 12,
    lifecycle_feedback_target_pool_scope_count: 3,
    lifecycle_feedback_generator_mode_scope_count: 2,
    lifecycle_feedback_runtime_alert_count: 6,
    lifecycle_feedback_promotion_review_count: 5,
    lifecycle_feedback_promotion_review_status_counts: {
      approved: 3,
      watch: 2,
    },
    readiness_reference: {},
    top_candidate_lineage_preview: [],
  },
  task_artifact: {
    available: true,
    contract_version: 'task-artifact/v1',
    planned_task_count: 3,
    executed_task_count: 3,
    generated_candidate_count: 8,
    event_task_count: 1,
    snapshot_task_count: 1,
  },
  candidate_artifact: {
    available: true,
    contract_version: 'candidate-artifact/v1',
    candidate_count: 8,
    targeted_candidate_count: 6,
    experiment_linked_count: 4,
    candidate_contract_ready_count: 5,
    candidate_evidence_ready_count: 4,
    family_counts: {
      momentum: 4,
      quality: 2,
    },
    task_source_counts: {
      event_driven: 2,
      snapshot: 1,
    },
    candidate_briefs: [],
  },
  evidence_artifact: {
    available: true,
    contract_version: 'evidence-artifact/v1',
    experiment_count: 4,
    task_evidence_count: 6,
    task_run_count: 3,
    external_llm_status: 'healthy',
    external_llm_network_request_count: 2,
    external_llm_status_counts: {
      healthy: 2,
    },
    experiment_briefs: [],
  },
  stages: {
    collect: {
      ok: true,
      status: 'completed',
    },
    submit: {
      ok: true,
      status: 'completed',
    },
  },
};

export const strategyDetail = {
  strategy: {
    id: DEMO_STRATEGY_ID,
    name: DEMO_STRATEGY_NAME,
    description: '用于验证策略工厂 P3 反馈闭环展示增强',
    strategy_type: 'multi_factor',
    status: 'listed',
    author_id: 'factory-bot',
    subscriber_count: 18,
    avg_rating: 4.6,
    review_count: 7,
    factor_weights: {
      momentum: 0.5,
      quality: 0.3,
      value: 0.2,
    },
    sample_start_date: '2025-01-01',
    sample_end_date: '2026-04-08',
    turnover_rate: 0.18,
    capacity: 5000000,
    capacity_label: '容量上限',
  },
  metrics: [
    {
      period: 'all',
      total_return: 0.32,
      annual_return: 0.18,
      sharpe_ratio: 1.42,
      max_drawdown: -0.12,
      win_rate: 0.61,
      trade_count: 48,
    },
    {
      period: '2025',
      total_return: 0.24,
      annual_return: 0.16,
      sharpe_ratio: 1.2,
      max_drawdown: -0.1,
      win_rate: 0.58,
      trade_count: 31,
    },
  ],
  reviews: [
    {
      user_id: 'demo',
      rating: 5,
      comment: '信号稳定，适合做工厂回归验证',
      created_at: '2026-04-08T09:15:00',
    },
  ],
  nav_series: [1, 1.03, 1.05, 1.08, 1.12],
  latest_quality_report: {
    passed: true,
    summary: {
      validation_grade: 'A',
      review_source: 'strategy_review_workflow',
      primary_validation_layer: 'governance',
    },
    quality_gate: {
      deflated_sharpe_ratio: 1.23,
      pbo: 0.18,
      hansen_spa_pvalue: 0.04,
      white_reality_check_pvalue: 0.06,
      multiple_testing_mode: 'formal_runtime',
    },
  },
  incubation_account: {
    strategy_id: DEMO_STRATEGY_ID,
    account_id: 'paper-001',
    stage: 'paper',
    status: 'active',
  },
  latest_incubation_metric: {
    metric_date: '2026-04-08',
    account_id: 'paper-001',
    stage: 'paper',
    decision: 'promote',
    nav: 1.1042,
    total_value: 1104200,
    daily_return: 0.013,
    max_drawdown: -0.08,
    sharpe_ratio: 1.31,
    hit_rate_5d: 0.64,
    forward_ic_5d: 0.12,
    forward_sharpe_5d: 0.88,
    total_signals: 14,
  },
  open_risk_events: [
    {
      event_id: 1,
      event_type: 'drawdown_watch',
      severity: 'medium',
      status: 'open',
      title: '回撤接近阈值',
    },
  ],
  vector_profiles: [
    {
      strategy_id: DEMO_STRATEGY_ID,
      profile_id: 'vec-profile-001',
      backend: 'pgvector',
    },
  ],
};

export const signalStats = {
  total_signals: 14,
  hit_rate: {
    5: 0.64,
    10: 0.58,
  },
  forward_ic: {
    5: 0.12,
    10: 0.16,
  },
  forward_sharpe: {
    5: 0.88,
    10: 1.05,
  },
};

export const signals = {
  subscriber: true,
  signals: [
    {
      signal_date: '2026-04-07',
      code: '600519',
      signal: 1,
      score: 0.91,
    },
    {
      signal_date: '2026-04-08',
      code: '000001',
      signal: -1,
      score: 0.62,
    },
  ],
  count: 2,
};

export const reviewWorkflow = {
  passed: true,
  summary: {
    validation_grade: 'A',
    review_source: 'strategy_review_workflow',
    primary_validation_layer: 'governance',
    refresh_mode: 'refresh_metrics_only',
    committee_decision: 'accept',
  },
  quality_gate: {
    wf_ic_ir: 1.1284,
    pkf_ic: 0.1423,
    pbo: 0.18,
    hansen_spa_pvalue: 0.04,
    white_reality_check_pvalue: 0.06,
  },
  committee_review: {
    decision: 'accept',
    final_score: 0.87,
    execution_score: 0.81,
    capacity_score: 0.76,
    task_alignment_score: 0.73,
  },
  run_correction: {
    multiple_testing_mode: 'formal_runtime',
    pbo: 0.18,
    hansen_spa_pvalue: 0.04,
  },
  validation_profile: {
    profile: 'factory-governed',
  },
  task_signature: {
    strategy_scope: 'promotion_review',
  },
};

export const lifecycleEvents = {
  events: [
    {
      event_type: 'status_change',
      from_status: 'incubating',
      to_status: 'review_ready',
      actor_id: 'factory-review-bot',
      reason: 'promotion review triggered',
      created_at: '2026-04-08T10:18:00',
      metadata: {
        review_source: 'strategy_review_workflow',
        decision: 'accept',
      },
    },
    {
      event_type: 'status_change',
      from_status: 'review_ready',
      to_status: 'listed',
      actor_id: 'promotion-committee',
      reason: 'committee accepted candidate',
      created_at: '2026-04-08T10:26:00',
      metadata: {
        release_mode: 'active',
        aggregate_version: 12,
      },
    },
  ],
  count: 2,
};

export const incubationOverview = {
  validation_grade: 'A',
  promotion_ready: true,
  deprecation_risk: false,
  blockers: [],
  risk_flags: ['runtime watch'],
  total_signals: 14,
  hit_rate_5d: 0.64,
  sharpe_ratio: 1.31,
  max_drawdown: -0.08,
  forward_ic_5d: 0.12,
  forward_sharpe_5d: 0.88,
  forward_returns: [
    {
      label: '5D',
      hit_rate: 0.64,
      forward_ic: 0.12,
      forward_sharpe: 0.88,
    },
    {
      label: '10D',
      hit_rate: 0.58,
      forward_ic: 0.16,
      forward_sharpe: 1.05,
    },
  ],
};

export const runtimeControl = {
  control_mode: 'active',
  status: 'released',
  source: 'promotion_review',
  trigger_event_type: 'promotion_accept',
  reason: 'committee approved controlled release',
  activated_at: '2026-04-08T10:20:00',
  released_at: '2026-04-08T10:28:00',
  action_summary: {
    release_scope: 'core_pool',
    escalation: 'watch',
  },
};

export const domainProjection = {
  current_status: 'listed',
  aggregate_version: 12,
  status_event_count: 6,
  domain_event_count: 14,
  open_risk_count: 1,
  runtime_control_mode: 'active',
  runtime_control_status: 'released',
  latest_promotion_status: 'approved',
  latest_promotion_recommendation: 'promote',
  ai_cycle_count: 3,
  runtime_cycle_count: 2,
  last_domain_event_at: '2026-04-08T10:28:00',
};

export const projectionSnapshot = {
  items: [
    {
      aggregate_version: 12,
      rebuilt_at: '2026-04-08T10:29:00',
      source: 'factory_review_projection',
      task_run_id: 'task-projection-001',
      projection: domainProjection,
    },
  ],
  latest: {
    aggregate_version: 12,
    rebuilt_at: '2026-04-08T10:29:00',
    source: 'factory_review_projection',
    task_run_id: 'task-projection-001',
    projection: domainProjection,
  },
  count: 1,
};

async function fulfillEnvelope(route: Route, data: unknown) {
  await route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({
      success: true,
      data,
    }),
  });
}

export async function mockStrategyMarketScenario(page: Page) {
  await page.route(/\/api\/strategy-market(?:\/.*)?$/, async (route) => {
    const url = new URL(route.request().url());

    switch (url.pathname) {
      case '/api/strategy-market/ranking':
        return fulfillEnvelope(route, {
          strategies: [
            {
              id: DEMO_STRATEGY_ID,
              name: DEMO_STRATEGY_NAME,
              strategy_type: 'multi_factor',
              description: '用于验证策略工厂 P3 反馈闭环展示增强',
              subscriber_count: 18,
              metrics: {
                annual_return: 0.18,
                sharpe_ratio: 1.42,
                max_drawdown: -0.12,
              },
            },
          ],
        });
      case '/api/strategy-market/factory/status':
        return fulfillEnvelope(route, {
          running: false,
          last_run: '2026-04-08T10:30:00',
          last_summary: factorySummary,
          last_result: {
            status: 'success',
          },
        });
      case '/api/strategy-market/capabilities':
        return fulfillEnvelope(route, {
          daily_snapshot: true,
          paper_incubation: true,
          runtime_risk: true,
          execution_risk: true,
          runtime_controls: true,
          promotion_pipeline: true,
          projection_snapshots: true,
          event_replay: true,
          vector_platform: true,
          vector_governance: true,
          ai_generation: true,
          multi_agent_review: true,
          quality_governance: true,
          domain_events: true,
          domain_projection: true,
          runtime_cycle: true,
        });
      case '/api/strategy-market/daily-snapshot':
        return fulfillEnvelope(route, {
          snapshot_date: '2026-04-08',
          degraded: false,
          hot_sectors: ['AI 算力', '高股息'],
          failure_reasons: [],
          summary: {
            listed_count: 21,
          },
          completeness: {
            completion_ratio: 0.95,
          },
        });
      case '/api/strategy-market/factory/runs':
        return fulfillEnvelope(route, {
          items: [
            {
              run_id: DEMO_RUN_ID,
              status: 'success',
              started_at: '2026-04-08T10:30:00',
              completed_at: '2026-04-08T10:31:32',
              elapsed_seconds: 92,
              summary: factorySummary,
              stages: {
                collect: { ok: true },
                submit: { ok: true },
              },
            },
          ],
          count: 1,
        });
      case '/api/strategy-market/factory/observability':
        return fulfillEnvelope(route, {
          overview: {
            latest_factory_status: 'success',
            active_factor_count: 12,
            governed_factor_count: 10,
            passed_quality_gate: 3,
            champion_count: 1,
            challenger_count: 2,
            scheduler_quality_status: 'healthy',
            recent_generated_candidate_count: 8,
            recent_validated_candidate_count: 3,
            retrain_plan_count: 1,
            latest_factory_run_id: DEMO_RUN_ID,
            blocked_factor_count: 2,
            recent_governed_active_count_after_run: 10,
            retrain_pending_count: 1,
          },
          factory: {
            runs: [{ run_id: DEMO_RUN_ID }],
          },
          factor_governance: {
            scheduler: {
              freshness_sec: 12,
            },
            recent_run: {
              generated_candidate_count: 8,
              validated_candidate_count: 3,
              governed_active_count_after_run: 10,
            },
            registry_summary: {
              registry_stage_counts: {
                active: 2,
                incubation: 1,
              },
            },
            active_pool: {
              family_summary: [{ family: 'momentum', count: 2 }],
              regime_summary: [{ regime: 'bull', count: 1 }],
            },
            retrain_summary: {
              status_counts: {
                queued: 1,
              },
            },
            retrain_queue: [{ id: 'retrain-001', status: 'queued' }],
          },
          errors: [],
        });
      case `/api/strategy-market/factory/runs/${DEMO_RUN_ID}`:
        return fulfillEnvelope(route, factoryRunDetail);
      case `/api/strategy-market/${DEMO_STRATEGY_ID}`:
        return fulfillEnvelope(route, strategyDetail);
      case '/api/strategy-market/my-subscriptions':
        return fulfillEnvelope(route, {
          subscriptions: [],
          count: 0,
        });
      case `/api/strategy-market/${DEMO_STRATEGY_ID}/signal-stats`:
        return fulfillEnvelope(route, signalStats);
      case `/api/strategy-market/${DEMO_STRATEGY_ID}/signals`:
        return fulfillEnvelope(route, signals);
      case `/api/strategy-market/${DEMO_STRATEGY_ID}/review-workflow`:
        return fulfillEnvelope(route, reviewWorkflow);
      case `/api/strategy-market/${DEMO_STRATEGY_ID}/events`:
        return fulfillEnvelope(route, lifecycleEvents);
      case `/api/strategy-market/${DEMO_STRATEGY_ID}/incubation-overview`:
        return fulfillEnvelope(route, incubationOverview);
      case `/api/strategy-market/${DEMO_STRATEGY_ID}/runtime-control`:
        return fulfillEnvelope(route, runtimeControl);
      case `/api/strategy-market/${DEMO_STRATEGY_ID}/domain-projection`:
        return fulfillEnvelope(route, domainProjection);
      case `/api/strategy-market/${DEMO_STRATEGY_ID}/domain-projection/snapshot`:
        return fulfillEnvelope(route, projectionSnapshot);
      default:
        return route.continue();
    }
  });
}
