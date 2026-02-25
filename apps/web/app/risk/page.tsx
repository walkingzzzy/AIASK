'use client';

import { FormEvent, useMemo, useState } from 'react';
import { PageContainer, SectionCard, KpiCard, KpiGrid, Badge } from '@/components/ui';
import { BarChart, PieChart } from '@/components/charts';
import { useApiQuery } from '@/hooks/use-api-query';
import { EmptyState, ErrorState, LoadingState, MetaLine } from '@/components/status-state';
import { ensureRecord } from '@/lib/query-parse';

type ModuleKey = 'var' | 'stress' | 'exposure';
type RiskSummary = {
  portfolioId?: number | null; lookbackDays?: number;
  varResult?: unknown; stressResult?: unknown; exposureResult?: unknown;
  moduleStatus?: Partial<Record<ModuleKey, { ok?: boolean; reason?: string | null }>>;
  degraded?: boolean; degradeReasons?: string[];
  meta?: { fetchedAt?: string; cache?: { hit?: boolean; backend?: string; ttlSeconds?: number } };
};

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
  const [portfolioId, setPortfolioId] = useState('');
  const [lookbackDays, setLookbackDays] = useState('252');
  const [formError, setFormError] = useState<string | null>(null);
  const [submittedQs, setSubmittedQs] = useState<string | null>(null);

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

  function onLoad(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setFormError(null);
    if (portfolioId && !/^\d+$/.test(portfolioId)) return setFormError('portfolioId 必须为数字');
    if (!/^\d+$/.test(lookbackDays)) return setFormError('lookbackDays 必须为数字');
    const qs = new URLSearchParams();
    if (portfolioId) qs.set('portfolioId', portfolioId);
    qs.set('lookbackDays', lookbackDays);
    const newQs = qs.toString();
    if (newQs === submittedQs) { summaryQ.refetch(); varQ.refetch(); }
    else setSubmittedQs(newQs);
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
    if (!varQ.data || typeof varQ.data !== 'object') return [];
    return Object.entries(varQ.data as Record<string, unknown>)
      .filter(([, v]) => typeof v === 'number')
      .slice(0, 10)
      .map(([k, v]) => ({ label: k, value: Number(v) }));
  }, [varQ.data]);

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

  return (
    <PageContainer>
      <h1>风险分析</h1>
      {loading ? <LoadingState text="加载风险分析中..." /> : null}
      {error ? <ErrorState text={error} /> : null}

      <SectionCard className="p-4">
        <h3 className="mt-0">参数</h3>
        <form onSubmit={onLoad} className="flex gap-2 flex-wrap">
          <input value={portfolioId} onChange={(e) => setPortfolioId(e.target.value)} placeholder="portfolioId（可选）" className="w-[180px] px-2 py-1 rounded text-sm" />
          <input value={lookbackDays} onChange={(e) => setLookbackDays(e.target.value)} placeholder="lookbackDays" className="w-[160px] px-2 py-1 rounded text-sm" />
          <button type="submit">查询风险</button>
        </form>
      </SectionCard>

      <KpiGrid cols={4} className="mt-3">
        <KpiCard title="组合ID" value={topCards.portfolioId} />
        <KpiCard title="回看天数" value={topCards.lookbackDays} />
        <KpiCard title="降级状态" value={topCards.degraded} />
        <KpiCard title="缓存" value={topCards.cache} />
      </KpiGrid>

      {!summary ? <EmptyState text="暂无结果，请先执行查询" /> : null}
      {allEmpty ? <MetaLine>当前三大子模块均无数据。</MetaLine> : null}
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

      {summary ? <details className="mt-3"><summary className="cursor-pointer text-text-secondary text-sm">summary JSON</summary><pre className="mt-1 text-xs glass p-3 rounded-xl overflow-auto max-h-[300px]">{JSON.stringify(summary, null, 2)}</pre></details> : null}
      {varQ.data != null ? <details><summary className="cursor-pointer text-text-secondary text-sm">varOnly JSON</summary><pre className="mt-1 text-xs glass p-3 rounded-xl overflow-auto max-h-[300px]">{JSON.stringify(varQ.data, null, 2)}</pre></details> : null}
    </PageContainer>
  );
}
