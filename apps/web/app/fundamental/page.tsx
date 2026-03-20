'use client';

import { FormEvent, useEffect, useMemo, useRef, useState } from 'react';
import { PageContainer, SectionCard, TabBar, DataTable, StockCodeInput, KpiCard, KpiGrid, Skeleton, SkeletonCard } from '@/components/ui';
import { LineChart } from '@/components/charts';
import { useApiQuery } from '@/hooks/use-api-query';
import { useApiMutation } from '@/hooks/use-api-mutation';
import { useStockCode } from '@/hooks/use-stock-code';
import { EmptyState, ErrorState } from '@/components/status-state';
import { StockLink } from '@/components/stock-link';
import { WatchlistButton } from '@/components/watchlist-button';
import { cacheText, type CacheMeta } from '@/lib/api';

import { extractArray, extractObject, fmtNum, fmtAmount, fmtPct } from '@/lib/data-utils';
import { exportCSV } from '@/lib/export';
import { ensureRecord, ensureRecordOrArray } from '@/lib/query-parse';

type OverviewData = { code?: string; financials?: { roe: number | null; netProfit: number | null; revenue: number | null; debtRatio: number | null }; valuation?: { pe: number | null; pb: number | null; ps: number | null; marketCap: number | null }; sourceTools?: Record<string, unknown>; meta?: CacheMeta };
type HistoryPoint = { date: string; pe: number | null; pb: number | null; ps: number | null; close: number | null };
type HistoryData = { code?: string; days?: number; points?: HistoryPoint[]; sourceTool?: string; meta?: CacheMeta };
type ExtraTab = 'info' | 'snapshot' | 'f10' | 'history';

const FIELD_LABELS: Record<string, string> = {
  eps: '每股收益',
  roe: 'ROE',
  net_profit: '归母净利润',
  revenue: '营业收入',
  debt_ratio: '资产负债率',
  operating_profit_rate: '营业利润率',
  bvps: '每股净资产',
  net_profit_margin: '净利率',
  operating_profit: '营业利润',
  netProfit: '归母净利润',
  grossProfitMargin: '毛利率',
  netProfitMargin: '净利率',
  roa: '总资产收益率',
  debtRatio: '资产负债率',
  currentRatio: '流动比率',
  reportDate: '报告期',
  code: '代码',
  name: '名称',
  industry: '行业',
  listDate: '上市日期',
  totalShares: '总股本',
  floatShares: '流通股本',
  totalMarketCap: '总市值',
  floatMarketCap: '流通市值',
  gross_profit_margin: '毛利率',
  operatingCashFlow: '经营现金流',
  pe: '市盈率 PE',
  pb: '市净率 PB',
  ps: '市销率 PS',
  forecastDate: '预测日期',
  forecastInstitution: '预测机构',
  forecastRating: '评级',
  epsForecast: 'EPS预测',
  netprofitForecast: '净利润预测',
};

const extraTabs: readonly { key: ExtraTab; label: string }[] = [
  { key: 'info', label: '基本信息' },
  { key: 'snapshot', label: '财务快照' },
  { key: 'f10', label: 'F10资料' },
  { key: 'history', label: '财务历史' },
];

/** Recursively flatten nested object for display */
function flattenObj(obj: Record<string, unknown>): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(obj)) {
    if (['raw', 'data_quality', 'field_state', 'missing_fields', 'null_fields', 'normalized_from'].includes(k)) {
      continue;
    }
    if (v && typeof v === 'object' && !Array.isArray(v)) {
      Object.assign(out, flattenObj(v as Record<string, unknown>));
    } else if (!Array.isArray(v)) {
      out[k] = v;
    }
  }
  return out;
}

