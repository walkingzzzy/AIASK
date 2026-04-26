'use client';

import { useMemo, useState } from 'react';
import type {
  McpJobAcceptedResponse,
  McpJobRecord,
  StrategyFactoryReadinessRemediation,
  StrategyManagerAction,
  StrategyOperatorJobRecord,
  StrategyOperatorParityResponse,
} from '@aiask/shared-types';
import { Badge, SectionCard } from '@/components/ui';
import { ErrorState, LoadingState } from '@/components/status-state';
import { useApiMutation } from '@/hooks/use-api-mutation';
import { useApiQuery } from '@/hooks/use-api-query';
import { apiKeys } from '@/lib/query-keys';

type OperatorAction = {
  action: StrategyManagerAction;
  label: string;
  description: string;
  params?: Record<string, unknown>;
  strategyScoped?: boolean;
};

const OPERATOR_ACTIONS: OperatorAction[] = [
  {
    action: 'factory_dispatch_run',
    label: '后台调度工厂',
    description: '提交一轮后台工厂调度，适合作为页面侧默认运行入口。',
  },
  {
    action: 'factory_run_once',
    label: '同步验收工厂',
    description: '高级验收动作，直接执行一次 factory_run_once 核验 submit stage。',
  },
  {
    action: 'publish',
    label: '发布策略',
    description: '将目标策略推进到 listed 状态。',
    strategyScoped: true,
  },
  {
    action: 'archive',
    label: '归档策略',
    description: '将目标策略归档，保留状态事件证据。',
    strategyScoped: true,
  },
  {
    action: 'submit',
    label: '提交策略',
    description: '将目标策略送入提交门禁。',
    strategyScoped: true,
  },
  {
    action: 'update_metrics',
    label: '更新策略指标',
    description: '按当前参数触发 update_metrics；需要额外指标时请从后台任务带入 params。',
    strategyScoped: true,
    params: { period: 'all', metrics: {}, source: 'strategy_operator_console' },
  },
  {
    action: 'lifecycle_scan',
    label: '生命周期扫描',
    description: '扫描策略生命周期异常并生成治理证据。',
  },
  {
    action: 'incubation_pipeline_run',
    label: '运行孵化流水线',
    description: '补齐孵化指标、forward window 和 promotion 输入。',
    params: { limit: 200, source: 'strategy_operator_console' },
  },
  {
    action: 'promotion_review_run',
    label: '运行晋级评审',
    description: '对目标策略补 promotion review 证据。',
    strategyScoped: true,
    params: { auto_apply: false, source: 'strategy_operator_console' },
  },
  {
    action: 'execution_audit_acceptance',
    label: '执行审计验收',
    description: '重算目标策略 execution audit acceptance。',
    strategyScoped: true,
    params: { backfill: true },
  },
  {
    action: 'incubation_sync_run',
    label: '补 production samples',
    description: '按历史信号 replay 真实 paper/incubation 样本，强制平仓后复验 execution audit。',
    strategyScoped: true,
    params: {
      replay_history: true,
      include_market_days: true,
      max_dates: 3000,
      force_close_open_positions: true,
      run_acceptance: true,
      source: 'strategy_operator_console',
    },
  },
  {
    action: 'submission_replay',
    label: '提交重放',
    description: '对目标策略执行 submission replay。',
    strategyScoped: true,
  },
  {
    action: 'runtime_cycle_run',
    label: '运行 runtime cycle',
    description: '触发运行态风控闭环。',
  },
  {
    action: 'vector_reconcile',
    label: '向量索引对账',
    description: '复查向量 profile 与索引快照一致性。',
    params: { limit_profiles: 500 },
  },
  {
    action: 'vector_rebuild',
    label: '重建向量索引',
    description: '重建 strategy_behavior 索引，用于修复索引健康异常。',
    params: { index_name: 'strategy_behavior', limit: 500, source: 'strategy_operator_console' },
  },
  {
    action: 'vector_cleanup',
    label: '清理向量历史',
    description: '默认 dry-run 清理，先检查待清理范围再执行非 dry-run。',
    params: { index_name: 'strategy_behavior', dry_run: true, keep_versions: 3, source: 'strategy_operator_console' },
  },
  {
    action: 'domain_projection_rebuild',
    label: '重建领域投影',
    description: '重放领域事件并刷新 projection snapshot。',
    params: { limit: 300, source: 'strategy_operator_console' },
  },
  {
    action: 'ai_generate',
    label: 'AI 生成候选',
    description: '生成候选策略但不自动提交。',
    params: { limit: 3, auto_submit: false },
  },
];

