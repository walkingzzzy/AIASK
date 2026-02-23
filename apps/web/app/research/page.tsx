'use client';

import { FormEvent, ReactNode, useMemo, useState } from 'react';
import { PageContainer, SectionCard, TabBar, DataTable, StockCodeInput, KpiCard, KpiGrid } from '@/components/ui';
import { BarChart } from '@/components/charts';
import { useApiQuery } from '@/hooks/use-api-query';
import { useStockCode } from '@/hooks/use-stock-code';
import { ErrorState } from '@/components/status-state';
import { extractArray, fmtNum, fmtPct, fmtAmount } from '@/lib/data-utils';
import { exportCSV } from '@/lib/export';
import { fmt, cacheText, type CacheMeta } from '@/lib/api';
import { StockLink } from '@/components/stock-link';

type ResearchItem = { title: string; date: string; source: string; summary: string };
type ResearchData = {
  reports?: ResearchItem[];
  notices?: ResearchItem[];
  query?: { startDate: string; endDate: string; keyword: string; limit: number };
  sourceTools?: Record<string, unknown>;
  meta?: CacheMeta;
};
type Range = '7' | '30' | '90' | 'custom';

const NEWS_TABS = [
  { key: 'stock-news', label: '个股新闻' },
  { key: 'market-news', label: '市场新闻' },
  { key: 'analyst', label: '分析师排名' },
  { key: 'forecast', label: '盈利预测' },
  { key: 'search-research', label: '研报搜索' },
  { key: 'reports', label: '研报列表' },
  { key: 'macro', label: '宏观数据' },
] as const;
type NewsTab = typeof NEWS_TABS[number]['key'];

function highlight(text: string, kw: string): ReactNode {
  if (!kw.trim()) return text || '-';
  const esc = kw.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const reg = new RegExp(`(${esc})`, 'ig');
  const parts = (text || '').split(reg);
  return parts.map((p, i) =>
    reg.test(p) ? <mark key={`${p}-${i}`}>{p}</mark> : <span key={`${p}-${i}`}>{p}</span>,
  );
}

