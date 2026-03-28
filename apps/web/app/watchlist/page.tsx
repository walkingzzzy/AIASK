'use client';

import { useState, useMemo, useCallback, useEffect } from 'react';
import { AskAiButton } from '@/components/ask-ai-button';
import { PageContainer, SectionCard, KpiCard, KpiGrid, ConfirmDialog } from '@/components/ui';
import { useApiQuery } from '@/hooks/use-api-query';
import { useHydrated } from '@/hooks/use-hydrated';
import { usePageActions } from '@/hooks/use-page-actions';
import { usePageContext } from '@/hooks/use-page-context';
import { useWatchlistStore } from '@/store/watchlist-store';
import { StockLink } from '@/components/stock-link';
import { extractArray, fmtNum, fmtPct } from '@/lib/data-utils';
import Link from 'next/link';
import { useQuoteSubscription, type QuoteData } from '@/lib/ws';
import { EmptyState } from '@/components/status-state';
import { exportCSV } from '@/lib/export';

export default function WatchlistPage() {
    const hydrated = useHydrated();
    const groups = useWatchlistStore((s) => s.groups);
    const syncFromServer = useWatchlistStore((s) => s.syncFromServer);
    const createGroup = useWatchlistStore((s) => s.createGroup);
    const deleteGroup = useWatchlistStore((s) => s.deleteGroup);
    const remove = useWatchlistStore((s) => s.remove);
    const add = useWatchlistStore((s) => s.add);

    const [activeGroupId, setActiveGroupId] = useState<string | null>(null);
    const [viewMode, setViewMode] = useState<'grid' | 'list'>('grid');
    const [newGroupName, setNewGroupName] = useState('');
    const [showNewGroup, setShowNewGroup] = useState(false);
    const [pendingDialog, setPendingDialog] = useState<
      | { type: 'remove'; code: string; groupId?: string; groupName: string }
      | { type: 'delete-group'; groupId: string; groupName: string }
      | null
    >(null);

    // ── 搜索/添加自选股 ──
    const [searchKeyword, setSearchKeyword] = useState('');
    const [searchPath, setSearchPath] = useState<string | null>(null);
    const searchQ = useApiQuery<unknown>(searchPath);
    const searchRows = useMemo(() => extractArray(searchQ.data) as Record<string, unknown>[], [searchQ.data]);

    const handleSearch = () => {
        const kw = searchKeyword.trim();
        if (!kw) return;
        const p = `/market/search?keyword=${encodeURIComponent(kw)}`;
        if (p === searchPath) searchQ.refetch();
        else setSearchPath(p);
    };

    const handleAddStock = (code: string, name: string) => {
        void add(code, name, activeGroup?.id);
        // 清空搜索结果，方便继续操作
        setSearchKeyword('');
        setSearchPath(null);
    };

    // Sync on mount
    useEffect(() => { syncFromServer(); }, [syncFromServer]);

    const visibleGroups = hydrated ? groups : [];
    const fallbackActiveGroup = visibleGroups.find((g) => g.items.length > 0) || visibleGroups[0] || null;
    const effectiveActiveGroupId = activeGroupId != null && visibleGroups.some((g) => g.id === activeGroupId)
        ? activeGroupId
        : fallbackActiveGroup?.id ?? null;
    const activeGroup = visibleGroups.find((g) => g.id === effectiveActiveGroupId) || fallbackActiveGroup;
    const activeGroupName = activeGroup?.name ?? '';
    const activeGroupIdValue = activeGroup?.id ?? '';
    const activeGroupExportRows = (activeGroup?.items ?? []).map((item) => ({
        代码: item.code,
        名称: item.name,
        分组: activeGroupName,
        添加时间: new Date(item.addedAt).toLocaleString('zh-CN'),
    }));
    const allCodes = hydrated ? visibleGroups.flatMap((g) => g.items.map((i) => i.code)) : [];

    // Batch quote for all watchlist stocks
    const batchQ = useApiQuery<unknown>(
        allCodes.length > 0 ? '/market/batch-quotes' : null,
        { body: { codes: allCodes }, refetchInterval: 30000, placeholderData: 'keepPrevious' },
    );

    const quoteMap = useMemo(() => {
        const m = new Map<string, Record<string, unknown>>();
        const arr = extractArray(batchQ.data, 'quotes', 'items', 'data');
        arr.forEach((q) => { const c = String(q.code ?? ''); if (c) m.set(c, q); });
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

    const handleCreateGroup = async () => {
        const groupName = newGroupName.trim();
        if (!groupName) return;

        const createdGroupId = await createGroup(groupName);
        if (createdGroupId) {
            setActiveGroupId(createdGroupId);
        }

        setNewGroupName('');
        setShowNewGroup(false);
    };

    const handleRemoveStock = (code: string, groupName: string) => {
        setPendingDialog({ type: 'remove', code, groupId: activeGroup?.id, groupName });
    };

    const handleDeleteGroup = (groupId: string, groupName: string) => {
        setPendingDialog({ type: 'delete-group', groupId, groupName });
    };

    const handleConfirmPendingAction = () => {
        if (!pendingDialog) return;
        if (pendingDialog.type === 'remove') {
            void remove(pendingDialog.code, pendingDialog.groupId);
        } else {
            if (activeGroupId === pendingDialog.groupId) {
                setActiveGroupId('default');
            }
            void deleteGroup(pendingDialog.groupId);
        }
        setPendingDialog(null);
    };

    usePageContext({
        pageKey: 'watchlist',
        title: '自选股',
        summary: `当前共有 ${visibleGroups.length} 个分组，活跃分组 ${activeGroup?.name ?? '未选择'}，包含 ${activeGroup?.items.length ?? 0} 只股票。`,
        stockCode: activeGroup?.items[0]?.code,
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
        raw: {
            groupCount: visibleGroups.length,
            activeGroupId: activeGroup?.id ?? null,
            activeGroupName: activeGroup?.name ?? null,
            stockCount: activeGroup?.items.length ?? 0,
            viewMode,
        },
    });

    const pageActions = [
        {
            id: 'watchlist.refresh',
            label: '刷新自选股',
            description: '重新同步自选股分组并刷新行情',
            keywords: ['刷新', '自选'],
            scope: 'page' as const,
            pageKey: 'watchlist',
            run: async () => {
                await syncFromServer();
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

    return (
        <PageContainer>
            <div className="flex items-center justify-between mb-4">
                <h1 className="text-lg font-semibold">📋 我的自选</h1>
                <div className="flex items-center gap-2">
                    <AskAiButton
                        stockCode={activeGroup?.items[0]?.code}
                        summary={`分组 ${activeGroup?.name ?? '未选择'}，共 ${activeGroup?.items.length ?? 0} 只股票`}
                        prompt="请基于当前自选股分组给我一个盘中观察顺序"
                    />
                    {activeGroup?.items.length ? (
                        <button
                            onClick={() => exportCSV(activeGroup.items.map((item) => ({
                                代码: item.code,
                                名称: item.name,
                                分组: activeGroup.name,
                                添加时间: new Date(item.addedAt).toLocaleString('zh-CN'),
                            })), `watchlist-${activeGroup.id}`)}
                            className="text-xs px-2 py-1 rounded border border-border cursor-pointer hover:bg-white/10"
                        >
                            导出 CSV
                        </button>
                    ) : null}
                    <button
                        onClick={() => setViewMode(viewMode === 'grid' ? 'list' : 'grid')}
                        className="text-xs px-2 py-1 rounded border border-border cursor-pointer hover:bg-white/10"
                    >
                        {viewMode === 'grid' ? '📃 列表' : '📊 网格'}
                    </button>
                    <button
                        onClick={() => setShowNewGroup(true)}
                        className="text-xs px-2 py-1 rounded border border-primary/50 text-primary cursor-pointer hover:bg-primary/10"
                    >
                        + 新建分组
                    </button>
                </div>
            </div>

            {/* ── 搜索并添加自选股 ── */}
            <SectionCard className="mb-4">
                <p className="text-xs text-text-secondary mb-2 font-medium">🔍 搜索并添加自选股</p>
                <div className="flex gap-2 items-center flex-wrap">
                    <label htmlFor="watchlist-search" className="sr-only">搜索股票代码或名称</label>
                    <input
                        id="watchlist-search"
                        type="text"
                        value={searchKeyword}
                        onChange={(e) => setSearchKeyword(e.target.value)}
                        onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
                        placeholder="输入股票代码或名称，如 600519 或 茅台"
                        className="flex-1 min-w-[200px] border border-border rounded px-3 py-1.5 bg-surface text-sm"
                    />
                    <button
                        onClick={handleSearch}
                        disabled={searchQ.isFetching}
                        className="px-3 py-1.5 rounded bg-primary text-white text-sm cursor-pointer disabled:opacity-50"
                    >
                        {searchQ.isFetching ? '搜索中...' : '搜索'}
                    </button>
                    {searchPath && (
                        <button
                            onClick={() => { setSearchPath(null); setSearchKeyword(''); }}
                            className="px-3 py-1.5 rounded border border-border text-sm cursor-pointer text-text-secondary hover:text-text-primary"
                        >
                            清空
                        </button>
                    )}
                </div>
                {searchRows.length > 0 && (
                    <div className="mt-3 max-h-48 overflow-auto border border-glass-border rounded">
                        <table className="w-full text-sm">
                            <thead className="sticky top-0 bg-surface">
                                <tr className="border-b border-glass-border text-text-secondary text-xs">
                                    <th className="text-left py-1.5 px-3">代码</th>
                                    <th className="text-left py-1.5 px-3">名称</th>
                                    <th className="text-left py-1.5 px-3">行业</th>
                                    <th className="text-center py-1.5 px-3">操作</th>
                                </tr>
                            </thead>
                            <tbody>
                                {searchRows.map((row, i) => {
                                    const code = String(row.code ?? '');
                                    const name = String(row.name ?? '');
                                    const alreadyAdded = activeGroup?.items.some((item) => item.code === code);
                                    return (
                                        <tr key={i} className="border-b border-glass-border/50 hover:bg-white/5">
                                            <td className="py-1.5 px-3 font-mono text-xs">{code}</td>
                                            <td className="py-1.5 px-3">{name}</td>
                                            <td className="py-1.5 px-3 text-text-secondary text-xs">{String(row.industry ?? '-')}</td>
                                            <td className="py-1.5 px-3 text-center">
                                                {alreadyAdded ? (
                                                    <span className="text-xs text-yellow-500">✓ 已添加</span>
                                                ) : (
                                                    <button
                                                        onClick={() => handleAddStock(code, name)}
                                                        className="text-xs px-2 py-0.5 rounded bg-primary/20 text-primary hover:bg-primary/30 cursor-pointer"
                                                    >
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
                )}
                {searchPath && !searchQ.isFetching && searchRows.length === 0 && (
                    <p className="text-xs text-text-muted mt-2">未找到相关股票</p>
                )}
            </SectionCard>

            {/* Group Tabs */}
            <div className="flex gap-2 mb-4 flex-wrap">
                {visibleGroups.map((group) => (
                    <button
                        key={group.id}
                        onClick={() => setActiveGroupId(group.id)}
                        className={`px-3 py-1.5 rounded-full text-xs font-medium cursor-pointer transition-all ${(activeGroup?.id === group.id)
                            ? 'bg-primary/20 text-primary border border-primary/40'
                            : 'bg-surface border border-glass-border text-text-secondary hover:bg-white/10'
                            }`}
                    >
                        <span
                            className="inline-block w-2 h-2 rounded-full mr-1.5"
                            style={{ background: group.color }}
                        />
                        {group.name} ({group.items.length})
                    </button>
                ))}
            </div>

            {/* New Group Form */}
            {showNewGroup && (
                <SectionCard className="mb-4">
                    <div className="flex items-center gap-2">
                        <input
                            type="text"
                            value={newGroupName}
                            onChange={(e) => setNewGroupName(e.target.value)}
                            placeholder="分组名称"
                            className="flex-1 border border-border rounded px-3 py-1.5 bg-surface text-sm"
                            onKeyDown={(e) => e.key === 'Enter' && handleCreateGroup()}
                        />
                        <button
                            onClick={handleCreateGroup}
                            className="px-3 py-1.5 rounded bg-primary text-white text-sm cursor-pointer"
                        >
                            创建
                        </button>
                        <button
                            onClick={() => setShowNewGroup(false)}
                            className="px-3 py-1.5 rounded border border-border text-sm cursor-pointer"
                        >
                            取消
                        </button>
                    </div>
                </SectionCard>
            )}

            {/* Stats */}
            <KpiGrid cols={4} className="mb-4">
                <KpiCard title="自选总数" value={String(allCodes.length)} />
                <KpiCard title="分组数" value={String(visibleGroups.length)} />
                <KpiCard
                    title="涨"
                    value={String(
                        allCodes.filter((c) => {
                            const q = getQuote(c);
                            return Number(q.changePercent ?? q.change_pct ?? q.pct_chg ?? 0) > 0;
                        }).length,
                    )}
                />
                <KpiCard
                    title="跌"
                    value={String(
                        allCodes.filter((c) => {
                            const q = getQuote(c);
                            return Number(q.changePercent ?? q.change_pct ?? q.pct_chg ?? 0) < 0;
                        }).length,
                    )}
                />
            </KpiGrid>

            {/* Active Group Contents */}
            {!hydrated ? (
                <SectionCard>
                    <p className="text-sm text-text-secondary">正在加载自选数据...</p>
                </SectionCard>
            ) : activeGroup && activeGroup.items.length > 0 ? (
                viewMode === 'grid' ? (
                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
                        {activeGroup.items.map((item) => {
                            const q = getQuote(item.code);
                            const price = Number(q.price ?? q.current_price ?? q.close ?? 0);
                            const changePct = Number(q.changePercent ?? q.change_pct ?? q.pct_chg ?? 0);
                            const vol = Number(q.volume ?? q.vol ?? 0);
                            return (
                                <SectionCard key={item.code} className="hover:border-primary/40 transition-all group relative overflow-hidden">
                                    {/* 右上角操作区：行情 + 个股详情 + 移除 */}
                                    <div className="absolute top-2 right-2 flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                                        <Link
                                            href={`/market?code=${encodeURIComponent(item.code)}`}
                                            className="text-xs px-1.5 py-0.5 rounded bg-primary/20 text-primary hover:bg-primary/40 no-underline"
                                            title="查看行情看板"
                                        >
                                            📈
                                        </Link>
                                        <Link
                                            href={`/stock?code=${encodeURIComponent(item.code)}`}
                                            className="text-xs px-1.5 py-0.5 rounded bg-surface/80 text-text-secondary hover:text-primary border border-glass-border no-underline"
                                            title="个股详情"
                                        >
                                            📋
                                        </Link>
                                        <button
                                            onClick={() => handleRemoveStock(item.code, activeGroup?.name ?? '当前分组')}
                                            className="text-xs px-1.5 py-0.5 rounded text-danger/70 hover:text-danger cursor-pointer hover:bg-danger/10"
                                            title="从自选股移除"
                                        >
                                            ✕
                                        </button>
                                    </div>
                                    {/* 卡片主体：点击跳行情看板 */}
                                    <Link
                                        href={`/market?code=${encodeURIComponent(item.code)}`}
                                        className="block no-underline"
                                        title={`查看 ${item.name || item.code} 行情`}
                                    >
                                        <div className="mb-2">
                                            <p className="font-semibold text-sm text-text-primary">{item.name || item.code}</p>
                                            <p className="text-xs text-text-secondary">{item.code}</p>
                                        </div>
                                        <div className="flex items-end justify-between">
                                            <span className={`text-xl font-bold ${changePct >= 0 ? 'text-danger' : 'text-success'}`}>
                                                {price > 0 ? fmtNum(price, 2) : '--'}
                                            </span>
                                            <span className={`text-sm font-medium ${changePct >= 0 ? 'text-danger' : 'text-success'}`}>
                                                {changePct >= 0 ? '+' : ''}{fmtPct(changePct)}
                                            </span>
                                        </div>
                                        {vol > 0 && (
                                            <p className="text-xs text-text-secondary mt-1">成交量: {fmtNum(vol / 10000, 0)}万</p>
                                        )}
                                    </Link>
                                </SectionCard>
                            );
                        })}
                    </div>
                ) : (
                    /* List View */
                    <SectionCard>
                        <table className="w-full text-sm">
                            <thead>
                                <tr className="border-b border-glass-border text-text-secondary text-xs">
                                    <th className="text-left py-2 px-2">代码</th>
                                    <th className="text-left py-2 px-2">名称</th>
                                    <th className="text-right py-2 px-2">现价</th>
                                    <th className="text-right py-2 px-2">涨跌幅</th>
                                    <th className="text-right py-2 px-2">成交量</th>
                                    <th className="text-center py-2 px-2">操作</th>
                                </tr>
                            </thead>
                            <tbody>
                                {activeGroup.items.map((item) => {
                                    const q = getQuote(item.code);
                                    const price = Number(q.price ?? q.current_price ?? q.close ?? 0);
                                    const changePct = Number(q.changePercent ?? q.change_pct ?? q.pct_chg ?? 0);
                                    const vol = Number(q.volume ?? q.vol ?? 0);
                                    return (
                                        <tr key={item.code} className="border-b border-glass-border/50 hover:bg-white/5">
                                            <td className="py-2 px-2">
                                                <Link
                                                    href={`/market?code=${encodeURIComponent(item.code)}`}
                                                    className="text-primary hover:underline no-underline font-mono text-sm"
                                                    title="查看行情"
                                                >
                                                    {item.code}
                                                </Link>
                                            </td>
                                            <td className="py-2 px-2">
                                                <StockLink code={item.code} name={item.name || '--'} className="font-medium" />
                                            </td>
                                            <td className={`py-2 px-2 text-right font-medium ${changePct >= 0 ? 'text-danger' : 'text-success'}`}>
                                                {price > 0 ? fmtNum(price, 2) : '--'}
                                            </td>
                                            <td className={`py-2 px-2 text-right ${changePct >= 0 ? 'text-danger' : 'text-success'}`}>
                                                {changePct >= 0 ? '+' : ''}{fmtPct(changePct)}
                                            </td>
                                            <td className="py-2 px-2 text-right text-text-secondary">
                                                {vol > 0 ? `${fmtNum(vol / 10000, 0)}万` : '--'}
                                            </td>
                                            <td className="py-2 px-2 text-center">
                                                <button
                                                    onClick={() => handleRemoveStock(item.code, activeGroup?.name ?? '当前分组')}
                                                    className="text-xs text-danger/80 hover:text-danger cursor-pointer px-2 py-0.5 rounded hover:bg-danger/10"
                                                >
                                                    移除
                                                </button>
                                            </td>
                                        </tr>
                                    );
                                })}
                            </tbody>
                        </table>
                    </SectionCard>
                )
            ) : (
                <EmptyState
                    text="暂无自选股，可使用上方搜索框添加股票"
                    hint="如果你刚开始使用，建议先从行情看板挑 1-2 只常看股票加入自选，后续这里会持续展示它们的价格和涨跌幅。"
                    action={
                        <>
                            <button
                                type="button"
                                onClick={() => {
                                    setSearchKeyword('600519');
                                    setSearchPath('/market/search?keyword=600519');
                                }}
                                className="rounded-full border border-primary px-3 py-1 text-xs text-primary"
                            >
                                试试 600519
                            </button>
                            <Link href="/market" className="rounded-full border border-glass-border px-3 py-1 text-xs text-text-secondary no-underline">
                                去行情看板添加
                            </Link>
                        </>
                    }
                />
            )}

            {/* Group Management */}
            {visibleGroups.length > 1 && (
                <SectionCard className="mt-4">
                    <h3 className="font-medium mb-2 text-sm">分组管理</h3>
                    <div className="flex flex-wrap gap-2">
                        {visibleGroups.map((g) => (
                            <div key={g.id} className="flex items-center gap-1 px-2 py-1 rounded bg-surface border border-glass-border text-xs">
                                <span className="inline-block w-2 h-2 rounded-full" style={{ background: g.color }} />
                                <span>{g.name} ({g.items.length})</span>
                                {visibleGroups.length > 1 && (
                                    <button
                                        onClick={() => handleDeleteGroup(g.id, g.name)}
                                        className="ml-1 text-danger/60 hover:text-danger cursor-pointer"
                                        title="删除分组"
                                    >
                                        ✕
                                    </button>
                                )}
                            </div>
                        ))}
                    </div>
                </SectionCard>
            )}

            <ConfirmDialog
                open={pendingDialog != null}
                title={pendingDialog?.type === 'remove' ? '确认移除自选股' : '确认删除分组'}
                message={pendingDialog?.type === 'remove'
                    ? `确认从“${pendingDialog.groupName}”中移除 ${pendingDialog.code} 吗？`
                    : pendingDialog
                        ? `确认删除分组“${pendingDialog.groupName}”吗？分组内股票会回到默认分组。`
                        : ''}
                confirmText={pendingDialog?.type === 'remove' ? '确认移除' : '确认删除'}
                danger
                onConfirm={handleConfirmPendingAction}
                onCancel={() => setPendingDialog(null)}
            />
        </PageContainer>
    );
}
