'use client';

import { useState, useMemo, useCallback, useRef, useEffect } from 'react';
import { PageContainer, SectionCard, KpiCard, KpiGrid } from '@/components/ui';
import { useApiQuery } from '@/hooks/use-api-query';
import { useWatchlistStore } from '@/store/watchlist-store';
import { StockLink } from '@/components/stock-link';
import { extractArray, fmtNum, fmtPct } from '@/lib/data-utils';
import Link from 'next/link';
import { useQuoteSubscription, type QuoteData } from '@/lib/ws';
import { EmptyState } from '@/components/status-state';

export default function WatchlistPage() {
    const groups = useWatchlistStore((s) => s.groups);
    const syncFromServer = useWatchlistStore((s) => s.syncFromServer);
    const synced = useWatchlistStore((s) => s.synced);
    const createGroup = useWatchlistStore((s) => s.createGroup);
    const deleteGroup = useWatchlistStore((s) => s.deleteGroup);
    const remove = useWatchlistStore((s) => s.remove);
    const add = useWatchlistStore((s) => s.add);

    const [activeGroupId, setActiveGroupId] = useState<string | null>(null);
    const [viewMode, setViewMode] = useState<'grid' | 'list'>('grid');
    const [newGroupName, setNewGroupName] = useState('');
    const [showNewGroup, setShowNewGroup] = useState(false);

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
        add(code, name, activeGroup?.id);
        // 清空搜索结果，方便继续操作
        setSearchKeyword('');
        setSearchPath(null);
    };

    // Sync on mount
    useEffect(() => { syncFromServer(); }, [syncFromServer]);

    const activeGroup = groups.find((g) => g.id === activeGroupId) || groups[0];
    const allCodes = useMemo(() => groups.flatMap((g) => g.items.map((i) => i.code)), [groups]);

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
    const wsQuotesRef = useRef<Map<string, Record<string, unknown>>>(new Map());
    const [wsQuoteTick, setWsQuoteTick] = useState(0);
    const handleWsQuote = useCallback((data: QuoteData) => {
        wsQuotesRef.current.set(data.code, data as Record<string, unknown>);
        setWsQuoteTick((t) => t + 1);
    }, []);
    useQuoteSubscription({ codes: allCodes, type: 'stock', onUpdate: handleWsQuote });

    // Merge REST + WS quotes
    const getQuote = (code: string) => {
        return wsQuotesRef.current.get(code) || quoteMap.get(code) || {};
    };

    const handleCreateGroup = () => {
        if (!newGroupName.trim()) return;
        createGroup(newGroupName.trim());
        setNewGroupName('');
        setShowNewGroup(false);
    };

    return (
        <PageContainer>
            <div className="flex items-center justify-between mb-4">
                <h2 className="text-lg font-semibold">📋 我的自选</h2>
                <div className="flex items-center gap-2">
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
                    <input
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
                {groups.map((group) => (
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
                <KpiCard title="分组数" value={String(groups.length)} />
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
            {activeGroup && activeGroup.items.length > 0 ? (
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
                                            onClick={() => remove(item.code)}
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
                                                    onClick={() => remove(item.code)}
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
                <EmptyState text="暂无自选股，可使用上方搜索框添加股票" />
            )}

            {/* Group Management */}
            {groups.length > 1 && (
                <SectionCard className="mt-4">
                    <h3 className="font-medium mb-2 text-sm">分组管理</h3>
                    <div className="flex flex-wrap gap-2">
                        {groups.map((g) => (
                            <div key={g.id} className="flex items-center gap-1 px-2 py-1 rounded bg-surface border border-glass-border text-xs">
                                <span className="inline-block w-2 h-2 rounded-full" style={{ background: g.color }} />
                                <span>{g.name} ({g.items.length})</span>
                                {groups.length > 1 && (
                                    <button
                                        onClick={() => deleteGroup(g.id)}
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
        </PageContainer>
    );
}