function asRecord(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return {};
  return value as Record<string, unknown>;
}

function asStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.map((item) => String(item ?? '').trim()).filter(Boolean);
}

function collectReadinessCodes(...sources: unknown[]) {
  const keys = [
    'factory_readiness_effective_blocking_reason_codes',
    'factory_readiness_blocking_reason_codes',
    'factory_readiness_warning_reason_codes',
    'blocking_reason_codes',
    'warning_reason_codes',
  ];
  const codes = new Set<string>();
  const visit = (source: unknown) => {
    const record = asRecord(source);
    for (const key of keys) {
      asStringArray(record[key]).forEach((code) => codes.add(code));
    }
    const summary = asRecord(record.summary);
    if (Object.keys(summary).length > 0) visit(summary);
    const lastSummary = asRecord(record.last_summary);
    if (Object.keys(lastSummary).length > 0) visit(lastSummary);
    const readiness = asRecord(record.readiness);
    if (Object.keys(readiness).length > 0) visit(readiness);
  };
  sources.forEach(visit);
  return Array.from(codes);
}

function jobStatusVariant(status: string): 'success' | 'warning' | 'danger' | 'info' | 'neutral' {
  if (status === 'succeeded') return 'success';
  if (status === 'failed') return 'danger';
  if (status === 'running') return 'warning';
  if (status === 'queued') return 'info';
  return 'neutral';
}

function resolveRemediation(
  code: string,
  remediations: StrategyFactoryReadinessRemediation[],
): StrategyFactoryReadinessRemediation | null {
  return remediations.find((item) => item.code === code) ?? null;
}

