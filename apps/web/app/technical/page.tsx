'use client';

import { useState, useMemo } from 'react';
import { PageContainer, TabBar, SectionCard, StockCodeInput, Badge, DataTable } from '@/components/ui';
import { useApiMutation } from '@/hooks/use-api-mutation';
import { useStockCode } from '@/hooks/use-stock-code';
import { LoadingState, ErrorState, EmptyState } from '@/components/status-state';
import { LineChart, COLORS } from '@/components/charts';
import { extractArray } from '@/lib/data-utils';
import { exportCSV } from '@/lib/export';

const TABS = [
  { key: 'indicators', label: '技术指标' },
  { key: 'patterns', label: 'K线形态' },
  { key: 'available', label: '可用形态' },
] as const;

type Tab = (typeof TABS)[number]['key'];
const INDICATOR_OPTIONS = ['MA', 'EMA', 'RSI', 'MACD', 'KDJ', 'BOLL', 'ATR', 'CCI', 'WR'];

export default function TechnicalPage() {
  const [tab, setTab] = useState<Tab>('indicators');
  const { code, setCode, codeError, validate, trimmedCode } = useStockCode('600519');
  const [period, setPeriod] = useState('daily');
  const [limit, setLimit] = useState('100');
  const [selectedIndicators, setSelectedIndicators] = useState<string[]>(['MA', 'RSI', 'MACD']);
  const { trigger, data, isPending, error, reset } = useApiMutation<unknown>();

  function toggleIndicator(ind: string) {
    setSelectedIndicators((prev) =>
      prev.includes(ind) ? prev.filter((x) => x !== ind) : [...prev, ind],
    );
  }

  function submit() {
    if (tab === 'available') {
      trigger('/technical/available-patterns');
    } else {
      if (!validate()) return;
      const endpoint = tab === 'indicators' ? '/technical/indicators' : '/technical/patterns';
      const body: Record<string, unknown> = { code: trimmedCode, period, limit: Number(limit) };
      if (tab === 'indicators') body.indicators = selectedIndicators;
      trigger(endpoint, { method: 'POST' }, body);
    }
  }

  const rows = useMemo(() => {
    if (!data) return [];
    if (tab === 'indicators') return extractArray(data, 'indicators', 'values', 'results');
    if (tab === 'patterns') return extractArray(data, 'patterns', 'results');
    return extractArray(data, 'patterns', 'available');
  }, [data, tab]);

  const indicatorChart = useMemo(() => {
    if (tab !== 'indicators' || rows.length === 0) return null;
    const sample = rows[0] as Record<string, unknown>;
    const keys = Object.keys(sample);
    const dateKey = keys.find(k => /date|time|日期/i.test(k));
    const numKeys = keys.filter(k => k !== dateKey && typeof sample[k] === 'number');
    if (!dateKey || numKeys.length === 0) return null;
    return {
      categories: rows.map(r => String((r as Record<string, unknown>)[dateKey!])),
      series: numKeys.map((key, i) => ({
        name: key,
        data: rows.map(r => Number((r as Record<string, unknown>)[key]) || 0),
        color: COLORS.series[i % COLORS.series.length],
      })),
    };
  }, [rows, tab]);

  return (
    <PageContainer>
      <h1>技术分析</h1>
      <TabBar tabs={TABS} active={tab} onChange={(key) => { setTab(key); reset(); }} />
      <SectionCard tabAttached>
        {tab !== 'available' ? (
          <div className="flex gap-2 flex-wrap items-center mb-3">
            <StockCodeInput value={code} onChange={setCode} error={codeError} />
            <select
              value={period}
              onChange={(e) => setPeriod(e.target.value)}
              className="px-2 py-1 border border-border rounded text-sm"
            >
              <option value="daily">日线</option>
              <option value="weekly">周线</option>
              <option value="monthly">月线</option>
            </select>
            <label className="text-sm">
              数量{' '}
              <input
                value={limit}
                onChange={(e) => setLimit(e.target.value)}
                className="w-[60px] px-2 py-1 border border-border rounded text-sm"
              />
            </label>
          </div>
        ) : null}
        {tab === 'indicators' ? (
          <div className="mb-3">
            <div className="text-[13px] text-muted mb-1">选择指标：</div>
            <div className="flex gap-1.5 flex-wrap">
              {INDICATOR_OPTIONS.map((ind) => (
                <label key={ind} className="flex items-center gap-1 cursor-pointer text-sm">
                  <input
                    type="checkbox"
                    checked={selectedIndicators.includes(ind)}
                    onChange={() => toggleIndicator(ind)}
                  />
                  {ind}
                </label>
              ))}
            </div>
          </div>
        ) : null}
        <button
          type="button"
          disabled={isPending}
          onClick={submit}
          className="px-3 py-1 border border-border rounded text-sm disabled:opacity-50"
        >
          {tab === 'available' ? '查看可用形态' : tab === 'indicators' ? '计算指标' : '识别形态'}
        </button>
        {isPending ? <LoadingState text="计算中..." /> : null}
        {error ? <ErrorState text={error} hint="请检查参数后重试" /> : null}
        {!isPending && !data && !error ? <EmptyState text="点击按钮开始分析" /> : null}
        {data != null && tab === 'indicators' ? (
          <div className="mt-3 space-y-4">
            {indicatorChart ? (
              <LineChart categories={indicatorChart.categories} series={indicatorChart.series} height={350} />
            ) : null}
            <DataTable
              rows={rows as Record<string, unknown>[]}
              maxHeight={400}
              onExport={() => exportCSV(rows as Record<string, unknown>[], '技术指标')}
            />
          </div>
        ) : null}
        {data != null && tab === 'patterns' ? (
          <div className="mt-3">
            <DataTable
              rows={rows as Record<string, unknown>[]}
              columns={[
                { key: 'date', label: '日期' },
                { key: 'pattern', label: '形态' },
                { key: 'type', label: '类型', render: (v) => (
                  <Badge variant={String(v) === 'bullish' ? 'success' : String(v) === 'bearish' ? 'danger' : 'info'}>{String(v)}</Badge>
                )},
                { key: 'reliability', label: '可靠性' },
              ]}
              onExport={() => exportCSV(rows as Record<string, unknown>[], 'K线形态')}
            />
          </div>
        ) : null}
        {data != null && tab === 'available' ? (
          <div className="mt-3">
            <DataTable
              rows={rows as Record<string, unknown>[]}
              columns={[
                { key: 'name', label: '名称' },
                { key: 'description', label: '描述' },
                { key: 'type', label: '类型', render: (v) => (
                  <Badge variant={String(v) === 'bullish' ? 'success' : String(v) === 'bearish' ? 'danger' : 'info'}>{String(v)}</Badge>
                )},
              ]}
              onExport={() => exportCSV(rows as Record<string, unknown>[], '可用形态')}
            />
          </div>
        ) : null}
      </SectionCard>
    </PageContainer>
  );
}
