'use client';

import { FormEvent, useMemo, useState } from 'react';
import { PageContainer, SectionCard, KpiCard, KpiGrid, Badge } from '@/components/ui';
import { BarChart, PieChart } from '@/components/charts';
import { useApiQuery } from '@/hooks/use-api-query';
import { ErrorState, LoadingState, MetaLine } from '@/components/status-state';
import { ensureRecord } from '@/lib/query-parse';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import Link from 'next/link';

type ModuleKey = 'var' | 'stress' | 'exposure';
type RiskSummary = {
  portfolioId?: number | null; lookbackDays?: number;
  varResult?: unknown; stressResult?: unknown; exposureResult?: unknown;
  moduleStatus?: Partial<Record<ModuleKey, { ok?: boolean; reason?: string | null }>>;
  degraded?: boolean; degradeReasons?: string[];
  meta?: { fetchedAt?: string; cache?: { hit?: boolean; backend?: string; ttlSeconds?: number } };
};

const LOOKBACK_PRESETS = [90, 252, 504] as const;

function buildRiskQueryString(portfolioId: string, lookbackDays: string) {
  const qs = new URLSearchParams();
  if (portfolioId) qs.set('portfolioId', portfolioId);
  qs.set('lookbackDays', lookbackDays || '252');
  return qs.toString();
}

function brief(v: unknown): string {
  if (v == null) return '无数据';
  if (Array.isArray(v)) return `数组(${v.length})`;
  if (typeof v !== 'object') return String(v);
  const o = v as Record<string, unknown>;
  const pairs = Object.entries(o).filter(([, x]) => ['string', 'number', 'boolean'].includes(typeof x)).slice(0, 3);
  if (!pairs.length) return `对象(${Object.keys(o).length}键)`;
  return pairs.map(([k, x]) => `${k}:${String(x)}`).join(' | ');
}

