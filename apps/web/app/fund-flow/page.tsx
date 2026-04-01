'use client';

import { useState } from 'react';
import { PageContainer } from '@/components/ui';
import { useApiQuery } from '@/hooks/use-api-query';
import { useStockCode } from '@/hooks/use-stock-code';
import { ErrorState, LoadingState } from '@/components/status-state';
import FundFlowHero from '@/app/fund-flow/components/fund-flow-hero';
import FundFlowTabPanels from '@/app/fund-flow/components/fund-flow-tab-panels';
import FundFlowTabsShell from '@/app/fund-flow/components/fund-flow-tabs-shell';
import { FUND_FLOW_HERO_NOTES, FUND_FLOW_TABS, type FundFlowTab } from '@/app/fund-flow/lib/fund-flow-view';

export default function FundFlowPage() {
  const [tab, setTab] = useState<FundFlowTab>('stock');
  const { code, setCode, codeError, validate, trimmedCode, resolvedCode } = useStockCode('600519');
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

  const stockQ = useApiQuery<unknown>(effectiveStockPath);
  const sectorQ = useApiQuery<unknown>(sectorPath);
  const conceptQ = useApiQuery<unknown>(conceptPath);
  const northQ = useApiQuery<unknown>(northPath);
  const dragonQ = useApiQuery<unknown>(dragonPath);
  const marginQ = useApiQuery<unknown>(marginPath);
  const marginRankQ = useApiQuery<unknown>(marginRankPath);
  const blockTradesQ = useApiQuery<unknown>(blockTradesPath);
  const northHoldingQ = useApiQuery<unknown>(northHoldingPath);
  const northTopQ = useApiQuery<unknown>(northTopPath);

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
  const activeTabLabel = FUND_FLOW_TABS.find((item) => item.key === tab)?.label ?? '资金流向';
  const activeCodeLabel = trimmedCode || resolvedCode || '600519';
  const tabStatusLabel = loading ? '加载中' : error ? '需重试' : '就绪';

  function loadStockFlow(nextCode = trimmedCode || resolvedCode || '600519') {
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

  function loadNorthDetail(nextCode = trimmedCode || resolvedCode || '600519') {
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

  return (
    <PageContainer className="app-theme-market">
      <FundFlowHero
        activeTabLabel={activeTabLabel}
        hasError={Boolean(error)}
        loading={loading}
        tabStatusLabel={tabStatusLabel}
        activeCodeLabel={activeCodeLabel}
        heroNotes={FUND_FLOW_HERO_NOTES}
        resolvedCode={resolvedCode}
        onOpenStockFlow={() => {
          setTab('stock');
          loadStockFlow(activeCodeLabel);
        }}
        onOpenNorthFlow={() => {
          setTab('north');
          loadNorthFlow();
        }}
      />

      {loading ? <LoadingState text="加载中..." /> : null}
      {error ? <ErrorState text={error} hint="请稍后重试" /> : null}
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
