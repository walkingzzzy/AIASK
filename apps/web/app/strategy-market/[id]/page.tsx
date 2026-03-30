'use client';

import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';
import { useEffect, useMemo } from 'react';
import { LineChart, BarChart } from '@/components/charts';
import WorkspaceSplitLayout from '@/components/workspace-split-layout';
import WorkspaceToolbar from '@/components/workspace-toolbar';
import { EmptyState, ErrorState, LoadingState } from '@/components/status-state';
import { Badge, KpiCard, KpiGrid, PageContainer, SectionCard, TabBar } from '@/components/ui';
import { usePageActions } from '@/hooks/use-page-actions';
import { usePageContext } from '@/hooks/use-page-context';
import { fmtNum, fmtPct } from '@/lib/data-utils';
import { useAuthStore } from '@/store/auth-store';
import { useCartStore } from '@/store/cart-store';
import { useWorkbenchStore } from '@/store/workbench-store';
import { FactoryReviewPanel } from '../components/FactoryReviewPanel';
import { LiveTrackingPanel } from '../components/LiveTrackingPanel';
import { useStrategyDetailPage } from '../hooks/use-strategy-detail-page';
import type { FactoryReviewSection } from '../types';

const DETAIL_TABS = [
  { key: 'overview', label: '策略概览' },
  { key: 'tracking', label: '实盘跟踪' },
  { key: 'factory', label: '工厂审查' },
] as const;

const FACTORY_SECTIONS: FactoryReviewSection[] = ['summary', 'incubation', 'runtime', 'vectors', 'experiments'];

function extractTraceId(text: string | null): string | null {
  const source = String(text ?? '');
  const match = source.match(/trace[_-]?[A-Za-z0-9]+/i) ?? source.match(/traceId:\s*([A-Za-z0-9_-]+)/i);
  if (!match) return null;
  return match[1] ?? match[0] ?? null;
}

function isMissingStrategyError(text: string | null): boolean {
  const source = String(text ?? '').toLowerCase();
  return (
    source.includes('404') ||
    source.includes('not_found') ||
    source.includes('strategy not found') ||
    source.includes('不存在') ||
    source.includes('未找到')
  );
}

function firstFiniteNumber(...values: Array<number | null | undefined>) {
  for (const value of values) {
    if (value != null && Number.isFinite(Number(value))) {
      return Number(value);
    }
  }
  return null;
}

function formatMultipleTestingMode(value?: string | null) {
  const mode = String(value ?? '').trim();
  if (!mode) return '-';
  if (mode === 'formal_runtime') return '正式论文实现';
  if (mode === 'paper_runtime') return '论文实现';
  if (mode === 'runtime_proxy') return '运行时代理';
  return mode.replaceAll('_', ' ');
}

