'use client';

import Link from 'next/link';
import { useEffect, useMemo, useRef, useState } from 'react';
import LightOverviewHero from '@/components/light-overview-hero';
import ProgressiveWorkbenchSection from '@/components/progressive-workbench-section';
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
import { usePageActions } from '@/hooks/use-page-actions';
import { usePageContext } from '@/hooks/use-page-context';
import { useMobile } from '@/hooks/use-mobile';
import { useStockCode } from '@/hooks/use-stock-code';
import { LoadingState, ErrorState, EmptyState } from '@/components/status-state';
import { LineChart, COLORS } from '@/components/charts';
import { extractArray } from '@/lib/data-utils';
import { exportCSV } from '@/lib/export';
import { buildLocalResultContract, defaultWorkbenchTask, evidenceToSummary } from '@/lib/result-workbench';
import { StockLink } from '@/components/stock-link';
import { WatchlistButton } from '@/components/watchlist-button';
import { extractToolError, unwrapToolPayload } from '@/lib/tool-result';
import { RESPONSIVE_BREAKPOINTS } from '@/lib/responsive-layout';

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
  const compactLayout = useMobile(RESPONSIVE_BREAKPOINTS.splitCollapse);
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
      const timer = window.setTimeout(() => setIndicatorBody({
        code: resolvedCode,
        indicators: selectedIndicators,
        period,
        limit: Number(limit),
      }), 0);
      return () => window.clearTimeout(timer);
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
  const isPending = isAutoBootstrapping || (hasRequested && (activeQ.isPending || (activeQ.isFetching && rawData == null)));
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
    if (tab === 'patterns') return extractArray(unwrapped, 'patterns', 'results').filter((row) => row && typeof row === 'object');
    return extractArray(unwrapped, 'patterns', 'available').filter((row) => row && typeof row === 'object');
  }, [tab, unwrapped]);
  const hasIndicatorData = indicatorSeries.length > 0 || indicatorSummary.length > 0;
  const indicatorCategories = useMemo(() => {
    const longest = indicatorSeries.reduce((max, series) => Math.max(max, series.data.length), 0);
    return Array.from({ length: longest }, (_, index) => String(index + 1));
  }, [indicatorSeries]);
  const explanation = useMemo(() => {
    if (!rawData || error) return null;
    if (tab === 'indicators') {
      if (!hasIndicatorData) {
        return {
          title: '当前指标信号不足',
          description: '这通常意味着参数过窄或指标组合过多，建议先回到日线 120 根加常用三件套，确认趋势和动量是否一致。',
        };
      }
      return {
        title: '先用指标确认趋势与动量',
        description: '更适合回答“当前趋势是否延续、动量是否转弱”。看完后再去个股详情、资金流或回测页验证信号是否具备可执行性。',
      };
    }
    if (tab === 'patterns') {
      return rows.length > 0
        ? {
            title: '形态结果适合做二次确认',
            description: 'K 线形态更偏提示信号，不建议单独下结论。下一步优先叠加情绪、资金流和风险页。',
          }
        : {
            title: '未识别到典型形态',
            description: '当前价格结构相对平稳，可切换周线或扩大观察窗口，再观察是否出现更明确的突破或反转模式。',
          };
    }
    return rows.length > 0
      ? {
          title: '先确认有哪些可用形态',
          description: '能力库更适合作为识别前的准备动作。明确名称和方向后，再回到上一页对具体股票做筛查。',
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
  const pageActions = [
    {
      id: 'technical.run-recommended',
      label: '运行推荐分析',
      description: '用推荐参数直接发起技术分析',
      keywords: ['推荐分析', '技术'],
      scope: 'page' as const,
      pageKey: 'technical',
      run: () => {
        runRecommendedAnalysis();
        return { message: '已触发推荐技术分析' };
      },
    },
    {
      id: 'technical.submit',
      label: tab === 'available' ? '刷新可用形态' : tab === 'indicators' ? '计算指标' : '识别形态',
      description: '按当前参数提交技术分析请求',
      keywords: ['技术分析', '提交'],
      scope: 'page' as const,
      pageKey: 'technical',
      run: () => {
        submit();
        return { message: '已提交当前技术分析请求' };
      },
    },
    {
      id: 'technical.open-stock',
      label: '打开个股详情',
      description: '跳到个股详情页继续看行情和盘口',
      keywords: ['个股详情', '跳转'],
      scope: 'page' as const,
      pageKey: 'technical',
      run: () => {
        window.location.href = `/stock?code=${encodeURIComponent(focusCode)}`;
        return { message: '已跳到个股详情' };
      },
    },
  ];
  usePageActions(pageActions);
  const technicalSummary = `当前技术页聚焦 ${focusCode}，Tab 为 ${activeTabLabel}，周期 ${periodLabel}，状态 ${isPending ? '加载中' : error ? '需重试' : rawData ? '已返回' : '待分析'}。`;
  const technicalViews = [
    ...(rows.length > 1 || indicatorSeries.length > 1 ? (['compare'] as const) : []),
    ...(indicatorSeries.length > 0 ? (['visual'] as const) : []),
  ];
  const technicalResult = buildLocalResultContract({
    summary: technicalSummary,
    availableViews: technicalViews,
    pageActions,
    preferredActionIds: ['technical.run-recommended', 'technical.submit', 'technical.open-stock'],
    recommendedLinks: [
      { id: 'technical-open-stock-link', label: '个股详情', href: `/stock?code=${encodeURIComponent(focusCode)}` },
      { id: 'technical-open-fund-flow-link', label: '资金流', href: `/fund-flow?code=${encodeURIComponent(focusCode)}` },
      { id: 'technical-open-risk-link', label: '风险页', href: '/risk' },
      { id: 'technical-open-backtest-link', label: '回测', href: `/backtest?code=${encodeURIComponent(focusCode)}` },
    ],
    evidence: [
      { label: '当前 Tab', value: activeTabLabel },
      { label: '标的', value: focusCode },
      { label: '周期', value: periodLabel },
      { label: '结果条数', value: String(rows.length || indicatorSeries.length || indicatorSummary.length) },
      { label: '状态', value: isPending ? '加载中' : error ? '需重试' : rawData ? '已返回' : '待分析' },
    ],
    riskNotes: [error, mcpErr, explanation?.description].filter((item): item is string => Boolean(item)),
    freshness: lastUpdatedText ? { label: '最近更新', updatedAt: lastUpdatedText } : null,
    platformMeta: {
      sourceTool: 'technical',
      sourceChain: ['technical', tab, period],
      degraded: Boolean(error),
      fallbackReason: error ? [error] : undefined,
    },
    workbenchTask: defaultWorkbenchTask('technical', `复查${activeTabLabel}`, `/technical?code=${encodeURIComponent(focusCode)}`, 'technical-review', {
      code: focusCode,
      tab,
      period,
      limit,
    }),
  });
  usePageContext({
    pageKey: 'technical',
    title: '技术分析工作台',
    summary: technicalSummary,
    stockCode: focusCode || undefined,
    objectType: 'stock',
    objectId: focusCode,
    resultType: `technical-${tab}`,
    tags: [activeTabLabel, periodLabel, focusCode],
    suggestions: [
      `总结 ${focusCode} 当前技术面的关键结论`,
      '告诉我下一步更该看资金流还是风险',
      '把当前技术结果整理成操作清单',
    ],
    recommendedActions: technicalResult.recommendedActions ?? [],
    recommendedLinks: technicalResult.recommendedLinks ?? [],
    evidenceSummary: evidenceToSummary(technicalResult.evidence),
    riskNotes: technicalResult.riskNotes ?? [],
    freshness: technicalResult.freshness ?? null,
    raw: {
      code: focusCode,
      tab,
      period,
      limit,
      hasData: Boolean(rawData),
    },
  });

  return (
    <PageContainer>
      <LightOverviewHero
        eyebrow="Technical Workspace"
        title="技术分析工作台"
        summary="先确定股票与周期，再看一个主结果块。参数矩阵、推荐预设和联动跳转都收进按需展开区。"
        badges={(
          <>
            <Badge variant="info">Technical Workspace</Badge>
            <Badge variant="neutral">{activeTabLabel}</Badge>
            <Badge variant={tab === 'available' ? 'info' : 'success'}>
              {tab === 'available' ? '形态库视图' : `${focusCode} · ${periodLabel}`}
            </Badge>
          </>
        )}
        actions={(
          <button type="button" onClick={runRecommendedAnalysis} data-testid="page-primary-action" className={HERO_PRIMARY_BUTTON_CLS}>
            运行推荐分析
          </button>
        )}
        status={(
          <div
            data-testid="page-primary-status"
            className="rounded-[20px] border border-white/50 bg-white/28 px-4 py-3 text-sm shadow-[inset_0_1px_0_rgba(255,255,255,0.68)]"
          >
            <div className="font-medium text-text-primary">
              当前焦点：{tab === 'available' ? '可用形态库' : `${focusCode} · ${periodLabel}`}
            </div>
            <p className="mt-1 mb-0 text-xs leading-6 text-text-secondary">{requestSummary}</p>
          </div>
        )}
        metrics={[
          { key: 'technical-focus', label: '当前焦点', value: tab === 'available' ? '可用形态库' : focusCode },
          { key: 'technical-period', label: '观察周期', value: tab === 'available' ? '形态库' : periodLabel },
          { key: 'technical-updated', label: '最近更新', value: lastUpdatedText || '尚未更新' },
          { key: 'technical-result', label: '当前结论', value: explanation?.title ?? '等待结果返回' },
        ]}
        compact={compactLayout}
        detailsTitle="展开解读与联动入口"
        detailsContent={(
          <div className="space-y-3">
            <div className="grid gap-3 sm:grid-cols-2">
              <div className={NOTE_CARD_CLS}>当前结论：{explanation?.title ?? '等待结果返回'}</div>
              <div className={NOTE_CARD_CLS}>最近更新：{lastUpdatedText || '尚未更新'}</div>
            </div>
            {resolvedCode && tab !== 'available' ? (
              <div className="flex items-center gap-2">
                <StockLink code={resolvedCode} name={resolvedCode} />
                <WatchlistButton code={resolvedCode} name="" />
              </div>
            ) : null}
            <div className="flex flex-wrap gap-2">
              {actionLinks.map((link) => (
                <Link key={link.href} href={link.href} className={`${CHIP_BUTTON_CLS} no-underline text-inherit`}>
                  {link.label}
                </Link>
              ))}
            </div>
          </div>
        )}
      />

      {!compactLayout ? (
        <ProgressiveWorkbenchSection pageKey="technical" title="技术结果工作台" result={technicalResult} summaryMode="strip" />
      ) : null}

      <div className="panel-soft rounded-[28px] p-4 sm:p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="eyebrow">Technical Setup</div>
            <h2 className="mb-0 mt-2 text-xl font-semibold text-text-primary">参数与结果</h2>
            <p className="mb-0 mt-2 text-sm leading-7 text-text-secondary">
              当前模式一次只展示一个主结果区域，参数扩展折叠后再展开。
            </p>
          </div>
        </div>

        <div className="mt-4">
          <TabBar tabs={TABS} active={tab} onChange={setTab} />
        </div>

        <SectionCard tabAttached>
          {tab !== 'available' ? (
            <div className="space-y-4">
              <div className="grid gap-4 xl:grid-cols-[260px_180px_120px_auto] xl:items-end">
                <StockCodeInput id="technical-stock-code" label="股票代码" value={code} onChange={setCode} error={codeError} />
                <label htmlFor="technical-period" className="grid gap-2 text-xs text-text-secondary">
                  <span className="font-medium uppercase tracking-[0.12em] text-text-muted">观察周期</span>
                  <select id="technical-period" value={period} onChange={(e) => setPeriod(e.target.value)} className={FIELD_CLS}>
                    <option value="daily">日线</option>
                    <option value="weekly">周线</option>
                    <option value="monthly">月线</option>
                  </select>
                </label>
                <label htmlFor="technical-limit" className="grid gap-2 text-xs text-text-secondary">
                  <span className="font-medium uppercase tracking-[0.12em] text-text-muted">K 线数量</span>
                  <input id="technical-limit" value={limit} onChange={(e) => setLimit(e.target.value)} className={FIELD_CLS} />
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

              <details className="rounded-[22px] border border-glass-border bg-white/35 px-4 py-3">
                <summary className="cursor-pointer text-sm font-medium text-text-primary">参数展开</summary>
                <div className="mt-3 space-y-4">
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

                  {tab === 'indicators' ? (
                    <>
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
                          <button key={preset.label} type="button" onClick={() => setSelectedIndicators([...preset.values])} className={CHIP_BUTTON_CLS}>
                            {preset.label}
                          </button>
                        ))}
                      </div>
                    </>
                  ) : null}
                </div>
              </details>
            </div>
          ) : (
            <div className="flex flex-wrap items-center gap-2">
              <button type="button" disabled={isSubmitting} onClick={submit} className={HERO_PRIMARY_BUTTON_CLS}>
                {isSubmitting ? '处理中...' : '查看可用形态'}
              </button>
              <div className="text-sm text-text-secondary">先查看系统当前支持的 K 线形态库，再决定识别方向。</div>
            </div>
          )}
        </SectionCard>
      </div>

      <div className="panel-soft mt-4 rounded-[28px] p-4 sm:p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="eyebrow">Result View</div>
            <h2 className="mb-0 mt-2 text-xl font-semibold text-text-primary">技术结果</h2>
            <p className="mb-0 mt-2 text-sm leading-7 text-text-secondary">
              结果区只保留一个主结果块，解读和联动入口已经下沉到折叠区。
            </p>
          </div>
          <div className="metric-tile rounded-[22px] px-4 py-3 text-sm text-text-secondary">
            当前模式：<span className="font-medium text-text-primary">{activeTabLabel}</span>
          </div>
        </div>

        {error ? <ErrorState text={error} /> : null}
        {isPending ? <LoadingState text="处理中..." /> : null}

        {!error && !isPending && !hasRequested ? (
          <EmptyState text="先运行一次推荐分析或手动提交参数" hint="当前页面会把技术指标、形态识别和能力库都收进同一套阅读流。" />
        ) : null}

        {!error && !isPending && hasRequested && tab === 'indicators' ? (
          hasIndicatorData ? (
            <div className="space-y-4">
              {indicatorSeries.length > 0 ? (
                <LineChart
                  categories={indicatorCategories}
                  series={indicatorSeries}
                  height={compactLayout ? 220 : 280}
                  yAxisName="指标值"
                />
              ) : null}
              {indicatorSummary.length > 0 ? (
                <DataTable
                  rows={indicatorSummary.map((item) => ({
                    indicator: item.key,
                    summary: item.entries.map(([key, value]) => `${key}:${String(value)}`).join(' ｜ '),
                  }))}
                  columns={[
                    { key: 'indicator', label: '指标' },
                    { key: 'summary', label: '摘要' },
                  ]}
                />
              ) : null}
              <div className={NOTE_CARD_CLS}>{explanation?.description ?? '当前指标已经返回，可以继续去资金流或风险页交叉验证。'}</div>
            </div>
          ) : (
            <EmptyState text="当前没有可展示的指标结果" hint={explanation?.description ?? '建议扩大窗口或切换推荐参数后重试。'} />
          )
        ) : null}

        {!error && !isPending && hasRequested && tab !== 'indicators' ? (
          rows.length > 0 ? (
            <div className="space-y-4">
              <DataTable rows={rows as Record<string, unknown>[]} onExport={() => exportCSV(rows as Record<string, unknown>[], 'technical-results')} />
              <div className={NOTE_CARD_CLS}>{explanation?.description ?? '当前结果已经返回，可继续联动情绪、资金流和风险页。'}</div>
            </div>
          ) : (
            <EmptyState text={tab === 'available' ? '当前没有可用的形态库结果' : '当前没有识别到明确形态'} hint={explanation?.description ?? '可以切换周期或扩大观察窗口后重试。'} />
          )
        ) : null}

        {resolvedCode && tab !== 'available' && !error && !isPending && hasRequested ? (
          <KpiGrid cols={4} className="mt-4">
            <KpiCard title="当前标的" value={focusCode} />
            <KpiCard title="当前周期" value={periodLabel} />
            <KpiCard title="K 线数量" value={limit} />
            <KpiCard title="结果条数" value={tab === 'indicators' ? indicatorSeries.length + indicatorSummary.length : rows.length} />
          </KpiGrid>
        ) : null}
      </div>
    </PageContainer>
  );
}
