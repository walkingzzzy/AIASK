'use client';

import { useState, useMemo, useCallback, useEffect } from 'react';
import { AskAiButton } from '@/components/ask-ai-button';
import ProgressiveWorkbenchSection from '@/components/progressive-workbench-section';
import { Badge, PageContainer, SectionCard, KpiCard, KpiGrid, ConfirmDialog } from '@/components/ui';
import { useApiQuery } from '@/hooks/use-api-query';
import { useHydrated } from '@/hooks/use-hydrated';
import { usePageActions } from '@/hooks/use-page-actions';
import { usePageContext } from '@/hooks/use-page-context';
import { useWatchlistStore } from '@/store/watchlist-store';
import { StockLink } from '@/components/stock-link';
import { extractArray, fmtNum, fmtPct } from '@/lib/data-utils';
import Link from 'next/link';
import { useQuoteSubscription, type QuoteData } from '@/lib/ws';
import { EmptyState, LoadingState, PageStatusCard } from '@/components/status-state';
import { exportCSV } from '@/lib/export';
import { buildLocalResultContract, defaultWorkbenchTask, evidenceToSummary } from '@/lib/result-workbench';
import { useMobile } from '@/hooks/use-mobile';
import { useToast } from '@/components/ui/toast';

const HERO_PRIMARY_BUTTON_CLS =
  'inline-flex cursor-pointer items-center justify-center rounded-full bg-primary px-4 py-2 text-sm font-medium text-white shadow-[0_20px_40px_-24px_rgba(11,107,203,0.52)] transition hover:-translate-y-0.5 hover:shadow-[0_24px_46px_-24px_rgba(11,107,203,0.58)] disabled:cursor-not-allowed disabled:opacity-50';
const HERO_SECONDARY_BUTTON_CLS =
  'action-chip cursor-pointer text-sm text-text-primary shadow-[0_16px_32px_-24px_rgba(15,23,42,0.28)]';
const CHIP_BUTTON_CLS = 'action-chip cursor-pointer text-xs text-text-primary';
const LINK_CHIP_CLS = 'action-chip text-sm no-underline text-inherit';
const PANEL_CLS = 'panel-soft rounded-[28px] p-4 sm:p-5';
const NOTE_CARD_CLS = 'metric-tile rounded-[22px] p-3 text-xs text-text-secondary';
const FIELD_CLS =
  'h-11 rounded-[20px] border border-white/65 bg-white/55 px-4 text-sm text-text-primary shadow-[inset_0_1px_0_rgba(255,255,255,0.75)] outline-none transition placeholder:text-text-muted focus:border-primary/45 focus:bg-white/72';

