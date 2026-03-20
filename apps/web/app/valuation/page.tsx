'use client';

import { useState, useMemo } from 'react';
import Link from 'next/link';
import { PageContainer, TabBar, SectionCard, StockCodeInput, KpiGrid, KpiCard, DataTable, Badge } from '@/components/ui';
import { useApiMutation } from '@/hooks/use-api-mutation';
import { useStockCode } from '@/hooks/use-stock-code';
import { LoadingState, ErrorState, EmptyState } from '@/components/status-state';
import { BarChart, COLORS } from '@/components/charts';
import { extractArray, fmtNum, fmtPct, fmtAmount } from '@/lib/data-utils';
import { exportCSV } from '@/lib/export';
import { StockLink } from '@/components/stock-link';
import { WatchlistButton } from '@/components/watchlist-button';
import { extractToolError, unwrapToolPayload } from '@/lib/tool-result';

const TABS = [
  { key: 'dcf', label: 'DCF估值' },
  { key: 'ddm', label: 'DDM估值' },
  { key: 'relative', label: '相对估值' },
  { key: 'scenario', label: '情景DCF' },
] as const;
const DCF_PRESETS = [
  { label: '稳健', discountRate: '0.10', growthRate: '0.05', years: '5' },
  { label: '成长', discountRate: '0.09', growthRate: '0.07', years: '7' },
  { label: '保守', discountRate: '0.12', growthRate: '0.03', years: '5' },
] as const;
const DDM_PRESETS = [
  { label: '成熟分红', dividend: '25', growthRate: '0.03', requiredReturn: '0.08' },
  { label: '稳健', dividend: '18', growthRate: '0.02', requiredReturn: '0.09' },
] as const;
const SCENARIO_PRESETS = [
  { label: '消费龙头', baseRevenue: '1300', years: '5', industry: '消费' },
  { label: '制造升级', baseRevenue: '800', years: '6', industry: '制造' },
] as const;

type Tab = (typeof TABS)[number]['key'];

