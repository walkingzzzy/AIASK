'use client';

import { FormEvent, ReactNode, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { PageContainer, SectionCard, TabBar, DataTable, StockCodeInput, KpiCard, KpiGrid } from '@/components/ui';
import { BarChart } from '@/components/charts';
import { useApiQuery } from '@/hooks/use-api-query';
import { useStockCode } from '@/hooks/use-stock-code';
import { EmptyState, ErrorState } from '@/components/status-state';
import { extractArray, fmtNum, fmtPct, fmtAmount } from '@/lib/data-utils';
import { exportCSV } from '@/lib/export';
import { fmt, cacheText, type CacheMeta } from '@/lib/api';
import { StockLink } from '@/components/stock-link';
import { WatchlistButton } from '@/components/watchlist-button';
import { useHydrated } from '@/hooks/use-hydrated';

type ResearchItem = { title: string; date: string; source: string; summary: string };
type ResearchData = {
  reports?: ResearchItem[];
  notices?: ResearchItem[];
  query?: { startDate: string; endDate: string; keyword: string; limit: number };
  sourceTools?: Record<string, unknown>;
  meta?: CacheMeta;
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
  return parts.map((p, i) =>
    reg.test(p) ? <mark key={`${p}-${i}`}>{p}</mark> : <span key={`${p}-${i}`}>{p}</span>,
  );
}

export default function ResearchPage() {
  const mounted = useHydrated();
  const savedView = useMemo(() => readSavedResearchView(), []);
  const savedCode = typeof savedView?.code === 'string' && savedView.code.trim() ? savedView.code.trim() : '600519';
  const { code, setCode, codeError, validate, trimmedCode, resolvedCode } = useStockCode(savedCode);
  const [range, setRange] = useState<Range>(() => (isValidRange(savedView?.range) ? savedView.range : '30'));
  const [startDate, setStartDate] = useState(() => (typeof savedView?.startDate === 'string' ? savedView.startDate : ''));
  const [endDate, setEndDate] = useState(() => (typeof savedView?.endDate === 'string' ? savedView.endDate : ''));
  const [keyword, setKeyword] = useState(() => (typeof savedView?.keyword === 'string' ? savedView.keyword : ''));
  const [formError, setFormError] = useState<string | null>(null);
  const autoListPath = resolvedCode ? `/research/list?code=${encodeURIComponent(resolvedCode)}&days=30&limit=20&keyword=` : null;
  const [listPath, setListPath] = useState<string | null>(() =>
    typeof savedView?.listPath === 'string' || savedView?.listPath === null ? savedView.listPath ?? null : null,
  );
  const effectiveListPath = listPath ?? autoListPath;

  const listQ = useApiQuery<ResearchData>(effectiveListPath);
  const [newsTab, setNewsTab] = useState<NewsTab>(() => (isValidNewsTab(savedView?.newsTab) ? savedView.newsTab : 'stock-news'));
  const [newsPath, setNewsPath] = useState<string | null>(null);
  const newsQ = useApiQuery<unknown>(newsPath);

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

  function submitListQuery(nextRange = range, nextStartDate = startDate, nextEndDate = endDate, nextKeyword = keyword) {
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
  }

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    submitListQuery();
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
  const showPrimaryEmptyState = !loading && !error && reports.length === 0 && notices.length === 0;

  return (
    <PageContainer narrow>
      <h1>研报公告</h1>
      {resolvedCode && (
        <div className="flex items-center gap-2 mb-2">
          <StockLink code={resolvedCode} name={resolvedCode} />
          <WatchlistButton code={resolvedCode} name="" />
        </div>
      )}
      <SectionCard className="p-4 mb-3">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <h3 className="mt-0 mb-1 text-base">常用入口</h3>
            <p className="m-0 text-sm text-text-secondary">如果默认结果较少，优先扩大时间范围或切到市场新闻，不用先手动重填一遍表单。</p>
          </div>
          <div className="flex gap-2 flex-wrap">
            <button
              type="button"
              onClick={() => {
                setRange('90');
                submitListQuery('90', startDate, endDate, keyword);
              }}
              className="px-3 py-1.5 rounded border border-primary text-primary text-sm cursor-pointer hover:bg-primary/5"
            >
              查看近 90 天
            </button>
            <button
              type="button"
              onClick={() => {
                setRange('7');
                submitListQuery('7', startDate, endDate, keyword);
              }}
              className="px-3 py-1.5 rounded border border-border text-sm cursor-pointer hover:bg-surface-alt"
            >
              查看近 7 天
            </button>
            <button
              type="button"
              onClick={() => {
                setNewsTab('market-news');
                fetchNews('market-news');
              }}
              className="px-3 py-1.5 rounded border border-border text-sm cursor-pointer hover:bg-surface-alt"
            >
              查看市场新闻
            </button>
          </div>
        </div>
      </SectionCard>
      <form onSubmit={onSubmit} className="grid gap-3 md:grid-cols-2">
        <StockCodeInput id="research-stock-code" label="股票代码" value={code} onChange={setCode} error={codeError} placeholder="如 600519" />
        <label className="grid gap-1 text-xs text-text-secondary">
          <span>时间范围</span>
          <select value={range} onChange={(e) => setRange(e.target.value as Range)}>
            <option value="7">近1周</option>
            <option value="30">近1月</option>
            <option value="90">近3月</option>
            <option value="custom">自定义</option>
          </select>
        </label>
        {range === 'custom' ? (
          <>
            <label className="grid gap-1 text-xs text-text-secondary">
              <span>开始日期</span>
              <input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
            </label>
            <label className="grid gap-1 text-xs text-text-secondary">
              <span>结束日期</span>
              <input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} />
            </label>
          </>
        ) : null}
        <label className="grid gap-1 text-xs text-text-secondary">
          <span>关键词</span>
          <input value={keyword} onChange={(e) => setKeyword(e.target.value)} placeholder="可输入行业、机构或主题词" />
        </label>
        <div className="flex items-end">
          <button type="submit" disabled={loading}>{loading ? '查询中...' : '查询'}</button>
        </div>
      </form>
      {error ? <ErrorState text={error} /> : null}
      <div className="mt-2 text-text-secondary">
        更新：{mounted && listQ.dataUpdatedAt ? new Date(listQ.dataUpdatedAt).toLocaleString('zh-CN') : '-'} ｜ 抓取：{mounted && freshness ? new Date(freshness).toLocaleString('zh-CN') : '-'} ｜ 缓存：{cacheText(cache)}
      </div>

      <section className="mt-3.5 grid grid-cols-1 xl:grid-cols-2 gap-3">
        {showPrimaryEmptyState ? (
          <SectionCard className="xl:col-span-2 p-5">
            <h3 className="mt-0">当前条件下暂无结果</h3>
            <p className="text-sm text-text-secondary mb-3">近 30 天未命中时，可以直接扩大时间范围或切换到市场新闻继续查看，不用手动重新组织查询。</p>
            <div className="flex gap-2 flex-wrap">
              <button
                type="button"
                onClick={() => {
                  setRange('90');
                  submitListQuery('90', startDate, endDate, keyword);
                }}
                className="px-3 py-1.5 rounded border border-primary text-primary text-sm cursor-pointer hover:bg-primary/5"
              >
                查看近 90 天
              </button>
              <button
                type="button"
                onClick={() => {
                  setNewsTab('market-news');
                  fetchNews('market-news');
                }}
                className="px-3 py-1.5 rounded border border-border text-sm cursor-pointer hover:bg-surface-alt"
              >
                查看市场新闻
              </button>
              <Link href="/market" className="px-3 py-1.5 rounded border border-border text-sm no-underline text-inherit hover:bg-surface-alt">
                回行情页换标的
              </Link>
            </div>
          </SectionCard>
        ) : (
          <>
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
                          className="px-3 py-1 rounded-full border border-primary text-xs text-primary cursor-pointer"
                        >
                          扩大到近 90 天
                        </button>
                        <button
                          type="button"
                          onClick={() => {
                            setNewsTab('search-research');
                            fetchNews('search-research');
                          }}
                          className="px-3 py-1 rounded-full border border-border text-xs text-text-secondary cursor-pointer"
                        >
                          去研报搜索
                        </button>
                      </>
                    }
                  />
                ) : null}
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
                          className="px-3 py-1 rounded-full border border-primary text-xs text-primary cursor-pointer"
                        >
                          去看市场新闻
                        </button>
                        <Link href="/alerts" className="px-3 py-1 rounded-full border border-border text-xs text-text-secondary no-underline">
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
                  : (
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
                              className="px-3 py-1 rounded-full border border-primary text-xs text-primary cursor-pointer"
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
                              className="px-3 py-1 rounded-full border border-border text-xs text-text-secondary cursor-pointer"
                            >
                              看研报列表
                            </button>
                          ) : null}
                          <Link href="/market" className="px-3 py-1 rounded-full border border-border text-xs text-text-secondary no-underline">
                            回行情页换标的
                          </Link>
                        </>
                      }
                    />
                  )}
              </>
            );
          })() : null}
        </SectionCard>
      </section>
    </PageContainer>
  );
}
