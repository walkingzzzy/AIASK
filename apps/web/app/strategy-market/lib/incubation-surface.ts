'use client';

import type {
  IncubationAccount,
  IncubationMetric,
  IncubationOverviewResponse,
  IncubationPipelineSnapshot,
  Strategy,
  StrategyIncubationSurface,
  StrategyOwnerState,
  StrategyPaperSessionState,
} from '../types';

type BadgeVariant = 'success' | 'danger' | 'warning' | 'info' | 'neutral';

export type StrategyStatusMeta = {
  code: string;
  label: string;
  variant: BadgeVariant;
};

export type StrategyIncubationStageFilter =
  | 'all'
  | 'not_started'
  | 'warmup'
  | 'observe'
  | 'candidate'
  | 'graduation_ready'
  | 'promoted'
  | 'failed';

export type ResolvedIncubationSurface = {
  stage: StrategyStatusMeta;
  latestDecision: StrategyStatusMeta;
  executionAuditGate: StrategyStatusMeta;
  promotionReady: boolean;
  blockerCount: number;
  riskCount: number;
  enteredIncubator: boolean;
  summaryLine: string;
};

type ResolveIncubationSurfaceArgs = {
  strategyStatus?: string | null;
  incubationSurface?: StrategyIncubationSurface | null;
  overview?: IncubationOverviewResponse | null;
  account?: IncubationAccount | null;
  latestMetric?: IncubationMetric | null;
  latestPipelineSnapshot?: IncubationPipelineSnapshot | null;
};

type ResolveDisplayStatusArgs = {
  strategyStatus?: string | null;
  ownerState?: StrategyOwnerState | null;
  paperSessionState?: StrategyPaperSessionState | null;
};

const MARKET_STATUS_META: Record<string, StrategyStatusMeta> = {
  listed: { code: 'listed', label: '已上架', variant: 'success' },
  published: { code: 'listed', label: '已上架', variant: 'success' },
  incubating: { code: 'incubating', label: '孵化中', variant: 'info' },
  submitted: { code: 'submitted', label: '已提交', variant: 'warning' },
  draft: { code: 'draft', label: '草稿', variant: 'neutral' },
  rejected: { code: 'rejected', label: '已淘汰', variant: 'danger' },
  deprecated: { code: 'deprecated', label: '已退化', variant: 'danger' },
  suspended: { code: 'suspended', label: '已暂停', variant: 'warning' },
  archived: { code: 'archived', label: '已归档', variant: 'neutral' },
};

const INCUBATION_STAGE_META: Record<Exclude<StrategyIncubationStageFilter, 'all'>, StrategyStatusMeta> = {
  not_started: { code: 'not_started', label: '未入孵化', variant: 'neutral' },
  warmup: { code: 'warmup', label: '预热采样', variant: 'warning' },
  observe: { code: 'observe', label: '观察验证', variant: 'info' },
  candidate: { code: 'candidate', label: '候选晋级', variant: 'info' },
  graduation_ready: { code: 'graduation_ready', label: '晋级就绪', variant: 'success' },
  promoted: { code: 'promoted', label: '晋级完成', variant: 'success' },
  failed: { code: 'failed', label: '孵化失败', variant: 'danger' },
};

const DECISION_META: Record<string, StrategyStatusMeta> = {
  promote: { code: 'promote', label: '推进晋级', variant: 'success' },
  observe: { code: 'observe', label: '继续观察', variant: 'info' },
  halt: { code: 'halt', label: '暂停修复', variant: 'danger' },
};

const EXECUTION_AUDIT_GATE_META: Record<string, StrategyStatusMeta> = {
  passed: { code: 'passed', label: '执行审计已通过', variant: 'success' },
  bootstrap_ready: { code: 'bootstrap_ready', label: '执行样本待补齐', variant: 'warning' },
  pending: { code: 'pending', label: '执行审计待完成', variant: 'warning' },
  failed: { code: 'failed', label: '执行审计未通过', variant: 'danger' },
  failed_metrics: { code: 'failed_metrics', label: '执行指标未通过', variant: 'danger' },
  blocked: { code: 'blocked', label: '执行审计被阻塞', variant: 'danger' },
};

export const INCUBATION_STAGE_FILTER_OPTIONS: Array<{
  value: StrategyIncubationStageFilter;
  label: string;
}> = [
  { value: 'all', label: '全部' },
  { value: 'not_started', label: '未入孵化' },
  { value: 'warmup', label: '预热采样' },
  { value: 'observe', label: '观察验证' },
  { value: 'candidate', label: '候选晋级' },
  { value: 'graduation_ready', label: '晋级就绪' },
  { value: 'promoted', label: '晋级完成' },
  { value: 'failed', label: '孵化失败' },
];

function normalizeText(value: unknown) {
  return String(value ?? '').trim();
}

function normalizeStatusCode(value: unknown) {
  const code = normalizeText(value).toLowerCase();
  return code === 'published' ? 'listed' : code;
}

function normalizeStageCode(value: unknown): Exclude<StrategyIncubationStageFilter, 'all'> {
  const code = normalizeStatusCode(value);
  if (
    code === 'warmup'
    || code === 'observe'
    || code === 'candidate'
    || code === 'graduation_ready'
    || code === 'promoted'
    || code === 'failed'
  ) {
    return code;
  }
  return 'not_started';
}

function countIssues(value: unknown) {
  if (!Array.isArray(value)) return 0;
  return value.filter((item) => normalizeText(item)).length;
}