function v(obj: Record<string, unknown>, ...keys: string[]): unknown {
  for (const k of keys) if (obj[k] != null) return obj[k];
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
  const [formError, setFormError] = useState<string | null>(null);

  function applyDcfPreset(preset: typeof DCF_PRESETS[number]) {
    setDiscountRate(preset.discountRate);
    setGrowthRate(preset.growthRate);
    setYears(preset.years);
  }

  function applyDdmPreset(preset: typeof DDM_PRESETS[number]) {
    setDividend(preset.dividend);
    setDdmGrowth(preset.growthRate);
    setRequiredReturn(preset.requiredReturn);
  }

  function applyScenarioPreset(preset: typeof SCENARIO_PRESETS[number]) {
    setBaseRevenue(preset.baseRevenue);
    setYears(preset.years);
    setIndustry(preset.industry);
  }

  function submit() {
    setFormError(null);
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
      if (!baseRevenue) {
        setFormError('情景 DCF 需要先填写基础营收，例如 1300');
        return;
      }
      body.baseRevenue = Number(baseRevenue);
      if (industry) body.industry = industry;
      body.years = Number(years);
    }
    trigger(endpoint, { method: 'POST' }, body);
  }

  function runRecommendedValuation() {
    const nextCode = trimmedCode || resolvedCode || '600519';
    setCode(nextCode);
    setFormError(null);

    if (tab === 'dcf') {
      const preset = DCF_PRESETS[0];
      applyDcfPreset(preset);
      trigger('/valuation/dcf', { method: 'POST' }, {
        code: nextCode,
        discountRate: Number(preset.discountRate),
        growthRate: Number(preset.growthRate),
        years: Number(preset.years),
      });
      return;
    }

    if (tab === 'ddm') {
      const preset = DDM_PRESETS[0];
      applyDdmPreset(preset);
      trigger('/valuation/ddm', { method: 'POST' }, {
        code: nextCode,
        dividend: Number(preset.dividend),
        growthRate: Number(preset.growthRate),
        requiredReturn: Number(preset.requiredReturn),
      });
      return;
    }

    if (tab === 'relative') {
      trigger('/valuation/relative', { method: 'POST' }, { code: nextCode });
      return;
    }

    const preset = SCENARIO_PRESETS[0];
    applyScenarioPreset(preset);
    trigger('/valuation/scenario-dcf', { method: 'POST' }, {
      code: nextCode,
      baseRevenue: Number(preset.baseRevenue),
      years: Number(preset.years),
      industry: preset.industry,
    });
  }

  const result = useMemo(() => (data ? unwrapToolPayload(data) : null), [data]);
  const mcpErr = data ? extractToolError(data) : null;
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
        <StockCodeInput id="valuation-stock-code" label="股票代码" value={code} onChange={setCode} error={codeError} />
      </div>
      <p className="mb-3 text-sm text-text-secondary">先确定标的，再根据公司特点选择模型：成熟分红公司更适合 DDM，成长型公司更适合 DCF 或情景 DCF。</p>
      {resolvedCode ? (
        <div className="mb-3 flex gap-2 flex-wrap">
          <Link href={`/stock?code=${encodeURIComponent(resolvedCode)}`} className="rounded-full border border-glass-border px-3 py-1 text-xs text-text-secondary no-underline">
            返回个股详情
          </Link>
          <button
            type="button"
            onClick={() => setTab('relative')}
            className="rounded-full border border-glass-border px-3 py-1 text-xs text-text-secondary cursor-pointer"
          >
            快速看同行估值
          </button>
          <Link href={`/fundamental?code=${encodeURIComponent(resolvedCode)}`} className="rounded-full border border-glass-border px-3 py-1 text-xs text-text-secondary no-underline">
            联动基本面
          </Link>
        </div>
      ) : null}
      <TabBar tabs={TABS} active={tab} onChange={(key) => { setTab(key); reset(); setFormError(null); }} />
      <SectionCard tabAttached>
        {tab === 'dcf' ? (
          <div className="space-y-3">
            <div className="flex gap-2 flex-wrap items-center">
              <label className="text-sm">折现率 <input value={discountRate} onChange={(e) => setDiscountRate(e.target.value)} className={`w-[80px] ${inputCls}`} /></label>
              <label className="text-sm">增长率 <input value={growthRate} onChange={(e) => setGrowthRate(e.target.value)} className={`w-[80px] ${inputCls}`} /></label>
              <label className="text-sm">年数 <input value={years} onChange={(e) => setYears(e.target.value)} className={`w-[60px] ${inputCls}`} /></label>
              <button type="button" disabled={isPending} onClick={submit} className={btnCls}>计算DCF</button>
            </div>
            <div className="flex gap-2 flex-wrap items-center text-xs text-text-secondary">
              <span>推荐参数：</span>
              {DCF_PRESETS.map((preset) => (
                <button key={preset.label} type="button" onClick={() => applyDcfPreset(preset)} className="rounded-full border border-glass-border px-3 py-1">
                  {preset.label}
                </button>
              ))}
            </div>
          </div>
        ) : null}
        {tab === 'ddm' ? (
          <div className="space-y-3">
            <div className="flex gap-2 flex-wrap items-center">
              <label className="text-sm">股息 <input value={dividend} onChange={(e) => setDividend(e.target.value)} className={`w-[80px] ${inputCls}`} placeholder="可选" /></label>
              <label className="text-sm">增长率 <input value={ddmGrowth} onChange={(e) => setDdmGrowth(e.target.value)} className={`w-[80px] ${inputCls}`} /></label>
              <label className="text-sm">要求回报率 <input value={requiredReturn} onChange={(e) => setRequiredReturn(e.target.value)} className={`w-[80px] ${inputCls}`} /></label>
              <button type="button" disabled={isPending} onClick={submit} className={btnCls}>计算DDM</button>
            </div>
            <div className="flex gap-2 flex-wrap items-center text-xs text-text-secondary">
              <span>适合稳定分红公司：</span>
              {DDM_PRESETS.map((preset) => (
                <button key={preset.label} type="button" onClick={() => applyDdmPreset(preset)} className="rounded-full border border-glass-border px-3 py-1">
                  {preset.label}
                </button>
              ))}
            </div>
          </div>
        ) : null}
        {tab === 'relative' ? (
          <div>
            <p className="mb-3 text-sm text-text-secondary">相对估值适合先看同业横向比较，确认目标股票当前处在行业估值的高位还是低位。</p>
            <button type="button" disabled={isPending} onClick={submit} className={btnCls}>查询相对估值</button>
          </div>
        ) : null}
        {tab === 'scenario' ? (
          <div className="space-y-3">
            <div className="flex gap-2 flex-wrap items-center">
              <label className="text-sm">基础营收 <input value={baseRevenue} onChange={(e) => setBaseRevenue(e.target.value)} className={`w-[100px] ${inputCls}`} placeholder="必填，如 1300亿" /></label>
              <label className="text-sm">行业 <input value={industry} onChange={(e) => setIndustry(e.target.value)} className={`w-[100px] ${inputCls}`} placeholder="可选" /></label>
              <label className="text-sm">年数 <input value={years} onChange={(e) => setYears(e.target.value)} className={`w-[60px] ${inputCls}`} /></label>
              <button type="button" disabled={isPending} onClick={submit} className={btnCls}>情景分析</button>
            </div>
            <div className="flex gap-2 flex-wrap items-center text-xs text-text-secondary">
              <span>快速填充：</span>
              {SCENARIO_PRESETS.map((preset) => (
                <button key={preset.label} type="button" onClick={() => applyScenarioPreset(preset)} className="rounded-full border border-glass-border px-3 py-1">
                  {preset.label}
                </button>
              ))}
            </div>
          </div>
        ) : null}
        {isPending ? <LoadingState text="计算中..." /> : null}
        {formError || error || friendlyErr ? <ErrorState text={formError || error || friendlyErr!} hint="请检查参数后重试" /> : null}
        {!isPending && !data && !error && !formError ? (
          <EmptyState
            text={tab === 'dcf' ? '先设置现金流假设，再估算企业内在价值' : tab === 'ddm' ? '先填写分红假设，再估算每股价值' : tab === 'relative' ? '先查询同业估值对比，快速判断目标股票高估还是低估' : '先填写基础营收，再比较不同增长情景下的价值区间'}
            hint={tab === 'dcf' ? '推荐从折现率 10%、增长率 5%、5 年的稳健参数开始。' : tab === 'ddm' ? 'DDM 更适合稳定分红公司，推荐先从成熟分红模板开始。' : tab === 'relative' ? '相对估值是最快的入门方式，适合第一次进入页面时先做横向判断。' : '情景 DCF 适合不确定性较高的成长公司，先给一个基础营收就能看乐观/基准/悲观差异。'}
            action={
              <>
                <button type="button" onClick={runRecommendedValuation} className="rounded-full border border-primary px-3 py-1 text-xs text-primary">使用推荐参数</button>
                {resolvedCode ? <Link href={`/stock?code=${encodeURIComponent(resolvedCode)}`} className="rounded-full border border-glass-border px-3 py-1 text-xs text-text-secondary no-underline">回个股详情</Link> : null}
              </>
            }
          />
        ) : null}
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
                {resolvedCode ? (
                  <div className="flex gap-2 flex-wrap">
                    <Link href={`/stock?code=${encodeURIComponent(resolvedCode)}`} className="rounded-full border border-glass-border px-3 py-1 text-xs text-text-secondary no-underline">
                      返回个股详情
                    </Link>
                    <Link href={`/fundamental?code=${encodeURIComponent(resolvedCode)}`} className="rounded-full border border-glass-border px-3 py-1 text-xs text-text-secondary no-underline">
                      去基本面对比
                    </Link>
                  </div>
                ) : null}
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
