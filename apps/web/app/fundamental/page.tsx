'use client';

import { FormEvent, useEffect, useMemo, useRef, useState } from 'react';
import {
  PageContainer,
  SectionCard,
  TabBar,
  DataTable,
  StockCodeInput,
  KpiCard,
  KpiGrid,
  Skeleton,
  SkeletonCard,
  Badge,
} from '@/components/ui';
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

type OverviewData = {
  code?: string;
  financials?: { roe: number | null; netProfit: number | null; revenue: number | null; debtRatio: number | null };
  valuation?: { pe: number | null; pb: number | null; ps: number | null; marketCap: number | null };
  sourceTools?: Record<string, unknown>;
  meta?: CacheMeta;
};
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
const HERO_PRIMARY_BUTTON_CLS =
  'inline-flex cursor-pointer items-center justify-center rounded-full bg-primary px-4 py-2 text-sm font-medium text-white shadow-[0_20px_40px_-24px_rgba(11,107,203,0.52)] transition hover:-translate-y-0.5 hover:shadow-[0_24px_46px_-24px_rgba(11,107,203,0.58)] disabled:cursor-not-allowed disabled:opacity-50';
const HERO_SECONDARY_BUTTON_CLS =
  'action-chip cursor-pointer text-sm text-text-primary shadow-[0_16px_32px_-24px_rgba(15,23,42,0.28)]';
