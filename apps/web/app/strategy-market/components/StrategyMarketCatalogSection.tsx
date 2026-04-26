'use client';

import Link from 'next/link';
import { Badge, DataTable, SectionCard, TabBar } from '@/components/ui';
import { StrategyCard } from '@/components/strategy-card';
import { fmtNum, fmtPct } from '@/lib/data-utils';
import { getStrategyMetricSnapshot } from '@/lib/strategy-metrics';
import type { Strategy, StrategyRuntimeActionContractItem } from '../types';
import { StrategyRuntimeActionBar } from './StrategyRuntimeActionBar';
import {
  INCUBATION_STAGE_FILTER_OPTIONS,
  resolveIncubationSurface,
  resolveIncubationStageFilterLabel,
  type StrategyIncubationStageFilter,
} from '../lib/incubation-surface';
import {
  CATEGORIES,
  resolveCategoryLabel,
  resolveStrategyStatusMeta,
  type StrategyMarketStatusCounts,
  type StrategyMarketStatusSegment,
  type StrategySortKey,
} from './strategy-market-support';

type StrategyMarketCatalogSectionProps = {
  category: string;
  setCategory: (value: string) => void;
  search: string;
  setSearch: (value: string) => void;
  showFeatured: boolean;
  setShowFeatured: (value: boolean) => void;
  sortBy: StrategySortKey;
  setSortBy: (value: StrategySortKey) => void;
  sortDir: 'desc' | 'asc';
  toggleSortDir: () => void;
  strategies: Strategy[];
  activeCategoryLabel: string;
  showStatusFilters?: boolean;
  statusSegment?: StrategyMarketStatusSegment;
  setStatusSegment?: (value: StrategyMarketStatusSegment) => void;
  statusCounts?: StrategyMarketStatusCounts;
  statusLabel?: string;
  statusHelpText?: string;
  incubationStageFilter?: StrategyIncubationStageFilter;
  setIncubationStageFilter?: (value: StrategyIncubationStageFilter) => void;
  catalogTotalCount?: number;
  featuredStrategies: Strategy[];
  onAddToCart: (strategy: Strategy) => void;
  onRuntimeAction: (action: StrategyRuntimeActionContractItem, strategy: Strategy) => void | Promise<void>;
  showPersonalTestingBadge?: boolean;
  showResults?: boolean;
  emptyText?: string;
};

function hasPersonalTestingSession(row: Record<string, unknown>) {
  const paperSessionState = row.paper_session_state;
  return Boolean(
    paperSessionState
    && typeof paperSessionState === 'object'
    && !Array.isArray(paperSessionState)
    && (paperSessionState as Record<string, unknown>).has_session === true,
  );
}

