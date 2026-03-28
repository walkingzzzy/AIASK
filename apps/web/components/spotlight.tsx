'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { getBffBaseUrl } from '@/lib/bff-base';

type SpotlightResult = {
    type: 'stock' | 'page' | 'command';
    label: string;
    sublabel?: string;
    href: string;
};

const PAGES: SpotlightResult[] = [
    { type: 'page', label: '首页', sublabel: '仪表盘概览', href: '/' },
    { type: 'page', label: '行情看板', sublabel: '市场总览', href: '/market' },
    { type: 'page', label: '自选股', sublabel: '我的关注', href: '/watchlist' },
    { type: 'page', label: '基本面', sublabel: '财务分析', href: '/fundamental' },
    { type: 'page', label: '技术分析', sublabel: '指标图表', href: '/technical' },
    { type: 'page', label: '资金流向', sublabel: '主力追踪', href: '/fund-flow' },
    { type: 'page', label: '情绪分析', sublabel: '市场情绪', href: '/sentiment' },
    { type: 'page', label: '研报公告', sublabel: '券商研究', href: '/research' },
    { type: 'page', label: '估值分析', sublabel: 'PE/PB估值', href: '/valuation' },
    { type: 'page', label: '策略超市', sublabel: '量化策略', href: '/strategy-market' },
    { type: 'page', label: '回测分析', sublabel: '策略回测', href: '/backtest' },
    { type: 'page', label: '模拟交易', sublabel: '纸上交易', href: '/paper-trading' },
    { type: 'page', label: '组合管理', sublabel: '投资组合', href: '/portfolio' },
    { type: 'page', label: '风控中心', sublabel: '风险管理', href: '/risk' },
    { type: 'page', label: '告警管理', sublabel: '价格预警', href: '/alerts' },
    { type: 'page', label: '通知中心', sublabel: '消息通知', href: '/notifications' },
    { type: 'page', label: '智能助手', sublabel: 'AI 分析', href: '/assistant' },
    { type: 'page', label: 'AI 对话', sublabel: '智能问答', href: '/chat' },
    { type: 'page', label: '数据中心', sublabel: '数据总览', href: '/data' },
    { type: 'page', label: '用户中心', sublabel: '个人设置', href: '/user' },
];

const TYPE_ICONS: Record<string, string> = {
    stock: '📈',
    page: '📄',
    command: '⚡',
};

function readRecord(value: unknown): Record<string, unknown> {
    if (!value || typeof value !== 'object' || Array.isArray(value)) {
        return {};
    }
    return value as Record<string, unknown>;
}