export default function StrategyDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const addToCart = useCartStore((st) => st.addStrategy);
  const updateWorkbenchContext = useWorkbenchStore((state) => state.updateContext);
  const addWorkbenchTask = useWorkbenchStore((state) => state.addTask);
  const user = useAuthStore((st) => st.user);
  const userId = user?.id ?? user?.username ?? null;
  const {
    detailLoading,
    detailError,
    strategy,
    statusVariant,
    activeTab,
    setActiveTab,
    overview,
    trackingPanelProps,
    factoryPanelProps,
  } = useStrategyDetailPage(id ?? null, userId);

  const {
    metrics,
    allMetrics,
    reviews,
    navSeries,
    navCategories,
    factorBars,
    latestQualityReport,
    incubationAccount,
    latestIncubationMetric,
    paperAccount,
    latestPaperNav,
    paperNavRows,
    openRiskEvents,
    vectorProfiles,
    promotionReady,
    rating,
    setRating,
    comment,
    setComment,
    isSubscribed,
    subscribePending,
    reviewPending,
    handleSubscribe,
    handleReview,
  } = overview;

  const pageKey = 'strategy-detail';
  const activeTabLabel = DETAIL_TABS.find((item) => item.key === activeTab)?.label ?? '策略概览';
  const strategySummary =
    strategy?.description ||
    '先确认策略合同、质量门状态和当前孵化决策，再决定是加入组合、继续订阅，还是转到工厂审查继续追踪。';
  const portfolioHref = strategy?.id
    ? `/portfolio?from=strategy-detail&strategy_id=${encodeURIComponent(String(strategy.id))}`
    : '/portfolio';
  const paperHref = strategy?.id
    ? `/paper-trading?from=strategy-detail&strategy_id=${encodeURIComponent(String(strategy.id))}`
    : '/paper-trading';
  const heroPrimaryButtonCls =
    'inline-flex cursor-pointer items-center justify-center rounded-full bg-primary px-4 py-2 text-sm font-medium text-white shadow-[0_20px_40px_-24px_rgba(11,107,203,0.52)] transition hover:-translate-y-0.5 hover:shadow-[0_24px_46px_-24px_rgba(11,107,203,0.58)] disabled:cursor-not-allowed disabled:opacity-50';
  const heroSecondaryButtonCls =
    'action-chip cursor-pointer text-sm text-text-primary shadow-[0_16px_32px_-24px_rgba(15,23,42,0.28)]';
  const chipLinkCls = 'action-chip text-xs no-underline text-inherit';
  const chipButtonCls = 'action-chip cursor-pointer text-xs text-text-primary';
  const sidePanelCls = 'panel-soft rounded-[28px] p-4 sm:p-5';
  const sideMetricCls = 'metric-tile rounded-[22px] px-4 py-3';

  const currentView = useMemo(
    () => ({
      strategyId: strategy?.id ?? id ?? null,
      activeTab,
      factorySection: factoryPanelProps.activeSection,
      subscribed: isSubscribed,
    }),
    [activeTab, factoryPanelProps.activeSection, id, isSubscribed, strategy?.id],
  );

  useEffect(() => {
    if (!strategy) return;
    updateWorkbenchContext({
      strategyId: String(strategy.id),
      strategyName: strategy.name,
    });
  }, [strategy, updateWorkbenchContext]);

  usePageContext({
    pageKey,
    title: strategy?.name ? `策略详情 · ${strategy.name}` : '策略详情',
    summary: strategy
      ? `${strategy.name} 当前处于 ${strategy.status ?? '未知状态'}，当前工作流为 ${activeTabLabel}。订阅数 ${strategy.subscriber_count ?? 0}，风险事件 ${openRiskEvents.length}，向量画像 ${vectorProfiles.length}。`
      : detailLoading
        ? '策略详情加载中。'
        : detailError
          ? '策略详情暂时无法加载。'
          : '策略详情待初始化。',
    tags: [
      strategy?.status ? String(strategy.status) : null,
      activeTabLabel,
      strategy?.author_id ? `作者 ${strategy.author_id}` : null,
      strategy?.subscriber_count != null ? `${strategy.subscriber_count} 订阅` : null,
      latestQualityReport?.summary?.validation_grade ? `评级 ${latestQualityReport.summary.validation_grade}` : null,
    ].filter((item): item is string => Boolean(item)),
    suggestions: strategy
      ? [
          activeTab === 'overview' ? '切到实盘跟踪看信号与命中率' : '回概览确认样本期和质量门',
          activeTab === 'factory' ? '继续切换工厂审查分区' : '打开工厂审查看运行风控与实验事件',
          isSubscribed ? '取消订阅策略并返回列表继续筛选' : '订阅该策略并纳入后续跟踪',
        ]
      : ['返回策略超市', '重新加载策略详情'],
    raw: {
      strategyId: strategy?.id ?? id ?? null,
      activeTab,
      factorySection: factoryPanelProps.activeSection,
      subscribed: isSubscribed,
      riskEvents: openRiskEvents.length,
      vectorProfiles: vectorProfiles.length,
      promotionReady,
    },
  });

  const pageActions = useMemo(
    () => [
      {
        id: 'strategy-detail.open-market',
        label: '返回策略超市',
        description: '回到策略列表继续筛选和比较',
        keywords: ['策略超市', '返回列表'],
        scope: 'page' as const,
        pageKey,
        run: () => {
          router.push('/strategy-market');
          return { message: '已返回策略超市' };
        },
      },
      {
        id: 'strategy-detail.switch.overview',
        label: '切到策略概览',
        description: '查看样本期、质量门、净值轨迹和用户评价',
        keywords: ['概览', '质量门'],
        scope: 'page' as const,
        pageKey,
        run: () => {
          setActiveTab('overview');
          return { message: '已切到策略概览' };
        },
      },
      {
        id: 'strategy-detail.switch.tracking',
        label: '切到实盘跟踪',
        description: '查看信号统计、前向验证与历史信号',
        keywords: ['实盘跟踪', '信号'],
        scope: 'page' as const,
        pageKey,
        run: () => {
          setActiveTab('tracking');
          return { message: '已切到实盘跟踪' };
        },
      },
      {
        id: 'strategy-detail.switch.factory',
        label: '切到工厂审查',
        description: '查看工厂摘要、孵化闭环、运行风控和实验事件',
        keywords: ['工厂审查', '风控'],
        scope: 'page' as const,
        pageKey,
        run: () => {
          setActiveTab('factory');
          return { message: '已切到工厂审查' };
        },
      },
      {
        id: 'strategy-detail.subscribe',
        label: isSubscribed ? '取消订阅策略' : '订阅策略',
        description: '切换当前策略的订阅状态',
        keywords: ['订阅', '策略'],
        scope: 'page' as const,
        pageKey,
        run: async () => {
          if (!strategy) throw new Error('当前策略尚未加载完成');
          await handleSubscribe();
          return { message: isSubscribed ? `已取消订阅 ${strategy.name}` : `已订阅 ${strategy.name}` };
        },
      },
      {
        id: 'strategy-detail.add-to-portfolio',
        label: '加入组合并打开组合页',
        description: '将当前策略加入组合购物车并跳转到组合页继续配置',
        keywords: ['加入组合', '组合页'],
        scope: 'page' as const,
        pageKey,
        run: () => {
          if (!strategy) throw new Error('当前策略尚未加载完成');
          addToCart({ strategyId: strategy.id, name: strategy.name, weight: 0 });
          updateWorkbenchContext({
            strategyId: String(strategy.id),
            strategyName: strategy.name,
          });
          addWorkbenchTask({
            pageKey,
            title: `配置策略 ${strategy.name} 的组合权重`,
            href: portfolioHref,
            kind: 'portfolio-review',
            payload: { strategyId: strategy.id, strategyName: strategy.name },
          });
          router.push(portfolioHref);
          return { message: `已把 ${strategy.name} 加入组合并打开组合页` };
        },
      },
      {
        id: 'strategy-detail.open-paper',
        label: '打开模拟交易页',
        description: '切到模拟交易页查看该策略的交易联动',
        keywords: ['模拟交易', 'paper'],
        scope: 'page' as const,
        pageKey,
        run: () => {
          router.push(paperHref);
          return { message: '已打开模拟交易页' };
        },
      },
    ],
    [
      addToCart,
      addWorkbenchTask,
      handleSubscribe,
      isSubscribed,
      pageKey,
      paperHref,
      portfolioHref,
      router,
      setActiveTab,
      strategy,
      updateWorkbenchContext,
    ],
  );

  usePageActions(pageActions);

  if (detailLoading) {
    return (
      <PageContainer>
        <LoadingState text="加载策略详情..." />
      </PageContainer>
    );
  }

  const traceId = extractTraceId(detailError);
  const missingStrategy = !strategy || isMissingStrategyError(detailError);

  if (detailError || !strategy) {
    return (
      <PageContainer narrow>
        <SectionCard className="p-5 sm:p-6">
          <div className="mb-4">
            <Link href="/strategy-market" className="text-sm text-text-secondary no-underline hover:text-primary">
              &larr; 返回策略超市
            </Link>
          </div>
          {missingStrategy ? (
            <EmptyState
              text="策略不存在或已下架"
              hint={`你访问的策略 ID「${id ?? '-'}」目前不可用，可能是链接无效、策略已归档，或当前环境没有这条记录。`}
              action={
                <>
                  <Link href="/strategy-market" className={chipLinkCls}>
                    返回策略列表
                  </Link>
                  <button type="button" onClick={() => window.location.reload()} className={chipButtonCls}>
                    重新加载
                  </button>
                </>
              }
            />
          ) : (
            <>
              <ErrorState
                text="策略详情暂时无法加载"
                hint="可以先返回策略超市重新选择，或稍后再试；原始接口路径和技术细节已下沉到下方折叠区。"
              />
              <div className="mt-4 flex flex-wrap gap-2">
                <Link href="/strategy-market" className={chipLinkCls}>
                  返回策略列表
                </Link>
                <button type="button" onClick={() => window.location.reload()} className={chipButtonCls}>
                  重新加载
                </button>
              </div>
            </>
          )}
          {detailError ? (
            <details className="mt-4">
              <summary className="cursor-pointer text-xs text-text-muted">查看技术详情</summary>
              <div className="panel-soft mt-2 rounded-[22px] p-3 text-xs text-text-secondary">
                <div>策略 ID：{id ?? '-'}</div>
                {traceId ? <div className="mt-1">Trace ID：{traceId}</div> : null}
                <pre className="mt-2 overflow-auto whitespace-pre-wrap break-all text-xs">{detailError}</pre>
              </div>
            </details>
          ) : null}
        </SectionCard>
      </PageContainer>
    );
  }

  const sampleStart = strategy.sample_start_date ?? paperNavRows[0]?.nav_date ?? null;
  const sampleEnd = strategy.sample_end_date ?? paperNavRows[paperNavRows.length - 1]?.nav_date ?? null;
  const sampleWindow = sampleStart && sampleEnd ? `${sampleStart} - ${sampleEnd}` : (sampleStart ?? sampleEnd ?? '-');
  const turnoverRate = latestIncubationMetric?.turnover_rate ?? null;
  const capacityValue = strategy.capacity ?? paperAccount?.total_value ?? latestPaperNav?.total_value ?? null;
  const capacityLabel = strategy.capacity_label ?? '当前模拟容量';
  const qualityGate = latestQualityReport?.quality_gate;
  const runCorrection = latestQualityReport?.run_correction;
  const multipleTestingMode = runCorrection?.multiple_testing_mode ?? qualityGate?.multiple_testing_mode ?? null;
  const deflatedSharpeRatio = firstFiniteNumber(
    runCorrection?.deflated_sharpe_ratio,
    qualityGate?.deflated_sharpe_ratio,
    runCorrection?.deflated_sharpe_proxy,
    qualityGate?.deflated_sharpe_proxy,
  );
  const pboValue = firstFiniteNumber(
    runCorrection?.pbo,
    qualityGate?.pbo,
    runCorrection?.pbo_proxy,
    qualityGate?.pbo_proxy,
  );
  const hansenSpaPvalue = firstFiniteNumber(
    runCorrection?.hansen_spa_pvalue,
    qualityGate?.hansen_spa_pvalue,
    runCorrection?.spa_pvalue_proxy,
    qualityGate?.spa_pvalue_proxy,
  );
  const whiteRealityCheckPvalue = firstFiniteNumber(
    runCorrection?.white_reality_check_pvalue,
    qualityGate?.white_reality_check_pvalue,
    runCorrection?.reality_check_pvalue_proxy,
    qualityGate?.reality_check_pvalue_proxy,
  );

  function applyView(snapshot: Record<string, unknown>) {
    if (typeof snapshot.activeTab === 'string' && DETAIL_TABS.some((item) => item.key === snapshot.activeTab)) {
      setActiveTab(snapshot.activeTab as (typeof DETAIL_TABS)[number]['key']);
    }
    if (
      typeof snapshot.factorySection === 'string' &&
      FACTORY_SECTIONS.includes(snapshot.factorySection as FactoryReviewSection)
    ) {
      factoryPanelProps.onSectionChange(snapshot.factorySection as FactoryReviewSection);
      setActiveTab('factory');
    }
  }

  function addStrategyToCart() {
    if (!strategy) return;
    addToCart({ strategyId: strategy.id, name: strategy.name, weight: 0 });
    updateWorkbenchContext({
      strategyId: String(strategy.id),
      strategyName: strategy.name,
    });
  }

  const overviewContent = (
    <>
      {allMetrics ? (
        <KpiGrid cols={6}>
          <KpiCard title="总收益" value={fmtPct(allMetrics.total_return ?? 0)} change={allMetrics.total_return} />
          <KpiCard title="年化收益" value={fmtPct(allMetrics.annual_return ?? 0)} />
          <KpiCard title="Sharpe" value={fmtNum(allMetrics.sharpe_ratio ?? 0, 2)} />
          <KpiCard title="最大回撤" value={fmtPct(allMetrics.max_drawdown ?? 0)} />
          <KpiCard title="胜率" value={fmtPct(allMetrics.win_rate ?? 0)} />
          <KpiCard title="交易次数" value={allMetrics.trade_count ?? '-'} />
        </KpiGrid>
      ) : null}

      <div className="mt-4 grid grid-cols-1 gap-4 xl:grid-cols-[1.4fr_1fr]">
        {navSeries.length > 1 ? (
          <SectionCard className="mt-0 p-3">
            <h3 className="mt-0">净值轨迹</h3>
            <LineChart
              categories={navCategories}
              series={[{ name: 'NAV', data: navSeries, color: '#1a73e8' }]}
              height={280}
            />
          </SectionCard>
        ) : null}
        <SectionCard className="mt-0 p-4 sm:p-5">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h3 className="mt-0">运行摘要</h3>
              <p className="mb-0 mt-2 text-sm leading-6 text-text-secondary">
                把孵化状态、风险信号与统计修正并列呈现，方便先判断是否值得继续跟踪，再决定要不要切到工厂审查。
              </p>
            </div>
            <Badge variant={promotionReady ? 'success' : 'warning'}>
              {promotionReady ? '达到上架条件' : '仍在孵化观察'}
            </Badge>
          </div>
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            <div className="metric-tile rounded-[24px] p-4">
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">孵化上下文</div>
              <div className="mt-3 space-y-2 text-sm text-text-secondary">
                <div>
                  孵化阶段：
                  <span className="font-medium text-text-primary">
                    {incubationAccount?.stage ?? latestIncubationMetric?.stage ?? '-'}
                  </span>
                </div>
                <div>
                  账户状态：<span className="font-medium text-text-primary">{incubationAccount?.status ?? '-'}</span>
                </div>
                <div>
                  最新 NAV：
                  <span className="font-medium text-text-primary">{fmtNum(latestIncubationMetric?.nav ?? 0, 4)}</span>
                </div>
              </div>
            </div>
            <div className="metric-tile rounded-[24px] p-4">
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">风险与画像</div>
              <div className="mt-3 grid gap-3 sm:grid-cols-2">
                <div>
                  <div className="text-2xl font-semibold text-text-primary">{openRiskEvents.length}</div>
                  <div className="mt-1 text-xs text-text-secondary">开放风险事件</div>
                </div>
                <div>
                  <div className="text-2xl font-semibold text-text-primary">{vectorProfiles.length}</div>
                  <div className="mt-1 text-xs text-text-secondary">向量画像数</div>
                </div>
              </div>
            </div>
            <div className="metric-tile rounded-[24px] p-4">
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">质量门</div>
              <div className="mt-3 space-y-2 text-sm text-text-secondary">
                <div>
                  质量评级：
                  <span className="font-medium text-text-primary">
                    {latestQualityReport?.summary?.validation_grade ?? '-'}
                  </span>
                </div>
                <div>
                  DSR：
                  <span className="font-medium text-text-primary">
                    {deflatedSharpeRatio == null ? '-' : fmtNum(deflatedSharpeRatio, 4)}
                  </span>
                </div>
                <div>
                  PBO：
                  <span className="font-medium text-text-primary">{pboValue == null ? '-' : fmtNum(pboValue, 4)}</span>
                </div>
              </div>
            </div>
            <div className="metric-tile rounded-[24px] p-4">
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">统计修正</div>
              <div className="mt-3 space-y-2 text-sm text-text-secondary">
                <div>
                  SPA p-value：
                  <span className="font-medium text-text-primary">
                    {hansenSpaPvalue == null ? '-' : fmtNum(hansenSpaPvalue, 4)}
                  </span>
                </div>
                <div>
                  White RC：
                  <span className="font-medium text-text-primary">
                    {whiteRealityCheckPvalue == null ? '-' : fmtNum(whiteRealityCheckPvalue, 4)}
                  </span>
                </div>
                <div>
                  多重检验：
                  <span className="font-medium text-text-primary">
                    {formatMultipleTestingMode(multipleTestingMode)}
                  </span>
                </div>
              </div>
            </div>
          </div>
          <div className="mt-3 flex flex-wrap gap-2 text-sm">
            {latestIncubationMetric?.decision ? (
              <Badge
                variant={
                  latestIncubationMetric.decision === 'promote'
                    ? 'success'
                    : latestIncubationMetric.decision === 'halt'
                      ? 'danger'
                      : 'warning'
                }
              >
                最新决策: {latestIncubationMetric.decision}
              </Badge>
            ) : null}
            {promotionReady ? (
              <Badge variant="success">达到上架条件</Badge>
            ) : (
              <Badge variant="warning">仍在孵化观察</Badge>
            )}
            {openRiskEvents.length > 0 ? (
              <Badge variant="danger">存在实时风控告警</Badge>
            ) : (
              <Badge variant="neutral">无实时风控告警</Badge>
            )}
            {multipleTestingMode ? (
              <Badge variant={multipleTestingMode === 'formal_runtime' ? 'success' : 'warning'}>
                多重检验: {formatMultipleTestingMode(multipleTestingMode)}
              </Badge>
            ) : null}
            {pboValue != null ? (
              <Badge variant={pboValue > 0.55 ? 'danger' : 'info'}>PBO {fmtNum(pboValue, 4)}</Badge>
            ) : null}
            {hansenSpaPvalue != null ? (
              <Badge variant={hansenSpaPvalue > 0.2 ? 'warning' : 'success'}>SPA p {fmtNum(hansenSpaPvalue, 4)}</Badge>
            ) : null}
          </div>
        </SectionCard>
      </div>

      <SectionCard className="p-4 sm:p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h3 className="mt-0">可信信息</h3>
            <p className="mb-0 mt-2 text-sm leading-6 text-text-secondary">
              合同字段、样本边界与容量口径放在同一层，避免这类“可信来源”被埋在指标流里。
            </p>
          </div>
          <Badge variant="info">Contract First</Badge>
        </div>
        <div className="mt-4 grid gap-3 md:grid-cols-3">
          <div className="metric-tile rounded-[24px] p-4">
            <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">样本期</div>
            <div className="mt-3 text-base font-semibold text-text-primary">{sampleWindow}</div>
          </div>
          <div className="metric-tile rounded-[24px] p-4">
            <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">最近换手</div>
            <div className="mt-3 text-base font-semibold text-text-primary">
              {turnoverRate == null ? '-' : fmtPct(turnoverRate)}
            </div>
          </div>
          <div className="metric-tile rounded-[24px] p-4">
            <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">{capacityLabel}</div>
            <div className="mt-3 text-base font-semibold text-text-primary">
              {capacityValue == null ? '-' : fmtNum(capacityValue, 2)}
            </div>
          </div>
        </div>
        <div className="mt-3 text-xs leading-6 text-text-secondary">
          样本期优先取策略合同字段，缺失时回退到孵化账户 NAV 区间；容量优先展示合同声明，缺失时回退到模拟盘当前总资产。
        </div>
      </SectionCard>

      {metrics.length > 1
        ? (() => {
            const sorted = [...metrics].sort((a, b) => (a.period ?? '').localeCompare(b.period ?? ''));
            const periods = sorted.map((m) => m.period ?? '');
            const returns = sorted.map((m) => Number(m.total_return ?? 0));
            const sharpes = sorted.map((m) => Number(m.sharpe_ratio ?? 0));
            return (
              <SectionCard className="p-3">
                <h3 className="mt-0">各期表现</h3>
                <LineChart
                  categories={periods}
                  series={[
                    { name: '总收益', data: returns, color: '#1a73e8' },
                    { name: 'Sharpe', data: sharpes, color: '#f59e0b', yAxisIndex: 1 },
                  ]}
                  height={260}
                  yAxisName="收益率"
                  y2AxisName="Sharpe"
                />
              </SectionCard>
            );
          })()
        : null}

      {factorBars.length > 0 ? (
        <SectionCard className="p-3">
          <h3 className="mt-0">因子暴露度</h3>
          <BarChart
            items={factorBars.map((item) => ({ label: item.name, value: item.value, color: '#6366f1' }))}
            height={220}
          />
        </SectionCard>
      ) : null}

      <SectionCard className="p-4 sm:p-5">
        <h3 className="mt-0">
          用户评价
          {strategy.avg_rating != null ? (
            <span className="ml-2 text-sm text-amber-500">
              {'★'.repeat(Math.round(strategy.avg_rating))} {strategy.avg_rating.toFixed(1)}
            </span>
          ) : null}
        </h3>

        <div className="panel-soft mb-4 rounded-[24px] p-3 sm:p-4">
          <div className="mb-3 text-xs leading-6 text-text-secondary">
            用更轻的 glass 表单承接评分与短评，既保留互动感，也不会把整块界面拉回传统后台风格。
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <select
              value={rating}
              onChange={(event) => setRating(Number(event.target.value))}
              className="w-auto min-w-[104px] text-sm"
            >
              {[5, 4, 3, 2, 1].map((value) => (
                <option key={value} value={value}>
                  {value} 星
                </option>
              ))}
            </select>
            <input
              value={comment}
              onChange={(event) => setComment(event.target.value)}
              placeholder="写一条评价..."
              className="min-w-[220px] flex-1 text-sm"
            />
            <button onClick={handleReview} disabled={reviewPending || !userId} className={heroPrimaryButtonCls}>
              {reviewPending ? '提交中...' : !userId ? '登录后可评价' : '提交'}
            </button>
          </div>
        </div>

        {reviews.length ? (
          <div className="space-y-3">
            {reviews.map((review, index) => (
              <div
                key={`${review.user_id}-${review.created_at ?? index}`}
                className="panel-soft rounded-[22px] p-4 text-sm"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-amber-400">{'★'.repeat(review.rating)}</span>
                  <span className="text-text-secondary">{review.user_id}</span>
                </div>
                {review.comment ? <p className="mt-1 text-text-secondary">{review.comment}</p> : null}
              </div>
            ))}
          </div>
        ) : (
          <p className="text-sm text-text-secondary">暂无评价</p>
        )}
      </SectionCard>
    </>
  );

  const primaryContent = (
    <div className="space-y-4 xl:h-full xl:overflow-y-auto xl:pr-1">
      {activeTab === 'overview' ? overviewContent : null}
      {activeTab === 'tracking' ? <LiveTrackingPanel {...trackingPanelProps} /> : null}
      {activeTab === 'factory' ? <FactoryReviewPanel {...factoryPanelProps} /> : null}
    </div>
  );

  const secondaryContent = (
    <div className="space-y-4 xl:h-full xl:overflow-y-auto xl:pl-1">
      <div className={sidePanelCls}>
        <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">当前策略</div>
        <div className="mt-3 text-base font-semibold text-text-primary">{strategy.name}</div>
        <div className="mt-3 flex flex-wrap gap-2">
          <Badge variant={statusVariant}>{strategy.status ?? '-'}</Badge>
          <Badge variant={promotionReady ? 'success' : 'warning'}>
            {promotionReady ? '达到上架条件' : '仍在孵化观察'}
          </Badge>
        </div>
        <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-1">
          <div className={sideMetricCls}>
            <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-text-muted">样本期</div>
            <div className="mt-2 text-sm font-medium text-text-primary">{sampleWindow}</div>
          </div>
          <div className={sideMetricCls}>
            <div className="grid grid-cols-3 gap-3 text-center">
              <div>
                <div className="text-lg font-semibold text-text-primary">{strategy.subscriber_count ?? 0}</div>
                <div className="mt-1 text-[11px] text-text-secondary">订阅</div>
              </div>
              <div>
                <div className="text-lg font-semibold text-text-primary">{openRiskEvents.length}</div>
                <div className="mt-1 text-[11px] text-text-secondary">风险</div>
              </div>
              <div>
                <div className="text-lg font-semibold text-text-primary">{vectorProfiles.length}</div>
                <div className="mt-1 text-[11px] text-text-secondary">画像</div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className={sidePanelCls}>
        <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">当前工作流</div>
        <div className="mt-3 text-base font-semibold text-text-primary">{activeTabLabel}</div>
        <div className="mt-4 space-y-3">
          {activeTab === 'overview' ? (
            <div className={sideMetricCls}>
              <div className="space-y-2 text-xs leading-6 text-text-secondary">
                <div>
                  质量评级：
                  <span className="font-medium text-text-primary">
                    {latestQualityReport?.summary?.validation_grade ?? '-'}
                  </span>
                </div>
                <div>
                  最新孵化决策：
                  <span className="font-medium text-text-primary">{latestIncubationMetric?.decision ?? '-'}</span>
                </div>
                <div>
                  多重检验：
                  <span className="font-medium text-text-primary">
                    {formatMultipleTestingMode(multipleTestingMode)}
                  </span>
                </div>
              </div>
            </div>
          ) : null}
          {activeTab === 'tracking' ? (
            <div className={sideMetricCls}>
              <div className="space-y-2 text-xs leading-6 text-text-secondary">
                <div>
                  总信号数：
                  <span className="font-medium text-text-primary">{trackingPanelProps.stats?.total_signals ?? 0}</span>
                </div>
                <div>
                  信号订阅：
                  <span className="font-medium text-text-primary">
                    {trackingPanelProps.signals?.subscriber === false ? '延迟模式' : '实时订阅'}
                  </span>
                </div>
                <div>
                  当前建议：<span className="font-medium text-text-primary">先看命中率，再看前向 IC / Sharpe。</span>
                </div>
              </div>
            </div>
          ) : null}
          {activeTab === 'factory' ? (
            <div className={sideMetricCls}>
              <div className="space-y-2 text-xs leading-6 text-text-secondary">
                <div>
                  当前分区：<span className="font-medium text-text-primary">{factoryPanelProps.activeSection}</span>
                </div>
                <div>
                  运行告警：
                  <span className="font-medium text-text-primary">{factoryPanelProps.runtimeAlerts.length}</span>
                </div>
                <div>
                  实验任务：<span className="font-medium text-text-primary">{factoryPanelProps.taskRuns.length}</span>
                </div>
              </div>
            </div>
          ) : null}
        </div>
        <div className="mt-4 flex flex-wrap gap-2">
          <button type="button" onClick={() => router.push('/strategy-market')} className={chipButtonCls}>
            回策略超市
          </button>
          <button type="button" onClick={() => router.push(portfolioHref)} className={chipButtonCls}>
            去组合页
          </button>
          <button type="button" onClick={() => router.push(paperHref)} className={chipButtonCls}>
            去模拟交易
          </button>
        </div>
      </div>

      <div className={sidePanelCls}>
        <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">可信指标</div>
        <div className="mt-4 grid gap-3">
          <div className={sideMetricCls}>
            <div className="grid grid-cols-2 gap-3 text-xs text-text-secondary">
              <div>
                <div className="text-[11px] uppercase tracking-[0.16em] text-text-muted">DSR</div>
                <div className="mt-1 text-sm font-medium text-text-primary">
                  {deflatedSharpeRatio == null ? '-' : fmtNum(deflatedSharpeRatio, 4)}
                </div>
              </div>
              <div>
                <div className="text-[11px] uppercase tracking-[0.16em] text-text-muted">PBO</div>
                <div className="mt-1 text-sm font-medium text-text-primary">
                  {pboValue == null ? '-' : fmtNum(pboValue, 4)}
                </div>
              </div>
              <div>
                <div className="text-[11px] uppercase tracking-[0.16em] text-text-muted">SPA p</div>
                <div className="mt-1 text-sm font-medium text-text-primary">
                  {hansenSpaPvalue == null ? '-' : fmtNum(hansenSpaPvalue, 4)}
                </div>
              </div>
              <div>
                <div className="text-[11px] uppercase tracking-[0.16em] text-text-muted">White RC</div>
                <div className="mt-1 text-sm font-medium text-text-primary">
                  {whiteRealityCheckPvalue == null ? '-' : fmtNum(whiteRealityCheckPvalue, 4)}
                </div>
              </div>
            </div>
          </div>
          <div className={sideMetricCls}>
            <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-text-muted">{capacityLabel}</div>
            <div className="mt-2 text-base font-semibold text-text-primary">
              {capacityValue == null ? '-' : fmtNum(capacityValue, 2)}
            </div>
          </div>
        </div>
      </div>
    </div>
  );

  return (
    <PageContainer className="space-y-4">
      <section className="page-hero p-5 sm:p-6">
        <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_clamp(280px,25vw,380px)]">
          <div>
            <Link href="/strategy-market" className="text-xs text-text-secondary no-underline hover:text-primary">
              &larr; 返回策略超市
            </Link>
            <div className="mt-4 flex flex-wrap items-center gap-2">
              <Badge variant="info">Strategy Workspace</Badge>
              <Badge variant={statusVariant}>{strategy.status ?? '-'}</Badge>
              <Badge variant={promotionReady ? 'success' : 'warning'}>
                {promotionReady ? '达到上架条件' : '仍在孵化观察'}
              </Badge>
            </div>
            <h1 className="mb-0 mt-4 text-[2rem] font-semibold tracking-[-0.03em] text-text-primary sm:text-[2.4rem]">
              {strategy.name}
            </h1>
            <p className="mb-0 mt-3 max-w-3xl text-sm leading-7 text-text-secondary sm:text-[15px]">
              {strategySummary}
            </p>
            <div className="mt-5 flex flex-wrap gap-2">
              <button
                onClick={() => {
                  addStrategyToCart();
                }}
                className={heroPrimaryButtonCls}
              >
                加入组合
              </button>
              <button
                onClick={handleSubscribe}
                disabled={subscribePending || !userId}
                className={`${heroSecondaryButtonCls} ${isSubscribed ? 'border-primary/35 bg-primary/12 text-primary' : ''}`}
              >
                {subscribePending ? '处理中...' : !userId ? '登录后订阅' : isSubscribed ? '取消订阅' : '订阅策略'}
              </button>
              <button type="button" onClick={() => router.push(portfolioHref)} className={heroSecondaryButtonCls}>
                去组合页配置
              </button>
            </div>

            <div className="mt-5 grid gap-3 sm:grid-cols-4">
              <div className="rounded-[24px] border border-white/45 bg-white/38 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.55)]">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">当前工作流</div>
                <div className="mt-3 text-2xl font-semibold text-text-primary">{activeTabLabel}</div>
                <div className="mt-1 text-xs text-text-secondary">
                  {activeTab === 'factory' ? `分区 ${factoryPanelProps.activeSection}` : '可在下方继续切换视图'}
                </div>
              </div>
              <div className="rounded-[24px] border border-white/45 bg-white/30 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.48)]">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">样本期</div>
                <div className="mt-3 text-2xl font-semibold text-text-primary">{sampleStart || '-'}</div>
                <div className="mt-1 text-xs text-text-secondary">{sampleWindow}</div>
              </div>
              <div className="rounded-[24px] border border-white/45 bg-white/26 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.42)]">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">风险 / 向量</div>
                <div className="mt-3 text-2xl font-semibold text-text-primary">
                  {openRiskEvents.length} / {vectorProfiles.length}
                </div>
                <div className="mt-1 text-xs text-text-secondary">开放风险事件 / 向量画像</div>
              </div>
              <div className="rounded-[24px] border border-white/45 bg-white/24 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.38)]">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">订阅与评分</div>
                <div className="mt-3 text-2xl font-semibold text-text-primary">{strategy.subscriber_count ?? 0}</div>
                <div className="mt-1 text-xs text-text-secondary">
                  {strategy.avg_rating != null ? `平均评分 ${strategy.avg_rating.toFixed(1)}` : '暂无公开评分'}
                </div>
              </div>
            </div>
          </div>

          <div className="grid gap-3">
            <div className={sidePanelCls}>
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">当前策略</div>
              <div className="mt-3 text-base font-semibold text-text-primary">{strategy.name}</div>
              <div className="mt-4 grid gap-3">
                <div className={sideMetricCls}>
                  <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-text-muted">
                    作者与评级
                  </div>
                  <div className="mt-2 space-y-2 text-xs leading-6 text-text-secondary">
                    <div>
                      作者：<span className="font-medium text-text-primary">{strategy.author_id ?? '-'}</span>
                    </div>
                    <div>
                      质量评级：
                      <span className="font-medium text-text-primary">
                        {latestQualityReport?.summary?.validation_grade ?? '-'}
                      </span>
                    </div>
                  </div>
                </div>
                <div className={sideMetricCls}>
                  <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-text-muted">当前决策</div>
                  <div className="mt-2 space-y-2 text-xs leading-6 text-text-secondary">
                    <div>
                      最新孵化决策：
                      <span className="font-medium text-text-primary">{latestIncubationMetric?.decision ?? '-'}</span>
                    </div>
                    <div>
                      多重检验：
                      <span className="font-medium text-text-primary">
                        {formatMultipleTestingMode(multipleTestingMode)}
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <div className={sidePanelCls}>
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">下一步建议</div>
              <div className="mt-4 space-y-3">
                <div className={sideMetricCls}>
                  {activeTab === 'overview'
                    ? '先确认质量门、DSR、PBO，再决定是否值得继续跟踪。'
                    : activeTab === 'tracking'
                      ? '先看命中率和前向 Sharpe，再决定是否需要回工厂审查。'
                      : '先排运行告警，再检查实验与向量分区是否存在偏差。'}
                </div>
                <div className={sideMetricCls}>
                  {promotionReady
                    ? '当前策略已接近上架条件，适合继续联动组合页做配置模拟。'
                    : '当前策略仍处孵化观察阶段，建议不要直接跳到配置，先补完工厂审查。'}
                </div>
                <div className={sideMetricCls}>
                  {isSubscribed
                    ? '你已订阅该策略，可继续留在当前页做深度复盘。'
                    : '若准备持续跟踪，建议先订阅，再把它加入组合购物车。'}
                </div>
              </div>
              <div className="mt-4 flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={handleSubscribe}
                  disabled={subscribePending || !userId}
                  className={chipButtonCls}
                >
                  {isSubscribed ? '取消订阅' : '立即订阅'}
                </button>
                <button type="button" onClick={() => router.push(paperHref)} className={chipButtonCls}>
                  查看模拟交易
                </button>
              </div>
            </div>
          </div>
        </div>
      </section>

      <WorkspaceToolbar pageKey={pageKey} currentView={currentView} onApplyView={applyView} supportsPagePanels />

      <TabBar tabs={DETAIL_TABS} active={activeTab} onChange={setActiveTab} />

      <WorkspaceSplitLayout pageKey={pageKey} primary={primaryContent} secondary={secondaryContent} />
    </PageContainer>
  );
}
