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

const CONDITION_OPTIONS = [
  { value: '>', label: '大于' },
  { value: '<', label: '小于' },
  { value: '>=', label: '大于等于' },
  { value: '<=', label: '小于等于' },
  { value: '==', label: '等于' },
] as const;

const STATUS_OPTIONS = [
  { value: 'active', label: '生效中' },
  { value: 'inactive', label: '已停用' },
  { value: 'all', label: '全部' },
] as const;

const ALERT_TEMPLATES = [
  { label: '价格突破', indicator: 'price', condition: '>', value: '1800' },
  { label: 'RSI 超卖', indicator: 'rsi', condition: '<', value: '30' },
  { label: '成交量放大', indicator: 'volume_ratio', condition: '>', value: '2' },
] as const;

export default function AlertsPage() {
  const { code, setCode, codeError, validate, trimmedCode } = useStockCode('600519');
  const [indicator, setIndicator] = useState('price');
  const [condition, setCondition] = useState('>');
  const [value, setValue] = useState('1800');
  const [status, setStatus] = useState('active');
  const [lastCreatedSummary, setLastCreatedSummary] = useState<string | null>(null);

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
      setLastCreatedSummary(`${trimmedCode} · ${indicator.trim()} ${condition} ${value.trim()}`);
    } catch { /* error captured by mutation */ }
  }

  async function onDelete(id: string) {
    try {
      await deleteApi.triggerAsync(`/alerts/delete?alertId=${encodeURIComponent(id)}`, { method: 'DELETE' });
      setLastCreatedSummary(null);
    } catch { /* error captured by mutation */ }
  }

  const items = useMemo(() => listQ.data?.items ?? [], [listQ.data]);
  const freshness = listQ.data?.meta?.fetchedAt ?? '';
  const cache = listQ.data?.meta?.cache;
  const indicatorKey = indicator.trim().toLowerCase();
  const indicatorHint = useMemo(() => {
    if (indicatorKey === 'price') return '价格告警按元填写，例如 `> 1800` 表示股价上穿 1800 元。';
    if (indicatorKey === 'rsi') return 'RSI 取值范围通常是 0-100，常见阈值是 30 / 70。';
    if (indicatorKey === 'volume_ratio') return '量比大于 2 通常表示明显放量，适合盘中异动监控。';
    return '常用指标包括 `price`、`rsi`、`volume_ratio`，也可以按后端支持的指标名扩展。';
  }, [indicatorKey]);
  const thresholdHint = useMemo(() => {
    if (indicatorKey === 'rsi') return 'RSI 阈值建议填写 0-100 之间的整数，例如 30 或 70。';
    if (indicatorKey === 'volume_ratio') return '量比阈值通常使用 1.5、2、3 这类倍数值。';
    return '阈值会按照你选择的指标解释；价格单位为元，其它指标按各自量纲处理。';
  }, [indicatorKey]);

  function applyTemplate(template: typeof ALERT_TEMPLATES[number]) {
    setIndicator(template.indicator);
    setCondition(template.condition);
    setValue(template.value);
  }

  return (
    <PageContainer narrow>
      <h1>告警中心</h1>
      <div className="grid gap-4 lg:grid-cols-[minmax(0,0.92fr)_minmax(320px,1.08fr)]">
        <SectionCard className="p-4">
          <div className="flex items-start justify-between gap-3">
            <div>
              <h3 className="mt-0 mb-1">创建告警</h3>
              <p className="m-0 text-xs leading-5 text-text-secondary">模板、创建结果和列表放在同一任务流中。创建成功后右侧会立即显示最新结果，避免“创建完不知道去哪看”。</p>
            </div>
            <Badge variant="info">步骤 1</Badge>
          </div>
          <div className="mt-3 mb-3 flex gap-2 flex-wrap">
            {ALERT_TEMPLATES.map((template) => (
              <button
                key={template.label}
                type="button"
                onClick={() => applyTemplate(template)}
                className="text-xs px-3 py-1 rounded-full border border-border cursor-pointer hover:bg-surface-alt"
              >
                {template.label}
              </button>
            ))}
          </div>
          <form onSubmit={onCreate} className="grid gap-3 md:grid-cols-2">
            <StockCodeInput id="alerts-stock-code" label="股票代码" value={code} onChange={setCode} error={codeError} placeholder="如 600519" />
            <label className="grid gap-1 text-xs text-text-secondary">
              <span>指标</span>
              <input
                id="alerts-indicator"
                value={indicator}
                onChange={(e) => setIndicator(e.target.value)}
                list="alerts-indicator-options"
                placeholder="如 price / rsi"
                aria-describedby="alerts-indicator-help"
                className="px-2 py-1 rounded text-sm"
              />
              <span id="alerts-indicator-help" className="text-[11px] leading-5 text-text-muted">{indicatorHint}</span>
            </label>
            <label className="grid gap-1 text-xs text-text-secondary">
              <span>条件</span>
              <select id="alerts-condition" value={condition} onChange={(e) => setCondition(e.target.value)} className="px-2 py-1 rounded text-sm">
                {CONDITION_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>{option.label}</option>
                ))}
              </select>
            </label>
            <label className="grid gap-1 text-xs text-text-secondary">
              <span>阈值</span>
              <input id="alerts-threshold" value={value} onChange={(e) => setValue(e.target.value)} placeholder="输入阈值" aria-describedby="alerts-threshold-help" className="px-2 py-1 rounded text-sm" />
              <span id="alerts-threshold-help" className="text-[11px] leading-5 text-text-muted">{thresholdHint}</span>
            </label>
            <div className="md:col-span-2 rounded-xl border border-border bg-surface-alt/40 p-3 text-xs text-text-secondary">
              <div className="font-medium text-text-primary">当前预览</div>
              <div className="mt-2">{trimmedCode || '股票代码'} · {indicator.trim() || '指标'} {condition} {value.trim() || '阈值'}</div>
              <div className="mt-1">创建后会自动刷新列表，并保留当前筛选条件。</div>
            </div>
            <button type="submit" disabled={loading} className="md:col-span-2">{loading ? '处理中...' : '创建告警'}</button>
          </form>
          <datalist id="alerts-indicator-options">
            <option value="price" />
            <option value="rsi" />
            <option value="volume_ratio" />
          </datalist>
        </SectionCard>

        <SectionCard className="p-4">
          <div className="flex items-start justify-between gap-3 mb-3">
            <div>
              <h3 className="mt-0 mb-1 flex items-center gap-2">
                告警列表
                <Badge variant={items.length > 0 ? 'info' : 'neutral'}>{items.length}</Badge>
              </h3>
              <p className="m-0 text-xs leading-5 text-text-secondary">创建成功后，最新结果会在这里直接可见；也可以随时切换状态筛选查看当前生效中的规则。</p>
            </div>
            <Badge variant="neutral">步骤 2</Badge>
          </div>
          {lastCreatedSummary ? (
            <div className="mb-3 rounded-xl border border-primary/20 bg-primary/5 px-3 py-2 text-xs text-text-secondary">
              最近创建：<span className="font-medium text-text-primary">{lastCreatedSummary}</span>
            </div>
          ) : null}
          <div className="mb-3 flex gap-2.5 items-end flex-wrap">
            <label className="grid gap-1 text-xs text-text-secondary">
              <span>状态筛选</span>
              <select value={status} onChange={(e) => setStatus(e.target.value)} className="px-2 py-1 rounded text-sm">
                {STATUS_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>{option.label}</option>
                ))}
              </select>
            </label>
            <button type="button" disabled={loading} onClick={() => listQ.refetch()}>{loading ? '加载中...' : '刷新列表'}</button>
          </div>
          {loading ? <LoadingState text="处理中..." /> : null}
          {error ? <ErrorState text={error} hint="请稍后重试" /> : null}
          <MetaLine>更新：{listQ.dataUpdatedAt ? new Date(listQ.dataUpdatedAt).toLocaleString('zh-CN') : '-'} ｜ 抓取：{freshness ? new Date(freshness).toLocaleString('zh-CN') : '-'} ｜ 来源：{fmt(listQ.data?.sourceTool)} ｜ 缓存：{cacheText(cache)}</MetaLine>
          <div className="mt-3 max-h-[520px] overflow-auto space-y-2">
            {items.map((it, idx) => {
              const id = it.id;
              return (
                <div key={`${id || 'row'}-${idx}`} className="glass rounded-lg p-3 flex items-center justify-between gap-3">
                  <div className="flex items-center gap-3 min-w-0">
                    <div className="w-1 h-10 rounded-full bg-primary" />
                    <div className="min-w-0">
                      <div className="font-semibold text-sm">{fmt(it.code)} - {fmt(it.indicator)}</div>
                      <div className="text-xs text-text-secondary mt-0.5 break-all">
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
            {!items.length ? <EmptyState text="暂无告警数据，先创建或点击刷新列表。" hint="你也可以先套用下方模板，再回到左侧完成创建。" /> : null}
            {!items.length ? (
              <div className="flex justify-center gap-2 flex-wrap pb-2">
                {ALERT_TEMPLATES.map((template) => (
                  <button
                    key={`empty-${template.label}`}
                    type="button"
                    onClick={() => applyTemplate(template)}
                    className="text-xs px-3 py-1 rounded-full border border-border cursor-pointer hover:bg-surface-alt"
                  >
                    使用{template.label}模板
                  </button>
                ))}
              </div>
            ) : null}
          </div>
        </SectionCard>
      </div>
    </PageContainer>
  );
}
