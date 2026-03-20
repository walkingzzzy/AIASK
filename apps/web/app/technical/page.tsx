'use client';

import { useState, useMemo, useEffect, useRef } from 'react';
import { PageContainer, TabBar, SectionCard, StockCodeInput, Badge, DataTable } from '@/components/ui';
import { useApiQuery } from '@/hooks/use-api-query';
import { useStockCode } from '@/hooks/use-stock-code';
import { LoadingState, ErrorState, EmptyState } from '@/components/status-state';
import { LineChart, COLORS } from '@/components/charts';
import { extractArray, fmtNum } from '@/lib/data-utils';
import { exportCSV } from '@/lib/export';
import { StockLink } from '@/components/stock-link';
import { WatchlistButton } from '@/components/watchlist-button';
import { extractToolError, unwrapToolPayload } from '@/lib/tool-result';
import Link from 'next/link';

const TABS = [
  { key: 'indicators', label: '技术指标' },
  { key: 'patterns', label: 'K线形态' },
  { key: 'available', label: '可用形态' },
] as const;

type Tab = (typeof TABS)[number]['key'];
type SubmittedPayload = Record<string, unknown>;

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
const actionLinkCls = 'rounded-full border border-glass-border px-3 py-1 text-xs text-text-secondary no-underline';

/**
 * Transform indicator response into chart-friendly data.
 * API returns: { ma: number[], rsi: {value,signal,...}, macd: {macd:[],signal:[],histogram:[]} }
 * We produce: { series for LineChart, summary items for non-array indicators }
 */
