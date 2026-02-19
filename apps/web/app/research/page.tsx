'use client';

import { FormEvent, ReactNode, useMemo, useState } from 'react';
import { PageContainer, SectionCard, TabBar, DataTable, StockCodeInput } from '@/components/ui';
import { useApiMutation } from '@/hooks/use-api-mutation';
import { useStockCode } from '@/hooks/use-stock-code';
import { ErrorState } from '@/components/status-state';
import { extractArray } from '@/lib/data-utils';
import { exportCSV } from '@/lib/export';
import { fmt, cacheText, type CacheMeta } from '@/lib/api';

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
  const [updatedAt, setUpdatedAt] = useState('');

  const listMut = useApiMutation<ResearchData>();
  const [newsTab, setNewsTab] = useState<NewsTab>('stock-news');
  const newsMut = useApiMutation<unknown>();

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
    try {
      await listMut.triggerAsync(`/research/list?${params.toString()}`);
      setUpdatedAt(new Date().toLocaleString('zh-CN'));
    } catch { /* error handled by mutation */ }
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
    newsMut.trigger(paths[type] ?? `/research/reports?code=${encodeURIComponent(c)}`);
  }

  const reports = useMemo(() => listMut.data?.reports ?? [], [listMut.data]);
  const notices = useMemo(() => listMut.data?.notices ?? [], [listMut.data]);
  const freshness = listMut.data?.meta?.fetchedAt ?? '';
  const cache = listMut.data?.meta?.cache;
  const loading = listMut.isPending;
  const error = formError || codeError || listMut.error;

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
        更新：{updatedAt || '-'} ｜ 抓取：{freshness ? new Date(freshness).toLocaleString('zh-CN') : '-'} ｜ 缓存：{cacheText(cache)}
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
          <button type="button" disabled={newsMut.isPending} onClick={() => fetchNews(newsTab)}>
            {newsMut.isPending ? '加载中...' : '查询'}
          </button>
          {newsMut.error ? <ErrorState text={newsMut.error} /> : null}
          {newsMut.data != null ? (() => {
            const rows = extractArray(newsMut.data);
            return rows.length
              ? <DataTable rows={rows} maxHeight={400} onExport={() => exportCSV(rows, `research-${newsTab}`)} />
              : <pre className="mt-2 text-xs bg-surface-alt p-2 rounded overflow-auto max-h-[300px]">{JSON.stringify(newsMut.data, null, 2)}</pre>;
          })() : null}
        </SectionCard>
      </section>
    </PageContainer>
  );
}