export default function WatchlistPage() {
  const hydrated = useHydrated();
  const compactBoard = useMobile(640);
  const { toast } = useToast();
  const groups = useWatchlistStore((s) => s.groups);
  const syncFromServer = useWatchlistStore((s) => s.syncFromServer);
  const createGroup = useWatchlistStore((s) => s.createGroup);
  const deleteGroup = useWatchlistStore((s) => s.deleteGroup);
  const remove = useWatchlistStore((s) => s.remove);
  const add = useWatchlistStore((s) => s.add);
  const synced = useWatchlistStore((s) => s.synced);
  const syncing = useWatchlistStore((s) => s.syncing);
  const syncError = useWatchlistStore((s) => s.syncError);

  const [activeGroupId, setActiveGroupId] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<'grid' | 'list'>('grid');
  const [newGroupName, setNewGroupName] = useState('');
  const [showNewGroup, setShowNewGroup] = useState(false);
  const [managementOpen, setManagementOpen] = useState(false);
  const [showAllActiveItems, setShowAllActiveItems] = useState(false);
  const [pendingDialog, setPendingDialog] = useState<
    | { type: 'remove'; code: string; groupId?: string; groupName: string }
    | { type: 'delete-group'; groupId: string; groupName: string }
    | null
  >(null);

  // ── 搜索/添加自选股 ──
  const [searchKeyword, setSearchKeyword] = useState('');
  const [searchPath, setSearchPath] = useState<string | null>(null);
  const searchQ = useApiQuery<unknown>(searchPath, { critical: true });
  const searchRows = useMemo(() => extractArray(searchQ.data) as Record<string, unknown>[], [searchQ.data]);

  const handleSearch = () => {
    const kw = searchKeyword.trim();
    if (!kw) return;
    const p = `/market/search?keyword=${encodeURIComponent(kw)}`;
    if (p === searchPath) searchQ.refetch();
    else setSearchPath(p);
  };

  const handleAddStock = async (code: string, name: string) => {
    try {
      await add(code, name, activeGroup?.id);
      setSearchKeyword('');
      setSearchPath(null);
      toast(`已将 ${name || code} 加入 ${activeGroup?.name ?? '当前分组'}`, 'success');
    } catch (error) {
      toast(error instanceof Error ? error.message : '添加自选失败', 'error');
    }
  };

  // Sync on mount
  useEffect(() => {
    void syncFromServer().catch(() => {});
  }, [syncFromServer]);

  const visibleGroups = hydrated ? groups : [];
  const fallbackActiveGroup = visibleGroups.find((g) => g.items.length > 0) || visibleGroups[0] || null;
  const effectiveActiveGroupId =
    activeGroupId != null && visibleGroups.some((g) => g.id === activeGroupId)
      ? activeGroupId
      : (fallbackActiveGroup?.id ?? null);
  const activeGroup = visibleGroups.find((g) => g.id === effectiveActiveGroupId) || fallbackActiveGroup;
  const activeGroupName = activeGroup?.name ?? '';
  const activeGroupIdValue = activeGroup?.id ?? '';
  const activeGroupCount = activeGroup?.items.length ?? 0;
  const activeGroupItems = activeGroup?.items ?? [];
  const visibleActiveGroupItems =
    compactBoard && !showAllActiveItems ? activeGroupItems.slice(0, 3) : activeGroupItems;
  const hiddenActiveGroupCount = Math.max(0, activeGroupItems.length - visibleActiveGroupItems.length);
  const activeGroupExportRows = (activeGroup?.items ?? []).map((item) => ({
    代码: item.code,
    名称: item.name,
    分组: activeGroupName,
    添加时间: new Date(item.addedAt).toLocaleString('zh-CN'),
  }));
  const allCodes = hydrated ? visibleGroups.flatMap((g) => g.items.map((i) => i.code)) : [];

  // Batch quote for all watchlist stocks
  const batchQ = useApiQuery<unknown>(allCodes.length > 0 ? '/market/batch-quotes' : null, {
    body: { codes: allCodes },
    refetchInterval: 30000,
    placeholderData: 'keepPrevious',
    critical: true,
  });

  const quoteMap = useMemo(() => {
    const m = new Map<string, Record<string, unknown>>();
    const arr = extractArray(batchQ.data, 'quotes', 'items', 'data');
    arr.forEach((q) => {
      const c = String(q.code ?? '');
      if (c) m.set(c, q);
    });
    return m;
  }, [batchQ.data]);

  // WS real-time quotes for watchlist stocks
  const [wsQuotes, setWsQuotes] = useState<Record<string, Record<string, unknown>>>({});
  const handleWsQuote = useCallback((data: QuoteData) => {
    if (!data.code) return;
    setWsQuotes((prev) => ({ ...prev, [data.code]: data as Record<string, unknown> }));
  }, []);
  useQuoteSubscription({ codes: allCodes, type: 'stock', onUpdate: handleWsQuote });

  // Merge REST + WS quotes
  const getQuote = (code: string) => {
    return wsQuotes[code] || quoteMap.get(code) || {};
  };

  const risingCount = allCodes.filter((c) => {
    const q = getQuote(c);
    return Number(q.changePercent ?? q.change_pct ?? q.pct_chg ?? 0) > 0;
  }).length;
  const fallingCount = allCodes.filter((c) => {
    const q = getQuote(c);
    return Number(q.changePercent ?? q.change_pct ?? q.pct_chg ?? 0) < 0;
  }).length;
  const viewModeLabel = viewMode === 'grid' ? '网格视图' : '列表视图';
  const heroNotes = [
    '先切到一个明确分组，再决定看网格还是列表，不建议在所有股票混在一起的状态下做判断。',
    '网格视图更适合快速扫价格和涨跌幅，列表视图更适合做有序复盘和逐行比对。',
    '搜索只负责把股票加进工作流，真正的下一步通常是去行情、个股详情、研究或交易页面。',
  ];

  useEffect(() => {
    setShowAllActiveItems(false);
  }, [compactBoard, activeGroup?.id, viewMode]);

  const handleCreateGroup = async () => {
    const groupName = newGroupName.trim();
    if (!groupName) return;
    try {
      const createdGroupId = await createGroup(groupName);
      if (createdGroupId) {
        setActiveGroupId(createdGroupId);
      }
      setNewGroupName('');
      setShowNewGroup(false);
      toast(`已创建分组 ${groupName}`, 'success');
    } catch (error) {
      toast(error instanceof Error ? error.message : '创建分组失败', 'error');
    }
  };

  const handleOpenGroupComposer = () => {
    setManagementOpen(true);
    setShowNewGroup(true);
  };

  const handleRemoveStock = (code: string, groupName: string) => {
    setPendingDialog({ type: 'remove', code, groupId: activeGroup?.id, groupName });
  };

  const handleDeleteGroup = (groupId: string, groupName: string) => {
    setPendingDialog({ type: 'delete-group', groupId, groupName });
  };

  const handleConfirmPendingAction = async () => {
    if (!pendingDialog) return;
    try {
      if (pendingDialog.type === 'remove') {
        await remove(pendingDialog.code, pendingDialog.groupId);
        toast(`已从 ${pendingDialog.groupName} 移除 ${pendingDialog.code}`, 'success');
      } else {
        if (activeGroupId === pendingDialog.groupId) {
          setActiveGroupId('default');
        }
        await deleteGroup(pendingDialog.groupId);
        toast(`已删除分组 ${pendingDialog.groupName}`, 'success');
      }
      setPendingDialog(null);
    } catch (error) {
      toast(error instanceof Error ? error.message : '自选股操作失败', 'error');
    }
  };

  const pageActions = [
    {
      id: 'watchlist.refresh',
      label: '刷新自选股',
      description: '重新同步自选股分组并刷新行情',
      keywords: ['刷新', '自选'],
      scope: 'page' as const,
      pageKey: 'watchlist',
      run: async () => {
        await syncFromServer(true);
        await batchQ.refetch();
        return { message: '已刷新自选股与行情' };
      },
    },
    {
      id: 'watchlist.toggle-view',
      label: viewMode === 'grid' ? '切到列表视图' : '切到网格视图',
      description: '切换自选股展示方式',
      keywords: ['视图', '列表', '网格'],
      scope: 'page' as const,
      pageKey: 'watchlist',
      run: () => {
        setViewMode((prev) => (prev === 'grid' ? 'list' : 'grid'));
        return { message: '已切换自选股视图' };
      },
    },
    {
      id: 'watchlist.export-active',
      label: '导出当前分组',
      description: '导出当前分组股票清单',
      keywords: ['导出', '分组'],
      scope: 'page' as const,
      pageKey: 'watchlist',
      run: () => {
        if (!activeGroupExportRows.length) {
          return { message: '当前分组没有可导出的股票' };
        }
        exportCSV(activeGroupExportRows, `watchlist-${activeGroupIdValue}`);
        return { message: `已导出分组 ${activeGroupName}` };
      },
    },
  ];

  usePageActions(pageActions);

  const watchlistSummary = `当前共有 ${visibleGroups.length} 个分组，活跃分组 ${activeGroup?.name ?? '未选择'}，包含 ${activeGroup?.items.length ?? 0} 只股票。`;
  const watchlistFreshness =
    hydrated && batchQ.dataUpdatedAt ? new Date(batchQ.dataUpdatedAt).toLocaleString('zh-CN') : null;
  const watchlistStatus =
    hydrated && syncing && !synced
      ? 'loading'
      : hydrated && !synced && syncError
        ? 'unavailable'
        : batchQ.error && activeGroupItems.length > 0
          ? 'degraded'
          : (activeGroup?.items.length ?? 0) === 0
            ? 'empty'
            : 'ready';
  const watchlistEvidence = [
    { label: '分组数量', value: String(visibleGroups.length) },
    { label: '当前分组', value: activeGroup?.name ?? '未选择' },
    { label: '股票数量', value: String(activeGroup?.items.length ?? 0) },
    { label: '视图模式', value: viewMode === 'grid' ? '网格视图' : '列表视图' },
  ];
  const leadCode = activeGroup?.items[0]?.code?.trim() || '';
  const watchlistLinks = [
    leadCode ? { id: 'watchlist-open-stock', label: '个股详情', href: `/stock?code=${encodeURIComponent(leadCode)}` } : { id: 'watchlist-open-market', label: '行情看板', href: '/market?from=watchlist' },
    { id: 'watchlist-open-research', label: '研报公告', href: leadCode ? `/research?code=${encodeURIComponent(leadCode)}` : '/research' },
    { id: 'watchlist-open-paper', label: '模拟交易', href: '/paper-trading?from=watchlist' },
    { id: 'watchlist-open-skills', label: '技能中心', href: '/skills?from=watchlist' },
  ];
  const watchlistRiskNotes = [] as string[];
  if ((activeGroup?.items.length ?? 0) === 0) {
    watchlistRiskNotes.push('当前分组为空，建议先补入候选标的后再做排序和巡检。');
  }
  if (hydrated && !synced && syncError) {
    watchlistRiskNotes.push('自选股分组同步失败，当前只能先切到其他页面继续工作。');
  }
  if (batchQ.error && activeGroupItems.length > 0) {
    watchlistRiskNotes.push('实时行情拉取失败，当前只保留分组和后续跳转，价格判断需要等待行情恢复。');
  }
  const watchlistResult = buildLocalResultContract({
    summary: watchlistSummary,
    status: watchlistStatus,
    pageActions,
    preferredActionIds: ['watchlist.refresh', 'watchlist.toggle-view', 'watchlist.export-active'],
    recommendedLinks: watchlistLinks,
    recommendedNextActions: [
      activeGroup?.id ? '先锁定一个分组，再决定看网格还是列表。' : '先建一个分组，避免所有股票混在一起。',
      (activeGroup?.items.length ?? 0) === 0 ? '先从行情页补入 1 到 2 只常看股票，再回来巡检。' : '先看当前分组里的强弱分布，再决定跳去行情、研究还是交易。',
      batchQ.error && activeGroupItems.length > 0 ? '行情恢复前先整理观察顺序，不要在无实时报价时直接做价格判断。' : '如果需要更深判断，再把当前分组送去 AI 做盘中观察顺序。',
    ],
    evidence: watchlistEvidence,
    riskNotes: watchlistRiskNotes,
    emptyState: {
      title: '当前分组还没有股票',
      description: '先建立一个明确的观察池，再开始排序、巡检和跳转到研究或交易页。',
      example: '先建“核心观察”分组，再从行情页加入 1 到 2 只常看股票。',
    },
    degradedState: batchQ.error
      ? {
          title: '实时行情暂不可用',
          description: '分组仍然可用，但当前价格和涨跌幅不能作为判断依据。',
          reason: batchQ.error,
          example: '先按分组和标的名称整理观察顺序，行情恢复后再回来自选页。',
        }
      : null,
    freshness: watchlistFreshness ? { updatedAt: watchlistFreshness, label: '行情刷新时间' } : null,
    workbenchTask: defaultWorkbenchTask('watchlist', `自选巡检：${activeGroup?.name ?? '当前分组'}`, '/watchlist', 'watchlist-review', {
      groupId: activeGroup?.id ?? null,
      groupName: activeGroup?.name ?? null,
      stockCount: activeGroup?.items.length ?? 0,
    }),
  });

  usePageContext({
    pageKey: 'watchlist',
    title: '自选股',
    summary: watchlistSummary,
    primaryGoal: '先锁定一个明确分组，再判断当前观察池里最该优先盯的标的。',
    requiredInputs: ['watchlistGroup'],
    stockCode: activeGroup?.items[0]?.code,
    objectType: activeGroup?.items.length ? 'stock-list' : 'workspace',
    objectId: activeGroup?.id ?? 'watchlist',
    resultType: 'watchlist-summary',
    tags: [
      `${visibleGroups.length} 个分组`,
      `${activeGroup?.items.length ?? 0} 只股票`,
      viewMode === 'grid' ? '网格视图' : '列表视图',
    ],
    suggestions: [
      '总结当前分组里最值得关注的股票',
      '按涨跌幅和成交额给自选股做优先级排序',
      '把当前分组整理成盘中巡检清单',
    ],
    recommendedActions: watchlistResult.recommendedActions,
    recommendedLinks: watchlistResult.recommendedLinks,
    evidenceSummary: evidenceToSummary(watchlistResult.evidence),
    riskNotes: watchlistResult.riskNotes ?? [],
    freshness: watchlistResult.freshness ?? null,
    dataFreshness: watchlistResult.freshness?.updatedAt ?? null,
    degradedReason: watchlistResult.riskNotes ?? [],
    raw: {
      groupCount: visibleGroups.length,
      activeGroupId: activeGroup?.id ?? null,
      activeGroupName: activeGroup?.name ?? null,
      stockCount: activeGroup?.items.length ?? 0,
      viewMode,
    },
  });

  if (hydrated && syncing && !synced) {
    return (
      <PageContainer className="app-theme-market space-y-4">
        <PageStatusCard
          status="loading"
          title="正在准备自选股工作区"
          reason="需要先同步分组和观察池，完成后才能稳定切分组、看实时行情和导出当前清单。"
          primaryAction={(
            <button
              type="button"
              onClick={() => {
                void syncFromServer(true).catch(() => {});
              }}
              className={HERO_PRIMARY_BUTTON_CLS}
            >
              重新同步
            </button>
          )}
          secondaryAction={(
            <Link href="/market" className={HERO_SECONDARY_BUTTON_CLS}>
              先去行情看板
            </Link>
          )}
          example="先建立一个核心观察分组，再回来统一巡检。"
        />
        <LoadingState text="正在同步自选股分组与行情工作台..." />
      </PageContainer>
    );
  }

  if (hydrated && !synced && syncError) {
    return (
      <PageContainer className="app-theme-market">
        <PageStatusCard
          status="unavailable"
          title="自选股主链路暂不可用"
          reason={syncError}
          primaryAction={(
            <button
              type="button"
              onClick={() => {
                void syncFromServer(true).catch(() => {});
              }}
              className={HERO_PRIMARY_BUTTON_CLS}
            >
              重试同步
            </button>
          )}
          secondaryAction={(
            <Link href="/market" className={HERO_SECONDARY_BUTTON_CLS}>
              先去行情看板
            </Link>
          )}
          example="先从行情页挑 1 到 2 只常看股票，待自选页恢复后再建立观察池。"
        />
      </PageContainer>
    );
  }

  return (
    <PageContainer className="app-theme-market space-y-4">
      <section className="page-hero p-5 sm:p-6">
        <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_clamp(280px,25vw,380px)]">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="info">Watchlist Workspace</Badge>
              <Badge variant="neutral">{activeGroupName || '未选择分组'}</Badge>
              <Badge variant={activeGroupCount > 0 ? 'success' : 'warning'}>
                {activeGroupCount > 0 ? `${activeGroupCount} 只股票` : '等待添加股票'}
              </Badge>
            </div>
            <h1 className="mb-0 mt-4 text-[2rem] font-semibold tracking-[-0.03em] text-text-primary sm:text-[2.4rem]">
              自选股工作台
            </h1>
            <p className="mb-0 mt-3 max-w-3xl text-sm leading-7 text-text-secondary sm:text-[15px]">
              这次重构把自选页从“股票堆叠列表”升级成连续工作台。搜索、分组、视图切换、分组统计和后续跳转都放回同一条阅读动线，方便你把盘中观察节奏固定下来。
            </p>
            <div className="mt-5 flex flex-wrap gap-2">
              <AskAiButton
                stockCode={activeGroup?.items[0]?.code}
                summary={`分组 ${activeGroup?.name ?? '未选择'}，共 ${activeGroup?.items.length ?? 0} 只股票`}
                prompt="请基于当前自选股分组给我一个盘中观察顺序"
                label="生成观察顺序"
              />
              <button
                type="button"
                onClick={() => setViewMode(viewMode === 'grid' ? 'list' : 'grid')}
                className={HERO_SECONDARY_BUTTON_CLS}
              >
                {viewMode === 'grid' ? '切到列表视图' : '切到网格视图'}
              </button>
              <button type="button" onClick={handleOpenGroupComposer} className={HERO_PRIMARY_BUTTON_CLS}>
                新建分组
              </button>
            </div>

            <div className="mt-5 grid grid-cols-2 gap-3 xl:grid-cols-4">
              <div className="rounded-[24px] border border-white/45 bg-white/38 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.55)]">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">活跃分组</div>
                <div className="mt-3 text-xl font-semibold text-text-primary">{activeGroupName || '未选择'}</div>
                <div className="mt-1 text-xs text-text-secondary">当前主要观察池</div>
              </div>
              <div className="rounded-[24px] border border-white/45 bg-white/30 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.48)]">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">股票数</div>
                <div className="mt-3 text-xl font-semibold text-text-primary">{activeGroupCount}</div>
                <div className="mt-1 text-xs text-text-secondary">{viewModeLabel}</div>
              </div>
              <div className="rounded-[24px] border border-white/45 bg-white/26 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.42)]">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">上涨数</div>
                <div className="mt-3 text-xl font-semibold text-text-primary">{risingCount}</div>
                <div className="mt-1 text-xs text-text-secondary">当前全部自选中的上涨个数</div>
              </div>
              <div className="rounded-[24px] border border-white/45 bg-white/24 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.38)]">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">下跌数</div>
                <div className="mt-3 text-xl font-semibold text-text-primary">{fallingCount}</div>
                <div className="mt-1 text-xs text-text-secondary">用于快速判断盘面强弱分布</div>
              </div>
            </div>
          </div>

          {!compactBoard ? (
            <div className="grid gap-3">
              <div className={PANEL_CLS}>
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">使用建议</div>
                <div className="mt-4 space-y-3">
                  {heroNotes.map((note) => (
                    <div key={note} className={NOTE_CARD_CLS}>
                      {note}
                    </div>
                  ))}
                </div>
              </div>
              <div className={PANEL_CLS}>
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">快捷跳转</div>
                <div className="mt-4 flex flex-wrap gap-2">
                  <Link href="/market" className={LINK_CHIP_CLS}>
                    去行情看板
                  </Link>
                  <Link href="/stock" className={LINK_CHIP_CLS}>
                    去个股详情
                  </Link>
                  <Link href="/research" className={LINK_CHIP_CLS}>
                    去研究页
                  </Link>
                  <Link href="/paper-trading" className={LINK_CHIP_CLS}>
                    去模拟交易
                  </Link>
                </div>
                {activeGroup?.items.length ? (
                  <div className="mt-4">
                    <button
                      onClick={() =>
                        exportCSV(
                          activeGroup.items.map((item) => ({
                            代码: item.code,
                            名称: item.name,
                            分组: activeGroup.name,
                            添加时间: new Date(item.addedAt).toLocaleString('zh-CN'),
                          })),
                          `watchlist-${activeGroup.id}`,
                        )
                      }
                      className={HERO_SECONDARY_BUTTON_CLS}
                    >
                      导出当前分组
                    </button>
                  </div>
                ) : null}
              </div>
            </div>
          ) : null}
        </div>
      </section>

      {!compactBoard || watchlistStatus !== 'ready' ? (
        <ProgressiveWorkbenchSection
          pageKey="watchlist"
          title="自选研究工作台"
          result={watchlistResult}
          summaryMode="strip"
        />
      ) : null}


      <div className={PANEL_CLS}>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <div className="eyebrow">Active Pool</div>
            <h2 className="mb-0 mt-2 text-xl font-semibold text-text-primary">按分组切换当前观察池</h2>
            <p className="mb-0 mt-2 text-sm leading-7 text-text-secondary">
              默认先切换分组，再进入下方观察面板。搜索、建组和全局统计都收进下方管理区，避免把自选页变成长控制台。
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Badge variant="neutral">{viewModeLabel}</Badge>
            <Badge variant="info">{activeGroupCount} 只股票</Badge>
          </div>
        </div>
        <div className="mt-4 flex gap-2 flex-wrap">
          {visibleGroups.map((group) => (
            <button
              key={group.id}
              onClick={() => setActiveGroupId(group.id)}
              className={`action-chip cursor-pointer text-sm ${
                activeGroup?.id === group.id ? 'border-primary/30 bg-primary/10 text-primary' : 'text-text-secondary'
              }`}
            >
              <span className="inline-block h-2 w-2 rounded-full" style={{ background: group.color }} />
              <span>{group.name}</span>
              <span className="text-xs">({group.items.length})</span>
            </button>
          ))}
        </div>
        <div className="mt-4 flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => setViewMode(viewMode === 'grid' ? 'list' : 'grid')}
            className={HERO_SECONDARY_BUTTON_CLS}
          >
            {viewMode === 'grid' ? '切到列表视图' : '切到网格视图'}
          </button>
          <button type="button" onClick={handleOpenGroupComposer} className={HERO_PRIMARY_BUTTON_CLS}>
            新建分组
          </button>
        </div>
      </div>

      <details
        open={managementOpen}
        onToggle={(event) => setManagementOpen(event.currentTarget.open)}
        className={`${PANEL_CLS} overflow-hidden`}
      >
        <summary className="flex cursor-pointer list-none items-center justify-between gap-3 rounded-[24px] text-left">
          <div>
            <div className="eyebrow">Management Zone</div>
            <h2 className="mb-0 mt-2 text-xl font-semibold text-text-primary">展开分组管理、搜索与全局统计</h2>
            <p className="mb-0 mt-2 text-sm leading-7 text-text-secondary">
              这些是次级管理动作，不默认占据主阅读路径；需要补充股票、建组或看全局统计时再展开。
            </p>
          </div>
          <Badge variant={allCodes.length > 0 ? 'success' : 'warning'}>
            {allCodes.length > 0 ? `${allCodes.length} 只自选` : '等待建立观察池'}
          </Badge>
        </summary>

        <div className="mt-4 space-y-4">
          {showNewGroup ? (
            <div className="rounded-[24px] border border-white/50 bg-white/28 p-4">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
                <input
                  type="text"
                  value={newGroupName}
                  onChange={(e) => setNewGroupName(e.target.value)}
                  placeholder="分组名称"
                  className={`${FIELD_CLS} flex-1`}
                  onKeyDown={(e) => e.key === 'Enter' && handleCreateGroup()}
                />
                <div className="flex flex-wrap gap-2">
                  <button onClick={handleCreateGroup} className={HERO_PRIMARY_BUTTON_CLS}>
                    创建分组
                  </button>
                  <button onClick={() => setShowNewGroup(false)} className={HERO_SECONDARY_BUTTON_CLS}>
                    取消
                  </button>
                </div>
              </div>
            </div>
          ) : null}

          <SectionCard className="mt-0 p-4 sm:p-5">
            <div className="flex flex-col gap-4">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                <div>
                  <div className="eyebrow">Search Deck</div>
                  <h2 className="mb-0 mt-2 text-xl font-semibold text-text-primary">搜索并添加股票</h2>
                  <p className="mb-0 mt-2 text-sm leading-7 text-text-secondary">
                    搜索结果会直接告诉你当前分组是否已经包含该标的，补池后再回到主观察面板继续看盘。
                  </p>
                </div>
                <Badge variant="info">{activeGroupName || '未选择分组'}</Badge>
              </div>

              <div className="flex items-center gap-2 flex-wrap">
                <label htmlFor="watchlist-search" className="sr-only">
                  搜索股票代码或名称
                </label>
                <input
                  id="watchlist-search"
                  type="text"
                  value={searchKeyword}
                  onChange={(e) => setSearchKeyword(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
                  placeholder="输入股票代码或名称，如 600519 或 茅台"
                  className={`${FIELD_CLS} min-w-[220px] flex-1`}
                />
                <button onClick={handleSearch} disabled={searchQ.isFetching} className={HERO_PRIMARY_BUTTON_CLS}>
                  {searchQ.isFetching ? '搜索中...' : '搜索'}
                </button>
                {searchPath ? (
                  <button
                    onClick={() => {
                      setSearchPath(null);
                      setSearchKeyword('');
                    }}
                    className={HERO_SECONDARY_BUTTON_CLS}
                  >
                    清空
                  </button>
                ) : null}
              </div>

              {searchRows.length > 0 ? (
                <div className="mt-1 max-h-56 overflow-auto rounded-[24px] border border-glass-border bg-white/30">
                  <table className="w-full text-sm">
                    <thead className="sticky top-0 bg-white/75 backdrop-blur-xl">
                      <tr className="border-b border-glass-border text-text-secondary text-xs">
                        <th className="text-left py-2 px-3">代码</th>
                        <th className="text-left py-2 px-3">名称</th>
                        <th className="text-left py-2 px-3">行业</th>
                        <th className="text-center py-2 px-3">操作</th>
                      </tr>
                    </thead>
                    <tbody>
                      {searchRows.map((row, i) => {
                        const code = String(row.code ?? '');
                        const name = String(row.name ?? '');
                        const alreadyAdded = activeGroup?.items.some((item) => item.code === code);
                        return (
                          <tr key={i} className="border-b border-glass-border/50 hover:bg-white/10">
                            <td className="py-2 px-3 font-mono text-xs">{code}</td>
                            <td className="py-2 px-3">{name}</td>
                            <td className="py-2 px-3 text-text-secondary text-xs">{String(row.industry ?? '-')}</td>
                            <td className="py-2 px-3 text-center">
                              {alreadyAdded ? (
                                <span className="text-xs text-yellow-600">已在当前分组</span>
                              ) : (
                                <button onClick={() => handleAddStock(code, name)} className={CHIP_BUTTON_CLS}>
                                  + 添加
                                </button>
                              )}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              ) : null}
              {searchPath && !searchQ.isFetching && searchRows.length === 0 ? (
                <p className="mt-1 text-xs text-text-muted">未找到相关股票</p>
              ) : null}
              {searchQ.error ? (
                <PageStatusCard
                  status="unavailable"
                  title="股票搜索暂不可用"
                  reason={searchQ.error}
                  primaryAction={(
                    <button
                      type="button"
                      onClick={() => {
                        if (searchPath) {
                          void searchQ.refetch();
                        }
                      }}
                      className={CHIP_BUTTON_CLS}
                    >
                      重试搜索
                    </button>
                  )}
                  secondaryAction={(
                    searchPath ? (
                      <button
                        type="button"
                        onClick={() => {
                          setSearchPath(null);
                          setSearchKeyword('');
                        }}
                        className={CHIP_BUTTON_CLS}
                      >
                        清空搜索
                      </button>
                    ) : (
                      <Link href="/market" className={LINK_CHIP_CLS}>
                        去行情看板
                      </Link>
                    )
                  )}
                  example="输入 600519 或 贵州茅台，把标的补进当前观察池。"
                  className="mt-3"
                />
              ) : null}
            </div>
          </SectionCard>

          <SectionCard className="mt-0 p-4 sm:p-5">
            <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
              <div>
                <div className="eyebrow">Overview</div>
                <h2 className="mb-0 mt-2 text-xl font-semibold text-text-primary">全局统计与分组概览</h2>
              </div>
              <Badge variant={allCodes.length > 0 ? 'success' : 'warning'}>
                {allCodes.length > 0 ? '已有观察池' : '等待建立观察池'}
              </Badge>
            </div>
            <KpiGrid cols={4}>
              <KpiCard title="自选总数" value={String(allCodes.length)} />
              <KpiCard title="分组数" value={String(visibleGroups.length)} />
              <KpiCard title="上涨" value={String(risingCount)} />
              <KpiCard title="下跌" value={String(fallingCount)} />
            </KpiGrid>
          </SectionCard>
        </div>
      </details>

      <section className="panel-soft rounded-[32px] p-4 sm:p-5">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <div className="eyebrow">Live Board</div>
            <h2 className="mb-0 mt-2 text-xl font-semibold text-text-primary">当前分组观察面板</h2>
            <p className="mb-0 mt-2 text-sm leading-7 text-text-secondary">
              这里负责承接真正的盯盘动作。网格模式偏向“快速扫一眼”，列表模式偏向“逐行比较”，两种视图都围绕当前分组展开，避免信息散掉。
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Badge variant="neutral">{viewModeLabel}</Badge>
            <Badge variant="info">{activeGroupCount} 只股票</Badge>
            <button
              type="button"
              onClick={() => {
                void (async () => {
                  try {
                    await syncFromServer(true);
                    await batchQ.refetch();
                    toast('已刷新自选股与行情', 'success');
                  } catch (error) {
                    toast(error instanceof Error ? error.message : '刷新自选股失败', 'error');
                  }
                })();
              }}
              className={CHIP_BUTTON_CLS}
            >
              刷新行情
            </button>
            {activeGroup?.items.length ? (
              <button
                type="button"
                onClick={() => exportCSV(activeGroupExportRows, `watchlist-${activeGroupIdValue}`)}
                className={CHIP_BUTTON_CLS}
              >
                导出分组
              </button>
            ) : null}
          </div>
        </div>

        {!hydrated ? (
          <div className="mt-5 rounded-[24px] border border-white/45 bg-white/30 p-4 text-sm text-text-secondary">
            正在加载自选数据...
          </div>
        ) : batchQ.error && activeGroupItems.length > 0 ? (
          <div className="mt-5">
            <PageStatusCard
              status="degraded"
              title="自选股实时行情暂不可用"
              reason={batchQ.error}
              freshness={watchlistFreshness}
              primaryAction={(
                <button
                  type="button"
                  onClick={() => {
                    void batchQ.refetch();
                  }}
                  className={CHIP_BUTTON_CLS}
                >
                  重试行情
                </button>
              )}
              secondaryAction={(
                <Link href="/market" className={LINK_CHIP_CLS}>
                  去行情看板
                </Link>
              )}
              example="先按分组整理观察顺序，行情恢复后再回来自选页做价格判断。"
            />
          </div>
        ) : activeGroup && activeGroupItems.length > 0 ? (
          viewMode === 'grid' ? (
            <div className="mt-5 grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
              {visibleActiveGroupItems.map((item) => {
                const q = getQuote(item.code);
                const price = Number(q.price ?? q.current_price ?? q.close ?? 0);
                const changePct = Number(q.changePercent ?? q.change_pct ?? q.pct_chg ?? 0);
                const vol = Number(q.volume ?? q.vol ?? 0);
                const changePositive = changePct >= 0;
                return (
                  <article
                    key={item.code}
                    className="group relative overflow-hidden rounded-[28px] border border-white/50 bg-[linear-gradient(160deg,rgba(255,255,255,0.44),rgba(255,255,255,0.16))] p-4 shadow-[0_24px_54px_-34px_rgba(15,23,42,0.38)] backdrop-blur-2xl transition hover:-translate-y-1 hover:border-primary/28 hover:shadow-[0_32px_72px_-38px_rgba(11,107,203,0.35)]"
                  >
                    <div className="absolute inset-x-0 top-0 h-24 bg-[radial-gradient(circle_at_top_left,rgba(47,140,255,0.16),transparent_58%)] opacity-80" />
                    <div className="relative">
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <Link
                            href={`/market?code=${encodeURIComponent(item.code)}`}
                            className="text-base font-semibold text-text-primary no-underline transition hover:text-primary"
                          >
                            {item.name || item.code}
                          </Link>
                          <p className="mb-0 mt-1 font-mono text-xs text-text-secondary">{item.code}</p>
                        </div>
                        <span
                          className={`rounded-full border px-2.5 py-1 text-[11px] font-medium ${
                            changePositive
                              ? 'border-danger/20 bg-danger/10 text-danger'
                              : 'border-success/20 bg-success/10 text-success'
                          }`}
                        >
                          {changePositive ? '偏强' : '偏弱'}
                        </span>
                      </div>

                      <div className="mt-5 flex items-end justify-between gap-4">
                        <div>
                          <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">
                            最新价格
                          </div>
                          <div
                            className={`mt-2 text-[1.8rem] font-semibold tracking-[-0.03em] ${
                              changePositive ? 'text-danger' : 'text-success'
                            }`}
                          >
                            {price > 0 ? fmtNum(price, 2) : '--'}
                          </div>
                        </div>
                        <div className="text-right">
                          <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">
                            涨跌幅
                          </div>
                          <div
                            className={`mt-2 text-lg font-semibold ${changePositive ? 'text-danger' : 'text-success'}`}
                          >
                            {changePositive ? '+' : ''}
                            {fmtPct(changePct)}
                          </div>
                        </div>
                      </div>

                      <div className="mt-5 grid gap-3 sm:grid-cols-2">
                        <div className="rounded-[20px] border border-white/50 bg-white/34 p-3">
                          <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">
                            成交量
                          </div>
                          <div className="mt-2 text-sm font-medium text-text-primary">
                            {vol > 0 ? `${fmtNum(vol / 10000, 0)}万` : '--'}
                          </div>
                        </div>
                        <div className="rounded-[20px] border border-white/50 bg-white/28 p-3">
                          <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">
                            分组
                          </div>
                          <div className="mt-2 text-sm font-medium text-text-primary">{activeGroup.name}</div>
                        </div>
                      </div>

                      <div className="mt-5 flex flex-wrap gap-2">
                        <Link href={`/market?code=${encodeURIComponent(item.code)}`} className={LINK_CHIP_CLS}>
                          查看行情
                        </Link>
                        <Link href={`/stock?code=${encodeURIComponent(item.code)}`} className={LINK_CHIP_CLS}>
                          个股详情
                        </Link>
                        <button
                          type="button"
                          onClick={() => handleRemoveStock(item.code, activeGroup.name)}
                          className={CHIP_BUTTON_CLS}
                        >
                          移出分组
                        </button>
                      </div>
                    </div>
                  </article>
                );
              })}
            </div>
          ) : (
            <div className="mt-5 overflow-hidden rounded-[28px] border border-white/50 bg-white/28 shadow-[0_24px_48px_-32px_rgba(15,23,42,0.35)] backdrop-blur-2xl">
              <div className="overflow-x-auto">
                <table className="w-full min-w-[640px] text-sm">
                  <thead className="bg-white/70 backdrop-blur-xl">
                    <tr className="border-b border-glass-border text-xs text-text-secondary">
                      <th className="px-3 py-3 text-left">代码</th>
                      <th className="px-3 py-3 text-left">名称</th>
                      <th className="px-3 py-3 text-right">现价</th>
                      <th className="px-3 py-3 text-right">涨跌幅</th>
                      <th className="px-3 py-3 text-right">成交量</th>
                      <th className="px-3 py-3 text-right">操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    {visibleActiveGroupItems.map((item) => {
                      const q = getQuote(item.code);
                      const price = Number(q.price ?? q.current_price ?? q.close ?? 0);
                      const changePct = Number(q.changePercent ?? q.change_pct ?? q.pct_chg ?? 0);
                      const vol = Number(q.volume ?? q.vol ?? 0);
                      const changePositive = changePct >= 0;
                      return (
                        <tr key={item.code} className="border-b border-glass-border/45 transition hover:bg-white/12">
                          <td className="px-3 py-3">
                            <Link
                              href={`/market?code=${encodeURIComponent(item.code)}`}
                              className="font-mono text-sm text-primary no-underline transition hover:opacity-80"
                              title="查看行情"
                            >
                              {item.code}
                            </Link>
                          </td>
                          <td className="px-3 py-3">
                            <StockLink code={item.code} name={item.name || '--'} className="font-medium" />
                          </td>
                          <td
                            className={`px-3 py-3 text-right font-medium ${
                              changePositive ? 'text-danger' : 'text-success'
                            }`}
                          >
                            {price > 0 ? fmtNum(price, 2) : '--'}
                          </td>
                          <td className={`px-3 py-3 text-right ${changePositive ? 'text-danger' : 'text-success'}`}>
                            {changePositive ? '+' : ''}
                            {fmtPct(changePct)}
                          </td>
                          <td className="px-3 py-3 text-right text-text-secondary">
                            {vol > 0 ? `${fmtNum(vol / 10000, 0)}万` : '--'}
                          </td>
                          <td className="px-3 py-3">
                            <div className="flex justify-end gap-2">
                              <Link href={`/stock?code=${encodeURIComponent(item.code)}`} className={LINK_CHIP_CLS}>
                                详情
                              </Link>
                              <button
                                type="button"
                                onClick={() => handleRemoveStock(item.code, activeGroup.name)}
                                className={CHIP_BUTTON_CLS}
                              >
                                移除
                              </button>
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )
        ) : (
          <div className="mt-5">
            <EmptyState
              text="暂无自选股，可使用上方搜索框添加股票"
              hint="如果你刚开始使用，建议先从行情看板挑 1 到 2 只常看股票加入自选，后续这里会持续展示它们的价格和涨跌幅。"
              variant="full"
              action={
                <>
                  <Link href="/market" className={LINK_CHIP_CLS}>
                    去行情看板添加
                  </Link>
                  <button
                    type="button"
                    onClick={() => setShowNewGroup(true)}
                    className={HERO_SECONDARY_BUTTON_CLS}
                  >
                    先建分组
                  </button>
                </>
              }
            />
          </div>
        )}

        {hiddenActiveGroupCount > 0 ? (
          <div className="mt-4 rounded-[24px] border border-white/45 bg-white/22 px-4 py-3 text-sm text-text-secondary">
            默认先展示前 {visibleActiveGroupItems.length} 只股票，剩余 {hiddenActiveGroupCount} 只已折叠，避免移动端一次展开整个观察池。
            <div className="mt-3 flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => setShowAllActiveItems((current) => !current)}
                className={HERO_SECONDARY_BUTTON_CLS}
              >
                {showAllActiveItems ? '收起剩余股票' : '展开全部股票'}
              </button>
            </div>
          </div>
        ) : null}
      </section>

      <ConfirmDialog
        open={pendingDialog != null}
        title={pendingDialog?.type === 'remove' ? '确认移除自选股' : '确认删除分组'}
        message={
          pendingDialog?.type === 'remove'
            ? `确认从“${pendingDialog.groupName}”中移除 ${pendingDialog.code} 吗？`
            : pendingDialog
              ? `确认删除分组“${pendingDialog.groupName}”吗？分组内股票会回到默认分组。`
              : ''
        }
        confirmText={pendingDialog?.type === 'remove' ? '确认移除' : '确认删除'}
        danger
        onConfirm={() => {
          void handleConfirmPendingAction();
        }}
        onCancel={() => setPendingDialog(null)}
      />
    </PageContainer>
  );
}