export function Spotlight() {
    const [open, setOpen] = useState(false);
    const [query, setQuery] = useState('');
    const [results, setResults] = useState<SpotlightResult[]>([]);
    const [selectedIdx, setSelectedIdx] = useState(0);
    const inputRef = useRef<HTMLInputElement>(null);
    const router = useRouter();

    const openSpotlight = useCallback(() => {
        setQuery('');
        setResults(PAGES.slice(0, 8));
        setSelectedIdx(0);
        setOpen(true);
    }, []);

    const closeSpotlight = useCallback(() => {
        setOpen(false);
    }, []);

    // Global ⌘K / Ctrl+K shortcut
    useEffect(() => {
        const handler = (e: KeyboardEvent) => {
            if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
                e.preventDefault();
                if (open) closeSpotlight();
                else openSpotlight();
            }
            if (e.key === 'Escape') closeSpotlight();
        };
        window.addEventListener('keydown', handler);
        return () => window.removeEventListener('keydown', handler);
    }, [closeSpotlight, open, openSpotlight]);

    // Search logic
    const search = useCallback(async (q: string) => {
        if (!q.trim()) {
            setResults(PAGES.slice(0, 8));
            return;
        }

        const lower = q.toLowerCase();
        const matched: SpotlightResult[] = [];

        // Check if it looks like a stock code (6 digits)
        if (/^\d{1,6}$/.test(q.trim())) {
            matched.push({
                type: 'stock',
                label: `查看 ${q.trim()}`,
                sublabel: '个股详情',
                href: `/stock?code=${q.trim()}`,
            });
        }

        // Filter pages
        PAGES.forEach((p) => {
            if (p.label.toLowerCase().includes(lower) || (p.sublabel?.toLowerCase().includes(lower))) {
                matched.push(p);
            }
        });

        // Try BFF search if query is text
        if (q.trim().length >= 2 && !/^\d+$/.test(q.trim())) {
            try {
                const res = await fetch(`${getBffBaseUrl()}/market/search?keyword=${encodeURIComponent(q.trim())}&limit=5`, {
                    credentials: 'include',
                });
                if (res.ok) {
                    const json = await res.json();
                    const data = readRecord(json);
                    const nested = readRecord(data.data);
                    const stocks = data.items ?? nested.items ?? data.data ?? [];
                    if (Array.isArray(stocks)) {
                        stocks.forEach((stock) => {
                            const record = readRecord(stock);
                            matched.push({
                                type: 'stock',
                                label: `${record.name ?? record.stock_name ?? ''} ${record.code ?? record.stock_code ?? ''}`,
                                sublabel: String(record.industry ?? record.sector ?? '个股'),
                                href: `/stock?code=${record.code ?? record.stock_code ?? ''}`,
                            });
                        });
                    }
                }
            } catch { /* ignore */ }
        }

        setResults(matched.slice(0, 10));
        setSelectedIdx(0);
    }, []);

    useEffect(() => {
        const timer = setTimeout(() => search(query), 200);
        return () => clearTimeout(timer);
    }, [query, search]);

    const handleSelect = (result: SpotlightResult) => {
        closeSpotlight();
        router.push(result.href);
    };

    const handleKeyDown = (e: React.KeyboardEvent) => {
        if (e.key === 'ArrowDown') {
            e.preventDefault();
            setSelectedIdx((i) => Math.min(i + 1, results.length - 1));
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            setSelectedIdx((i) => Math.max(i - 1, 0));
        } else if (e.key === 'Enter' && results[selectedIdx]) {
            e.preventDefault();
            handleSelect(results[selectedIdx]);
        }
    };

    if (!open) return null;

    return (
        <>
            <div className="fixed inset-0 bg-black/50 z-50 backdrop-blur-sm" onClick={closeSpotlight} />
            <div className="fixed top-[15%] left-1/2 -translate-x-1/2 w-[90%] max-w-lg z-50 animate-fade-up" role="dialog" aria-modal="true" aria-label="全局搜索">
                <div className="glass-strong rounded-xl border border-glass-border shadow-2xl overflow-hidden">
                    <div className="flex items-center gap-3 px-4 py-3 border-b border-glass-border">
                        <span className="text-lg">🔍</span>
                        <input
                            ref={inputRef}
                            autoFocus
                            type="text"
                            value={query}
                            onChange={(e) => setQuery(e.target.value)}
                            onKeyDown={handleKeyDown}
                            placeholder="搜索股票、页面、功能... (⌘K)"
                            className="flex-1 bg-transparent border-none outline-none text-sm placeholder:text-text-secondary"
                            aria-label="全局搜索"
                            aria-autocomplete="list"
                            aria-activedescendant={results[selectedIdx] ? `spotlight-result-${selectedIdx}` : undefined}
                        />
                        <kbd className="text-[10px] text-text-secondary bg-surface px-1.5 py-0.5 rounded border border-border">ESC</kbd>
                    </div>
                    <div className="max-h-[320px] overflow-y-auto" role="listbox" aria-label="搜索结果">
                        {results.length === 0 ? (
                            <div className="px-4 py-6 text-center text-text-secondary text-sm">
                                {query ? '没有找到结果' : '输入关键词开始搜索'}
                            </div>
                        ) : (
                            results.map((r, i) => (
                                <button
                                    id={`spotlight-result-${i}`}
                                    key={`${r.type}-${r.href}-${i}`}
                                    role="option"
                                    aria-selected={i === selectedIdx}
                                    onClick={() => handleSelect(r)}
                                    className={`w-full flex items-center gap-3 px-4 py-2.5 text-left cursor-pointer transition-colors ${i === selectedIdx ? 'bg-primary/15 text-primary' : 'hover:bg-white/5'
                                        }`}
                                >
                                    <span className="text-sm" aria-hidden="true">{TYPE_ICONS[r.type] || '📌'}</span>
                                    <div className="flex-1 min-w-0">
                                        <p className="text-sm font-medium truncate">{r.label}</p>
                                        {r.sublabel && <p className="text-xs text-text-secondary truncate">{r.sublabel}</p>}
                                    </div>
                                    {i === selectedIdx && <span className="text-xs text-text-secondary" aria-hidden="true">↵</span>}
                                </button>
                            ))
                        )}
                    </div>
                    <div className="px-4 py-2 border-t border-glass-border text-[10px] text-text-secondary flex gap-4">
                        <span>↑↓ 导航</span>
                        <span>↵ 打开</span>
                        <span>ESC 关闭</span>
                    </div>
                </div>
            </div>
        </>
    );
}
