'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import WorkspaceSplitLayout from '@/components/workspace-split-layout';
import WorkspaceToolbar from '@/components/workspace-toolbar';
import { Badge, KpiCard, KpiGrid, PageContainer, SectionCard, StockCodeInput, DataTable } from '@/components/ui';
import { useApiMutation } from '@/hooks/use-api-mutation';
import { useApiQuery } from '@/hooks/use-api-query';
import { usePageActions } from '@/hooks/use-page-actions';
import { usePageContext } from '@/hooks/use-page-context';
import { useStableSearchParams } from '@/hooks/use-stable-search-params';
import { useStockCode } from '@/hooks/use-stock-code';
import { selectActiveWorkspace, useWorkbenchStore } from '@/store/workbench-store';
import type {
  EventImportantResponse,
  EventSubscriptionMutationResponse,
  EventSubscriptionsResponse,
  EventTimelineResponse,
} from '@aiask/shared-types';

const DAY_PRESETS = [3, 7, 14, 30] as const;
const EVENT_TYPES = [
  { key: 'all', label: '全部事件' },
  { key: 'notice', label: '公告' },
  { key: 'research', label: '研报' },
  { key: 'news', label: '新闻' },
] as const;

function eventBadgeVariant(value?: string | null) {
  if (value === 'high' || value === 'today') return 'warning' as const;
  if (value === 'upcoming') return 'info' as const;
  return 'neutral' as const;
}