const CHIP_BUTTON_CLS = 'action-chip cursor-pointer text-xs text-text-primary';
const NOTE_CARD_CLS = 'metric-tile rounded-[22px] p-3 text-xs text-text-secondary';
const SIDE_PANEL_CLS = 'panel-soft rounded-[28px] p-4 sm:p-5';

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

  const overviewQ = useApiQuery<OverviewData>(submittedCode ? `/fundamental/overview?code=${submittedCode}` : null, {
    parse: (raw) => ensureRecord(raw, '基本面概览') as OverviewData,
  });
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
      overviewQ.refetch();
      historyQ.refetch();
      fetchExtra(extraTab, submittedCode);
    } else {
      setSubmittedCode(trimmedCode);
      setSubmittedDays(days);
    }
  }
  function fetchExtra(type: string, code: string | null = submittedCode) {
    if (!code) return;
    if (type === 'history') {
      historyMut.trigger(
        '/fundamental/financial-history',
        { method: 'POST' },
        {
          codes: [code],
          fields: ['eps', 'roe', 'net_profit', 'revenue', 'debt_ratio', 'operating_profit_rate'],
          date: new Date().toISOString().slice(0, 10).replace(/-/g, ''),
        },
      );
    } else {
      const endpoint =
        type === 'info'
          ? `/fundamental/stock-info?code=${code}`
          : type === 'snapshot'
            ? `/fundamental/financial-snapshot?code=${code}`
            : `/fundamental/f10?code=${code}`;
      if (endpoint === extraPath) extraQ.refetch();
      else setExtraPath(endpoint);
    }
  }

  const overview = overviewQ.data;
  const history = historyQ.data;
  const extraDataEnvelope =
    extraQ.data && typeof extraQ.data === 'object' && !Array.isArray(extraQ.data)
      ? (extraQ.data as Record<string, unknown>)
      : {};
  const extraDataRoot = extractObject(extraDataEnvelope.data ?? extraQ.data) as Record<string, unknown>;
  const extraDataF10 = extractObject(extraDataRoot.f10) as Record<string, unknown>;
  const extraDataSnapshot = extractObject(extraDataRoot.snapshot) as Record<string, unknown>;
  const extraDataNested = extractObject(extraDataRoot.data) as Record<string, unknown>;
  const stockName = String(
    extraDataRoot.name ?? extraDataF10.name ?? extraDataSnapshot.name ?? extraDataNested.name ?? '',
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
  const focusCode = submittedCode ?? resolvedCode ?? trimmedCode;
  const focusName = resolvedStockName || stockName || focusCode;

  useEffect(() => {
    if (stockName) setResolvedStockName(stockName);
  }, [stockName]);

  useEffect(() => {
    if (resolvedStockName && submittedCode) {
      document.title = `${resolvedStockName}(${submittedCode}) | AIASK`;
      return () => {
        document.title = '基本面分析 | AIASK';
      };
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
      <section className="page-hero mb-4 p-5 sm:p-6">
        <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_clamp(280px,25vw,380px)]">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="info">Fundamental Workbench</Badge>
              <Badge variant={submittedCode ? 'success' : 'warning'}>
                {submittedCode ? `当前标的 ${submittedCode}` : '等待确认标的'}
              </Badge>
              <Badge variant="neutral">{days} 天窗口</Badge>
              <Badge variant="neutral">{activeExtraLabel}</Badge>
            </div>
            <h1 className="mb-0 mt-4 text-[2rem] font-semibold tracking-[-0.03em] text-text-primary sm:text-[2.4rem]">
              基本面分析工作台
            </h1>
            <p className="mb-0 mt-3 max-w-3xl text-sm leading-7 text-text-secondary sm:text-[15px]">
              这一页先回答三件事：当前看的标的是谁、估值区间在最近窗口里怎么变化、财务与补充资料是否支持当前判断。
              先用摘要卡快速判断，再进入历史走势和详细资料下钻。
            </p>
            <div className="mt-5 flex flex-wrap gap-2">
              <button type="button" onClick={() => setDays(90)} className={HERO_PRIMARY_BUTTON_CLS}>
                切到 90 天窗口
              </button>
              <button type="button" onClick={() => setExtraTab('snapshot')} className={HERO_SECONDARY_BUTTON_CLS}>
                查看财务快照
              </button>
              <button type="button" onClick={() => setExtraTab('history')} className={HERO_SECONDARY_BUTTON_CLS}>
                查看财务历史
              </button>
            </div>

            <div className="mt-5 grid gap-3 sm:grid-cols-4">
              <div className="rounded-[24px] border border-white/45 bg-white/38 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.55)]">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">当前标的</div>
                <div className="mt-3 text-2xl font-semibold text-text-primary">{focusCode || '-'}</div>
                <div className="mt-1 text-xs text-text-secondary">{focusName || '等待名称解析'}</div>
              </div>
              <div className="rounded-[24px] border border-white/45 bg-white/30 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.48)]">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">最近更新</div>
                <div className="mt-3 text-lg font-semibold text-text-primary">{updatedAt || '-'}</div>
                <div className="mt-1 text-xs text-text-secondary">
                  抓取时间 {freshness ? new Date(freshness).toLocaleString('zh-CN') : '-'}
                </div>
              </div>
              <div className="rounded-[24px] border border-white/45 bg-white/26 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.42)]">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">关键缺口</div>
                <div className="mt-3 text-2xl font-semibold text-text-primary">{missing.length}</div>
                <div className="mt-1 text-xs text-text-secondary">
                  {missing.length ? missing.join('、') : '核心字段齐全'}
                </div>
              </div>
              <div className="rounded-[24px] border border-white/45 bg-white/24 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.38)]">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">资料标签</div>
                <div className="mt-3 text-2xl font-semibold text-text-primary">{activeExtraLabel}</div>
                <div className="mt-1 text-xs text-text-secondary">适合从快照切到 F10 或财务历史继续下钻</div>
              </div>
            </div>
          </div>

          <div className="grid gap-3">
            <div className={SIDE_PANEL_CLS}>
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">当前聚焦</div>
              <div className="mt-3 text-base font-semibold text-text-primary">{focusName || '未选择标的'}</div>
              {focusCode ? (
                <div className="mt-3 flex items-center gap-2">
                  <StockLink code={focusCode} name={focusName} />
                  <WatchlistButton code={focusCode} name={focusName} />
                </div>
              ) : null}
              <div className="mt-4 space-y-3">
                <div className={NOTE_CARD_CLS}>
                  PE / PB：
                  <span className="font-medium text-text-primary">
                    {fmtNum(valuation?.pe, 2)} / {fmtNum(valuation?.pb, 2)}
                  </span>
                </div>
                <div className={NOTE_CARD_CLS}>
                  ROE / 资产负债率：
                  <span className="font-medium text-text-primary">
                    {' '}
                    {fmtNum(financials?.roe, 2)}% / {fmtNum(financials?.debtRatio, 2)}%
                  </span>
                </div>
                <div className={NOTE_CARD_CLS}>
                  历史点位：<span className="font-medium text-text-primary">{points.length || 0} 条</span>
                </div>
              </div>
            </div>

            <div className={SIDE_PANEL_CLS}>
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">阅读建议</div>
              <div className="mt-4 space-y-3">
                <div className={NOTE_CARD_CLS}>1. 先看摘要 KPI，确认估值与盈利能力是否同时改善。</div>
                <div className={NOTE_CARD_CLS}>2. 再看历史走势，判断当前估值位置是修复还是透支。</div>
                <div className={NOTE_CARD_CLS}>3. 最后切到 F10 与财务历史，核对公司规模、行业和报告期细节。</div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {error ? <ErrorState text={error} /> : null}

      <KpiGrid cols={4} className="mb-4">
        <KpiCard title="PE" value={fmtNum(valuation?.pe, 2)} />
        <KpiCard title="PB" value={fmtNum(valuation?.pb, 2)} />
        <KpiCard title="ROE" value={fmtNum(financials?.roe, 2)} suffix="%" />
        <KpiCard title="资产负债率" value={fmtNum(financials?.debtRatio, 2)} suffix="%" />
      </KpiGrid>

      <div className="panel-soft rounded-[28px] p-4 sm:p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="eyebrow">Analysis Setup</div>
            <h2 className="mb-0 mt-2 text-xl font-semibold text-text-primary">查询工作台</h2>
            <p className="mb-0 mt-2 text-sm leading-7 text-text-secondary">
              先确认股票代码，再用 90 天或 180 天窗口观察估值区间与核心财务指标是否同步改善。
            </p>
          </div>
          <div className="metric-tile rounded-[22px] px-4 py-3 text-sm text-text-secondary">
            Overview：{cacheText(ovCache)} ｜ History：{cacheText(hsCache)}
          </div>
        </div>

        <form onSubmit={onSubmit} className="mt-4 grid gap-4 xl:grid-cols-[minmax(0,260px)_180px_auto] xl:items-end">
          <StockCodeInput
            id="fundamental-stock-code"
            label="股票代码"
            value={code}
            onChange={setCode}
            error={codeError}
            placeholder="如 600519"
          />
          <label htmlFor="fundamental-days" className="grid gap-2 text-xs text-text-secondary">
            <span className="font-medium uppercase tracking-[0.12em] text-text-muted">观察区间</span>
            <select
              id="fundamental-days"
              value={days}
              onChange={(e) => setDays(Number(e.target.value))}
              className="h-11 rounded-[20px] border border-white/65 bg-white/55 px-4 text-sm text-text-primary shadow-[inset_0_1px_0_rgba(255,255,255,0.75)] outline-none transition focus:border-primary/45 focus:bg-white/72"
            >
              <option value={30}>近1月</option>
              <option value={90}>近3月</option>
              <option value={180}>近6月</option>
              <option value={365}>近1年</option>
            </select>
          </label>
          <div className="flex flex-wrap items-center gap-2 xl:justify-end">
            <button type="submit" disabled={loading} className={HERO_PRIMARY_BUTTON_CLS}>
              {loading ? '查询中...' : '查询'}
            </button>
            <button type="button" onClick={() => setExtraTab('f10')} className={HERO_SECONDARY_BUTTON_CLS}>
              直达 F10
            </button>
          </div>
        </form>

        <div className="mt-4 flex flex-wrap gap-2">
          {[30, 90, 180, 365].map((windowDays) => (
            <button
              key={windowDays}
              type="button"
              onClick={() => setDays(windowDays)}
              className={`${CHIP_BUTTON_CLS} ${days === windowDays ? 'border-primary/35 bg-primary/12 text-primary' : 'text-text-secondary'}`}
            >
              {windowDays === 30 ? '近1月' : windowDays === 90 ? '近3月' : windowDays === 180 ? '近6月' : '近1年'}
            </button>
          ))}
        </div>
      </div>

      <section className="mt-4 grid grid-cols-1 gap-4 xl:grid-cols-2">
        <div className="panel-soft rounded-[28px] p-4 sm:p-5">
          <div className="text-sm font-medium text-text-primary">估值快照</div>
          <p className="mb-0 mt-2 text-xs leading-6 text-text-secondary">
            适合先确认当前估值水平，再和历史走势对照估值修复节奏。
          </p>
          {showOverviewSkeleton ? (
            <KpiGrid cols={2} className="mt-4">
              <SkeletonCard />
              <SkeletonCard />
              <SkeletonCard />
              <SkeletonCard />
            </KpiGrid>
          ) : (
            <KpiGrid cols={2} className="mt-4">
              <KpiCard title="PE" value={fmtNum(valuation?.pe, 2)} />
              <KpiCard title="PB" value={fmtNum(valuation?.pb, 2)} />
              <KpiCard title="PS" value={fmtNum(valuation?.ps, 2)} />
              <KpiCard title="总市值" value={fmtAmount(valuation?.marketCap)} />
            </KpiGrid>
          )}
        </div>
        <div className="panel-soft rounded-[28px] p-4 sm:p-5">
          <div className="text-sm font-medium text-text-primary">财务快照</div>
          <p className="mb-0 mt-2 text-xs leading-6 text-text-secondary">
            把盈利能力、规模和杠杆放在同一屏里看，能更快判断基本面是否支持当前估值。
          </p>
          {showOverviewSkeleton ? (
            <KpiGrid cols={2} className="mt-4">
              <SkeletonCard />
              <SkeletonCard />
              <SkeletonCard />
              <SkeletonCard />
            </KpiGrid>
          ) : (
            <KpiGrid cols={2} className="mt-4">
              <KpiCard title="ROE" value={fmtNum(financials?.roe, 2)} suffix="%" />
              <KpiCard title="净利润" value={fmtAmount(financials?.netProfit)} />
              <KpiCard title="营收" value={fmtAmount(financials?.revenue)} />
              <KpiCard title="资产负债率" value={fmtNum(financials?.debtRatio, 2)} suffix="%" />
            </KpiGrid>
          )}
        </div>
      </section>

      <div className="panel-soft mt-4 rounded-[28px] p-4 sm:p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="eyebrow">History View</div>
            <h2 className="mb-0 mt-2 text-xl font-semibold text-text-primary">历史估值走势（{days}天）</h2>
          </div>
          <div className="metric-tile rounded-[22px] px-4 py-3 text-sm text-text-secondary">
            最新点位：{latest?.date ?? '暂无'} ｜ 首个点位：{first?.date ?? '暂无'}
          </div>
        </div>
        <div className="mb-2 mt-3 text-sm text-text-secondary">
          PE变化：{fmtNum(first?.pe)} → {fmtNum(latest?.pe)}（Δ {peDelta}）｜ PB变化：{fmtNum(first?.pb)} →{' '}
          {fmtNum(latest?.pb)}（Δ {pbDelta}）
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
      </div>
      {missing.length ? (
        <div className="panel-soft mt-4 rounded-[24px] px-4 py-3 text-sm text-text-secondary">
          提示：{missing.join('、')}暂无数据，已显示为“-”。
        </div>
      ) : null}
      <section className="mt-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2>详细资料</h2>
            <p className="mt-1 text-sm text-text-secondary">
              切换标签会自动抓取对应资料。适合先看“基本信息/财务快照”，再进入 F10 与财务历史做深挖。
            </p>
          </div>
          <button
            type="button"
            disabled={extraQ.isFetching || historyMut.isPending}
            onClick={() => fetchExtra(extraTab)}
            className={HERO_SECONDARY_BUTTON_CLS}
          >
            {extraQ.isFetching || historyMut.isPending ? '加载中...' : '刷新当前资料'}
          </button>
        </div>
        <div className="mt-3">
          <TabBar<ExtraTab> tabs={extraTabs} active={extraTab} onChange={setExtraTab} />
        </div>
        <SectionCard tabAttached className="min-h-[340px]">
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
            ) : (
              (() => {
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
                if (rows.length)
                  return (
                    <DataTable
                      rows={rows}
                      maxHeight={400}
                      onExport={() => exportCSV(rows, `fundamental-${extraTab}`)}
                    />
                  );
                // Structured key-value display for single-object responses
                const obj = extractObject(raw);
                const pickDisplayRoot = () => {
                  if (extraTab === 'snapshot') {
                    const snapshot = obj.snapshot;
                    if (snapshot && typeof snapshot === 'object' && !Array.isArray(snapshot)) {
                      const snapshotObj = extractObject(snapshot as Record<string, unknown>);
                      if (
                        snapshotObj.data &&
                        typeof snapshotObj.data === 'object' &&
                        !Array.isArray(snapshotObj.data)
                      ) {
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
                const errorMessage =
                  typeof errorField === 'string'
                    ? errorField
                    : errorField &&
                        typeof errorField === 'object' &&
                        typeof (errorField as { message?: unknown }).message === 'string'
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
                const f10FallbackHint =
                  extraTab === 'f10' && typeof displayRoot.fallbackHint === 'string'
                    ? String(displayRoot.fallbackHint)
                    : '';
                const hiddenKeys = new Set([
                  'infoType',
                  'cached',
                  'source',
                  'source_chain',
                  'fallback_reason',
                  'method',
                  'note',
                  'degraded',
                  'fallbackHint',
                  'stockCodes',
                  'date',
                  'fields',
                  'fnFields',
                  'raw',
                  'data_quality',
                  'field_state',
                  'missing_fields',
                  'null_fields',
                  'normalized_from',
                  'report_date',
                  'gross_profit_margin',
                  'net_profit_margin',
                  'debt_ratio',
                  'current_ratio',
                  'revenue_growth',
                  'profit_growth',
                  'operating_cash_flow',
                  'ts_code',
                  'symbol',
                  'market',
                  'list_date',
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
                const entries = Object.entries(flat).filter(
                  ([k, v]) =>
                    v != null &&
                    v !== '' &&
                    v !== 0 &&
                    String(v) !== '0' &&
                    String(v) !== '0.00' &&
                    String(v) !== '--' &&
                    !hiddenKeys.has(k) &&
                    !duplicateSnakeKeys.has(k),
                );
                const renderValue = (k: string, v: unknown) => {
                  const numericLike = typeof v === 'string' && v.trim() !== '' && !Number.isNaN(Number(v));
                  const numericValue = typeof v === 'number' ? v : numericLike ? Number(v) : null;
                  const amountKeys = new Set([
                    'totalShares',
                    'floatShares',
                    'totalMarketCap',
                    'floatMarketCap',
                    'netProfit',
                    'revenue',
                    'operatingCashFlow',
                    'netprofitForecast',
                    'operating_profit',
                    'net_profit',
                  ]);
                  const percentKeys = new Set([
                    'roe',
                    'debtRatio',
                    'grossProfitMargin',
                    'netProfitMargin',
                    'roa',
                    'debt_ratio',
                    'gross_profit_margin',
                    'net_profit_margin',
                    'operating_profit_rate',
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
                          完整 F10
                          数据源暂时不可用，页面已自动降级为最小可用公司资料，方便你继续核对基础信息与规模数据。
                        </div>
                        <div className="mt-1 text-amber-700">{f10FallbackHint}</div>
                      </div>
                    ) : null}
                    <div className="grid grid-cols-2 sm:grid-cols-3 gap-x-4 gap-y-1 text-sm mt-2">
                      {entries.map(([k, v]) => (
                        <div key={k}>
                          <span className="text-text-muted">{FIELD_LABELS[k] ?? k}：</span>
                          {renderValue(k, v)}
                        </div>
                      ))}
                    </div>
                  </>
                ) : (
                  <EmptyState
                    text={`${activeExtraLabel}暂无可展示字段`}
                    hint="这通常表示上游数据源只返回了原始结构或当前标的资料较少，可以切换到其他标签继续核对。"
                  />
                );
              })()
            )}
          </div>
        </SectionCard>
      </section>
    </PageContainer>
  );
}
