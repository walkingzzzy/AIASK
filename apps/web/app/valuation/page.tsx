'use client';

import { useMemo, useState } from 'react';
import Link from 'next/link';
import {
  PageContainer,
  TabBar,
  SectionCard,
  StockCodeInput,
  KpiGrid,
  KpiCard,
  DataTable,
  Badge,
} from '@/components/ui';
import { useApiMutation } from '@/hooks/use-api-mutation';
import { useStockCode } from '@/hooks/use-stock-code';
import { LoadingState, ErrorState, EmptyState } from '@/components/status-state';
import { BarChart, COLORS } from '@/components/charts';
import { extractArray, fmtAmount, fmtNum, fmtPct } from '@/lib/data-utils';
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

const HERO_PRIMARY_BUTTON_CLS =
  'inline-flex cursor-pointer items-center justify-center rounded-full bg-primary px-4 py-2 text-sm font-medium text-white shadow-[0_20px_40px_-24px_rgba(11,107,203,0.52)] transition hover:-translate-y-0.5 hover:shadow-[0_24px_46px_-24px_rgba(11,107,203,0.58)] disabled:cursor-not-allowed disabled:opacity-50';
const HERO_SECONDARY_BUTTON_CLS =
  'action-chip cursor-pointer text-sm text-text-primary shadow-[0_16px_32px_-24px_rgba(15,23,42,0.28)]';
const CHIP_BUTTON_CLS = 'action-chip cursor-pointer text-xs text-text-primary';
const NOTE_CARD_CLS = 'metric-tile rounded-[22px] p-3 text-xs text-text-secondary';
const SIDE_PANEL_CLS = 'panel-soft rounded-[28px] p-4 sm:p-5';
const FIELD_CLS =
  'h-11 rounded-[20px] border border-white/65 bg-white/55 px-4 text-sm text-text-primary shadow-[inset_0_1px_0_rgba(255,255,255,0.75)] outline-none transition placeholder:text-text-muted focus:border-primary/45 focus:bg-white/72';

type Tab = (typeof TABS)[number]['key'];