export default function FundamentalPage() {
  const { code, setCode, codeError, validate, trimmedCode, resolvedCode } = useStockCode('600519');
  const [days, setDays] = useState(90);
  const [extraTab, setExtraTab] = useState<ExtraTab>('info');
  const [submittedCode, setSubmittedCode] = useState<string | null>(null);
  const [submittedDays, setSubmittedDays] = useState<number>(90);

  // 自动查询：URL 或 Store 携带了有效代码时自动触发
  const autoFetched = useRef(false);
  useEffect(() => {
    if (!autoFetched.current && resolvedCode) {
      autoFetched.current = true;
      setSubmittedCode(resolvedCode);
    }
  }, [resolvedCode]);

  const overviewQ = useApiQuery<OverviewData>(
    submittedCode ? `/fundamental/overview?code=${submittedCode}` : null,
    { parse: (raw) => ensureRecord(raw, '基本面概览') as OverviewData },
  );
  const historyQ = useApiQuery<HistoryData>(
    submittedCode ? `/fundamental/history?code=${submittedCode}&days=${submittedDays}` : null,
    { parse: (raw) => ensureRecord(raw, '基本面历史') as HistoryData },
  );
  const [extraPath, setExtraPath] = useState<string | null>(null);
  const extraQ = useApiQuery<unknown>(extraPath, {
    parse: (raw) => ensureRecordOrArray(raw, '基本面扩展数据'),
  });
  const historyMut = useApiMutation<unknown>({
    parse: (raw) => ensureRecordOrArray(raw, '财务历史'),
  });

  const loading = overviewQ.isFetching || historyQ.isFetching;
  const error = overviewQ.error || historyQ.error;

  // Auto-load extra tab data when switching tabs
  useEffect(() => {
    if (submittedCode) fetchExtra(extraTab, submittedCode);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [extraTab, submittedCode]);

  function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!validate()) return;
    if (trimmedCode === submittedCode && days === submittedDays) {
      overviewQ.refetch(); historyQ.refetch();
      fetchExtra(extraTab, submittedCode);
    } else {
      setSubmittedCode(trimmedCode);
      setSubmittedDays(days);
    }
  }
  function fetchExtra(type: string, code: string | null = submittedCode) {
    if (!code) return;
    if (type === 'history') {
      historyMut.trigger('/fundamental/financial-history', { method: 'POST' }, {
        codes: [code], fields: ['eps', 'roe', 'net_profit', 'revenue', 'debt_ratio', 'operating_profit_rate'], date: new Date().toISOString().slice(0, 10).replace(/-/g, ''),
      });
    } else {
      const endpoint = type === 'info' ? `/fundamental/stock-info?code=${code}`
        : type === 'snapshot' ? `/fundamental/financial-snapshot?code=${code}`
        : `/fundamental/f10?code=${code}`;
      if (endpoint === extraPath) extraQ.refetch(); else setExtraPath(endpoint);
    }
  }

  const overview = overviewQ.data;
  const history = historyQ.data;
  const extraDataRoot = (extraQ.data as any)?.data ?? extraQ.data ?? {};
  const stockName = String(
    (extraDataRoot as any)?.name
    ?? (extraDataRoot as any)?.f10?.name
    ?? (extraDataRoot as any)?.snapshot?.name
    ?? (extraDataRoot as any)?.data?.name
    ?? ''
  );
  const [resolvedStockName, setResolvedStockName] = useState('');
  const valuation = overview?.valuation;
  const financials = overview?.financials;
  const points = history?.points ?? [];
  const ovCache = overview?.meta?.cache;
  const hsCache = history?.meta?.cache;
  const freshness = [overview?.meta?.fetchedAt, history?.meta?.fetchedAt].filter(Boolean).sort().at(-1) ?? '';
  const updatedAt = overviewQ.dataUpdatedAt ? new Date(overviewQ.dataUpdatedAt).toLocaleString('zh-CN') : '';
  const latest = points.at(-1);
  const first = points[0];
  const peDelta = latest?.pe != null && first?.pe != null ? (latest.pe - first.pe).toFixed(2) : '-';
  const pbDelta = latest?.pb != null && first?.pb != null ? (latest.pb - first.pb).toFixed(2) : '-';
  const activeExtraLabel = extraTabs.find((tab) => tab.key === extraTab)?.label ?? '扩展';

  useEffect(() => {
    if (stockName) setResolvedStockName(stockName);
  }, [stockName]);

  useEffect(() => {
    if (resolvedStockName && submittedCode) {
      document.title = `${resolvedStockName}(${submittedCode}) | AIASK`;
      return () => { document.title = '基本面分析 | AIASK'; };
    }
    document.title = '基本面分析 | AIASK';
    return undefined;
  }, [resolvedStockName, submittedCode]);

  const missing = useMemo(() => {
    const checks = [
      { label: 'PE', v: valuation?.pe },
      { label: 'PB', v: valuation?.pb },
      { label: 'ROE', v: financials?.roe },
      { label: '净利润', v: financials?.netProfit },
    ];
    return checks.filter((x) => x.v == null).map((x) => x.label);
  }, [valuation, financials]);
  const showOverviewSkeleton = overviewQ.isPending && !overview;
  const showHistorySkeleton = historyQ.isPending && points.length === 0;
  const activeExtraRaw = extraTab === 'history' ? historyMut.data : extraQ.data;
  const activeExtraLoading = extraTab === 'history' ? historyMut.isPending : extraQ.isFetching;
  const activeExtraError = extraTab === 'history' ? historyMut.error : extraQ.error;

  return (
    <PageContainer narrow>
      <h1>基本面分析</h1>
      <form onSubmit={onSubmit} className="mt-3 flex gap-3 flex-wrap items-end">
        <StockCodeInput
          id="fundamental-stock-code"
          label="股票代码"
          value={code}
          onChange={setCode}
          error={codeError}
          placeholder="如 600519"
        />
        <label htmlFor="fundamental-days" className="grid gap-1 text-xs text-text-secondary">
          <span>观察区间</span>
          <select id="fundamental-days" value={days} onChange={(e) => setDays(Number(e.target.value))} className="px-2 py-1 border border-border rounded text-sm">
            <option value={30}>近1月</option>
            <option value={90}>近3月</option>
            <option value={180}>近6月</option>
            <option value={365}>近1年</option>
          </select>
        </label>
        <button type="submit" disabled={loading}>{loading ? '查询中...' : '查询'}</button>
      </form>
      <p className="mt-2 text-sm text-text-secondary">先确认股票代码，再用 90 天或 180 天窗口观察估值区间与核心财务指标是否同步改善。</p>
      {error ? <ErrorState text={error} /> : null}
      <div className="mt-2 text-text-secondary text-sm">
        更新：{updatedAt || '-'} ｜ 抓取：{freshness ? new Date(freshness).toLocaleString('zh-CN') : '-'}
      </div>
      <details className="text-xs text-text-muted mt-1">
        <summary className="cursor-pointer">缓存详情</summary>
        <span>Overview：{cacheText(ovCache)} ｜ History：{cacheText(hsCache)}</span>
      </details>
      {overview?.code && (
        <div className="mt-3 flex items-center gap-2">
          <StockLink code={overview.code} name={resolvedStockName || stockName || overview.code} />
          <WatchlistButton code={overview.code} name={resolvedStockName || stockName} />
        </div>
      )}
      <section className="mt-3.5 grid grid-cols-1 sm:grid-cols-2 gap-3">
        <SectionCard className="p-4 min-h-[216px]">
          <h3 className="mt-0">估值指标</h3>
          {showOverviewSkeleton ? (
            <KpiGrid cols={2}>
              <SkeletonCard />
              <SkeletonCard />
              <SkeletonCard />
              <SkeletonCard />
            </KpiGrid>
          ) : (
            <KpiGrid cols={2}>
              <KpiCard title="PE" value={fmtNum(valuation?.pe, 2)} />
              <KpiCard title="PB" value={fmtNum(valuation?.pb, 2)} />
              <KpiCard title="PS" value={fmtNum(valuation?.ps, 2)} />
              <KpiCard title="总市值" value={fmtAmount(valuation?.marketCap)} />
            </KpiGrid>
          )}
        </SectionCard>
        <SectionCard className="p-4 min-h-[216px]">
          <h3 className="mt-0">财务指标</h3>
          {showOverviewSkeleton ? (
            <KpiGrid cols={2}>
              <SkeletonCard />
              <SkeletonCard />
              <SkeletonCard />
              <SkeletonCard />
            </KpiGrid>
          ) : (
            <KpiGrid cols={2}>
              <KpiCard title="ROE" value={fmtNum(financials?.roe, 2)} suffix="%" />
              <KpiCard title="净利润" value={fmtAmount(financials?.netProfit)} />
              <KpiCard title="营收" value={fmtAmount(financials?.revenue)} />
              <KpiCard title="资产负债率" value={fmtNum(financials?.debtRatio, 2)} suffix="%" />
            </KpiGrid>
          )}
        </SectionCard>
      </section>
      <SectionCard className="p-4 mt-3 min-h-[420px]">
        <h3 className="mt-0">历史估值走势（{days}天）</h3>
        <div className="text-sm text-text-secondary mb-2">
          PE变化：{fmtNum(first?.pe)} → {fmtNum(latest?.pe)}（Δ {peDelta}）｜ PB变化：{fmtNum(first?.pb)} → {fmtNum(latest?.pb)}（Δ {pbDelta}）
        </div>
        <div className="min-h-[300px]">
          {showHistorySkeleton ? (
            <div className="space-y-3">
              <Skeleton width="48%" height={16} />
              <Skeleton height={280} />
            </div>
          ) : points.length > 1 ? (
            <LineChart
              categories={points.map((p) => p.date.slice(5))}
              series={[
                { name: 'PE', data: points.map((p) => p.pe ?? 0) },
                { name: 'PB', data: points.map((p) => p.pb ?? 0) },
              ]}
              height={280}
            />
          ) : (
            <EmptyState
              text={`近 ${days} 天没有可绘制的历史估值数据`}
              hint="可以切换到 180 天或 365 天窗口，或改查成交更活跃的股票后重新比较。"
            />
          )}
        </div>
      </SectionCard>
      {missing.length ? <p className="mt-3 text-text-muted text-sm">提示：{missing.join('、')}暂无数据，已显示为"-"</p> : null}
      <section className="mt-5">
        <h2>详细资料</h2>
        <p className="mt-1 text-sm text-text-secondary">切换标签会自动抓取对应资料。适合先看“基本信息/财务快照”，再进入 F10 与财务历史做深挖。</p>
        <TabBar<ExtraTab> tabs={extraTabs} active={extraTab} onChange={setExtraTab} />
        <SectionCard tabAttached className="min-h-[340px]">
          <button type="button" disabled={extraQ.isFetching || historyMut.isPending} onClick={() => fetchExtra(extraTab)}>{extraQ.isFetching || historyMut.isPending ? '加载中...' : '刷新'}</button>
          <div className="mt-3 min-h-[260px]">
          {activeExtraError ? (
            <ErrorState
              text={activeExtraError}
              hint="当前上游资料源暂时不可用，可以稍后重试，或先查看基本信息 / 财务快照 / 财务历史。"
            />
          ) : activeExtraLoading && activeExtraRaw == null ? (
            <div className="space-y-3">
              <Skeleton width="35%" height={16} />
              <Skeleton height={180} />
            </div>
          ) : (() => {
            const raw = activeExtraRaw;
            if (raw == null) {
              return (
                <EmptyState
                  text={`还没有加载${activeExtraLabel}`}
                  hint="切换标签后会自动查询；如果结果为空，可以点击上方“刷新”再次尝试。"
                />
              );
            }
            const rows = extractArray(raw).filter((r) => r && typeof r === 'object');
            if (rows.length) return <DataTable rows={rows} maxHeight={400} onExport={() => exportCSV(rows, `fundamental-${extraTab}`)} />;
            // Structured key-value display for single-object responses
            const obj = extractObject(raw);
            const pickDisplayRoot = () => {
              if (extraTab === 'snapshot') {
                const snapshot = obj.snapshot;
                if (snapshot && typeof snapshot === 'object' && !Array.isArray(snapshot)) {
                  const snapshotObj = extractObject(snapshot as Record<string, unknown>);
                  if (snapshotObj.data && typeof snapshotObj.data === 'object' && !Array.isArray(snapshotObj.data)) {
                    return extractObject(snapshotObj.data as Record<string, unknown>);
                  }
                  return snapshotObj;
                }
              }

              if (extraTab === 'f10') {
                const f10 = obj.f10;
                if (f10 && typeof f10 === 'object' && !Array.isArray(f10)) {
                  return extractObject(f10 as Record<string, unknown>);
                }
              }

              if (obj.data && typeof obj.data === 'object' && !Array.isArray(obj.data)) {
                return extractObject(obj.data as Record<string, unknown>);
              }

              return obj;
            };
            const displayRoot = pickDisplayRoot();
            const flat = flattenObj(displayRoot);
            const statusFlag = flat.success ?? obj.success;
            const errorField = flat.error ?? obj.error;
            const errorMessage = typeof errorField === 'string'
              ? errorField
              : errorField && typeof errorField === 'object' && typeof (errorField as { message?: unknown }).message === 'string'
                ? String((errorField as { message: string }).message)
                : '';
            if (statusFlag === false || statusFlag === 'false' || errorMessage) {
              return (
                <ErrorState
                  text={errorMessage || `${activeExtraLabel}加载失败`}
                  hint="当前上游资料源暂时不可用，可以稍后重试，或先查看基本信息 / 财务快照 / 财务历史。"
                />
              );
            }
            const f10FallbackHint = extraTab === 'f10' && typeof displayRoot.fallbackHint === 'string'
              ? String(displayRoot.fallbackHint)
              : '';
            const hiddenKeys = new Set([
              'infoType', 'cached', 'source', 'source_chain', 'fallback_reason', 'method', 'note', 'degraded', 'fallbackHint',
              'stockCodes', 'date', 'fields', 'fnFields', 'raw', 'data_quality', 'field_state', 'missing_fields', 'null_fields',
              'normalized_from', 'report_date', 'gross_profit_margin', 'net_profit_margin', 'debt_ratio', 'current_ratio',
              'revenue_growth', 'profit_growth', 'operating_cash_flow', 'ts_code', 'symbol', 'market', 'list_date',
            ]);
            const duplicateSnakeKeys = new Set<string>();
            if (extraTab === 'snapshot' || extraTab === 'f10') {
              if ('reportDate' in flat) duplicateSnakeKeys.add('report_date');
              if ('netProfit' in flat) duplicateSnakeKeys.add('net_profit');
              if ('grossProfitMargin' in flat) duplicateSnakeKeys.add('gross_profit_margin');
              if ('netProfitMargin' in flat) duplicateSnakeKeys.add('net_profit_margin');
              if ('debtRatio' in flat) duplicateSnakeKeys.add('debt_ratio');
              if ('currentRatio' in flat) duplicateSnakeKeys.add('current_ratio');
              if ('listDate' in flat) duplicateSnakeKeys.add('list_date');
            }
            const entries = Object.entries(flat).filter(([k, v]) => (
              v != null
              && v !== ''
              && v !== 0
              && String(v) !== '0'
              && String(v) !== '0.00'
              && String(v) !== '--'
              && !hiddenKeys.has(k)
              && !duplicateSnakeKeys.has(k)
            ));
            const renderValue = (k: string, v: unknown) => {
              const numericLike = typeof v === 'string' && v.trim() !== '' && !Number.isNaN(Number(v));
              const numericValue = typeof v === 'number' ? v : numericLike ? Number(v) : null;
              const amountKeys = new Set([
                'totalShares', 'floatShares', 'totalMarketCap', 'floatMarketCap', 'netProfit', 'revenue', 'operatingCashFlow', 'netprofitForecast', 'operating_profit', 'net_profit',
              ]);
              const percentKeys = new Set([
                'roe', 'debtRatio', 'grossProfitMargin', 'netProfitMargin', 'roa', 'debt_ratio', 'gross_profit_margin', 'net_profit_margin', 'operating_profit_rate',
              ]);
              const ratioKeys = new Set(['pe', 'pb', 'ps', 'epsForecast', 'bvps', 'currentRatio']);
              const dateKeys = new Set(['listDate', 'reportDate', 'forecastDate']);
              const formatDate = (value: string) => {
                const trimmed = value.trim();
                if (/^[0-9]{8}$/.test(trimmed)) {
                  return `${trimmed.slice(0, 4)}-${trimmed.slice(4, 6)}-${trimmed.slice(6, 8)}`;
                }
                return trimmed;
              };
              if (typeof v === 'string' && dateKeys.has(k)) {
                return formatDate(v);
              }
              if (numericValue != null && dateKeys.has(k)) {
                return formatDate(String(numericValue));
              }
              if (numericValue != null && percentKeys.has(k)) {
                return fmtPct(numericValue);
              }
              if (numericValue != null && amountKeys.has(k)) {
                return fmtAmount(numericValue);
              }
              if (numericValue != null && ratioKeys.has(k)) {
                return fmtNum(numericValue, 2);
              }
              if (typeof v === 'number') {
                return Math.abs(v) >= 1e6 ? fmtAmount(v) : fmtNum(v, 2);
              }
              return String(v);
            };
            return entries.length ? (
              <>
                {f10FallbackHint ? (
                  <div className="mb-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
                    <div className="font-medium">当前展示的是降级资料</div>
                    <div className="mt-1 text-amber-800">
                      完整 F10 数据源暂时不可用，页面已自动降级为最小可用公司资料，方便你继续核对基础信息与规模数据。
                    </div>
                    <div className="mt-1 text-amber-700">{f10FallbackHint}</div>
                  </div>
                ) : null}
                <div className="grid grid-cols-2 sm:grid-cols-3 gap-x-4 gap-y-1 text-sm mt-2">
                  {entries.map(([k, v]) => <div key={k}><span className="text-text-muted">{FIELD_LABELS[k] ?? k}：</span>{renderValue(k, v)}</div>)}
                </div>
              </>
            ) : (
              <EmptyState
                text={`${activeExtraLabel}暂无可展示字段`}
                hint="这通常表示上游数据源只返回了原始结构或当前标的资料较少，可以切换到其他标签继续核对。"
              />
            );
          })()}
          </div>
        </SectionCard>
      </section>
    </PageContainer>
  );
}
