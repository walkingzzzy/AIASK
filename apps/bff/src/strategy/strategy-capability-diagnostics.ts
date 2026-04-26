import type {
  StrategyCapabilityDiagnosticsResponse,
  StrategyCapabilityGapIssue,
  StrategyCapabilityGapSeverity,
  StrategyCapabilityLayerStatus,
  StrategyCapabilityMatchRow,
  StrategyCapabilityMatchStatus,
  StrategyManagerAction,
} from '@aiask/shared-types';
import {
  STRATEGY_MANAGER_ACTIONS,
  STRATEGY_MANAGER_CONTRACT_VERSION,
} from '@aiask/shared-types';

type McpRuntimeSnapshot = {
  reachable: boolean;
  toolCount: number | null;
  expectedTools: number | null;
  matched: boolean;
  source: string;
  message: string;
};

type RowDraft = {
  id: string;
  label: string;
  domain: StrategyCapabilityMatchRow['domain'];
  userIntent: string;
  mcpActions?: StrategyManagerAction[];
  workflowTools?: string[];
  artifactIds?: string[];
  artifactTables?: string[];
  bffEndpoints?: string[];
  dtoVersions?: string[];
  frontendEntries?: string[];
  consumedEndpoints?: string[];
  pageSurfaces?: string[];
  exposedToUser?: boolean;
  frontendNotes?: string | null;
  bffNotes?: string | null;
  artifactNotes?: string | null;
  mcpNotes?: string | null;
  issues?: StrategyCapabilityGapIssue[];
  impact: string;
};

const MCP_MANAGER_TOOL = 'strategy_manager';
const MCP_WORKFLOW_TOOL = 'strategy_review_workflow';
const MCP_ACTION_SET = new Set<StrategyManagerAction>(STRATEGY_MANAGER_ACTIONS);

function issue(
  kind: StrategyCapabilityGapIssue['kind'],
  severity: StrategyCapabilityGapSeverity,
  summary: string,
  userImpact: string,
  evidence: string[],
): StrategyCapabilityGapIssue {
  return {
    kind,
    severity,
    summary,
    user_impact: userImpact,
    evidence,
  };
}

