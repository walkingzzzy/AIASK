'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import Link from 'next/link';
import { AskAiButton } from '@/components/ask-ai-button';
import { useOnboarding } from '@/components/onboarding';
import WorkspaceSplitLayout from '@/components/workspace-split-layout';
import WorkspaceToolbar from '@/components/workspace-toolbar';
import { Badge, PageContainer, TabBar, SectionCard, StockCodeInput, DataTable } from '@/components/ui';
import { ProgressBar } from '@/components/ui';
import { useApiQuery } from '@/hooks/use-api-query';
import { useHydrated } from '@/hooks/use-hydrated';
import { usePageActions } from '@/hooks/use-page-actions';
import { usePageContext } from '@/hooks/use-page-context';
import { useStableSearchParams } from '@/hooks/use-stable-search-params';
import { useStockCode } from '@/hooks/use-stock-code';
import { useMobile } from '@/hooks/use-mobile';
import { LoadingState, ErrorState, EmptyState } from '@/components/status-state';
import { fmtNum } from '@/lib/data-utils';
import { exportCSV } from '@/lib/export';
import { StockLink } from '@/components/stock-link';
import { WatchlistButton } from '@/components/watchlist-button';
import { RESPONSIVE_BREAKPOINTS } from '@/lib/responsive-layout';
import ResultWorkbench from '@/components/result-workbench';
import { useCopilotStore } from '@/store/copilot-store';
import { selectActiveWorkspace, useWorkbenchStore } from '@/store/workbench-store';
import type { ResultAction, ResultContract, ResultLink } from '@aiask/shared-types';

const TABS = [
  { key: 'similar', label: '相似股票' },
  { key: 'semantic', label: '语义搜索' },
  { key: 'kline', label: 'K线搜索' },
] as const;

type Tab = (typeof TABS)[number]['key'];
const SEMANTIC_EXAMPLES: string[] = [];
const STOCK_EXAMPLES: string[] = [];
const HERO_PRIMARY_BUTTON_CLS =
  'inline-flex cursor-pointer items-center justify-center rounded-full bg-primary px-4 py-2 text-sm font-medium text-white shadow-[0_20px_40px_-24px_rgba(11,107,203,0.52)] transition hover:-translate-y-0.5 hover:shadow-[0_24px_46px_-24px_rgba(11,107,203,0.58)] disabled:cursor-not-allowed disabled:opacity-50';
const HERO_SECONDARY_BUTTON_CLS =
  'action-chip cursor-pointer text-sm text-text-primary shadow-[0_16px_32px_-24px_rgba(15,23,42,0.28)]';
const CHIP_BUTTON_CLS = 'action-chip cursor-pointer text-xs text-text-primary';
const LINK_CHIP_CLS = 'action-chip text-sm no-underline text-inherit';
const NOTE_CARD_CLS = 'metric-tile rounded-[22px] p-3 text-xs text-text-secondary';
const PANEL_CLS = 'panel-soft rounded-[28px] p-4 sm:p-5';
const FIELD_CLS =
  'h-11 rounded-[20px] border border-white/65 bg-white/55 px-4 text-sm text-text-primary shadow-[inset_0_1px_0_rgba(255,255,255,0.75)] outline-none transition placeholder:text-text-muted focus:border-primary/45 focus:bg-white/72';

function isRecord(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === 'object' && !Array.isArray(value);
}

function readSearchItems(payload: unknown): Record<string, unknown>[] {
  const record = isRecord(payload) ? payload : {};
  const nested = isRecord(record.data) ? record.data : {};
  const candidates = [
    record.items,
    record.results,
    record.similar_stocks,
    nested.items,
    nested.results,
    nested.similar_stocks,
  ];
  const items = candidates.find(Array.isArray);
  if (!Array.isArray(items)) {
    return [];
  }
  return items.filter((item): item is Record<string, unknown> => isRecord(item));
}