export default function RiskPage() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const [portfolioId, setPortfolioId] = useState(() => searchParams.get('portfolioId') ?? '');
  const [lookbackDays, setLookbackDays] = useState(() => searchParams.get('lookbackDays') ?? '252');
  const [formError, setFormError] = useState<string | null>(null);
  const task = searchParams.get('task');
  const from = searchParams.get('from');
  const submittedQs = useMemo(
    () => buildRiskQueryString(searchParams.get('portfolioId') ?? '', searchParams.get('lookbackDays') ?? '252'),
    [searchParams],
  );

  const summaryQ = useApiQuery<RiskSummary>(
    submittedQs ? `/risk/summary?${submittedQs}` : null,
    {
      parse: (raw) => {
        const obj = ensureRecord(raw, '风险汇总');
        if ('moduleStatus' in obj && obj.moduleStatus != null && typeof obj.moduleStatus !== 'object') {
          throw new Error('风险汇总.moduleStatus 字段类型异常');
        }
        return obj as RiskSummary;
      },
    },
  );
  const varQ = useApiQuery<unknown>(
    submittedQs ? `/risk/var?${submittedQs}` : null,
    { parse: (raw) => ensureRecord(raw, '风险VaR') },
  );

  const loading = summaryQ.isFetching || varQ.isFetching;
  const error = formError || summaryQ.error || varQ.error;
  const summary = summaryQ.data;
  const varResult = useMemo(() => {
    if (!varQ.data || typeof varQ.data !== 'object') return null;
    const raw = varQ.data as Record<string, unknown>;
    return raw.result && typeof raw.result === 'object'
      ? raw.result as Record<string, unknown>
      : raw;
  }, [varQ.data]);

  function onLoad(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setFormError(null);
    if (portfolioId && !/^\d+$/.test(portfolioId)) return setFormError('portfolioId 必须为数字');
    if (!/^\d+$/.test(lookbackDays)) return setFormError('lookbackDays 必须为数字');
    const newQs = buildRiskQueryString(portfolioId, lookbackDays);
    if (newQs === submittedQs) { summaryQ.refetch(); varQ.refetch(); }
    else router.replace(`${pathname}?${newQs}`, { scroll: false });
  }

  const topCards = useMemo(() => {
    const cache = summary?.meta?.cache;
    return {
      portfolioId: String(summary?.portfolioId ?? '-'),
      lookbackDays: String(summary?.lookbackDays ?? '-'),
      degraded: summary?.degraded ? '是' : '否',
      cache: cache ? `${cache.hit ? '命中' : '未命中'}(${cache.backend ?? '-'}) TTL=${cache.ttlSeconds ?? '-'}s` : '-',
    };
  }, [summary]);

  const moduleCards = useMemo(() => {
    const cfg: Array<{ key: ModuleKey; title: string; data: unknown }> = [
      { key: 'var', title: 'VaR', data: summary?.varResult },
      { key: 'stress', title: '压力测试', data: summary?.stressResult },
      { key: 'exposure', title: '风险暴露', data: summary?.exposureResult },
    ];
    return cfg.map((x) => {
      const st = summary?.moduleStatus?.[x.key];
      const ok = st?.ok ?? x.data != null;
      return { ...x, status: ok ? '成功' : summary?.degraded ? '降级' : '空数据', reason: st?.reason ?? null, brief: brief(x.data) };
    });
  }, [summary]);

  const varBarItems = useMemo(() => {
    if (!varResult) return [];
    const candidates = [
      { label: 'VaR 金额', value: Number(((varResult.var as Record<string, unknown> | undefined)?.amount ?? (varResult as Record<string, unknown>).var_amount) ?? NaN) },
      { label: 'CVaR 金额', value: Number(((varResult.cvar as Record<string, unknown> | undefined)?.amount ?? (varResult as Record<string, unknown>).cvar_amount) ?? NaN) },
      { label: 'VaR 百分比', value: Number(((varResult.var as Record<string, unknown> | undefined)?.percentage ?? (varResult as Record<string, unknown>).var_percent ?? (varResult as Record<string, unknown>).var95) ?? NaN) },
      { label: 'CVaR 百分比', value: Number(((varResult.cvar as Record<string, unknown> | undefined)?.percentage ?? (varResult as Record<string, unknown>).cvar_percent) ?? NaN) },
      { label: '波动率', value: Number((varResult as Record<string, unknown>).volatility ?? NaN) },
      { label: '最大回撤', value: Number((varResult as Record<string, unknown>).max_drawdown ?? NaN) },
    ];
    return candidates.filter((item) => Number.isFinite(item.value));
  }, [varResult]);

  const stressItems = useMemo(() => {
    const raw = summary?.stressResult;
    if (!raw || typeof raw !== 'object') return [];
    const obj = raw as Record<string, unknown>;
    const scenarios = (obj.scenarios ?? obj.results ?? obj.items) as Record<string, unknown>[] | undefined;
    if (Array.isArray(scenarios)) {
      return scenarios.map((s) => ({
        label: String(s.name ?? s.scenario ?? ''),
        value: Number(s.impact ?? s.loss ?? s.change ?? 0),
      }));
    }
    return Object.entries(obj)
      .filter(([, v]) => typeof v === 'number')
      .slice(0, 8)
      .map(([k, v]) => ({ label: k, value: Number(v) }));
  }, [summary]);

  const exposureItems = useMemo(() => {
    const raw = summary?.exposureResult;
    if (!raw || typeof raw !== 'object') return [];
    const obj = raw as Record<string, unknown>;
    const sectors = (obj.sectors ?? obj.sector_exposure ?? obj.items) as Record<string, unknown>[] | undefined;
    if (Array.isArray(sectors)) {
      return sectors.map((s) => ({
        name: String(s.name ?? s.sector ?? ''),
        value: Number(s.weight ?? s.exposure ?? s.ratio ?? 0),
      }));
    }
    return Object.entries(obj)
      .filter(([, v]) => typeof v === 'number')
      .slice(0, 10)
      .map(([k, v]) => ({ name: k, value: Math.abs(Number(v)) }));
  }, [summary]);

  const allEmpty = !!summary && moduleCards.every((c) => c.data == null);
  const partialDegraded = !!summary?.degraded && moduleCards.some((c) => c.data != null) && moduleCards.some((c) => c.data == null);
  const showInitialEmptyState = !summary && !loading && !error;

  return (
    <PageContainer>
      <h1>风险分析</h1>
      {(from || task) ? (
        <MetaLine>
          上下文跳转
          {from ? ` · 来源: ${from}` : ''}
          {from === 'home' ? ' · 来自首页快捷入口' : ''}
          {task ? ` · 任务：${task}` : ''}
        </MetaLine>
      ) : null}
      {loading ? <LoadingState text="加载风险分析中..." /> : null}
      {error ? <ErrorState text={error} /> : null}

      <SectionCard className="p-4">
        <h3 className="mt-0">参数</h3>
        <p className="text-sm text-text-secondary mt-1 mb-3">优先选择一个组合，再决定用 90 / 252 / 504 天哪个观察窗口来判断风险暴露与回撤特征。</p>
        <form onSubmit={onLoad} className="flex gap-3 flex-wrap items-end">
          <label htmlFor="risk-portfolio-id" className="grid gap-1">
            <span className="text-xs text-text-secondary">组合 ID</span>
            <input id="risk-portfolio-id" value={portfolioId} onChange={(e) => setPortfolioId(e.target.value)} placeholder="可选，不填则尝试自动选择" className="w-[220px] px-2 py-1 rounded text-sm" />
          </label>
          <label htmlFor="risk-lookback-days" className="grid gap-1">
            <span className="text-xs text-text-secondary">回看天数</span>
            <input id="risk-lookback-days" value={lookbackDays} onChange={(e) => setLookbackDays(e.target.value)} placeholder="252" className="w-[160px] px-2 py-1 rounded text-sm" />
          </label>
          <div className="flex gap-2 flex-wrap">
            {LOOKBACK_PRESETS.map((days) => (
              <button
                key={days}
                type="button"
                onClick={() => setLookbackDays(String(days))}
                className={`px-3 py-1 rounded-full text-xs border cursor-pointer ${lookbackDays === String(days) ? 'border-primary text-primary' : 'border-glass-border text-text-secondary'}`}
              >
                {days} 天
              </button>
            ))}
          </div>
          <button type="submit">查询风险</button>
        </form>
      </SectionCard>

      <KpiGrid cols={4} className="mt-3">
        <KpiCard title="组合ID" value={topCards.portfolioId} />
        <KpiCard title="回看天数" value={topCards.lookbackDays} />
        <KpiCard title="降级状态" value={topCards.degraded} />
        <KpiCard title="缓存" value={topCards.cache} />
      </KpiGrid>

      {showInitialEmptyState ? (
        <SectionCard className="mt-3 p-5">
          <h3 className="mt-0">还没有可分析的风险上下文</h3>
          <p className="text-sm text-text-secondary mb-3">如果还没有组合或模拟持仓，这里不会直接给出有意义的 VaR、压力测试和暴露结果。建议先准备可分析的资产上下文。</p>
          <div className="flex gap-2 flex-wrap">
            <Link href="/portfolio" className="px-3 py-1.5 rounded border border-border text-sm no-underline text-inherit hover:bg-surface-alt">去创建组合</Link>
            <Link href="/paper-trading" className="px-3 py-1.5 rounded border border-border text-sm no-underline text-inherit hover:bg-surface-alt">去模拟交易</Link>
          </div>
        </SectionCard>
      ) : null}
      {allEmpty ? (
        <SectionCard className="mt-3 p-4">
          <h3 className="mt-0 text-base">暂无可用风险结果</h3>
          <p className="m-0 text-sm text-text-secondary">当前组合或账户还没有足够数据来生成 VaR、压力测试和暴露分析。先补充持仓，再重新运行风险分析会更有意义。</p>
        </SectionCard>
      ) : null}
      {partialDegraded ? <MetaLine>检测到部分降级。</MetaLine> : null}
      {summary?.degraded && summary.degradeReasons?.length ? <MetaLine>降级原因：{summary.degradeReasons.join(' | ')}</MetaLine> : null}

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mt-3">
        {moduleCards.map((m) => (
          <SectionCard key={m.key} className="p-4">
            <div className="flex items-center justify-between mb-2">
              <span className="font-medium">{m.title}</span>
              <Badge variant={m.status === '成功' ? 'success' : m.status === '降级' ? 'warning' : 'neutral'}>
                {m.status}
              </Badge>
            </div>
            <div className="text-sm text-text-secondary">{m.brief}</div>
            {m.reason && <div className="mt-2 text-xs text-warning">原因: {m.reason}</div>}
          </SectionCard>
        ))}
      </div>

      {varBarItems.length > 0 && (
        <SectionCard className="p-4 mt-3">
          <h3 className="mt-0">VaR 分布</h3>
          <BarChart items={varBarItems} height={240} yAxisName="VaR" colorByValue />
        </SectionCard>
      )}

      {/* Stress Test + Exposure side by side */}
      {(stressItems.length > 0 || exposureItems.length > 0) && (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mt-3">
          {stressItems.length > 0 && (
            <SectionCard className="p-4">
              <h3 className="mt-0">压力测试场景</h3>
              <BarChart items={stressItems} height={220} yAxisName="影响(%)" colorByValue />
            </SectionCard>
          )}
          {exposureItems.length > 0 && (
            <SectionCard className="p-4">
              <h3 className="mt-0">风险暴露分布</h3>
              <PieChart data={exposureItems} donut height={220} />
            </SectionCard>
          )}
        </div>
      )}

      {(summary || varQ.data != null) ? (
        <SectionCard className="p-4 mt-3">
          <h3 className="mt-0">技术详情（排查用）</h3>
          <p className="text-sm text-text-secondary mt-1 mb-3">下面是接口返回的原始数据，默认收起，只有在需要排查数据源异常或降级原因时再展开查看。</p>
          {summary ? (
            <details className="mt-2">
              <summary className="cursor-pointer text-text-secondary text-sm">查看风险汇总原始数据（summary）</summary>
              <pre className="mt-1 text-xs glass p-3 rounded-xl overflow-auto max-h-[300px]">{JSON.stringify(summary, null, 2)}</pre>
            </details>
          ) : null}
          {varQ.data != null ? (
            <details className="mt-2">
              <summary className="cursor-pointer text-text-secondary text-sm">查看 VaR 原始数据（varOnly）</summary>
              <pre className="mt-1 text-xs glass p-3 rounded-xl overflow-auto max-h-[300px]">{JSON.stringify(varQ.data, null, 2)}</pre>
            </details>
          ) : null}
        </SectionCard>
      ) : null}
    </PageContainer>
  );
}
