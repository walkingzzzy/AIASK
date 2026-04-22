'use client';

import { useMemo, useState } from 'react';
import ResultWorkbench from '@/components/result-workbench';
import { PageContainer, SectionCard, StockCodeInput, Badge, TabBar } from '@/components/ui';
import { LineChart, BarChart } from '@/components/charts';
import { useApiQuery } from '@/hooks/use-api-query';
import { useApiMutation } from '@/hooks/use-api-mutation';
import { useMobile } from '@/hooks/use-mobile';
import { usePageActions } from '@/hooks/use-page-actions';
import { usePageContext } from '@/hooks/use-page-context';
import { useStockCode } from '@/hooks/use-stock-code';
import { EmptyState, ErrorState, LoadingState } from '@/components/status-state';
import { fmtNum } from '@/lib/data-utils';
import { buildLocalResultContract, defaultWorkbenchTask, evidenceToSummary } from '@/lib/result-workbench';
import { RESPONSIVE_BREAKPOINTS } from '@/lib/responsive-layout';

type FactorItem = { name: string; description: string; category: string };
type LibraryResponse = { data?: { factors?: FactorItem[] } };
type IcResponse = { data?: { ic?: number; ic_ir?: number; p_value?: number; [k: string]: unknown } };
type BacktestResponse = { data?: { group_returns?: Record<string, number>; [k: string]: unknown } };
type IcHistoryItem = { date: string; ic_value?: number; rank_ic?: number; stock_count?: number };
type IcHistoryResponse = { data?: { history?: IcHistoryItem[]; [k: string]: unknown } };
type DecayPoint = { date: string; value: number };
type DecayResponse = {
  data?: {
    half_life?: number | null;
    sample_count?: number;
    decay_curve?: DecayPoint[];
    [k: string]: unknown;
  };
};

const DEFAULT_FACTOR_UNIVERSE = [
  '600519',
  '000858',
  '300750',
  '601318',
  '000001',
  '600036',
  '601166',
  '000333',
  '600276',
  '601899',
  '002594',
  '000651',
];
const HERO_PRIMARY_BUTTON_CLS =
  'inline-flex cursor-pointer items-center justify-center rounded-full bg-primary px-4 py-2 text-sm font-medium text-white shadow-[0_20px_40px_-24px_rgba(11,107,203,0.52)] transition hover:-translate-y-0.5 hover:shadow-[0_24px_46px_-24px_rgba(11,107,203,0.58)] disabled:cursor-not-allowed disabled:opacity-50';
const HERO_SECONDARY_BUTTON_CLS =
  'action-chip cursor-pointer text-sm text-text-primary shadow-[0_16px_32px_-24px_rgba(15,23,42,0.28)]';
const NOTE_CARD_CLS = 'metric-tile rounded-[22px] p-3 text-xs text-text-secondary';
const SIDE_PANEL_CLS = 'panel-soft rounded-[28px] p-4 sm:p-5';
const RESULT_TABS = [
  { key: 'setup', label: '配置' },
  { key: 'ic', label: 'IC' },
  { key: 'decay', label: '衰减' },
  { key: 'groups', label: '分组收益' },
] as const;
type ResultTab = (typeof RESULT_TABS)[number]['key'];

