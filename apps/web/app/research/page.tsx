'use client';

import { FormEvent, ReactNode, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import Link from 'next/link';
import { AskAiButton } from '@/components/ask-ai-button';
import { useOnboarding } from '@/components/onboarding';
import ProgressiveWorkbenchSection from '@/components/progressive-workbench-section';
import WorkspaceSplitLayout from '@/components/workspace-split-layout';
import WorkspaceToolbar from '@/components/workspace-toolbar';
import {
  PageContainer,
  SectionCard,
  TabBar,
  DataTable,
  StockCodeInput,
  KpiCard,
  KpiGrid,
  Badge,
} from '@/components/ui';
import { BarChart } from '@/components/charts';
import { useApiQuery } from '@/hooks/use-api-query';
import { usePageActions } from '@/hooks/use-page-actions';
import { usePageContext } from '@/hooks/use-page-context';
import { useStockCode } from '@/hooks/use-stock-code';
import { EmptyState, ErrorState, PageStatusCard } from '@/components/status-state';
import { extractArray, fmtNum, fmtPct, fmtAmount } from '@/lib/data-utils';
import { exportCSV } from '@/lib/export';
import { fmt, cacheText, type CacheMeta } from '@/lib/api';
import {
  buildLocalResultContract,
  defaultWorkbenchTask,
  evidenceToSummary,
  resolveResultContract,
} from '@/lib/result-workbench';
import { StockLink } from '@/components/stock-link';
import { WatchlistButton } from '@/components/watchlist-button';
import { useHydrated } from '@/hooks/use-hydrated';
import { useMobile } from '@/hooks/use-mobile';
import { RESPONSIVE_BREAKPOINTS } from '@/lib/responsive-layout';
import { selectActiveWorkspace, useWorkbenchStore } from '@/store/workbench-store';
import type { ResultContract } from '@aiask/shared-types';

type ResearchItem = { title: string; date: string; source: string; summary: string };
type ResearchData = {
  reports?: ResearchItem[];
  notices?: ResearchItem[];
  query?: { startDate: string; endDate: string; keyword: string; limit: number };
  sourceTools?: Record<string, unknown>;
  meta?: CacheMeta;
  result_contract?: ResultContract | null;
};
type Range = '7' | '30' | '90' | 'custom';
type SavedResearchView = {
  code: string;
  range: Range;
  startDate: string;
  endDate: string;
  keyword: string;
  newsTab: NewsTab;
  listPath: string | null;
};

const RESEARCH_VIEW_STORAGE_KEY = 'aiask.research.saved-view.v1';
const DEFAULT_RESEARCH_CODE = '';

const NEWS_TABS = [
  { key: 'stock-news', label: '个股新闻' },
  { key: 'market-news', label: '市场新闻' },
  { key: 'analyst', label: '分析师排名' },
  { key: 'forecast', label: '盈利预测' },
  { key: 'search-research', label: '研报搜索' },
  { key: 'reports', label: '研报列表' },
  { key: 'macro', label: '宏观数据' },
] as const;
type NewsTab = (typeof NEWS_TABS)[number]['key'];

function readSavedResearchView(): Partial<SavedResearchView> | null {
  if (typeof window === 'undefined') return null;
  try {
    const raw = window.localStorage.getItem(RESEARCH_VIEW_STORAGE_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as Partial<SavedResearchView>;
  } catch {
    return null;
  }
}

function isValidRange(value: unknown): value is Range {
  return value === '7' || value === '30' || value === '90' || value === 'custom';
}

function isValidNewsTab(value: unknown): value is NewsTab {
  return typeof value === 'string' && NEWS_TABS.some((tab) => tab.key === value);
}

function highlight(text: string, kw: string): ReactNode {
  if (!kw.trim()) return text || '-';
  const esc = kw.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const reg = new RegExp(`(${esc})`, 'ig');
  const parts = (text || '').split(reg);
  return parts.map((p, i) => (reg.test(p) ? <mark key={`${p}-${i}`}>{p}</mark> : <span key={`${p}-${i}`}>{p}</span>));
}

export default function ResearchPage() {
  const { completeStep } = useOnboarding();
  const compactLayout = useMobile(RESPONSIVE_BREAKPOINTS.splitCollapse);
  const mounted = useHydrated();
  const workbenchHydrated = useWorkbenchStore((state) => state.hydrated);
  const activeWorkspaceId = useWorkbenchStore((state) => state.activeWorkspaceId);
  const workbenchContext = useWorkbenchStore((state) => selectActiveWorkspace(state).context);
  const updateWorkbenchContext = useWorkbenchStore((state) => state.updateContext);
  const lastWorkspaceIdRef = useRef<string | null>(null);
  const restoredSavedViewRef = useRef(false);
  const { code, setCode, codeError, validate, trimmedCode, resolvedCode } = useStockCode(DEFAULT_RESEARCH_CODE);
  const [range, setRange] = useState<Range>('30');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [keyword, setKeyword] = useState('');
  const [formError, setFormError] = useState<string | null>(null);
  const autoListPath = resolvedCode
    ? `/research/list?code=${encodeURIComponent(resolvedCode)}&days=30&limit=20&keyword=`
    : null;
  const [listPath, setListPath] = useState<string | null>(null);
  const effectiveListPath = listPath ?? autoListPath;

  const listQ = useApiQuery<ResearchData>(effectiveListPath, { critical: true });
  const [newsTab, setNewsTab] = useState<NewsTab>('stock-news');
  const [newsPath, setNewsPath] = useState<string | null>(null);
  const newsQ = useApiQuery<unknown>(newsPath, { critical: true });

  useEffect(() => {
    if (!mounted || typeof window === 'undefined') return;
    const payload: SavedResearchView = {
      code,
      range,
      startDate,
      endDate,
      keyword,
      newsTab,
      listPath,
    };
    window.localStorage.setItem(RESEARCH_VIEW_STORAGE_KEY, JSON.stringify(payload));
  }, [code, endDate, keyword, listPath, mounted, newsTab, range, startDate]);

  useEffect(() => {
    if (!mounted || restoredSavedViewRef.current) return;
    restoredSavedViewRef.current = true;
    const savedView = readSavedResearchView();
    if (!savedView) return;

    if (typeof savedView.code === 'string' && savedView.code.trim()) {
      setCode(savedView.code.trim());
    }
    if (isValidRange(savedView.range)) {
      setRange(savedView.range);
    }
    if (typeof savedView.startDate === 'string') {
      setStartDate(savedView.startDate);
    }
    if (typeof savedView.endDate === 'string') {
      setEndDate(savedView.endDate);
    }
    if (typeof savedView.keyword === 'string') {
      setKeyword(savedView.keyword);
    }
    if (isValidNewsTab(savedView.newsTab)) {
      setNewsTab(savedView.newsTab);
    }
    if (typeof savedView.listPath === 'string') {
      setListPath(savedView.listPath);
    } else if (savedView.listPath === null) {
      setListPath(null);
    }
  }, [mounted, setCode]);

  useEffect(() => {
    if (!workbenchHydrated) return;
    const workspaceChanged = lastWorkspaceIdRef.current !== activeWorkspaceId;
    lastWorkspaceIdRef.current = activeWorkspaceId;
    if (!workspaceChanged) return;
    const nextCode = workbenchContext.stockCode || workbenchContext.eventCode || DEFAULT_RESEARCH_CODE;
    setCode(nextCode);
  }, [
    activeWorkspaceId,
    setCode,
    workbenchContext.eventCode,
    workbenchContext.stockCode,
    workbenchHydrated,
  ]);

  useEffect(() => {
    if (!workbenchHydrated) return;
    updateWorkbenchContext({
      stockCode: resolvedCode || null,
      eventCode: resolvedCode || null,
    });
  }, [resolvedCode, updateWorkbenchContext, workbenchHydrated]);

  const submitListQuery = useCallback(
    (nextRange = range, nextStartDate = startDate, nextEndDate = endDate, nextKeyword = keyword) => {
      if (!validate()) return;
      if (nextRange === 'custom' && (!nextStartDate || !nextEndDate)) {
        setFormError('自定义时间范围需要开始与结束日期');
        return;
      }
      setFormError(null);
      const params = new URLSearchParams({ code: trimmedCode, limit: '20', keyword: nextKeyword.trim() });
      if (nextRange === 'custom') {
        params.set('startDate', nextStartDate);
        params.set('endDate', nextEndDate);
      } else {
        params.set('days', nextRange);
      }
      const newPath = `/research/list?${params.toString()}`;
      if (newPath === effectiveListPath) listQ.refetch();
      else setListPath(newPath);
    },
    [effectiveListPath, keyword, listQ, range, startDate, endDate, trimmedCode, validate],
  );

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    submitListQuery();
  }

  const fetchNews = useCallback(
    (type: string) => {
      if (['stock-news', 'forecast'].includes(type) && !validate()) return;
      setFormError(null);
      const c = trimmedCode;
      const paths: Record<string, string> = {
        'stock-news': `/research/stock-news?code=${encodeURIComponent(c)}`,
        'market-news': '/research/market-news',
        analyst: '/research/analyst-ranking',
        forecast: `/research/profit-forecast?code=${encodeURIComponent(c)}`,
        'search-research': `/research/search?code=${encodeURIComponent(c)}`,
        macro: '/research/macro',
        reports: `/research/reports?code=${encodeURIComponent(c)}`,
      };
      const newPath = paths[type] ?? `/research/reports?code=${encodeURIComponent(c)}`;
      if (newPath === newsPath) newsQ.refetch();
      else setNewsPath(newPath);
    },
    [newsPath, newsQ, trimmedCode, validate],
  );

  const reports = useMemo(() => listQ.data?.reports ?? [], [listQ.data]);
  const notices = useMemo(() => listQ.data?.notices ?? [], [listQ.data]);
  const freshness = listQ.data?.meta?.fetchedAt ?? '';
  const cache = listQ.data?.meta?.cache;
  const loading = listQ.isFetching;
  const error = formError || codeError || listQ.error;
  const showPrimaryEmptyState = !loading && !error && reports.length === 0 && notices.length === 0;
  const rangeLabel = range === 'custom' ? `${startDate || '-'} ~ ${endDate || '-'}` : `近 ${range} 天`;
  const newsTabLabel = NEWS_TABS.find((tab) => tab.key === newsTab)?.label ?? newsTab;
  const updatedAtLabel = mounted && listQ.dataUpdatedAt ? new Date(listQ.dataUpdatedAt).toLocaleString('zh-CN') : '-';
  const fetchedAtLabel = mounted && freshness ? new Date(freshness).toLocaleString('zh-CN') : '-';

  const pageActions = useMemo(
    () => [
      {
        id: 'research.refresh',
        label: '刷新研报公告',
        description: '刷新当前研报列表与资讯标签',
        keywords: ['刷新', '研报', '公告'],
        scope: 'page' as const,
        pageKey: 'research',
        run: async () => {
          await Promise.allSettled([listQ.refetch(), newsPath ? newsQ.refetch() : Promise.resolve(null)]);
          return { message: '已刷新研报公告数据' };
        },
      },
      {
        id: 'research.open-market-news',
        label: '切到市场新闻',
        description: '切换资讯标签到市场新闻并立即拉取',
        keywords: ['市场新闻', '资讯'],
        scope: 'page' as const,
        pageKey: 'research',
        run: () => {
          setNewsTab('market-news');
          fetchNews('market-news');
          return { message: '已切到市场新闻' };
        },
      },
      {
        id: 'research.expand-window',
        label: '扩到近 90 天',
        description: '把时间范围切换到近 90 天并重查',
        keywords: ['90天', '时间范围'],
        scope: 'page' as const,
        pageKey: 'research',
        run: () => {
          setRange('90');
          submitListQuery('90', startDate, endDate, keyword);
          return { message: '已扩展到近 90 天' };
        },
      },
    ],
    [endDate, fetchNews, keyword, listQ, newsPath, newsQ, startDate, submitListQuery],
  );

  usePageActions(pageActions);

  const researchSummary = `当前标的 ${resolvedCode || '未选择'}，研报 ${reports.length} 条，公告 ${notices.length} 条，资讯标签 ${newsTab}。`;
  const researchEvidence = useMemo(
    () => [
      { label: '当前标的', value: resolvedCode || '未选择' },
      { label: '研报数量', value: String(reports.length) },
      { label: '公告数量', value: String(notices.length) },
      { label: '资讯分组', value: newsTabLabel },
      { label: '抓取时间', value: fetchedAtLabel || '-' },
    ],
    [fetchedAtLabel, newsTabLabel, notices.length, reports.length, resolvedCode],
  );
  const researchLinks = useMemo(
    () => [
      resolvedCode
        ? { id: 'research-open-stock', label: '个股详情', href: `/stock?code=${encodeURIComponent(resolvedCode)}` }
        : { id: 'research-open-market', label: '行情看板', href: '/market?from=research' },
      { id: 'research-open-skills', label: '去技能中心', href: '/skills?skill=akshare-fund-news' },
      { id: 'research-open-data', label: '去数据中心', href: '/data?from=research' },
      { id: 'research-open-strategy', label: '去策略超市', href: `/strategy-market?from=research&q=${encodeURIComponent(resolvedCode || keyword || newsTab)}` },
    ],
    [keyword, newsTab, resolvedCode],
  );
  const researchRiskNotes = useMemo(() => {
    const notes: string[] = [];
    if (!resolvedCode) notes.push('当前还没有锁定研究标的，建议先确认股票代码。');
    if (showPrimaryEmptyState) notes.push('当前窗口下没有命中研报或公告，建议扩大时间范围或切换资讯分组。');
    return notes;
  }, [resolvedCode, showPrimaryEmptyState]);
  const researchResult = useMemo(
    () => {
      const localFallback = buildLocalResultContract({
        summary: researchSummary,
        status: error ? 'unavailable' : showPrimaryEmptyState ? 'empty' : 'ready',
        pageActions,
        preferredActionIds: ['research.refresh', 'research.open-market-news', 'research.expand-window'],
        recommendedLinks: researchLinks,
        recommendedNextActions: [
          resolvedCode ? '先锁定标的，再决定看研报、公告还是市场新闻。' : '先输入股票代码，避免研究页变成空列表。',
          showPrimaryEmptyState ? '当前窗口没有结果，优先扩大时间范围或切换资讯分组。' : '只有在当前窗口证据不足时再扩大时间范围。',
          '需要更强结论时再把当前结果送去 AI 或策略页。',
        ],
        evidence: researchEvidence,
        riskNotes: researchRiskNotes,
        emptyState: {
          title: '当前窗口没有命中研究内容',
          description: '先确认标的和时间范围，再决定是否扩大窗口或切到市场新闻。',
          example: 'code=600519，days=90',
        },
        freshness: freshness ? { updatedAt: freshness, label: '资讯抓取时间' } : null,
        platformMeta: {
          sourceTool: 'research-feed',
          sourceChain: [newsTabLabel, rangeLabel],
        },
        workbenchTask: defaultWorkbenchTask('research', `研究纪要：${resolvedCode || keyword || '当前资讯页'}`, resolvedCode ? `/research?code=${encodeURIComponent(resolvedCode)}` : '/research', 'research-review', {
          code: resolvedCode || null,
          range,
          newsTab,
        }),
      });
      return resolveResultContract(listQ.data?.result_contract, localFallback);
    },
    [freshness, keyword, newsTab, newsTabLabel, pageActions, range, rangeLabel, researchEvidence, researchLinks, researchRiskNotes, researchSummary, resolvedCode],
  );

  usePageContext({
    pageKey: 'research',
    title: '研报公告',
    summary: researchSummary,
    primaryGoal: '锁定研究标的和时间窗口后，尽快拿到首批可判断的证据。',
    requiredInputs: ['stockCode', 'timeRange'],
    stockCode: resolvedCode || undefined,
    objectType: resolvedCode ? 'stock' : 'research-feed',
    objectId: resolvedCode || keyword || newsTab,
    resultType: 'research-feed',
    tags: [
      range === 'custom' ? '自定义区间' : `近 ${range} 天`,
      newsTab,
      `${reports.length} 条研报`,
      `${notices.length} 条公告`,
    ],
    suggestions: [
      resolvedCode ? `总结 ${resolvedCode} 近阶段研报和公告的核心变化` : '选择股票后总结近阶段研报公告变化',
      '把当前资讯页整理成研究纪要',
      '指出当前资讯里最值得继续核验的结论',
    ],
    recommendedNextActions: researchResult.recommendedNextActions,
    recommendedActions: researchResult.recommendedActions,
    recommendedLinks: researchResult.recommendedLinks,
    evidenceSummary: evidenceToSummary(researchResult.evidence),
    riskNotes: researchResult.riskNotes ?? [],
    freshness: researchResult.freshness ?? null,
    dataFreshness: researchResult.freshness?.updatedAt ?? null,
    degradedReason: researchRiskNotes,
    raw: {
      code: resolvedCode || null,
      range,
      keyword,
      newsTab,
      reports: reports.length,
      notices: notices.length,
    },
  });

  useEffect(() => {
    if (newsPath || newsTab !== 'stock-news' || keyword.trim() || range !== '30' || listPath !== null) {
      completeStep('research');
    }
  }, [completeStep, keyword, listPath, newsPath, newsTab, range]);

  const heroPrimaryButtonCls =
    'inline-flex cursor-pointer items-center justify-center rounded-full bg-primary px-4 py-2 text-sm font-medium text-white shadow-[0_20px_40px_-24px_rgba(11,107,203,0.52)] transition hover:-translate-y-0.5 hover:shadow-[0_24px_46px_-24px_rgba(11,107,203,0.58)] disabled:cursor-not-allowed disabled:opacity-50';
  const heroSecondaryButtonCls =
    'action-chip cursor-pointer text-sm text-text-primary shadow-[0_16px_32px_-24px_rgba(15,23,42,0.28)]';
  const chipButtonCls = 'action-chip cursor-pointer text-xs text-text-primary';
  const chipLinkCls = 'action-chip text-sm no-underline text-inherit';
  const noteCardCls = 'metric-tile rounded-[22px] p-3 text-xs text-text-secondary';
  const sidePanelCls = 'panel-soft rounded-[28px] p-4 sm:p-5';

  const currentView = useMemo<Record<string, unknown>>(
    () => ({
      code,
      range,
      startDate,
      endDate,
      keyword,
      newsTab,
      listPath,
      newsPath,
    }),
    [code, endDate, keyword, listPath, newsPath, newsTab, range, startDate],
  );

  const applyView = useCallback(
    (snapshot: Record<string, unknown>) => {
      if (typeof snapshot.code === 'string') {
        setCode(snapshot.code);
      }
      if (isValidRange(snapshot.range)) {
        setRange(snapshot.range);
      }
      if (typeof snapshot.startDate === 'string') {
        setStartDate(snapshot.startDate);
      }
      if (typeof snapshot.endDate === 'string') {
        setEndDate(snapshot.endDate);
      }
      if (typeof snapshot.keyword === 'string') {
        setKeyword(snapshot.keyword);
      }
      if (isValidNewsTab(snapshot.newsTab)) {
        setNewsTab(snapshot.newsTab);
      }
      if (typeof snapshot.listPath === 'string') {
        setListPath(snapshot.listPath);
      } else if (snapshot.listPath === null) {
        setListPath(null);
      }
      if (typeof snapshot.newsPath === 'string') {
        setNewsPath(snapshot.newsPath);
      } else if (snapshot.newsPath === null) {
        setNewsPath(null);
      }
    },
    [setCode],
  );

  const primaryContent = (
    <>
      <section className="page-hero p-5 sm:p-6">
        <div className="grid gap-5 2xl:grid-cols-[minmax(0,1.2fr)_380px]">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="info">Research Workspace</Badge>
              <Badge variant={resolvedCode ? 'success' : 'warning'}>
                {resolvedCode ? `当前标的 ${resolvedCode}` : '等待选择标的'}
              </Badge>
              <Badge variant="neutral">{rangeLabel}</Badge>
              <Badge variant="neutral">{newsTabLabel}</Badge>
            </div>
            <h1 className="mb-0 mt-4 text-[2rem] font-semibold tracking-[-0.03em] text-text-primary sm:text-[2.4rem]">
              研究工作台
            </h1>
            <p className="mb-0 mt-3 max-w-3xl text-sm leading-7 text-text-secondary sm:text-[15px]">
              先锁定标的和时间窗口，再决定看研报、公告还是资讯流，避免首屏先被结果摘要和长列表抢走注意力。
            </p>
            <div className="mt-5 flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => {
                  setRange('90');
                  submitListQuery('90', startDate, endDate, keyword);
                }}
                className={heroPrimaryButtonCls}
              >
                查看近 90 天
              </button>
              <button
                type="button"
                onClick={() => {
                  setRange('7');
                  submitListQuery('7', startDate, endDate, keyword);
                }}
                className={heroSecondaryButtonCls}
              >
                查看近 7 天
              </button>
              <button
                type="button"
                onClick={() => {
                  setNewsTab('market-news');
                  fetchNews('market-news');
                }}
                className={heroSecondaryButtonCls}
              >
                查看市场新闻
              </button>
            </div>

            <div className="mt-5 grid grid-cols-2 gap-3 xl:grid-cols-4">
              <div className="rounded-[24px] border border-white/45 bg-white/38 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.55)]">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">当前标的</div>
                <div className="mt-3 text-2xl font-semibold text-text-primary">{resolvedCode || '-'}</div>
                <div className="mt-1 text-xs text-text-secondary">{keyword.trim() || '未设置关键词'}</div>
              </div>
              <div className="rounded-[24px] border border-white/45 bg-white/30 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.48)]">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">观察窗口</div>
                <div className="mt-3 text-2xl font-semibold text-text-primary">{rangeLabel}</div>
                <div className="mt-1 text-xs text-text-secondary">当前拉取区间</div>
              </div>
              <div className="rounded-[24px] border border-white/45 bg-white/26 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.42)]">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">研报 / 公告</div>
                <div className="mt-3 text-2xl font-semibold text-text-primary">
                  {reports.length} / {notices.length}
                </div>
                <div className="mt-1 text-xs text-text-secondary">当前命中条数</div>
              </div>
              <div className="rounded-[24px] border border-white/45 bg-white/24 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.38)]">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">资讯分组</div>
                <div className="mt-3 text-2xl font-semibold text-text-primary">{newsTabLabel}</div>
                <div className="mt-1 text-xs text-text-secondary">缓存 {cacheText(cache)}</div>
              </div>
            </div>
          </div>

          <div className="hidden xl:grid gap-3">
            <div className={sidePanelCls}>
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">当前聚焦</div>
              <div className="mt-3 text-base font-semibold text-text-primary">{resolvedCode || '未选择标的'}</div>
              {resolvedCode ? (
                <div className="mt-3 flex items-center gap-2">
                  <StockLink code={resolvedCode} name={resolvedCode} />
                  <WatchlistButton code={resolvedCode} name="" />
                </div>
              ) : null}
              <div className="mt-4 space-y-3">
                <div className={noteCardCls}>
                  本次窗口：<span className="font-medium text-text-primary">{rangeLabel}</span>
                </div>
                <div className={noteCardCls}>
                  当前资讯组：<span className="font-medium text-text-primary">{newsTabLabel}</span>
                </div>
                <div className={noteCardCls}>
                  最近刷新：<span className="font-medium text-text-primary">{updatedAtLabel}</span>
                </div>
              </div>
              <div className="mt-4">
                <AskAiButton
                  stockCode={resolvedCode || undefined}
                  summary={`研报 ${reports.length} 条，公告 ${notices.length} 条，资讯标签 ${newsTab}`}
                  prompt={resolvedCode ? `请总结 ${resolvedCode} 近期研报与公告变化` : '请总结当前研报公告页'}
                />
              </div>
            </div>

            <div className={sidePanelCls}>
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">数据新鲜度</div>
              <div className="mt-4 space-y-3">
                <div className={noteCardCls}>更新：{updatedAtLabel}</div>
                <div className={noteCardCls}>抓取：{fetchedAtLabel}</div>
                <div className={noteCardCls}>缓存状态：{cache ? cacheText(cache) : '未知'}</div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <SectionCard className="mt-0 p-4 sm:p-5">
        <div className="grid gap-4 2xl:grid-cols-[minmax(0,1.08fr)_minmax(320px,0.92fr)]">
          <div>
            <div className="eyebrow">Operation Workspace</div>
            <h2 className="mt-2 mb-0 text-xl font-semibold text-text-primary">先放宽或收紧范围，再进入正文</h2>
            <p className="mb-0 mt-2 text-sm leading-7 text-text-secondary">
              如果默认结果较少，优先扩大时间范围或切到市场新闻，不用先手动重填一遍表单。研究页的重点是先定范围，再决定继续追研报、公告还是资讯流。
            </p>
            <div className="mt-4 flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => {
                  setRange('90');
                  submitListQuery('90', startDate, endDate, keyword);
                }}
                className={chipButtonCls}
              >
                查看近 90 天
              </button>
              <button
                type="button"
                onClick={() => {
                  setRange('7');
                  submitListQuery('7', startDate, endDate, keyword);
                }}
                className={chipButtonCls}
              >
                查看近 7 天
              </button>
              <button
                type="button"
                onClick={() => {
                  setNewsTab('market-news');
                  fetchNews('market-news');
                }}
                className={chipButtonCls}
              >
                查看市场新闻
              </button>
            </div>
          </div>

          <div className="panel-soft rounded-[24px] p-4">
            <div className="text-sm font-medium text-text-primary">当前研究上下文</div>
            <div className="mt-3 space-y-3">
              <div className={noteCardCls}>标的：{resolvedCode || '-'}</div>
              <div className={noteCardCls}>关键词：{keyword.trim() || '未设置'}</div>
              <div className={noteCardCls}>
                研报 / 公告：{reports.length} / {notices.length}
              </div>
            </div>
          </div>
        </div>

        <div className="mt-4">
          <div className="toolbar-strip">
            <form
              onSubmit={onSubmit}
              className="grid flex-1 gap-3 lg:grid-cols-[minmax(0,220px)_120px_minmax(0,180px)_minmax(0,180px)_minmax(0,1fr)_auto] lg:items-end"
            >
              <StockCodeInput
                id="research-stock-code"
                label="股票代码"
                value={code}
                onChange={setCode}
                error={codeError}
                placeholder="如 600519"
              />
              <label className="grid gap-1 text-xs font-medium uppercase tracking-[0.12em] text-text-muted">
                <span>时间范围</span>
                <select value={range} onChange={(event) => setRange(event.target.value as Range)} className="text-sm">
                  <option value="7">近1周</option>
                  <option value="30">近1月</option>
                  <option value="90">近3月</option>
                  <option value="custom">自定义</option>
                </select>
              </label>
              {range === 'custom' ? (
                <>
                  <label className="grid gap-1 text-xs font-medium uppercase tracking-[0.12em] text-text-muted">
                    <span>开始日期</span>
                    <input
                      type="date"
                      value={startDate}
                      onChange={(event) => setStartDate(event.target.value)}
                      className="text-sm"
                    />
                  </label>
                  <label className="grid gap-1 text-xs font-medium uppercase tracking-[0.12em] text-text-muted">
                    <span>结束日期</span>
                    <input
                      type="date"
                      value={endDate}
                      onChange={(event) => setEndDate(event.target.value)}
                      className="text-sm"
                    />
                  </label>
                </>
              ) : (
                <>
                  <div className="hidden lg:block" />
                  <div className="hidden lg:block" />
                </>
              )}
              <label className="grid gap-1 text-xs font-medium uppercase tracking-[0.12em] text-text-muted">
                <span>关键词</span>
                <input
                  value={keyword}
                  onChange={(event) => setKeyword(event.target.value)}
                  placeholder="可输入行业、机构或主题词"
                  className="text-sm"
                />
              </label>
              <div className="flex flex-wrap gap-2 lg:justify-end">
                <button type="submit" disabled={loading} className={heroPrimaryButtonCls}>
                  {loading ? '查询中...' : '查询'}
                </button>
              </div>
            </form>
          </div>
        </div>
      </SectionCard>

      {error ? <ErrorState text={error} /> : null}

      <div className="panel-soft mt-3 rounded-[24px] px-4 py-3 text-sm text-text-secondary">
        更新：{updatedAtLabel} ｜ 抓取：{fetchedAtLabel} ｜ 缓存：{cacheText(cache)}
      </div>

      {!showPrimaryEmptyState || !compactLayout ? (
        <ProgressiveWorkbenchSection
          pageKey="research"
          title="研究结果工作台"
          result={researchResult}
          summaryMode="strip"
          className="mt-3"
        />
      ) : null}

      {showPrimaryEmptyState ? (
        <PageStatusCard
          status="empty"
          title="当前窗口还没有研究结果"
          reason="先确认股票代码和时间范围，再决定是否扩大窗口或切换资讯分组。"
          freshness={fetchedAtLabel}
          primaryAction={(
            <button
              type="button"
              onClick={() => submitListQuery('90', startDate, endDate, keyword)}
              className={heroPrimaryButtonCls}
            >
              扩到近 90 天
            </button>
          )}
          secondaryAction={(
            <button
              type="button"
              onClick={() => {
                setNewsTab('market-news');
                fetchNews('market-news');
              }}
              className={heroSecondaryButtonCls}
            >
              查看市场新闻
            </button>
          )}
          example="code=600519，days=90"
          className="mt-4"
        />
      ) : null}

      <section className="mt-4 grid grid-cols-1 gap-4 xl:grid-cols-2">
        {showPrimaryEmptyState ? (
          compactLayout ? null : (
          <SectionCard className="xl:col-span-2 p-5">
            <h3 className="mt-0">当前条件下暂无结果</h3>
            <p className="mb-0 mt-3 text-sm leading-7 text-text-secondary">
              近 30 天未命中时，可以直接扩大时间范围或切换到市场新闻继续查看，不用手动重新组织查询。
            </p>
            <div className="mt-4 flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => {
                  setRange('90');
                  submitListQuery('90', startDate, endDate, keyword);
                }}
                className={chipButtonCls}
              >
                查看近 90 天
              </button>
              <button
                type="button"
                onClick={() => {
                  setNewsTab('market-news');
                  fetchNews('market-news');
                }}
                className={chipButtonCls}
              >
                查看市场新闻
              </button>
              <Link href="/market" className={chipLinkCls}>
                回行情页换标的
              </Link>
            </div>
          </SectionCard>
          )
        ) : (
          <>
            <SectionCard className="p-4 sm:p-5">
              <h3 className="mt-0">研报（{reports.length}）</h3>
              <div className="mt-4 max-h-[420px] space-y-3 overflow-auto pr-1">
                {reports.map((item, index) => (
                  <div key={`r-${index}`} className="panel-soft rounded-[20px] p-4">
                    <div className="font-semibold text-text-primary">{highlight(item.title, keyword)}</div>
                    <div className="mt-2 text-xs text-text-secondary">
                      {fmt(item.date)} ｜ {fmt(item.source)}
                    </div>
                    <div className="mt-2 text-sm leading-6 text-text-secondary">
                      {highlight(item.summary || '-', keyword)}
                    </div>
                  </div>
                ))}
                {!reports.length ? (
                  <EmptyState
                    text="当前条件下没有匹配研报"
                    hint="可以扩大到近 90 天，或者去资讯与分析区直接看机构预测和研报搜索。"
                    action={
                      <>
                        <button
                          type="button"
                          onClick={() => {
                            setRange('90');
                            submitListQuery('90', startDate, endDate, keyword);
                          }}
                          className={chipButtonCls}
                        >
                          扩大到近 90 天
                        </button>
                        <button
                          type="button"
                          onClick={() => {
                            setNewsTab('search-research');
                            fetchNews('search-research');
                          }}
                          className={chipButtonCls}
                        >
                          去研报搜索
                        </button>
                      </>
                    }
                  />
                ) : null}
              </div>
            </SectionCard>

            <SectionCard className="p-4 sm:p-5">
              <h3 className="mt-0">公告（{notices.length}）</h3>
              <div className="mt-4 max-h-[420px] space-y-3 overflow-auto pr-1">
                {notices.map((item, index) => (
                  <div key={`n-${index}`} className="panel-soft rounded-[20px] p-4">
                    <div className="font-semibold text-text-primary">{highlight(item.title, keyword)}</div>
                    <div className="mt-2 text-xs text-text-secondary">
                      {fmt(item.date)} ｜ {fmt(item.source)}
                    </div>
                    <div className="mt-2 text-sm leading-6 text-text-secondary">
                      {highlight(item.summary || '-', keyword)}
                    </div>
                  </div>
                ))}
                {!notices.length ? (
                  <EmptyState
                    text="当前条件下没有匹配公告"
                    hint="如果你只是想确认近期事件，直接切到市场新闻通常比继续缩小条件更有效。"
                    action={
                      <>
                        <button
                          type="button"
                          onClick={() => {
                            setNewsTab('market-news');
                            fetchNews('market-news');
                          }}
                          className={chipButtonCls}
                        >
                          去看市场新闻
                        </button>
                        <Link href="/alerts" className={chipLinkCls}>
                          去告警中心设提醒
                        </Link>
                      </>
                    }
                  />
                ) : null}
              </div>
            </SectionCard>
          </>
        )}
      </section>

      <section className="mt-5">
        <div className="mb-2">
          <h2 className="mb-0 mt-0 text-xl font-semibold text-text-primary">资讯与分析</h2>
          <p className="mb-0 mt-2 text-sm text-text-secondary">
            资讯区保留多源视角，但用更统一的容器和操作入口来避免“表格块”和“图表块”割裂。
          </p>
        </div>
        <div>
          <TabBar tabs={NEWS_TABS} active={newsTab} onChange={setNewsTab} />
        </div>
        <SectionCard tabAttached className="p-4 sm:p-5">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <div className="text-sm text-text-secondary">当前分组：{newsTabLabel}</div>
            <button
              type="button"
              disabled={newsQ.isFetching}
              onClick={() => fetchNews(newsTab)}
              className={chipButtonCls}
            >
              {newsQ.isFetching ? '加载中...' : '查询'}
            </button>
          </div>
          {newsQ.error ? <ErrorState text={newsQ.error} /> : null}
          {newsQ.data != null
            ? (() => {
                const rows = extractArray(newsQ.data, 'items', 'analysts', 'reports', 'data');
                const columnMap: Record<
                  string,
                  Array<{
                    key: string;
                    label: string;
                    align?: 'left' | 'right' | 'center';
                    render?: (v: unknown) => ReactNode;
                  }>
                > = {
                  'stock-news': [
                    { key: 'title', label: '标题' },
                    { key: 'date', label: '日期' },
                    { key: 'source', label: '来源' },
                  ],
                  'market-news': [
                    { key: 'title', label: '标题' },
                    { key: 'date', label: '日期' },
                    { key: 'source', label: '来源' },
                  ],
                  analyst: [
                    { key: 'rank', label: '排名', align: 'right' as const },
                    { key: 'name', label: '分析师' },
                    { key: 'institution', label: '机构' },
                    { key: 'industry', label: '行业' },
                    {
                      key: 'winRate',
                      label: '胜率',
                      align: 'right' as const,
                      render: (v: unknown) => fmtPct(v as number),
                    },
                  ],
                  forecast: [
                    { key: 'date', label: '日期' },
                    { key: 'institution', label: '机构' },
                    { key: 'rating', label: '评级' },
                    {
                      key: 'epsForecast',
                      label: 'EPS预测',
                      align: 'right' as const,
                      render: (v: unknown) => fmtNum(v as number, 2),
                    },
                    {
                      key: 'netprofitForecast',
                      label: '净利润预测',
                      align: 'right' as const,
                      render: (v: unknown) => fmtAmount(v as number),
                    },
                  ],
                  'search-research': [
                    { key: 'title', label: '标题' },
                    { key: 'institution', label: '机构' },
                    { key: 'rating', label: '评级' },
                    { key: 'date', label: '日期' },
                    { key: 'stockCode', label: '代码', render: (v: unknown) => <StockLink code={String(v)} /> },
                  ],
                  reports: [
                    { key: 'title', label: '标题' },
                    { key: 'institution', label: '机构' },
                    { key: 'author', label: '作者' },
                    { key: 'rating', label: '评级' },
                    { key: 'date', label: '日期' },
                  ],
                  macro: [],
                };
                const cols = columnMap[newsTab];
                const analystChart =
                  newsTab === 'analyst' && rows.length > 0
                    ? rows.slice(0, 10).map((r: Record<string, unknown>) => ({
                        label: String(r.name ?? '').slice(0, 6),
                        value: Number(r.winRate ?? r.win_rate ?? 0) * 100,
                      }))
                    : null;
                const forecastSummary =
                  newsTab === 'forecast' && rows.length > 0
                    ? {
                        avgEps:
                          rows.reduce(
                            (s: number, r: Record<string, unknown>) => s + Number(r.epsForecast ?? r.eps_forecast ?? 0),
                            0,
                          ) / rows.length,
                        count: rows.length,
                        ratings: rows.reduce(
                          (m: Record<string, number>, r: Record<string, unknown>) => {
                            const rt = String(r.rating ?? '未知');
                            m[rt] = (m[rt] || 0) + 1;
                            return m;
                          },
                          {} as Record<string, number>,
                        ),
                      }
                    : null;
                return (
                  <>
                    {analystChart && analystChart.length > 0 ? (
                      <div className="panel-soft mb-4 rounded-[24px] p-4">
                        <h4 className="mb-0 mt-0 text-sm font-medium text-text-primary">分析师胜率 TOP10</h4>
                        <div className="mt-3">
                          <BarChart items={analystChart} height={200} yAxisName="胜率 %" horizontal />
                        </div>
                      </div>
                    ) : null}
                    {forecastSummary ? (
                      <KpiGrid cols={3} className="mb-4">
                        <KpiCard title="预测机构数" value={forecastSummary.count} />
                        <KpiCard title="平均EPS预测" value={fmtNum(forecastSummary.avgEps, 2)} />
                        <KpiCard
                          title="评级分布"
                          value={Object.entries(forecastSummary.ratings)
                            .map(([k, v]) => `${k}:${v}`)
                            .join(' ')}
                        />
                      </KpiGrid>
                    ) : null}
                    {rows.length ? (
                      <DataTable
                        rows={rows}
                        columns={cols?.length ? cols : undefined}
                        maxHeight={400}
                        onExport={() => exportCSV(rows, `research-${newsTab}`)}
                      />
                    ) : (
                      <EmptyState
                        text="当前资讯分组暂无数据"
                        hint={
                          newsTab === 'market-news'
                            ? '可以先改看个股新闻或研报搜索，避免停在空分组里。'
                            : newsTab === 'forecast'
                              ? '如果当前标的缺少盈利预测，可先看研报列表或返回行情页换成覆盖度更高的龙头标的。'
                              : '建议切换资讯分组，或回上方放宽时间范围后重新查询。'
                        }
                        action={
                          <>
                            {newsTab !== 'market-news' ? (
                              <button
                                type="button"
                                onClick={() => {
                                  setNewsTab('market-news');
                                  fetchNews('market-news');
                                }}
                                className={chipButtonCls}
                              >
                                看市场新闻
                              </button>
                            ) : null}
                            {newsTab !== 'reports' ? (
                              <button
                                type="button"
                                onClick={() => {
                                  setNewsTab('reports');
                                  fetchNews('reports');
                                }}
                                className={chipButtonCls}
                              >
                                看研报列表
                              </button>
                            ) : null}
                            <Link href="/market" className={chipLinkCls}>
                              回行情页换标的
                            </Link>
                          </>
                        }
                      />
                    )}
                  </>
                );
              })()
            : null}
        </SectionCard>
      </section>
    </>
  );

  const secondaryContent = (
    <SectionCard className="p-4 sm:p-5">
      <div className="eyebrow">Research Summary</div>
      <h3 className="mt-2 mb-0 text-lg font-semibold text-text-primary">研究工作区摘要</h3>
      <div className="mt-4 grid gap-3">
        <div className="metric-tile rounded-[24px] p-4">
          <div className="metric-label">研究对象</div>
          <div className="metric-value mt-3 text-[1.45rem]">{resolvedCode || '-'}</div>
          <div className="mt-2 text-xs text-text-secondary">
            {range === 'custom' ? `${startDate || '-'} ~ ${endDate || '-'}` : `近 ${range} 天`}
          </div>
        </div>
        <div className="metric-tile rounded-[24px] p-4">
          <div className="metric-label">信息源</div>
          <div className="metric-value mt-3 text-[1.45rem]">{newsTabLabel}</div>
          <div className="mt-2 text-xs text-text-secondary">
            研报 / 公告 {reports.length} / {notices.length}
          </div>
        </div>
        <div className="metric-tile rounded-[24px] p-4">
          <div className="metric-label">检索状态</div>
          <div className="metric-value mt-3 text-[1.45rem]">{keyword.trim() || '未设关键词'}</div>
          <div className="mt-2 text-xs text-text-secondary">缓存 {cache ? cacheText(cache) : '未知'}</div>
        </div>
        <div className="panel-soft rounded-[24px] p-4 text-xs text-text-secondary">
          保存视图后，可把当前标的、时间窗口、关键词和资讯标签打包成研究快照，在不同工作区之间复用。
        </div>
      </div>
    </SectionCard>
  );

  return (
    <PageContainer>
      <WorkspaceToolbar
        pageKey="research"
        currentView={currentView}
        onApplyView={applyView}
        supportsPagePanels
        mobileSummaryMode="hidden"
      />
      <WorkspaceSplitLayout
        pageKey="research"
        primary={primaryContent}
        secondary={secondaryContent}
        primaryLabel="研究主区"
        secondaryLabel="研究摘要"
        defaultMobileTab="primary"
      />
    </PageContainer>
  );
}
