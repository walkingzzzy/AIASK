'use client';

import { FormEvent, useEffect, useMemo, useRef, useState } from 'react';
import { PageContainer, SectionCard, TabBar, DataTable, StockCodeInput, KpiCard, KpiGrid } from '@/components/ui';
import { LineChart } from '@/components/charts';
import { useApiQuery } from '@/hooks/use-api-query';
import { useApiMutation } from '@/hooks/use-api-mutation';
import { useStockCode } from '@/hooks/use-stock-code';
import { ErrorState } from '@/components/status-state';
import { StockLink } from '@/components/stock-link';
import { WatchlistButton } from '@/components/watchlist-button';
import { cacheText, type CacheMeta } from '@/lib/api';

import { extractArray, extractObject, fmtNum, fmtAmount, fmtPct } from '@/lib/data-utils';
import { exportCSV } from '@/lib/export';
import { ensureRecord, ensureRecordOrArray } from '@/lib/query-parse';

type OverviewData = { code?: string; financials?: { roe: number | null; netProfit: number | null; revenue: number | null; debtRatio: number | null }; valuation?: { pe: number | null; pb: number | null; ps: number | null; marketCap: number | null }; sourceTools?: Record<string, unknown>; meta?: CacheMeta };
type HistoryPoint = { date: string; pe: number | null; pb: number | null; ps: number | null; close: number | null };
type HistoryData = { code?: string; days?: number; points?: HistoryPoint[]; sourceTool?: string; meta?: CacheMeta };
type ExtraTab = 'info' | 'snapshot' | 'f10' | 'history';

const FIELD_LABELS: Record<string, string> = {
  eps: '每股收益', roe: '净资产收益率(%)', net_profit: '归母净利润(亿)',
  revenue: '营业收入(亿)', debt_ratio: '资产负债率(%)', operating_profit_rate: '营业利润率(%)',
  bvps: '每股净资产', net_profit_margin: '销售净利率(%)', operating_profit: '营业利润(亿)',
  // Snapshot fallback fields
  netProfit: '归母净利润', grossProfitMargin: '毛利率(%)', netProfitMargin: '净利率(%)',
  roa: '总资产收益率(%)', debtRatio: '资产负债率(%)', currentRatio: '流动比率',
  reportDate: '报告期', code: '代码', name: '名称', industry: '行业', listDate: '上市日期',
  totalShares: '总股本', floatShares: '流通股本', totalMarketCap: '总市值', floatMarketCap: '流通市值',
};

const extraTabs: readonly { key: ExtraTab; label: string }[] = [
  { key: 'info', label: '基本信息' },
  { key: 'snapshot', label: '财务快照' },
  { key: 'f10', label: 'F10资料' },
  { key: 'history', label: '财务历史' },
];

/** Recursively flatten nested object for display */
function flattenObj(obj: Record<string, unknown>): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(obj)) {
    if (v && typeof v === 'object' && !Array.isArray(v)) {
      Object.assign(out, flattenObj(v as Record<string, unknown>));
    } else if (!Array.isArray(v)) {
      out[k] = v;
    }
  }
  return out;
}

