'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { AskAiButton } from '@/components/ask-ai-button';
import WorkspaceSplitLayout from '@/components/workspace-split-layout';
import WorkspaceToolbar from '@/components/workspace-toolbar';
import { PageContainer, TabBar, SectionCard, StockCodeInput, DataTable } from '@/components/ui';
import { ProgressBar } from '@/components/ui';
import { useApiQuery } from '@/hooks/use-api-query';
import { usePageActions } from '@/hooks/use-page-actions';
import { usePageContext } from '@/hooks/use-page-context';
import { useStockCode } from '@/hooks/use-stock-code';
import { LoadingState, ErrorState, EmptyState } from '@/components/status-state';
import { extractArray, fmtNum } from '@/lib/data-utils';
import { exportCSV } from '@/lib/export';
import { StockLink } from '@/components/stock-link';
import { WatchlistButton } from '@/components/watchlist-button';
import { selectActiveWorkspace, useWorkbenchStore } from '@/store/workbench-store';

const TABS = [
  { key: 'similar', label: '相似股票' },
  { key: 'semantic', label: '语义搜索' },
  { key: 'kline', label: 'K线搜索' },
] as const;

type Tab = (typeof TABS)[number]['key'];
const SEMANTIC_EXAMPLES = ['新能源龙头', '高股息银行', '白酒龙头', '半导体设备'];
const STOCK_EXAMPLES = ['600519', '000858', '300750'];
const starterActionCls = 'rounded-full border border-glass-border px-3 py-1 text-xs text-text-secondary no-underline';

