'use client';

import Link from 'next/link';
import { FormEvent, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Badge, PageContainer, SectionCard } from '@/components/ui';
import { ErrorState, LoadingState } from '@/components/status-state';
import { useApiMutation } from '@/hooks/use-api-mutation';
import { useApiQuery } from '@/hooks/use-api-query';
import { useStableSearchParams } from '@/hooks/use-stable-search-params';
import { apiKeys } from '@/lib/query-keys';
import { parseCoreChainAcceptanceResponse } from '../lib/contracts';
import type {
  StrategyCoreChainAcceptanceResponse,
  StrategyCoreChainStep,
  StrategyCoreChainStepStatus,
} from '../types';

function statusLabel(status: StrategyCoreChainStepStatus) {
  switch (status) {
    case 'passed':
      return '已打通';
    case 'ready':
      return '可执行';
    case 'degraded':
      return '降级';
    case 'blocked':
    default:
      return '阻断';
  }
}

function statusVariant(status: StrategyCoreChainStepStatus): 'success' | 'warning' | 'danger' | 'info' | 'neutral' {
  if (status === 'passed') return 'success';
  if (status === 'ready') return 'info';
  if (status === 'degraded') return 'warning';
  if (status === 'blocked') return 'danger';
  return 'neutral';
}

function formatTime(value: string | null | undefined) {
  if (!value) return '-';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString('zh-CN', { hour12: false });
}

function isRunnablePost(step: StrategyCoreChainStep) {
  return step.action.method !== 'GET' && !step.action.path.includes(':id') && step.can_complete;
}

function StepAction({
  step,
  pending,
  onRun,
}: {
  step: StrategyCoreChainStep;
  pending: boolean;
  onRun: (step: StrategyCoreChainStep) => void;
}) {
  if (step.action.method === 'GET') {
    return (
      <Link
        href={step.action.href || step.action.path}
        className="rounded-full border border-border bg-surface px-3 py-1.5 text-xs font-medium text-text-primary no-underline"
      >
        {step.action.label}
      </Link>
    );
  }
  return (
    <button
      type="button"
      disabled={!isRunnablePost(step) || pending}
      onClick={() => onRun(step)}
      className="rounded-full border border-primary/20 bg-primary px-3 py-1.5 text-xs font-medium text-white disabled:cursor-not-allowed disabled:border-border disabled:bg-surface-alt disabled:text-text-muted"
    >
      {pending ? '执行中' : step.action.label}
    </button>
  );
}

