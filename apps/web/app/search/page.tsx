'use client';

import { useMemo, useState } from 'react';
import { PageContainer, TabBar, SectionCard, StockCodeInput, DataTable } from '@/components/ui';
import { ProgressBar } from '@/components/ui';
import { useApiQuery } from '@/hooks/use-api-query';
import { useStockCode } from '@/hooks/use-stock-code';
import { LoadingState, ErrorState, EmptyState } from '@/components/status-state';
import { extractArray, fmtNum } from '@/lib/data-utils';
import { exportCSV } from '@/lib/export';

const TABS = [
  { key: 'similar', label: '相似股票' },
  { key: 'semantic', label: '语义搜索' },
  { key: 'kline', label: 'K线搜索' },
] as const;

type Tab = (typeof TABS)[number]['key'];

export default function SearchPage() {
  const [tab, setTab] = useState<Tab>('similar');
  const { code, setCode, codeError, validate, trimmedCode } = useStockCode('600519');
  const [query, setQuery] = useState('');
  const [queryError, setQueryError] = useState<string | null>(null);
  const [queryPath, setQueryPath] = useState<string | null>(null);
  const { data, isFetching: isPending, error, refetch } = useApiQuery<unknown>(queryPath);

  function submit() {
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
  }

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

  return (
    <PageContainer>
      <h1>智能搜索</h1>
      <TabBar tabs={TABS} active={tab} onChange={(key) => { setTab(key); setQueryPath(null); }} />
      <SectionCard tabAttached>
        {tab === 'semantic' ? (
          <div className="flex gap-2 items-center">
            <input
              value={query}
              onChange={(e) => { setQuery(e.target.value); setQueryError(null); }}
              placeholder="输入搜索词，如：新能源龙头"
              className="w-[300px] px-2 py-1 border border-border rounded text-sm"
            />
            {queryError ? <span className="text-error text-xs">{queryError}</span> : null}
            <button type="button" disabled={isPending} onClick={submit} className="px-3 py-1 border border-border rounded text-sm disabled:opacity-50">
              搜索
            </button>
          </div>
        ) : (
          <div className="flex gap-2 items-center">
            <StockCodeInput value={code} onChange={setCode} error={codeError} />
            <button type="button" disabled={isPending} onClick={submit} className="px-3 py-1 border border-border rounded text-sm disabled:opacity-50">
              {tab === 'similar' ? '查找相似' : 'K线搜索'}
            </button>
          </div>
        )}
        {isPending ? <LoadingState text="搜索中..." /> : null}
        {error ? <ErrorState text={error} hint="请检查输入后重试" /> : null}
        {!isPending && !data && !error ? <EmptyState text="输入条件后点击按钮搜索" /> : null}
        {rows.length ? <DataTable rows={rows} columns={columns} maxHeight={500} onExport={() => exportCSV(rows, `search-${tab}`)} /> : null}
        {!isPending && !!data && !error && rows.length === 0 ? <EmptyState text="本次搜索没有匹配结果" /> : null}
      </SectionCard>
    </PageContainer>
  );
}
