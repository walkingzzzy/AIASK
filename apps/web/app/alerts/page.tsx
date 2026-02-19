'use client';

import { FormEvent, useMemo, useState } from 'react';
import { PageContainer, SectionCard, StockCodeInput } from '@/components/ui';
import { useApiMutation } from '@/hooks/use-api-mutation';
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
  const [updatedAt, setUpdatedAt] = useState('');

  const list = useApiMutation<ListData>();
  const createApi = useApiMutation<unknown>();
  const deleteApi = useApiMutation<unknown>();

  const loading = list.isPending || createApi.isPending || deleteApi.isPending;
  const error = list.error || createApi.error || deleteApi.error;

  async function fetchList(sv: string) {
    await list.triggerAsync(`/alerts/list?status=${encodeURIComponent(sv)}`);
    setUpdatedAt(new Date().toLocaleString('zh-CN'));
  }

  async function onCreate(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!validate()) return;
    try {
      await createApi.triggerAsync('/alerts/create', { method: 'POST' }, {
        code: trimmedCode, indicator: indicator.trim(), condition, value: value.trim(),
      });
      await fetchList(status);
    } catch { /* error captured by mutation */ }
  }

  async function onRefresh() {
    try { await fetchList(status); } catch { /* error captured by mutation */ }
  }

  async function onDelete(id: string) {
    try {
      await deleteApi.triggerAsync(`/alerts/delete?alertId=${encodeURIComponent(id)}`, { method: 'DELETE' });
      await fetchList(status);
    } catch { /* error captured by mutation */ }
  }

  const items = useMemo(() => list.data?.items ?? [], [list.data]);
  const freshness = list.data?.meta?.fetchedAt ?? '';
  const cache = list.data?.meta?.cache;

  return (
    <PageContainer narrow>
      <h1>告警中心</h1>
      <form onSubmit={onCreate} className="flex gap-2.5 flex-wrap items-center">
        <StockCodeInput value={code} onChange={setCode} error={codeError} placeholder="如 600519" />
        <input value={indicator} onChange={(e) => setIndicator(e.target.value)} placeholder="indicator，如 price/rsi" className="px-2 py-1 border border-border rounded text-sm" />
        <select value={condition} onChange={(e) => setCondition(e.target.value)} className="px-2 py-1 border border-border rounded text-sm">
          <option value=">">&gt;</option><option value="<">&lt;</option><option value=">=">&gt;=</option><option value="<=">&lt;=</option><option value="==">==</option>
        </select>
        <input value={value} onChange={(e) => setValue(e.target.value)} placeholder="阈值" className="px-2 py-1 border border-border rounded text-sm" />
        <button type="submit" disabled={loading}>{loading ? '处理中...' : '创建告警'}</button>
      </form>
      <div className="mt-3 flex gap-2.5 items-center">
        <select value={status} onChange={(e) => setStatus(e.target.value)} className="px-2 py-1 border border-border rounded text-sm">
          <option value="active">active</option><option value="inactive">inactive</option><option value="all">all</option>
        </select>
        <button type="button" disabled={loading} onClick={onRefresh}>{loading ? '加载中...' : '刷新列表'}</button>
      </div>
      {loading ? <LoadingState text="处理中..." /> : null}
      {error ? <ErrorState text={error} hint="请稍后重试" /> : null}
      <MetaLine>更新：{updatedAt || '-'} ｜ 抓取：{freshness ? new Date(freshness).toLocaleString('zh-CN') : '-'} ｜ 来源：{fmt(list.data?.sourceTool)} ｜ 缓存：{cacheText(cache)}</MetaLine>
      <SectionCard>
        <h3 className="mt-0">告警列表（{items.length}）</h3>
        <div className="max-h-[420px] overflow-auto">
          {items.map((it, idx) => {
            const id = it.id;
            return (
              <div key={`${id || 'row'}-${idx}`} className="py-2 border-b border-dashed border-border">
                <div className="font-semibold">{fmt(id) || `item-${idx + 1}`}</div>
                <div>code={fmt(it.code)} indicator={fmt(it.indicator)} condition={fmt(it.condition)} value={fmt(it.value)}</div>
                {id ? <button type="button" onClick={() => onDelete(id)} disabled={loading}>删除</button> : null}
              </div>
            );
          })}
          {!items.length ? <EmptyState text="暂无告警数据，先创建或点击刷新列表。" /> : null}
        </div>
      </SectionCard>
    </PageContainer>
  );
}
