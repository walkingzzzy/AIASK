'use client';

import { FormEvent, useMemo, useState } from 'react';
import { PageContainer, SectionCard, TabBar, DataTable, StockCodeInput } from '@/components/ui';
import { useApiMutation } from '@/hooks/use-api-mutation';
import { useStockCode } from '@/hooks/use-stock-code';
import { ErrorState } from '@/components/status-state';
import { fmt, cacheText, type CacheMeta } from '@/lib/api';

import { extractArray } from '@/lib/data-utils';
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
  const [updatedAt, setUpdatedAt] = useState('');
  const [extraTab, setExtraTab] = useState<ExtraTab>('info');

  const overviewApi = useApiMutation<OverviewData>();
  const historyApi = useApiMutation<HistoryData>();
  const extraApi = useApiMutation<unknown>();

  const loading = overviewApi.isPending || historyApi.isPending;
  const error = overviewApi.error || historyApi.error;

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!validate()) return;
    try {
      await Promise.all([
        overviewApi.triggerAsync(`/fundamental/overview?code=${trimmedCode}`),
        historyApi.triggerAsync(`/fundamental/history?code=${trimmedCode}&days=${days}`),
      ]);
      setUpdatedAt(new Date().toLocaleString('zh-CN'));
    } catch { /* errors captured by mutations */ }
  }
  function fetchExtra(type: string) {
    if (!validate()) return;
    if (type === 'history') {
      extraApi.trigger('/fundamental/financial-history', { method: 'POST' }, {
        codes: [trimmedCode], fields: ['roe', 'net_profit', 'revenue'], date: '',
      });
    } else {
      const endpoint = type === 'info' ? `/fundamental/stock-info?code=${trimmedCode}`
        : type === 'snapshot' ? `/fundamental/financial-snapshot?code=${trimmedCode}`
        : `/fundamental/f10?code=${trimmedCode}`;
      extraApi.trigger(endpoint);
    }
  }

  const overview = overviewApi.data;
  const history = historyApi.data;
  const valuation = overview?.valuation;
  const financials = overview?.financials;
  const points = history?.points ?? [];
  const ovCache = overview?.meta?.cache;
  const hsCache = history?.meta?.cache;
  const freshness = [overview?.meta?.fetchedAt, history?.meta?.fetchedAt].filter(Boolean).sort().at(-1) ?? '';
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
      <section className="mt-3.5 grid grid-cols-2 gap-3">
        <SectionCard>
          <h3 className="mt-0">估值指标</h3>
          <div>PE：{fmt(valuation?.pe)}</div>
          <div>PB：{fmt(valuation?.pb)}</div>
          <div>PS：{fmt(valuation?.ps)}</div>
          <div>总市值：{fmt(valuation?.marketCap)}</div>
        </SectionCard>
        <SectionCard>
          <h3 className="mt-0">财务指标</h3>
          <div>ROE：{fmt(financials?.roe)}</div>
          <div>净利润：{fmt(financials?.netProfit)}</div>
          <div>营收：{fmt(financials?.revenue)}</div>
          <div>资产负债率：{fmt(financials?.debtRatio)}</div>
        </SectionCard>
      </section>
      <SectionCard>
        <h3 className="mt-0">历史对比（{days}天）</h3>
        <div>PE变化：{fmt(first?.pe)} → {fmt(latest?.pe)}（Δ {peDelta}）</div>
        <div>PB变化：{fmt(first?.pb)} → {fmt(latest?.pb)}（Δ {pbDelta}）</div>
        <div className="mt-2 max-h-[220px] overflow-auto border-t border-dashed border-border pt-2">
          {points.slice(-8).map((p) => <div key={p.date}>{p.date}: PE={fmt(p.pe)} PB={fmt(p.pb)} PS={fmt(p.ps)} Close={fmt(p.close)}</div>)}
          {!points.length ? <div>暂无历史估值数据</div> : null}
        </div>
      </SectionCard>
      {missing.length ? <p className="mt-3 text-warning">数据完整性提示：缺失字段 {missing.join('、')}，已降级展示为"-"。</p> : null}
      <section className="mt-5">
        <h2>详细资料</h2>
        <TabBar<ExtraTab> tabs={extraTabs} active={extraTab} onChange={setExtraTab} />
        <SectionCard tabAttached>
          <button type="button" disabled={extraApi.isPending} onClick={() => fetchExtra(extraTab)}>{extraApi.isPending ? '加载中...' : '查询'}</button>
          {extraApi.error ? <p className="text-error">{extraApi.error}</p> : null}
          {extraApi.data != null ? (() => {
            const rows = extractArray(extraApi.data);
            return rows.length
              ? <DataTable rows={rows} maxHeight={400} onExport={() => exportCSV(rows, `fundamental-${extraTab}`)} />
              : <pre className="mt-2 text-xs bg-surface-alt p-2 rounded overflow-auto max-h-[300px]">{JSON.stringify(extraApi.data, null, 2)}</pre>;
          })() : null}
        </SectionCard>
      </section>
    </PageContainer>
  );
}