function parseIndicators(raw: unknown) {
  const obj = raw as Record<string, unknown> | null;
  if (!obj || typeof obj !== 'object') return { series: [], summary: [] as { key: string; entries: [string, unknown][] }[] };

  const series: { name: string; data: number[]; color: string }[] = [];
  const summary: { key: string; entries: [string, unknown][] }[] = [];
  let ci = 0;

  for (const [key, val] of Object.entries(obj)) {
    if (Array.isArray(val) && val.length > 0 && typeof val[0] === 'number') {
      // Array indicator (MA, EMA, etc.) → line series
      series.push({ name: key.toUpperCase(), data: val, color: COLORS.series[ci++ % COLORS.series.length] });
    } else if (val && typeof val === 'object' && !Array.isArray(val)) {
      const inner = val as Record<string, unknown>;
      // Check for nested arrays (MACD has macd/signal/histogram arrays)
      let hasArrays = false;
      for (const [sk, sv] of Object.entries(inner)) {
        if (Array.isArray(sv) && sv.length > 0 && typeof sv[0] === 'number') {
          series.push({ name: `${key.toUpperCase()}_${sk}`, data: sv, color: COLORS.series[ci++ % COLORS.series.length] });
          hasArrays = true;
        }
      }
      if (!hasArrays) {
        // Scalar indicator (RSI single value, etc.) → summary card
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

  // Auto-fetch indicators on mount
  const autoFetched = useRef(false);
  useEffect(() => {
    if (!autoFetched.current && resolvedCode) {
      autoFetched.current = true;
      setIndicatorBody({
        code: resolvedCode, indicators: selectedIndicators, period, limit: Number(limit),
      });
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resolvedCode]);
  function toggleIndicator(ind: string) {
    setSelectedIndicators((prev) =>
      prev.includes(ind) ? prev.filter((x) => x !== ind) : [...prev, ind],
    );
  }

  function submit() {
    if (tab === 'available') {
      if (availablePath) availableQ.refetch(); else setAvailablePath('/technical/available-patterns');
    } else {
      if (!validate()) return;
      const body: SubmittedPayload = { code: trimmedCode, period, limit: Number(limit) };
      if (tab === 'indicators') {
        body.indicators = selectedIndicators;
        if (indicatorBody && JSON.stringify(indicatorBody) === JSON.stringify(body)) indicatorsQ.refetch();
        else setIndicatorBody(body);
        return;
      }
      if (patternBody && JSON.stringify(patternBody) === JSON.stringify(body)) patternsQ.refetch();
      else setPatternBody(body);
    }
  }

  function runRecommendedAnalysis() {
    if (tab === 'available') {
      if (availablePath) availableQ.refetch(); else setAvailablePath('/technical/available-patterns');
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
  const hasRequested = tab === 'available' ? availablePath != null : tab === 'indicators' ? indicatorBody != null : patternBody != null;
  const rawData = activeQ.data;
  const isAutoBootstrapping = tab === 'indicators' && resolvedCode && indicatorBody == null;
  const isPending = isAutoBootstrapping || (hasRequested && (activeQ.isPending || (activeQ.isFetching && rawData == null)));
  const isSubmitting = hasRequested && activeQ.isPending;
  const fetchError = activeQ.error;
  const mcpErr = rawData ? extractToolError(rawData) : null;
  const error = fetchError || mcpErr;
  const lastUpdatedText = activeQ.dataUpdatedAt ? new Date(activeQ.dataUpdatedAt).toLocaleString('zh-CN') : null;
  const requestSummary = tab === 'available'
    ? '当前查看：系统支持的 K 线形态库'
    : `最近一次参数：${trimmedCode || resolvedCode || '600519'} / ${period === 'daily' ? '日线' : period === 'weekly' ? '周线' : '月线'} / ${limit} 根${tab === 'indicators' ? ` / ${selectedIndicators.join('、')}` : ''}`;

  // Unwrap MCP envelope for all tabs
  const unwrapped = useMemo(() => rawData ? unwrapToolPayload(rawData) : null, [rawData]);

  // Indicators: parse into series + summary
  const { series: indSeries, summary: indSummary } = useMemo(() => {
    if (tab !== 'indicators' || !unwrapped) return { series: [], summary: [] };
    return parseIndicators(unwrapped);
  }, [unwrapped, tab]);

  // Patterns / Available: extract row arrays
  const rows = useMemo(() => {
    if (!unwrapped) return [];
    if (tab === 'indicators') return []; // handled by indSeries/indSummary
    if (tab === 'patterns') return extractArray(unwrapped, 'patterns', 'results').filter(r => r && typeof r === 'object');
    return extractArray(unwrapped, 'patterns', 'available').filter(r => r && typeof r === 'object');
  }, [unwrapped, tab]);

  const hasIndicatorData = indSeries.length > 0 || indSummary.length > 0;
  const explanation = useMemo(() => {
    if (!rawData || error) return null;
    if (tab === 'indicators') {
      if (!hasIndicatorData) return {
        title: '当前指标信号不足',
        description: '这通常意味着参数过窄或指标组合过多，建议先回到日线 120 根 + 常用三件套，确认趋势和动量是否一致。',
      };
      return {
        title: '先用指标确认趋势与动量',
        description: '这一屏更适合回答“当前趋势是否延续、动量是否转弱”。看完后建议继续去个股详情、资金流或回测页验证信号是否具备可执行性。',
      };
    }
    if (tab === 'patterns') {
      return rows.length > 0 ? {
        title: '形态结果适合做二次确认',
        description: 'K 线形态更偏提示信号，不建议单独下结论。下一步优先叠加情绪、资金流和风险页，确认这类形态是否有资金或预期配合。',
      } : {
        title: '未识别到典型形态',
        description: '说明当前价格结构相对平稳，可切换周线或扩大观察窗口，再观察是否出现更明确的突破/反转模式。',
      };
    }
    return rows.length > 0 ? {
      title: '先确认有哪些可用形态',
      description: '可用形态列表更适合作为识别前的准备动作。明确名称和方向后，再回到上一页对具体股票做筛查。',
    } : {
      title: '形态库暂未返回',
      description: '如果形态库为空，优先检查后端能力是否就绪；前端已经为“先看能力，再做筛查”的路径预留了解释层。',
    };
  }, [error, hasIndicatorData, rawData, rows.length, tab]);
  const actionLinks = useMemo(() => {
    const c = encodeURIComponent(trimmedCode || resolvedCode || '600519');
    return [
      { label: '个股详情', href: `/stock?code=${c}` },
      { label: '资金流', href: `/fund-flow?code=${c}` },
      { label: '情绪分析', href: `/sentiment?code=${c}` },
      { label: '风险页', href: `/risk?code=${c}` },
      { label: '回测', href: `/backtest?code=${c}` },
    ];
  }, [resolvedCode, trimmedCode]);
  return (
    <PageContainer>
      <h1>技术分析</h1>
      {resolvedCode && (
        <div className="flex items-center gap-2 mb-2">
          <StockLink code={resolvedCode} name={resolvedCode} />
          <WatchlistButton code={resolvedCode} name="" />
        </div>
      )}
      <TabBar tabs={TABS} active={tab} onChange={setTab} />
      <SectionCard tabAttached>
        {tab !== 'available' ? (
          <div className="mb-3 space-y-3">
            <div className="flex gap-3 flex-wrap items-end">
              <StockCodeInput
                id="technical-stock-code"
                label="股票代码"
                value={code}
                onChange={setCode}
                error={codeError}
              />
              <label htmlFor="technical-period" className="grid gap-1 text-xs text-text-secondary">
                <span>观察周期</span>
                <select id="technical-period" value={period} onChange={(e) => setPeriod(e.target.value)}
                  className="px-2 py-1 border border-border rounded text-sm">
                  <option value="daily">日线</option>
                  <option value="weekly">周线</option>
                  <option value="monthly">月线</option>
                </select>
              </label>
              <label htmlFor="technical-limit" className="grid gap-1 text-xs text-text-secondary">
                <span>K线数量</span>
                <input id="technical-limit" value={limit} onChange={(e) => setLimit(e.target.value)}
                  className="w-24 px-2 py-1 border border-border rounded text-sm" />
              </label>
            </div>
            <div className="flex gap-2 flex-wrap items-center text-xs text-text-secondary">
              <span>推荐观察：</span>
              {PERIOD_PRESETS.map((preset) => (
                <button
                  key={preset.label}
                  type="button"
                  onClick={() => { setPeriod(preset.period); setLimit(preset.limit); }}
                  className={`rounded-full border px-3 py-1 ${period === preset.period && limit === preset.limit ? 'border-primary text-primary' : 'border-glass-border'}`}
                >
                  {preset.label}
                </button>
              ))}
            </div>
          </div>
        ) : null}
        {tab === 'indicators' ? (
          <div className="mb-3 space-y-2">
            <div className="text-[13px] text-muted mb-1">选择指标：</div>
            <div className="flex gap-1.5 flex-wrap">
              {INDICATOR_OPTIONS.map((ind) => (
                <label key={ind} className="flex items-center gap-1 cursor-pointer text-sm">
                  <input type="checkbox" checked={selectedIndicators.includes(ind)}
                    onChange={() => toggleIndicator(ind)} />
                  {ind}
                </label>
              ))}
            </div>
            <div className="flex gap-2 flex-wrap items-center text-xs text-text-secondary">
              <span>常用组合：</span>
              {INDICATOR_PRESETS.map((preset) => (
                <button
                  key={preset.label}
                  type="button"
                  onClick={() => setSelectedIndicators([...preset.values])}
                  className="rounded-full border border-glass-border px-3 py-1"
                >
                  {preset.label}
                </button>
              ))}
            </div>
          </div>
        ) : null}
        <div className="flex flex-wrap items-center gap-3">
          <button type="button" disabled={isSubmitting} onClick={submit}
            className="px-3 py-1 border border-border rounded text-sm disabled:opacity-50">
            {isSubmitting ? '处理中...' : tab === 'available' ? '查看可用形态' : tab === 'indicators' ? '计算指标' : '识别形态'}
          </button>
          <button
            type="button"
            onClick={runRecommendedAnalysis}
            className="rounded-full border border-glass-border px-3 py-1 text-xs text-text-secondary"
          >
            使用推荐参数
          </button>
          <div className="text-xs text-text-secondary">
            {requestSummary}
            {lastUpdatedText ? ` ｜ 更新：${lastUpdatedText}` : ''}
          </div>
        </div>
        {isPending ? <LoadingState text={isAutoBootstrapping ? '正在自动加载默认指标...' : '计算中...'} /> : null}
        {error ? <ErrorState text={error} hint="请检查参数后重试" /> : null}
        {!isPending && !rawData && !error ? (
          <EmptyState
            text={tab === 'available' ? '先查看当前支持的形态库，再决定识别方向' : tab === 'indicators' ? '先选择股票、周期与指标组合，再开始技术分析' : '先确认股票代码和K线数量，再识别近期形态'}
            hint={tab === 'available' ? '这一步适合先了解系统能识别哪些经典形态，再回到上一页做实盘筛查。' : tab === 'indicators' ? '推荐先用日线 120 根 + MA / RSI / MACD 的组合，作为第一次分析入口。' : '推荐先从日线 120 根开始，适合观察近期是否出现吞没、十字星或突破信号。'}
            action={<button type="button" onClick={runRecommendedAnalysis} className="rounded-full border border-primary px-3 py-1 text-xs text-primary">使用推荐参数</button>}
          />
        ) : null}
        {rawData != null && !error && explanation ? (
          <div className="mt-3 rounded-xl border border-border bg-surface-alt/50 p-3">
            <div className="text-sm font-medium text-text-primary">{explanation.title}</div>
            <p className="mt-1 mb-0 text-sm text-text-secondary">{explanation.description}</p>
            <div className="mt-3 flex gap-2 flex-wrap">
              {actionLinks.map((link) => (
                <Link key={link.href} href={link.href} className={actionLinkCls}>
                  {link.label}
                </Link>
              ))}
            </div>
          </div>
        ) : null}
{/* Indicators tab */}
        {rawData != null && !mcpErr && tab === 'indicators' ? (
          hasIndicatorData ? (
            <div className="mt-3 space-y-4">
              {indSeries.length > 0 && (
                <LineChart
                  categories={Array.from({ length: indSeries[0].data.length }, (_, i) => String(i + 1))}
                  series={indSeries}
                  height={350}
                />
              )}
              {indSummary.map((s) => (
                <div key={s.key} className="p-3 border border-border rounded">
                  <div className="font-medium text-sm mb-1">{s.key}</div>
                  <div className="flex flex-wrap gap-x-4 gap-y-1 text-sm">
                    {s.entries.map(([k, v]) => (
                      <span key={k} className="text-text-secondary">
                        {k}: <span className="text-text-primary font-medium">
                          {typeof v === 'number' ? fmtNum(v, 2) : String(v)}
                        </span>
                      </span>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          ) : <EmptyState text="当前参数下暂无可展示的指标结果" hint="可以切换到日线 120 根，或减少指标数量后再次计算。" />
        ) : null}
        {/* Patterns tab */}
        {rawData != null && !mcpErr && tab === 'patterns' ? (
          rows.length > 0 ? (
            <div className="mt-3">
              <DataTable
                rows={rows as Record<string, unknown>[]}
                columns={[
                  { key: 'date', label: '日期' },
                  { key: 'pattern', label: '形态' },
                  { key: 'name', label: '名称' },
                  { key: 'type', label: '类型', render: (v) => (
                    <Badge variant={String(v) === 'bullish' ? 'success' : String(v) === 'bearish' ? 'danger' : 'info'}>{String(v)}</Badge>
                  )},
                  { key: 'reliability', label: '可靠性' },
                ]}
                onExport={() => exportCSV(rows as Record<string, unknown>[], 'K线形态')}
              />
            </div>
          ) : <EmptyState text="近期未识别到典型K线形态" hint="这通常意味着价格波动较平缓，可以放大观察窗口或切换到周线再试。" />
        ) : null}
        {/* Available patterns tab */}
        {rawData != null && !mcpErr && tab === 'available' ? (
          rows.length > 0 ? (
            <div className="mt-3">
              <DataTable
                rows={rows as Record<string, unknown>[]}
                columns={[
                  { key: 'name', label: '名称' },
                  { key: 'pattern', label: '代码' },
                  { key: 'bullish', label: '方向', render: (v) => (
                    <Badge variant={v === true ? 'success' : v === false ? 'danger' : 'info'}>
                      {v === true ? '看涨' : v === false ? '看跌' : '双向'}
                    </Badge>
                  )},
                  { key: 'reliability', label: '可靠性' },
                ]}
                onExport={() => exportCSV(rows as Record<string, unknown>[], '可用形态')}
              />
            </div>
          ) : <EmptyState text="当前没有返回可用形态列表" hint="可稍后重试；如果持续为空，优先检查后端形态能力是否已就绪。" />
        ) : null}
      </SectionCard>
    </PageContainer>
  );
}
