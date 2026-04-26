'use client';

import { FormEvent, useMemo, useState } from 'react';
import { ConfirmDialog, PageContainer, StockCodeInput, Badge } from '@/components/ui';
import ResponsiveResultWorkbench from '@/components/responsive-result-workbench';
import { useApiQuery } from '@/hooks/use-api-query';
import { useApiMutation } from '@/hooks/use-api-mutation';
import { usePageActions } from '@/hooks/use-page-actions';
import { usePageContext } from '@/hooks/use-page-context';
import { apiKeys } from '@/lib/query-keys';
import { buildLocalResultContract, defaultWorkbenchTask, evidenceToSummary } from '@/lib/result-workbench';
import { useStockCode } from '@/hooks/use-stock-code';
import { EmptyState, ErrorState, LoadingState, MetaLine } from '@/components/status-state';
import { cacheText, fmt, type CacheMeta } from '@/lib/api';
import { readTransactionConfirmations } from '@/lib/transaction-confirmations';

type AlertItem = { id: string; code: string; indicator: string; condition: string; value: number | null };
type ListData = { status?: string; items?: AlertItem[]; sourceTool?: string; meta?: CacheMeta };
type PendingAlertAction =
  | {
      type: 'create';
      summary: string;
      payload: { code: string; indicator: string; condition: string; value: string };
    }
  | {
      type: 'delete';
      summary: string;
      alertId: string;
    };

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

const HERO_PRIMARY_BUTTON_CLS =
  'inline-flex cursor-pointer items-center justify-center rounded-full bg-primary px-4 py-2 text-sm font-medium text-white shadow-[0_20px_40px_-24px_rgba(11,107,203,0.52)] transition hover:-translate-y-0.5 hover:shadow-[0_24px_46px_-24px_rgba(11,107,203,0.58)] disabled:cursor-not-allowed disabled:opacity-50';
const HERO_SECONDARY_BUTTON_CLS =
  'action-chip cursor-pointer text-sm text-text-primary shadow-[0_16px_32px_-24px_rgba(15,23,42,0.28)]';
const CHIP_BUTTON_CLS = 'action-chip cursor-pointer text-xs text-text-primary';
const NOTE_CARD_CLS = 'metric-tile rounded-[22px] p-3 text-xs text-text-secondary';
const FIELD_CLS =
  'h-11 rounded-[20px] border border-white/65 bg-white/55 px-4 text-sm text-text-primary shadow-[inset_0_1px_0_rgba(255,255,255,0.75)] outline-none transition placeholder:text-text-muted focus:border-primary/45 focus:bg-white/72';