export function StrategyMarketCatalogSection({
  category,
  setCategory,
  search,
  setSearch,
  showFeatured,
  setShowFeatured,
  sortBy,
  setSortBy,
  sortDir,
  toggleSortDir,
  strategies,
  activeCategoryLabel,
  showStatusFilters = false,
  statusSegment = 'visible',
  setStatusSegment,
  statusCounts,
  statusLabel = '全部状态',
  statusHelpText = '',
  incubationStageFilter = 'all',
  setIncubationStageFilter,
  catalogTotalCount = strategies.length,
  featuredStrategies,
  onAddToCart,
  onRuntimeAction,
  showPersonalTestingBadge = false,
  showResults = true,
  emptyText = '暂无可展示策略',
}: StrategyMarketCatalogSectionProps) {
  const statusTabs = [
    { key: 'visible', label: `市场可见 ${statusCounts?.visible ?? 0}` },
    { key: 'submitted', label: `已提交 ${statusCounts?.submitted ?? 0}` },
    { key: 'draft', label: `草稿 ${statusCounts?.draft ?? 0}` },
    { key: 'rejected', label: `已淘汰 ${statusCounts?.rejected ?? 0}` },
    { key: 'archived', label: `已归档 ${statusCounts?.archived ?? 0}` },
    { key: 'all', label: `全部 ${statusCounts?.all ?? strategies.length}` },
  ] as const;

  const strategyColumns = [
    {
      key: 'name',
      label: '策略',
      render: (_: unknown, row: Record<string, unknown>) => {
        const strategy = row as Strategy;
        const showTesting = showPersonalTestingBadge && hasPersonalTestingSession(row);
        return (
          <div className="min-w-[200px]">
            <Link href={`/strategy-market/${strategy.id}`} className="no-underline text-inherit">
              <div className="flex flex-wrap items-center gap-2 font-semibold text-text-primary">
                <span>{strategy.name}</span>
                {showTesting ? <Badge variant="info">个人测试中</Badge> : null}
              </div>
              <div className="mt-1 text-xs text-text-secondary">
                {strategy.description || strategy.strategy_type || '暂无描述'}
              </div>
            </Link>
          </div>
        );
      },
    },
    {
      key: 'strategy_type',
      label: '类型',
      render: (value: unknown) => {
        const type = String(value ?? '其他');
        const label = resolveCategoryLabel(type);
        const variant =
          type === 'momentum' || type === 'ma_cross'
            ? 'info'
            : type === 'value'
              ? 'success'
              : type === 'quality' || type === 'quality_factor'
                ? 'warning'
                : 'neutral';
        return <Badge variant={variant}>{label}</Badge>;
      },
    },
    {
      key: 'status',
      label: '市场状态',
      render: (value: unknown) => {
        const meta = resolveStrategyStatusMeta(String(value ?? ''));
        return <Badge variant={meta.variant}>{meta.label}</Badge>;
      },
    },
    {
      key: 'incubation_stage',
      label: '孵化阶段',
      render: (_: unknown, row: Record<string, unknown>) => {
        const strategy = row as Strategy;
        const incubation = resolveIncubationSurface({
          strategyStatus: strategy.status,
          incubationSurface: strategy.incubation_surface,
        });
        return <Badge variant={incubation.stage.variant}>{incubation.stage.label}</Badge>;
      },
    },
    {
      key: 'incubation_summary',
      label: '孵化摘要',
      render: (_: unknown, row: Record<string, unknown>) => {
        const strategy = row as Strategy;
        const incubation = resolveIncubationSurface({
          strategyStatus: strategy.status,
          incubationSurface: strategy.incubation_surface,
        });
        return <div className="min-w-[180px] text-xs leading-6 text-text-secondary">{incubation.summaryLine}</div>;
      },
    },
    {
      key: 'annual_return',
      label: '回测年化',
      align: 'right' as const,
      render: (_: unknown, row: Record<string, unknown>) => {
        const value = Number(getStrategyMetricSnapshot(row as Strategy).totalReturn ?? 0);
        return <span className={value >= 0 ? 'text-success font-medium' : 'text-danger font-medium'}>{fmtPct(value)}</span>;
      },
    },
    {
      key: 'sharpe_ratio',
      label: 'Sharpe',
      align: 'right' as const,
      render: (_: unknown, row: Record<string, unknown>) => fmtNum(getStrategyMetricSnapshot(row as Strategy).sharpe ?? 0, 2),
    },
    {
      key: 'max_drawdown',
      label: '最大回撤',
      align: 'right' as const,
      render: (_: unknown, row: Record<string, unknown>) => (
        <span className="text-danger font-medium">{fmtPct(getStrategyMetricSnapshot(row as Strategy).maxDrawdown ?? 0)}</span>
      ),
    },
    {
      key: 'subscriber_count',
      label: '收藏',
      align: 'right' as const,
      render: (value: unknown) => String(value ?? 0),
    },
    {
      key: '_actions',
      label: '操作',
      sortable: false,
      render: (_: unknown, row: Record<string, unknown>) => {
        const strategy = row as Strategy;
        return (
          <div className="flex min-w-[280px] flex-col items-end gap-2">
            <Link
              href={`/strategy-market/${strategy.id}`}
              className="rounded-full border border-border bg-surface px-3 py-1 text-xs no-underline text-text-secondary"
            >
              详情
            </Link>
            <StrategyRuntimeActionBar
              contract={strategy.runtime_action_contract}
              compact
              onAction={(action) => onRuntimeAction(action, strategy)}
            />
          </div>
        );
      },
    },
  ];

  return (
    <>
      <SectionCard className="mt-0">
        <div className="flex flex-col gap-3">
          <div className="toolbar-strip">
            <div className="flex flex-1 flex-wrap items-center gap-2">
              <input
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="搜索策略名称 / 描述"
                aria-label="搜索策略名称、描述或类型"
                className="w-48 px-3 py-2 text-sm"
              />
              <span className="hidden text-xs text-text-muted sm:inline">排序</span>
              <select
                value={sortBy}
                onChange={(event) => setSortBy(event.target.value as StrategySortKey)}
                aria-label="排序字段"
                className="w-28 px-2 py-2 text-xs"
              >
                <option value="totalReturn">按回测年化</option>
                <option value="sharpe">按 Sharpe</option>
                <option value="maxDrawdown">按最大回撤</option>
                <option value="subscriber_count">按收藏数</option>
              </select>
              <button
                type="button"
                onClick={toggleSortDir}
                className="action-chip text-xs"
                title={sortDir === 'desc' ? '当前降序' : '当前升序'}
              >
                {sortDir === 'desc' ? '↓ 降序' : '↑ 升序'}
              </button>
              <select
                value={incubationStageFilter}
                onChange={(event) => setIncubationStageFilter?.(event.target.value as StrategyIncubationStageFilter)}
                aria-label="孵化阶段筛选"
                className="w-32 px-2 py-2 text-xs"
              >
                {INCUBATION_STAGE_FILTER_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
              <button type="button" onClick={() => setShowFeatured(!showFeatured)} className="action-chip ml-auto text-xs">
                {showFeatured ? '收起精选卡片' : '展开精选卡片'}
              </button>
              <Link href="/paper-trading?from=strategy-market" className="action-chip text-xs no-underline text-inherit">
                去模拟盘总览
              </Link>
              <Link href="/portfolio?from=strategy-market" className="action-chip text-xs no-underline text-inherit">
                去组合页创建组合
              </Link>
            </div>
          </div>
          <div className="rounded-[18px] border border-white/45 bg-white/24 px-4 py-3 text-xs leading-6 text-text-secondary">
            列表页当前只负责筛选、查看详情和加入组合。这里的收益字段统一是回测口径，真实模拟盘表现请进入详情页查看“个人模拟盘测试 / 孵化模拟盘”双卡；市场状态和孵化阶段会并列展示，帮助区分“是否处于市场生命周期可见态”和“在孵化器内部走到哪一步”。
          </div>
          {showStatusFilters ? (
            <div className="rounded-[20px] border border-white/45 bg-white/28 px-4 py-3">
              <div className="flex flex-wrap items-center gap-3">
                <div className="eyebrow mb-0">生命周期分层</div>
                <span className="text-xs text-text-muted">
                  当前分层 <span className="font-semibold text-text-primary">{statusLabel}</span> · 目录总量{' '}
                  <span className="font-semibold text-text-primary">{catalogTotalCount}</span>
                </span>
              </div>
              <div className="mt-3 overflow-x-auto">
                <TabBar
                  tabs={statusTabs}
                  active={statusSegment}
                  onChange={(value) => setStatusSegment?.(value as StrategyMarketStatusSegment)}
                />
              </div>
              <div className="mt-3 text-xs leading-6 text-text-secondary">{statusHelpText}</div>
            </div>
          ) : null}
          <div className="flex flex-wrap items-center gap-3">
            <div className="overflow-x-auto">
              <TabBar
                tabs={CATEGORIES}
                active={category}
                onChange={(value) => {
                  setCategory(value);
                  setSearch('');
                }}
              />
            </div>
            <span className="ml-auto shrink-0 text-xs text-text-muted">
              当前结果 <span className="font-semibold text-text-primary">{strategies.length}</span> 条
              {' '}· 孵化阶段 <span className="font-semibold text-text-primary">{resolveIncubationStageFilterLabel(incubationStageFilter)}</span>
              {showStatusFilters ? (
                <>
                  {' '}· 目录总量 <span className="font-semibold text-text-primary">{catalogTotalCount}</span> 条
                </>
              ) : null}
            </span>
          </div>
        </div>
      </SectionCard>

      {!showResults ? null : (
        <>
          {showFeatured ? (
            <SectionCard className="mt-0">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div className="eyebrow">精选策略卡片</div>
                  <h2 className="mt-1">前 3 个候选（按当前排序）</h2>
                </div>
                <div className="panel-soft rounded-[22px] px-4 py-3 text-sm text-text-secondary">
                  {showStatusFilters ? (
                    <>
                      分层：<span className="font-semibold text-text-primary">{statusLabel}</span> ·{' '}
                    </>
                  ) : null}
                  孵化阶段：<span className="font-semibold text-text-primary">{resolveIncubationStageFilterLabel(incubationStageFilter)}</span> ·{' '}
                  分类：<span className="font-semibold text-text-primary">{activeCategoryLabel}</span>
                </div>
              </div>
              {featuredStrategies.length ? (
                <div className="mt-4 grid gap-4 lg:grid-cols-3">
                  {featuredStrategies.map((strategy) => (
                    <StrategyCard
                      key={strategy.id}
                      s={strategy}
                      onAdd={(item) => onAddToCart(item)}
                      onRuntimeAction={onRuntimeAction}
                    />
                  ))}
                </div>
              ) : (
                <div className="mt-4 rounded-[18px] border border-dashed border-border bg-surface-alt/40 px-4 py-4 text-sm text-text-secondary">
                  当前分层或搜索条件下暂无可展示的精选策略，请切换状态分层或调整筛选条件。
                </div>
              )}
            </SectionCard>
          ) : null}

          <SectionCard className="mt-0" data-testid="strategy-market-catalog">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
              <div>
                <div className="eyebrow">全量目录</div>
                <h2 className="mt-1">策略表格视图</h2>
              </div>
              <span className="text-xs text-text-muted">
                当前结果 {strategies.length} 条
                {showStatusFilters ? (
                  <>
                    {' '}· 分层 <b className="text-text-primary">{statusLabel}</b> · 目录总量 {catalogTotalCount} 条 · 按{' '}
                  </>
                ) : (
                  <> · 按{' '}</>
                )}
                · 孵化阶段 <b className="text-text-primary">{resolveIncubationStageFilterLabel(incubationStageFilter)}</b> ·{' '}
                <b className="text-text-primary">
                  {sortBy === 'totalReturn'
                    ? '回测年化'
                    : sortBy === 'sharpe'
                      ? 'Sharpe'
                      : sortBy === 'maxDrawdown'
                        ? '最大回撤'
                        : '收藏数'}
                </b>{' '}
                {sortDir === 'desc' ? '降序' : '升序'}
              </span>
            </div>
            <DataTable
              rows={strategies as Record<string, unknown>[]}
              columns={strategyColumns}
              rowKey="id"
              maxHeight={560}
              emptyText={emptyText}
              mobileCardRender={(row) => {
                const strategy = row as Strategy;
                const metrics = getStrategyMetricSnapshot(strategy);
                const statusMeta = resolveStrategyStatusMeta(strategy.status);
                const showTesting = showPersonalTestingBadge && hasPersonalTestingSession(row);
                const incubation = resolveIncubationSurface({
                  strategyStatus: strategy.status,
                  incubationSurface: strategy.incubation_surface,
                });
                return (
                  <div className="space-y-3">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <Link href={`/strategy-market/${strategy.id}`} className="no-underline text-inherit">
                          <div className="flex flex-wrap items-center gap-2 text-sm font-semibold text-text-primary">
                            <span>{strategy.name}</span>
                            {showTesting ? <Badge variant="info">个人测试中</Badge> : null}
                          </div>
                        </Link>
                        <div className="mt-1 text-xs text-text-secondary">
                          {strategy.description || strategy.strategy_type || '暂无描述'}
                        </div>
                      </div>
                      <div className="flex flex-wrap items-center justify-end gap-2">
                        <Badge variant="neutral">{resolveCategoryLabel(strategy.strategy_type)}</Badge>
                        <Badge variant={statusMeta.variant}>{statusMeta.label}</Badge>
                        <Badge variant={incubation.stage.variant}>{incubation.stage.label}</Badge>
                      </div>
                    </div>
                    <div className="rounded-[14px] border border-border bg-surface-alt/50 px-3 py-2 text-[11px] leading-5 text-text-secondary">
                      {incubation.summaryLine}
                    </div>
                    <div className="grid grid-cols-3 gap-2 text-xs text-text-secondary">
                      <div>
                        <div className="metric-label">回测年化</div>
                        <div className={`mt-2 text-sm font-semibold ${(metrics.totalReturn ?? 0) >= 0 ? 'text-success' : 'text-danger'}`}>
                          {fmtPct(metrics.totalReturn ?? 0)}
                        </div>
                      </div>
                      <div>
                        <div className="metric-label">Sharpe</div>
                        <div className="mt-2 text-sm font-semibold text-text-primary">{fmtNum(metrics.sharpe ?? 0, 2)}</div>
                      </div>
                      <div>
                        <div className="metric-label">回撤</div>
                        <div className="mt-2 text-sm font-semibold text-danger">{fmtPct(metrics.maxDrawdown ?? 0)}</div>
                      </div>
                    </div>
                    <div className="space-y-2 border-t border-border pt-3 text-xs text-text-secondary">
                      <div className="flex items-center justify-between gap-2">
                        <span>{strategy.favorite_count ?? strategy.subscriber_count ?? 0} 人收藏 · 回测收益见此处，真实模拟盘看详情页</span>
                        <button
                          type="button"
                          onClick={() => onAddToCart(strategy)}
                          className="rounded-full bg-primary px-3 py-1.5 text-xs text-white shadow-sm"
                        >
                          加入组合
                        </button>
                      </div>
                      <StrategyRuntimeActionBar
                        contract={strategy.runtime_action_contract}
                        compact
                        onAction={(action) => onRuntimeAction(action, strategy)}
                      />
                    </div>
                  </div>
                );
              }}
            />
          </SectionCard>
        </>
      )}
    </>
  );
}