function resolveBoolean(value: unknown): boolean | null {
  if (typeof value === 'boolean') return value;
  if (value == null) return null;
  if (typeof value === 'number') return Boolean(value);
  const normalized = normalizeText(value).toLowerCase();
  if (['1', 'true', 'yes', 'y', 'on'].includes(normalized)) return true;
  if (['0', 'false', 'no', 'n', 'off'].includes(normalized)) return false;
  return null;
}

function formatFallbackLabel(value: string, empty = '-') {
  const normalized = normalizeText(value);
  return normalized ? normalized.replaceAll('_', ' ') : empty;
}

function isPersonalStrategy(ownerState?: StrategyOwnerState | null) {
  return Boolean(ownerState?.personal_strategy);
}

export function normalizeIncubationStageFilter(raw?: string | null): StrategyIncubationStageFilter {
  const normalized = normalizeStatusCode(raw);
  if (
    normalized === 'not_started'
    || normalized === 'warmup'
    || normalized === 'observe'
    || normalized === 'candidate'
    || normalized === 'graduation_ready'
    || normalized === 'promoted'
    || normalized === 'failed'
  ) {
    return normalized;
  }
  return 'all';
}

export function resolveMarketStatusMeta(status?: string | null): StrategyStatusMeta {
  const code = normalizeStatusCode(status);
  return MARKET_STATUS_META[code] ?? {
    code: code || 'unknown',
    label: formatFallbackLabel(code, '未知状态'),
    variant: 'neutral',
  };
}

export function resolveStrategyDisplayStatus({
  strategyStatus,
  ownerState,
  paperSessionState,
}: ResolveDisplayStatusArgs): StrategyStatusMeta {
  if (isPersonalStrategy(ownerState)) {
    if (paperSessionState?.has_session) {
      return { code: 'personal_paper', label: '个人测试中', variant: 'info' };
    }
    return { code: 'personal_draft', label: '个人草稿', variant: 'neutral' };
  }
  return resolveMarketStatusMeta(strategyStatus);
}

export function resolveIncubationSurface({
  strategyStatus,
  incubationSurface,
  overview,
  account,
  latestMetric,
  latestPipelineSnapshot,
}: ResolveIncubationSurfaceArgs): ResolvedIncubationSurface {
  const marketStatus = normalizeStatusCode(strategyStatus);
  const surface = incubationSurface ?? null;
  const stageCode = normalizeStageCode(
    surface?.pipeline_stage
      ?? latestPipelineSnapshot?.pipeline_stage
      ?? overview?.pipeline_stage
      ?? account?.stage
      ?? (marketStatus === 'listed' ? 'promoted' : marketStatus === 'incubating' ? 'observe' : 'not_started'),
  );

  const latestDecisionCode = normalizeStatusCode(
    surface?.latest_decision
      ?? latestPipelineSnapshot?.latest_decision
      ?? latestMetric?.decision,
  );
  const latestDecision = DECISION_META[latestDecisionCode] ?? {
    code: latestDecisionCode || 'unknown',
    label: formatFallbackLabel(latestDecisionCode, '暂无决策'),
    variant: latestDecisionCode ? 'neutral' : 'neutral',
  };

  const executionAuditGateCode = normalizeStatusCode(
    surface?.execution_audit_gate_status
      ?? overview?.execution_audit_gate_status
      ?? latestPipelineSnapshot?.hard_gate_result?.execution_audit_gate_status
      ?? (latestPipelineSnapshot?.summary as Record<string, unknown> | undefined)?.execution_audit_gate_status,
  );
  const executionAuditGate = EXECUTION_AUDIT_GATE_META[executionAuditGateCode] ?? {
    code: executionAuditGateCode || 'unknown',
    label: formatFallbackLabel(executionAuditGateCode, '执行审计未知'),
    variant: executionAuditGateCode ? 'neutral' : 'neutral',
  };

  const blockerCount = surface?.blocker_count ?? countIssues(overview?.blockers ?? latestPipelineSnapshot?.blockers);
  const riskCount = surface?.risk_count ?? countIssues(overview?.risk_flags ?? latestPipelineSnapshot?.risk_flags);
  const promotionReady = resolveBoolean(surface?.promotion_ready) ?? resolveBoolean(overview?.promotion_ready) ?? (
    stageCode === 'graduation_ready' || stageCode === 'promoted'
  );
  const enteredIncubator = resolveBoolean(surface?.entered_incubator) ?? (
    stageCode !== 'not_started'
    || ['incubating', 'listed', 'deprecated', 'suspended'].includes(marketStatus)
  );

  const summaryParts = [
    latestDecision.label !== '暂无决策' ? latestDecision.label : null,
    `${blockerCount} 个阻塞`,
    `${riskCount} 个风险`,
  ].filter((item): item is string => Boolean(item));

  return {
    stage: INCUBATION_STAGE_META[stageCode],
    latestDecision,
    executionAuditGate,
    promotionReady: Boolean(promotionReady),
    blockerCount,
    riskCount,
    enteredIncubator: Boolean(enteredIncubator),
    summaryLine: summaryParts.join(' · '),
  };
}

export function resolveIncubationStageFilterLabel(filter: StrategyIncubationStageFilter) {
  return INCUBATION_STAGE_FILTER_OPTIONS.find((item) => item.value === filter)?.label ?? '全部';
}

export function matchesIncubationStageFilter(strategy: Strategy, filter: StrategyIncubationStageFilter) {
  if (filter === 'all') return true;
  const surface = resolveIncubationSurface({
    strategyStatus: strategy.status,
    incubationSurface: strategy.incubation_surface,
  });
  return surface.stage.code === filter;
}
