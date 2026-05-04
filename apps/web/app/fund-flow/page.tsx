'use client';

import { useState } from 'react';
import ProgressiveWorkbenchSection from '@/components/progressive-workbench-section';
import { PageContainer } from '@/components/ui';
import { useApiQuery } from '@/hooks/use-api-query';
import { usePageActions } from '@/hooks/use-page-actions';
import { usePageContext } from '@/hooks/use-page-context';
import { useMobile } from '@/hooks/use-mobile';
import { RESPONSIVE_BREAKPOINTS } from '@/lib/responsive-layout';
import { useStockCode } from '@/hooks/use-stock-code';
import { DataQualityBanner, ErrorState, LoadingState } from '@/components/status-state';
import { buildLocalResultContract, defaultWorkbenchTask, evidenceToSummary } from '@/lib/result-workbench';
import FundFlowHero from '@/app/fund-flow/components/fund-flow-hero';
import FundFlowTabPanels from '@/app/fund-flow/components/fund-flow-tab-panels';
import FundFlowTabsShell from '@/app/fund-flow/components/fund-flow-tabs-shell';
import { FUND_FLOW_HERO_NOTES, FUND_FLOW_TABS, type FundFlowTab } from '@/app/fund-flow/lib/fund-flow-view';

export default function FundFlowPage() {
  const compactLayout = useMobile(RESPONSIVE_BREAKPOINTS.dockOverlay);
  const [tab, setTab] = useState<FundFlowTab>('stock');
  const { code, setCode, codeError, validate, trimmedCode, resolvedCode, setCodeError } = useStockCode();
  const autoStockPath = resolvedCode ? `/fund-flow/stock?code=${encodeURIComponent(resolvedCode)}` : null;
  const [stockPath, setStockPath] = useState<string | null>(null);
  const [sectorPath, setSectorPath] = useState<string | null>(null);
  const [conceptPath, setConceptPath] = useState<string | null>(null);
  const [northPath, setNorthPath] = useState<string | null>(null);
  const [dragonPath, setDragonPath] = useState<string | null>(null);
  const [marginPath, setMarginPath] = useState<string | null>(null);
  const [marginRankPath, setMarginRankPath] = useState<string | null>(null);
  const [blockTradesPath, setBlockTradesPath] = useState<string | null>(null);
  const [northHoldingPath, setNorthHoldingPath] = useState<string | null>(null);
  const [northTopPath, setNorthTopPath] = useState<string | null>(null);

  const effectiveStockPath = stockPath ?? autoStockPath;

  const strictRead = { critical: true, retry: false, timeoutMs: 15_000 };
  const stockQ = useApiQuery<unknown>(effectiveStockPath, strictRead);
  const sectorQ = useApiQuery<unknown>(sectorPath, strictRead);
  const conceptQ = useApiQuery<unknown>(conceptPath, strictRead);
  const northQ = useApiQuery<unknown>(northPath, strictRead);
  const dragonQ = useApiQuery<unknown>(dragonPath, strictRead);
  const marginQ = useApiQuery<unknown>(marginPath, strictRead);
  const marginRankQ = useApiQuery<unknown>(marginRankPath, strictRead);
  const blockTradesQ = useApiQuery<unknown>(blockTradesPath, strictRead);
  const northHoldingQ = useApiQuery<unknown>(northHoldingPath, strictRead);
  const northTopQ = useApiQuery<unknown>(northTopPath, strictRead);

  // Per-tab loading & error — 避免跨 Tab 互相阻塞
  const tabLoading: Record<FundFlowTab, boolean> = {
    stock: stockQ.isFetching,
    sector: sectorQ.isFetching,
    concept: conceptQ.isFetching,
    north: northQ.isFetching,
    dragon: dragonQ.isFetching,
    margin: marginQ.isFetching || marginRankQ.isFetching,
    'block-trades': blockTradesQ.isFetching,
    'north-detail': northHoldingQ.isFetching || northTopQ.isFetching,
  };
  const tabError: Record<FundFlowTab, string | null> = {
    stock: codeError || stockQ.error,
    sector: sectorQ.error,
    concept: conceptQ.error,
    north: northQ.error,
    dragon: dragonQ.error,
    margin: marginQ.error || marginRankQ.error,
    'block-trades': blockTradesQ.error,
    'north-detail': codeError || northHoldingQ.error || northTopQ.error,
  };
  const loading = tabLoading[tab];
  const error = tabError[tab];
  const activeQuery = tab === 'stock'
    ? stockQ
    : tab === 'sector'
      ? sectorQ
      : tab === 'concept'
        ? conceptQ
        : tab === 'north'
          ? northQ
          : tab === 'dragon'
            ? dragonQ
            : tab === 'margin'
              ? (marginQ.trust.degraded ? marginQ : marginRankQ)
              : tab === 'block-trades'
                ? blockTradesQ
                : (northHoldingQ.trust.degraded ? northHoldingQ : northTopQ);
  const activeTabLabel = FUND_FLOW_TABS.find((item) => item.key === tab)?.label ?? '资金流向';
  const activeCode = trimmedCode || resolvedCode || '';
  const activeCodeLabel = activeCode || '未选择标的';
  const trustStatus = activeQuery.trust.status;
  const tabStatusLabel = loading
    ? '加载中'
    : error
      ? '需重试'
      : trustStatus === 'partial'
        ? '部分降级'
        : trustStatus === 'degraded'
          ? '降级'
          : trustStatus === 'conflict'
            ? '源冲突'
            : trustStatus === 'empty'
              ? '真实无数据'
              : trustStatus === 'unavailable'
                ? '不可用'
                : '就绪';
  const degradedReasons = activeQuery.trust.reasons.length ? activeQuery.trust.reasons : activeQuery.trust.qualityFlags;

  function loadStockFlow(nextCode = trimmedCode || resolvedCode || '') {
    if (!nextCode) {
      setCodeError('请先选择你的关注股票');
      return;
    }
    setCode(nextCode);
    const p = `/fund-flow/stock?code=${encodeURIComponent(nextCode)}`;
    if (p === effectiveStockPath) stockQ.refetch();
    else setStockPath(p);
  }

  function loadMarginData(nextCode?: string) {
    const effectiveCode = nextCode ?? trimmedCode;
    if (nextCode !== undefined) setCode(nextCode);
    const params = effectiveCode ? `?code=${encodeURIComponent(effectiveCode)}` : '';
    const p = `/fund-flow/margin${params}`;
    if (p === marginPath) marginQ.refetch();
    else setMarginPath(p);
  }

  function loadNorthDetail(nextCode = trimmedCode || resolvedCode || '') {
    if (!nextCode) {
      setCodeError('请先选择你的关注股票');
      return;
    }
    setCode(nextCode);
    const hp = `/fund-flow/north-holding?code=${encodeURIComponent(nextCode)}`;
    if (hp === northHoldingPath) northHoldingQ.refetch();
    else setNorthHoldingPath(hp);
    if (northTopPath) northTopQ.refetch();
    else setNorthTopPath('/fund-flow/north-top');
  }

  function loadSectorFlow() {
    if (sectorPath) sectorQ.refetch();
    else setSectorPath('/fund-flow/sector');
  }

  function loadConceptFlow() {
    if (conceptPath) conceptQ.refetch();
    else setConceptPath('/fund-flow/concept');
  }

  function loadNorthFlow() {
    if (northPath) northQ.refetch();
    else setNorthPath('/fund-flow/north');
  }

  function loadDragonTiger() {
    if (dragonPath) dragonQ.refetch();
    else setDragonPath('/fund-flow/dragon-tiger');
  }

  function loadMarginRanking() {
    if (marginRankPath) marginRankQ.refetch();
    else setMarginRankPath('/fund-flow/margin-ranking');
  }

  function loadBlockTrades() {
    if (blockTradesPath) blockTradesQ.refetch();
    else setBlockTradesPath('/fund-flow/block-trades');
  }

  const pageActions = [
    {
      id: 'fund-flow.refresh-tab',
      label: `刷新${activeTabLabel}`,
      description: '按当前 Tab 重新拉取资金流数据',
      keywords: ['刷新', '资金流'],
      scope: 'page' as const,
      pageKey: 'fund-flow',
      run: () => {
        if (tab === 'stock') loadStockFlow(activeCode);
        else if (tab === 'sector') loadSectorFlow();
        else if (tab === 'concept') loadConceptFlow();
        else if (tab === 'north') loadNorthFlow();
        else if (tab === 'dragon') loadDragonTiger();
        else if (tab === 'margin') {
          loadMarginData(activeCode);
          loadMarginRanking();
        } else if (tab === 'block-trades') loadBlockTrades();
        else loadNorthDetail(activeCode);
        return { message: `已触发${activeTabLabel}刷新` };
      },
    },
    {
      id: 'fund-flow.open-stock',
      label: '切回个股资金流',
      description: '聚焦当前股票代码的单股资金流',
      keywords: ['个股', '资金流'],
      scope: 'page' as const,
      pageKey: 'fund-flow',
      run: () => {
        setTab('stock');
        loadStockFlow(activeCode);
        return { message: `已切到 ${activeCodeLabel} 的个股资金流` };
      },
    },
    {
      id: 'fund-flow.open-north',
      label: '查看北向资金',
      description: '切到北向资金总览',
      keywords: ['北向', '资金'],
      scope: 'page' as const,
      pageKey: 'fund-flow',
      run: () => {
        setTab('north');
        loadNorthFlow();
        return { message: '已切到北向资金' };
      },
    },
  ];
  usePageActions(pageActions);

  const fundFlowSummary = `当前查看 ${activeTabLabel}，聚焦 ${activeCodeLabel}，状态 ${tabStatusLabel}。`;
  const fundFlowResult = buildLocalResultContract({
    summary: fundFlowSummary,
    pageActions,
    preferredActionIds: ['fund-flow.refresh-tab', 'fund-flow.open-stock', 'fund-flow.open-north'],
    recommendedLinks: [
      { id: 'fund-flow-open-assistant-link', label: '继续问 Copilot', href: '/assistant' },
      activeCode
        ? { id: 'fund-flow-open-stock-link', label: '个股详情', href: `/stock?code=${encodeURIComponent(activeCode)}` }
        : { id: 'fund-flow-open-watchlist-link', label: '自选股', href: '/watchlist?from=fund-flow' },
      activeCode
        ? { id: 'fund-flow-open-technical-link', label: '技术分析', href: `/technical?code=${encodeURIComponent(activeCode)}` }
        : { id: 'fund-flow-open-market-link', label: '行情看板', href: '/market?from=fund-flow' },
      { id: 'fund-flow-open-risk-link', label: '风险中心', href: '/risk' },
    ],
    evidence: [
      { label: '当前 Tab', value: activeTabLabel },
      { label: '聚焦标的', value: activeCodeLabel },
      { label: '状态', value: tabStatusLabel },
      { label: '是否报错', value: error ? '是' : '否' },
      { label: '自动标的', value: resolvedCode || '-' },
    ],
    riskNotes: error ? [error] : degradedReasons,
    platformMeta: {
      sourceTool: 'fund-flow',
      sourceChain: ['fund-flow', tab],
      degraded: Boolean(error) || activeQuery.trust.degraded,
      fallbackReason: error ? [error] : degradedReasons.length ? degradedReasons : undefined,
    },
    workbenchTask: defaultWorkbenchTask(
      'fund-flow',
      `复查${activeTabLabel}`,
      `/fund-flow`,
      'fund-flow-review',
      { tab, code: activeCode || null },
    ),
  });
  usePageContext({
    pageKey: 'fund-flow',
    title: '资金流向',
    summary: fundFlowSummary,
    stockCode: activeCode || undefined,
    objectType: tab === 'stock' || tab === 'north-detail' ? 'stock' : 'stock-list',
    objectId: activeCode || 'fund-flow',
    resultType: `fund-flow-${tab}`,
    tags: [activeTabLabel, tabStatusLabel, activeCodeLabel],
    suggestions: [
      `总结当前${activeTabLabel}最值得关注的信号`,
      '告诉我下一步该看技术面还是风险面',
      '把当前资金流整理成行动清单',
    ],
    recommendedActions: fundFlowResult.recommendedActions ?? [],
    recommendedLinks: fundFlowResult.recommendedLinks ?? [],
    evidenceSummary: evidenceToSummary(fundFlowResult.evidence),
    riskNotes: fundFlowResult.riskNotes ?? [],
    freshness: fundFlowResult.freshness ?? null,
    raw: {
      tab,
      code: activeCode || null,
      status: tabStatusLabel,
      hasError: Boolean(error),
    },
  });

  return (
    <PageContainer className="app-theme-market">
      <FundFlowHero
        activeTabLabel={activeTabLabel}
        hasError={Boolean(error) || activeQuery.trust.degraded}
        loading={loading}
        tabStatusLabel={tabStatusLabel}
        activeCodeLabel={activeCodeLabel}
        heroNotes={FUND_FLOW_HERO_NOTES}
        resolvedCode={resolvedCode}
        onOpenStockFlow={() => {
          setTab('stock');
          loadStockFlow(activeCode);
        }}
        onOpenNorthFlow={() => {
          setTab('north');
          loadNorthFlow();
        }}
      />

      {!compactLayout ? (
        <ProgressiveWorkbenchSection pageKey="fund-flow" title="资金流结果工作台" result={fundFlowResult} summaryMode="strip" />
      ) : null}

      {loading ? <LoadingState text="加载中..." /> : null}
      {error ? <ErrorState text={error} hint="请稍后重试" /> : null}
      <DataQualityBanner trust={activeQuery.trust} title={`${activeTabLabel}数据质量`} onRetry={() => void activeQuery.refetch()} />
      <FundFlowTabsShell activeTabLabel={activeTabLabel} activeTab={tab} onTabChange={setTab} />
      <FundFlowTabPanels
        tab={tab}
        loading={loading}
        code={code}
        codeError={codeError}
        trimmedCode={trimmedCode}
        stockData={stockQ.data}
        sectorData={sectorQ.data}
        conceptData={conceptQ.data}
        northData={northQ.data}
        dragonData={dragonQ.data}
        marginData={marginQ.data}
        marginRankData={marginRankQ.data}
        blockTradesData={blockTradesQ.data}
        northHoldingData={northHoldingQ.data}
        northTopData={northTopQ.data}
        setCode={setCode}
        setTab={setTab}
        validate={validate}
        loadStockFlow={loadStockFlow}
        loadMarginData={loadMarginData}
        loadNorthDetail={loadNorthDetail}
        loadSectorFlow={loadSectorFlow}
        loadConceptFlow={loadConceptFlow}
        loadNorthFlow={loadNorthFlow}
        loadDragonTiger={loadDragonTiger}
        loadMarginRanking={loadMarginRanking}
        loadBlockTrades={loadBlockTrades}
      />
    </PageContainer>
  );
}
