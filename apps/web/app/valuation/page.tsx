'use client';

import { useState, useMemo } from 'react';
import { PageContainer, TabBar, SectionCard, StockCodeInput, KpiGrid, KpiCard, DataTable, Badge } from '@/components/ui';
import { useApiMutation } from '@/hooks/use-api-mutation';
import { useStockCode } from '@/hooks/use-stock-code';
import { LoadingState, ErrorState, EmptyState } from '@/components/status-state';
import { BarChart, COLORS } from '@/components/charts';
import { extractArray, extractObject, fmtNum, fmtPct, fmtAmount } from '@/lib/data-utils';
import { exportCSV } from '@/lib/export';
import { StockLink } from '@/components/stock-link';
import { WatchlistButton } from '@/components/watchlist-button';

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

/** Unwrap MCP envelope: data -> result -> data */
function unwrapMcp(raw: unknown): Record<string, unknown> {
  const obj = extractObject(raw);
  if (typeof obj.result === 'string') return obj as Record<string, unknown>; // error string
  if (obj.result) {
    const inner = extractObject(obj.result as Record<string, unknown>);
    return inner as Record<string, unknown>;
  }
  return obj as Record<string, unknown>;
}

/** Get MCP-level error */
function mcpError(raw: unknown): string | null {
  const obj = extractObject(raw);
  if (typeof obj.result === 'string' && /error/i.test(obj.result)) return obj.result;
  if (obj.result && typeof obj.result === 'object') {
    const inner = obj.result as Record<string, unknown>;
    if (inner.success === false && inner.error) return String(inner.error);
    const d = extractObject(inner);
    if (d.success === false && d.error) return String(d.error);
  }
  return null;
}

export default function ValuationPage() {
  const [tab, setTab] = useState<Tab>('dcf');
  const { code, setCode, codeError, validate, trimmedCode, resolvedCode } = useStockCode('600519');
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
      if (!baseRevenue) { alert('请输入基础营收'); return; }
      body.baseRevenue = Number(baseRevenue);
      if (industry) body.industry = industry;
      body.years = Number(years);
    }
    trigger(endpoint, { method: 'POST' }, body);
  }

  const result = useMemo(() => (data ? unwrapMcp(data) : null), [data]);
  const mcpErr = data ? mcpError(data) : null;
  const friendlyErr = mcpErr
    ? /No valid valuation metrics/i.test(mcpErr) ? `该股票(${trimmedCode})暂无有效估值指标数据` : mcpErr
    : null;
  const relativeRows = useMemo(() => (result && tab === 'relative' ? extractArray(result, 'comparisons', 'peers', 'results') : []), [result, tab]);
  const scenarioRows = useMemo(() => (result && tab === 'scenario' ? extractArray(result, 'scenarios', 'results') : []), [result, tab]);

  const inputCls = 'px-2 py-1 border border-border rounded text-sm';
  const btnCls = 'px-3 py-1 border border-border rounded text-sm disabled:opacity-50';

  return (
    <PageContainer>
      <h1>估值分析</h1>
      {resolvedCode && (
        <div className="flex items-center gap-2 mb-2">
          <StockLink code={resolvedCode} name={resolvedCode} />
          <WatchlistButton code={resolvedCode} name="" />
        </div>
      )}
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
            <label className="text-sm">基础营收 <input value={baseRevenue} onChange={(e) => setBaseRevenue(e.target.value)} className={`w-[100px] ${inputCls}`} placeholder="必填，如 1300亿" /></label>
            <label className="text-sm">行业 <input value={industry} onChange={(e) => setIndustry(e.target.value)} className={`w-[100px] ${inputCls}`} placeholder="可选" /></label>
            <label className="text-sm">年数 <input value={years} onChange={(e) => setYears(e.target.value)} className={`w-[60px] ${inputCls}`} /></label>
            <button type="button" disabled={isPending} onClick={submit} className={btnCls}>情景分析</button>
          </div>
        ) : null}
        {isPending ? <LoadingState text="计算中..." /> : null}
        {error || friendlyErr ? <ErrorState text={error || friendlyErr!} hint="请检查参数后重试" /> : null}
        {!isPending && !data && !error ? <EmptyState text="设置参数后点击按钮开始估值" /> : null}
        {data != null && !friendlyErr && tab === 'dcf' && result ? (() => {
          const r = result as Record<string, unknown>;
          const intrinsic = Number(v(r, 'intrinsic_value', 'intrinsicValue', 'value') ?? 0);
          const pvSum = Number(v(r, 'pv_sum', 'pvSum') ?? 0);
          const pvTerminal = Number(v(r, 'pv_terminal', 'pvTerminal') ?? 0);
          const terminalValue = Number(v(r, 'terminal_value', 'terminalValue') ?? 0);
          const model = String(v(r, 'model') ?? '');
          const wacc = r.wacc_breakdown as Record<string, unknown> | undefined;
          const cfs = (r.cash_flows ?? r.cashFlows ?? r.projected_cash_flows ?? r.projection ?? []) as Record<string, unknown>[];
          return (
            <div className="mt-3 space-y-4">
              <KpiGrid cols={4}>
                <KpiCard title="内在价值(总)" value={fmtAmount(intrinsic)} />
                <KpiCard title="现金流现值" value={fmtAmount(pvSum)} />
                <KpiCard title="终值现值" value={fmtAmount(pvTerminal)} />
                <KpiCard title="终值" value={fmtAmount(terminalValue)} />
              </KpiGrid>
              {model && <div className="text-xs text-text-secondary">模型: {model}</div>}
              {wacc && (
                <div className="text-xs text-text-secondary flex flex-wrap gap-x-4">
                  <span>WACC: {fmtPct(Number(wacc.wacc ?? 0) * 100)}</span>
                  <span>权益成本: {fmtPct(Number(wacc.cost_of_equity ?? 0) * 100)}</span>
                  <span>债务成本(税后): {fmtPct(Number(wacc.cost_of_debt_after_tax ?? 0) * 100)}</span>
                </div>
              )}
              {Array.isArray(cfs) && cfs.length > 0 && (
                <BarChart
                  items={cfs.map((cf, i) => ({
                    label: String(cf.year ?? cf.period ?? `Y${i + 1}`),
                    value: Number(cf.pv_fcf ?? cf.fcf ?? cf.value ?? cf.cash_flow ?? 0),
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
        {data != null && !friendlyErr && tab === 'ddm' && result ? (() => {
          const r = result as Record<string, unknown>;
          const intrinsic = Number(v(r, 'intrinsic_value', 'intrinsicValue', 'value') ?? 0);
          const curDiv = Number(v(r, 'current_dividend', 'currentDividend') ?? 0);
          const nextDiv = Number(v(r, 'next_dividend', 'nextDividend') ?? 0);
          const model = String(v(r, 'model') ?? '');
          return (
            <div className="mt-3">
              <KpiGrid cols={3}>
                <KpiCard title="内在价值" value={fmtNum(intrinsic, 2)} suffix="元/股" />
                <KpiCard title="当前股息" value={fmtNum(curDiv, 2)} suffix="元" />
                <KpiCard title="预期下期股息" value={fmtNum(nextDiv, 2)} suffix="元" />
              </KpiGrid>
              {model && <div className="text-xs text-text-secondary mt-2">模型: {model}</div>}
            </div>
          );
        })() : null}
        {data != null && !friendlyErr && tab === 'relative' ? (
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
        {data != null && !friendlyErr && tab === 'scenario' ? (() => {
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