const rows: RowDraft[] = [
  {
    id: 'market_catalog',
    label: '策略超市目录与榜单',
    domain: 'market',
    userIntent: '用户进入策略超市后按状态、分类和指标筛选策略。',
    mcpActions: ['list', 'rank', 'capabilities'],
    artifactIds: ['strategies', 'strategy_metrics', 'strategy_reviews', 'incubation_surface'],
    artifactTables: ['strategies', 'strategy_metrics', 'strategy_reviews'],
    bffEndpoints: [
      'GET /api/strategy-market/list',
      'GET /api/strategy-market/ranking',
      'GET /api/strategy-market/capabilities',
    ],
    dtoVersions: ['strategy_market.detail.v2'],
    frontendEntries: ['/strategy-market?workspace=market'],
    consumedEndpoints: [
      'GET /strategy-market/ranking',
      'GET /strategy-market/capabilities',
    ],
    pageSurfaces: ['StrategyMarketCatalogSection', 'StrategyMarketHeroSection'],
    exposedToUser: true,
    impact: '榜单和目录是闭环的，用户能看到市场策略并继续进入详情。',
  },
  {
    id: 'strategy_detail_closure_review',
    label: '策略详情与工厂审查',
    domain: 'factory',
    userIntent: '用户打开单个策略后阅读概览、追踪和工厂审查证据。',
    mcpActions: [
      'detail',
      'closure_review',
      'review_report',
      'events',
      'incubation_overview',
      'runtime_alerts',
      'vector_profiles',
      'domain_events',
      'task_runs',
    ],
    workflowTools: [MCP_WORKFLOW_TOOL],
    artifactIds: [
      'strategy_review_report',
      'closure_review',
      'incubation_overview',
      'runtime_alert_snapshot',
      'vector_index_snapshot',
      'domain_projection_snapshot',
    ],
    artifactTables: [
      'strategy_status_events',
      'strategy_runtime_alerts',
      'strategy_vector_profiles',
      'strategy_domain_events',
      'strategy_task_runs',
    ],
    bffEndpoints: [
      'GET /api/strategy-market/:id',
      'GET /api/strategy-market/:id/closure-review',
      'GET /api/strategy-market/:id/review-report',
      'GET /api/strategy-market/:id/events',
    ],
    frontendEntries: ['/strategy-market/:id'],
    consumedEndpoints: [
      'GET /strategy-market/:id',
      'GET /strategy-market/:id/closure-review',
      'GET /strategy-market/:id/review-report',
      'GET /strategy-market/:id/events',
    ],
    pageSurfaces: ['StrategyDetailShell', 'FactoryReviewPanel', 'useStrategyDetailPage'],
    exposedToUser: true,
    impact: '详情页能展示只读审查证据；老接口作为 closure-review 失败时的回退。',
  },
  {
    id: 'favorites_alias',
    label: '收藏 / 订阅语义',
    domain: 'personal',
    userIntent: '用户把策略标为收藏，并在“我的收藏”里继续比较。',
    mcpActions: ['favorite', 'unfavorite', 'my_favorites', 'subscribe', 'unsubscribe', 'my_subscriptions'],
    artifactIds: ['strategy_subscriptions'],
    artifactTables: ['strategy_subscriptions'],
    bffEndpoints: [
      'POST /api/strategy-market/:id/favorite',
      'DELETE /api/strategy-market/:id/favorite',
      'GET /api/strategy-market/my-favorites',
      'GET /api/strategy-market/my-subscriptions',
    ],
    frontendEntries: ['/strategy-market?workspace=favorites', '/strategy-market/:id'],
    consumedEndpoints: [
      'GET /strategy-market/my-favorites',
      'POST /strategy-market/:id/favorite',
      'DELETE /strategy-market/:id/favorite',
    ],
    pageSurfaces: ['StrategyMarketCatalogSection', 'StrategyDetailOverviewTab'],
    exposedToUser: true,
    mcpNotes: 'favorite/unfavorite/my_favorites 是应用端主语义；subscribe/unsubscribe/my_subscriptions 作为 legacy alias 保留。',
    impact: '用户只看到收藏语义；后端保留订阅别名以兼容历史数据和脚本。',
  },
  {
    id: 'personal_strategy_workspace',
    label: '我的策略与个人草稿',
    domain: 'personal',
    userIntent: '用户创建、复制、编辑、删除自己的策略，并请求 AI 修改建议。',
    mcpActions: [
      'create',
      'my_strategies',
      'fork_strategy',
      'personal_strategy_context',
      'personal_strategy_suggestions',
      'update_strategy',
      'delete_personal_strategy',
      'ai_optimize_personal_strategy',
    ],
    artifactIds: ['personal_strategy', 'draft_strategy', 'strategy_change_request'],
    artifactTables: ['strategies', 'strategy_status_events', 'strategy_artifacts'],
    bffEndpoints: [
      'POST /api/strategy-market/create',
      'GET /api/strategy-market/my-strategies',
      'POST /api/strategy-market/:id/fork',
      'GET /api/strategy-market/:id/personal-context',
      'POST /api/strategy-market/:id/ai-modification-suggestions',
      'PATCH /api/strategy-market/:id',
      'DELETE /api/strategy-market/:id',
      'POST /api/strategy-market/:id/ai-optimize',
    ],
    frontendEntries: ['/strategy-market?workspace=mine', '/strategy-market/:id'],
    consumedEndpoints: [
      'GET /strategy-market/my-strategies',
      'POST /strategy-market/create',
      'GET /strategy-market/:id/personal-context',
      'POST /strategy-market/:id/fork',
      'PATCH /strategy-market/:id',
      'POST /strategy-market/:id/ai-modification-suggestions',
      'POST /strategy-market/:id/ai-optimize',
    ],
    pageSurfaces: ['StrategyMarketPage mine workspace', 'StrategyDetailShell personal edit panel'],
    exposedToUser: true,
    impact: '个人策略主链已接上，用户可以从目录或详情进入个人策略工作流。',
  },
  {
    id: 'strategy_paper_session',
    label: '策略绑定个人模拟盘',
    domain: 'personal',
    userIntent: '用户从策略详情进入个人模拟盘测试，并携带 strategy_id 建立个人测试上下文。',
    mcpActions: ['paper_session_get', 'paper_session_get_or_create', 'paper_account', 'paper_orders', 'paper_nav'],
    artifactIds: ['strategy_paper_session', 'paper_account', 'paper_orders', 'paper_nav'],
    artifactTables: ['paper_accounts', 'paper_orders', 'paper_nav', 'strategy_paper_sessions'],
    bffEndpoints: [
      'GET /api/strategy-market/:id/paper-context',
      'GET /api/strategy-market/:id/paper-session',
      'POST /api/strategy-market/:id/paper-session',
    ],
    frontendEntries: ['/strategy-market/:id', '/paper-trading?strategy_id=:id&mode=personal-strategy'],
    consumedEndpoints: [
      'GET /strategy-market/:id/paper-context',
      'POST /strategy-market/:id/paper-session',
      'GET /paper-trading/* account endpoints',
    ],
    pageSurfaces: ['StrategyDetailOverviewTab', 'PaperTradingPage'],
    exposedToUser: true,
    impact: '详情页到模拟盘的策略上下文已经闭环，用户能看到个人测试和孵化测试两条轨道。',
  },
  {
    id: 'factory_market_view',
    label: '工厂运行态聚合视图',
    domain: 'factory',
    userIntent: '用户在工厂工作区看最近 run、快照、TopN、可观测性和可见产物。',
    mcpActions: [
      'capabilities',
      'factory_status',
      'daily_snapshot',
      'factory_runs',
      'factory_run_detail',
      'factory_topn_latest',
    ],
    artifactIds: [
      'factory_run_snapshot',
      'daily_snapshot',
      'full_market_topn',
      'portfolio_candidate',
      'model_retrain_plan',
      'factor_governance_registry',
    ],
    artifactTables: [
      'strategy_factory_runs',
      'strategy_factory_topn_snapshots',
      'strategy_factory_full_market_scores',
      'strategy_artifacts',
    ],
    bffEndpoints: ['GET /api/strategy-market/factory/market-view'],
    dtoVersions: ['strategy_market.factory_market_view.v1', 'strategy_market.factory_runs.v2'],
    frontendEntries: ['/strategy-market?workspace=factory'],
    consumedEndpoints: ['GET /strategy-market/factory/market-view'],
    pageSurfaces: ['StrategyMarketFactoryOverviewSection', 'FactoryDashboard', 'StrategyMarketObservabilitySection'],
    exposedToUser: true,
    impact: '工厂运行态通过一个聚合 DTO 可见，用户不需要分别调用慢接口。',
  },
  {
    id: 'factory_run_action_alias',
    label: '运行一轮工厂动作',
    domain: 'factory',
    userIntent: '管理员从页面触发一轮策略工厂运行。',
    mcpActions: ['factory_run_once', 'factory_dispatch_run', 'factory_dispatch_status'],
    artifactIds: ['factory_dispatch', 'factory_run_snapshot'],
    artifactTables: ['strategy_factory_dispatches', 'strategy_factory_runs'],
    bffEndpoints: [
      'POST /api/strategy-market/factory/dispatch/run',
      'POST /api/strategy-market/factory/run-once',
      'POST /api/strategy-market/operator/jobs',
      'GET /api/strategy-market/factory/dispatches/:dispatchId',
    ],
    frontendEntries: ['/strategy-market?workspace=factory'],
    consumedEndpoints: [
      'POST /strategy-market/factory/dispatch/run',
      'POST /strategy-market/operator/jobs(action=factory_dispatch_run)',
      'GET /strategy-market/factory/dispatches/:dispatchId',
    ],
    pageSurfaces: ['StrategyMarketHeroSection', 'StrategyMarketOperatorPanel', 'StrategyFactoryRawArtifactsPanel'],
    exposedToUser: false,
    bffNotes: 'factory/dispatch/run 是 canonical route；factory/run-once 保留为 deprecated alias。',
    frontendNotes: '主入口统一提交 factory_dispatch_run；factory_run_once 只在管理员高级验收区展示。',
    impact: '普通用户只能读结果；管理员通过后台调度入口触发，历史 run-once 路由仍兼容。',
  },
  {
    id: 'incubation_pipeline',
    label: '孵化、执行审计与晋级证据',
    domain: 'incubation',
    userIntent: '用户/管理员检查孵化模拟盘、执行审计、晋级评审和流水线快照。',
    mcpActions: [
      'incubation_accounts',
      'incubation_metrics',
      'paper_account',
      'paper_orders',
      'paper_nav',
      'execution_audit_acceptance',
      'incubation_pipeline',
      'incubation_pipeline_run',
      'promotion_reviews',
      'promotion_review_run',
    ],
    artifactIds: [
      'incubation_account',
      'incubation_metric',
      'execution_audit_acceptance',
      'incubation_pipeline_snapshot',
      'promotion_review',
    ],
    artifactTables: [
      'strategy_incubation_accounts',
      'strategy_incubation_metrics',
      'strategy_incubation_pipeline_snapshots',
      'strategy_promotion_reviews',
    ],
    bffEndpoints: [
      'GET /api/strategy-market/:id/incubation-overview',
      'GET /api/strategy-market/:id/incubation-metrics',
      'GET /api/strategy-market/:id/paper-account',
      'GET /api/strategy-market/:id/execution-audit',
      'POST /api/strategy-market/operator/jobs',
    ],
    frontendEntries: ['/strategy-market/:id?tab=factory'],
    consumedEndpoints: [
      'GET /strategy-market/:id/closure-review',
      'GET /strategy-market/:id/incubation-pipeline',
      'GET /strategy-market/:id/promotion-reviews',
      'POST /strategy-market/:id/incubation-pipeline/run',
      'POST /strategy-market/:id/execution-audit/run',
    ],
    pageSurfaces: ['FactoryReviewPanel incubation section', 'StrategyMarketOperatorPanel'],
    exposedToUser: true,
    impact: '孵化证据可读，部分修复动作通过详情页或管理员操作台执行。',
  },
  {
    id: 'runtime_governance',
    label: '运行态风控与告警',
    domain: 'runtime',
    userIntent: '用户查看开放风险、风险快照、运行控制和告警；管理员触发扫描或恢复。',
    mcpActions: [
      'risk_events',
      'risk_snapshots',
      'risk_scan_run',
      'risk_recovery',
      'resolve_risk_event',
      'runtime_alerts',
      'runtime_alert_dispatch_run',
      'runtime_alert_ack',
      'runtime_control',
      'runtime_control_set',
      'runtime_cycle_status',
      'runtime_cycle_run',
    ],
    artifactIds: ['risk_event', 'runtime_risk_snapshot', 'runtime_alert_snapshot', 'runtime_control'],
    artifactTables: ['strategy_risk_events', 'strategy_runtime_risk_snapshots', 'strategy_runtime_alerts'],
    bffEndpoints: [
      'GET /api/strategy-market/:id/risk-events',
      'GET /api/strategy-market/:id/risk-snapshots',
      'GET /api/strategy-market/:id/runtime-alerts',
      'GET /api/strategy-market/:id/runtime-control',
      'GET /api/strategy-market/runtime-cycle/status',
      'POST /api/strategy-market/:id/runtime-control',
      'POST /api/strategy-market/risk-events/:eventId/resolve',
      'POST /api/strategy-market/runtime-cycle/run',
      'POST /api/strategy-market/operator/jobs',
    ],
    frontendEntries: ['/strategy-market/:id?tab=factory&section=runtime', '/strategy-market?workspace=factory#operator'],
    consumedEndpoints: [
      'GET /strategy-market/:id/closure-review',
      'GET /strategy-market/:id/runtime-alerts',
      'POST /strategy-market/:id/runtime-alerts/dispatch',
      'POST /strategy-market/runtime-alerts/:alertId/ack',
      'POST /strategy-market/:id/runtime-control',
      'POST /strategy-market/risk-events/:eventId/resolve',
      'POST /strategy-market/runtime-cycle/run',
      'POST /strategy-market/operator/jobs(action=runtime_cycle_run)',
    ],
    pageSurfaces: ['FactoryReviewPanel runtime section', 'StrategyMarketOperatorPanel'],
    exposedToUser: true,
    frontendNotes: '读链路面向用户，处置动作仅管理员可见。',
    impact: '用户能看到风险和告警；管理员可以在详情页完成控制切换、事件解决和 runtime cycle。',
  },
  {
    id: 'vector_governance',
    label: '向量平台与索引治理',
    domain: 'vector',
    userIntent: '用户查看策略相似性和向量索引证据；管理员重建或清理索引。',
    mcpActions: [
      'vector_profiles',
      'vector_indexes',
      'vector_index_snapshots',
      'vector_ann_search',
      'vector_reconcile',
      'vector_rebuild',
      'vector_health',
      'vector_cleanup',
    ],
    artifactIds: ['vector_profile', 'vector_index_registry', 'vector_index_snapshot', 'vector_ann_search'],
    artifactTables: [
      'strategy_vector_profiles',
      'strategy_vector_index_snapshots',
      'strategy_vector_index_items',
      'vector_index_registry',
    ],
    bffEndpoints: [
      'GET /api/strategy-market/:id/vector-profiles',
      'GET /api/strategy-market/vector-indexes',
      'GET /api/strategy-market/vector-indexes/snapshots',
      'GET /api/strategy-market/vector-health',
      'POST /api/strategy-market/vector-indexes/reconcile',
      'POST /api/strategy-market/vector-indexes/rebuild',
      'POST /api/strategy-market/vector-indexes/cleanup',
      'POST /api/strategy-market/operator/jobs',
    ],
    frontendEntries: ['/strategy-market/:id?tab=factory&section=vectors', '/strategy-market?workspace=factory#operator'],
    consumedEndpoints: [
      'GET /strategy-market/:id/closure-review',
      'GET /strategy-market/:id/vector-profiles',
      'GET /strategy-market/:id/vector-ann-search',
      'GET /strategy-market/vector-health',
      'GET /strategy-market/vector-indexes',
      'GET /strategy-market/vector-indexes/snapshots',
      'POST /strategy-market/vector-indexes/reconcile',
      'POST /strategy-market/vector-indexes/rebuild',
      'POST /strategy-market/vector-indexes/cleanup',
    ],
    pageSurfaces: ['FactoryReviewPanel vectors section', 'StrategyFactoryVectorGovernancePanel', 'StrategyMarketOperatorPanel'],
    exposedToUser: true,
    frontendNotes: '索引健康公开可读；reconcile/rebuild/cleanup 仅管理员可执行，cleanup 默认 dry-run。',
    impact: '用户能看相似策略、索引快照和健康状态；管理员可以直接对账、重建和清理。',
  },
  {
    id: 'domain_projection',
    label: '领域事件与投影',
    domain: 'domain',
    userIntent: '用户查看策略生命周期事件、投影和最新 projection snapshot。',
    mcpActions: ['domain_events', 'domain_projection', 'domain_projection_snapshot', 'domain_projection_rebuild'],
    artifactIds: ['domain_event', 'domain_projection', 'domain_projection_snapshot'],
    artifactTables: ['strategy_domain_events', 'strategy_domain_projections', 'strategy_domain_projection_snapshots'],
    bffEndpoints: [
      'GET /api/strategy-market/:id/domain-events',
      'GET /api/strategy-market/:id/domain-projection',
      'GET /api/strategy-market/:id/domain-projection/snapshot',
      'POST /api/strategy-market/:id/domain-projection/rebuild',
    ],
    frontendEntries: ['/strategy-market/:id?tab=factory', '/strategy-market?workspace=factory#operator'],
    consumedEndpoints: [
      'GET /strategy-market/:id/closure-review',
      'GET /strategy-market/:id/domain-events',
      'GET /strategy-market/:id/domain-projection',
      'GET /strategy-market/:id/domain-projection/snapshot',
      'POST /strategy-market/:id/domain-projection/rebuild',
      'POST /strategy-market/operator/jobs(action=domain_projection_rebuild)',
    ],
    pageSurfaces: ['FactoryReviewPanel summary/experiments sections', 'StrategyMarketOperatorPanel'],
    exposedToUser: true,
    impact: '事件和投影证据可读，重建动作也有详情页与管理员入口。',
  },
  {
    id: 'ai_generation_and_experiments',
    label: 'AI 生成候选与实验记录',
    domain: 'ai',
    userIntent: '管理员生成候选策略；用户在工厂/详情中读取 AI 实验和任务记录。',
    mcpActions: ['ai_generate', 'ai_experiments', 'task_runs'],
    artifactIds: ['ai_experiment', 'strategy_task_run', 'generated_strategy_candidate'],
    artifactTables: ['strategy_ai_experiments', 'strategy_task_runs', 'strategy_artifacts'],
    bffEndpoints: [
      'POST /api/strategy-market/ai/generate',
      'GET /api/strategy-market/ai/experiments',
      'GET /api/strategy-market/task-runs',
      'POST /api/strategy-market/operator/jobs',
    ],
    frontendEntries: ['/strategy-market?workspace=factory', '/strategy-market/:id?tab=factory&section=experiments'],
    consumedEndpoints: [
      'POST /strategy-market/operator/jobs(action=ai_generate)',
      'GET /strategy-market/ai/experiments',
      'GET /strategy-market/task-runs',
    ],
    pageSurfaces: ['StrategyMarketHeroSection', 'StrategyMarketOperatorPanel', 'FactoryReviewPanel experiments section'],
    exposedToUser: false,
    frontendNotes: 'AI 生成是管理员入口；实验记录和 task runs 保持只读可见。',
    impact: '普通用户不会看到“AI 生成策略”按钮，但能看到已生成/已孵化结果；管理员可从工厂页或详情实验区触发。',
  },
  {
    id: 'factory_artifact_direct_reads',
    label: '工厂原始产物直读接口',
    domain: 'factory',
    userIntent: '用户或管理员直接读取日快照、TopN、run 明细和调度状态。',
    mcpActions: [
      'daily_snapshots',
      'daily_snapshot',
      'factory_runs',
      'factory_run_detail',
      'factory_topn_latest',
      'factory_run_topn',
      'factory_dispatch_status',
    ],
    artifactIds: ['daily_snapshot', 'factory_run_detail', 'full_market_topn', 'factory_dispatch'],
    artifactTables: [
      'strategy_daily_snapshots',
      'strategy_factory_runs',
      'strategy_factory_topn_snapshots',
      'strategy_factory_dispatches',
    ],
    bffEndpoints: [
      'GET /api/strategy-market/daily-snapshots',
      'GET /api/strategy-market/daily-snapshot',
      'GET /api/strategy-market/factory/runs',
      'GET /api/strategy-market/factory/runs/:runId',
      'GET /api/strategy-market/factory/topn/latest',
      'GET /api/strategy-market/factory/runs/:runId/topn',
      'GET /api/strategy-market/factory/dispatches/:dispatchId',
    ],
    frontendEntries: ['/strategy-market?workspace=factory'],
    consumedEndpoints: [
      'GET /strategy-market/factory/market-view',
      'GET /strategy-market/daily-snapshots',
      'GET /strategy-market/factory/topn/latest',
      'GET /strategy-market/factory/runs/:runId/topn',
      'GET /strategy-market/factory/dispatches/:dispatchId',
    ],
    pageSurfaces: ['FactoryDashboard via aggregate market-view DTO', 'StrategyFactoryRawArtifactsPanel'],
    exposedToUser: true,
    impact: '聚合视图保留；需要排查历史快照、特定 TopN 或调度状态时已有直读入口。',
  },
  {
    id: 'admin_lifecycle_controls',
    label: '发布、归档、提交与生命周期扫描',
    domain: 'operator',
    userIntent: '管理员把策略推进到上架/归档/提交状态，并扫描生命周期异常。',
    mcpActions: ['publish', 'archive', 'submit', 'lifecycle_scan', 'update_metrics', 'submission_replay'],
    artifactIds: ['strategy_status_event', 'lifecycle_scan_report', 'submission_gate_report'],
    artifactTables: ['strategy_status_events', 'strategy_artifacts'],
    bffEndpoints: [
      'POST /api/strategy-market/:id/publish',
      'POST /api/strategy-market/:id/archive',
      'POST /api/strategy-market/:id/submit',
      'POST /api/strategy-market/:id/update-metrics',
      'POST /api/strategy-market/lifecycle-scan',
      'POST /api/strategy-market/operator/jobs',
    ],
    frontendEntries: ['/strategy-market?workspace=factory#operator'],
    consumedEndpoints: [
      'POST /strategy-market/operator/jobs(action=publish)',
      'POST /strategy-market/operator/jobs(action=archive)',
      'POST /strategy-market/operator/jobs(action=submit)',
      'POST /strategy-market/operator/jobs(action=update_metrics)',
      'POST /strategy-market/operator/jobs(action=lifecycle_scan)',
      'POST /strategy-market/operator/jobs(action=submission_replay)',
    ],
    pageSurfaces: ['StrategyMarketOperatorPanel'],
    exposedToUser: false,
    frontendNotes: '生命周期按钮只在管理员 operator panel 中显示，且必须二次确认。',
    impact: '普通用户只能看到策略状态；管理员可以在页面里完成发布、归档、提交、指标更新和生命周期扫描。',
  },
  {
    id: 'frontend_workbench_promises',
    label: '前端工作台承诺动作',
    domain: 'market',
    userIntent: 'Copilot/工作台推荐页面动作时，用户希望推荐动作都可执行。',
    mcpActions: [],
    artifactIds: [],
    bffEndpoints: [],
    frontendEntries: ['/strategy-market ProgressiveWorkbenchSection'],
    consumedEndpoints: ['pageActionBus.execute(strategy-market.refresh)', 'pageActionBus.execute(strategy-market.open-workspace)'],
    pageSurfaces: ['StrategyMarketPage.strategyMarketResult.preferredActionIds', 'usePageActions(pageActions)'],
    exposedToUser: true,
    frontendNotes: 'preferredActionIds 中的 refresh/open-workspace 均有页面动作实现。',
    impact: 'Copilot 和工作台推荐的刷新/打开工作区动作可以直接执行。',
  },
];

