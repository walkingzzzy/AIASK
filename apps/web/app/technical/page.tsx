'use client';

import Link from 'next/link';
import { useEffect, useMemo, useRef, useState } from 'react';
import {
  PageContainer,
  TabBar,
  SectionCard,
  StockCodeInput,
  Badge,
  DataTable,
  KpiGrid,
  KpiCard,
} from '@/components/ui';
import { useApiQuery } from '@/hooks/use-api-query';
import { useStockCode } from '@/hooks/use-stock-code';
import { LoadingState, ErrorState, EmptyState } from '@/components/status-state';
import { LineChart, COLORS } from '@/components/charts';
import { extractArray, fmtNum } from '@/lib/data-utils';
import { exportCSV } from '@/lib/export';
import { StockLink } from '@/components/stock-link';
import { WatchlistButton } from '@/components/watchlist-button';
import { extractToolError, unwrapToolPayload } from '@/lib/tool-result';

const TABS = [
  { key: 'indicators', label: '技术指标' },
  { key: 'patterns', label: 'K线形态' },
  { key: 'available', label: '可用形态' },
] as const;

const INDICATOR_OPTIONS = ['MA', 'EMA', 'RSI', 'MACD', 'KDJ', 'BOLL', 'ATR', 'CCI', 'WR'];
const PERIOD_PRESETS = [
  { label: '日线 120', period: 'daily', limit: '120' },
  { label: '周线 60', period: 'weekly', limit: '60' },
  { label: '月线 36', period: 'monthly', limit: '36' },
] as const;
const INDICATOR_PRESETS = [
  { label: '常用三件套', values: ['MA', 'RSI', 'MACD'] },
  { label: '趋势跟踪', values: ['MA', 'EMA', 'MACD', 'BOLL'] },
  { label: '震荡观察', values: ['RSI', 'KDJ', 'CCI', 'WR'] },
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
type SubmittedPayload = Record<string, unknown>;

function parseIndicators(raw: unknown) {
  const obj = raw as Record<string, unknown> | null;
  if (!obj || typeof obj !== 'object') {
    return { series: [], summary: [] as { key: string; entries: [string, unknown][] }[] };
  }

  const series: { name: string; data: number[]; color: string }[] = [];
  const summary: { key: string; entries: [string, unknown][] }[] = [];
  let colorIndex = 0;

  for (const [key, value] of Object.entries(obj)) {
    if (Array.isArray(value) && value.length > 0 && typeof value[0] === 'number') {
      series.push({
        name: key.toUpperCase(),
        data: value,
        color: COLORS.series[colorIndex++ % COLORS.series.length],
      });
    } else if (value && typeof value === 'object' && !Array.isArray(value)) {
      const inner = value as Record<string, unknown>;
      let hasArrays = false;
      for (const [subKey, subValue] of Object.entries(inner)) {
        if (Array.isArray(subValue) && subValue.length > 0 && typeof subValue[0] === 'number') {
          series.push({
            name: `${key.toUpperCase()}_${subKey}`,
            data: subValue,
            color: COLORS.series[colorIndex++ % COLORS.series.length],
          });
          hasArrays = true;
        }
      }
      if (!hasArrays) {
        summary.push({ key: key.toUpperCase(), entries: Object.entries(inner) });
      }
    }
  }

  return { series, summary };
}

export default function TechnicalPage() {
  const [tab, setTab] = useState<Tab>('indicators');
  const { code, setCode, codeError, validate, trimmedCode, resolvedCode } = useStockCode('600519');
  const [period, setPeriod] = useState('daily');
  const [limit, setLimit] = useState('100');
  const [selectedIndicators, setSelectedIndicators] = useState<string[]>(['MA', 'RSI', 'MACD']);
  const [indicatorBody, setIndicatorBody] = useState<SubmittedPayload | null>(null);
  const [patternBody, setPatternBody] = useState<SubmittedPayload | null>(null);
  const [availablePath, setAvailablePath] = useState<string | null>(null);
  const availableQ = useApiQuery<unknown>(availablePath);
  const indicatorsQ = useApiQuery<unknown>(indicatorBody ? '/technical/indicators' : null, {
    body: indicatorBody ?? undefined,
    fetchOptions: { method: 'POST' },
  });
  const patternsQ = useApiQuery<unknown>(patternBody ? '/technical/patterns' : null, {
    body: patternBody ?? undefined,
    fetchOptions: { method: 'POST' },
  });

  const autoFetched = useRef(false);
  useEffect(() => {
    if (!autoFetched.current && resolvedCode) {
      autoFetched.current = true;
      setIndicatorBody({
        code: resolvedCode,
        indicators: selectedIndicators,
        period,
        limit: Number(limit),
      });
    }
  }, [limit, period, resolvedCode, selectedIndicators]);

  function toggleIndicator(indicator: string) {
    setSelectedIndicators((prev) =>
      prev.includes(indicator) ? prev.filter((item) => item !== indicator) : [...prev, indicator],
    );
  }

  function submit() {
    if (tab === 'available') {
      if (availablePath) availableQ.refetch();
      else setAvailablePath('/technical/available-patterns');
      return;
    }

    if (!validate()) return;

    const body: SubmittedPayload = {
      code: trimmedCode,
      period,
      limit: Number(limit),
    };

    if (tab === 'indicators') {
      body.indicators = selectedIndicators;
      if (indicatorBody && JSON.stringify(indicatorBody) === JSON.stringify(body)) indicatorsQ.refetch();
      else setIndicatorBody(body);
      return;
    }

    if (patternBody && JSON.stringify(patternBody) === JSON.stringify(body)) patternsQ.refetch();
    else setPatternBody(body);
  }

  function runRecommendedAnalysis() {
    if (tab === 'available') {
      if (availablePath) availableQ.refetch();
      else setAvailablePath('/technical/available-patterns');
      return;
    }

    const nextCode = trimmedCode || resolvedCode || '600519';
    const nextPeriod = 'daily';
    const nextLimit = 120;
    setCode(nextCode);
    setPeriod(nextPeriod);
    setLimit(String(nextLimit));

    if (tab === 'indicators') {
      const indicators = ['MA', 'RSI', 'MACD'];
      setSelectedIndicators(indicators);
      setIndicatorBody({
        code: nextCode,
        indicators,
        period: nextPeriod,
        limit: nextLimit,
      });
      return;
    }

    setPatternBody({
      code: nextCode,
      period: nextPeriod,
      limit: nextLimit,
    });
  }

  const activeQ = tab === 'available' ? availableQ : tab === 'indicators' ? indicatorsQ : patternsQ;
  const hasRequested =
    tab === 'available' ? availablePath != null : tab === 'indicators' ? indicatorBody != null : patternBody != null;
  const rawData = activeQ.data;
  const isAutoBootstrapping = tab === 'indicators' && resolvedCode && indicatorBody == null;
  const isPending =
    isAutoBootstrapping || (hasRequested && (activeQ.isPending || (activeQ.isFetching && rawData == null)));
  const isSubmitting = hasRequested && activeQ.isPending;
  const fetchError = activeQ.error;
  const mcpErr = rawData ? extractToolError(rawData) : null;
  const error = fetchError || mcpErr;
  const lastUpdatedText = activeQ.dataUpdatedAt ? new Date(activeQ.dataUpdatedAt).toLocaleString('zh-CN') : null;
  const requestSummary =
    tab === 'available'
      ? '当前查看：系统支持的 K 线形态库'
      : `最近一次参数：${trimmedCode || resolvedCode || '600519'} / ${period === 'daily' ? '日线' : period === 'weekly' ? '周线' : '月线'} / ${limit} 根${tab === 'indicators' ? ` / ${selectedIndicators.join('、')}` : ''}`;
  const unwrapped = useMemo(() => (rawData ? unwrapToolPayload(rawData) : null), [rawData]);
  const { series: indicatorSeries, summary: indicatorSummary } = useMemo(() => {
    if (tab !== 'indicators' || !unwrapped) return { series: [], summary: [] };
    return parseIndicators(unwrapped);
  }, [tab, unwrapped]);
  const rows = useMemo(() => {
    if (!unwrapped) return [];
    if (tab === 'indicators') return [];
    if (tab === 'patterns')
      return extractArray(unwrapped, 'patterns', 'results').filter((row) => row && typeof row === 'object');
    return extractArray(unwrapped, 'patterns', 'available').filter((row) => row && typeof row === 'object');
  }, [tab, unwrapped]);
  const hasIndicatorData = indicatorSeries.length > 0 || indicatorSummary.length > 0;
  const explanation = useMemo(() => {
    if (!rawData || error) return null;

    if (tab === 'indicators') {
      if (!hasIndicatorData) {
        return {
          title: '当前指标信号不足',
          description:
            '这通常意味着参数过窄或指标组合过多，建议先回到日线 120 根加常用三件套，确认趋势和动量是否一致。',
        };
      }
      return {
        title: '先用指标确认趋势与动量',
        description:
          '这一屏更适合回答“当前趋势是否延续、动量是否转弱”。看完后建议继续去个股详情、资金流或回测页验证信号是否具备可执行性。',
      };
    }

    if (tab === 'patterns') {
      return rows.length > 0
        ? {
            title: '形态结果适合做二次确认',
            description:
              'K 线形态更偏提示信号，不建议单独下结论。下一步优先叠加情绪、资金流和风险页，确认这类形态是否有资金或预期配合。',
          }
        : {
            title: '未识别到典型形态',
            description: '说明当前价格结构相对平稳，可切换周线或扩大观察窗口，再观察是否出现更明确的突破或反转模式。',
          };
    }

    return rows.length > 0
      ? {
          title: '先确认有哪些可用形态',
          description: '可用形态列表更适合作为识别前的准备动作。明确名称和方向后，再回到上一页对具体股票做筛查。',
        }
      : {
          title: '形态库暂未返回',
          description: '如果形态库为空，优先检查后端能力是否就绪；前端已经为“先看能力，再做筛查”的路径预留了解释层。',
        };
  }, [error, hasIndicatorData, rawData, rows.length, tab]);
  const actionLinks = useMemo(() => {
    const encodedCode = encodeURIComponent(trimmedCode || resolvedCode || '600519');
    return [
      { label: '个股详情', href: `/stock?code=${encodedCode}` },
      { label: '资金流', href: `/fund-flow?code=${encodedCode}` },
      { label: '情绪分析', href: `/sentiment?code=${encodedCode}` },
      { label: '风险页', href: `/risk?code=${encodedCode}` },
      { label: '回测', href: `/backtest?code=${encodedCode}` },
    ];
  }, [resolvedCode, trimmedCode]);
  const activeTabLabel = TABS.find((item) => item.key === tab)?.label ?? '技术分析';
  const focusCode = trimmedCode || resolvedCode || '600519';
  const periodLabel = period === 'daily' ? '日线' : period === 'weekly' ? '周线' : '月线';

  return (
    <PageContainer>
      <section className="page-hero mb-4 p-5 sm:p-6">
        <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_clamp(280px,25vw,380px)]">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="info">Technical Workspace</Badge>
              <Badge variant="neutral">{activeTabLabel}</Badge>
              <Badge variant={tab === 'available' ? 'info' : 'success'}>
                {tab === 'available' ? '形态库视图' : `${focusCode} · ${periodLabel}`}
              </Badge>
            </div>
            <h1 className="mb-0 mt-4 text-[2rem] font-semibold tracking-[-0.03em] text-text-primary sm:text-[2.4rem]">
              技术分析工作台
            </h1>
            <p className="mb-0 mt-3 max-w-3xl text-sm leading-7 text-text-secondary sm:text-[15px]">
              这里负责把指标、形态识别和能力清单收进同一套阅读流。先确定股票与周期，再判断趋势、动量和形态是否互相支持，最后再决定跳到资金流、情绪或回测页做交叉验证。
            </p>
            <div className="mt-5 flex flex-wrap gap-2">
              <button type="button" onClick={submit} disabled={isSubmitting} className={HERO_PRIMARY_BUTTON_CLS}>
                {isSubmitting
                  ? '处理中...'
                  : tab === 'available'
                    ? '查看可用形态'
                    : tab === 'indicators'
                      ? '计算指标'
                      : '识别形态'}
              </button>
              <button type="button" onClick={runRecommendedAnalysis} className={HERO_SECONDARY_BUTTON_CLS}>
                使用推荐参数
              </button>
            </div>

            <div className="mt-5 grid gap-3 sm:grid-cols-4">
              <div className="rounded-[24px] border border-white/45 bg-white/38 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.55)]">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">当前模式</div>
                <div className="mt-3 text-2xl font-semibold text-text-primary">{activeTabLabel}</div>
                <div className="mt-1 text-xs text-text-secondary">决定当前读取的是指标、形态还是能力库</div>
              </div>
              <div className="rounded-[24px] border border-white/45 bg-white/30 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.48)]">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">当前标的</div>
                <div className="mt-3 text-2xl font-semibold text-text-primary">
                  {tab === 'available' ? '-' : focusCode}
                </div>
                <div className="mt-1 text-xs text-text-secondary">
                  {tab === 'available' ? '能力库不依赖单只股票' : `${periodLabel} · ${limit} 根`}
                </div>
              </div>
              <div className="rounded-[24px] border border-white/45 bg-white/26 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.42)]">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">结果规模</div>
                <div className="mt-3 text-2xl font-semibold text-text-primary">
                  {tab === 'indicators' ? indicatorSeries.length + indicatorSummary.length : rows.length}
                </div>
                <div className="mt-1 text-xs text-text-secondary">帮助判断当前结果是否足够继续解读</div>
              </div>
              <div className="rounded-[24px] border border-white/45 bg-white/24 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.38)]">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">最近更新</div>
                <div className="mt-3 text-sm font-semibold leading-6 text-text-primary">{lastUpdatedText || '-'}</div>
              </div>
            </div>
          </div>

          <div className="grid gap-3">
            <div className={SIDE_PANEL_CLS}>
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">当前焦点</div>
              <div className="mt-3 text-base font-semibold text-text-primary">
                {tab === 'available' ? '可用形态库' : focusCode}
              </div>
              {resolvedCode && tab !== 'available' ? (
                <div className="mt-3 flex items-center gap-2">
                  <StockLink code={resolvedCode} name={resolvedCode} />
                  <WatchlistButton code={resolvedCode} name="" />
                </div>
              ) : null}
              <div className="mt-4 space-y-3">
                <div className={NOTE_CARD_CLS}>
                  查询摘要：<span className="font-medium text-text-primary">{requestSummary}</span>
                </div>
                <div className={NOTE_CARD_CLS}>
                  当前结论：
                  <span className="font-medium text-text-primary">{explanation?.title ?? '等待结果返回'}</span>
                </div>
              </div>
            </div>

            <div className={SIDE_PANEL_CLS}>
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">关联跳转</div>
              <div className="mt-4 flex flex-wrap gap-2">
                {actionLinks.map((link) => (
                  <Link key={link.href} href={link.href} className={`${CHIP_BUTTON_CLS} no-underline text-inherit`}>
                    {link.label}
                  </Link>
                ))}
              </div>
            </div>
          </div>
        </div>
      </section>

      {resolvedCode && tab !== 'available' ? (
        <KpiGrid cols={4} className="mb-4">
          <KpiCard title="当前标的" value={focusCode} />
          <KpiCard title="当前周期" value={periodLabel} />
          <KpiCard title="K 线数量" value={limit} />
          <KpiCard
            title="结果条数"
            value={tab === 'indicators' ? indicatorSeries.length + indicatorSummary.length : rows.length}
          />
        </KpiGrid>
      ) : null}

      <div className="panel-soft rounded-[28px] p-4 sm:p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="eyebrow">Technical Setup</div>
            <h2 className="mb-0 mt-2 text-xl font-semibold text-text-primary">参数工作台</h2>
            <p className="mb-0 mt-2 text-sm leading-7 text-text-secondary">
              这里负责确定分析对象、周期和指标组合。配置区只关注输入，不在这里展示结果图表，避免查询前后界面结构剧烈跳动。
            </p>
          </div>
          <div className="metric-tile rounded-[22px] px-4 py-3 text-sm text-text-secondary">
            当前模式：<span className="font-medium text-text-primary">{activeTabLabel}</span>
          </div>
        </div>

        <div className="mt-4">
          <TabBar tabs={TABS} active={tab} onChange={setTab} />
        </div>

        <SectionCard tabAttached>
          {tab !== 'available' ? (
            <div className="space-y-4">
              <div className="grid gap-4 xl:grid-cols-[260px_180px_120px_auto] xl:items-end">
                <StockCodeInput
                  id="technical-stock-code"
                  label="股票代码"
                  value={code}
                  onChange={setCode}
                  error={codeError}
                />
                <label htmlFor="technical-period" className="grid gap-2 text-xs text-text-secondary">
                  <span className="font-medium uppercase tracking-[0.12em] text-text-muted">观察周期</span>
                  <select
                    id="technical-period"
                    value={period}
                    onChange={(e) => setPeriod(e.target.value)}
                    className={FIELD_CLS}
                  >
                    <option value="daily">日线</option>
                    <option value="weekly">周线</option>
                    <option value="monthly">月线</option>
                  </select>
                </label>
                <label htmlFor="technical-limit" className="grid gap-2 text-xs text-text-secondary">
                  <span className="font-medium uppercase tracking-[0.12em] text-text-muted">K 线数量</span>
                  <input
                    id="technical-limit"
                    value={limit}
                    onChange={(e) => setLimit(e.target.value)}
                    className={FIELD_CLS}
                  />
                </label>
                <div className="flex flex-wrap items-center gap-2 xl:justify-end">
                  <button type="button" disabled={isSubmitting} onClick={submit} className={HERO_PRIMARY_BUTTON_CLS}>
                    {isSubmitting ? '处理中...' : tab === 'indicators' ? '计算指标' : '识别形态'}
                  </button>
                  <button type="button" onClick={runRecommendedAnalysis} className={HERO_SECONDARY_BUTTON_CLS}>
                    推荐参数
                  </button>
                </div>
              </div>

              <div className="flex flex-wrap gap-2">
                {PERIOD_PRESETS.map((preset) => (
                  <button
                    key={preset.label}
                    type="button"
                    onClick={() => {
                      setPeriod(preset.period);
                      setLimit(preset.limit);
                    }}
                    className={`${CHIP_BUTTON_CLS} ${period === preset.period && limit === preset.limit ? 'border-primary/35 bg-primary/12 text-primary' : 'text-text-secondary'}`}
                  >
                    {preset.label}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="flex flex-wrap items-center gap-2">
              <button type="button" disabled={isSubmitting} onClick={submit} className={HERO_PRIMARY_BUTTON_CLS}>
                {isSubmitting ? '处理中...' : '查看可用形态'}
              </button>
              <div className="text-sm text-text-secondary">先查看系统当前支持的 K 线形态库，再决定识别方向。</div>
            </div>
          )}

          {tab === 'indicators' ? (
            <div className="mt-4 space-y-4">
              <div>
                <div className="text-sm font-medium text-text-primary">指标选择</div>
                <div className="mt-3 flex flex-wrap gap-2">
                  {INDICATOR_OPTIONS.map((indicator) => (
                    <button
                      key={indicator}
                      type="button"
                      onClick={() => toggleIndicator(indicator)}
                      className={`${CHIP_BUTTON_CLS} ${selectedIndicators.includes(indicator) ? 'border-primary/35 bg-primary/12 text-primary' : 'text-text-secondary'}`}
                    >
                      {indicator}
                    </button>
                  ))}
                </div>
              </div>

              <div className="flex flex-wrap gap-2">
                {INDICATOR_PRESETS.map((preset) => (
                  <button
                    key={preset.label}
                    type="button"
                    onClick={() => setSelectedIndicators([...preset.values])}
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
            <h2 className="mb-0 mt-2 text-xl font-semibold text-text-primary">结果与解释</h2>
            <p className="mb-0 mt-2 text-sm leading-7 text-text-secondary">
              结果区先给出解释层，再展示图表或表格，帮助你决定要不要继续跳到情绪、资金流或回测页做第二次验证。
            </p>
          </div>
          <div className="metric-tile rounded-[22px] px-4 py-3 text-sm text-text-secondary">
            {requestSummary}
            {lastUpdatedText ? ` ｜ 更新：${lastUpdatedText}` : ''}
          </div>
        </div>

        {isPending ? <LoadingState text={isAutoBootstrapping ? '正在自动加载默认指标...' : '计算中...'} /> : null}
        {error ? <ErrorState text={error} hint="请检查参数后重试" /> : null}

        {!isPending && !rawData && !error ? (
          <EmptyState
            text={
              tab === 'available'
                ? '先查看当前支持的形态库，再决定识别方向'
                : tab === 'indicators'
                  ? '先选择股票、周期与指标组合，再开始技术分析'
                  : '先确认股票代码和 K 线数量，再识别近期形态'
            }
            hint={
              tab === 'available'
                ? '这一步适合先了解系统能识别哪些经典形态，再回到上一页做实盘筛查。'
                : tab === 'indicators'
                  ? '推荐先用日线 120 根加 MA / RSI / MACD 的组合，作为第一次分析入口。'
                  : '推荐先从日线 120 根开始，适合观察近期是否出现吞没、十字星或突破信号。'
            }
            action={
              <button type="button" onClick={runRecommendedAnalysis} className={CHIP_BUTTON_CLS}>
                使用推荐参数
              </button>
            }
          />
        ) : null}

        {rawData != null && !error && explanation ? (
          <div className="metric-tile mt-4 rounded-[24px] p-4">
            <div className="text-sm font-medium text-text-primary">{explanation.title}</div>
            <p className="mb-0 mt-1 text-sm text-text-secondary">{explanation.description}</p>
            <div className="mt-3 flex flex-wrap gap-2">
              {actionLinks.map((link) => (
                <Link key={link.href} href={link.href} className={`${CHIP_BUTTON_CLS} no-underline text-inherit`}>
                  {link.label}
                </Link>
              ))}
            </div>
          </div>
        ) : null}

        {rawData != null && !mcpErr && tab === 'indicators' ? (
          hasIndicatorData ? (
            <div className="mt-4 space-y-4">
              {indicatorSeries.length > 0 ? (
                <LineChart
                  categories={Array.from({ length: indicatorSeries[0].data.length }, (_, index) => String(index + 1))}
                  series={indicatorSeries}
                  height={360}
                />
              ) : null}
              {indicatorSummary.length > 0 ? (
                <div className="grid gap-3 lg:grid-cols-2">
                  {indicatorSummary.map((item) => (
                    <div key={item.key} className="metric-tile rounded-[24px] p-4">
                      <div className="text-sm font-medium text-text-primary">{item.key}</div>
                      <div className="mt-3 flex flex-wrap gap-x-4 gap-y-2 text-sm">
                        {item.entries.map(([entryKey, entryValue]) => (
                          <span key={entryKey} className="text-text-secondary">
                            {entryKey}：
                            <span className="ml-1 font-medium text-text-primary">
                              {typeof entryValue === 'number' ? fmtNum(entryValue, 2) : String(entryValue)}
                            </span>
                          </span>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              ) : null}
            </div>
          ) : (
            <EmptyState
              text="当前参数下暂无可展示的指标结果"
              hint="可以切换到日线 120 根，或减少指标数量后再次计算。"
            />
          )
        ) : null}

        {rawData != null && !mcpErr && tab === 'patterns' ? (
          rows.length > 0 ? (
            <div className="mt-4">
              <DataTable
                rows={rows as Record<string, unknown>[]}
                columns={[
                  { key: 'date', label: '日期' },
                  { key: 'pattern', label: '形态' },
                  { key: 'name', label: '名称' },
                  {
                    key: 'type',
                    label: '类型',
                    render: (value) => (
                      <Badge
                        variant={
                          String(value) === 'bullish' ? 'success' : String(value) === 'bearish' ? 'danger' : 'info'
                        }
                      >
                        {String(value)}
                      </Badge>
                    ),
                  },
                  { key: 'reliability', label: '可靠性' },
                ]}
                onExport={() => exportCSV(rows as Record<string, unknown>[], 'K线形态')}
              />
            </div>
          ) : (
            <EmptyState
              text="近期未识别到典型 K 线形态"
              hint="这通常意味着价格波动较平缓，可以放大观察窗口或切换到周线再试。"
            />
          )
        ) : null}

        {rawData != null && !mcpErr && tab === 'available' ? (
          rows.length > 0 ? (
            <div className="mt-4">
              <DataTable
                rows={rows as Record<string, unknown>[]}
                columns={[
                  { key: 'name', label: '名称' },
                  { key: 'pattern', label: '代码' },
                  {
                    key: 'bullish',
                    label: '方向',
                    render: (value) => (
                      <Badge variant={value === true ? 'success' : value === false ? 'danger' : 'info'}>
                        {value === true ? '看涨' : value === false ? '看跌' : '双向'}
                      </Badge>
                    ),
                  },
                  { key: 'reliability', label: '可靠性' },
                ]}
                onExport={() => exportCSV(rows as Record<string, unknown>[], '可用形态')}
              />
            </div>
          ) : (
            <EmptyState
              text="当前没有返回可用形态列表"
              hint="可稍后重试；如果持续为空，优先检查后端形态能力是否已就绪。"
            />
          )
        ) : null}
      </div>
    </PageContainer>
  );
}
