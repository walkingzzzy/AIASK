'use client';

import { useState, useMemo } from 'react';
import { PageContainer, TabBar, SectionCard, StockCodeInput, KpiGrid, KpiCard, DataTable, Badge } from '@/components/ui';
import { useApiMutation } from '@/hooks/use-api-mutation';
import { useStockCode } from '@/hooks/use-stock-code';
import { LoadingState, ErrorState, EmptyState } from '@/components/status-state';
import { BarChart, COLORS } from '@/components/charts';
import { extractArray, extractObject, fmtNum, fmtPct } from '@/lib/data-utils';
import { exportCSV } from '@/lib/export';

const TABS = [
  { key: 'dcf', label: 'DCF估值' },
  { key: 'ddm', label: 'DDM估值' },
  { key: 'relative', label: '相对估值' },
  { key: 'scenario', label: '情景DCF' },
] as const;

type Tab = (typeof TABS)[number]['key'];

function v(obj: Record<string, unknown>, ...keys: string[]): unknown {
  for (const k of keys) if (obj[k] != null) return obj[k];
  return null;
}

export default function ValuationPage() {
  const [tab, setTab] = useState<Tab>('dcf');
  const { code, setCode, codeError, validate, trimmedCode } = useStockCode('600519');
  const { trigger, data, isPending, error, reset } = useApiMutation<unknown>();
  const [discountRate, setDiscountRate] = useState('0.1');
  const [growthRate, setGrowthRate] = useState('0.05');
  const [years, setYears] = useState('5');
  const [dividend, setDividend] = useState('');
  const [ddmGrowth, setDdmGrowth] = useState('0.03');
  const [requiredReturn, setRequiredReturn] = useState('0.08');
  const [baseRevenue, setBaseRevenue] = useState('');
  const [industry, setIndustry] = useState('');

  function submit() {
    if (!validate()) return;
    let body: Record<string, unknown> = { code: trimmedCode };
    let endpoint = '';
    if (tab === 'dcf') {
      endpoint = '/valuation/dcf';
      body = { ...body, discountRate: Number(discountRate), growthRate: Number(growthRate), years: Number(years) };
    } else if (tab === 'ddm') {
      endpoint = '/valuation/ddm';
      body = { ...body, growthRate: Number(ddmGrowth), requiredReturn: Number(requiredReturn) };
      if (dividend) body.dividend = Number(dividend);
    } else if (tab === 'relative') {
      endpoint = '/valuation/relative';
    } else {
      endpoint = '/valuation/scenario-dcf';
      if (baseRevenue) body.baseRevenue = Number(baseRevenue);
      if (industry) body.industry = industry;
      body.years = Number(years);
    }
    trigger(endpoint, { method: 'POST' }, body);
  }

  const result = useMemo(() => (data ? extractObject(data) : null), [data]);
  const relativeRows = useMemo(() => (data && tab === 'relative' ? extractArray(data, 'comparisons', 'peers', 'results') : []), [data, tab]);
  const scenarioRows = useMemo(() => (data && tab === 'scenario' ? extractArray(data, 'scenarios', 'results') : []), [data, tab]);

  const inputCls = 'px-2 py-1 border border-border rounded text-sm';
  const btnCls = 'px-3 py-1 border border-border rounded text-sm disabled:opacity-50';

  return (
    <PageContainer>
      <h1>估值分析</h1>
      <div className="flex gap-2 items-center mb-3">
        <StockCodeInput value={code} onChange={setCode} error={codeError} />
      </div>
      <TabBar tabs={TABS} active={tab} onChange={(key) => { setTab(key); reset(); }} />
      <SectionCard tabAttached>
        {tab === 'dcf' ? (
          <div className="flex gap-2 flex-wrap items-center">
            <label className="text-sm">折现率 <input value={discountRate} onChange={(e) => setDiscountRate(e.target.value)} className={`w-[80px] ${inputCls}`} /></label>
            <label className="text-sm">增长率 <input value={growthRate} onChange={(e) => setGrowthRate(e.target.value)} className={`w-[80px] ${inputCls}`} /></label>
            <label className="text-sm">年数 <input value={years} onChange={(e) => setYears(e.target.value)} className={`w-[60px] ${inputCls}`} /></label>
            <button type="button" disabled={isPending} onClick={submit} className={btnCls}>计算DCF</button>
          </div>
        ) : null}
        {tab === 'ddm' ? (
          <div className="flex gap-2 flex-wrap items-center">
            <label className="text-sm">股息 <input value={dividend} onChange={(e) => setDividend(e.target.value)} className={`w-[80px] ${inputCls}`} placeholder="可选" /></label>
            <label className="text-sm">增长率 <input value={ddmGrowth} onChange={(e) => setDdmGrowth(e.target.value)} className={`w-[80px] ${inputCls}`} /></label>
            <label className="text-sm">要求回报率 <input value={requiredReturn} onChange={(e) => setRequiredReturn(e.target.value)} className={`w-[80px] ${inputCls}`} /></label>
            <button type="button" disabled={isPending} onClick={submit} className={btnCls}>计算DDM</button>
          </div>
        ) : null}
        {tab === 'relative' ? (
          <div>
            <button type="button" disabled={isPending} onClick={submit} className={btnCls}>查询相对估值</button>
          </div>
        ) : null}
        {tab === 'scenario' ? (
          <div className="flex gap-2 flex-wrap items-center">
            <label className="text-sm">基础营收 <input value={baseRevenue} onChange={(e) => setBaseRevenue(e.target.value)} className={`w-[100px] ${inputCls}`} placeholder="可选" /></label>
            <label className="text-sm">行业 <input value={industry} onChange={(e) => setIndustry(e.target.value)} className={`w-[100px] ${inputCls}`} placeholder="可选" /></label>
            <label className="text-sm">年数 <input value={years} onChange={(e) => setYears(e.target.value)} className={`w-[60px] ${inputCls}`} /></label>
            <button type="button" disabled={isPending} onClick={submit} className={btnCls}>情景分析</button>
          </div>
        ) : null}
        {isPending ? <LoadingState text="计算中..." /> : null}
        {error ? <ErrorState text={error} hint="请检查参数后重试" /> : null}
        {!isPending && !data && !error ? <EmptyState text="设置参数后点击按钮开始估值" /> : null}
        {data != null && tab === 'dcf' && result ? (() => {
          const r = result as Record<string, unknown>;
          const intrinsic = Number(v(r, 'intrinsic_value', 'intrinsicValue', 'value') ?? 0);
          const price = Number(v(r, 'current_price', 'currentPrice', 'price') ?? 0);
          const upside = Number(v(r, 'upside', 'upside_pct', 'upsidePct') ?? (price ? ((intrinsic - price) / price) * 100 : 0));
          const mos = Number(v(r, 'margin_of_safety', 'marginOfSafety', 'mos') ?? 0);
          const cfs = (r.cash_flows ?? r.cashFlows ?? r.projected_cash_flows ?? []) as Record<string, unknown>[];
          return (
            <div className="mt-3 space-y-4">
              <KpiGrid cols={4}>
                <KpiCard title="内在价值" value={fmtNum(intrinsic, 2)} suffix="元" />
                <KpiCard title="当前价格" value={fmtNum(price, 2)} suffix="元" />
                <KpiCard title="上涨空间" value={fmtPct(upside)} change={upside || null} />
                <KpiCard title="安全边际" value={fmtPct(mos)} />
              </KpiGrid>
              {Array.isArray(cfs) && cfs.length > 0 && (
                <BarChart
                  items={cfs.map((cf, i) => ({
                    label: String(cf.year ?? cf.period ?? `Y${i + 1}`),
                    value: Number(cf.value ?? cf.cash_flow ?? cf.fcf ?? 0),
                    color: COLORS.primary,
                  }))}
                  yAxisName="现金流"
                />
              )}
              {r.assumptions ? (
                <div className="text-xs text-muted p-2 bg-muted/10 rounded">
                  假设: {JSON.stringify(r.assumptions)}
                </div>
              ) : null}
            </div>
          );
        })() : null}
        {data != null && tab === 'ddm' && result ? (() => {
          const r = result as Record<string, unknown>;
          const intrinsic = Number(v(r, 'intrinsic_value', 'intrinsicValue', 'value') ?? 0);
          const price = Number(v(r, 'current_price', 'currentPrice', 'price') ?? 0);
          const upside = Number(v(r, 'upside', 'upside_pct', 'upsidePct') ?? (price ? ((intrinsic - price) / price) * 100 : 0));
          const divYield = Number(v(r, 'dividend_yield', 'dividendYield', 'yield') ?? 0);
          return (
            <div className="mt-3">
              <KpiGrid cols={4}>
                <KpiCard title="内在价值" value={fmtNum(intrinsic, 2)} suffix="元" />
                <KpiCard title="当前价格" value={fmtNum(price, 2)} suffix="元" />
                <KpiCard title="上涨空间" value={fmtPct(upside)} change={upside || null} />
                <KpiCard title="股息率" value={fmtPct(divYield)} />
              </KpiGrid>
            </div>
          );
        })() : null}
        {data != null && tab === 'relative' ? (
          <div className="mt-3 space-y-4">
            {relativeRows.length > 0 && (
              <>
                <DataTable
                  rows={relativeRows as Record<string, unknown>[]}
                  columns={[
                    { key: 'name', label: '名称' },
                    { key: 'code', label: '代码' },
                    { key: 'pe', label: 'PE', align: 'right' as const, render: (val) => fmtNum(Number(val), 2) },
                    { key: 'pb', label: 'PB', align: 'right' as const, render: (val) => fmtNum(Number(val), 2) },
                    { key: 'ps', label: 'PS', align: 'right' as const, render: (val) => fmtNum(Number(val), 2) },
                    { key: 'peg', label: 'PEG', align: 'right' as const, render: (val) => fmtNum(Number(val), 2) },
                    { key: 'dividend_yield', label: '股息率', align: 'right' as const, render: (val) => fmtPct(Number(val)) },
                  ]}
                  onExport={() => exportCSV(relativeRows as Record<string, unknown>[], '相对估值')}
                />
                <BarChart
                  items={relativeRows.slice(0, 10).map((r) => {
                    const row = r as Record<string, unknown>;
                    return { label: String(row.name ?? row.code ?? ''), value: Number(row.pe ?? 0), color: COLORS.primary };
                  })}
                  yAxisName="PE"
                  horizontal
                />
              </>
            )}
            {relativeRows.length === 0 && result && (
              <DataTable rows={[result as Record<string, unknown>]} />
            )}
          </div>
        ) : null}
        {data != null && tab === 'scenario' ? (() => {
          const scenarios = scenarioRows.length > 0 ? scenarioRows : (() => {
            if (!result) return [];
            const r = result as Record<string, unknown>;
            return ['optimistic', 'base', 'pessimistic']
              .filter(k => r[k] != null)
              .map(k => ({ scenario: k, ...(r[k] as Record<string, unknown>) }));
          })();
          const badgeVariant = (s: string) => /optim/i.test(s) ? 'success' as const : /pessim/i.test(s) ? 'danger' as const : 'warning' as const;
          return (
            <div className="mt-3 space-y-4">
              {scenarios.length > 0 && (
                <>
                  <KpiGrid cols={3}>
                    {(scenarios as Record<string, unknown>[]).map((s, i) => {
                      const label = String(s.scenario ?? s.name ?? s.label ?? `情景${i + 1}`);
                      const val = Number(s.intrinsic_value ?? s.intrinsicValue ?? s.value ?? 0);
                      const up = Number(s.upside ?? s.upside_pct ?? 0);
                      return (
                        <KpiCard
                          key={i}
                          title={<><Badge variant={badgeVariant(label)}>{label}</Badge></> as unknown as string}
                          value={fmtNum(val, 2)}
                          suffix="元"
                          change={up || null}
                        />
                      );
                    })}
                  </KpiGrid>
                  <BarChart
                    items={(scenarios as Record<string, unknown>[]).map((s, i) => ({
                      label: String(s.scenario ?? s.name ?? `情景${i + 1}`),
                      value: Number(s.intrinsic_value ?? s.intrinsicValue ?? s.value ?? 0),
                      color: [COLORS.success, COLORS.warning, COLORS.danger][i] ?? COLORS.primary,
                    }))}
                    yAxisName="内在价值"
                  />
                </>
              )}
              {scenarios.length === 0 && result && (
                <DataTable rows={[result as Record<string, unknown>]} />
              )}
            </div>
          );
        })() : null}
      </SectionCard>
      <div className="mt-4 p-2.5 bg-amber-50 rounded-md text-xs text-amber-800">
        免责声明：估值模型结果仅供参考，不构成投资建议。模型假设可能与实际情况存在偏差。
      </div>
    </PageContainer>
  );
}
