'use client';

import { FormEvent, useMemo, useState } from 'react';
import { PageContainer, SectionCard, TabBar, DataTable, StockCodeInput, KpiCard, KpiGrid } from '@/components/ui';
import { LineChart } from '@/components/charts';
import { useApiQuery } from '@/hooks/use-api-query';
import { useApiMutation } from '@/hooks/use-api-mutation';
import { useStockCode } from '@/hooks/use-stock-code';
import { ErrorState } from '@/components/status-state';
import { fmt, cacheText, type CacheMeta } from '@/lib/api';

import { extractArray, fmtNum, fmtAmount } from '@/lib/data-utils';
import { exportCSV } from '@/lib/export';

type OverviewData = { code?: string; financials?: { roe: number | null; netProfit: number | null; revenue: number | null; debtRatio: number | null }; valuation?: { pe: number | null; pb: number | null; ps: number | null; marketCap: number | null }; sourceTools?: Record<string, unknown>; meta?: CacheMeta };
type HistoryPoint = { date: string; pe: number | null; pb: number | null; ps: number | null; close: number | null };
type HistoryData = { code?: string; days?: number; points?: HistoryPoint[]; sourceTool?: string; meta?: CacheMeta };
type ExtraTab = 'info' | 'snapshot' | 'f10' | 'history';

const extraTabs: readonly { key: ExtraTab; label: string }[] = [
  { key: 'info', label: '基本信息' },
  { key: 'snapshot', label: '财务快照' },
  { key: 'f10', label: 'F10资料' },
  { key: 'history', label: '财务历史' },
];

export default function FundamentalPage() {
  const { code, setCode, codeError, validate, trimmedCode } = useStockCode('600519');
  const [days, setDays] = useState(90);
  const [extraTab, setExtraTab] = useState<ExtraTab>('info');
  const [submittedCode, setSubmittedCode] = useState<string | null>(null);
  const [submittedDays, setSubmittedDays] = useState<number>(90);

  const overviewQ = useApiQuery<OverviewData>(submittedCode ? `/fundamental/overview?code=${submittedCode}` : null);
  const historyQ = useApiQuery<HistoryData>(submittedCode ? `/fundamental/history?code=${submittedCode}&days=${submittedDays}` : null);
  const [extraPath, setExtraPath] = useState<string | null>(null);
  const extraQ = useApiQuery<unknown>(extraPath);
  const historyMut = useApiMutation<unknown>();

  const loading = overviewQ.isFetching || historyQ.isFetching;
  const error = overviewQ.error || historyQ.error;

  function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!validate()) return;
    if (trimmedCode === submittedCode && days === submittedDays) {
      overviewQ.refetch(); historyQ.refetch();
    } else {
      setSubmittedCode(trimmedCode);
      setSubmittedDays(days);
    }
  }
  function fetchExtra(type: string) {
    if (!validate()) return;
    if (type === 'history') {
      historyMut.trigger('/fundamental/financial-history', { method: 'POST' }, {
        codes: [trimmedCode], fields: ['roe', 'net_profit', 'revenue'], date: '',
      });
    } else {
      const endpoint = type === 'info' ? `/fundamental/stock-info?code=${trimmedCode}`
        : type === 'snapshot' ? `/fundamental/financial-snapshot?code=${trimmedCode}`
        : `/fundamental/f10?code=${trimmedCode}`;
      if (endpoint === extraPath) extraQ.refetch(); else setExtraPath(endpoint);
    }
  }

  const overview = overviewQ.data;
  const history = historyQ.data;
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
      <div className="mt-2 text-text-secondary">
        更新：{updatedAt || '-'} ｜ 抓取：{freshness ? new Date(freshness).toLocaleString('zh-CN') : '-'}
        <br />Overview缓存：{cacheText(ovCache)} ｜ History缓存：{cacheText(hsCache)}
      </div>
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
          PE变化：{fmt(first?.pe)} → {fmt(latest?.pe)}（Δ {peDelta}）｜ PB变化：{fmt(first?.pb)} → {fmt(latest?.pb)}（Δ {pbDelta}）
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
      {missing.length ? <p className="mt-3 text-warning">数据完整性提示：缺失字段 {missing.join('、')}，已降级展示为"-"。</p> : null}
      <section className="mt-5">
        <h2>详细资料</h2>
        <TabBar<ExtraTab> tabs={extraTabs} active={extraTab} onChange={setExtraTab} />
        <SectionCard tabAttached>
          <button type="button" disabled={extraQ.isFetching || historyMut.isPending} onClick={() => fetchExtra(extraTab)}>{extraQ.isFetching || historyMut.isPending ? '加载中...' : '查询'}</button>
          {extraQ.error || historyMut.error ? <p className="text-error">{extraQ.error || historyMut.error}</p> : null}
          {(() => {
            const raw = extraTab === 'history' ? historyMut.data : extraQ.data;
            if (raw == null) return null;
            const rows = extractArray(raw);
            return rows.length
              ? <DataTable rows={rows} maxHeight={400} onExport={() => exportCSV(rows, `fundamental-${extraTab}`)} />
              : <pre className="mt-2 text-xs bg-surface-alt p-2 rounded overflow-auto max-h-[300px]">{JSON.stringify(raw, null, 2)}</pre>;
          })()}
        </SectionCard>
      </section>
    </PageContainer>
  );
}