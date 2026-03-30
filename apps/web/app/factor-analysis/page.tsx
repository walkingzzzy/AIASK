'use client';

import { useMemo, useState } from 'react';
import { PageContainer, SectionCard, StockCodeInput, KpiCard, KpiGrid, Badge } from '@/components/ui';
import { LineChart, BarChart } from '@/components/charts';
import { useApiQuery } from '@/hooks/use-api-query';
import { useApiMutation } from '@/hooks/use-api-mutation';
import { useStockCode } from '@/hooks/use-stock-code';
import { EmptyState, ErrorState, LoadingState } from '@/components/status-state';
import { fmtNum } from '@/lib/data-utils';

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
const CHIP_LINK_CLS = 'action-chip text-xs no-underline text-inherit';
const NOTE_CARD_CLS = 'metric-tile rounded-[22px] p-3 text-xs text-text-secondary';
const SIDE_PANEL_CLS = 'panel-soft rounded-[28px] p-4 sm:p-5';

export default function FactorAnalysisPage() {
  const [libraryLoaded, setLibraryLoaded] = useState(false);
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

  return (
    <PageContainer className="app-theme-strategy">
      <section className="page-hero mb-4 p-5 sm:p-6">
        <div className="grid gap-5 xl:grid-cols-[minmax(0,1.2fr)_380px]">
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
              这个页面聚焦单一因子的快速判断: 先确认目标股票和分析维度，再同时拉起 IC、分组收益、IC
              历史与衰减曲线，快速判断一个因子是不是值得继续深挖。
            </p>

            <div className="mt-5 flex flex-wrap gap-2">
              <button type="button" onClick={loadLibrary} className={HERO_PRIMARY_BUTTON_CLS}>
                {libraryLoaded ? '刷新因子候选' : '加载因子库'}
              </button>
              <button type="button" onClick={runAnalysis} disabled={loading} className={HERO_SECONDARY_BUTTON_CLS}>
                {loading ? '分析中...' : '运行分析'}
              </button>
              <a href="#factor-analysis-ic" className={CHIP_LINK_CLS}>
                看 IC 走势
              </a>
              <a href="#factor-analysis-decay" className={CHIP_LINK_CLS}>
                看衰减曲线
              </a>
              <a href="#factor-analysis-backtest" className={CHIP_LINK_CLS}>
                看分组收益
              </a>
            </div>

            <div className="mt-5 grid gap-3 sm:grid-cols-4">
              <div className="rounded-[24px] border border-white/45 bg-white/38 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.55)]">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">目标股票</div>
                <div className="mt-3 text-2xl font-semibold text-text-primary">{trimmedCode || '600519'}</div>
                <div className="mt-1 text-xs text-text-secondary">与默认样本池合并后统一做横截面分析</div>
              </div>
              <div className="rounded-[24px] border border-white/45 bg-white/30 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.48)]">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">分析维度</div>
                <div className="mt-3 text-2xl font-semibold text-text-primary">{factor}</div>
                <div className="mt-1 text-xs text-text-secondary">{activeFactorMeta?.category || '默认分类'}</div>
              </div>
              <div className="rounded-[24px] border border-white/45 bg-white/26 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.42)]">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">样本范围</div>
                <div className="mt-3 text-2xl font-semibold text-text-primary">{sampleUniverse.length}</div>
                <div className="mt-1 text-xs text-text-secondary">IC 窗口 20 期，最多展示 60 个观察点</div>
              </div>
              <div className="rounded-[24px] border border-white/45 bg-white/24 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.38)]">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">当前状态</div>
                <div className="mt-3 text-2xl font-semibold text-text-primary">
                  {analysisReady ? fmtNum(ic?.ic ?? null, 4) : '-'}
                </div>
                <div className="mt-1 text-xs text-text-secondary">
                  {analysisReady ? '已生成第一层信号证据' : '先运行一次分析再看时序与衰减'}
                </div>
              </div>
            </div>
          </div>

          <div className="grid gap-3">
            <div className={SIDE_PANEL_CLS}>
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">建议顺序</div>
              <div className="mt-4 space-y-3">
                <div className={NOTE_CARD_CLS}>1. 先确认因子名称与股票样本，避免在错误的研究语境上继续放大分析。</div>
                <div className={NOTE_CARD_CLS}>2. 再看 IC、Rank IC 和分组收益，确认这个因子是否真的有方向性。</div>
                <div className={NOTE_CARD_CLS}>
                  3. 最后看 IC 时序和衰减曲线，判断它是稳定信号还是只在局部时间窗口有效。
                </div>
              </div>
            </div>

            <div className={SIDE_PANEL_CLS}>
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">当前配置</div>
              <div className="mt-4 space-y-3">
                <div className={NOTE_CARD_CLS}>
                  因子：
                  <span className="font-medium text-text-primary">{factor}</span>
                </div>
                <div className={NOTE_CARD_CLS}>
                  样本池：
                  <span className="font-medium text-text-primary">{sampleUniverse.length} 只股票</span>
                </div>
                <div className={NOTE_CARD_CLS}>
                  因子说明：
                  <span className="font-medium text-text-primary">
                    {activeFactorMeta?.description || '当前默认使用单因子快速分析路径'}
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {loading ? <LoadingState text="因子分析中..." /> : null}
      {error ? <ErrorState text={error} /> : null}

      <KpiGrid cols={5} className="mb-4">
        <KpiCard title="IC" value={analysisReady ? fmtNum(ic?.ic ?? null, 4) : null} />
        <KpiCard title="IC IR" value={analysisReady ? fmtNum(ic?.ic_ir ?? null, 4) : null} />
        <KpiCard title="P-Value" value={analysisReady ? fmtNum(ic?.p_value ?? null, 4) : null} />
        <KpiCard title="信号半衰期" value={decayView?.halfLife == null ? null : `${decayView.halfLife}`} />
        <KpiCard title="衰减样本数" value={decayView ? `${decayView.sampleCount}` : null} />
      </KpiGrid>

      <SectionCard className="p-4 sm:p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="eyebrow">Analysis Setup</div>
            <h3 className="mt-2 mb-0 text-xl font-semibold text-text-primary">分析配置</h3>
            <p className="mb-0 mt-2 text-sm leading-7 text-text-secondary">
              这一步只保留必要输入，减少“单因子快判”场景下的配置噪音。因子库可以提前加载，也可以在选择器聚焦时自动拉起。
            </p>
          </div>
        </div>

        <div className="mt-4 grid gap-4 xl:grid-cols-[minmax(0,1.1fr)_320px]">
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
              当前会使用目标股票加默认样本池共 {sampleUniverse.length} 只股票，IC 历史窗口为 20 期，最多展示 60
              个观察点。
            </div>
          </div>

          <div className={SIDE_PANEL_CLS}>
            <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">结果预期</div>
            <div className="mt-4 space-y-3">
              <div className={NOTE_CARD_CLS}>IC 与 IC IR 会告诉你信号方向和稳定性。</div>
              <div className={NOTE_CARD_CLS}>分组收益用来判断排序后是否能形成清晰收益层次。</div>
              <div className={NOTE_CARD_CLS}>衰减曲线帮助判断信号是不是来得快、去得也快。</div>
            </div>
          </div>
        </div>
      </SectionCard>

      <div id="factor-analysis-ic" className="scroll-mt-24">
        <SectionCard className="p-4 sm:p-5">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="eyebrow">Signal Evidence</div>
              <h3 className="mt-2 mb-0 text-xl font-semibold text-text-primary">IC 时序走势</h3>
              <p className="mb-0 mt-2 text-sm leading-7 text-text-secondary">
                这里同时看 IC 和 Rank IC，判断同一因子在时间序列上是持续有效，还是只在某段行情里短暂成立。
              </p>
            </div>
            <a href="#factor-analysis-decay" className={CHIP_LINK_CLS}>
              继续看衰减
            </a>
          </div>

          <div className="mt-4">
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
        </SectionCard>
      </div>

      <div id="factor-analysis-decay" className="scroll-mt-24">
        <SectionCard className="p-4 sm:p-5">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="eyebrow">Decay Evidence</div>
              <h3 className="mt-2 mb-0 text-xl font-semibold text-text-primary">信号衰减曲线</h3>
              <p className="mb-0 mt-2 text-sm leading-7 text-text-secondary">
                衰减越快，因子越可能只适合短窗口或更高频的执行节奏；衰减越慢，说明它更有机会支持中短期持有。
              </p>
            </div>
            <a href="#factor-analysis-backtest" className={CHIP_LINK_CLS}>
              继续看分组收益
            </a>
          </div>

          <div className="mt-4">
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
        </SectionCard>
      </div>

      <div id="factor-analysis-backtest" className="scroll-mt-24">
        <SectionCard className="p-4 sm:p-5">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="eyebrow">Cross-Section Return</div>
              <h3 className="mt-2 mb-0 text-xl font-semibold text-text-primary">因子分组回测收益</h3>
              <p className="mb-0 mt-2 text-sm leading-7 text-text-secondary">
                这一层看的是“排序之后有没有收益层次”，它和 IC 一起构成单因子快判的主要证据。
              </p>
            </div>
          </div>

          <div className="mt-4">
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
        </SectionCard>
      </div>
    </PageContainer>
  );
}