export default function AlertsPage() {
  const { code, setCode, codeError, validate, trimmedCode } = useStockCode('600519');
  const [indicator, setIndicator] = useState('price');
  const [condition, setCondition] = useState('>');
  const [value, setValue] = useState('1800');
  const [status, setStatus] = useState('active');
  const [lastCreatedSummary, setLastCreatedSummary] = useState<string | null>(null);
  const [pendingAction, setPendingAction] = useState<PendingAlertAction | null>(null);

  const profileQ = useApiQuery<Record<string, unknown>>('/auth/profile');
  const listQ = useApiQuery<ListData>(`/alerts/list?status=${encodeURIComponent(status)}`);
  const createApi = useApiMutation<unknown>({ invalidates: [[...apiKeys.alerts()]] });
  const deleteApi = useApiMutation<unknown>({ invalidates: [[...apiKeys.alerts()]] });

  const loading = listQ.isFetching || createApi.isPending || deleteApi.isPending;
  const error = listQ.error || createApi.error || deleteApi.error;
  const confirmPrefs = useMemo(() => readTransactionConfirmations(profileQ.data), [profileQ.data]);

  async function executeCreate(payload: { code: string; indicator: string; condition: string; value: string }, summary: string) {
    await createApi.triggerAsync('/alerts/create', { method: 'POST' }, payload);
    setLastCreatedSummary(summary);
  }

  async function executeDelete(alertId: string) {
    await deleteApi.triggerAsync(`/alerts/delete?alertId=${encodeURIComponent(alertId)}`, { method: 'DELETE' });
    setLastCreatedSummary(null);
  }

  async function onCreate(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!validate()) return;
    const payload = {
      code: trimmedCode,
      indicator: indicator.trim(),
      condition,
      value: value.trim(),
    };
    const summary = `${trimmedCode} · ${indicator.trim()} ${condition} ${value.trim()}`;
    try {
      if (confirmPrefs.alertRuleChange) {
        setPendingAction({ type: 'create', summary, payload });
        return;
      }
      await executeCreate(payload, summary);
    } catch {
      // error handled by mutation hook
    }
  }

  async function onDelete(id: string) {
    try {
      const item = items.find((alert) => alert.id === id);
      const summary = item
        ? `${item.code} · ${item.indicator} ${item.condition} ${item.value ?? '-'}`
        : `规则 ${id}`;
      if (confirmPrefs.alertRuleChange) {
        setPendingAction({ type: 'delete', summary, alertId: id });
        return;
      }
      await executeDelete(id);
    } catch {
      // error handled by mutation hook
    }
  }

  async function handleConfirmAction() {
    if (!pendingAction) return;
    const action = pendingAction;
    setPendingAction(null);
    if (action.type === 'create') {
      await executeCreate(action.payload, action.summary);
      return;
    }
    await executeDelete(action.alertId);
  }

  const items = listQ.data?.items ?? [];
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

  const pageActions = [
    {
      id: 'alerts.refresh',
      label: '刷新告警列表',
      description: '重新拉取当前状态下的告警规则',
      keywords: ['刷新', '告警'],
      scope: 'page' as const,
      pageKey: 'alerts',
      run: async () => {
        await listQ.refetch();
        return { message: '已刷新告警列表' };
      },
    },
    {
      id: 'alerts.apply-price-template',
      label: '套用价格模板',
      description: '快速把表单切到价格突破模板',
      keywords: ['模板', '价格突破'],
      scope: 'page' as const,
      pageKey: 'alerts',
      run: () => {
        applyTemplate(ALERT_TEMPLATES[0]);
        return { message: '已套用价格突破模板' };
      },
    },
    {
      id: 'alerts.toggle-status',
      label: status === 'active' ? '切到全部规则' : '切到生效中',
      description: '在生效中和全部规则之间切换',
      keywords: ['状态', '规则'],
      scope: 'page' as const,
      pageKey: 'alerts',
      run: () => {
        setStatus((prev) => (prev === 'active' ? 'all' : 'active'));
        return { message: status === 'active' ? '已切到全部规则' : '已切到生效中规则' };
      },
    },
  ];

  usePageActions(pageActions);

  const alertsSummary = `当前告警状态 ${STATUS_OPTIONS.find((item) => item.value === status)?.label ?? status}，共 ${items.length} 条规则，正在编辑 ${trimmedCode || '未填写'} 的 ${indicator} 条件。`;
  const alertsResult = buildLocalResultContract({
    summary: alertsSummary,
    pageActions,
    preferredActionIds: ['alerts.refresh', 'alerts.apply-price-template', 'alerts.toggle-status'],
    recommendedLinks: [
      trimmedCode ? { id: 'alerts-open-stock', label: '个股详情', href: `/stock?code=${encodeURIComponent(trimmedCode)}` } : { id: 'alerts-open-market', label: '行情看板', href: '/market?from=alerts' },
      { id: 'alerts-open-watchlist', label: '自选股', href: '/watchlist' },
      { id: 'alerts-open-risk', label: '风险中心', href: '/risk?from=alerts' },
      { id: 'alerts-open-data', label: '数据中心', href: '/data?from=alerts' },
    ],
    evidence: [
      { label: '状态', value: STATUS_OPTIONS.find((item) => item.value === status)?.label ?? status },
      { label: '规则数量', value: String(items.length) },
      { label: '当前代码', value: trimmedCode || '-' },
      { label: '当前指标', value: indicator },
      { label: '抓取时间', value: freshness ? new Date(freshness).toLocaleString('zh-CN') : '-' },
    ],
    riskNotes: error ? [error] : items.length === 0 ? ['当前筛选状态下没有规则，建议先创建第一条告警。'] : [],
    freshness: freshness ? { updatedAt: freshness, label: '告警抓取时间' } : null,
    workbenchTask: defaultWorkbenchTask('alerts', `告警复查：${trimmedCode || '当前规则集'}`, '/alerts', 'alerts-review', {
      code: trimmedCode || null,
      indicator,
      status,
    }),
  });

  usePageContext({
    pageKey: 'alerts',
    title: '告警中心',
    summary: alertsSummary,
    stockCode: trimmedCode || undefined,
    objectType: trimmedCode ? 'stock' : 'workspace',
    objectId: trimmedCode || status,
    resultType: 'alerts-summary',
    tags: [STATUS_OPTIONS.find((item) => item.value === status)?.label ?? status, `${items.length} 条规则`, indicator],
    suggestions: [
      '总结当前告警配置的主要风险点',
      '判断还需要补哪些监控规则',
      '把当前规则集整理成盘中巡检清单',
    ],
    recommendedActions: alertsResult.recommendedActions,
    recommendedLinks: alertsResult.recommendedLinks,
    evidenceSummary: evidenceToSummary(alertsResult.evidence),
    riskNotes: alertsResult.riskNotes ?? [],
    freshness: alertsResult.freshness ?? null,
    raw: {
      code: trimmedCode || null,
      indicator,
      condition,
      value,
      status,
      items: items.length,
    },
  });

  function applyTemplate(template: (typeof ALERT_TEMPLATES)[number]) {
    setIndicator(template.indicator);
    setCondition(template.condition);
    setValue(template.value);
  }

  return (
    <PageContainer narrow>
      <section className="page-hero mb-4 p-5 sm:p-6">
        <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_clamp(280px,25vw,380px)]">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="info">Alerts Workspace</Badge>
              <Badge variant="neutral">{STATUS_OPTIONS.find((item) => item.value === status)?.label ?? status}</Badge>
              <Badge variant={items.length > 0 ? 'success' : 'warning'}>
                {items.length > 0 ? `已加载 ${items.length} 条规则` : '等待创建或加载'}
              </Badge>
            </div>
            <h1 className="mb-0 mt-4 text-[2rem] font-semibold tracking-[-0.03em] text-text-primary sm:text-[2.4rem]">
              告警中心工作台
            </h1>
            <p className="mb-0 mt-3 hidden max-w-3xl text-sm leading-7 text-text-secondary sm:block sm:text-[15px]">
              这一页把模板、创建、筛选和结果放进一条连续链路。先确定监控指标和阈值，再在右侧立即确认列表结果，不用在多个页面之间来回跳转。
            </p>
            <div className="mt-5 flex flex-wrap gap-2">
              <button type="submit" form="alerts-create-form" disabled={loading} className={HERO_PRIMARY_BUTTON_CLS}>
                {loading ? '处理中...' : '创建告警'}
              </button>
              <button type="button" onClick={() => listQ.refetch()} className={HERO_SECONDARY_BUTTON_CLS}>
                刷新列表
              </button>
            </div>

            <div className="mt-5 hidden gap-3 md:grid md:grid-cols-4">
              <div className="rounded-[24px] border border-white/45 bg-white/38 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.55)]">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">当前代码</div>
                <div className="mt-3 text-2xl font-semibold text-text-primary">{trimmedCode || '600519'}</div>
                <div className="mt-1 text-xs text-text-secondary">用于创建下一条监控规则</div>
              </div>
              <div className="rounded-[24px] border border-white/45 bg-white/30 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.48)]">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">当前指标</div>
                <div className="mt-3 text-2xl font-semibold text-text-primary">{indicator}</div>
                <div className="mt-1 text-xs text-text-secondary">
                  {condition} {value}
                </div>
              </div>
              <div className="rounded-[24px] border border-white/45 bg-white/26 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.42)]">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">生效列表</div>
                <div className="mt-3 text-2xl font-semibold text-text-primary">{items.length}</div>
                <div className="mt-1 text-xs text-text-secondary">当前筛选状态下返回的告警数</div>
              </div>
              <div className="rounded-[24px] border border-white/45 bg-white/24 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.38)]">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">最近创建</div>
                <div className="mt-3 text-sm font-semibold leading-6 text-text-primary">
                  {lastCreatedSummary || '尚未创建'}
                </div>
              </div>
            </div>
          </div>

          <div className="hidden gap-3 md:grid">
            <div className="panel-soft rounded-[28px] p-4 sm:p-5">
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">创建提示</div>
              <div className="mt-4 space-y-3">
                <div className={NOTE_CARD_CLS}>1. 先用模板快速建立第一条规则，再按需要微调阈值。</div>
                <div className={NOTE_CARD_CLS}>2. 规则创建后会立即刷新列表，优先确认是否落在当前筛选状态里。</div>
                <div className={NOTE_CARD_CLS}>
                  3. 盘中异动更适合监控 `price` 与 `volume_ratio`，震荡策略更适合 `rsi`。
                </div>
              </div>
            </div>

            <div className="panel-soft rounded-[28px] p-4 sm:p-5">
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">模板捷径</div>
              <div className="mt-4 flex flex-wrap gap-2">
                {ALERT_TEMPLATES.map((template) => (
                  <button
                    key={template.label}
                    type="button"
                    onClick={() => applyTemplate(template)}
                    className={CHIP_BUTTON_CLS}
                  >
                    {template.label}
                  </button>
                ))}
              </div>
            </div>
          </div>
        </div>
      </section>

      <ResponsiveResultWorkbench pageKey="alerts" title="告警结果工作台" result={alertsResult} />

      {error ? <ErrorState text={error} hint="请稍后重试" /> : null}

      <div className="grid gap-4 lg:grid-cols-[minmax(0,0.92fr)_minmax(320px,1.08fr)]">
        <div className="panel-soft rounded-[28px] p-4 sm:p-5">
          <div className="flex items-start justify-between gap-3">
            <div>
              <div className="eyebrow">Create Alert</div>
              <h2 className="mb-0 mt-2 text-xl font-semibold text-text-primary">创建告警</h2>
              <p className="mb-0 mt-2 hidden text-sm leading-7 text-text-secondary sm:block">
                模板、创建结果和列表放在同一任务流中。创建成功后右侧会立即显示最新结果，避免“创建完不知道去哪看”。
              </p>
            </div>
            <Badge variant="info">步骤 1</Badge>
          </div>

          <div className="mt-4 hidden flex-wrap gap-2 sm:flex">
            {ALERT_TEMPLATES.map((template) => (
              <button
                key={template.label}
                type="button"
                onClick={() => applyTemplate(template)}
                className={CHIP_BUTTON_CLS}
              >
                {template.label}
              </button>
            ))}
          </div>

          <form id="alerts-create-form" onSubmit={onCreate} className="mt-4 grid gap-4 md:grid-cols-2">
            <StockCodeInput
              id="alerts-stock-code"
              label="股票代码"
              value={code}
              onChange={setCode}
              error={codeError}
              placeholder="如 600519"
            />
            <label className="grid gap-2 text-xs text-text-secondary">
              <span className="font-medium uppercase tracking-[0.12em] text-text-muted">指标</span>
              <input
                id="alerts-indicator"
                value={indicator}
                onChange={(e) => setIndicator(e.target.value)}
                list="alerts-indicator-options"
                placeholder="如 price / rsi"
                aria-describedby="alerts-indicator-help"
                className={FIELD_CLS}
              />
              <span id="alerts-indicator-help" className="text-[11px] leading-5 text-text-muted">
                {indicatorHint}
              </span>
            </label>
            <label className="grid gap-2 text-xs text-text-secondary">
              <span className="font-medium uppercase tracking-[0.12em] text-text-muted">条件</span>
              <select
                id="alerts-condition"
                value={condition}
                onChange={(e) => setCondition(e.target.value)}
                className={FIELD_CLS}
              >
                {CONDITION_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="grid gap-2 text-xs text-text-secondary">
              <span className="font-medium uppercase tracking-[0.12em] text-text-muted">阈值</span>
              <input
                id="alerts-threshold"
                value={value}
                onChange={(e) => setValue(e.target.value)}
                placeholder="输入阈值"
                aria-describedby="alerts-threshold-help"
                className={FIELD_CLS}
              />
              <span id="alerts-threshold-help" className="text-[11px] leading-5 text-text-muted">
                {thresholdHint}
              </span>
            </label>
            <div className="hidden md:col-span-2 md:block metric-tile rounded-[24px] p-4 text-xs text-text-secondary">
              <div className="font-medium text-text-primary">当前预览</div>
              <div className="mt-2">
                {trimmedCode || '股票代码'} · {indicator.trim() || '指标'} {condition} {value.trim() || '阈值'}
              </div>
              <div className="mt-1">创建后会自动刷新列表，并保留当前筛选条件。</div>
            </div>
          </form>

          <datalist id="alerts-indicator-options">
            <option value="price" />
            <option value="rsi" />
            <option value="volume_ratio" />
          </datalist>
        </div>

        <div className="panel-soft rounded-[28px] p-4 sm:p-5">
          <div className="flex items-start justify-between gap-3">
            <div>
              <div className="eyebrow">Alert List</div>
              <h2 className="mb-0 mt-2 flex items-center gap-2 text-xl font-semibold text-text-primary">
                告警列表
                <Badge variant={items.length > 0 ? 'info' : 'neutral'}>{items.length}</Badge>
              </h2>
              <p className="mb-0 mt-2 hidden text-sm leading-7 text-text-secondary sm:block">
                创建成功后，最新结果会在这里直接可见；也可以随时切换状态筛选查看当前生效中的规则。
              </p>
            </div>
            <Badge variant="neutral">步骤 2</Badge>
          </div>

          {lastCreatedSummary ? (
            <div className="mt-4 metric-tile rounded-[22px] px-4 py-3 text-sm text-text-secondary">
              最近创建：<span className="font-medium text-text-primary">{lastCreatedSummary}</span>
            </div>
          ) : null}

          <div className="mt-4 flex flex-wrap items-end gap-2.5">
            <label className="grid gap-2 text-xs text-text-secondary">
              <span className="font-medium uppercase tracking-[0.12em] text-text-muted">状态筛选</span>
              <select value={status} onChange={(e) => setStatus(e.target.value)} className={FIELD_CLS}>
                {STATUS_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
            <button
              type="button"
              disabled={loading}
              onClick={() => listQ.refetch()}
              className={HERO_SECONDARY_BUTTON_CLS}
            >
              {loading ? '加载中...' : '刷新列表'}
            </button>
          </div>

          {loading ? <LoadingState text="处理中..." /> : null}
          {error ? <ErrorState text={error} hint="请稍后重试" /> : null}

          <MetaLine>
            更新：{listQ.dataUpdatedAt ? new Date(listQ.dataUpdatedAt).toLocaleString('zh-CN') : '-'} ｜ 抓取：
            {freshness ? new Date(freshness).toLocaleString('zh-CN') : '-'} ｜ 来源：{fmt(listQ.data?.sourceTool)} ｜
            缓存：
            {cacheText(cache)}
          </MetaLine>

          <div className="mt-4 max-h-[560px] space-y-2 overflow-auto">
            {items.map((item, index) => {
              const id = item.id;
              return (
                <div
                  key={`${id || 'row'}-${index}`}
                  className="metric-tile flex items-center justify-between gap-3 rounded-[22px] p-3"
                >
                  <div className="flex min-w-0 items-center gap-3">
                    <div className="h-10 w-1 rounded-full bg-primary" />
                    <div className="min-w-0">
                      <div className="text-sm font-semibold text-text-primary">
                        {fmt(item.code)} - {fmt(item.indicator)}
                      </div>
                      <div className="mt-0.5 break-all text-xs text-text-secondary">
                        {fmt(item.condition)} {fmt(item.value)}
                      </div>
                    </div>
                  </div>
                  {id ? (
                    <button
                      type="button"
                      onClick={() => onDelete(id)}
                      disabled={loading}
                      className="rounded-full px-3 py-1 text-xs text-danger transition hover:bg-danger/10"
                    >
                      删除
                    </button>
                  ) : null}
                </div>
              );
            })}

            {!items.length ? (
              <EmptyState
                text="暂无告警数据，先创建或点击刷新列表"
                hint="你也可以先套用模板，再回到左侧完成创建。"
                action={
                  <>
                    {ALERT_TEMPLATES.map((template) => (
                      <button
                        key={`empty-${template.label}`}
                        type="button"
                        onClick={() => applyTemplate(template)}
                        className={CHIP_BUTTON_CLS}
                      >
                        使用{template.label}
                      </button>
                    ))}
                  </>
                }
              />
            ) : null}
          </div>
        </div>
      </div>

      <ConfirmDialog
        open={pendingAction != null}
        title={pendingAction?.type === 'delete' ? '确认删除告警规则' : '确认创建告警规则'}
        confirmText={pendingAction?.type === 'delete' ? '确认删除' : '确认创建'}
        danger={pendingAction?.type === 'delete'}
        onCancel={() => setPendingAction(null)}
        onConfirm={() => { void handleConfirmAction(); }}
      >
        <div className="space-y-2">
          <div>当前操作已开启“告警规则修改”二次确认。</div>
          <div className="text-xs text-text-secondary">
            {pendingAction?.type === 'delete' ? '即将删除：' : '即将创建：'}
            <span className="ml-1 font-medium text-text-primary">{pendingAction?.summary ?? '-'}</span>
          </div>
        </div>
      </ConfirmDialog>
    </PageContainer>
  );
}