export default function ResearchPage() {
  const { code, setCode, codeError, validate, trimmedCode } = useStockCode('600519');
  const [range, setRange] = useState<Range>('30');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [keyword, setKeyword] = useState('');
  const [formError, setFormError] = useState<string | null>(null);
  const [listPath, setListPath] = useState<string | null>(null);

  const listQ = useApiQuery<ResearchData>(listPath);
  const [newsTab, setNewsTab] = useState<NewsTab>('stock-news');
  const [newsPath, setNewsPath] = useState<string | null>(null);
  const newsQ = useApiQuery<unknown>(newsPath);

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!validate()) return;
    if (range === 'custom' && (!startDate || !endDate)) {
      setFormError('自定义时间范围需要开始与结束日期');
      return;
    }
    setFormError(null);
    const params = new URLSearchParams({ code: trimmedCode, limit: '20', keyword: keyword.trim() });
    if (range === 'custom') {
      params.set('startDate', startDate);
      params.set('endDate', endDate);
    } else {
      params.set('days', range);
    }
    const newPath = `/research/list?${params.toString()}`;
    if (newPath === listPath) listQ.refetch();
    else setListPath(newPath);
  }

  function fetchNews(type: string) {
    if (['stock-news', 'forecast'].includes(type) && !validate()) return;
    setFormError(null);
    const c = trimmedCode;
    const paths: Record<string, string> = {
      'stock-news': `/research/stock-news?code=${encodeURIComponent(c)}`,
      'market-news': '/research/market-news',
      'analyst': '/research/analyst-ranking',
      'forecast': `/research/profit-forecast?code=${encodeURIComponent(c)}`,
      'search-research': `/research/search?code=${encodeURIComponent(c)}`,
      'macro': '/research/macro',
      'reports': `/research/reports?code=${encodeURIComponent(c)}`,
    };
    const newPath = paths[type] ?? `/research/reports?code=${encodeURIComponent(c)}`;
    if (newPath === newsPath) newsQ.refetch();
    else setNewsPath(newPath);
  }

  const reports = useMemo(() => listQ.data?.reports ?? [], [listQ.data]);
  const notices = useMemo(() => listQ.data?.notices ?? [], [listQ.data]);
  const freshness = listQ.data?.meta?.fetchedAt ?? '';
  const cache = listQ.data?.meta?.cache;
  const loading = listQ.isFetching;
  const error = formError || codeError || listQ.error;

  return (
    <PageContainer narrow>
      <h1>研报公告</h1>
      <form onSubmit={onSubmit} className="flex gap-2.5 flex-wrap items-center">
        <StockCodeInput value={code} onChange={setCode} error={codeError} placeholder="如 600519" />
        <select value={range} onChange={(e) => setRange(e.target.value as Range)}>
          <option value="7">近1周</option>
          <option value="30">近1月</option>
          <option value="90">近3月</option>
          <option value="custom">自定义</option>
        </select>
        {range === 'custom' ? (
          <>
            <input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
            <input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} />
          </>
        ) : null}
        <input value={keyword} onChange={(e) => setKeyword(e.target.value)} placeholder="关键词" />
        <button type="submit" disabled={loading}>{loading ? '查询中...' : '查询'}</button>
      </form>
      {error ? <ErrorState text={error} /> : null}
      <div className="mt-2 text-text-secondary">
        更新：{listQ.dataUpdatedAt ? new Date(listQ.dataUpdatedAt).toLocaleString('zh-CN') : '-'} ｜ 抓取：{freshness ? new Date(freshness).toLocaleString('zh-CN') : '-'} ｜ 缓存：{cacheText(cache)}
      </div>

      <section className="mt-3.5 grid grid-cols-2 gap-3">
        <SectionCard>
          <h3 className="mt-0">研报（{reports.length}）</h3>
          <div className="max-h-[420px] overflow-auto">
            {reports.map((it, idx) => (
              <div key={`r-${idx}`} className="py-2 border-b border-dashed border-border/50">
                <div className="font-semibold">{highlight(it.title, keyword)}</div>
                <div className="text-text-secondary text-xs">{fmt(it.date)} ｜ {fmt(it.source)}</div>
                <div>{highlight(it.summary || '-', keyword)}</div>
              </div>
            ))}
            {!reports.length ? <div>无匹配研报</div> : null}
          </div>
        </SectionCard>
        <SectionCard>
          <h3 className="mt-0">公告（{notices.length}）</h3>
          <div className="max-h-[420px] overflow-auto">
            {notices.map((it, idx) => (
              <div key={`n-${idx}`} className="py-2 border-b border-dashed border-border/50">
                <div className="font-semibold">{highlight(it.title, keyword)}</div>
                <div className="text-text-secondary text-xs">{fmt(it.date)} ｜ {fmt(it.source)}</div>
                <div>{highlight(it.summary || '-', keyword)}</div>
              </div>
            ))}
            {!notices.length ? <div>无匹配公告</div> : null}
          </div>
        </SectionCard>
      </section>

      <section className="mt-5">
        <h2>资讯与分析</h2>
        <TabBar tabs={NEWS_TABS} active={newsTab} onChange={setNewsTab} />
        <SectionCard tabAttached>
          <button type="button" disabled={newsQ.isFetching} onClick={() => fetchNews(newsTab)}>
            {newsQ.isFetching ? '加载中...' : '查询'}
          </button>
          {newsQ.error ? <ErrorState text={newsQ.error} /> : null}
          {newsQ.data != null ? (() => {
            const rows = extractArray(newsQ.data, 'items', 'analysts', 'reports', 'data');
            const columnMap: Record<string, Array<{ key: string; label: string; align?: 'left' | 'right' | 'center'; render?: (v: unknown) => ReactNode }>> = {
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
              'analyst': [
                { key: 'rank', label: '排名', align: 'right' as const },
                { key: 'name', label: '分析师' },
                { key: 'institution', label: '机构' },
                { key: 'industry', label: '行业' },
                { key: 'winRate', label: '胜率', align: 'right' as const, render: (v: unknown) => fmtPct(v as number) },
              ],
              'forecast': [
                { key: 'date', label: '日期' },
                { key: 'institution', label: '机构' },
                { key: 'rating', label: '评级' },
                { key: 'epsForecast', label: 'EPS预测', align: 'right' as const, render: (v: unknown) => fmtNum(v as number, 2) },
                { key: 'netprofitForecast', label: '净利润预测', align: 'right' as const, render: (v: unknown) => fmtAmount(v as number) },
              ],
              'search-research': [
                { key: 'title', label: '标题' },
                { key: 'institution', label: '机构' },
                { key: 'rating', label: '评级' },
                { key: 'date', label: '日期' },
                { key: 'stockCode', label: '代码', render: (v: unknown) => <StockLink code={String(v)} /> },
              ],
              'reports': [
                { key: 'title', label: '标题' },
                { key: 'institution', label: '机构' },
                { key: 'author', label: '作者' },
                { key: 'rating', label: '评级' },
                { key: 'date', label: '日期' },
              ],
              'macro': [],
            };
            const cols = columnMap[newsTab];
            // Analyst bar chart: top 10 by win rate
            const analystChart = newsTab === 'analyst' && rows.length > 0
              ? rows.slice(0, 10).map((r: Record<string, unknown>) => ({
                  label: String(r.name ?? '').slice(0, 6),
                  value: Number(r.winRate ?? r.win_rate ?? 0) * 100,
                }))
              : null;
            // Forecast summary KPIs
            const forecastSummary = newsTab === 'forecast' && rows.length > 0
              ? {
                  avgEps: rows.reduce((s: number, r: Record<string, unknown>) => s + Number(r.epsForecast ?? r.eps_forecast ?? 0), 0) / rows.length,
                  count: rows.length,
                  ratings: rows.reduce((m: Record<string, number>, r: Record<string, unknown>) => {
                    const rt = String(r.rating ?? '未知');
                    m[rt] = (m[rt] || 0) + 1;
                    return m;
                  }, {} as Record<string, number>),
                }
              : null;
            return (
              <>
                {analystChart && analystChart.length > 0 && (
                  <div className="mb-3">
                    <h4 className="text-sm font-medium mb-1">分析师胜率 TOP10</h4>
                    <BarChart items={analystChart} height={200} yAxisName="胜率 %" horizontal />
                  </div>
                )}
                {forecastSummary && (
                  <KpiGrid cols={3} className="mb-3">
                    <KpiCard title="预测机构数" value={forecastSummary.count} />
                    <KpiCard title="平均EPS预测" value={fmtNum(forecastSummary.avgEps, 2)} />
                    <KpiCard title="评级分布" value={Object.entries(forecastSummary.ratings).map(([k, v]) => `${k}:${v}`).join(' ')} />
                  </KpiGrid>
                )}
                {rows.length
                  ? <DataTable rows={rows} columns={cols?.length ? cols : undefined} maxHeight={400} onExport={() => exportCSV(rows, `research-${newsTab}`)} />
                  : <p className="text-text-secondary text-sm mt-2">暂无数据</p>}
              </>
            );
          })() : null}
        </SectionCard>
      </section>
    </PageContainer>
  );
}