export default function SearchPage() {
  const { completeStep } = useOnboarding();
  const searchParams = useStableSearchParams();
  const initialSemanticQuery = searchParams.get('q')?.trim() || searchParams.get('query')?.trim() || '';
  const initialCode = searchParams.get('code')?.trim() || '';
  const initialUrlAppliedRef = useRef(false);
  const hydrated = useHydrated();
  const compactLayoutDetected = useMobile(RESPONSIVE_BREAKPOINTS.dockOverlay);
  const compactLayout = hydrated ? compactLayoutDetected : true;
  const workbenchHydrated = useWorkbenchStore((state) => state.hydrated);
  const workbenchContext = useWorkbenchStore((state) => selectActiveWorkspace(state).context);
  const updateWorkbenchContext = useWorkbenchStore((state) => state.updateContext);
  const setDockOpen = useCopilotStore((state) => state.setDockOpen);
  const setPendingInject = useCopilotStore((state) => state.setPendingInject);
  const [tab, setTab] = useState<Tab>(() => (initialSemanticQuery ? 'semantic' : 'similar'));
  const { code, setCode, codeError, validate, trimmedCode } = useStockCode(initialCode);
  const [query, setQuery] = useState(initialSemanticQuery);
  const [queryError, setQueryError] = useState<string | null>(null);
  const [queryPath, setQueryPath] = useState<string | null>(null);
  const { data, isFetching: isPending, error, refetch } = useApiQuery<unknown>(queryPath, { critical: true });

  const submit = useCallback(() => {
    let p: string;
    if (tab === 'semantic') {
      if (!query.trim()) {
        setQueryError('请输入搜索关键词');
        return;
      }
      setQueryError(null);
      p = `/search/semantic?query=${encodeURIComponent(query.trim())}`;
    } else {
      if (!validate()) return;
      const endpoint = tab === 'similar' ? '/search/similar' : '/search/vector-kline';
      p = `${endpoint}?code=${encodeURIComponent(trimmedCode)}`;
    }
    if (p === queryPath) refetch();
    else setQueryPath(p);
  }, [query, queryPath, refetch, tab, trimmedCode, validate]);

  useEffect(() => {
    if (initialUrlAppliedRef.current) return;
    initialUrlAppliedRef.current = true;
    if (initialSemanticQuery) {
      queueMicrotask(() => {
        setTab('semantic');
        setQuery(initialSemanticQuery);
        setQueryError(null);
        setQueryPath(`/search/semantic?query=${encodeURIComponent(initialSemanticQuery)}`);
      });
      return;
    }
    if (initialCode) {
      queueMicrotask(() => {
        setTab('similar');
        setCode(initialCode);
        setQueryPath(`/search/similar?code=${encodeURIComponent(initialCode)}`);
      });
    }
  }, [initialCode, initialSemanticQuery, setCode]);

  const rows = useMemo(() => {
    const arr = readSearchItems(data);
    return arr
      .map((r, i) => ({
      rank: i + 1,
      ...r,
      code: String(r.code ?? r.stock_code ?? r.symbol ?? ''),
      name: String(r.name ?? r.stock_name ?? r.display_name ?? ''),
      industry: r.industry ?? r.sector ?? null,
      similarity: r.similarity ?? r.score ?? null,
      score: r.score ?? r.similarity,
    }))
      .filter((row) => row.code || row.name);
  }, [data]);
  const resultContract = useMemo(
    () =>
      ((data && typeof data === 'object' && !Array.isArray(data)
        ? (data as Record<string, unknown>).result_contract
        : null) as ResultContract | null),
    [data],
  );
  const hasSearchOutcome = rows.length > 0 || Boolean(resultContract);

  const similarColumns = useMemo(
    () => [
      { key: 'rank', label: '#', width: 50 },
      { key: 'code', label: '代码', width: 90 },
      { key: 'name', label: '名称', width: 100 },
      {
        key: 'similarity',
        label: '相似度',
        render: (v: unknown) => {
          const n = Number(v ?? 0);
          return (
            <div className="flex items-center gap-2">
              <ProgressBar value={n * 100} max={100} />
              <span className="text-xs whitespace-nowrap">{fmtNum(n * 100, 1)}%</span>
            </div>
          );
        },
      },
      { key: 'industry', label: '行业' },
    ],
    [],
  );
  const klineColumns = useMemo(
    () => [
      { key: 'rank', label: '#', width: 50 },
      { key: 'code', label: '代码', width: 90 },
      { key: 'name', label: '名称', width: 100 },
      {
        key: 'score',
        label: '匹配度',
        render: (v: unknown) => {
          const n = Number(v ?? 0);
          return (
            <div className="flex items-center gap-2">
              <ProgressBar value={n * 100} max={100} />
              <span className="text-xs whitespace-nowrap">{fmtNum(n * 100, 1)}%</span>
            </div>
          );
        },
      },
      { key: 'industry', label: '行业' },
    ],
    [],
  );

  const semanticColumns = useMemo(
    () => [
      { key: 'rank', label: '#', width: 50 },
      { key: 'code', label: '代码', width: 90 },
      { key: 'name', label: '名称', width: 100 },
      { key: 'score', label: '得分', align: 'right' as const, render: (v: unknown) => fmtNum(Number(v ?? 0), 2) },
      { key: 'industry', label: '行业' },
    ],
    [],
  );

  const columns = tab === 'similar' ? similarColumns : tab === 'kline' ? klineColumns : semanticColumns;
  const primaryResult = (rows[0] ?? null) as Record<string, unknown> | null;
  const primaryCode = String(primaryResult?.code ?? '').trim();
  const primaryName = String(primaryResult?.name ?? primaryCode).trim();
  const resultLinks = useMemo(
    () =>
      primaryCode
        ? [
            { label: '个股详情', href: `/stock?code=${encodeURIComponent(primaryCode)}` },
            { label: '技术分析', href: `/technical?code=${encodeURIComponent(primaryCode)}` },
            { label: '资金流', href: `/fund-flow?code=${encodeURIComponent(primaryCode)}` },
            { label: '情绪分析', href: `/sentiment?code=${encodeURIComponent(primaryCode)}` },
            { label: '基本面', href: `/fundamental?code=${encodeURIComponent(primaryCode)}` },
          ]
        : [],
    [primaryCode],
  );
  const activeTabLabel = TABS.find((item) => item.key === tab)?.label ?? '智能搜索';
  const activePrompt = tab === 'semantic' ? query.trim() || '等待输入主题词' : trimmedCode || '等待输入股票代码';
  const tabDescription =
    tab === 'semantic'
      ? '按主题词拉出候选标的，更适合从方向和叙事出发搭建研究清单。'
      : tab === 'similar'
        ? '从一只熟悉标的反向找相似公司，快速补齐同赛道对照组。'
        : '用 K 线结构检索相似走势，适合寻找形态一致的观察池。';
  const heroSummary = rows.length
    ? `当前模式 ${activeTabLabel}，已返回 ${rows.length} 条结果，优先结果 ${primaryCode || '无'}。`
    : `当前模式 ${activeTabLabel}，等待发起一次搜索。`;
  const heroNotes =
    tab === 'semantic'
      ? [
          '先用行业、风格或市场叙事做宽泛搜索，再从结果里选一只继续深挖。',
          '如果结果过散，优先缩短语义词，把“新能源龙头”改成“储能逆变器龙头”。',
          '拿到首条结果后，建议继续去技术面与资金流页做交叉验证。',
        ]
      : [
          '相似股票更适合横向比较商业模式与估值，K 线搜索更适合观察交易结构。',
          '第一次使用建议先跑你熟悉的真实标的或当前自选股，便于判断结果是否合理。',
          '结果出来后优先看首条命中，再决定是否把其加入自选或转去研究页。',
        ];
  const quickJumpLinks = useMemo(
    () =>
      primaryCode
        ? resultLinks
        : [
            { label: '去行情看板', href: '/market' },
            { label: '查看自选股', href: '/watchlist' },
            { label: '继续研究页', href: '/research' },
          ],
    [primaryCode, resultLinks],
  );
  const searchResultLinks = useMemo<ResultLink[]>(
    () =>
      (primaryCode ? resultLinks : quickJumpLinks).map((link, index) => ({
        id: `search-link-${index}`,
        label: link.label,
        href: link.href,
      })),
    [primaryCode, quickJumpLinks, resultLinks],
  );
  const searchResultSummary = resultContract?.summary ?? heroSummary;
  const searchEvidenceSummary = useMemo(
    () => resultContract?.evidence?.map((item) => `${item.label}：${item.value}`) ?? [],
    [resultContract?.evidence],
  );
  const searchResultActions = useMemo<ResultAction[]>(
    () =>
      rows.length > 0
        ? [
            ...(primaryCode
              ? [{
                  id: 'search.open-stock-detail',
                  actionId: 'global.open-stock-detail',
                  label: '打开个股详情',
                  description: '直接打开当前优先股票的实时内容页。',
                  payload: {
                    code: primaryCode,
                  },
                } satisfies ResultAction]
              : []),
            {
              id: 'search.open-copilot-followup',
              actionId: 'search.open-copilot-followup',
              label: '打开 Copilot 解读结果',
              description: '把当前搜索结果注入 Copilot，继续决定下一步研究动作。',
            },
          ]
        : [],
    [primaryCode, rows.length],
  );
  const searchCompareContent = useMemo(() => {
    if (rows.length < 2) return null;
    return (
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {rows.slice(0, 3).map((row) => {
          const entry = row as Record<string, unknown>;
          return (
            <div key={String(entry.code ?? entry.rank)} className="metric-tile rounded-[22px] p-4">
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">
                {String(entry.code ?? '候选标的')}
              </div>
              <div className="mt-3 text-base font-semibold text-text-primary">
                {String(entry.name ?? entry.code ?? '未命名')}
              </div>
              <div className="mt-2 text-xs leading-6 text-text-secondary">
                行业 {String(entry.industry ?? '未知')} ｜ 得分 {fmtNum(Number(entry.score ?? 0), 2)}
              </div>
            </div>
          );
        })}
      </div>
    );
  }, [rows]);
  const searchVisualContent = useMemo(() => {
    const counts = rows.reduce<Record<string, number>>((acc, row) => {
      const entry = row as Record<string, unknown>;
      const key = String(entry.industry ?? '未知');
      acc[key] = (acc[key] ?? 0) + 1;
      return acc;
    }, {});
    const items = Object.entries(counts).sort((left, right) => right[1] - left[1]).slice(0, 6);
    if (items.length === 0) return null;
    return (
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {items.map(([industry, count]) => (
          <div key={industry} className="metric-tile rounded-[22px] p-4">
            <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">行业分布</div>
            <div className="mt-3 text-base font-semibold text-text-primary">{industry}</div>
            <div className="mt-2 text-xs text-text-secondary">{count} 只候选股票</div>
          </div>
        ))}
      </div>
    );
  }, [rows]);
  const mobileSummary = (
    <div className="rounded-[20px] border border-white/50 bg-white/24 px-4 py-2 text-sm text-text-secondary">
      <span className="font-medium text-text-primary">{activeTabLabel}</span>
      <span className="mx-2 text-text-muted">/</span>
      <span>{activePrompt}</span>
      <span className="mx-2 text-text-muted">/</span>
      <span>{rows.length} 条结果</span>
    </div>
  );

  usePageContext({
    pageKey: 'search',
    title: '智能搜索',
    summary: rows.length
      ? `当前为 ${tab} 模式，已返回 ${rows.length} 条结果，优先结果 ${primaryCode || '无'}。`
      : hasSearchOutcome
        ? `当前为 ${tab} 模式，搜索已完成，但当前没有命中可继续查看的股票结果。`
      : `智能搜索页，当前模式 ${tab === 'semantic' ? '语义搜索' : tab === 'similar' ? '相似股票' : 'K 线搜索'}。`,
    stockCode: tab === 'semantic' ? primaryCode || undefined : trimmedCode || primaryCode || undefined,
    objectType: primaryCode ? 'stock' : hasSearchOutcome ? 'stock-list' : undefined,
    objectId: primaryCode || query.trim() || trimmedCode || undefined,
    resultType: hasSearchOutcome ? 'search-result' : undefined,
    tags: [tab, `${rows.length} 条结果`],
    suggestions: [
      '总结当前搜索结果里最值得继续跟进的股票',
      tab === 'semantic' ? '优化当前语义搜索词并给出更聚焦的版本' : '解释当前相似/形态搜索的命中逻辑',
      '把结果整理成下一步研究路线',
    ],
    recommendedActions: searchResultActions,
    recommendedLinks: searchResultLinks,
    evidenceSummary: searchEvidenceSummary,
    riskNotes: resultContract?.riskNotes ?? [],
    freshness: resultContract?.freshness ?? null,
    raw: {
      tab,
      query,
      code: trimmedCode,
      resultCount: rows.length,
      primaryCode,
    },
  });

  const pageActions = useMemo(
    () => [
      {
        id: 'search.open-copilot-followup',
        label: '打开 Copilot 解读结果',
        description: '把当前搜索结果注入 Copilot，并给出下一步研究建议。',
        keywords: ['copilot', '结果解读', '追问'],
        scope: 'page' as const,
        pageKey: 'search',
        run: () => {
          if (!searchResultSummary) {
            throw new Error('当前还没有可解读的搜索结果');
          }
          setPendingInject({
            prompt: `请解读当前${activeTabLabel}结果，并给出下一步研究建议。`,
            contextPatch: {
              ...(primaryCode || trimmedCode ? { stockCode: primaryCode || trimmedCode } : {}),
              summary: searchResultSummary,
              resultType: 'search-result',
              recommendedActions: searchResultActions,
              recommendedLinks: searchResultLinks,
              evidenceSummary: searchEvidenceSummary,
              riskNotes: resultContract?.riskNotes ?? [],
              freshness: resultContract?.freshness ?? null,
              raw: {
                tab,
                query,
                code: trimmedCode,
                primaryCode,
              },
            },
          });
          setDockOpen(true);
          return { message: '已打开 Copilot 并注入搜索结果' };
        },
      },
      {
        id: 'search.run',
        label: '执行当前搜索',
        description: '按当前 tab 和输入重新执行搜索',
        keywords: ['搜索', '执行'],
        scope: 'page' as const,
        pageKey: 'search',
        run: () => {
          submit();
          return { message: '已触发搜索' };
        },
      },
      {
        id: 'search.try-semantic',
        label: '填入语义搜索词',
        description: '切换到语义搜索并填入查询词',
        keywords: ['语义', 'query'],
        scope: 'page' as const,
        pageKey: 'search',
        run: (payload?: Record<string, unknown>) => {
          if (typeof payload?.query === 'string') {
            setTab('semantic');
            setQuery(payload.query);
            setQueryError(null);
            return { message: `已填入搜索词：${payload.query}` };
          }
          return { message: '缺少 query 参数' };
        },
      },
      {
        id: 'search.set-code',
        label: '填入股票代码',
        description: '切换到股票搜索并填入代码',
        keywords: ['代码', 'stock'],
        scope: 'page' as const,
        pageKey: 'search',
        run: (payload?: Record<string, unknown>) => {
          if (typeof payload?.code === 'string') {
            setTab('similar');
            setCode(payload.code);
            return { message: `已填入股票代码 ${payload.code}` };
          }
          return { message: '缺少 code 参数' };
        },
      },
    ],
    [
      activeTabLabel,
      primaryCode,
      query,
      resultContract?.freshness,
      resultContract?.riskNotes,
      searchEvidenceSummary,
      searchResultActions,
      searchResultLinks,
      searchResultSummary,
      setCode,
      setDockOpen,
      setPendingInject,
      submit,
      tab,
      trimmedCode,
    ],
  );

  usePageActions(pageActions);

  useEffect(() => {
    if (!workbenchHydrated) return;
    if (!trimmedCode && workbenchContext.stockCode) {
      setCode(workbenchContext.stockCode);
    }
  }, [setCode, trimmedCode, workbenchContext.stockCode, workbenchHydrated]);

  useEffect(() => {
    if (!workbenchHydrated) return;
    updateWorkbenchContext({
      stockCode: primaryCode || trimmedCode || null,
      sourcePage: queryPath ? 'search' : null,
      taskType: queryPath
        ? (tab === 'semantic' ? 'semantic_search' : tab === 'similar' ? 'similar_search' : 'kline_search')
        : null,
      resultType: queryPath ? 'search-result' : null,
    });
  }, [primaryCode, queryPath, tab, trimmedCode, updateWorkbenchContext, workbenchHydrated]);

  useEffect(() => {
    if (queryPath && hasSearchOutcome) {
      completeStep('ai-tools');
    }
  }, [completeStep, hasSearchOutcome, queryPath]);

  const currentView = useMemo<Record<string, unknown>>(
    () => ({ tab, query, code: trimmedCode, queryPath }),
    [query, queryPath, tab, trimmedCode],
  );

  const applyView = useCallback(
    (snapshot: Record<string, unknown>) => {
      if (snapshot.tab === 'semantic' || snapshot.tab === 'similar' || snapshot.tab === 'kline') {
        setTab(snapshot.tab);
      }
      if (typeof snapshot.query === 'string') {
        setQuery(snapshot.query);
        setQueryError(null);
      }
      if (typeof snapshot.code === 'string') {
        setCode(snapshot.code);
      }
      if (typeof snapshot.queryPath === 'string') {
        setQueryPath(snapshot.queryPath);
      } else if (snapshot.queryPath === null) {
        setQueryPath(null);
      }
    },
    [setCode],
  );

  const searchPanel = (
    <div className="grid gap-4 xl:h-full xl:grid-rows-[auto_minmax(0,1fr)]">
      <div className={PANEL_CLS}>
        <div className="flex flex-col gap-4">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
            <div>
              <div className="eyebrow">搜索输入</div>
              <h2 className="mb-0 mt-2 text-xl font-semibold text-text-primary">输入、搜索与结果阅读顺序</h2>
              {!compactLayout ? <p className="mb-0 mt-2 max-w-3xl text-sm leading-7 text-text-secondary">{tabDescription}</p> : null}
            </div>
            <Badge variant="info">步骤 1</Badge>
          </div>

          <div>
            <TabBar
              tabs={TABS}
              active={tab}
              onChange={(key) => {
                setTab(key);
                setQueryPath(null);
              }}
            />
          </div>
        </div>
        <SectionCard tabAttached className={compactLayout ? 'min-h-0' : 'min-h-[560px]'}>
          <div className="space-y-4">
            <div className="space-y-4">
              <div className="metric-tile rounded-[24px] p-4">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">当前输入焦点</div>
                <div className="mt-3 text-lg font-semibold text-text-primary">{activePrompt}</div>
                {!compactLayout ? <div className="mt-2 text-sm text-text-secondary">{tabDescription}</div> : null}
              </div>

              {tab === 'semantic' ? (
                <div className="grid gap-4">
                  <label htmlFor="semantic-search-query" className="grid gap-2 text-xs text-text-secondary">
                    <span className="font-medium uppercase tracking-[0.12em] text-text-muted">搜索关键词</span>
                    <div className="flex flex-wrap items-center gap-2">
                      <input
                        id="semantic-search-query"
                        value={query}
                        onChange={(e) => {
                          setQuery(e.target.value);
                          setQueryError(null);
                        }}
                        placeholder="输入搜索词，如：新能源龙头"
                        className={`${FIELD_CLS} w-full sm:min-w-[320px] sm:flex-1`}
                      />
                      <button type="button" disabled={isPending} onClick={submit} className={HERO_PRIMARY_BUTTON_CLS}>
                        {isPending ? '搜索中...' : '执行语义搜索'}
                      </button>
                    </div>
                  </label>
                  <div className="flex flex-wrap gap-2">
                    {SEMANTIC_EXAMPLES.map((example) => (
                      <button
                        key={example}
                        type="button"
                        onClick={() => {
                          setQuery(example);
                          setQueryError(null);
                        }}
                        className={CHIP_BUTTON_CLS}
                      >
                        {example}
                      </button>
                    ))}
                  </div>
                  {queryError ? <span className="text-xs text-error">{queryError}</span> : null}
                </div>
              ) : (
                <div className="grid gap-4">
                  <div className="flex flex-wrap items-end gap-3">
                    <div className="min-w-[220px] flex-1">
                      <StockCodeInput
                        id="search-stock-code"
                        label="股票代码"
                        value={code}
                        onChange={setCode}
                        error={codeError}
                        placeholder="如 600519"
                      />
                    </div>
                    <button type="button" disabled={isPending} onClick={submit} className={HERO_PRIMARY_BUTTON_CLS}>
                      {isPending ? '搜索中...' : tab === 'similar' ? '查找相似股票' : '执行 K 线搜索'}
                    </button>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {STOCK_EXAMPLES.map((example) => (
                      <button key={example} type="button" onClick={() => setCode(example)} className={CHIP_BUTTON_CLS}>
                        示例 {example}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {isPending ? <LoadingState text="搜索中..." /> : null}
              {error ? <ErrorState text={error} hint="请检查输入后重试" /> : null}
              {!isPending && !data && !error ? (
                compactLayout ? (
                  <div className="rounded-[24px] border border-dashed border-white/55 bg-white/18 px-4 py-4 text-sm text-text-secondary">
                    <div className="font-medium text-text-primary">
                      {tab === 'semantic' ? '先输入主题词开始语义搜索' : '先输入股票代码开始搜索'}
                    </div>
                    <div className="mt-2 leading-6">
                      {tab === 'semantic'
                        ? '建议先用行业或风格词拉一轮候选，再决定是否进入个股详情。'
                        : '建议先输入你当前正在研究的真实标的，再把结果联动到详情、技术面或基本面页。'}
                    </div>
                    <div className="mt-3 flex flex-wrap gap-2">
                      {(tab === 'semantic' ? SEMANTIC_EXAMPLES : STOCK_EXAMPLES).slice(0, 2).map((example) => (
                        <button
                          key={example}
                          type="button"
                          onClick={() => {
                            if (tab === 'semantic') {
                              setQuery(example);
                              setQueryError(null);
                            } else {
                              setCode(example);
                            }
                          }}
                          className={LINK_CHIP_CLS}
                        >
                          {tab === 'semantic' ? example : `示例 ${example}`}
                        </button>
                      ))}
                    </div>
                  </div>
                ) : (
                  <EmptyState
                    text={tab === 'semantic' ? '输入主题词后开始语义搜索' : '输入股票代码后开始相似/形态搜索'}
                    hint={
                      tab === 'semantic'
                        ? '先用行业、风格或主题词快速拉出候选，再继续跳到个股详情、技术面或基本面页面。'
                        : '先输入一只真实股票代码，搜索结果出来后再进入个股详情、资金流、技术分析等下一步动作。'
                    }
                    action={
                      <>
                        {tab === 'semantic'
                          ? SEMANTIC_EXAMPLES.slice(0, 2).map((example) => (
                              <button
                                key={example}
                                type="button"
                                onClick={() => {
                                  setQuery(example);
                                  setQueryError(null);
                                }}
                                className={LINK_CHIP_CLS}
                              >
                                试试“{example}”
                              </button>
                            ))
                          : STOCK_EXAMPLES.slice(0, 2).map((example) => (
                              <button
                                key={example}
                                type="button"
                                onClick={() => setCode(example)}
                                className={LINK_CHIP_CLS}
                              >
                                示例 {example}
                              </button>
                            ))}
                        <Link href="/watchlist" className={LINK_CHIP_CLS}>
                          查看自选股
                        </Link>
                      </>
                    }
                  />
                )
              ) : null}
            </div>

            <div>
              {hasSearchOutcome ? (
                <div className="space-y-4">
                  {resultContract ? (
                    <ResultWorkbench
                      pageKey="search"
                      title="搜索结果下一步"
                      result={resultContract}
                      compareContent={searchCompareContent}
                      visualContent={searchVisualContent}
                      extraActions={searchResultActions}
                      extraLinks={searchResultLinks}
                    />
                  ) : null}
                  {primaryCode ? (
                    <div className={`${PANEL_CLS} p-4`}>
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div>
                          <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">
                            Result Focus
                          </div>
                          <div className="mt-2 text-lg font-semibold text-text-primary">{primaryName || primaryCode}</div>
                          <p className="mb-0 mt-2 text-sm leading-7 text-text-secondary">
                            当前优先结果已经可继续联动到个股详情、技术面与资金流页，建议先确认它是不是最值得进入观察池的那一只。
                          </p>
                        </div>
                        <div className="flex flex-wrap items-center gap-2">
                          <StockLink code={primaryCode} name={primaryName || primaryCode} />
                          <WatchlistButton code={primaryCode} name={primaryName || primaryCode} />
                        </div>
                      </div>
                      <div className="mt-4 flex flex-wrap gap-2">
                        {resultLinks.map((link) => (
                          <Link key={link.href} href={link.href} className={LINK_CHIP_CLS}>
                            {link.label}
                          </Link>
                        ))}
                      </div>
                    </div>
                  ) : null}
                  {rows.length > 0 ? (
                    <DataTable
                      rows={rows}
                      columns={columns}
                      maxHeight={500}
                      onExport={() => exportCSV(rows, `search-${tab}`)}
                    />
                  ) : null}
                </div>
              ) : null}

              {!isPending && !!data && !error && rows.length === 0 ? (
                <EmptyState
                  text="本次搜索没有匹配结果"
                  hint={
                    tab === 'semantic'
                      ? '可以换一个更通用的主题词，或改从具体股票出发再去技术/基本面页继续查。'
                      : '可以换一个真实股票代码、切换搜索模式，或直接去行情、自选和研究页重新选择标的。'
                  }
                  action={
                    <>
                      <Link href="/market" className={LINK_CHIP_CLS}>
                        去行情看板
                      </Link>
                      <Link href="/watchlist" className={LINK_CHIP_CLS}>
                        回到自选
                      </Link>
                      <Link href="/research" className={LINK_CHIP_CLS}>
                        继续做研究
                      </Link>
                    </>
                  }
                />
              ) : null}
            </div>
          </div>
        </SectionCard>
      </div>
    </div>
  );

  const workspacePanel = compactLayout ? (
    <div className="space-y-3">
      <div className="rounded-[24px] border border-white/50 bg-white/24 px-4 py-4">
        <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">搜索工作区摘要</div>
        <div className="mt-2 text-sm font-semibold text-text-primary">
          {activeTabLabel} ｜ {rows.length} 条 ｜ {primaryCode || activePrompt}
        </div>
      </div>
      <details className="rounded-[24px] border border-white/50 bg-white/24 px-4 py-3">
        <summary className="cursor-pointer list-none text-sm font-medium text-text-primary">
          {primaryCode ? `围绕 ${primaryName || primaryCode} 继续深入` : '展开下一步联动'}
        </summary>
        <div className="mt-3 space-y-3">
          <div className={NOTE_CARD_CLS}>{primaryCode ? heroNotes[0] : '先跑出一组候选结果，再决定是否进入详情页。'}</div>
          <div className="flex flex-wrap gap-2">
            {(primaryCode ? resultLinks.slice(0, 3) : quickJumpLinks.slice(0, 3)).map((link) => (
              <Link key={link.href} href={link.href} className={LINK_CHIP_CLS}>
                {link.label}
              </Link>
            ))}
          </div>
        </div>
      </details>
    </div>
  ) : (
    <div className="grid gap-4 xl:h-full xl:grid-rows-[auto_auto_minmax(0,1fr)]">
      <div className={PANEL_CLS}>
        <div className="eyebrow">搜索摘要</div>
        <h2 className="mb-0 mt-2 text-lg font-semibold text-text-primary">搜索工作区摘要</h2>
        <div className="mt-4 grid gap-3">
          <div className="metric-tile rounded-[24px] p-4">
            <div className="metric-label">当前模式</div>
            <div className="mt-3 text-xl font-semibold text-text-primary">{activeTabLabel}</div>
            <div className="mt-2 text-xs text-text-secondary">{tabDescription}</div>
          </div>
          <div className="grid gap-3 sm:grid-cols-3 xl:grid-cols-1">
            <div className="metric-tile rounded-[24px] p-4">
              <div className="metric-label">结果数</div>
              <div className="mt-3 text-2xl font-semibold text-text-primary">{rows.length}</div>
              <div className="mt-1 text-xs text-text-secondary">当前检索返回条目</div>
            </div>
            <div className="metric-tile rounded-[24px] p-4">
              <div className="metric-label">输入对象</div>
              <div className="mt-3 text-sm font-semibold text-text-primary">{activePrompt}</div>
              <div className="mt-1 text-xs text-text-secondary">当前已填入的主查询对象</div>
            </div>
            <div className="metric-tile rounded-[24px] p-4">
              <div className="metric-label">优先结果</div>
              <div className="mt-3 text-sm font-semibold text-text-primary">{primaryCode || '待返回'}</div>
              <div className="mt-1 text-xs text-text-secondary">{primaryName || '运行一次搜索后自动更新'}</div>
            </div>
          </div>
        </div>
      </div>

      <div className={PANEL_CLS}>
        <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">阅读建议</div>
        <div className="mt-4 space-y-3">
          {heroNotes.map((note) => (
            <div key={note} className={NOTE_CARD_CLS}>
              {note}
            </div>
          ))}
        </div>
      </div>

      <div className={PANEL_CLS}>
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">下一步联动</div>
            <h3 className="mb-0 mt-2 text-base font-semibold text-text-primary">
              {primaryCode ? `围绕 ${primaryName || primaryCode} 继续深入` : '先跑出一组候选结果'}
            </h3>
          </div>
          {primaryCode ? <Badge variant="success">已准备跳转</Badge> : <Badge variant="neutral">等待结果</Badge>}
        </div>

        <div className="mt-4 grid gap-3">
          {primaryCode ? (
            <div className="metric-tile rounded-[24px] p-4">
              <div className="text-sm font-semibold text-text-primary">{primaryName || primaryCode}</div>
              <div className="mt-2 text-xs leading-6 text-text-secondary">
                结果已经足够进入下一轮验证。推荐先看个股详情确认基本画像，再从技术分析和资金流核对交易结构。
              </div>
              <div className="mt-3 flex flex-wrap gap-2">
                {resultLinks.slice(0, 3).map((link) => (
                  <Link key={link.href} href={link.href} className={LINK_CHIP_CLS}>
                    {link.label}
                  </Link>
                ))}
              </div>
            </div>
          ) : (
            <div className="metric-tile rounded-[24px] p-4 text-sm text-text-secondary">
              运行一次搜索后，这里会展示优先结果与下一步跳转建议，便于把搜索页纳入完整工作流而不是停留在“只看表格”。
            </div>
          )}

          <div className="flex flex-wrap gap-2">
            {quickJumpLinks.map((link) => (
              <Link key={link.href} href={link.href} className={LINK_CHIP_CLS}>
                {link.label}
              </Link>
            ))}
          </div>
        </div>
      </div>
    </div>
  );

  return (
    <PageContainer className="app-theme-research">

      <section className="page-hero mb-4 p-4 sm:p-5">
        <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_clamp(280px,25vw,380px)]">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="info">搜索工作台</Badge>
              <Badge variant="neutral">{activeTabLabel}</Badge>
              <Badge variant={rows.length > 0 ? 'success' : 'warning'}>
                {rows.length > 0 ? `已返回 ${rows.length} 条结果` : '等待执行搜索'}
              </Badge>
            </div>
            <h1 className="mb-0 mt-3 text-[1.7rem] font-semibold tracking-[-0.03em] text-text-primary sm:text-[2rem]">
              {compactLayout ? '智能搜索' : '智能搜索工作台'}
            </h1>
            {!compactLayout ? (
              <p className="mb-0 mt-3 max-w-3xl text-sm leading-7 text-text-secondary sm:text-[15px]">
                这里把输入、结果、下一步跳转和工作区摘要放在同一条阅读线上，便于找到标的后直接进入研究或自选管理。
              </p>
            ) : null}
            <div className="mt-5 flex flex-wrap gap-2">
              <button type="button" onClick={submit} disabled={isPending} className={HERO_PRIMARY_BUTTON_CLS}>
                {isPending ? '搜索中...' : '执行当前搜索'}
              </button>
              {!compactLayout ? (
                <AskAiButton
                  stockCode={primaryCode || trimmedCode || undefined}
                  summary={heroSummary}
                  prompt="请帮我解释当前搜索结果，并给出下一步研究建议"
                  label="解读当前结果"
                />
              ) : null}
            </div>

            {compactLayout ? (
              <div className="mt-3 rounded-[20px] border border-white/45 bg-white/28 px-4 py-3 text-sm text-text-secondary">
                <span className="font-medium text-text-primary">{activeTabLabel}</span>
                <span className="mx-2 text-text-muted">/</span>
                <span>{activePrompt}</span>
              </div>
            ) : (
              <div className="mt-5 grid grid-cols-2 gap-3 xl:grid-cols-3">
                <div className="rounded-[24px] border border-white/45 bg-white/38 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.55)]">
                  <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">当前模式</div>
                  <div className="mt-3 text-lg font-semibold text-text-primary">{activeTabLabel}</div>
                  <div className="mt-1 text-xs text-text-secondary">根据任务目标切换检索方式</div>
                </div>
                <div className="rounded-[24px] border border-white/45 bg-white/30 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.48)]">
                  <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">当前输入</div>
                  <div className="mt-3 text-sm font-semibold leading-6 text-text-primary">{activePrompt}</div>
                  <div className="mt-1 text-xs text-text-secondary">优先聚焦一个明确线索</div>
                </div>
                <div className="col-span-2 rounded-[24px] border border-white/45 bg-white/26 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.42)] xl:col-span-1">
                  <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">优先结果</div>
                  <div className="mt-3 text-sm font-semibold leading-6 text-text-primary">
                    {primaryCode ? `${primaryName || primaryCode}` : '等待结果'}
                  </div>
                  <div className="mt-1 text-xs text-text-secondary">
                    {primaryCode ? '已可继续联动到其他分析页面' : '执行一次搜索后自动刷新'}
                  </div>
                </div>
              </div>
            )}
          </div>

          {!compactLayout ? (
          <div className="grid gap-3">
            <details className={PANEL_CLS} open={!compactLayout}>
              <summary className="cursor-pointer list-none text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">
                {compactLayout ? '展开使用建议与快速开始' : '使用建议'}
              </summary>
              <div className="mt-4 space-y-3">
                {heroNotes.map((note) => (
                  <div key={note} className={NOTE_CARD_CLS}>
                    {note}
                  </div>
                ))}
                <div className="flex flex-wrap gap-2">
                  {(tab === 'semantic' ? SEMANTIC_EXAMPLES : STOCK_EXAMPLES).map((example) => (
                    <button
                      key={example}
                      type="button"
                      onClick={() => {
                        if (tab === 'semantic') {
                          setQuery(example);
                          setQueryError(null);
                        } else {
                          setCode(example);
                        }
                      }}
                      className={CHIP_BUTTON_CLS}
                    >
                      {tab === 'semantic' ? example : `示例 ${example}`}
                    </button>
                  ))}
                </div>
                <div className="flex flex-wrap gap-2">
                  <button type="button" onClick={() => setTab('semantic')} className={HERO_SECONDARY_BUTTON_CLS}>
                    切到语义搜索
                  </button>
                  <button type="button" onClick={() => setTab('similar')} className={HERO_SECONDARY_BUTTON_CLS}>
                    切到相似股票
                  </button>
                </div>
                {compactLayout ? (
                  <div className={NOTE_CARD_CLS}>
                    优先结果：{primaryCode ? `${primaryName || primaryCode}` : '等待结果'}。
                    {primaryCode ? ' 结果已可联动到个股详情、技术面和研究页。' : ' 执行一次搜索后自动更新。'}
                  </div>
                ) : null}
              </div>
            </details>
          </div>
          ) : null}
        </div>
      </section>
      {!compactLayout ? (
        <WorkspaceToolbar pageKey="search" currentView={currentView} onApplyView={applyView} supportsPagePanels />
      ) : null}
      <WorkspaceSplitLayout
        pageKey="search"
        primary={searchPanel}
        secondary={workspacePanel}
        className="items-start"
        collapseSecondaryBelow={RESPONSIVE_BREAKPOINTS.dockOverlay}
        defaultMobileTab="primary"
        maxDefaultSections={1}
        mobileSummary={mobileSummary}
      />
    </PageContainer>
  );
}