function severityRank(severity: StrategyCapabilityGapSeverity) {
  return severity === 'p0' ? 0 : severity === 'p1' ? 1 : severity === 'p2' ? 2 : 3;
}

function resolveSeverity(issues: StrategyCapabilityGapIssue[]): StrategyCapabilityGapSeverity {
  return issues.reduce<StrategyCapabilityGapSeverity>(
    (current, item) => (severityRank(item.severity) < severityRank(current) ? item.severity : current),
    'p3',
  );
}

function layerStatus(hasPrimaryData: boolean, exposed?: boolean): StrategyCapabilityLayerStatus {
  if (!hasPrimaryData) return 'absent';
  if (exposed === false) return 'internal';
  return 'present';
}

function rowStatus(row: RowDraft, issues: StrategyCapabilityGapIssue[]): StrategyCapabilityMatchStatus {
  if (issues.some((item) => item.kind === 'naming_or_field_mismatch')) return 'mismatch';
  if (issues.length > 0) return 'gap';
  if (row.exposedToUser === false) return 'internal';
  return 'matched';
}

function normalizeRow(row: RowDraft): StrategyCapabilityMatchRow {
  const actions = row.mcpActions ?? [];
  const workflowTools = row.workflowTools ?? [];
  const missingActions = actions.filter((action) => !MCP_ACTION_SET.has(action));
  const issues = [...(row.issues ?? [])];
  if (missingActions.length > 0) {
    issues.push(
      issue(
        'frontend_without_backend',
        'p0',
        `MCP contract 缺少动作：${missingActions.join(', ')}`,
        '页面或 BFF 映射到未注册动作时，请求会在 strategy_manager 层失败。',
        missingActions.map((action) => `missing action ${action}`),
      ),
    );
  }

  const hasMcp = actions.length > 0 || workflowTools.length > 0;
  const status = rowStatus(row, issues);
  const severity = issues.length > 0 ? resolveSeverity(issues) : 'p3';
  return {
    id: row.id,
    label: row.label,
    domain: row.domain,
    user_intent: row.userIntent,
    status,
    severity,
    mcp: {
      status: layerStatus(hasMcp),
      tool_names: actions.length > 0 ? [MCP_MANAGER_TOOL] : [],
      manager_actions: actions,
      workflow_tools: workflowTools,
      registered: missingActions.length === 0 && hasMcp,
      notes: row.mcpNotes ?? null,
    },
    factory_artifacts: {
      status: layerStatus(Boolean(row.artifactIds?.length)),
      artifact_ids: row.artifactIds ?? [],
      artifact_tables: row.artifactTables ?? [],
      notes: row.artifactNotes ?? null,
    },
    bff: {
      status: layerStatus(Boolean(row.bffEndpoints?.length), row.exposedToUser),
      endpoints: row.bffEndpoints ?? [],
      dto_versions: row.dtoVersions ?? [],
      notes: row.bffNotes ?? null,
    },
    frontend: {
      status: layerStatus(Boolean(row.frontendEntries?.length || row.pageSurfaces?.length), row.exposedToUser),
      entry_points: row.frontendEntries ?? [],
      consumed_endpoints: row.consumedEndpoints ?? [],
      page_surfaces: row.pageSurfaces ?? [],
      exposed_to_user: row.exposedToUser !== false,
      notes: row.frontendNotes ?? null,
    },
    issues,
    user_visible_impact: row.impact,
  };
}