export function StrategyMarketOperatorPanel({
  enabled,
  factoryStatus,
  latestRun,
}: {
  enabled: boolean;
  factoryStatus: unknown;
  latestRun: unknown;
}) {
  const [targetStrategyId, setTargetStrategyId] = useState('');
  const [lastJobId, setLastJobId] = useState<string | null>(null);
  const [lastMcpJobId, setLastMcpJobId] = useState<string | null>(null);

  const parityQ = useApiQuery<StrategyOperatorParityResponse>(
    enabled ? '/strategy-market/operator/parity' : null,
    {
      enabled,
      refetchInterval: 60000,
      critical: true,
    },
  );
  const executionAuditQ = useApiQuery<Record<string, unknown>>(
    enabled ? '/strategy-market/execution-audit/verification' : null,
    {
      enabled,
      refetchInterval: 60000,
      nonFatal: true,
    },
  );
  const jobQ = useApiQuery<StrategyOperatorJobRecord>(
    enabled && lastJobId ? `/strategy-market/operator/jobs/${encodeURIComponent(lastJobId)}` : null,
    {
      enabled: enabled && Boolean(lastJobId),
      refetchInterval: 2500,
      nonFatal: true,
    },
  );
  const mcpJobQ = useApiQuery<McpJobRecord>(
    enabled && lastMcpJobId ? `/mcp/jobs/${encodeURIComponent(lastMcpJobId)}` : null,
    {
      enabled: enabled && Boolean(lastMcpJobId),
      refetchInterval: 2500,
      nonFatal: true,
    },
  );
  const operatorJobApi = useApiMutation<StrategyOperatorJobRecord>({
    critical: true,
    invalidates: [apiKeys.strategy()],
    successToast: '运营任务已提交，可在任务队列查看状态',
    onSuccess: (record) => {
      setLastJobId(record.job.job_id);
    },
  });
  const factorSchedulerApi = useApiMutation<McpJobAcceptedResponse>({
    critical: true,
    invalidates: [apiKeys.strategy()],
    successToast: 'MCP 因子治理任务已提交',
    onSuccess: (record) => {
      setLastMcpJobId(record.job.job_id);
    },
  });

  const parity = parityQ.data;
  const readinessCodes = useMemo(() => collectReadinessCodes(factoryStatus, latestRun), [factoryStatus, latestRun]);
  const remediations = parity?.readiness_remediations ?? [];
  const activeJob = jobQ.data ?? operatorJobApi.data;
  const activeMcpJob = mcpJobQ.data ?? factorSchedulerApi.data?.job ?? null;
  const executionAuditRoot = asRecord(executionAuditQ.data);
  const executionAuditDegraded = Boolean(executionAuditRoot.degraded);
  const verification = asRecord(executionAuditRoot.verification);
  const verificationSummary = asRecord(verification.summary);
  const verificationSchema = asRecord(verification.schema);
  const schemaReady = Boolean(
    verificationSchema.all_required_tables_present ?? verificationSchema.all_required_columns_present,
  );
  const mappedPct = parity && parity.total_actions > 0 ? Math.round((parity.mapped_actions / parity.total_actions) * 100) : 0;

  async function submitOperatorAction(action: OperatorAction) {
    const strategyId = targetStrategyId.trim();
    if (action.strategyScoped && !strategyId) {
      window.alert('这个动作需要先填写目标 strategy_id');
      return;
    }
    const confirmed = window.confirm(`确认提交高权限动作 ${action.action}？`);
    if (!confirmed) return;
    await operatorJobApi.triggerAsync(
      '/strategy-market/operator/jobs',
      { method: 'POST' },
      {
        action: action.action,
        strategy_id: strategyId || undefined,
        params: action.params ?? {},
        confirmed: true,
        confirmation_text: action.action,
        reason: 'strategy_market_operator_panel',
        timeout_ms: ['factory_run_once', 'incubation_sync_run', 'incubation_pipeline_run', 'promotion_review_run', 'lifecycle_scan', 'vector_rebuild'].includes(action.action)
          ? 300000
          : 120000,
      },
    );
  }

  if (!enabled) return null;

  return (
    <SectionCard className="mt-0" data-testid="strategy-market-operator-panel">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="eyebrow">Operator Closure</div>
          <h2 className="mt-2">MCP / 策略工厂运营闭环</h2>
          <p className="mb-0 mt-2 text-sm leading-7 text-text-secondary">
            管理员在这里查看 action parity、readiness 修复路径、execution audit 和后台任务状态。
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Badge variant={parity?.core_unmapped_actions === 0 ? 'success' : 'danger'}>
            核心未映射 {parity?.core_unmapped_actions ?? '-'}
          </Badge>
          <Badge variant={parity?.unmapped_actions === 0 ? 'success' : 'warning'}>
            总匹配 {parity ? `${mappedPct}%` : '-'}
          </Badge>
          <Badge variant="info">任务化动作 {parity?.job_actions ?? '-'}</Badge>
        </div>
      </div>

      {parityQ.isPending ? <LoadingState text="加载策略工厂匹配矩阵..." /> : null}
      {parityQ.error ? <ErrorState text={parityQ.error} /> : null}

      {parity ? (
        <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <div className="metric-tile rounded-[24px] px-4 py-4">
            <div className="metric-label">合约动作</div>
            <div className="mt-2 text-base font-semibold text-text-primary">{parity.total_actions}</div>
          </div>
          <div className="metric-tile rounded-[24px] px-4 py-4">
            <div className="metric-label">已映射</div>
            <div className="mt-2 text-base font-semibold text-text-primary">{parity.mapped_actions}</div>
          </div>
          <div className="metric-tile rounded-[24px] px-4 py-4">
            <div className="metric-label">核心动作</div>
            <div className="mt-2 text-base font-semibold text-text-primary">{parity.core_actions}</div>
          </div>
          <div className="metric-tile rounded-[24px] px-4 py-4">
            <div className="metric-label">高权限任务</div>
            <div className="mt-2 text-base font-semibold text-text-primary">{parity.job_actions}</div>
          </div>
        </div>
      ) : null}

      <div className="mt-4 grid gap-4 xl:grid-cols-[1fr_1.25fr]">
        <div className="rounded border border-border bg-surface-alt px-4 py-4">
          <div className="flex items-center justify-between gap-3">
            <h3 className="m-0 text-sm font-semibold text-text-primary">Readiness blockers</h3>
            <Badge variant={readinessCodes.length ? 'warning' : 'success'}>
              {readinessCodes.length ? `${readinessCodes.length} 个待处理` : '未见阻断'}
            </Badge>
          </div>
          <div className="mt-3 space-y-2">
            {readinessCodes.length ? (
              readinessCodes.map((code) => {
                const remediation = resolveRemediation(code, remediations);
                return (
                  <div key={code} className="rounded border border-border bg-surface px-3 py-3 text-xs">
                    <div className="font-medium text-text-primary">{code}</div>
                    <div className="mt-1 leading-5 text-text-secondary">
                      {remediation?.description ?? '当前 blocker 没有专用修复动作，先复查最新 factory run detail。'}
                    </div>
                    {remediation ? (
                      <div className="mt-2 flex flex-wrap items-center gap-2">
                        <Badge variant="info">{remediation.label}</Badge>
                        <span className="text-text-secondary">{remediation.endpoint}</span>
                      </div>
                    ) : null}
                  </div>
                );
              })
            ) : (
              <p className="mb-0 text-sm text-text-secondary">当前工厂状态没有暴露 readiness blocker。</p>
            )}
          </div>
        </div>

        <div className="rounded border border-border bg-surface-alt px-4 py-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h3 className="m-0 text-sm font-semibold text-text-primary">高权限任务</h3>
            <input
              value={targetStrategyId}
              onChange={(event) => setTargetStrategyId(event.target.value)}
              placeholder="strategy_id for scoped actions"
              className="min-w-[220px] rounded border border-border bg-surface px-3 py-2 text-xs text-text-primary outline-none"
            />
          </div>
          <div className="mt-3 grid gap-2 sm:grid-cols-2">
            <button
              type="button"
              onClick={() => {
                if (window.confirm('确认刷新因子调度并重建 governed registry 输入？')) {
                  factorSchedulerApi.trigger('/mcp/jobs', { method: 'POST' }, {
                    tool_name: 'quant_manager',
                    arguments: { action: 'scheduler_run_now' },
                    timeout_ms: 300000,
                    idempotency_key: `factor-scheduler-run-now-${Date.now()}`,
                  });
                }
              }}
              disabled={factorSchedulerApi.isPending}
              className="rounded border border-border bg-surface px-3 py-3 text-left text-xs text-text-primary disabled:opacity-50"
            >
              <span className="block font-medium">刷新 governed registry</span>
              <span className="mt-1 block leading-5 text-text-secondary">触发因子调度，为 active_pool 验证链刷新候选输入。</span>
            </button>
            <button
              type="button"
              onClick={() => {
                factorSchedulerApi.trigger('/mcp/jobs', { method: 'POST' }, {
                  tool_name: 'quant_manager',
                  arguments: {
                    action: 'factor_candidate_registry',
                    params: { op: 'active_pool', market_codes_only: true, limit: 200 },
                  },
                  timeout_ms: 120000,
                  idempotency_key: `factor-active-pool-${Date.now()}`,
                });
              }}
              disabled={factorSchedulerApi.isPending}
              className="rounded border border-border bg-surface px-3 py-3 text-left text-xs text-text-primary disabled:opacity-50"
            >
              <span className="block font-medium">核验 active_pool</span>
              <span className="mt-1 block leading-5 text-text-secondary">读取候选注册表 active_pool，用于确认 governed_freshness_days 不超过 3。</span>
            </button>
            {OPERATOR_ACTIONS.map((item) => (
              <button
                key={item.action}
                type="button"
                onClick={() => void submitOperatorAction(item)}
                disabled={operatorJobApi.isPending}
                className="rounded border border-border bg-surface px-3 py-3 text-left text-xs text-text-primary disabled:opacity-50"
              >
                <span className="block font-medium">{item.label}</span>
                <span className="mt-1 block leading-5 text-text-secondary">{item.description}</span>
              </button>
            ))}
          </div>
          {operatorJobApi.error ? <ErrorState text={operatorJobApi.error} /> : null}
          {factorSchedulerApi.error ? <ErrorState text={factorSchedulerApi.error} /> : null}
        </div>
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-2">
        <div className="rounded border border-border bg-surface-alt px-4 py-4">
          <div className="flex items-center justify-between gap-3">
            <h3 className="m-0 text-sm font-semibold text-text-primary">Execution audit verification</h3>
            <Badge variant={schemaReady ? 'success' : executionAuditQ.error || executionAuditDegraded ? 'warning' : 'info'}>
              {schemaReady ? 'schema ready' : executionAuditQ.error || executionAuditDegraded ? '读取降级' : '待核验'}
            </Badge>
          </div>
          {executionAuditQ.isPending ? <LoadingState text="读取 execution audit verification..." /> : null}
          <div className="mt-3 grid gap-2 sm:grid-cols-3">
            <div className="metric-tile rounded-[18px] px-3 py-3">
              <div className="metric-label">策略数</div>
              <div className="mt-2 text-sm font-semibold text-text-primary">
                {String(verificationSummary.strategy_count ?? '-')}
              </div>
            </div>
            <div className="metric-tile rounded-[18px] px-3 py-3">
              <div className="metric-label">Ready</div>
              <div className="mt-2 text-sm font-semibold text-text-primary">
                {String(verificationSummary.ready_count ?? '-')}
              </div>
            </div>
            <div className="metric-tile rounded-[18px] px-3 py-3">
              <div className="metric-label">Blockers</div>
              <div className="mt-2 text-sm font-semibold text-text-primary">
                {String(verificationSummary.blocker_count ?? '-')}
              </div>
            </div>
          </div>
          {executionAuditQ.error ? <p className="mb-0 mt-3 text-xs text-warning">{executionAuditQ.error}</p> : null}
          {executionAuditDegraded ? (
            <p className="mb-0 mt-3 text-xs text-warning">
              {String(asRecord(executionAuditRoot.error).message ?? 'execution audit verification 暂时不可用')}
            </p>
          ) : null}
        </div>

        <div className="rounded border border-border bg-surface-alt px-4 py-4" data-testid="strategy-operator-job-queue">
          <div className="flex items-center justify-between gap-3">
            <h3 className="m-0 text-sm font-semibold text-text-primary">MCP Job 队列</h3>
            <Badge variant={jobStatusVariant(String(activeJob?.job.status ?? activeMcpJob?.status ?? 'idle'))}>
              {activeJob?.job.status ?? activeMcpJob?.status ?? 'idle'}
            </Badge>
          </div>
          {activeJob ? (
            <div className="mt-3 space-y-2 text-xs text-text-secondary">
              <div>
                <span className="font-medium text-text-primary">{activeJob.action}</span>
                {' · '}
                {activeJob.job.job_id}
              </div>
              <div>提交时间：{activeJob.job.submitted_at}</div>
              <div>轮询路径：{activeJob.poll_path}</div>
              {activeJob.strategy_id ? <div>目标策略：{activeJob.strategy_id}</div> : null}
              {activeJob.job.error ? <div className="text-danger">错误：{activeJob.job.error}</div> : null}
            </div>
          ) : null}
          {activeMcpJob ? (
            <div className="mt-3 space-y-2 border-t border-border pt-3 text-xs text-text-secondary">
              <div>
                <span className="font-medium text-text-primary">{activeMcpJob.target.name}</span>
                {' · '}
                {activeMcpJob.job_id}
              </div>
              <div>提交时间：{activeMcpJob.submitted_at}</div>
              <div>轮询路径：{activeMcpJob.poll_path}</div>
              <div>超时阈值：{activeMcpJob.target.timeout_ms}ms</div>
              {activeMcpJob.error ? <div className="text-danger">错误：{activeMcpJob.error}</div> : null}
            </div>
          ) : null}
          {!activeJob && !activeMcpJob ? (
            <p className="mb-0 mt-3 text-sm text-text-secondary">还没有从当前操作台提交的 MCP Job。</p>
          ) : null}
          {mcpJobQ.error ? <p className="mb-0 mt-3 text-xs text-warning">{mcpJobQ.error}</p> : null}
        </div>
      </div>
    </SectionCard>
  );
}
