'use client';

import Link from 'next/link';
import { Badge, DataTable, SectionCard, TabBar } from '@/components/ui';
import { StrategyCard } from '@/components/strategy-card';
import { fmtNum, fmtPct } from '@/lib/data-utils';
import { getStrategyMetricSnapshot } from '@/lib/strategy-metrics';
import type { Strategy } from '../types';
import { CATEGORIES, resolveCategoryLabel, type StrategySortKey } from './strategy-market-support';

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
  featuredStrategies: Strategy[];
  onAddToCart: (strategy: Strategy) => void;
  showResults?: boolean;
};

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
  featuredStrategies,
  onAddToCart,
  showResults = true,
}: StrategyMarketCatalogSectionProps) {
  const strategyColumns = [
    {
      key: 'name',
      label: '策略',
      render: (_: unknown, row: Record<string, unknown>) => {
        const strategy = row as Strategy;
        return (
          <div className="min-w-[200px]">
            <Link href={`/strategy-market/${strategy.id}`} className="no-underline text-inherit">
              <div className="font-semibold text-text-primary">{strategy.name}</div>
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
      key: 'annual_return',
      label: '年化收益',
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
      label: '订阅',
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
          <div className="flex justify-end gap-2">
            <Link
              href={`/strategy-market/${strategy.id}`}
              className="rounded-full border border-border bg-surface px-3 py-1 text-xs no-underline text-text-secondary"
            >
              详情
            </Link>
            <button
              type="button"
              onClick={() => onAddToCart(strategy)}
              className="rounded-full bg-primary px-3 py-1 text-xs text-white shadow-sm"
            >
              加入组合
            </button>
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
                <option value="totalReturn">按年化</option>
                <option value="sharpe">按 Sharpe</option>
                <option value="maxDrawdown">按最大回撤</option>
                <option value="subscriber_count">按订阅数</option>
              </select>
              <button
                type="button"
                onClick={toggleSortDir}
                className="action-chip text-xs"
                title={sortDir === 'desc' ? '当前降序' : '当前升序'}
              >
                {sortDir === 'desc' ? '↓ 降序' : '↑ 升序'}
              </button>
              <button type="button" onClick={() => setShowFeatured(!showFeatured)} className="action-chip ml-auto text-xs">
                {showFeatured ? '收起精选卡片' : '展开精选卡片'}
              </button>
              <Link href="/paper-trading?from=strategy-market" className="action-chip text-xs no-underline text-inherit">
                去模拟盘
              </Link>
              <Link href="/portfolio?from=strategy-market" className="action-chip text-xs no-underline text-inherit">
                去组合页
              </Link>
            </div>
          </div>
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
              共 <span className="font-semibold text-text-primary">{strategies.length}</span> 个策略
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
                  分类：<span className="font-semibold text-text-primary">{activeCategoryLabel}</span>
                </div>
              </div>
              <div className="mt-4 grid gap-4 lg:grid-cols-3">
                {featuredStrategies.map((strategy) => (
                  <StrategyCard key={strategy.id} s={strategy} onAdd={(item) => onAddToCart(item)} />
                ))}
              </div>
            </SectionCard>
          ) : null}

          <SectionCard className="mt-0">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
              <div>
                <div className="eyebrow">全量目录</div>
                <h2 className="mt-1">策略表格视图</h2>
              </div>
              <span className="text-xs text-text-muted">
                共 {strategies.length} 条 · 按{' '}
                <b className="text-text-primary">
                  {sortBy === 'totalReturn'
                    ? '年化'
                    : sortBy === 'sharpe'
                      ? 'Sharpe'
                      : sortBy === 'maxDrawdown'
                        ? '最大回撤'
                        : '订阅数'}
                </b>{' '}
                {sortDir === 'desc' ? '降序' : '升序'}
              </span>
            </div>
            <DataTable
              rows={strategies as Record<string, unknown>[]}
              columns={strategyColumns}
              rowKey="id"
              maxHeight={560}
              mobileCardRender={(row) => {
                const strategy = row as Strategy;
                const metrics = getStrategyMetricSnapshot(strategy);
                return (
                  <div className="space-y-3">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <Link href={`/strategy-market/${strategy.id}`} className="no-underline text-inherit">
                          <div className="text-sm font-semibold text-text-primary">{strategy.name}</div>
                        </Link>
                        <div className="mt-1 text-xs text-text-secondary">
                          {strategy.description || strategy.strategy_type || '暂无描述'}
                        </div>
                      </div>
                      <Badge variant="neutral">{resolveCategoryLabel(strategy.strategy_type)}</Badge>
                    </div>
                    <div className="grid grid-cols-3 gap-2 text-xs text-text-secondary">
                      <div>
                        <div className="metric-label">年化</div>
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
                    <div className="flex items-center justify-between gap-2 border-t border-border pt-3 text-xs text-text-secondary">
                      <span>{strategy.subscriber_count ?? 0} 人订阅</span>
                      <button
                        type="button"
                        onClick={() => onAddToCart(strategy)}
                        className="rounded-full bg-primary px-3 py-1.5 text-xs text-white shadow-sm"
                      >
                        加入组合
                      </button>
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