export default function SearchPage() {
  const workbenchHydrated = useWorkbenchStore((state) => state.hydrated);
  const workbenchContext = useWorkbenchStore((state) => selectActiveWorkspace(state).context);
  const updateWorkbenchContext = useWorkbenchStore((state) => state.updateContext);
  const [tab, setTab] = useState<Tab>('similar');
  const { code, setCode, codeError, validate, trimmedCode } = useStockCode('600519');
  const [query, setQuery] = useState('');
  const [queryError, setQueryError] = useState<string | null>(null);
  const [queryPath, setQueryPath] = useState<string | null>(null);
  const { data, isFetching: isPending, error, refetch } = useApiQuery<unknown>(queryPath);

  const submit = useCallback(() => {
    let p: string;
    if (tab === 'semantic') {
      if (!query.trim()) { setQueryError('请输入搜索关键词'); return; }
      setQueryError(null);
      p = `/search/semantic?query=${encodeURIComponent(query.trim())}`;
    } else {
      if (!validate()) return;
      const endpoint = tab === 'similar' ? '/search/similar' : '/search/vector-kline';
      p = `${endpoint}?code=${encodeURIComponent(trimmedCode)}`;
    }
    if (p === queryPath) refetch(); else setQueryPath(p);
  }, [query, queryPath, refetch, tab, trimmedCode, validate]);

  const rows = useMemo(() => {
    const arr = extractArray(data, 'items', 'results', 'similar_stocks') as Record<string, unknown>[];
    return arr.map((r, i) => ({
      rank: i + 1,
      ...r,
      score: r.score ?? r.similarity,
    }));
  }, [data]);

  const similarColumns = useMemo(() => [
    { key: 'rank', label: '#', width: 50 },
    { key: 'code', label: '代码', width: 90 },
    { key: 'name', label: '名称', width: 100 },
    {
      key: 'similarity', label: '相似度',
      render: (v: unknown) => {
        const n = Number(v ?? 0);
        return <div className="flex items-center gap-2"><ProgressBar value={n * 100} max={100} /><span className="text-xs whitespace-nowrap">{fmtNum(n * 100, 1)}%</span></div>;
      },
    },
    { key: 'industry', label: '行业' },
  ], []);
  const klineColumns = useMemo(() => [
    { key: 'rank', label: '#', width: 50 },
    { key: 'code', label: '代码', width: 90 },
    { key: 'name', label: '名称', width: 100 },
    {
      key: 'score', label: '匹配度',
      render: (v: unknown) => {
        const n = Number(v ?? 0);
        return <div className="flex items-center gap-2"><ProgressBar value={n * 100} max={100} /><span className="text-xs whitespace-nowrap">{fmtNum(n * 100, 1)}%</span></div>;
      },
    },
    { key: 'industry', label: '行业' },
  ], []);

  const semanticColumns = useMemo(() => [
    { key: 'rank', label: '#', width: 50 },
    { key: 'code', label: '代码', width: 90 },
    { key: 'name', label: '名称', width: 100 },
    { key: 'score', label: '得分', align: 'right' as const, render: (v: unknown) => fmtNum(Number(v ?? 0), 2) },
    { key: 'industry', label: '行业' },
  ], []);

  const columns = tab === 'similar' ? similarColumns : tab === 'kline' ? klineColumns : semanticColumns;
  const primaryResult = (rows[0] ?? null) as Record<string, unknown> | null;
  const primaryCode = String(primaryResult?.code ?? '').trim();
  const primaryName = String(primaryResult?.name ?? primaryCode).trim();
  const resultLinks = primaryCode ? [
    { label: '个股详情', href: `/stock?code=${encodeURIComponent(primaryCode)}` },
    { label: '技术分析', href: `/technical?code=${encodeURIComponent(primaryCode)}` },
    { label: '资金流', href: `/fund-flow?code=${encodeURIComponent(primaryCode)}` },
    { label: '情绪分析', href: `/sentiment?code=${encodeURIComponent(primaryCode)}` },
    { label: '基本面', href: `/fundamental?code=${encodeURIComponent(primaryCode)}` },
  ] : [];

  usePageContext({
    pageKey: 'search',
    title: '智能搜索',
    summary: rows.length
      ? `当前为 ${tab} 模式，已返回 ${rows.length} 条结果，优先结果 ${primaryCode || '无'}。`
      : `智能搜索页，当前模式 ${tab === 'semantic' ? '语义搜索' : tab === 'similar' ? '相似股票' : 'K 线搜索'}。`,
    stockCode: tab === 'semantic' ? primaryCode || undefined : trimmedCode || primaryCode || undefined,
    tags: [tab, `${rows.length} 条结果`],
    suggestions: [
      '总结当前搜索结果里最值得继续跟进的股票',
      tab === 'semantic' ? '优化当前语义搜索词并给出更聚焦的版本' : '解释当前相似/形态搜索的命中逻辑',
      '把结果整理成下一步研究路线',
    ],
    raw: {
      tab,
      query,
      code: trimmedCode,
      resultCount: rows.length,
      primaryCode,
    },
  });

  const pageActions = useMemo(() => [
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
  ], [setCode, submit]);

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
    });
  }, [primaryCode, trimmedCode, updateWorkbenchContext, workbenchHydrated]);

  const currentView = useMemo<Record<string, unknown>>(
    () => ({ tab, query, code: trimmedCode, queryPath }),
    [query, queryPath, tab, trimmedCode],
  );

  const applyView = useCallback((snapshot: Record<string, unknown>) => {
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
  }, [setCode]);

  const searchPanel = (
    <>
      <TabBar tabs={TABS} active={tab} onChange={(key) => { setTab(key); setQueryPath(null); }} />
      <SectionCard tabAttached>
        {tab === 'semantic' ? (
          <div className="grid gap-2">
            <label htmlFor="semantic-search-query" className="grid gap-1 text-xs text-text-secondary">
              <span>搜索关键词</span>
              <div className="flex gap-2 items-center flex-wrap">
                <input
                  id="semantic-search-query"
                  value={query}
                  onChange={(e) => { setQuery(e.target.value); setQueryError(null); }}
                  placeholder="输入搜索词，如：新能源龙头"
                  className="w-[300px] px-2 py-1 border border-border rounded text-sm"
                />
                <button type="button" disabled={isPending} onClick={submit} className="px-3 py-1 border border-border rounded text-sm disabled:opacity-50">
                  搜索
                </button>
              </div>
            </label>
            <div className="flex gap-2 flex-wrap">
              {SEMANTIC_EXAMPLES.map((example) => (
                <button
                  key={example}
                  type="button"
                  onClick={() => {
                    setQuery(example);
                    setQueryError(null);
                  }}
                  className="px-3 py-1 rounded-full border border-border text-xs cursor-pointer hover:bg-surface-alt"
                >
                  {example}
                </button>
              ))}
            </div>
            {queryError ? <span className="text-error text-xs">{queryError}</span> : null}
          </div>
        ) : (
          <div className="grid gap-2">
            <div className="flex gap-2 items-center flex-wrap">
              <StockCodeInput id="search-stock-code" label="股票代码" value={code} onChange={setCode} error={codeError} placeholder="如 600519" />
              <button type="button" disabled={isPending} onClick={submit} className="px-3 py-1 border border-border rounded text-sm disabled:opacity-50">
                {tab === 'similar' ? '查找相似' : 'K线搜索'}
              </button>
            </div>
            <div className="flex gap-2 flex-wrap">
              {STOCK_EXAMPLES.map((example) => (
                <button
                  key={example}
                  type="button"
                  onClick={() => setCode(example)}
                  className="px-3 py-1 rounded-full border border-border text-xs cursor-pointer hover:bg-surface-alt"
                >
                  示例 {example}
                </button>
              ))}
            </div>
          </div>
        )}
        {isPending ? <LoadingState text="搜索中..." /> : null}
        {error ? <ErrorState text={error} hint="请检查输入后重试" /> : null}
        {!isPending && !data && !error ? (
          <EmptyState
            text={tab === 'semantic' ? '输入主题词后开始语义搜索' : '输入股票代码后开始相似/形态搜索'}
            hint={tab === 'semantic'
              ? '你可以先用“新能源龙头”“高股息银行”这类主题词快速找标的，再继续跳到个股详情、技术面或基本面页面。'
              : '推荐先从一只熟悉的股票开始，搜索结果出来后再进入个股详情、资金流、技术分析等下一步动作。'}
            action={
              <>
                {tab === 'semantic' ? (
                  SEMANTIC_EXAMPLES.slice(0, 2).map((example) => (
                    <button
                      key={example}
                      type="button"
                      onClick={() => {
                        setQuery(example);
                        setQueryError(null);
                      }}
                      className={starterActionCls}
                    >
                      试试“{example}”
                    </button>
                  ))
                ) : (
                  STOCK_EXAMPLES.slice(0, 2).map((example) => (
                    <button key={example} type="button" onClick={() => setCode(example)} className={starterActionCls}>
                      示例 {example}
                    </button>
                  ))
                )}
                <Link href="/watchlist" className={starterActionCls}>查看自选股</Link>
              </>
            }
          />
        ) : null}
        {rows.length ? (
          <div className="mt-4 space-y-4">
            {primaryCode ? (
              <div className="rounded-xl border border-border bg-surface-alt/50 p-3">
                <div className="flex items-start justify-between gap-3 flex-wrap">
                  <div>
                    <div className="text-sm font-medium text-text-primary">搜索结果下一步</div>
                    <p className="mt-1 mb-0 text-xs text-text-secondary">
                      当前优先结果为 {primaryName || primaryCode}，建议先确认个股详情，再结合技术面、资金流与情绪页做交叉验证。
                    </p>
                  </div>
                  <div className="flex items-center gap-2 flex-wrap">
                    <StockLink code={primaryCode} name={primaryName || primaryCode} />
                    <WatchlistButton code={primaryCode} name={primaryName || primaryCode} />
                  </div>
                </div>
                <div className="mt-3 flex gap-2 flex-wrap">
                  {resultLinks.map((link) => (
                    <Link key={link.href} href={link.href} className={starterActionCls}>
                      {link.label}
                    </Link>
                  ))}
                </div>
              </div>
            ) : null}
            <DataTable rows={rows} columns={columns} maxHeight={500} onExport={() => exportCSV(rows, `search-${tab}`)} />
          </div>
        ) : null}
        {!isPending && !!data && !error && rows.length === 0 ? (
          <EmptyState
            text="本次搜索没有匹配结果"
            hint={tab === 'semantic'
              ? '可以换一个更通用的主题词，或改从具体股票出发再去技术/基本面页继续查。'
              : '可以切换示例股票、换搜索模式，或直接去行情、自选和研究页重新选择标的。'}
            action={
              <>
                <Link href="/market" className={starterActionCls}>去行情看板</Link>
                <Link href="/watchlist" className={starterActionCls}>回到自选</Link>
                <Link href="/research" className={starterActionCls}>继续做研究</Link>
              </>
            }
          />
        ) : null}
      </SectionCard>
    </>
  );

  const workspacePanel = (
    <SectionCard className="p-4">
      <div className="text-sm font-medium text-text-primary">搜索工作区摘要</div>
      <div className="mt-3 grid gap-3">
        <div className="rounded-xl border border-glass-border bg-surface-alt/40 p-3 text-xs text-text-secondary">
          <div>模式：{tab}</div>
          <div className="mt-1">结果数：{rows.length}</div>
          <div className="mt-1">当前代码：{trimmedCode || '-'}</div>
          <div className="mt-1">优先结果：{primaryCode || '-'}</div>
        </div>
        {primaryCode ? (
          <div className="rounded-xl border border-glass-border bg-surface p-3">
            <div className="text-xs font-medium text-text-primary">优先结果</div>
            <div className="mt-2 text-sm text-text-primary">{primaryName || primaryCode}</div>
            <div className="mt-2 flex flex-wrap gap-2">
              {resultLinks.slice(0, 3).map((link) => (
                <Link key={link.href} href={link.href} className={starterActionCls}>
                  {link.label}
                </Link>
              ))}
            </div>
          </div>
        ) : (
          <div className="rounded-xl border border-dashed border-glass-border p-3 text-xs text-text-secondary">
            运行一次搜索后，这里会展示优先结果与下一步跳转。
          </div>
        )}
      </div>
    </SectionCard>
  );

  return (
    <PageContainer>
      <div className="mb-3 flex items-center justify-between gap-3">
        <h1 className="mb-0">智能搜索</h1>
        <AskAiButton
          stockCode={primaryCode || trimmedCode || undefined}
          summary={rows.length ? `当前模式 ${tab}，已返回 ${rows.length} 条结果` : `当前模式 ${tab}`}
          prompt="请帮我解释当前搜索结果，并给出下一步研究建议"
        />
      </div>
      <WorkspaceToolbar pageKey="search" currentView={currentView} onApplyView={applyView} supportsPagePanels />
      <WorkspaceSplitLayout pageKey="search" primary={searchPanel} secondary={workspacePanel} />
    </PageContainer>
  );
}
