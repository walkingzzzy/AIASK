'use client';

import { useMemo, useState } from 'react';
import LightOverviewHero from '@/components/light-overview-hero';
import ProgressiveWorkbenchSection from '@/components/progressive-workbench-section';
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
import { usePageActions } from '@/hooks/use-page-actions';
import { usePageContext } from '@/hooks/use-page-context';
import { useMobile } from '@/hooks/use-mobile';
import { useStockCode } from '@/hooks/use-stock-code';
import { LoadingState, ErrorState, EmptyState } from '@/components/status-state';
import { BarChart, COLORS } from '@/components/charts';
import { extractArray, fmtAmount, fmtNum, fmtPct } from '@/lib/data-utils';
import { exportCSV } from '@/lib/export';
import { buildLocalResultContract, defaultWorkbenchTask, evidenceToSummary } from '@/lib/result-workbench';
import { StockLink } from '@/components/stock-link';
import { WatchlistButton } from '@/components/watchlist-button';
import { extractToolError, unwrapToolPayload } from '@/lib/tool-result';
import { RESPONSIVE_BREAKPOINTS } from '@/lib/responsive-layout';

const TABS = [
  { key: 'dcf', label: 'DCF估值' },
  { key: 'ddm', label: 'DDM估值' },
  { key: 'relative', label: '相对估值' },
  { key: 'scenario', label: '情景DCF' },
] as const;
const VIEW_TABS = [
  { key: 'params', label: '参数' },
  { key: 'results', label: '结果' },
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
const FIELD_CLS =
  'h-11 rounded-[20px] border border-white/65 bg-white/55 px-4 text-sm text-text-primary shadow-[inset_0_1px_0_rgba(255,255,255,0.75)] outline-none transition placeholder:text-text-muted focus:border-primary/45 focus:bg-white/72';

type Tab = (typeof TABS)[number]['key'];
type ViewTab = (typeof VIEW_TABS)[number]['key'];

function v(obj: Record<string, unknown>, ...keys: string[]): unknown {
  for (const k of keys) {
    if (obj[k] != null) return obj[k];
  }
  return null;
}

export default function ValuationPage() {
  const compactLayout = useMobile(RESPONSIVE_BREAKPOINTS.splitCollapse);
  const [tab, setTab] = useState<Tab>('dcf');
  const [viewTab, setViewTab] = useState<ViewTab>('params');
  const { code, setCode, codeError, validate, trimmedCode, resolvedCode } = useStockCode();
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
    setViewTab('results');
  }

  function runRecommendedValuation() {
    const nextCode = trimmedCode || resolvedCode || '';
    if (!nextCode) {
      setFormError('请先选择你的关注股票，再运行推荐估值');
      return;
    }
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
      setViewTab('results');
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
      setViewTab('results');
      return;
    }

    if (tab === 'relative') {
      trigger('/valuation/relative', { method: 'POST' }, { code: nextCode });
      setViewTab('results');
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
    setViewTab('results');
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
  const pageActions = [
    {
      id: 'valuation.run-recommended',
      label: '运行推荐估值',
      description: '按当前模型加载推荐参数并发起估值',
      keywords: ['估值', '推荐'],
      scope: 'page' as const,
      pageKey: 'valuation',
      run: () => {
        runRecommendedValuation();
        return { message: '已触发推荐估值' };
      },
    },
    {
      id: 'valuation.submit',
      label: tab === 'relative' ? '查询相对估值' : '提交当前估值',
      description: '按当前参数发起估值请求',
      keywords: ['估值', '提交'],
      scope: 'page' as const,
      pageKey: 'valuation',
      run: () => {
        submit();
        return { message: '已提交当前估值请求' };
      },
    },
    {
      id: 'valuation.open-stock',
      label: '打开个股详情',
      description: '跳到个股详情页继续核对价格与盘口',
      keywords: ['个股详情', '跳转'],
      scope: 'page' as const,
      pageKey: 'valuation',
      run: () => {
        if (!focusCode) {
          setFormError('请先选择你的关注股票，再打开个股详情');
          return { message: '请先选择你的关注股票' };
        }
        window.location.href = `/stock?code=${encodeURIComponent(focusCode)}`;
        return { message: '已跳到个股详情' };
      },
    },
  ];
  usePageActions(pageActions);
  const valuationSummary = `当前模型 ${activeTabLabel}，标的 ${focusCode || '未确认'}，假设 ${currentAssumptionSummary}，视图 ${viewTab === 'params' ? '参数' : '结果'}。`;
  const valuationResult = buildLocalResultContract({
    summary: valuationSummary,
    availableViews: relativeRows.length > 1 || scenarioRows.length > 1 ? ['compare'] : [],
    pageActions,
    preferredActionIds: ['valuation.run-recommended', 'valuation.submit', 'valuation.open-stock'],
    recommendedLinks: [
      { id: 'valuation-open-stock-link', label: focusCode ? '个股详情' : '选择标的', href: focusCode ? `/stock?code=${encodeURIComponent(focusCode)}` : '/watchlist?from=valuation' },
      { id: 'valuation-open-fundamental-link', label: '基本面', href: focusCode ? `/fundamental?code=${encodeURIComponent(focusCode)}` : '/fundamental' },
      { id: 'valuation-open-research-link', label: '研究中心', href: focusCode ? `/research?code=${encodeURIComponent(focusCode)}` : '/research?from=valuation' },
      { id: 'valuation-open-risk-link', label: '风险中心', href: '/risk' },
    ],
    evidence: [
      { label: '当前模型', value: activeTabLabel },
      { label: '标的', value: focusCode || '未确认' },
      { label: '假设摘要', value: currentAssumptionSummary },
      { label: '当前视图', value: viewTab === 'params' ? '参数' : '结果' },
      { label: '状态', value: isPending ? '加载中' : friendlyErr || error ? '需重试' : data ? '已返回' : '待估值' },
    ],
    riskNotes: [formError, friendlyErr, error].filter((item): item is string => Boolean(item)),
    platformMeta: {
      sourceTool: 'valuation',
      sourceChain: ['valuation', tab],
      degraded: Boolean(formError || friendlyErr || error),
      fallbackReason: [formError, friendlyErr, error].filter((item): item is string => Boolean(item)),
    },
    workbenchTask: defaultWorkbenchTask('valuation', `复查${activeTabLabel}`, focusCode ? `/valuation?code=${encodeURIComponent(focusCode)}` : '/valuation', 'valuation-review', {
      code: focusCode || null,
      tab,
      viewTab,
    }),
  });
  usePageContext({
    pageKey: 'valuation',
    title: '估值分析工作台',
    summary: valuationSummary,
    stockCode: focusCode || undefined,
    objectType: 'stock',
    objectId: focusCode || activeTabLabel,
    resultType: `valuation-${tab}`,
    tags: [activeTabLabel, focusCode || '未确认标的', viewTab === 'params' ? '参数视图' : '结果视图'],
    suggestions: [
      `解释 ${activeTabLabel} 结果最该关注的含义`,
      '告诉我下一步该去基本面还是风险页',
      '把当前估值整理成结论和风险提示',
    ],
    recommendedActions: valuationResult.recommendedActions ?? [],
    recommendedLinks: valuationResult.recommendedLinks ?? [],
    evidenceSummary: evidenceToSummary(valuationResult.evidence),
    riskNotes: valuationResult.riskNotes ?? [],
    freshness: valuationResult.freshness ?? null,
    raw: {
      code: focusCode || null,
      tab,
      viewTab,
      hasData: Boolean(data),
    },
  });

  return (
    <PageContainer>
      <LightOverviewHero
        eyebrow="Valuation Workbench"
        title="估值分析工作台"
        summary={compactLayout ? '先选模型，再在参数和结果之间切换。' : '先选模型，再决定是继续调参数还是直接看结果。默认不再把说明、预设、配置和结果同时摊开。'}
        badges={(
          <>
            <Badge variant="info">Valuation Workbench</Badge>
            <Badge variant={focusCode ? 'success' : 'warning'}>
              {focusCode ? `当前标的 ${focusCode}` : '等待确认标的'}
            </Badge>
            <Badge variant="neutral">{activeTabLabel}</Badge>
          </>
        )}
        actions={(
          <>
            <button type="button" onClick={runRecommendedValuation} data-testid="page-primary-action" className={HERO_PRIMARY_BUTTON_CLS}>
              运行推荐估值
            </button>
            <button
              type="button"
              onClick={() => {
                setTab('relative');
                reset();
                setFormError(null);
                setViewTab('params');
              }}
              className={HERO_SECONDARY_BUTTON_CLS}
            >
              快速看同行估值
            </button>
          </>
        )}
        status={(
          <div
            data-testid="page-primary-status"
            className="rounded-[20px] border border-white/50 bg-white/28 px-4 py-3 text-sm shadow-[inset_0_1px_0_rgba(255,255,255,0.68)]"
          >
            <div className="font-medium text-text-primary">
              当前模型：{activeTabLabel} ｜ 标的：{focusCode || '-'} ｜ 当前视图：{viewTab === 'params' ? '参数' : '结果'}
            </div>
            <p className="mt-1 mb-0 text-xs leading-6 text-text-secondary">假设摘要：{currentAssumptionSummary}</p>
          </div>
        )}
        metrics={[
          { key: 'valuation-model', label: '当前模型', value: activeTabLabel },
          { key: 'valuation-stock', label: '当前标的', value: focusCode || '-' },
          { key: 'valuation-view', label: '当前视图', value: viewTab === 'params' ? '参数' : '结果' },
          { key: 'valuation-assumption', label: '假设摘要', value: currentAssumptionSummary },
        ]}
        compact={compactLayout}
        detailsTitle="展开模型假设与适用场景"
        detailsContent={(
          <div className="space-y-3">
            <div className="grid gap-3 sm:grid-cols-2">
              <div className={NOTE_CARD_CLS}>当前模型：{activeTabLabel}</div>
              <div className={NOTE_CARD_CLS}>适用场景：{recommendedAudience}</div>
              <div className={NOTE_CARD_CLS}>{tabDescription}</div>
            </div>
            {resolvedCode ? (
              <div className="flex items-center gap-2">
                <StockLink code={resolvedCode} name={resolvedCode} />
                <WatchlistButton code={resolvedCode} name="" />
              </div>
            ) : null}
          </div>
        )}
      />

      {!compactLayout ? (
        <ProgressiveWorkbenchSection pageKey="valuation" title="估值结果工作台" result={valuationResult} summaryMode="strip" />
      ) : null}

      <div className="panel-soft rounded-[28px] p-4 sm:p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="eyebrow">Valuation Workspace</div>
            <h2 className="mb-0 mt-2 text-xl font-semibold text-text-primary">模型与结果</h2>
            <p className="mb-0 mt-2 text-sm leading-7 text-text-secondary">
              先切模型，再决定当前是调参数还是读结果。这样横屏平板和移动端都不会在默认状态下堆满长内容。
            </p>
          </div>
        </div>

        <div className="mt-4">
          <TabBar
            tabs={TABS}
            active={tab}
            onChange={(key) => {
              setTab(key);
              reset();
              setFormError(null);
              setViewTab('params');
            }}
          />
        </div>

        <div className="mt-4">
          <TabBar tabs={VIEW_TABS} active={viewTab} onChange={(key) => setViewTab(key as ViewTab)} />
        </div>

        <SectionCard tabAttached>
          {viewTab === 'params' ? (
            <>
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
                  <details className="rounded-[22px] border border-glass-border bg-white/35 px-4 py-3">
                    <summary className="cursor-pointer text-sm font-medium text-text-primary">预设与适用场景</summary>
                    <div className="mt-3 flex flex-wrap gap-2">
                      {DCF_PRESETS.map((preset) => (
                        <button key={preset.label} type="button" onClick={() => applyDcfPreset(preset)} className={CHIP_BUTTON_CLS}>
                          {preset.label}
                        </button>
                      ))}
                    </div>
                  </details>
                </div>
              ) : null}

              {tab === 'ddm' ? (
                <div className="mt-4 space-y-4">
                  <div className="grid gap-4 xl:grid-cols-[repeat(3,minmax(0,160px))_auto] xl:items-end">
                    <label className="grid gap-2 text-xs text-text-secondary">
                      <span className="font-medium uppercase tracking-[0.12em] text-text-muted">股息</span>
                      <input value={dividend} onChange={(e) => setDividend(e.target.value)} className={FIELD_CLS} placeholder="可选" />
                    </label>
                    <label className="grid gap-2 text-xs text-text-secondary">
                      <span className="font-medium uppercase tracking-[0.12em] text-text-muted">增长率</span>
                      <input value={ddmGrowth} onChange={(e) => setDdmGrowth(e.target.value)} className={FIELD_CLS} />
                    </label>
                    <label className="grid gap-2 text-xs text-text-secondary">
                      <span className="font-medium uppercase tracking-[0.12em] text-text-muted">要求回报率</span>
                      <input value={requiredReturn} onChange={(e) => setRequiredReturn(e.target.value)} className={FIELD_CLS} />
                    </label>
                    <button type="button" disabled={isPending} onClick={submit} className={HERO_PRIMARY_BUTTON_CLS}>
                      计算 DDM
                    </button>
                  </div>
                  <details className="rounded-[22px] border border-glass-border bg-white/35 px-4 py-3">
                    <summary className="cursor-pointer text-sm font-medium text-text-primary">预设与适用场景</summary>
                    <div className="mt-3 flex flex-wrap gap-2">
                      {DDM_PRESETS.map((preset) => (
                        <button key={preset.label} type="button" onClick={() => applyDdmPreset(preset)} className={CHIP_BUTTON_CLS}>
                          {preset.label}
                        </button>
                      ))}
                    </div>
                  </details>
                </div>
              ) : null}

              {tab === 'relative' ? (
                <div className="mt-4 space-y-4">
                  <p className="mb-0 text-sm text-text-secondary">
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
                      <input value={baseRevenue} onChange={(e) => setBaseRevenue(e.target.value)} className={FIELD_CLS} placeholder="必填，如 1300 亿" />
                    </label>
                    <label className="grid gap-2 text-xs text-text-secondary">
                      <span className="font-medium uppercase tracking-[0.12em] text-text-muted">行业</span>
                      <input value={industry} onChange={(e) => setIndustry(e.target.value)} className={FIELD_CLS} placeholder="可选" />
                    </label>
                    <label className="grid gap-2 text-xs text-text-secondary">
                      <span className="font-medium uppercase tracking-[0.12em] text-text-muted">预测年数</span>
                      <input value={years} onChange={(e) => setYears(e.target.value)} className={FIELD_CLS} />
                    </label>
                    <button type="button" disabled={isPending} onClick={submit} className={HERO_PRIMARY_BUTTON_CLS}>
                      情景分析
                    </button>
                  </div>
                  <details className="rounded-[22px] border border-glass-border bg-white/35 px-4 py-3">
                    <summary className="cursor-pointer text-sm font-medium text-text-primary">预设与适用场景</summary>
                    <div className="mt-3 flex flex-wrap gap-2">
                      {SCENARIO_PRESETS.map((preset) => (
                        <button key={preset.label} type="button" onClick={() => applyScenarioPreset(preset)} className={CHIP_BUTTON_CLS}>
                          {preset.label}
                        </button>
                      ))}
                    </div>
                  </details>
                </div>
              ) : null}
            </>
          ) : null}

          {viewTab === 'results' ? (
            <>
              {isPending ? <LoadingState text="计算中..." /> : null}
              {formError || error || friendlyErr ? <ErrorState text={formError || error || friendlyErr!} hint="请检查参数后重试" /> : null}

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
                  hint={`当前模型：${activeTabLabel}。${recommendedAudience}`}
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
                    const cfs = (r.cash_flows ?? r.cashFlows ?? r.projected_cash_flows ?? r.projection ?? []) as Record<string, unknown>[];

                    return (
                      <div className="space-y-4">
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
                    return (
                      <KpiGrid cols={3}>
                        <KpiCard title="内在价值" value={fmtNum(intrinsic, 2)} suffix="元/股" />
                        <KpiCard title="当前股息" value={fmtNum(curDiv, 2)} suffix="元" />
                        <KpiCard title="预期下期股息" value={fmtNum(nextDiv, 2)} suffix="元" />
                      </KpiGrid>
                    );
                  })()
                : null}

              {data != null && !friendlyErr && tab === 'relative' ? (
                <div className="space-y-4">
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

                    return scenarios.length > 0 ? (
                      <div className="space-y-4">
                        <KpiGrid cols={3}>
                          {(scenarios as Record<string, unknown>[]).map((scenario, index) => {
                            const label = String(scenario.scenario ?? scenario.name ?? scenario.label ?? `情景${index + 1}`);
                            const value = Number(scenario.intrinsic_value ?? scenario.intrinsicValue ?? scenario.value ?? 0);
                            const upside = Number(scenario.upside ?? scenario.upside_pct ?? 0);
                            return <KpiCard key={label} title={label} value={fmtNum(value, 2)} suffix="元" change={upside || null} />;
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
                      </div>
                    ) : result ? (
                      <DataTable rows={[result as Record<string, unknown>]} />
                    ) : null;
                  })()
                : null}
            </>
          ) : null}
        </SectionCard>
      </div>

      {!compactLayout ? (
        <div className="metric-tile mt-4 rounded-[24px] p-4 text-xs text-text-secondary">
          免责声明：估值模型结果仅供参考，不构成投资建议。模型假设可能与实际情况存在偏差。
        </div>
      ) : null}
    </PageContainer>
  );
}