export default function EventsPage() {
  const router = useRouter();
  const searchParams = useStableSearchParams();
  const workbenchHydrated = useWorkbenchStore((state) => state.hydrated);
  const activeWorkspaceId = useWorkbenchStore((state) => state.activeWorkspaceId);
  const workbenchContext = useWorkbenchStore((state) => selectActiveWorkspace(state).context);
  const updateWorkbenchContext = useWorkbenchStore((state) => state.updateContext);
  const addWorkbenchTask = useWorkbenchStore((state) => state.addTask);
  const initialCode = searchParams.get('code') || workbenchContext.eventCode || workbenchContext.stockCode || '600519';
  const { code, setCode, trimmedCode, validate, codeError } = useStockCode(initialCode);
  const [days, setDays] = useState<number>(() => {
    const raw = Number(searchParams.get('days') ?? 7);
    return Number.isFinite(raw) && raw > 0 ? raw : 7;
  });
  const [type, setType] = useState(searchParams.get('type') ?? 'all');
  const lastWorkspaceIdRef = useRef<string | null>(null);

  const activeCode = useMemo(() => (/^\d{6}$/.test(trimmedCode) ? trimmedCode : ''), [trimmedCode]);
  const importantQ = useApiQuery<EventImportantResponse>(`/event/important?days=${days}&limit=10`);
  const calendarQ = useApiQuery<EventTimelineResponse>(`/event/calendar?days=${days}&type=${encodeURIComponent(type)}`);
  const subscriptionsQ = useApiQuery<EventSubscriptionsResponse>('/event/subscriptions');
  const timelineQ = useApiQuery<EventTimelineResponse>(
    activeCode ? `/event/by-code?code=${encodeURIComponent(activeCode)}&limit=12` : null,
  );
  const subscriptionApi = useApiMutation<EventSubscriptionMutationResponse>({
    invalidates: [['api', 'event']],
  });

  useEffect(() => {
    if (!workbenchHydrated) return;

    const workspaceChanged = lastWorkspaceIdRef.current !== activeWorkspaceId;
    lastWorkspaceIdRef.current = activeWorkspaceId;
    if (!workspaceChanged && searchParams.toString()) return;

    const nextCode = workbenchContext.eventCode || workbenchContext.stockCode;
    if (nextCode) setCode(nextCode);
  }, [activeWorkspaceId, searchParams, setCode, workbenchContext, workbenchHydrated]);

  useEffect(() => {
    const params = new URLSearchParams(searchParams.toString());
    if (activeCode) params.set('code', activeCode);
    else params.delete('code');
    params.set('days', String(days));
    params.set('type', type);
    const nextQs = params.toString();
    if (nextQs !== searchParams.toString()) {
      router.replace(`/events?${nextQs}`, { scroll: false });
    }
  }, [activeCode, days, router, searchParams, type]);

  useEffect(() => {
    if (!workbenchHydrated) return;
    updateWorkbenchContext({
      eventCode: activeCode || null,
      stockCode: activeCode || null,
    });
  }, [activeCode, updateWorkbenchContext, workbenchHydrated]);

  const subscriptions = subscriptionsQ.data?.items ?? [];
  const isSubscribed = Boolean(activeCode && subscriptions.some((item) => item.code === activeCode));
  const importantItems = importantQ.data?.items ?? [];
  const timelineItems = timelineQ.data?.events ?? [];
  const activeTypeLabel = EVENT_TYPES.find((item) => item.key === type)?.label ?? type;
  const nextImportantItem = importantItems[0] ?? null;
  const latestTimelineItem = timelineItems[0] ?? null;
  const latestEventRefreshAt =
    [importantQ.dataUpdatedAt, timelineQ.dataUpdatedAt, subscriptionsQ.dataUpdatedAt]
      .filter((value): value is number => typeof value === 'number' && value > 0)
      .sort((left, right) => right - left)[0] ?? null;
  const latestEventRefreshText = latestEventRefreshAt
    ? new Date(latestEventRefreshAt).toLocaleString('zh-CN')
    : '等待首个事件快照';
  const currentView = useMemo(
    () => ({
      code: activeCode,
      days,
      type,
    }),
    [activeCode, days, type],
  );

  const openStock = useCallback(
    (codeValue: string) => {
      updateWorkbenchContext({ stockCode: codeValue, eventCode: codeValue });
      addWorkbenchTask({
        pageKey: 'events',
        title: `查看 ${codeValue} 个股详情`,
        href: `/stock?code=${encodeURIComponent(codeValue)}`,
        kind: 'stock-review',
        payload: { code: codeValue },
      });
      router.push(`/stock?code=${encodeURIComponent(codeValue)}`);
    },
    [addWorkbenchTask, router, updateWorkbenchContext],
  );

  const openResearch = useCallback(
    (codeValue: string) => {
      updateWorkbenchContext({ stockCode: codeValue, eventCode: codeValue });
      addWorkbenchTask({
        pageKey: 'events',
        title: `查看 ${codeValue} 研究事件`,
        href: `/research?code=${encodeURIComponent(codeValue)}`,
        kind: 'research-review',
        payload: { code: codeValue },
      });
      router.push(`/research?code=${encodeURIComponent(codeValue)}`);
    },
    [addWorkbenchTask, router, updateWorkbenchContext],
  );

  const openExecution = useCallback(
    (codeValue: string) => {
      updateWorkbenchContext({ stockCode: codeValue, eventCode: codeValue });
      addWorkbenchTask({
        pageKey: 'events',
        title: `查看 ${codeValue} 的执行链路`,
        href: `/execution?code=${encodeURIComponent(codeValue)}`,
        kind: 'execution-review',
        payload: { code: codeValue },
      });
      router.push(`/execution?code=${encodeURIComponent(codeValue)}`);
    },
    [addWorkbenchTask, router, updateWorkbenchContext],
  );

  const subscribeCurrentCode = useCallback(async () => {
    if (!validate()) return;
    await subscriptionApi.triggerAsync('/event/subscribe', { method: 'POST' }, { code: activeCode });
  }, [activeCode, subscriptionApi, validate]);

  const unsubscribeCurrentCode = useCallback(
    async (codeValue?: string) => {
      const targetCode = String(codeValue ?? activeCode).trim();
      if (!targetCode) {
        if (!validate()) return;
      }
      const code = targetCode || activeCode;
      if (!code) return;
      await subscriptionApi.triggerAsync('/event/unsubscribe', { method: 'POST' }, { code });
    },
    [activeCode, subscriptionApi, validate],
  );

  usePageContext({
    pageKey: 'events',
    title: '事件日历',
    summary: `当前事件窗口 ${days} 天，重点事件 ${importantItems.length} 条，订阅标的 ${subscriptions.length} 个，聚焦标的 ${activeCode || '未选择'}。`,
    stockCode: activeCode || undefined,
    tags: [
      `${days} 天`,
      `${subscriptions.length} 个订阅`,
      `${importantItems.length} 条重点事件`,
      EVENT_TYPES.find((item) => item.key === type)?.label ?? type,
    ],
    suggestions: [
      isSubscribed ? '取消当前股票事件订阅' : '订阅当前股票事件',
      activeCode ? `打开 ${activeCode} 个股详情` : '选择一个股票查看个股事件时间线',
      '切到 14 天窗口看更长的事件排程',
    ],
    raw: {
      code: activeCode || null,
      days,
      type,
      subscriptions: subscriptions.length,
      subscribed: isSubscribed,
      important: importantItems.length,
      timeline: timelineItems.length,
    },
  });

  const pageActions = useMemo(
    () => [
      {
        id: 'events.refresh',
        label: '刷新事件日历',
        description: '刷新重点事件、事件日历和订阅列表',
        keywords: ['刷新', '事件'],
        scope: 'page' as const,
        pageKey: 'events',
        run: async () => {
          await Promise.allSettled([
            importantQ.refetch(),
            calendarQ.refetch(),
            subscriptionsQ.refetch(),
            timelineQ.refetch(),
          ]);
          return { message: '已刷新事件数据' };
        },
      },
      {
        id: 'events.subscribe',
        label: isSubscribed ? '取消当前股票事件订阅' : '订阅当前股票事件',
        description: isSubscribed
          ? '取消当前股票订阅并移出重点事件聚合范围'
          : '订阅当前股票，后续重点事件会自动进入事件工作台',
        keywords: ['订阅', '事件'],
        scope: 'page' as const,
        pageKey: 'events',
        run: async () => {
          if (isSubscribed) {
            await unsubscribeCurrentCode();
            return { message: `已取消订阅 ${activeCode}` };
          }
          await subscribeCurrentCode();
          return { message: `已订阅 ${activeCode}` };
        },
      },
      {
        id: 'events.unsubscribe',
        label: '取消当前股票事件订阅',
        description: '把当前股票从事件订阅列表移除',
        keywords: ['取消订阅', '事件'],
        scope: 'page' as const,
        pageKey: 'events',
        run: async () => {
          if (!activeCode) throw new Error('当前没有可取消订阅的股票代码');
          await unsubscribeCurrentCode();
          return { message: `已取消订阅 ${activeCode}` };
        },
      },
      {
        id: 'events.open-stock',
        label: '打开个股详情',
        description: '打开当前聚焦股票的详情页',
        keywords: ['个股详情', '股票'],
        scope: 'page' as const,
        pageKey: 'events',
        run: () => {
          if (!activeCode) throw new Error('当前没有可打开的股票代码');
          openStock(activeCode);
          return { message: `已打开 ${activeCode} 个股详情` };
        },
      },
      {
        id: 'events.open-research',
        label: '打开研究事件台',
        description: '把当前股票切换到研究页继续查看公告和研报',
        keywords: ['研究', '公告', '研报'],
        scope: 'page' as const,
        pageKey: 'events',
        run: () => {
          if (!activeCode) throw new Error('当前没有可打开的股票代码');
          openResearch(activeCode);
          return { message: `已打开 ${activeCode} 研究事件台` };
        },
      },
      {
        id: 'events.open-execution',
        label: '打开执行中心',
        description: '查看当前股票的执行和复盘链路',
        keywords: ['执行', '复盘'],
        scope: 'page' as const,
        pageKey: 'events',
        run: () => {
          if (!activeCode) throw new Error('当前没有可打开的股票代码');
          openExecution(activeCode);
          return { message: `已打开 ${activeCode} 执行中心` };
        },
      },
    ],
    [
      activeCode,
      calendarQ,
      importantQ,
      isSubscribed,
      openExecution,
      openResearch,
      openStock,
      subscribeCurrentCode,
      subscriptionsQ,
      timelineQ,
      unsubscribeCurrentCode,
    ],
  );

  usePageActions(pageActions);

  return (
    <PageContainer>
      <section className="mb-4 overflow-hidden rounded-[32px] border border-white/45 bg-[radial-gradient(circle_at_top_left,_rgba(255,255,255,0.28),_rgba(255,255,255,0.08)_35%,_rgba(207,226,255,0.18)_68%,_rgba(190,211,255,0.08)_100%)] p-5 shadow-[0_24px_80px_-40px_rgba(34,86,160,0.42)] backdrop-blur-xl sm:p-6">
        <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_clamp(280px,25vw,380px)]">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="info">Event Workspace</Badge>
              <Badge variant="neutral">{activeTypeLabel}</Badge>
              <Badge variant={isSubscribed ? 'success' : 'neutral'}>
                {isSubscribed ? '已订阅重点事件' : '未订阅当前标的'}
              </Badge>
            </div>
            <h1 className="mb-0 mt-4 text-[2rem] font-semibold tracking-[-0.03em] text-text-primary sm:text-[2.4rem]">
              事件日历工作台
            </h1>
            <p className="mb-0 mt-3 max-w-3xl text-sm leading-7 text-text-secondary sm:text-[15px]">
              把市场事件、重点订阅和单一标的时间线收进同一块工作台。你可以先压缩观察窗口，再沿着研究页、执行中心和个股详情形成一条连续动作链。
            </p>
            <div className="mt-5 flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => (isSubscribed ? unsubscribeCurrentCode() : subscribeCurrentCode())}
                disabled={subscriptionApi.isPending}
                data-testid="page-primary-action"
                data-action-testid="events-subscription-action"
                className={`rounded-full px-4 py-2 text-sm shadow-sm transition disabled:cursor-not-allowed disabled:opacity-50 ${isSubscribed ? 'border border-glass-border bg-white/45 text-text-primary' : 'bg-primary text-white'}`}
              >
                {subscriptionApi.isPending ? '处理中...' : isSubscribed ? '取消订阅当前股票事件' : '订阅当前股票事件'}
              </button>
              {activeCode ? (
                <button
                  type="button"
                  onClick={() => openResearch(activeCode)}
                  className="rounded-full border border-glass-border bg-white/35 px-4 py-2 text-sm text-text-primary shadow-sm"
                >
                  打开研究事件台
                </button>
              ) : null}
            </div>
            <div
              data-testid="page-primary-status"
              className="mt-4 rounded-[22px] border border-white/50 bg-white/28 px-4 py-3 text-sm shadow-[inset_0_1px_0_rgba(255,255,255,0.68)]"
            >
              <div className="font-medium text-text-primary">
                当前焦点 {activeCode || '未选择'}，订阅状态 {isSubscribed ? '已订阅' : '未订阅'}，重点事件{' '}
                {importantItems.length} 条
              </div>
              <p className="mt-1 mb-0 text-xs leading-6 text-text-secondary">
                个股时间线 {timelineItems.length} 条 ｜ 最新事件{' '}
                {latestTimelineItem?.title || nextImportantItem?.title || '当前窗口暂无高优先级事件'}
              </p>
              <p className="mt-2 mb-0 text-xs text-text-secondary">最近更新时间：{latestEventRefreshText}</p>
            </div>

            <div className="mt-5 grid gap-3 sm:grid-cols-3">
              <div className="rounded-[24px] border border-white/45 bg-white/38 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.55)]">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">聚焦标的</div>
                <div className="mt-3 text-2xl font-semibold text-text-primary">{activeCode || '未选择'}</div>
                <div className="mt-1 text-xs text-text-secondary">
                  {activeCode ? '当前时间线与订阅会围绕该股票联动' : '输入股票代码后再拉个股时间线'}
                </div>
              </div>
              <div className="rounded-[24px] border border-white/45 bg-white/30 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.48)]">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">观察窗口</div>
                <div className="mt-3 text-2xl font-semibold text-text-primary">{days} 天</div>
                <div className="mt-1 text-xs text-text-secondary">
                  当前事件类型为 {activeTypeLabel}，重点事件 {importantItems.length} 条
                </div>
              </div>
              <div className="rounded-[24px] border border-white/45 bg-white/26 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.42)]">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">订阅池</div>
                <div className="mt-3 text-2xl font-semibold text-text-primary">{subscriptions.length}</div>
                <div className="mt-1 text-xs text-text-secondary">
                  {subscriptions.length > 0 ? '已接入重点事件聚合与右侧订阅面板' : '还没有纳入任何跟踪标的'}
                </div>
              </div>
            </div>
          </div>

          <div className="grid gap-3">
            <div className="rounded-[28px] border border-white/45 bg-white/34 p-4 shadow-[0_22px_50px_-36px_rgba(36,74,144,0.42)] backdrop-blur-xl">
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">当前焦点</div>
              <div className="mt-3 text-base font-semibold text-text-primary">
                {nextImportantItem?.title || '当前窗口内暂无高优先级事件'}
              </div>
              <div className="mt-3 space-y-2 text-xs leading-6 text-text-secondary">
                <div>
                  重点事件日期：
                  <span className="font-medium text-text-primary">{nextImportantItem?.eventDate || '-'}</span>
                </div>
                <div>
                  来源范围：
                  <span className="font-medium text-text-primary">
                    {nextImportantItem?.scope || nextImportantItem?.source || '-'}
                  </span>
                </div>
                <div>
                  个股时间线：<span className="font-medium text-text-primary">{timelineItems.length} 条</span>
                </div>
              </div>
            </div>

            <div className="rounded-[28px] border border-dashed border-white/40 bg-white/20 p-4 backdrop-blur-xl">
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">下一步建议</div>
              <ul className="mb-0 mt-3 space-y-2 pl-4 text-xs leading-6 text-text-secondary">
                <li>
                  {latestTimelineItem?.title
                    ? `先处理最新个股事件：“${latestTimelineItem.title}”。`
                    : '先输入或确认当前聚焦股票，生成个股事件时间线。'}
                </li>
                <li>
                  {activeCode
                    ? `当前标的 ${activeCode} 已可直接联动到研究与执行页。`
                    : '建议从订阅列表中挑一只股票，避免在全市场日历中漫游。'}
                </li>
                <li>
                  {days <= 7
                    ? '短窗口适合看近端催化；如需排程，切到 14 或 30 天更稳。'
                    : '当前窗口偏长，重点事件较多时可回切 7 天提高辨识度。'}
                </li>
              </ul>
              {activeCode ? (
                <button
                  type="button"
                  onClick={() => openExecution(activeCode)}
                  className="mt-3 rounded-full border border-glass-border bg-white/35 px-4 py-2 text-xs text-text-primary shadow-sm"
                >
                  再联动执行中心
                </button>
              ) : null}
            </div>
          </div>
        </div>
      </section>

      <WorkspaceToolbar
        pageKey="events"
        currentView={currentView}
        onApplyView={(snapshot) => {
          const payload = snapshot as Record<string, unknown>;
          if (typeof payload.code === 'string') setCode(payload.code);
          if (typeof payload.days === 'number' && payload.days > 0) setDays(payload.days);
          if (typeof payload.type === 'string' && payload.type) setType(payload.type);
        }}
        supportsPagePanels
      />

      <WorkspaceSplitLayout
        pageKey="events"
        primary={
          <div className="space-y-4 xl:h-full xl:overflow-y-auto xl:pr-1">
            <SectionCard className="p-4">
              <div className="grid gap-4 2xl:grid-cols-[minmax(0,1.1fr)_minmax(320px,0.9fr)]">
                <div>
                  <h3 className="m-0 font-medium">事件筛选</h3>
                  <div className="mt-3 grid gap-3 sm:grid-cols-3">
                    <StockCodeInput
                      id="events-code"
                      label="股票代码"
                      value={code}
                      onChange={setCode}
                      error={codeError}
                    />
                    <label className="flex flex-col gap-1 text-xs text-text-secondary">
                      <span>事件类型</span>
                      <select
                        value={type}
                        onChange={(event) => setType(event.target.value)}
                        className="rounded border border-border px-2 py-1.5 text-sm"
                      >
                        {EVENT_TYPES.map((item) => (
                          <option key={item.key} value={item.key}>
                            {item.label}
                          </option>
                        ))}
                      </select>
                    </label>
                    <div className="flex items-end gap-2">
                      <button
                        type="button"
                        onClick={() => (isSubscribed ? unsubscribeCurrentCode() : subscribeCurrentCode())}
                        disabled={subscriptionApi.isPending}
                        className={`rounded px-4 py-2 text-sm text-white disabled:opacity-50 ${isSubscribed ? 'bg-slate-700' : 'bg-primary'}`}
                      >
                        {subscriptionApi.isPending
                          ? isSubscribed
                            ? '取消中...'
                            : '订阅中...'
                          : isSubscribed
                            ? '取消事件订阅'
                            : '订阅当前事件'}
                      </button>
                    </div>
                  </div>
                  <div className="mt-3 flex flex-wrap gap-2">
                    {DAY_PRESETS.map((item) => (
                      <button
                        key={item}
                        type="button"
                        onClick={() => setDays(item)}
                        className={`rounded border px-3 py-1 text-xs ${days === item ? 'border-primary text-primary' : 'border-glass-border text-text-secondary'}`}
                      >
                        {item} 天
                      </button>
                    ))}
                  </div>
                </div>
                <div className="rounded-xl border border-glass-border bg-surface-alt/40 p-4">
                  <div className="text-sm font-medium text-text-primary">当前重点</div>
                  <ul className="mb-0 mt-2 space-y-2 pl-4 text-xs leading-5 text-text-secondary">
                    {(importantQ.data?.highlights ?? ['当前窗口内暂无重点事件。']).map((item, index) => (
                      <li key={`${index}:${item}`}>{item}</li>
                    ))}
                  </ul>
                </div>
              </div>
            </SectionCard>

            <KpiGrid cols={4}>
              <KpiCard title="订阅标的" value={subscriptions.length} />
              <KpiCard title="重点事件" value={importantItems.length} />
              <KpiCard title="日历事件" value={calendarQ.data?.count ?? 0} />
              <KpiCard title="个股时间线" value={timelineItems.length} />
            </KpiGrid>

            <SectionCard>
              <div className="flex items-center justify-between gap-3 flex-wrap">
                <div>
                  <h3 className="m-0 font-medium">重点事件</h3>
                  <p className="mb-0 mt-1 text-xs text-text-secondary">
                    优先展示订阅标的和今日/即将发生的高优先级事件。
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => importantQ.refetch()}
                  className="rounded border border-glass-border px-3 py-1 text-xs"
                >
                  刷新重点事件
                </button>
              </div>
              <DataTable
                rows={importantItems as unknown as Record<string, unknown>[]}
                emptyText="暂无重点事件"
                searchable
                rowKey="id"
                onRowClick={(row) => {
                  const nextCode = String(row.code ?? '').trim();
                  if (nextCode) setCode(nextCode);
                }}
                columns={[
                  { key: 'rank', label: '序号' },
                  { key: 'scope', label: '范围' },
                  { key: 'code', label: '代码' },
                  { key: 'title', label: '标题' },
                  { key: 'eventDate', label: '日期' },
                  {
                    key: 'direction',
                    label: '状态',
                    render: (value: unknown) => (
                      <Badge variant={eventBadgeVariant(String(value ?? ''))}>{String(value ?? '-')}</Badge>
                    ),
                  },
                  {
                    key: 'importance',
                    label: '优先级',
                    render: (value: unknown) => (
                      <Badge variant={eventBadgeVariant(String(value ?? ''))}>{String(value ?? '-')}</Badge>
                    ),
                  },
                ]}
              />
            </SectionCard>

            <SectionCard>
              <div className="flex items-center justify-between gap-3 flex-wrap">
                <div>
                  <h3 className="m-0 font-medium">事件日历</h3>
                  <p className="mb-0 mt-1 text-xs text-text-secondary">直接映射未来窗口内的市场事件。</p>
                </div>
                <button
                  type="button"
                  onClick={() => calendarQ.refetch()}
                  className="rounded border border-glass-border px-3 py-1 text-xs"
                >
                  刷新日历
                </button>
              </div>
              <DataTable
                rows={(calendarQ.data?.events ?? []) as unknown as Record<string, unknown>[]}
                emptyText="暂无日历事件"
                rowKey="id"
                columns={[
                  { key: 'eventDate', label: '日期' },
                  { key: 'eventType', label: '类型' },
                  { key: 'code', label: '代码' },
                  { key: 'title', label: '标题' },
                  { key: 'source', label: '来源' },
                ]}
              />
            </SectionCard>
          </div>
        }
        secondary={
          <div className="space-y-4 xl:h-full xl:overflow-y-auto xl:pl-1">
            <SectionCard className="p-4">
              <div className="flex items-center justify-between gap-3 flex-wrap">
                <div>
                  <h3 className="m-0 font-medium">事件订阅</h3>
                  <p className="mb-0 mt-1 text-xs text-text-secondary">
                    订阅列表来自 watchlist 持久化，会参与重点事件聚合。
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => subscriptionsQ.refetch()}
                  className="rounded border border-glass-border px-3 py-1 text-xs"
                >
                  刷新订阅
                </button>
              </div>
              <div className="mt-3 flex flex-wrap gap-2">
                {subscriptions.length > 0 ? (
                  subscriptions.map((item) => (
                    <div
                      key={item.code}
                      className={`flex items-center gap-1 rounded-full border px-2 py-1 text-xs ${activeCode === item.code ? 'border-primary text-primary' : 'border-glass-border text-text-secondary'}`}
                    >
                      <button type="button" onClick={() => setCode(item.code)} className="px-1">
                        {item.code}
                        {item.name ? ` · ${item.name}` : ''}
                      </button>
                      <button
                        type="button"
                        onClick={() => unsubscribeCurrentCode(item.code)}
                        disabled={subscriptionApi.isPending}
                        className="rounded-full border border-current px-2 py-0.5 text-[11px] disabled:opacity-50"
                        aria-label={`取消订阅 ${item.code}`}
                      >
                        取消
                      </button>
                    </div>
                  ))
                ) : (
                  <span className="text-xs text-text-secondary">当前还没有事件订阅。</span>
                )}
              </div>
            </SectionCard>

            <SectionCard className="p-4">
              <div className="flex items-center justify-between gap-3 flex-wrap">
                <div>
                  <h3 className="m-0 font-medium">个股事件时间线</h3>
                  <p className="mb-0 mt-1 text-xs text-text-secondary">
                    聚焦单一标的时，这里会展示最近事件并直接联动研究、执行、详情页。
                  </p>
                </div>
                <div className="flex flex-wrap gap-2">
                  {activeCode ? (
                    <>
                      <button
                        type="button"
                        onClick={() => openStock(activeCode)}
                        className="rounded border border-glass-border px-3 py-1 text-xs"
                      >
                        个股详情
                      </button>
                      <button
                        type="button"
                        onClick={() => openResearch(activeCode)}
                        className="rounded border border-glass-border px-3 py-1 text-xs"
                      >
                        研究事件台
                      </button>
                      <button
                        type="button"
                        onClick={() => openExecution(activeCode)}
                        className="rounded border border-glass-border px-3 py-1 text-xs"
                      >
                        执行中心
                      </button>
                    </>
                  ) : null}
                </div>
              </div>
              <DataTable
                rows={timelineItems as unknown as Record<string, unknown>[]}
                emptyText="当前股票暂无事件时间线"
                rowKey="id"
                columns={[
                  { key: 'eventDate', label: '日期' },
                  { key: 'eventType', label: '类型' },
                  { key: 'title', label: '标题' },
                  {
                    key: 'direction',
                    label: '状态',
                    render: (value: unknown) => (
                      <Badge variant={eventBadgeVariant(String(value ?? ''))}>{String(value ?? '-')}</Badge>
                    ),
                  },
                  {
                    key: 'importance',
                    label: '优先级',
                    render: (value: unknown) => (
                      <Badge variant={eventBadgeVariant(String(value ?? ''))}>{String(value ?? '-')}</Badge>
                    ),
                  },
                  { key: 'source', label: '来源' },
                ]}
              />
            </SectionCard>
          </div>
        }
      />
    </PageContainer>
  );
}