function v(obj: Record<string, unknown>, ...keys: string[]): unknown {
  for (const k of keys) {
    if (obj[k] != null) return obj[k];
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
  const [formError, setFormError] = useState<string | null>(null);

  function applyDcfPreset(preset: (typeof DCF_PRESETS)[number]) {
    setDiscountRate(preset.discountRate);
    setGrowthRate(preset.growthRate);
    setYears(preset.years);
  }

  function applyDdmPreset(preset: (typeof DDM_PRESETS)[number]) {
    setDividend(preset.dividend);
    setDdmGrowth(preset.growthRate);
    setRequiredReturn(preset.requiredReturn);
  }

  function applyScenarioPreset(preset: (typeof SCENARIO_PRESETS)[number]) {
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
      body = {
        ...body,
        discountRate: Number(discountRate),
        growthRate: Number(growthRate),
        years: Number(years),
      };
    } else if (tab === 'ddm') {
      endpoint = '/valuation/ddm';
      body = {
        ...body,
        growthRate: Number(ddmGrowth),
        requiredReturn: Number(requiredReturn),
      };
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
      trigger(
        '/valuation/dcf',
        { method: 'POST' },
        {
          code: nextCode,
          discountRate: Number(preset.discountRate),
          growthRate: Number(preset.growthRate),
          years: Number(preset.years),
        },
      );
      return;
    }

    if (tab === 'ddm') {
      const preset = DDM_PRESETS[0];
      applyDdmPreset(preset);
      trigger(
        '/valuation/ddm',
        { method: 'POST' },
        {
          code: nextCode,
          dividend: Number(preset.dividend),
          growthRate: Number(preset.growthRate),
          requiredReturn: Number(preset.requiredReturn),
        },
      );
      return;
    }

    if (tab === 'relative') {
      trigger('/valuation/relative', { method: 'POST' }, { code: nextCode });
      return;
    }

    const preset = SCENARIO_PRESETS[0];
    applyScenarioPreset(preset);
    trigger(
      '/valuation/scenario-dcf',
      { method: 'POST' },
      {
        code: nextCode,
        baseRevenue: Number(preset.baseRevenue),
        years: Number(preset.years),
        industry: preset.industry,
      },
    );
  }

  const result = useMemo(() => (data ? unwrapToolPayload(data) : null), [data]);
  const mcpErr = data ? extractToolError(data) : null;
  const friendlyErr = mcpErr
    ? /No valid valuation metrics/i.test(mcpErr)
      ? `该股票(${trimmedCode})暂无有效估值指标数据`
      : mcpErr
    : null;
  const relativeRows = useMemo(
    () => (result && tab === 'relative' ? extractArray(result, 'comparisons', 'peers', 'results') : []),
    [result, tab],
  );
  const scenarioRows = useMemo(
    () => (result && tab === 'scenario' ? extractArray(result, 'scenarios', 'results') : []),
    [result, tab],
  );
  const activeTabLabel = TABS.find((item) => item.key === tab)?.label ?? '估值模型';
  const focusCode = resolvedCode || trimmedCode;
  const currentAssumptionSummary =
    tab === 'dcf'
      ? `折现率 ${discountRate}，增长率 ${growthRate}，预测 ${years} 年`
      : tab === 'ddm'
        ? `股息 ${dividend || '自动估算'}，增长率 ${ddmGrowth}，要求回报率 ${requiredReturn}`
        : tab === 'relative'
          ? '同业横向比较，先判断高估还是低估'
          : `基础营收 ${baseRevenue || '待填写'}，行业 ${industry || '未指定'}，预测 ${years} 年`;
  const tabDescription =
    tab === 'dcf'
      ? '适合现金流可预测、业务进入稳定扩张期的公司。'
      : tab === 'ddm'
        ? '适合分红稳定、资本开支波动较小的成熟公司。'
        : tab === 'relative'
          ? '适合快速建立行业位置感，尤其适合第一次进入页面时先做横向判断。'
          : '适合不确定性较高的成长公司，用乐观、基准、悲观三种假设看价值区间。';
  const recommendedAudience =
    tab === 'dcf'
      ? '成长型龙头、现金流稳定的经营模型'
      : tab === 'ddm'
        ? '高分红、公用事业、消费龙头等成熟公司'
        : tab === 'relative'
          ? '需要快速比同行估值水平时优先使用'
          : '高波动成长公司或行业假设分歧较大时更有价值';

  return (
    <PageContainer>
      <section className="page-hero mb-4 p-5 sm:p-6">
        <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_clamp(280px,25vw,380px)]">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="info">Valuation Workbench</Badge>
              <Badge variant={focusCode ? 'success' : 'warning'}>
                {focusCode ? `当前标的 ${focusCode}` : '等待确认标的'}
              </Badge>
              <Badge variant="neutral">{activeTabLabel}</Badge>
              <Badge variant={data ? 'success' : isPending ? 'warning' : 'neutral'}>
                {data ? '已生成估值结果' : isPending ? '模型计算中' : '等待运行'}
              </Badge>
            </div>
            <h1 className="mb-0 mt-4 text-[2rem] font-semibold tracking-[-0.03em] text-text-primary sm:text-[2.4rem]">
              估值分析工作台
            </h1>
            <p className="mb-0 mt-3 max-w-3xl text-sm leading-7 text-text-secondary sm:text-[15px]">
              先确定标的，再根据公司特点选择模型。成熟分红公司更适合 DDM，成长型公司更适合 DCF 或情景 DCF；
              如果只是想快速判断位置，先用相对估值建立行业坐标会更高效。
            </p>
            <div className="mt-5 flex flex-wrap gap-2">
              <button type="button" onClick={runRecommendedValuation} className={HERO_PRIMARY_BUTTON_CLS}>
                使用推荐参数
              </button>
              <button
                type="button"
                onClick={() => {
                  setTab('relative');
                  reset();
                  setFormError(null);
                }}
                className={HERO_SECONDARY_BUTTON_CLS}
              >
                快速看同行估值
              </button>
              {resolvedCode ? (
                <Link
                  href={`/fundamental?code=${encodeURIComponent(resolvedCode)}`}
                  className={`${HERO_SECONDARY_BUTTON_CLS} no-underline text-inherit`}
                >
                  联动基本面
                </Link>
              ) : null}
            </div>

            <div className="mt-5 grid gap-3 sm:grid-cols-4">
              <div className="rounded-[24px] border border-white/45 bg-white/38 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.55)]">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">当前标的</div>
                <div className="mt-3 text-2xl font-semibold text-text-primary">{focusCode || '-'}</div>
                <div className="mt-1 text-xs text-text-secondary">模型会基于当前代码发起估值计算</div>
              </div>
              <div className="rounded-[24px] border border-white/45 bg-white/30 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.48)]">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">当前模型</div>
                <div className="mt-3 text-2xl font-semibold text-text-primary">{activeTabLabel}</div>
                <div className="mt-1 text-xs text-text-secondary">{tabDescription}</div>
              </div>
              <div className="rounded-[24px] border border-white/45 bg-white/26 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.42)]">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">当前假设</div>
                <div className="mt-3 text-sm font-semibold leading-6 text-text-primary">{currentAssumptionSummary}</div>
              </div>
              <div className="rounded-[24px] border border-white/45 bg-white/24 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.38)]">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">推荐场景</div>
                <div className="mt-3 text-sm font-semibold leading-6 text-text-primary">{recommendedAudience}</div>
              </div>
            </div>
          </div>

          <div className="grid gap-3">
            <div className={SIDE_PANEL_CLS}>
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">
                当前估值上下文
              </div>
              <div className="mt-3 text-base font-semibold text-text-primary">{focusCode || '未选择标的'}</div>
              {resolvedCode ? (
                <div className="mt-3 flex items-center gap-2">
                  <StockLink code={resolvedCode} name={resolvedCode} />
                  <WatchlistButton code={resolvedCode} name="" />
                </div>
              ) : null}
              <div className="mt-4 space-y-3">
                <div className={NOTE_CARD_CLS}>
                  当前模型：<span className="font-medium text-text-primary">{activeTabLabel}</span>
                </div>
                <div className={NOTE_CARD_CLS}>
                  假设摘要：<span className="font-medium text-text-primary">{currentAssumptionSummary}</span>
                </div>
                <div className={NOTE_CARD_CLS}>
                  结果状态：
                  <span className="font-medium text-text-primary">
                    {data ? '已生成' : isPending ? '计算中' : '待执行'}
                  </span>
                </div>
              </div>
            </div>

            <div className={SIDE_PANEL_CLS}>
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">使用建议</div>
              <div className="mt-4 space-y-3">
                <div className={NOTE_CARD_CLS}>1. 先用推荐模板建立第一版估值，再手动细调关键假设。</div>
                <div className={NOTE_CARD_CLS}>2. 如果对现金流没把握，先切相对估值建立行业位置感。</div>
                <div className={NOTE_CARD_CLS}>3. 情景 DCF 更适合在高不确定性阶段比较上下行空间。</div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <div className="panel-soft rounded-[28px] p-4 sm:p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="eyebrow">Model Setup</div>
            <h2 className="mb-0 mt-2 text-xl font-semibold text-text-primary">模型配置</h2>
            <p className="mb-0 mt-2 text-sm leading-7 text-text-secondary">
              统一在这里切换模型、调整参数并发起计算。配置区负责收集假设，结果区负责比较输出，不把两类任务混在一屏里。
            </p>
          </div>
          {resolvedCode ? (
            <Link
              href={`/stock?code=${encodeURIComponent(resolvedCode)}`}
              className={`${HERO_SECONDARY_BUTTON_CLS} no-underline text-inherit`}
            >
              返回个股详情
            </Link>
          ) : null}
        </div>

        <div className="mt-4">
          <TabBar
            tabs={TABS}
            active={tab}
            onChange={(key) => {
              setTab(key);
              reset();
              setFormError(null);
            }}
          />
        </div>

        <SectionCard tabAttached>
          <div className="grid gap-4 xl:grid-cols-[260px_minmax(0,1fr)]">
            <StockCodeInput
              id="valuation-stock-code"
              label="股票代码"
              value={code}
              onChange={setCode}
              error={codeError}
            />
            <div className="metric-tile rounded-[24px] p-4 text-sm text-text-secondary">
              <div className="font-medium text-text-primary">{activeTabLabel}</div>
              <div className="mt-2 leading-7">{tabDescription}</div>
            </div>
          </div>

          {tab === 'dcf' ? (
            <div className="mt-4 space-y-4">
              <div className="grid gap-4 xl:grid-cols-[repeat(3,minmax(0,160px))_auto] xl:items-end">
                <label className="grid gap-2 text-xs text-text-secondary">
                  <span className="font-medium uppercase tracking-[0.12em] text-text-muted">折现率</span>
                  <input value={discountRate} onChange={(e) => setDiscountRate(e.target.value)} className={FIELD_CLS} />
                </label>
                <label className="grid gap-2 text-xs text-text-secondary">
                  <span className="font-medium uppercase tracking-[0.12em] text-text-muted">增长率</span>
                  <input value={growthRate} onChange={(e) => setGrowthRate(e.target.value)} className={FIELD_CLS} />
                </label>
                <label className="grid gap-2 text-xs text-text-secondary">
                  <span className="font-medium uppercase tracking-[0.12em] text-text-muted">预测年数</span>
                  <input value={years} onChange={(e) => setYears(e.target.value)} className={FIELD_CLS} />
                </label>
                <button type="button" disabled={isPending} onClick={submit} className={HERO_PRIMARY_BUTTON_CLS}>
                  计算 DCF
                </button>
              </div>
              <div className="flex flex-wrap gap-2">
                {DCF_PRESETS.map((preset) => (
                  <button
                    key={preset.label}
                    type="button"
                    onClick={() => applyDcfPreset(preset)}
                    className={CHIP_BUTTON_CLS}
                  >
                    {preset.label}
                  </button>
                ))}
              </div>
            </div>
          ) : null}

          {tab === 'ddm' ? (
            <div className="mt-4 space-y-4">
              <div className="grid gap-4 xl:grid-cols-[repeat(3,minmax(0,160px))_auto] xl:items-end">
                <label className="grid gap-2 text-xs text-text-secondary">
                  <span className="font-medium uppercase tracking-[0.12em] text-text-muted">股息</span>
                  <input
                    value={dividend}
                    onChange={(e) => setDividend(e.target.value)}
                    className={FIELD_CLS}
                    placeholder="可选"
                  />
                </label>
                <label className="grid gap-2 text-xs text-text-secondary">
                  <span className="font-medium uppercase tracking-[0.12em] text-text-muted">增长率</span>
                  <input value={ddmGrowth} onChange={(e) => setDdmGrowth(e.target.value)} className={FIELD_CLS} />
                </label>
                <label className="grid gap-2 text-xs text-text-secondary">
                  <span className="font-medium uppercase tracking-[0.12em] text-text-muted">要求回报率</span>
                  <input
                    value={requiredReturn}
                    onChange={(e) => setRequiredReturn(e.target.value)}
                    className={FIELD_CLS}
                  />
                </label>
                <button type="button" disabled={isPending} onClick={submit} className={HERO_PRIMARY_BUTTON_CLS}>
                  计算 DDM
                </button>
              </div>
              <div className="flex flex-wrap gap-2">
                {DDM_PRESETS.map((preset) => (
                  <button
                    key={preset.label}
                    type="button"
                    onClick={() => applyDdmPreset(preset)}
                    className={CHIP_BUTTON_CLS}
                  >
                    {preset.label}
                  </button>
                ))}
              </div>
            </div>
          ) : null}

          {tab === 'relative' ? (
            <div className="mt-4">
              <p className="mb-3 text-sm text-text-secondary">
                相对估值适合先看同业横向比较，确认目标股票当前处在行业估值的高位还是低位。
              </p>
              <button type="button" disabled={isPending} onClick={submit} className={HERO_PRIMARY_BUTTON_CLS}>
                查询相对估值
              </button>
            </div>
          ) : null}

          {tab === 'scenario' ? (
            <div className="mt-4 space-y-4">
              <div className="grid gap-4 xl:grid-cols-[repeat(3,minmax(0,180px))_auto] xl:items-end">
                <label className="grid gap-2 text-xs text-text-secondary">
                  <span className="font-medium uppercase tracking-[0.12em] text-text-muted">基础营收</span>
                  <input
                    value={baseRevenue}
                    onChange={(e) => setBaseRevenue(e.target.value)}
                    className={FIELD_CLS}
                    placeholder="必填，如 1300 亿"
                  />
                </label>
                <label className="grid gap-2 text-xs text-text-secondary">
                  <span className="font-medium uppercase tracking-[0.12em] text-text-muted">行业</span>
                  <input
                    value={industry}
                    onChange={(e) => setIndustry(e.target.value)}
                    className={FIELD_CLS}
                    placeholder="可选"
                  />
                </label>
                <label className="grid gap-2 text-xs text-text-secondary">
                  <span className="font-medium uppercase tracking-[0.12em] text-text-muted">预测年数</span>
                  <input value={years} onChange={(e) => setYears(e.target.value)} className={FIELD_CLS} />
                </label>
                <button type="button" disabled={isPending} onClick={submit} className={HERO_PRIMARY_BUTTON_CLS}>
                  情景分析
                </button>
              </div>
              <div className="flex flex-wrap gap-2">
                {SCENARIO_PRESETS.map((preset) => (
                  <button
                    key={preset.label}
                    type="button"
                    onClick={() => applyScenarioPreset(preset)}
                    className={CHIP_BUTTON_CLS}
                  >
                    {preset.label}
                  </button>
                ))}
              </div>
            </div>
          ) : null}
        </SectionCard>
      </div>

      <div className="panel-soft mt-4 rounded-[28px] p-4 sm:p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="eyebrow">Result View</div>
            <h2 className="mb-0 mt-2 text-xl font-semibold text-text-primary">估值结果</h2>
            <p className="mb-0 mt-2 text-sm leading-7 text-text-secondary">
              结果区负责显示计算结论和同行对比，建议先看核心数值，再决定是否继续回到配置区调参。
            </p>
          </div>
          <div className="metric-tile rounded-[22px] px-4 py-3 text-sm text-text-secondary">
            当前模型：<span className="font-medium text-text-primary">{activeTabLabel}</span>
          </div>
        </div>

        {isPending ? <LoadingState text="计算中..." /> : null}
        {formError || error || friendlyErr ? (
          <ErrorState text={formError || error || friendlyErr!} hint="请检查参数后重试" />
        ) : null}

        {!isPending && !data && !error && !formError ? (
          <EmptyState
            text={
              tab === 'dcf'
                ? '先设置现金流假设，再估算企业内在价值'
                : tab === 'ddm'
                  ? '先填写分红假设，再估算每股价值'
                  : tab === 'relative'
                    ? '先查询同业估值对比，快速判断目标股票高估还是低估'
                    : '先填写基础营收，再比较不同增长情景下的价值区间'
            }
            hint={
              tab === 'dcf'
                ? '推荐从折现率 10%、增长率 5%、5 年的稳健参数开始。'
                : tab === 'ddm'
                  ? 'DDM 更适合稳定分红公司，推荐先从成熟分红模板开始。'
                  : tab === 'relative'
                    ? '相对估值是最快的入门方式，适合第一次进入页面时先做横向判断。'
                    : '情景 DCF 适合不确定性较高的成长公司，先给一个基础营收就能看乐观/基准/悲观差异。'
            }
            action={
              <>
                <button type="button" onClick={runRecommendedValuation} className={CHIP_BUTTON_CLS}>
                  使用推荐参数
                </button>
                {resolvedCode ? (
                  <Link
                    href={`/stock?code=${encodeURIComponent(resolvedCode)}`}
                    className={`${CHIP_BUTTON_CLS} no-underline text-inherit`}
                  >
                    回个股详情
                  </Link>
                ) : null}
              </>
            }
          />
        ) : null}

        {data != null && !friendlyErr && tab === 'dcf' && result
          ? (() => {
              const r = result as Record<string, unknown>;
              const intrinsic = Number(v(r, 'intrinsic_value', 'intrinsicValue', 'value') ?? 0);
              const pvSum = Number(v(r, 'pv_sum', 'pvSum') ?? 0);
              const pvTerminal = Number(v(r, 'pv_terminal', 'pvTerminal') ?? 0);
              const terminalValue = Number(v(r, 'terminal_value', 'terminalValue') ?? 0);
              const model = String(v(r, 'model') ?? '');
              const wacc = r.wacc_breakdown as Record<string, unknown> | undefined;
              const cfs = (r.cash_flows ?? r.cashFlows ?? r.projected_cash_flows ?? r.projection ?? []) as Record<
                string,
                unknown
              >[];

              return (
                <div className="mt-4 space-y-4">
                  <KpiGrid cols={4}>
                    <KpiCard title="内在价值(总)" value={fmtAmount(intrinsic)} />
                    <KpiCard title="现金流现值" value={fmtAmount(pvSum)} />
                    <KpiCard title="终值现值" value={fmtAmount(pvTerminal)} />
                    <KpiCard title="终值" value={fmtAmount(terminalValue)} />
                  </KpiGrid>
                  {model ? <div className="text-xs text-text-secondary">模型: {model}</div> : null}
                  {wacc ? (
                    <div className="flex flex-wrap gap-x-4 gap-y-2 text-xs text-text-secondary">
                      <span>WACC: {fmtPct(Number(wacc.wacc ?? 0) * 100)}</span>
                      <span>权益成本: {fmtPct(Number(wacc.cost_of_equity ?? 0) * 100)}</span>
                      <span>债务成本(税后): {fmtPct(Number(wacc.cost_of_debt_after_tax ?? 0) * 100)}</span>
                    </div>
                  ) : null}
                  {Array.isArray(cfs) && cfs.length > 0 ? (
                    <BarChart
                      items={cfs.map((cf, index) => ({
                        label: String(cf.year ?? cf.period ?? `Y${index + 1}`),
                        value: Number(cf.pv_fcf ?? cf.fcf ?? cf.value ?? cf.cash_flow ?? 0),
                        color: COLORS.primary,
                      }))}
                      yAxisName="现金流"
                    />
                  ) : null}
                  {r.assumptions ? (
                    <div className="metric-tile rounded-[22px] p-3 text-xs text-text-secondary">
                      假设: {JSON.stringify(r.assumptions)}
                    </div>
                  ) : null}
                </div>
              );
            })()
          : null}

        {data != null && !friendlyErr && tab === 'ddm' && result
          ? (() => {
              const r = result as Record<string, unknown>;
              const intrinsic = Number(v(r, 'intrinsic_value', 'intrinsicValue', 'value') ?? 0);
              const curDiv = Number(v(r, 'current_dividend', 'currentDividend') ?? 0);
              const nextDiv = Number(v(r, 'next_dividend', 'nextDividend') ?? 0);
              const model = String(v(r, 'model') ?? '');

              return (
                <div className="mt-4">
                  <KpiGrid cols={3}>
                    <KpiCard title="内在价值" value={fmtNum(intrinsic, 2)} suffix="元/股" />
                    <KpiCard title="当前股息" value={fmtNum(curDiv, 2)} suffix="元" />
                    <KpiCard title="预期下期股息" value={fmtNum(nextDiv, 2)} suffix="元" />
                  </KpiGrid>
                  {model ? <div className="mt-2 text-xs text-text-secondary">模型: {model}</div> : null}
                </div>
              );
            })()
          : null}

        {data != null && !friendlyErr && tab === 'relative' ? (
          <div className="mt-4 space-y-4">
            {relativeRows.length > 0 ? (
              <>
                <DataTable
                  rows={relativeRows as Record<string, unknown>[]}
                  columns={[
                    { key: 'name', label: '名称' },
                    { key: 'code', label: '代码' },
                    { key: 'pe', label: 'PE', align: 'right' as const, render: (value) => fmtNum(Number(value), 2) },
                    { key: 'pb', label: 'PB', align: 'right' as const, render: (value) => fmtNum(Number(value), 2) },
                    { key: 'ps', label: 'PS', align: 'right' as const, render: (value) => fmtNum(Number(value), 2) },
                    { key: 'peg', label: 'PEG', align: 'right' as const, render: (value) => fmtNum(Number(value), 2) },
                    {
                      key: 'dividend_yield',
                      label: '股息率',
                      align: 'right' as const,
                      render: (value) => fmtPct(Number(value)),
                    },
                  ]}
                  onExport={() => exportCSV(relativeRows as Record<string, unknown>[], '相对估值')}
                />
                <BarChart
                  items={relativeRows.slice(0, 10).map((row) => {
                    const item = row as Record<string, unknown>;
                    return {
                      label: String(item.name ?? item.code ?? ''),
                      value: Number(item.pe ?? 0),
                      color: COLORS.primary,
                    };
                  })}
                  yAxisName="PE"
                  horizontal
                />
                {resolvedCode ? (
                  <div className="flex flex-wrap gap-2">
                    <Link
                      href={`/stock?code=${encodeURIComponent(resolvedCode)}`}
                      className={`${CHIP_BUTTON_CLS} no-underline text-inherit`}
                    >
                      返回个股详情
                    </Link>
                    <Link
                      href={`/fundamental?code=${encodeURIComponent(resolvedCode)}`}
                      className={`${CHIP_BUTTON_CLS} no-underline text-inherit`}
                    >
                      去基本面对比
                    </Link>
                  </div>
                ) : null}
              </>
            ) : result ? (
              <DataTable rows={[result as Record<string, unknown>]} />
            ) : null}
          </div>
        ) : null}

        {data != null && !friendlyErr && tab === 'scenario'
          ? (() => {
              const scenarios =
                scenarioRows.length > 0
                  ? scenarioRows
                  : (() => {
                      if (!result) return [];
                      const r = result as Record<string, unknown>;
                      return ['optimistic', 'base', 'pessimistic']
                        .filter((key) => r[key] != null)
                        .map((key) => ({ scenario: key, ...(r[key] as Record<string, unknown>) }));
                    })();
              const badgeVariant = (label: string) =>
                /optim/i.test(label)
                  ? ('success' as const)
                  : /pessim/i.test(label)
                    ? ('danger' as const)
                    : ('warning' as const);

              return (
                <div className="mt-4 space-y-4">
                  {scenarios.length > 0 ? (
                    <>
                      <KpiGrid cols={3}>
                        {(scenarios as Record<string, unknown>[]).map((scenario, index) => {
                          const label = String(
                            scenario.scenario ?? scenario.name ?? scenario.label ?? `情景${index + 1}`,
                          );
                          const value = Number(
                            scenario.intrinsic_value ?? scenario.intrinsicValue ?? scenario.value ?? 0,
                          );
                          const upside = Number(scenario.upside ?? scenario.upside_pct ?? 0);
                          return (
                            <KpiCard
                              key={label}
                              title={
                                (
                                  <>
                                    <Badge variant={badgeVariant(label)}>{label}</Badge>
                                  </>
                                ) as unknown as string
                              }
                              value={fmtNum(value, 2)}
                              suffix="元"
                              change={upside || null}
                            />
                          );
                        })}
                      </KpiGrid>
                      <BarChart
                        items={(scenarios as Record<string, unknown>[]).map((scenario, index) => ({
                          label: String(scenario.scenario ?? scenario.name ?? `情景${index + 1}`),
                          value: Number(scenario.intrinsic_value ?? scenario.intrinsicValue ?? scenario.value ?? 0),
                          color: [COLORS.success, COLORS.warning, COLORS.danger][index] ?? COLORS.primary,
                        }))}
                        yAxisName="内在价值"
                      />
                    </>
                  ) : result ? (
                    <DataTable rows={[result as Record<string, unknown>]} />
                  ) : null}
                </div>
              );
            })()
          : null}
      </div>

      <div className="metric-tile mt-4 rounded-[24px] p-4 text-xs text-text-secondary">
        免责声明：估值模型结果仅供参考，不构成投资建议。模型假设可能与实际情况存在偏差。
      </div>
    </PageContainer>
  );
}