export default function FactorAnalysisPage() {
  const compactLayout = useMobile(RESPONSIVE_BREAKPOINTS.mobile);
  const [libraryLoaded, setLibraryLoaded] = useState(false);
  const [resultTab, setResultTab] = useState<ResultTab>('setup');
  const libraryQ = useApiQuery<LibraryResponse>(libraryLoaded ? '/factor/library' : null);
  const icApi = useApiMutation<IcResponse>();
  const btApi = useApiMutation<BacktestResponse>();
  const [icHistoryPath, setIcHistoryPath] = useState<string | null>(null);
  const [decayPath, setDecayPath] = useState<string | null>(null);
  const icHistoryQ = useApiQuery<IcHistoryResponse>(icHistoryPath);
  const decayQ = useApiQuery<DecayResponse>(decayPath);
  const { code, setCode, codeError, validate, trimmedCode } = useStockCode('600519');
  const [factor, setFactor] = useState('momentum');
  const sampleUniverse = useMemo(
    () => Array.from(new Set([trimmedCode || '600519', ...DEFAULT_FACTOR_UNIVERSE])).filter(Boolean),
    [trimmedCode],
  );

  function loadLibrary() {
    if (!libraryLoaded) setLibraryLoaded(true);
  }

  const factors = useMemo(() => {
    const raw = libraryQ.data?.data?.factors ?? libraryQ.data?.data ?? [];
    return Array.isArray(raw) ? (raw as FactorItem[]) : [];
  }, [libraryQ.data]);

  function runAnalysis() {
    if (!validate()) return;
    const body = { factor_name: factor, stock_codes: sampleUniverse };
    icApi.trigger('/factor/ic', { method: 'POST' }, body);
    btApi.trigger('/factor/backtest', { method: 'POST' }, body);
    setIcHistoryPath(`/factor/ic-history?factor_name=${encodeURIComponent(factor)}&period=20&limit=60`);
    setDecayPath(`/factor/decay?factor_name=${encodeURIComponent(factor)}&period=20&limit=60`);
    setResultTab('ic');
  }

  const ic = icApi.data?.data;
  const groupReturns = btApi.data?.data?.group_returns;
  const groupBars = useMemo(() => {
    if (!groupReturns) return { cats: [] as string[], vals: [] as number[] };
    const entries = Object.entries(groupReturns).sort(([a], [b]) => a.localeCompare(b));
    return { cats: entries.map(([key]) => key), vals: entries.map(([, value]) => Number(value) || 0) };
  }, [groupReturns]);

  const icHistory = useMemo(() => {
    const raw = icHistoryQ.data?.data?.history ?? icHistoryQ.data?.data ?? [];
    const list = Array.isArray(raw) ? (raw as IcHistoryItem[]) : [];
    if (!list.length) return null;
    const sorted = [...list].sort((a, b) => a.date.localeCompare(b.date));
    return {
      dates: sorted.map((item) => item.date),
      ic: sorted.map((item) => Number(item.ic_value ?? 0)),
      rankIc: sorted.map((item) => Number(item.rank_ic ?? 0)),
    };
  }, [icHistoryQ.data]);

  const decayView = useMemo(() => {
    const raw = decayQ.data?.data?.decay_curve ?? decayQ.data?.data ?? [];
    const curve = Array.isArray(raw) ? (raw as DecayPoint[]) : [];
    const halfLifeRaw = decayQ.data?.data?.half_life;
    const sampleCountRaw = decayQ.data?.data?.sample_count;
    if (!curve.length && halfLifeRaw == null && sampleCountRaw == null) return null;
    return {
      halfLife: typeof halfLifeRaw === 'number' ? halfLifeRaw : null,
      sampleCount: Number(sampleCountRaw ?? curve.length) || 0,
      dates: curve.map((item) => item.date),
      values: curve.map((item) => Number(item.value ?? 0)),
    };
  }, [decayQ.data]);

  const loading = icApi.isPending || btApi.isPending || icHistoryQ.isFetching || decayQ.isFetching;
  const error = codeError || icApi.error || btApi.error || icHistoryQ.error || decayQ.error;
  const analysisReady = Boolean(ic || decayView || groupBars.cats.length > 0 || icHistory);
  const factorOptions =
    factors.length > 0 ? factors : [{ name: factor, description: '当前默认研究因子', category: 'default' }];
  const activeFactorMeta = factorOptions.find((item) => item.name === factor);
  const activeTabLabel = RESULT_TABS.find((item) => item.key === resultTab)?.label ?? '配置';
  const factorAnalysisActions = useMemo(
    () => [
      {
        id: 'factor-analysis.load-library',
        label: libraryLoaded ? '刷新因子库' : '加载因子库',
        description: '加载或刷新可选因子列表',
        keywords: ['因子库', '刷新'],
        scope: 'page' as const,
        pageKey: 'factor-analysis',
        run: () => {
          loadLibrary();
          if (libraryLoaded) {
            void libraryQ.refetch();
          }
          return { message: libraryLoaded ? '已刷新因子库' : '已加载因子库' };
        },
      },
      {
        id: 'factor-analysis.run',
        label: '运行分析',
        description: '同时发起 IC、分组收益和衰减分析',
        keywords: ['因子', '分析'],
        scope: 'page' as const,
        pageKey: 'factor-analysis',
        run: () => {
          runAnalysis();
          return { message: `已发起 ${factor} 的单因子分析` };
        },
      },
      {
        id: 'factor-analysis.view-ic',
        label: '切到 IC',
        description: '把视图切到 IC 时序与快判指标',
        keywords: ['IC', '切换视图'],
        scope: 'page' as const,
        pageKey: 'factor-analysis',
        run: () => {
          setResultTab('ic');
          return { message: '已切到 IC 视图' };
        },
      },
    ],
    [factor, libraryLoaded, libraryQ],
  );
  usePageActions(factorAnalysisActions);
  const factorAnalysisSummary = analysisReady
    ? `当前因子 ${factor} 已生成单因子分析，样本 ${sampleUniverse.length} 只，IC ${fmtNum(ic?.ic ?? null, 4)}，当前视图 ${activeTabLabel}。`
    : `当前因子 ${factor} 尚未生成分析结果，样本 ${sampleUniverse.length} 只，建议先运行一次分析再判断 IC、衰减和分组收益。`;
  const factorAnalysisResult = buildLocalResultContract({
    summary: factorAnalysisSummary,
    availableViews: analysisReady ? ['compare', 'visual'] : [],
    pageActions: factorAnalysisActions,
    preferredActionIds: ['factor-analysis.run', 'factor-analysis.view-ic', 'factor-analysis.load-library'],
    recommendedLinks: [
      { id: 'factor-analysis-link-factor', label: '回因子研究工作台', href: '/factor' },
      { id: 'factor-analysis-link-research', label: '去研究页', href: `/research?code=${encodeURIComponent(trimmedCode || '600519')}` },
      { id: 'factor-analysis-link-assistant', label: '继续追问 Copilot', href: `/assistant?from=factor-analysis&symbol=${encodeURIComponent(trimmedCode || '600519')}` },
    ],
    evidence: [
      { label: '当前因子', value: factor },
      { label: '样本数量', value: String(sampleUniverse.length) },
      { label: '当前视图', value: activeTabLabel },
      { label: 'IC', value: fmtNum(ic?.ic ?? null, 4) },
      { label: 'IC IR', value: fmtNum(ic?.ic_ir ?? null, 4) },
      { label: '分组数', value: String(groupBars.cats.length) },
    ],
    riskNotes: [
      ...(error ? [error] : []),
      ...(analysisReady ? [] : ['当前还没有生成单因子分析结果。']),
      ...(decayView?.halfLife != null && decayView.halfLife < 5 ? ['当前信号半衰期较短，落地前需要确认稳定性。'] : []),
    ],
    platformMeta: {
      sourceTool: 'factor-analysis',
      sourceChain: ['factor/ic', 'factor/backtest', 'factor/decay'],
      degraded: Boolean(error),
      fallbackReason: [error].filter((item): item is string => Boolean(item)),
    },
    workbenchTask: defaultWorkbenchTask('factor-analysis', `复查因子 ${factor}`, '/factor-analysis', 'factor-analysis-review', {
      factor,
      code: trimmedCode || '600519',
      ic: ic?.ic ?? null,
      tab: resultTab,
    }),
  });
  usePageContext({
    pageKey: 'factor-analysis',
    title: '因子洞察工作台',
    summary: factorAnalysisSummary,
    objectType: 'factor',
    objectId: factor,
    resultType: 'factor-analysis',
    tags: [
      factor,
      `${sampleUniverse.length} 样本`,
      activeTabLabel,
      analysisReady ? '已生成结果' : '待运行',
    ],
    suggestions: [
      '总结当前单因子是否值得继续深挖',
      '如果 IC、衰减和分组收益不一致，解释冲突原因',
      '给出下一步应回因子研究页还是继续做组合验证',
    ],
    recommendedActions: factorAnalysisResult.recommendedActions ?? [],
    recommendedLinks: factorAnalysisResult.recommendedLinks ?? [],
    evidenceSummary: evidenceToSummary(factorAnalysisResult.evidence),
    riskNotes: factorAnalysisResult.riskNotes ?? [],
    freshness: factorAnalysisResult.freshness ?? null,
    raw: {
      factor,
      code: trimmedCode || '600519',
      resultTab,
      sampleSize: sampleUniverse.length,
      ic: ic?.ic ?? null,
      halfLife: decayView?.halfLife ?? null,
    },
  });

  return (
    <PageContainer className="app-theme-strategy">
      <section className="page-hero mb-4 p-5 sm:p-6">
        <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_320px]">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="info">Factor Insight</Badge>
              <Badge variant={libraryLoaded ? 'success' : 'neutral'}>
                {libraryLoaded ? `因子库 ${factors.length || 1} 项` : '因子库待加载'}
              </Badge>
              <Badge variant={analysisReady ? 'success' : 'warning'}>
                {analysisReady ? '已生成分析结果' : '等待首次分析'}
              </Badge>
              <Badge variant="neutral">{trimmedCode || '600519'}</Badge>
            </div>

            <h1 className="mb-0 mt-4 text-[2rem] font-semibold tracking-[-0.03em] text-text-primary sm:text-[2.4rem]">
              因子洞察工作台
            </h1>
            <p className="mb-0 mt-3 max-w-3xl text-sm leading-7 text-text-secondary sm:text-[15px]">
              单因子页现在只保留一个活动视图。先确认标的与因子，再逐步看 IC、衰减和分组收益，不再把三块证据同时铺开。
            </p>

            {!compactLayout ? (
              <div className="mt-5 flex flex-wrap gap-2">
                <button type="button" onClick={loadLibrary} className={HERO_PRIMARY_BUTTON_CLS}>
                  {libraryLoaded ? '刷新因子候选' : '加载因子库'}
                </button>
                <button type="button" onClick={runAnalysis} disabled={loading} className={HERO_SECONDARY_BUTTON_CLS}>
                  {loading ? '分析中...' : '运行分析'}
                </button>
              </div>
            ) : null}

            <div
              data-testid="page-primary-status"
              className="mt-4 rounded-[22px] border border-white/50 bg-white/28 px-4 py-3 text-sm shadow-[inset_0_1px_0_rgba(255,255,255,0.68)]"
            >
              <div className="font-medium text-text-primary">
                当前因子：{factor} ｜ 样本 {sampleUniverse.length} 只 ｜ 当前视图：{activeTabLabel}
              </div>
              <p className="mt-1 mb-0 text-xs leading-6 text-text-secondary">
                {analysisReady
                  ? `IC ${fmtNum(ic?.ic ?? null, 4)} ｜ 半衰期 ${decayView?.halfLife == null ? '-' : decayView.halfLife}`
                  : '先运行一次分析，再决定继续看 IC、衰减还是分组收益。'}
              </p>
            </div>
          </div>

          <details className={SIDE_PANEL_CLS} open={!compactLayout}>
            <summary className="cursor-pointer list-none text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">
              研究顺序
            </summary>
            <div className="mt-4 space-y-3">
              <div className={NOTE_CARD_CLS}>1. 先确认因子名称与股票样本。</div>
              <div className={NOTE_CARD_CLS}>2. 再看 IC 和分组收益。</div>
              <div className={NOTE_CARD_CLS}>3. 最后看衰减，确认它是否稳定。</div>
              <div className={NOTE_CARD_CLS}>
                当前说明：
                <span className="font-medium text-text-primary"> {activeFactorMeta?.description || '当前默认研究因子'}</span>
              </div>
            </div>
          </details>
        </div>
      </section>

      <ResultWorkbench pageKey="factor-analysis" title="因子洞察结果工作台" result={factorAnalysisResult} />

      {loading ? <LoadingState text="因子分析中..." /> : null}
      {error ? <ErrorState text={error} /> : null}

      <div className="panel-soft rounded-[28px] p-4 sm:p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="eyebrow">Analysis Workspace</div>
            <h2 className="mb-0 mt-2 text-xl font-semibold text-text-primary">单因子快判</h2>
            <p className="mb-0 mt-2 text-sm leading-7 text-text-secondary">
              默认只展开一个活动视图。先配参数，再依次看 IC、衰减和分组收益。
            </p>
          </div>
          <div className="metric-tile rounded-[22px] px-4 py-3 text-sm text-text-secondary">
            当前状态：<span className="font-medium text-text-primary">{analysisReady ? '已生成结果' : '等待运行'}</span>
          </div>
        </div>

        <div className="mt-4">
          <TabBar tabs={RESULT_TABS} active={resultTab} onChange={(key) => setResultTab(key as ResultTab)} />
        </div>

        <SectionCard tabAttached>
          {resultTab === 'setup' ? (
            <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_320px]">
              <div className="panel-soft rounded-[26px] p-4 sm:p-5">
                <div className="grid gap-3 lg:grid-cols-[180px_minmax(0,1fr)_auto] lg:items-end">
                  <StockCodeInput
                    id="factor-analysis-stock-code"
                    label="股票代码"
                    value={code}
                    onChange={setCode}
                    error={codeError}
                    placeholder="如 600519"
                  />
                  <label htmlFor="factor-analysis-factor" className="grid gap-1 text-xs text-text-secondary">
                    <span>分析维度</span>
                    <select
                      id="factor-analysis-factor"
                      value={factor}
                      onChange={(e) => setFactor(e.target.value)}
                      onFocus={loadLibrary}
                      className="w-full min-w-[220px] text-sm text-text-primary"
                    >
                      {factorOptions.map((item) => (
                        <option key={item.name} value={item.name}>
                          {item.name} - {item.description}
                        </option>
                      ))}
                    </select>
                  </label>
                  <button type="button" onClick={runAnalysis} disabled={loading} className={HERO_PRIMARY_BUTTON_CLS}>
                    {loading ? '分析中...' : '运行分析'}
                  </button>
                </div>
                <div className={`${NOTE_CARD_CLS} mt-4`}>
                  当前会使用目标股票加默认样本池共 {sampleUniverse.length} 只股票，IC 历史窗口为 20 期，最多展示 60 个观察点。
                </div>
              </div>
              <details className={SIDE_PANEL_CLS} open={!compactLayout}>
                <summary className="cursor-pointer list-none text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">
                  结果预期
                </summary>
                <div className="mt-4 space-y-3">
                  <div className={NOTE_CARD_CLS}>IC 与 IC IR 用来判断信号方向和稳定性。</div>
                  <div className={NOTE_CARD_CLS}>分组收益用来判断排序后能否形成收益层次。</div>
                  <div className={NOTE_CARD_CLS}>衰减曲线帮助判断信号是不是来得快、去得也快。</div>
                </div>
              </details>
            </div>
          ) : null}

          {resultTab === 'ic' ? (
            <div className="space-y-4">
              <div className="grid gap-3 sm:grid-cols-3">
                <div className={NOTE_CARD_CLS}>IC：<span className="font-medium text-text-primary"> {fmtNum(ic?.ic ?? null, 4)}</span></div>
                <div className={NOTE_CARD_CLS}>IC IR：<span className="font-medium text-text-primary"> {fmtNum(ic?.ic_ir ?? null, 4)}</span></div>
                <div className={NOTE_CARD_CLS}>P-Value：<span className="font-medium text-text-primary"> {fmtNum(ic?.p_value ?? null, 4)}</span></div>
              </div>
              {icHistory ? (
                <LineChart
                  categories={icHistory.dates}
                  series={[
                    { name: 'IC', data: icHistory.ic, color: '#1a73e8' },
                    { name: 'Rank IC', data: icHistory.rankIc, color: '#f59e0b' },
                  ]}
                  height={260}
                  yAxisName="IC值"
                />
              ) : (
                <EmptyState text="运行分析后，这里会显示 IC 与 Rank IC 的时序走势。" />
              )}
            </div>
          ) : null}

          {resultTab === 'decay' ? (
            <div className="space-y-4">
              <div className="grid gap-3 sm:grid-cols-2">
                <div className={NOTE_CARD_CLS}>
                  信号半衰期：<span className="font-medium text-text-primary"> {decayView?.halfLife == null ? '-' : decayView.halfLife}</span>
                </div>
                <div className={NOTE_CARD_CLS}>
                  衰减样本数：<span className="font-medium text-text-primary"> {decayView ? decayView.sampleCount : '-'}</span>
                </div>
              </div>
              {decayView && decayView.dates.length > 0 ? (
                <LineChart
                  categories={decayView.dates}
                  series={[{ name: 'Decay', data: decayView.values, color: '#10b981' }]}
                  height={240}
                  yAxisName="相对强度"
                />
              ) : (
                <EmptyState text="运行分析后，这里会显示信号衰减曲线与半衰期。" />
              )}
            </div>
          ) : null}

          {resultTab === 'groups' ? (
            <div className="space-y-4">
              <div className={NOTE_CARD_CLS}>这一层看的是“排序之后有没有收益层次”，它和 IC 一起构成单因子快判的主要证据。</div>
              {groupBars.cats.length > 0 ? (
                <BarChart
                  items={groupBars.cats.map((cat, index) => ({ label: cat, value: groupBars.vals[index] }))}
                  height={280}
                  yAxisName="收益率"
                  colorByValue
                />
              ) : (
                <EmptyState text="运行分析后，这里会展示分组收益柱状图。" />
              )}
            </div>
          ) : null}
        </SectionCard>
      </div>
    </PageContainer>
  );
}