function summarize(items: StrategyCapabilityMatchRow[]): StrategyCapabilityDiagnosticsResponse['summary'] {
  const issueCount = (kind: StrategyCapabilityGapIssue['kind']) =>
    items.reduce((count, item) => count + item.issues.filter((issueItem) => issueItem.kind === kind).length, 0);
  const severityCount = (severity: StrategyCapabilityGapSeverity) =>
    items.filter((item) => item.severity === severity).length;

  return {
    total: items.length,
    matched: items.filter((item) => item.status === 'matched').length,
    gap: items.filter((item) => item.status === 'gap').length,
    mismatch: items.filter((item) => item.status === 'mismatch').length,
    internal: items.filter((item) => item.status === 'internal').length,
    backend_without_frontend: issueCount('backend_without_frontend'),
    frontend_without_backend: issueCount('frontend_without_backend'),
    internal_not_user_exposed: issueCount('internal_not_user_exposed'),
    naming_or_field_mismatch: issueCount('naming_or_field_mismatch'),
    p0: severityCount('p0'),
    p1: severityCount('p1'),
    p2: severityCount('p2'),
    p3: severityCount('p3'),
  };
}

export function buildStrategyCapabilityDiagnostics(
  options: { mcpRuntime?: McpRuntimeSnapshot | null; generatedAt?: string } = {},
): StrategyCapabilityDiagnosticsResponse {
  const items = rows.map(normalizeRow);
  return {
    dto_version: 'strategy_market.capability_diagnostics.v1',
    generated_at: options.generatedAt ?? new Date().toISOString(),
    mcp_contract_version: STRATEGY_MANAGER_CONTRACT_VERSION,
    layers: ['mcp_manager', 'strategy_factory_artifacts', 'bff_api', 'frontend_surface'],
    mcp_runtime: options.mcpRuntime
      ? {
          reachable: options.mcpRuntime.reachable,
          tool_count: options.mcpRuntime.toolCount,
          expected_tools: options.mcpRuntime.expectedTools,
          matched: options.mcpRuntime.matched,
          source: options.mcpRuntime.source,
          message: options.mcpRuntime.message,
        }
      : null,
    summary: summarize(items),
    items,
    critical_unmatched: items.filter(
      (item) =>
        item.issues.length > 0
        && (item.severity === 'p0' || item.severity === 'p1')
        && item.status !== 'matched',
    ),
  };
}