export default function FundamentalPage() {
  const { code, setCode, codeError, validate, trimmedCode, resolvedCode } = useStockCode('600519');
  const [days, setDays] = useState(90);
  const [extraTab, setExtraTab] = useState<ExtraTab>('info');
  const [submittedCode, setSubmittedCode] = useState<string | null>(null);
  const [submittedDays, setSubmittedDays] = useState<number>(90);

  // 自动查询：URL 或 Store 携带了有效代码时自动触发
  const autoFetched = useRef(false);
  useEffect(() => {
    if (!autoFetched.current && resolvedCode) {
      autoFetched.current = true;
      setSubmittedCode(resolvedCode);
    }
  }, [resolvedCode]);

  const overviewQ = useApiQuery<OverviewData>(
    submittedCode ? `/fundamental/overview?code=${submittedCode}` : null,
    { parse: (raw) => ensureRecord(raw, '基本面概览') as OverviewData },
  );
  const historyQ = useApiQuery<HistoryData>(
    submittedCode ? `/fundamental/history?code=${submittedCode}&days=${submittedDays}` : null,
    { parse: (raw) => ensureRecord(raw, '基本面历史') as HistoryData },
  );
  const [extraPath, setExtraPath] = useState<string | null>(null);
  const extraQ = useApiQuery<unknown>(extraPath, {
    parse: (raw) => ensureRecordOrArray(raw, '基本面扩展数据'),
  });
  const historyMut = useApiMutation<unknown>({
    parse: (raw) => ensureRecordOrArray(raw, '财务历史'),
  });

  const loading = overviewQ.isFetching || historyQ.isFetching;
  const error = overviewQ.error || historyQ.error;

  // Auto-load extra tab data when switching tabs
  useEffect(() => {
    if (submittedCode) fetchExtra(extraTab, submittedCode);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [extraTab, submittedCode]);

  function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!validate()) return;
    if (trimmedCode === submittedCode && days === submittedDays) {
      overviewQ.refetch(); historyQ.refetch();
      fetchExtra(extraTab, submittedCode);
    } else {
      setSubmittedCode(trimmedCode);
      setSubmittedDays(days);
    }
  }
  function fetchExtra(type: string, code: string | null = submittedCode) {
    if (!code) return;
    if (type === 'history') {
      historyMut.trigger('/fundamental/financial-history', { method: 'POST' }, {
        codes: [code], fields: ['eps', 'roe', 'net_profit', 'revenue', 'debt_ratio', 'operating_profit_rate'], date: new Date().toISOString().slice(0, 10).replace(/-/g, ''),
      });
    } else {
      const endpoint = type === 'info' ? `/fundamental/stock-info?code=${code}`
        : type === 'snapshot' ? `/fundamental/financial-snapshot?code=${code}`
        : `/fundamental/f10?code=${code}`;
      if (endpoint === extraPath) extraQ.refetch(); else setExtraPath(endpoint);
    }
  }

  const overview = overviewQ.data;
  const history = historyQ.data;
  const stockName = String((extraQ.data as any)?.data?.name ?? (extraQ.data as any)?.name ?? '');
  const valuation = overview?.valuation;
  const financials = overview?.financials;
  const points = history?.points ?? [];
  const ovCache = overview?.meta?.cache;
  const hsCache = history?.meta?.cache;
  const freshness = [overview?.meta?.fetchedAt, history?.meta?.fetchedAt].filter(Boolean).sort().at(-1) ?? '';
  const updatedAt = overviewQ.dataUpdatedAt ? new Date(overviewQ.dataUpdatedAt).toLocaleString('zh-CN') : '';
  const latest = points.at(-1);
  const first = points[0];
  const peDelta = latest?.pe != null && first?.pe != null ? (latest.pe - first.pe).toFixed(2) : '-';
  const pbDelta = latest?.pb != null && first?.pb != null ? (latest.pb - first.pb).toFixed(2) : '-';

  const missing = useMemo(() => {
    const checks = [
      { label: 'PE', v: valuation?.pe },
      { label: 'PB', v: valuation?.pb },
      { label: 'ROE', v: financials?.roe },
      { label: '净利润', v: financials?.netProfit },
    ];
    return checks.filter((x) => x.v == null).map((x) => x.label);
  }, [valuation, financials]);
  return (
    <PageContainer narrow>
      <h1>基本面分析</h1>
      <form onSubmit={onSubmit} className="flex gap-2.5 flex-wrap items-center">
        <StockCodeInput value={code} onChange={setCode} error={codeError} placeholder="如 600519" />
        <select value={days} onChange={(e) => setDays(Number(e.target.value))} className="px-2 py-1 border border-border rounded text-sm">
          <option value={30}>近1月</option><option value={90}>近3月</option><option value={180}>近6月</option><option value={365}>近1年</option>
        </select>
        <button type="submit" disabled={loading}>{loading ? '查询中...' : '查询'}</button>
      </form>
      {error ? <ErrorState text={error} /> : null}
      <div className="mt-2 text-text-secondary text-sm">
        更新：{updatedAt || '-'} ｜ 抓取：{freshness ? new Date(freshness).toLocaleString('zh-CN') : '-'}
      </div>
      <details className="text-xs text-text-muted mt-1">
        <summary className="cursor-pointer">缓存详情</summary>
        <span>Overview：{cacheText(ovCache)} ｜ History：{cacheText(hsCache)}</span>
      </details>
      {overview?.code && (
        <div className="mt-3 flex items-center gap-2">
          <StockLink code={overview.code} name={stockName || overview.code} />
          <WatchlistButton code={overview.code} name={stockName} />
        </div>
      )}
      <section className="mt-3.5 grid grid-cols-1 sm:grid-cols-2 gap-3">
        <SectionCard className="p-4">
          <h3 className="mt-0">估值指标</h3>
          <KpiGrid cols={2}>
            <KpiCard title="PE" value={fmtNum(valuation?.pe, 2)} />
            <KpiCard title="PB" value={fmtNum(valuation?.pb, 2)} />
            <KpiCard title="PS" value={fmtNum(valuation?.ps, 2)} />
            <KpiCard title="总市值" value={fmtAmount(valuation?.marketCap)} />
          </KpiGrid>
        </SectionCard>
        <SectionCard className="p-4">
          <h3 className="mt-0">财务指标</h3>
          <KpiGrid cols={2}>
            <KpiCard title="ROE" value={fmtNum(financials?.roe, 2)} suffix="%" />
            <KpiCard title="净利润" value={fmtAmount(financials?.netProfit)} />
            <KpiCard title="营收" value={fmtAmount(financials?.revenue)} />
            <KpiCard title="资产负债率" value={fmtNum(financials?.debtRatio, 2)} suffix="%" />
          </KpiGrid>
        </SectionCard>
      </section>
      <SectionCard className="p-4 mt-3">
        <h3 className="mt-0">历史估值走势（{days}天）</h3>
        <div className="text-sm text-text-secondary mb-2">
          PE变化：{fmtNum(first?.pe)} → {fmtNum(latest?.pe)}（Δ {peDelta}）｜ PB变化：{fmtNum(first?.pb)} → {fmtNum(latest?.pb)}（Δ {pbDelta}）
        </div>
        {points.length > 1 ? (
          <LineChart
            categories={points.map((p) => p.date.slice(5))}
            series={[
              { name: 'PE', data: points.map((p) => p.pe ?? 0) },
              { name: 'PB', data: points.map((p) => p.pb ?? 0) },
            ]}
            height={280}
          />
        ) : <p className="text-text-muted text-sm">暂无历史估值数据</p>}
      </SectionCard>
      {missing.length ? <p className="mt-3 text-text-muted text-sm">提示：{missing.join('、')}暂无数据，已显示为"-"</p> : null}
      <section className="mt-5">
        <h2>详细资料</h2>
        <TabBar<ExtraTab> tabs={extraTabs} active={extraTab} onChange={setExtraTab} />
        <SectionCard tabAttached>
          <button type="button" disabled={extraQ.isFetching || historyMut.isPending} onClick={() => fetchExtra(extraTab)}>{extraQ.isFetching || historyMut.isPending ? '加载中...' : '刷新'}</button>
          {extraQ.error || historyMut.error ? <p className="text-error">{extraQ.error || historyMut.error}</p> : null}
          {(() => {
            const raw = extraTab === 'history' ? historyMut.data : extraQ.data;
            if (raw == null) return null;
            const rows = extractArray(raw).filter((r) => r && typeof r === 'object');
            if (rows.length) return <DataTable rows={rows} maxHeight={400} onExport={() => exportCSV(rows, `fundamental-${extraTab}`)} />;
            // Structured key-value display for single-object responses
            const obj = extractObject(raw);
            const flat = flattenObj(obj);
            const entries = Object.entries(flat).filter(([k, v]) => v != null && v !== '' && v !== 0 && String(v) !== '0' && String(v) !== '0.00' && String(v) !== '--' && !['infoType', 'cached', 'source', 'source_chain', 'fallback_reason', 'method', 'note', 'degraded', 'stockCodes', 'date', 'fields', 'fnFields'].includes(k));
            return entries.length ? (
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-x-4 gap-y-1 text-sm mt-2">
                {entries.map(([k, v]) => <div key={k}><span className="text-text-muted">{FIELD_LABELS[k] ?? k}：</span>{typeof v === 'number' ? (Math.abs(v) >= 1e6 ? fmtAmount(v) : fmtNum(v, 2)) : String(v)}</div>)}
              </div>
            ) : <pre className="mt-2 text-xs bg-surface-alt p-2 rounded overflow-auto max-h-[300px]">{JSON.stringify(raw, null, 2)}</pre>;
          })()}
        </SectionCard>
      </section>
    </PageContainer>
  );
}