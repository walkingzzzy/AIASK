'use client';

import { FormEvent, useMemo, useState } from 'react';
import { PageContainer, SectionCard } from '@/components/ui';
import { useApiMutation } from '@/hooks/use-api-mutation';
import { EmptyState, ErrorState, LoadingState, MetaLine } from '@/components/status-state';

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
  const [injectFail, setInjectFail] = useState('');
  const [formError, setFormError] = useState<string | null>(null);

  const summaryApi = useApiMutation<RiskSummary>();
  const varApi = useApiMutation<unknown>();

  const loading = summaryApi.isPending || varApi.isPending;
  const error = formError || summaryApi.error || varApi.error;
  const summary = summaryApi.data;

  async function onLoad(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setFormError(null);
    if (portfolioId && !/^\d+$/.test(portfolioId)) return setFormError('portfolioId 必须为数字');
    if (!/^\d+$/.test(lookbackDays)) return setFormError('lookbackDays 必须为数字');
    if (injectFail && !['var', 'stress', 'exposure'].includes(injectFail)) return setFormError('injectFail 仅支持 var/stress/exposure');
    const qs = new URLSearchParams();
    if (portfolioId) qs.set('portfolioId', portfolioId);
    qs.set('lookbackDays', lookbackDays);
    if (injectFail) qs.set('injectFail', injectFail);
    try {
      await Promise.all([
        summaryApi.triggerAsync(`/risk/summary?${qs}`),
        varApi.triggerAsync(`/risk/var?${qs}`),
      ]);
    } catch { /* errors captured by mutations */ }
  }

  const topCards = useMemo(() => {
    const cache = summary?.meta?.cache;
    return {
      portfolioId: summary?.portfolioId ?? '-', lookbackDays: summary?.lookbackDays ?? '-', degraded: String(summary?.degraded ?? false),
      cache: cache ? `${cache.hit ? '命中' : '未命中'}(${cache.backend ?? '-'}) TTL=${cache.ttlSeconds ?? '-'}s` : '-',
      fetchedAt: summary?.meta?.fetchedAt ? new Date(summary.meta.fetchedAt).toLocaleString('zh-CN') : '-',
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

  const allEmpty = !!summary && moduleCards.every((c) => c.data == null);
  const partialDegraded = !!summary?.degraded && moduleCards.some((c) => c.data != null) && moduleCards.some((c) => c.data == null);
  return (
    <PageContainer>
      <h1>风险分析</h1>
      {loading ? <LoadingState text="加载风险分析中..." /> : null}
      {error ? <ErrorState text={error} /> : null}
      <SectionCard>
        <h3 className="mt-0">参数</h3>
        <form onSubmit={onLoad} className="flex gap-2 flex-wrap">
          <input value={portfolioId} onChange={(e) => setPortfolioId(e.target.value)} placeholder="portfolioId（可选）" className="w-[180px] px-2 py-1 border border-border rounded text-sm" />
          <input value={lookbackDays} onChange={(e) => setLookbackDays(e.target.value)} placeholder="lookbackDays" className="w-[160px] px-2 py-1 border border-border rounded text-sm" />
          <input value={injectFail} onChange={(e) => setInjectFail(e.target.value)} placeholder="injectFail（可选）" className="w-[280px] px-2 py-1 border border-border rounded text-sm" />
          <button type="submit">查询风险</button>
        </form>
      </SectionCard>
      <section className="grid grid-cols-[repeat(5,minmax(120px,1fr))] gap-2 mt-3">
        {Object.entries(topCards).map(([k, v]) => (
          <div key={k} className="border border-border rounded-lg p-2">
            <div className="text-text-secondary text-xs">{k}</div>
            <b>{String(v)}</b>
          </div>
        ))}
      </section>
      {!summary ? <EmptyState text="暂无结果，请先执行查询" /> : null}
      {allEmpty ? <MetaLine>当前三大子模块均无数据。</MetaLine> : null}
      {partialDegraded ? <MetaLine>检测到部分降级。</MetaLine> : null}
      {summary?.degraded && summary.degradeReasons?.length ? <MetaLine>降级原因：{summary.degradeReasons.join(' | ')}</MetaLine> : null}
      <section className="grid grid-cols-[repeat(3,minmax(220px,1fr))] gap-2 mt-3">
        {moduleCards.map((m) => (
          <div key={m.key} className="border border-border rounded-lg p-2.5">
            <div className="text-xs text-text-secondary">{m.title}</div><b>{m.status}</b>
            <div className="mt-1.5 text-[13px]">摘要：{m.brief}</div>
            {m.reason ? <div className="mt-1.5 text-warning text-xs">原因：{m.reason}</div> : null}
          </div>
        ))}
      </section>
      {summary ? <details className="mt-3"><summary className="cursor-pointer text-text-secondary text-sm">summary JSON</summary><pre className="mt-1 text-xs bg-surface-alt p-2 rounded overflow-auto max-h-[300px]">{JSON.stringify(summary, null, 2)}</pre></details> : null}
      {varApi.data != null ? <details><summary className="cursor-pointer text-text-secondary text-sm">varOnly JSON</summary><pre className="mt-1 text-xs bg-surface-alt p-2 rounded overflow-auto max-h-[300px]">{JSON.stringify(varApi.data, null, 2)}</pre></details> : null}
    </PageContainer>
  );
}
