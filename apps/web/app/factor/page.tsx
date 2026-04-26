'use client';

import { useState } from 'react';
import ResponsiveResultWorkbench from '@/components/responsive-result-workbench';
import { PageContainer, SectionCard, KpiCard, KpiGrid, DataTable, Badge, TabBar } from '@/components/ui';
import { BarChart, LineChart } from '@/components/charts';
import { useApiMutation } from '@/hooks/use-api-mutation';
import { useApiQuery } from '@/hooks/use-api-query';
import { useMobile } from '@/hooks/use-mobile';
import { usePageActions } from '@/hooks/use-page-actions';
import { usePageContext } from '@/hooks/use-page-context';
import { LoadingState, ErrorState, EmptyState } from '@/components/status-state';
import { extractArray, extractObject, fmtNum, fmtPct } from '@/lib/data-utils';
import { exportCSV } from '@/lib/export';
import { buildLocalResultContract, defaultWorkbenchTask, evidenceToSummary } from '@/lib/result-workbench';
import { RESPONSIVE_BREAKPOINTS } from '@/lib/responsive-layout';
import { FactorMiningWorkbench } from './components/factor-mining-workbench';

const DEFAULT_FACTOR_CODES = '600519,000858,300750,601318,000001,600036,601166,000333,600276,601899,002594,000651';
const HERO_PRIMARY_BUTTON_CLS =
  'inline-flex cursor-pointer items-center justify-center rounded-full bg-primary px-4 py-2 text-sm font-medium text-white shadow-[0_20px_40px_-24px_rgba(11,107,203,0.52)] transition hover:-translate-y-0.5 hover:shadow-[0_24px_46px_-24px_rgba(11,107,203,0.58)] disabled:cursor-not-allowed disabled:opacity-50';
const CHIP_LINK_CLS = 'action-chip cursor-pointer border-0 bg-transparent text-xs no-underline text-inherit';
const NOTE_CARD_CLS = 'metric-tile rounded-[22px] p-3 text-xs text-text-secondary';
const SIDE_PANEL_CLS = 'panel-soft rounded-[28px] p-4 sm:p-5';
type FactorStageTab = 'foundation' | 'validation' | 'mining';
type FactorFoundationTab = 'library' | 'calculate' | 'ic';
type FactorValidationTab = 'backtest' | 'oos' | 'robustness';

const FACTOR_STAGE_TABS = [
  { key: 'foundation', label: '基础研究' },
  { key: 'validation', label: '收益验证' },
  { key: 'mining', label: 'AI 挖掘' },
] as const;
const FACTOR_FOUNDATION_TABS = [
  { key: 'library', label: '因子库' },
  { key: 'calculate', label: '因子计算' },
  { key: 'ic', label: 'IC 分析' },
] as const;
const FACTOR_VALIDATION_TABS = [
  { key: 'backtest', label: '因子回测' },
  { key: 'oos', label: '样本外验证' },
  { key: 'robustness', label: '稳健性检验' },
] as const;

function ResearchField({
  id,
  label,
  value,
  onChange,
  placeholder,
  className = '',
}: {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
  className?: string;
}) {
  return (
    <label htmlFor={id} className={`grid gap-1 text-xs text-text-secondary ${className}`}>
      <span>{label}</span>
      <input
        id={id}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="w-full text-sm text-text-primary"
      />
    </label>
  );
}

function FactorRequestFields({
  legend,
  description,
  note,
  nameId,
  nameValue,
  onNameChange,
  codesId,
  codesValue,
  onCodesChange,
  actionLabel,
  actionLoadingLabel,
  loading,
  onSubmit,
}: {
  legend: string;
  description: string;
  note: string;
  nameId: string;
  nameValue: string;
  onNameChange: (value: string) => void;
  codesId: string;
  codesValue: string;
  onCodesChange: (value: string) => void;
  actionLabel: string;
  actionLoadingLabel: string;
  loading: boolean;
  onSubmit: () => void;
}) {
  return (
    <div className="panel-soft rounded-[26px] p-4 sm:p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="eyebrow">{legend}</div>
          <p className="mb-0 mt-2 text-sm leading-7 text-text-secondary">{description}</p>
        </div>
        <button type="button" disabled={loading} onClick={onSubmit} className={HERO_PRIMARY_BUTTON_CLS}>
          {loading ? actionLoadingLabel : actionLabel}
        </button>
      </div>
      <div className="mt-4 grid gap-3 lg:grid-cols-[180px_minmax(0,1fr)]">
        <ResearchField
          id={nameId}
          label="因子名称"
          value={nameValue}
          onChange={onNameChange}
          placeholder="例如 momentum"
        />
        <ResearchField
          id={codesId}
          label="股票池"
          value={codesValue}
          onChange={onCodesChange}
          placeholder="多个 6 位代码用英文逗号分隔"
        />
      </div>
      <div className={`${NOTE_CARD_CLS} mt-4`}>{note}</div>
    </div>
  );
}