export default function StrategyCoreChainDiagnosticsPage() {
  const router = useRouter();
  const searchParams = useStableSearchParams();
  const strategyId = searchParams.get('strategy_id')?.trim() ?? '';
  const personalStrategyId = searchParams.get('personal_strategy_id')?.trim() ?? '';
  const [strategyInput, setStrategyInput] = useState(strategyId);
  const [personalInput, setPersonalInput] = useState(personalStrategyId);
  const queryPath = useMemo(() => {
    const qs = new URLSearchParams();
    if (strategyId) qs.set('strategy_id', strategyId);
    if (personalStrategyId) qs.set('personal_strategy_id', personalStrategyId);
    const tail = qs.toString();
    return `/strategy-market/diagnostics/core-chain${tail ? `?${tail}` : ''}`;
  }, [personalStrategyId, strategyId]);

  const diagnosticsQ = useApiQuery<StrategyCoreChainAcceptanceResponse>(queryPath, {
    critical: true,
    parse: parseCoreChainAcceptanceResponse,
    refetchInterval: 30000,
  });
  const runStepApi = useApiMutation<Record<string, unknown>>({
    invalidates: [apiKeys.strategy()],
    successToast: '链路动作已执行，正在刷新诊断状态',
    onSuccess: () => {
      void diagnosticsQ.refetch();
    },
  });

  const diagnostics = diagnosticsQ.data;
  const summary = diagnostics?.summary;
  const passedSteps = diagnostics?.steps.filter((step) => step.status === 'passed') ?? [];
  const readySteps = diagnostics?.steps.filter((step) => step.status === 'ready') ?? [];
  const brokenSteps = diagnostics?.steps.filter((step) => step.status === 'blocked' || step.status === 'degraded') ?? [];

  function applyTarget(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const qs = new URLSearchParams();
    if (strategyInput.trim()) qs.set('strategy_id', strategyInput.trim());
    if (personalInput.trim()) qs.set('personal_strategy_id', personalInput.trim());
    router.push(`/strategy-market/diagnostics${qs.toString() ? `?${qs.toString()}` : ''}`);
  }

  function runStep(step: StrategyCoreChainStep) {
    if (!isRunnablePost(step)) return;
    const confirmed = window.confirm(`确认执行 ${step.title}：${step.action.label}？`);
    if (!confirmed) return;
    runStepApi.trigger(step.action.path, { method: step.action.method }, step.action.body ?? {});
  }

  return (
    <PageContainer className="space-y-5">
      <SectionCard className="mt-0">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="eyebrow">核心链路诊断</div>
            <h1 className="mt-2 mb-0">策略核心链路诊断</h1>
            <div className="mt-2 flex flex-wrap gap-2">
              <Badge variant={summary ? statusVariant(summary.overall_status) : 'neutral'}>
                {summary ? statusLabel(summary.overall_status) : '加载中'}
              </Badge>
              <Badge variant={summary?.runnable ? 'success' : 'warning'}>
                {summary?.runnable ? '当前可跑完整链路' : '当前链路不完整'}
              </Badge>
              <Badge variant={diagnostics?.environment.mcp_reachable ? 'success' : 'danger'}>
                MCP {diagnostics?.environment.mcp_reachable ? '可达' : '不可达'}
              </Badge>
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <Link className="rounded-full border border-border px-3 py-1.5 text-xs no-underline" href="/strategy-market">
              策略超市
            </Link>
            <button
              type="button"
              onClick={() => diagnosticsQ.refetch()}
              className="rounded-full border border-border bg-surface px-3 py-1.5 text-xs"
            >
              刷新
            </button>
          </div>
        </div>

        <form onSubmit={applyTarget} className="mt-5 grid gap-3 lg:grid-cols-[1fr_1fr_auto]">
          <label className="grid gap-1 text-xs text-text-secondary">
            <span>市场策略 ID</span>
            <input
              value={strategyInput}
              onChange={(event) => setStrategyInput(event.target.value)}
              placeholder="留空自动选取榜单第一条"
              className="w-full text-sm text-text-primary"
            />
          </label>
          <label className="grid gap-1 text-xs text-text-secondary">
            <span>个人策略 ID</span>
            <input
              value={personalInput}
              onChange={(event) => setPersonalInput(event.target.value)}
              placeholder="可选，用于指定我的策略草稿"
              className="w-full text-sm text-text-primary"
            />
          </label>
          <div className="flex items-end">
            <button type="submit" className="w-full rounded-full border border-primary/20 bg-primary px-4 py-2 text-sm font-medium text-white">
              应用目标
            </button>
          </div>
        </form>
      </SectionCard>

      {diagnosticsQ.isPending ? <LoadingState text="加载核心链路诊断状态..." /> : null}
      {diagnosticsQ.error ? <ErrorState text={diagnosticsQ.error} onRetry={() => diagnosticsQ.refetch()} /> : null}

      {diagnostics ? (
        <>
          <SectionCard>
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
              <div className="metric-tile rounded-[24px] px-4 py-4">
                <div className="metric-label">完成步骤</div>
                <div className="mt-2 text-base font-semibold text-text-primary">
                  {summary?.completed_steps ?? 0} / {diagnostics.steps.length}
                </div>
              </div>
              <div className="metric-tile rounded-[24px] px-4 py-4">
                <div className="metric-label">可执行待完成</div>
                <div className="mt-2 text-base font-semibold text-text-primary">{readySteps.length}</div>
              </div>
              <div className="metric-tile rounded-[24px] px-4 py-4">
                <div className="metric-label">阻断/降级</div>
                <div className="mt-2 text-base font-semibold text-text-primary">{brokenSteps.length}</div>
              </div>
              <div className="metric-tile rounded-[24px] px-4 py-4">
                <div className="metric-label">最近刷新</div>
                <div className="mt-2 text-base font-semibold text-text-primary">{formatTime(diagnostics.generated_at)}</div>
              </div>
            </div>
            <div className="mt-4 flex flex-wrap gap-2 text-xs text-text-secondary">
              <span className="rounded-full border border-border bg-surface-alt px-3 py-1">
                市场策略 {diagnostics.target.market_strategy_id ?? '-'}
              </span>
              <span className="rounded-full border border-border bg-surface-alt px-3 py-1">
                个人策略 {diagnostics.target.personal_strategy_id ?? '-'}
              </span>
              <span className="rounded-full border border-border bg-surface-alt px-3 py-1">
                当前用户 {diagnostics.actor.user_id}
              </span>
            </div>
          </SectionCard>

          <div className="grid gap-4">
            {diagnostics.steps.map((step) => (
              <SectionCard key={step.key} className="mt-0" data-testid={`core-chain-step-${step.key}`}>
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <div className="flex flex-wrap items-center gap-2">
                      <h2 className="m-0 text-lg">{step.title}</h2>
                      <Badge variant={statusVariant(step.status)}>{statusLabel(step.status)}</Badge>
                      <Badge variant={step.can_complete ? 'success' : 'warning'}>
                        {step.can_complete ? '可完成' : '不可完成'}
                      </Badge>
                    </div>
                    <p className="mb-0 mt-2 text-sm leading-7 text-text-secondary">{step.success_condition}</p>
                  </div>
                  <StepAction step={step} pending={runStepApi.isPending} onRun={runStep} />
                </div>

                <div className="mt-4 grid gap-3 lg:grid-cols-3">
                  <div className="rounded border border-border bg-surface-alt px-4 py-3">
                    <div className="metric-label">失败原因</div>
                    <div className="mt-2 text-sm leading-6 text-text-primary">{step.failure_reason ?? '无'}</div>
                  </div>
                  <div className="rounded border border-border bg-surface-alt px-4 py-3">
                    <div className="metric-label">最近成功时间</div>
                    <div className="mt-2 text-sm leading-6 text-text-primary">{formatTime(step.last_success_at)}</div>
                  </div>
                  <div className="rounded border border-border bg-surface-alt px-4 py-3">
                    <div className="metric-label">下一步动作</div>
                    <div className="mt-2 text-sm leading-6 text-text-primary">{step.next_action}</div>
                  </div>
                </div>

                <div className="mt-4 grid gap-3 lg:grid-cols-2">
                  <div>
                    <div className="metric-label">依赖缺口</div>
                    <div className="mt-2 flex flex-wrap gap-2">
                      {step.dependency_gaps.length ? (
                        step.dependency_gaps.map((gap) => (
                          <Badge key={gap} variant={step.status === 'passed' ? 'neutral' : 'warning'}>
                            {gap}
                          </Badge>
                        ))
                      ) : (
                        <Badge variant="success">无缺口</Badge>
                      )}
                    </div>
                  </div>
                  <div>
                    <div className="metric-label">证据来源</div>
                    <div className="mt-2 flex flex-wrap gap-2">
                      {step.sources.map((source) => (
                        <Badge key={source} variant="neutral">{source}</Badge>
                      ))}
                    </div>
                  </div>
                </div>

                {step.evidence.length ? (
                  <div className="mt-4 text-xs leading-6 text-text-secondary">
                    {step.evidence.map((item) => (
                      <span key={item} className="mr-3 inline-block">{item}</span>
                    ))}
                  </div>
                ) : null}
              </SectionCard>
            ))}
          </div>

          <SectionCard>
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <div className="eyebrow">当前结果</div>
                <h2 className="mt-2 mb-0">真实打通与断点</h2>
              </div>
              <Badge variant={summary?.fully_completed ? 'success' : 'info'}>
                {passedSteps.length} 已打通 / {diagnostics.steps.length}
              </Badge>
            </div>
            <div className="mt-4 grid gap-4 lg:grid-cols-3">
              <div>
                <div className="metric-label">已真实打通</div>
                <ul className="mt-2 space-y-1 pl-4 text-sm text-text-secondary">
                  {passedSteps.length ? passedSteps.map((step) => <li key={step.key}>{step.title}</li>) : <li>暂无</li>}
                </ul>
              </div>
              <div>
                <div className="metric-label">可执行但未完成</div>
                <ul className="mt-2 space-y-1 pl-4 text-sm text-text-secondary">
                  {readySteps.length ? readySteps.map((step) => <li key={step.key}>{step.title}</li>) : <li>暂无</li>}
                </ul>
              </div>
              <div>
                <div className="metric-label">仍然断着</div>
                <ul className="mt-2 space-y-1 pl-4 text-sm text-text-secondary">
                  {brokenSteps.length ? brokenSteps.map((step) => <li key={step.key}>{step.title}</li>) : <li>暂无</li>}
                </ul>
              </div>
            </div>
          </SectionCard>
        </>
      ) : null}
    </PageContainer>
  );
}
