'use client';

import { FormEvent, useMemo, useState } from 'react';
import { PageContainer, SectionCard, StockCodeInput, Badge } from '@/components/ui';
import { useApiQuery } from '@/hooks/use-api-query';
import { useApiMutation } from '@/hooks/use-api-mutation';
import { apiKeys } from '@/lib/query-keys';
import { useStockCode } from '@/hooks/use-stock-code';
import { EmptyState, ErrorState, LoadingState, MetaLine } from '@/components/status-state';
import { fmt, cacheText, type CacheMeta } from '@/lib/api';

type AlertItem = { id: string; code: string; indicator: string; condition: string; value: number | null };
type ListData = { status?: string; items?: AlertItem[]; sourceTool?: string; meta?: CacheMeta };

export default function AlertsPage() {
  const { code, setCode, codeError, validate, trimmedCode } = useStockCode('600519');
  const [indicator, setIndicator] = useState('price');
  const [condition, setCondition] = useState('>');
  const [value, setValue] = useState('1800');
  const [status, setStatus] = useState('active');

  const listQ = useApiQuery<ListData>(`/alerts/list?status=${encodeURIComponent(status)}`);
  const createApi = useApiMutation<unknown>({ invalidates: [[...apiKeys.alerts()]] });
  const deleteApi = useApiMutation<unknown>({ invalidates: [[...apiKeys.alerts()]] });

  const loading = listQ.isFetching || createApi.isPending || deleteApi.isPending;
  const error = listQ.error || createApi.error || deleteApi.error;

  async function onCreate(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!validate()) return;
    try {
      await createApi.triggerAsync('/alerts/create', { method: 'POST' }, {
        code: trimmedCode, indicator: indicator.trim(), condition, value: value.trim(),
      });
    } catch { /* error captured by mutation */ }
  }

  async function onDelete(id: string) {
    try {
      await deleteApi.triggerAsync(`/alerts/delete?alertId=${encodeURIComponent(id)}`, { method: 'DELETE' });
    } catch { /* error captured by mutation */ }
  }

  const items = useMemo(() => listQ.data?.items ?? [], [listQ.data]);
  const freshness = listQ.data?.meta?.fetchedAt ?? '';
  const cache = listQ.data?.meta?.cache;

  return (
    <PageContainer narrow>
      <h1>告警中心</h1>
      <SectionCard className="p-4 mb-3">
        <h3 className="mt-0 mb-3">创建告警</h3>
        <form onSubmit={onCreate} className="flex gap-2.5 flex-wrap items-center">
          <StockCodeInput value={code} onChange={setCode} error={codeError} placeholder="如 600519" />
          <input value={indicator} onChange={(e) => setIndicator(e.target.value)} placeholder="indicator，如 price/rsi" className="px-2 py-1 rounded text-sm" />
          <select value={condition} onChange={(e) => setCondition(e.target.value)} className="px-2 py-1 rounded text-sm">
            <option value=">">&gt;</option><option value="<">&lt;</option><option value=">=">&gt;=</option><option value="<=">&lt;=</option><option value="==">==</option>
          </select>
          <input value={value} onChange={(e) => setValue(e.target.value)} placeholder="阈值" className="px-2 py-1 rounded text-sm" />
          <button type="submit" disabled={loading}>{loading ? '处理中...' : '创建告警'}</button>
        </form>
      </SectionCard>
      <div className="mt-3 flex gap-2.5 items-center">
        <select value={status} onChange={(e) => setStatus(e.target.value)} className="px-2 py-1 rounded text-sm">
          <option value="active">active</option><option value="inactive">inactive</option><option value="all">all</option>
        </select>
        <button type="button" disabled={loading} onClick={() => listQ.refetch()}>{loading ? '加载中...' : '刷新列表'}</button>
      </div>
      {loading ? <LoadingState text="处理中..." /> : null}
      {error ? <ErrorState text={error} hint="请稍后重试" /> : null}
      <MetaLine>更新：{listQ.dataUpdatedAt ? new Date(listQ.dataUpdatedAt).toLocaleString('zh-CN') : '-'} ｜ 抓取：{freshness ? new Date(freshness).toLocaleString('zh-CN') : '-'} ｜ 来源：{fmt(listQ.data?.sourceTool)} ｜ 缓存：{cacheText(cache)}</MetaLine>
      <SectionCard>
        <h3 className="mt-0 flex items-center gap-2">
          告警列表
          <Badge variant={items.length > 0 ? 'info' : 'neutral'}>{items.length}</Badge>
        </h3>
        <div className="max-h-[420px] overflow-auto space-y-2">
          {items.map((it, idx) => {
            const id = it.id;
            return (
              <div key={`${id || 'row'}-${idx}`} className="glass rounded-lg p-3 flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className="w-1 h-10 rounded-full bg-primary" />
                  <div>
                    <div className="font-semibold text-sm">{fmt(it.code)} - {fmt(it.indicator)}</div>
                    <div className="text-xs text-text-secondary mt-0.5">
                      {fmt(it.condition)} {fmt(it.value)}
                    </div>
                  </div>
                </div>
                {id ? (
                  <button type="button" onClick={() => onDelete(id)} disabled={loading}
                    className="text-xs text-danger cursor-pointer px-2 py-1 rounded hover:bg-danger/10">
                    删除
                  </button>
                ) : null}
              </div>
            );
          })}
          {!items.length ? <EmptyState text="暂无告警数据，先创建或点击刷新列表。" /> : null}
        </div>
      </SectionCard>
    </PageContainer>
  );
}