export default function FactorPage() {
  const [formError, setFormError] = useState<string | null>(null);
  const [stageTab, setStageTab] = useState<FactorStageTab>('foundation');
  const [foundationTab, setFoundationTab] = useState<FactorFoundationTab>('library');
  const [validationTab, setValidationTab] = useState<FactorValidationTab>('backtest');
  const collapseToTabs = useMobile(RESPONSIVE_BREAKPOINTS.splitCollapse);

  const [libPath, setLibPath] = useState<string | null>(null);
  const libQ = useApiQuery<unknown>(libPath);

  const [calcName, setCalcName] = useState('momentum');
  const [calcCodes, setCalcCodes] = useState(DEFAULT_FACTOR_CODES);
  const calcMut = useApiMutation<unknown>();

  const [icName, setIcName] = useState('momentum');
  const [icCodes, setIcCodes] = useState(DEFAULT_FACTOR_CODES);
  const icMut = useApiMutation<unknown>();

  const [btName, setBtName] = useState('momentum');
  const [btCodes, setBtCodes] = useState(DEFAULT_FACTOR_CODES);
  const btMut = useApiMutation<unknown>();

  const [oosName, setOosName] = useState('momentum');
  const [oosCodes, setOosCodes] = useState(DEFAULT_FACTOR_CODES);
  const oosMut = useApiMutation<unknown>();

  const [robName, setRobName] = useState('momentum');
  const [robCodes, setRobCodes] = useState(DEFAULT_FACTOR_CODES);
  const robMut = useApiMutation<unknown>();

  const libLoading = libQ.isFetching;
  const calcLoading = calcMut.isPending;
  const icLoading = icMut.isPending;
  const btLoading = btMut.isPending;
  const oosLoading = oosMut.isPending;
  const robLoading = robMut.isPending;
  const anyLoading = libLoading || calcLoading || icLoading || btLoading || oosLoading || robLoading;
  const error = formError || libQ.error || calcMut.error || icMut.error || btMut.error || oosMut.error || robMut.error;

  function splitCodes(raw: string) {
    return raw
      .split(',')
      .map((item) => item.trim())
      .filter(Boolean);
  }

  function mcpError(payload: unknown): string | null {
    if (!payload || typeof payload !== 'object') return null;
    const obj = payload as Record<string, unknown>;
    const inner = typeof obj.data === 'object' && obj.data ? (obj.data as Record<string, unknown>) : obj;
    if (inner.success === false && inner.error) return String(inner.error);
    if (typeof inner.data === 'object' && inner.data) {
      const deep = inner.data as Record<string, unknown>;
      if (deep.success === false && deep.error) return String(deep.error);
    }
    return null;
  }

  function validateCodes(raw: string): boolean {
    const codes = splitCodes(raw);
    if (codes.length === 0) {
      setFormError('请输入至少一个股票代码');
      return false;
    }
    const invalid = codes.find((code) => !/^\d{6}$/.test(code));
    if (invalid) {
      setFormError(`股票代码格式错误: ${invalid}（需为6位数字）`);
      return false;
    }
    return true;
  }

  function runRecommendedResearchSample() {
    setFormError(null);
    setStageTab('foundation');
    setFoundationTab('calculate');
    const recommendedFactorName = 'momentum';
    const recommendedCodes = DEFAULT_FACTOR_CODES;
    const stockCodes = splitCodes(recommendedCodes);
    setCalcName(recommendedFactorName);
    setCalcCodes(recommendedCodes);
    setIcName(recommendedFactorName);
    setIcCodes(recommendedCodes);
    setBtName(recommendedFactorName);
    setBtCodes(recommendedCodes);
    if (libPath) libQ.refetch();
    else setLibPath('/factor/library');
    calcMut.trigger(
      '/factor/calculate',
      { method: 'POST' },
      {
        factor_name: recommendedFactorName,
        stock_codes: stockCodes,
      },
    );
  }

  const libFactors = extractArray(libQ.data, 'factors', 'values', 'results') as Array<Record<string, unknown>>;
  const libraryRows = (libFactors.length ? libFactors : extractArray(libQ.data)) as Array<Record<string, unknown>>;
  const calcRows = extractArray(calcMut.data, 'factors', 'values', 'results') as Array<Record<string, unknown>>;
  const calcFallbackRows = extractArray(calcMut.data) as Array<Record<string, unknown>>;
  const icObj = extractObject(icMut.data) as Record<string, unknown> | null;
  const icTimeSeries = extractArray(icMut.data, 'timeSeries', 'ic_series', 'series') as Array<Record<string, unknown>>;
  const btObj = extractObject(btMut.data) as Record<string, unknown> | null;
  const btEquity = extractArray(btMut.data, 'equityCurve', 'returns') as Array<Record<string, unknown>>;
  const btQuantile = extractArray(btMut.data, 'quantileReturns', 'quantiles') as Array<Record<string, unknown>>;
  const oosObj = extractObject(oosMut.data) as Record<string, unknown> | null;
  const robTests = extractArray(robMut.data, 'tests', 'checks', 'results') as Array<Record<string, unknown>>;
  const robFallbackRows = extractArray(robMut.data) as Array<Record<string, unknown>>;
  const robObj = extractObject(robMut.data) as Record<string, unknown> | null;

  const calcError = mcpError(calcMut.data);
  const icError = mcpError(icMut.data);
  const btError = mcpError(btMut.data);
  const oosError = mcpError(oosMut.data);
  const robError = mcpError(robMut.data);

  const oosPassed = Boolean(oosObj ? (oosObj.passed ?? oosObj.pass) : false);
  const robustPassed = Boolean(robObj ? (robObj.passed ?? robObj.pass ?? robObj.overall_pass) : false);
  const currentIc = !icError && icMut.data ? Number(icObj?.ic ?? icObj?.IC ?? 0) : null;
  const currentSharpe = !btError && btMut.data ? Number(btObj?.sharpe ?? btObj?.sharpe_ratio ?? 0) : null;
  const currentBacktestReturn = !btError && btMut.data ? Number(btObj?.totalReturn ?? btObj?.total_return ?? 0) : null;

  const sectionTabMap: Record<
    string,
    { stage: FactorStageTab; foundation?: FactorFoundationTab; validation?: FactorValidationTab }
  > = {
    'factor-library': { stage: 'foundation', foundation: 'library' },
    'factor-calculate': { stage: 'foundation', foundation: 'calculate' },
    'factor-ic': { stage: 'foundation', foundation: 'ic' },
    'factor-backtest': { stage: 'validation', validation: 'backtest' },
    'factor-oos': { stage: 'validation', validation: 'oos' },
    'factor-robustness': { stage: 'validation', validation: 'robustness' },
    'factor-mining': { stage: 'mining' },
  };

  function scrollToSection(id: string) {
    if (typeof document === 'undefined') return;
    const target = sectionTabMap[id];
    if (target) {
      setStageTab(target.stage);
      if (target.foundation) setFoundationTab(target.foundation);
      if (target.validation) setValidationTab(target.validation);
      window.setTimeout(() => {
        document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }, 40);
      return;
    }
    document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }
  const factorPageActions = [
    {
      id: 'factor.run-sample',
      label: '运行推荐研究样例',
      description: '按默认样本池启动一轮标准因子研究链路',
      keywords: ['因子', '样例', '研究'],
      scope: 'page' as const,
      pageKey: 'factor',
      run: () => {
        runRecommendedResearchSample();
        return { message: '已发起推荐因子研究样例' };
      },
    },
    {
      id: 'factor.open-ic',
      label: '跳到 IC 分析',
      description: '切到 IC 分析视图继续确认信号方向',
      keywords: ['IC', '信号验证'],
      scope: 'page' as const,
      pageKey: 'factor',
      run: () => {
        scrollToSection('factor-ic');
        return { message: '已切到 IC 分析' };
      },
    },
    {
      id: 'factor.open-mining',
      label: '切到 AI 挖掘',
      description: '切到 AI 候选生成与治理工作区',
      keywords: ['AI 挖掘', '候选治理'],
      scope: 'page' as const,
      pageKey: 'factor',
      run: () => {
        setStageTab('mining');
        return { message: '已切到 AI 挖掘工作区' };
      },
    },
  ];
  usePageActions(factorPageActions);
  const factorSummary = `当前因子研究聚焦 ${calcName.trim() || '-'}，样本 ${splitCodes(calcCodes).length} 只，IC ${currentIc != null ? fmtNum(currentIc, 4) : '-'}，夏普 ${currentSharpe != null ? fmtNum(currentSharpe, 2) : '-'}。`;
  const factorResult = buildLocalResultContract({
    summary: factorSummary,
    availableViews: calcMut.data || btMut.data || icMut.data ? ['compare', 'visual'] : [],
    pageActions: factorPageActions,
    preferredActionIds: ['factor.run-sample', 'factor.open-ic', 'factor.open-mining'],
    recommendedLinks: [
      { id: 'factor-link-analysis', label: '单因子快判页', href: '/factor-analysis' },
      { id: 'factor-link-strategy', label: '策略超市', href: '/strategy-market?from=factor&task=factor_research' },
      { id: 'factor-link-assistant', label: '继续追问 Copilot', href: `/assistant?from=factor&factor=${encodeURIComponent(calcName.trim() || 'momentum')}` },
    ],
    evidence: [
      { label: '当前因子', value: calcName.trim() || '-' },
      { label: '样本池', value: String(splitCodes(calcCodes).length) },
      { label: '研究阶段', value: stageTab === 'foundation' ? '基础研究' : stageTab === 'validation' ? '收益验证' : 'AI 挖掘' },
      { label: 'IC', value: currentIc != null ? fmtNum(currentIc, 4) : '-' },
      { label: '总收益', value: currentBacktestReturn != null ? fmtPct(currentBacktestReturn) : '-' },
      { label: '样本外', value: oosMut.data ? (oosPassed ? '通过' : '未通过') : '待验证' },
    ],
    riskNotes: [
      ...(error ? [error] : []),
      ...(!calcMut.data ? ['当前还没有完成首轮样本计算。'] : []),
      ...(oosMut.data && !oosPassed ? ['样本外验证未通过，进入策略或组合前需要复核。'] : []),
      ...(robMut.data && !robustPassed ? ['稳健性检验未通过，建议不要直接进入治理池或策略落地。'] : []),
    ],
    platformMeta: {
      sourceTool: 'factor',
      sourceChain: ['factor/library', 'factor/calculate', 'factor/ic', 'factor/backtest', 'factor/oos', 'factor/robustness'],
      degraded: Boolean(error),
      fallbackReason: [error].filter((item): item is string => Boolean(item)),
    },
    workbenchTask: defaultWorkbenchTask('factor', `复查因子研究 ${calcName.trim() || 'momentum'}`, '/factor', 'factor-research-review', {
      factor: calcName.trim() || 'momentum',
      sampleSize: splitCodes(calcCodes).length,
      stageTab,
    }),
  });
  usePageContext({
    pageKey: 'factor',
    title: '因子研究工作台',
    summary: factorSummary,
    objectType: 'factor',
    objectId: calcName.trim() || 'momentum',
    resultType: 'factor-research',
    tags: [
      calcName.trim() || 'momentum',
      `${splitCodes(calcCodes).length} 样本`,
      stageTab === 'foundation' ? '基础研究' : stageTab === 'validation' ? '收益验证' : 'AI 挖掘',
      calcMut.data ? '已完成样本计算' : '待计算',
    ],
    suggestions: [
      '总结当前因子研究是否值得继续推进',
      '如果验证结果冲突，解释最需要先修正哪一环',
      '给出下一步是继续做验证还是进入 AI 挖掘治理',
    ],
    recommendedActions: factorResult.recommendedActions ?? [],
    recommendedLinks: factorResult.recommendedLinks ?? [],
    evidenceSummary: evidenceToSummary(factorResult.evidence),
    riskNotes: factorResult.riskNotes ?? [],
    freshness: factorResult.freshness ?? null,
    raw: {
      factor: calcName.trim() || 'momentum',
      stageTab,
      sampleSize: splitCodes(calcCodes).length,
      currentIc,
      currentSharpe,
      currentBacktestReturn,
    },
  });

  return (
    <PageContainer className="app-theme-strategy">
      <SectionCard className="mb-4 p-4 sm:p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="eyebrow">Workspace Layers</div>
            <h3 className="mb-0 mt-2 text-xl font-semibold text-text-primary">因子研究切换</h3>
            <p className="mb-0 mt-2 max-w-3xl text-sm leading-7 text-text-secondary">
              基础研究、收益验证和 AI 挖掘分层显示。默认只保留当前步骤，避免因子库、IC、回测和稳健性同时平铺成长页。
            </p>
          </div>
          <Badge variant={stageTab === 'mining' ? 'info' : 'neutral'}>
            {stageTab === 'foundation' ? '基础研究' : stageTab === 'validation' ? '收益验证' : 'AI 挖掘'}
          </Badge>
        </div>
        <div className="mt-4 flex flex-wrap items-center gap-3">
          <TabBar tabs={FACTOR_STAGE_TABS} active={stageTab} onChange={setStageTab} />
          {stageTab === 'foundation' ? (
            <TabBar tabs={FACTOR_FOUNDATION_TABS} active={foundationTab} onChange={setFoundationTab} />
          ) : null}
          {stageTab === 'validation' ? (
            <TabBar tabs={FACTOR_VALIDATION_TABS} active={validationTab} onChange={setValidationTab} />
          ) : null}
        </div>
      </SectionCard>

      <section className="page-hero mb-4 p-5 sm:p-6">
        <div className="grid gap-5 2xl:grid-cols-[minmax(0,1.2fr)_380px]">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="info">Factor Workspace</Badge>
              <Badge variant={libraryRows.length > 0 ? 'success' : 'neutral'}>
                {libraryRows.length > 0 ? `因子库 ${libraryRows.length} 项` : '因子库待加载'}
              </Badge>
              <Badge variant={calcMut.data ? 'success' : 'warning'}>
                {calcMut.data ? '已完成一次样本计算' : '等待样本计算'}
              </Badge>
              <Badge variant={oosMut.data ? (oosPassed ? 'success' : 'warning') : 'neutral'}>
                {oosMut.data ? (oosPassed ? '样本外验证通过' : '样本外待优化') : '尚未做样本外验证'}
              </Badge>
            </div>

            <h1 className="mb-0 mt-4 text-[2rem] font-semibold tracking-[-0.03em] text-text-primary sm:text-[2.4rem]">
              因子研究工作台
            </h1>
            <p className="mb-0 mt-3 max-w-3xl text-sm leading-7 text-text-secondary sm:text-[15px]">
              这里把普通因子研究与 AI
              候选挖掘收进一条完整链路。先建立因子库认知，再完成计算、IC、回测、样本外与稳健性检验，最后进入候选生成、验证、记忆治理与调度巡检。
            </p>

            <div className="mt-5 flex flex-wrap gap-2">
              <button
                type="button"
                disabled={calcLoading}
                onClick={runRecommendedResearchSample}
                data-testid="page-primary-action"
                className={HERO_PRIMARY_BUTTON_CLS}
              >
                {calcLoading ? '运行中...' : '运行推荐研究样例'}
              </button>
            </div>
            <div
              data-testid="page-primary-status"
              className="mt-4 rounded-[22px] border border-white/50 bg-white/28 px-4 py-3 text-sm shadow-[inset_0_1px_0_rgba(255,255,255,0.68)]"
            >
              <div className="font-medium text-text-primary">
                当前因子 {calcName.trim() || '-'} ｜ 样本 {splitCodes(calcCodes).length} 只
              </div>
              <p className="mt-1 mb-0 text-xs leading-6 text-text-secondary">
                因子库 {libraryRows.length > 0 ? `已加载 ${libraryRows.length} 项` : '待加载'} ｜
                推荐流程会先刷新因子库，再运行首轮样本计算。
              </p>
              <p className="mt-2 mb-0 text-xs text-text-secondary">
                研究状态：{calcMut.data ? '已完成推荐样例计算' : anyLoading ? '处理中' : '等待启动'}
              </p>
            </div>

            <div className="mt-5 grid gap-3 sm:grid-cols-4">
              <div className="rounded-[24px] border border-white/45 bg-white/38 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.55)]">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">样本池</div>
                <div className="mt-3 text-2xl font-semibold text-text-primary">{splitCodes(calcCodes).length}</div>
                <div className="mt-1 text-xs text-text-secondary">默认覆盖白酒、银行、新能源与消费龙头</div>
              </div>
              <div className="rounded-[24px] border border-white/45 bg-white/30 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.48)]">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">当前因子</div>
                <div className="mt-3 text-2xl font-semibold text-text-primary">{calcName.trim() || '-'}</div>
                <div className="mt-1 text-xs text-text-secondary">IC / 回测 / 验证默认沿用同一名称</div>
              </div>
              <div className="rounded-[24px] border border-white/45 bg-white/26 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.42)]">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">关键读数</div>
                <div className="mt-3 text-2xl font-semibold text-text-primary">
                  {currentIc != null ? fmtNum(currentIc, 4) : '-'}
                </div>
                <div className="mt-1 text-xs text-text-secondary">
                  {currentSharpe != null ? `夏普 ${fmtNum(currentSharpe, 2)}` : '先做 IC 或回测生成关键指标'}
                </div>
              </div>
              <div className="rounded-[24px] border border-white/45 bg-white/24 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.38)]">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">下一步</div>
                <div className="mt-3 text-2xl font-semibold text-text-primary">
                  {robMut.data ? (robustPassed ? '通过' : '复核') : 'AI'}
                </div>
                <div className="mt-1 text-xs text-text-secondary">
                  {robMut.data ? '根据稳健性结果决定是否进入治理池' : '完成基础验证后再进入 AI 挖掘闭环'}
                </div>
              </div>
            </div>
          </div>

          {!collapseToTabs ? (
            <div className="grid gap-3">
              <div className={SIDE_PANEL_CLS}>
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">建议顺序</div>
                <div className="mt-4 space-y-3">
                  <div className={NOTE_CARD_CLS}>1. 先看因子库与样本池，确认这次研究的名称、覆盖面和研究意图。</div>
                  <div className={NOTE_CARD_CLS}>2. 再做因子计算、IC 和回测，建立“方向是否成立”的第一层证据。</div>
                  <div className={NOTE_CARD_CLS}>3. 最后做样本外与稳健性检验，只有稳定后才值得进入 AI 挖掘与治理。</div>
                </div>
              </div>

              <div className={SIDE_PANEL_CLS}>
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">当前研究状态</div>
                <div className="mt-3 text-base font-semibold text-text-primary">
                  {calcMut.data ? '基础研究链路已启动' : '等待第一次样本计算'}
                </div>
                <div className="mt-4 space-y-3">
                  <div className={NOTE_CARD_CLS}>
                    因子库：
                    <span className="font-medium text-text-primary">
                      {libraryRows.length > 0 ? `已加载 ${libraryRows.length} 项` : '尚未加载'}
                    </span>
                  </div>
                  <div className={NOTE_CARD_CLS}>
                    样本外：
                    <span className="font-medium text-text-primary">
                      {oosMut.data ? (oosPassed ? '通过' : '未通过') : '待验证'}
                    </span>
                  </div>
                  <div className={NOTE_CARD_CLS}>
                    AI 挖掘：
                    <span className="font-medium text-text-primary">基础验证清晰后再进入候选生成与记忆治理</span>
                  </div>
                </div>
              </div>
            </div>
          ) : (
            <div className={SIDE_PANEL_CLS}>
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">研究提示</div>
              <div className="mt-3 text-base font-semibold text-text-primary">
                {calcMut.data ? '基础研究链路已启动' : '等待第一次样本计算'}
              </div>
              <div className="mt-4 space-y-3">
                <div className={NOTE_CARD_CLS}>先看因子库和样本池，再进入 IC 与回测。</div>
                <div className={NOTE_CARD_CLS}>样本外与稳健性通过后，再进入 AI 候选治理。</div>
              </div>
            </div>
          )}
        </div>
      </section>

      <ResponsiveResultWorkbench pageKey="factor" title="因子研究结果工作台" result={factorResult} />

      {anyLoading ? <LoadingState text="处理中..." /> : null}
      {error ? <ErrorState text={error} hint="请先确认因子名称与股票池输入" /> : null}

      {!collapseToTabs ? (
        <KpiGrid cols={6} className="mb-4">
          <KpiCard title="因子库" value={libraryRows.length > 0 ? String(libraryRows.length) : null} />
          <KpiCard title="计算样本" value={String(splitCodes(calcCodes).length)} />
          <KpiCard title="IC" value={currentIc != null ? fmtNum(currentIc, 4) : null} />
          <KpiCard title="总收益" value={currentBacktestReturn != null ? fmtPct(currentBacktestReturn) : null} />
          <KpiCard title="样本外" value={oosMut.data ? (oosPassed ? '通过' : '未通过') : null} />
          <KpiCard title="稳健性" value={robMut.data ? (robustPassed ? '通过' : '未通过') : null} />
        </KpiGrid>
      ) : null}

      <div id="factor-library" className="scroll-mt-24">
        {stageTab === 'foundation' && foundationTab === 'library' ? (
        <SectionCard className="p-4 sm:p-5">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="eyebrow">Library Layer</div>
              <h3 className="mt-2 mb-0 text-xl font-semibold text-text-primary">因子库</h3>
              <p className="mb-0 mt-2 text-sm leading-7 text-text-secondary">
                先用因子库建立命名、分类和用途的共同语言，避免后续 IC 与回测只剩下数字，没有研究语境。
              </p>
            </div>
            <button
              type="button"
              disabled={libLoading}
              onClick={() => {
                setFormError(null);
                setStageTab('foundation');
                setFoundationTab('library');
                if (libPath) libQ.refetch();
                else setLibPath('/factor/library');
              }}
              className={HERO_PRIMARY_BUTTON_CLS}
            >
              {libLoading ? '刷新中...' : '刷新因子库'}
            </button>
          </div>

          <div className="mt-4 grid gap-4 xl:grid-cols-[320px_minmax(0,1fr)]">
            <div className={SIDE_PANEL_CLS}>
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">阅读提示</div>
              <div className="mt-4 space-y-3">
                <div className={NOTE_CARD_CLS}>优先识别因子名称、分类和用途，先判断它是不是你要研究的那一类信号。</div>
                <div className={NOTE_CARD_CLS}>
                  如果分类维度不足，可以先从表格里筛出同类因子，再决定是否进入计算与比较。
                </div>
                <div className={NOTE_CARD_CLS}>库中记录越清晰，后续 AI 候选治理就越容易形成统一的研究命名规则。</div>
              </div>
            </div>

            <div className="panel-soft rounded-[28px] p-4 sm:p-5">
              {libQ.data ? (
                libraryRows.length > 0 ? (
                  libFactors.length > 0 ? (
                    <DataTable
                      rows={libFactors}
                      columns={[
                        { key: 'name', label: '名称', sortable: true },
                        {
                          key: 'category',
                          label: '分类',
                          sortable: true,
                          render: (value) => (value ? <Badge variant="info">{String(value)}</Badge> : '-'),
                        },
                        { key: 'description', label: '描述' },
                      ]}
                      onExport={() => exportCSV(libFactors, 'factor-library')}
                    />
                  ) : (
                    <DataTable rows={libraryRows} onExport={() => exportCSV(libraryRows, 'factor-library')} />
                  )
                ) : (
                  <EmptyState text="因子库已返回，但暂未解析出可展示的记录" />
                )
              ) : (
                <EmptyState text="点击按钮加载因子库" />
              )}
            </div>
          </div>
        </SectionCard>
        ) : null}
      </div>

      <div id="factor-calculate" className="scroll-mt-24">
        {stageTab === 'foundation' && foundationTab === 'calculate' ? (
        <SectionCard className="p-4 sm:p-5">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="eyebrow">Calculation Layer</div>
              <h3 className="mt-2 mb-0 text-xl font-semibold text-text-primary">因子计算</h3>
              <p className="mb-0 mt-2 text-sm leading-7 text-text-secondary">
                先看单期因子值分布是否符合直觉，再决定是否进入 IC 与回测。这里更像“信号体检”，不是最后结论。
              </p>
            </div>
            <button type="button" onClick={() => scrollToSection('factor-ic')} className={CHIP_LINK_CLS}>
              继续做 IC 分析
            </button>
          </div>

          <div className="mt-4 grid gap-4 xl:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
            <FactorRequestFields
              legend="计算样本"
              description="先确认单期因子值是否合理，再继续看 IC 或回测。"
              note="默认样本覆盖 12 只龙头股，适合直接做首轮信号体检。若要做分组收益比较，建议再扩一轮股票池。"
              nameId="factor-calc-name"
              nameValue={calcName}
              onNameChange={setCalcName}
              codesId="factor-calc-codes"
              codesValue={calcCodes}
              onCodesChange={setCalcCodes}
              actionLabel="计算"
              actionLoadingLabel="计算中..."
              loading={calcLoading}
              onSubmit={() => {
                setFormError(null);
                setStageTab('foundation');
                setFoundationTab('calculate');
                if (!validateCodes(calcCodes)) return;
                calcMut.trigger(
                  '/factor/calculate',
                  { method: 'POST' },
                  {
                    factor_name: calcName.trim(),
                    stock_codes: splitCodes(calcCodes),
                  },
                );
              }}
            />

            <div className="panel-soft rounded-[26px] p-4 sm:p-5">
              <div className="eyebrow">Result Snapshot</div>
              <p className="mb-0 mt-2 text-sm leading-7 text-text-secondary">
                重点看不同股票之间是否形成有辨识度的差异，而不是所有值都挤在一条直线上。
              </p>
              <div className="mt-4">
                {calcError ? (
                  <ErrorState text={calcError} />
                ) : calcMut.data ? (
                  calcRows.length > 0 ? (
                    <BarChart
                      horizontal
                      items={calcRows.map((row) => ({
                        label: String(row.stock_code ?? row.code ?? row.name ?? ''),
                        value: Number(
                          row.factor_value ??
                            row.value ??
                            (row.data as Record<string, unknown> | undefined)?.value ??
                            0,
                        ),
                      }))}
                      yAxisName="因子值"
                    />
                  ) : calcFallbackRows.length > 0 ? (
                    <DataTable rows={calcFallbackRows} />
                  ) : (
                    <EmptyState text="接口已返回，但暂未解析出因子值明细" />
                  )
                ) : (
                  <EmptyState text="运行一次因子计算后，这里会展示样本横截面的因子值分布" />
                )}
              </div>
            </div>
          </div>
        </SectionCard>
        ) : null}
      </div>

      <div id="factor-ic" className="scroll-mt-24">
        {stageTab === 'foundation' && foundationTab === 'ic' ? (
        <SectionCard className="p-4 sm:p-5">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="eyebrow">Signal Verification</div>
              <h3 className="mt-2 mb-0 text-xl font-semibold text-text-primary">IC 分析</h3>
              <p className="mb-0 mt-2 text-sm leading-7 text-text-secondary">
                IC 用来回答一个更关键的问题: 因子值和未来收益是否同向，以及这种关系是否足够稳定。
              </p>
            </div>
            <button type="button" onClick={() => scrollToSection('factor-backtest')} className={CHIP_LINK_CLS}>
              继续看因子回测
            </button>
          </div>

          <div className="mt-4 grid gap-4 xl:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
            <FactorRequestFields
              legend="截面相关性"
              description="IC 用来验证因子值与未来收益是否同向，股票样本尽量覆盖 10 只以上。"
              note="如果 IC 很弱或方向颠倒，优先回头检查因子定义与样本覆盖，而不是直接跳进回测和优化。"
              nameId="factor-ic-name"
              nameValue={icName}
              onNameChange={setIcName}
              codesId="factor-ic-codes"
              codesValue={icCodes}
              onCodesChange={setIcCodes}
              actionLabel="分析"
              actionLoadingLabel="分析中..."
              loading={icLoading}
              onSubmit={() => {
                setFormError(null);
                setStageTab('foundation');
                setFoundationTab('ic');
                if (!validateCodes(icCodes)) return;
                icMut.trigger(
                  '/factor/ic',
                  { method: 'POST' },
                  {
                    factor_name: icName.trim(),
                    stock_codes: splitCodes(icCodes),
                  },
                );
              }}
            />

            <div className="panel-soft rounded-[26px] p-4 sm:p-5">
              <div className="eyebrow">IC Outcome</div>
              <p className="mb-0 mt-2 text-sm leading-7 text-text-secondary">
                除了看单次 IC，也要注意时间序列是否持续为正，以及波动是否过大。
              </p>
              <div className="mt-4">
                {icError ? (
                  <ErrorState text={icError} hint="IC 分析通常需要 10 只以上股票" />
                ) : icMut.data && icObj ? (
                  <>
                    <KpiGrid cols={4}>
                      <KpiCard title="IC" value={fmtNum(Number(icObj.ic ?? icObj.IC ?? 0), 4)} />
                      <KpiCard title="IC-IR" value={fmtNum(Number(icObj.icir ?? icObj.ic_ir ?? icObj.ICIR ?? 0), 4)} />
                      <KpiCard title="p-value" value={fmtNum(Number(icObj.pValue ?? icObj.p_value ?? 0), 4)} />
                      <KpiCard
                        title="t-stat"
                        value={fmtNum(Number(icObj.tStat ?? icObj.t_stat ?? icObj.tStatistic ?? 0), 4)}
                      />
                    </KpiGrid>
                    {icTimeSeries.length > 0 ? (
                      <div className="mt-4">
                        <LineChart
                          categories={icTimeSeries.map((item) => String(item.date ?? item.period ?? ''))}
                          series={[
                            {
                              name: 'IC',
                              data: icTimeSeries.map((item) => Number(item.ic ?? item.value ?? 0)),
                            },
                          ]}
                          yAxisName="IC"
                        />
                      </div>
                    ) : null}
                  </>
                ) : (
                  <EmptyState text="运行一次 IC 分析后，这里会展示横截面相关性与时间序列走势" />
                )}
              </div>
            </div>
          </div>
        </SectionCard>
        ) : null}
      </div>

      <div id="factor-backtest" className="scroll-mt-24">
        {stageTab === 'validation' && validationTab === 'backtest' ? (
        <SectionCard className="p-4 sm:p-5">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="eyebrow">Return Validation</div>
              <h3 className="mt-2 mb-0 text-xl font-semibold text-text-primary">因子回测</h3>
              <p className="mb-0 mt-2 text-sm leading-7 text-text-secondary">
                回测用来验证因子排序是否能形成稳定的分组收益与净值抬升，它是 IC 之后的第二层证据。
              </p>
            </div>
            <button type="button" onClick={() => scrollToSection('factor-oos')} className={CHIP_LINK_CLS}>
              继续做样本外验证
            </button>
          </div>

          <div className="mt-4 grid gap-4 xl:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
            <FactorRequestFields
              legend="收益验证"
              description="回测用来验证因子排序是否能稳定带来分组收益和净值抬升。"
              note="如果回测只在极少数样本里抬升明显，或分组收益没有层次感，就还不能直接进入生产或治理池。"
              nameId="factor-backtest-name"
              nameValue={btName}
              onNameChange={setBtName}
              codesId="factor-backtest-codes"
              codesValue={btCodes}
              onCodesChange={setBtCodes}
              actionLabel="回测"
              actionLoadingLabel="回测中..."
              loading={btLoading}
              onSubmit={() => {
                setFormError(null);
                setStageTab('validation');
                setValidationTab('backtest');
                if (!validateCodes(btCodes)) return;
                btMut.trigger(
                  '/factor/backtest',
                  { method: 'POST' },
                  {
                    factor_name: btName.trim(),
                    stock_codes: splitCodes(btCodes),
                  },
                );
              }}
            />

            <div className="panel-soft rounded-[26px] p-4 sm:p-5">
              <div className="eyebrow">Backtest Outcome</div>
              <p className="mb-0 mt-2 text-sm leading-7 text-text-secondary">
                看总收益的同时，也要一起看夏普、回撤和分组收益，否则很容易误把高波动当成好结果。
              </p>
              <div className="mt-4">
                {btError ? (
                  <ErrorState text={btError} hint="因子回测通常需要更多股票样本" />
                ) : btMut.data && btObj ? (
                  <>
                    <KpiGrid cols={4}>
                      <KpiCard title="总收益" value={fmtPct(Number(btObj.totalReturn ?? btObj.total_return ?? 0))} />
                      <KpiCard
                        title="年化收益"
                        value={fmtPct(Number(btObj.annualReturn ?? btObj.annual_return ?? 0))}
                      />
                      <KpiCard title="夏普比率" value={fmtNum(Number(btObj.sharpe ?? btObj.sharpe_ratio ?? 0), 2)} />
                      <KpiCard title="最大回撤" value={fmtPct(Number(btObj.maxDrawdown ?? btObj.max_drawdown ?? 0))} />
                    </KpiGrid>
                    {btEquity.length > 0 ? (
                      <div className="mt-4">
                        <LineChart
                          categories={btEquity.map((item) => String(item.date ?? item.period ?? ''))}
                          series={[
                            {
                              name: '净值',
                              data: btEquity.map((item) => Number(item.value ?? item.equity ?? item.nav ?? 0)),
                            },
                          ]}
                          yAxisName="净值"
                        />
                      </div>
                    ) : null}
                    {btQuantile.length > 0 ? (
                      <div className="mt-4">
                        <BarChart
                          items={btQuantile.map((item) => ({
                            label: String(item.quantile ?? item.group ?? item.name ?? ''),
                            value: Number(item.return ?? item.value ?? 0),
                          }))}
                          yAxisName="收益率"
                          colorByValue
                        />
                      </div>
                    ) : null}
                  </>
                ) : (
                  <EmptyState text="运行一次因子回测后，这里会展示净值曲线、分组收益与关键绩效指标" />
                )}
              </div>
            </div>
          </div>
        </SectionCard>
        ) : null}
      </div>

      <div id="factor-oos" className="scroll-mt-24">
        {stageTab === 'validation' && validationTab === 'oos' ? (
        <SectionCard className="p-4 sm:p-5">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="eyebrow">Generalization Check</div>
              <h3 className="mt-2 mb-0 text-xl font-semibold text-text-primary">样本外验证</h3>
              <p className="mb-0 mt-2 text-sm leading-7 text-text-secondary">
                样本外验证用来回答“这个因子能否离开样本内仍然有效”，它决定了研究结果是否有迁移价值。
              </p>
            </div>
            <button type="button" onClick={() => scrollToSection('factor-robustness')} className={CHIP_LINK_CLS}>
              继续做稳健性检验
            </button>
          </div>

          <div className="mt-4 grid gap-4 xl:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
            <FactorRequestFields
              legend="泛化能力"
              description="样本外验证用于检查因子从样本内迁移到样本外时是否仍然有效。"
              note="样本外通过并不意味着一定可投，但至少说明结果不是完全依赖样本内区间。"
              nameId="factor-oos-name"
              nameValue={oosName}
              onNameChange={setOosName}
              codesId="factor-oos-codes"
              codesValue={oosCodes}
              onCodesChange={setOosCodes}
              actionLabel="验证"
              actionLoadingLabel="验证中..."
              loading={oosLoading}
              onSubmit={() => {
                setFormError(null);
                setStageTab('validation');
                setValidationTab('oos');
                if (!validateCodes(oosCodes)) return;
                oosMut.trigger(
                  '/factor/validate-oos',
                  { method: 'POST' },
                  {
                    factor_name: oosName.trim(),
                    stock_codes: splitCodes(oosCodes),
                  },
                );
              }}
            />

            <div className="panel-soft rounded-[26px] p-4 sm:p-5">
              <div className="eyebrow">OOS Outcome</div>
              <p className="mb-0 mt-2 text-sm leading-7 text-text-secondary">
                样本内和样本外指标差距过大时，通常意味着过拟合或样本结构差异，需要重新审视因子定义。
              </p>
              <div className="mt-4">
                {oosError ? (
                  <ErrorState text={oosError} />
                ) : oosMut.data && oosObj ? (
                  <>
                    <div className="mb-3">
                      <Badge variant={oosPassed ? 'success' : 'danger'}>{oosPassed ? '验证通过' : '验证未通过'}</Badge>
                    </div>
                    <KpiGrid cols={4}>
                      <KpiCard
                        title="样本内 IC"
                        value={fmtNum(
                          Number(
                            (oosObj.inSample as Record<string, unknown> | undefined)?.ic ??
                              oosObj.in_sample_ic ??
                              oosObj.is_ic ??
                              0,
                          ),
                          4,
                        )}
                      />
                      <KpiCard
                        title="样本外 IC"
                        value={fmtNum(
                          Number(
                            (oosObj.outOfSample as Record<string, unknown> | undefined)?.ic ??
                              oosObj.out_of_sample_ic ??
                              oosObj.oos_ic ??
                              0,
                          ),
                          4,
                        )}
                      />
                      <KpiCard
                        title="样本内 Sharpe"
                        value={fmtNum(
                          Number(
                            (oosObj.inSample as Record<string, unknown> | undefined)?.sharpe ??
                              oosObj.in_sample_sharpe ??
                              oosObj.is_sharpe ??
                              0,
                          ),
                          2,
                        )}
                      />
                      <KpiCard
                        title="样本外 Sharpe"
                        value={fmtNum(
                          Number(
                            (oosObj.outOfSample as Record<string, unknown> | undefined)?.sharpe ??
                              oosObj.out_of_sample_sharpe ??
                              oosObj.oos_sharpe ??
                              0,
                          ),
                          2,
                        )}
                      />
                    </KpiGrid>
                  </>
                ) : (
                  <EmptyState text="运行一次样本外验证后，这里会显示样本内外指标对比与通过状态" />
                )}
              </div>
            </div>
          </div>
        </SectionCard>
        ) : null}
      </div>

      <div id="factor-robustness" className="scroll-mt-24">
        {stageTab === 'validation' && validationTab === 'robustness' ? (
        <SectionCard className="p-4 sm:p-5">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="eyebrow">Stability Check</div>
              <h3 className="mt-2 mb-0 text-xl font-semibold text-text-primary">稳健性检验</h3>
              <p className="mb-0 mt-2 text-sm leading-7 text-text-secondary">
                稳健性检验适合放在最后一步，用来判断结果是不是由少量样本、单一市场状态或偶然区间驱动。
              </p>
            </div>
            <button type="button" onClick={() => scrollToSection('factor-mining')} className={CHIP_LINK_CLS}>
              进入 AI 挖掘工作台
            </button>
          </div>

          <div className="mt-4 grid gap-4 xl:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
            <FactorRequestFields
              legend="稳定性检查"
              description="稳健性检验适合放在最后一步，确认结果不是由少数样本或偶然区间驱动。"
              note="当整体通过后，再把结果送进 AI 候选验证、研究记忆和活跃池治理，链路会更稳。"
              nameId="factor-robust-name"
              nameValue={robName}
              onNameChange={setRobName}
              codesId="factor-robust-codes"
              codesValue={robCodes}
              onCodesChange={setRobCodes}
              actionLabel="检验"
              actionLoadingLabel="检验中..."
              loading={robLoading}
              onSubmit={() => {
                setFormError(null);
                setStageTab('validation');
                setValidationTab('robustness');
                if (!validateCodes(robCodes)) return;
                robMut.trigger(
                  '/factor/robustness-check',
                  { method: 'POST' },
                  {
                    factor_name: robName.trim(),
                    stock_codes: splitCodes(robCodes),
                  },
                );
              }}
            />

            <div className="panel-soft rounded-[26px] p-4 sm:p-5">
              <div className="eyebrow">Robustness Outcome</div>
              <p className="mb-0 mt-2 text-sm leading-7 text-text-secondary">
                这里要关注“哪些检验项没过”，而不只是看最终是否通过，因为失败项本身就会提示下一轮修正方向。
              </p>
              <div className="mt-4">
                {robError ? (
                  <ErrorState text={robError} />
                ) : robMut.data ? (
                  <>
                    {robObj ? (
                      <div className="mb-3">
                        <Badge variant={robustPassed ? 'success' : 'danger'}>
                          {robustPassed ? '整体通过' : '整体未通过'}
                        </Badge>
                      </div>
                    ) : null}
                    {robTests.length > 0 ? (
                      <DataTable
                        rows={robTests}
                        columns={[
                          { key: 'name', label: '检验项', sortable: true },
                          {
                            key: 'passed',
                            label: '结果',
                            render: (value) => (
                              <Badge variant={value ? 'success' : 'danger'}>{value ? '通过' : '未通过'}</Badge>
                            ),
                          },
                          {
                            key: 'ic',
                            label: 'IC',
                            align: 'right',
                            render: (value) => fmtNum(Number(value ?? 0), 4),
                          },
                          {
                            key: 'pValue',
                            label: 'p-value',
                            align: 'right',
                            render: (value) => fmtNum(Number(value ?? 0), 4),
                          },
                        ]}
                      />
                    ) : robFallbackRows.length > 0 ? (
                      <DataTable rows={robFallbackRows} />
                    ) : (
                      <EmptyState text="接口已返回，但暂未解析出稳健性明细" />
                    )}
                  </>
                ) : (
                  <EmptyState text="运行一次稳健性检验后，这里会列出每个检验项的通过情况" />
                )}
              </div>
            </div>
          </div>
        </SectionCard>
        ) : null}
      </div>

      <div id="factor-mining" className="scroll-mt-24">
        {stageTab === 'mining' ? (
          <>
            <div className="panel-soft mb-4 rounded-[24px] px-4 py-3 text-sm text-text-secondary">
              基础研究链路确认后，再进入 AI 因子挖掘工作台，把候选生成、验证、研究记忆和候选池治理串成闭环。
            </div>
            <FactorMiningWorkbench />
          </>
        ) : null}
      </div>
    </PageContainer>
  );
}
